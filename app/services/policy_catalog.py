"""质量策略目录与确定性评估工具。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class PolicyRule:
    """一条可审计的质量规则。"""

    code: str
    label: str
    minimum: Decimal
    maximum: Decimal
    enabled: bool = True
    tags: tuple[str, ...] = ()

    def contains(self, value: Decimal) -> bool:
        return self.enabled and self.minimum <= value < self.maximum

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "minimum": str(self.minimum),
            "maximum": str(self.maximum),
            "enabled": self.enabled,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class PolicyRevision:
    """策略版本的不可变描述。"""

    revision: int
    name: str
    effective_at: datetime
    rules: tuple[PolicyRule, ...]
    weights: Mapping[str, Decimal]
    scope: Mapping[str, str] = field(default_factory=dict)
    note: str = ""

    def rule_for(self, score: Decimal) -> PolicyRule | None:
        for rule in self.rules:
            if rule.contains(score):
                return rule
        return None

    def applies_to(self, attributes: Mapping[str, str]) -> bool:
        return all(attributes.get(key) == value for key, value in self.scope.items())

    def fingerprint(self) -> str:
        parts = [str(self.revision), self.name, self.effective_at.isoformat()]
        parts.extend(f"{key}={value}" for key, value in sorted(self.weights.items()))
        parts.extend(f"{key}={value}" for key, value in sorted(self.scope.items()))
        parts.extend(f"{rule.code}:{rule.minimum}:{rule.maximum}" for rule in self.rules)
        return "|".join(parts)


class PolicyValidationError(ValueError):
    """策略无法发布时抛出的领域错误。"""


def as_decimal(value: Any, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PolicyValidationError(f"{field_name} 必须是数字") from exc
    if not result.is_finite():
        raise PolicyValidationError(f"{field_name} 不能是无穷或非数字")
    return result


def validate_weights(weights: Mapping[str, Any], *, tolerance: Decimal = Decimal("0.000001")) -> dict[str, Decimal]:
    if not weights:
        raise PolicyValidationError("至少需要一项权重")
    converted = {str(key): as_decimal(value, str(key)) for key, value in weights.items()}
    if any(value < 0 or value > 1 for value in converted.values()):
        raise PolicyValidationError("权重必须位于零到一之间")
    total = sum(converted.values(), Decimal("0"))
    if abs(total - Decimal("1")) > tolerance:
        raise PolicyValidationError("权重总和必须等于一")
    return converted


def validate_rules(rules: Iterable[PolicyRule]) -> tuple[PolicyRule, ...]:
    ordered = tuple(rules)
    if not ordered:
        raise PolicyValidationError("至少需要一条分级规则")
    seen: set[str] = set()
    previous: Decimal | None = None
    for rule in ordered:
        if not rule.code or rule.code in seen:
            raise PolicyValidationError("规则编码必须唯一且非空")
        if rule.minimum >= rule.maximum:
            raise PolicyValidationError(f"规则 {rule.code} 的区间无效")
        if previous is not None and rule.minimum < previous:
            raise PolicyValidationError("规则区间必须按下界递增")
        seen.add(rule.code)
        previous = rule.maximum
    return ordered


def make_revision(
    revision: int,
    name: str,
    effective_at: datetime,
    rules: Iterable[PolicyRule],
    weights: Mapping[str, Any],
    scope: Mapping[str, str] | None = None,
    note: str = "",
) -> PolicyRevision:
    if revision < 1:
        raise PolicyValidationError("版本号必须从一开始")
    if effective_at.tzinfo is None:
        raise PolicyValidationError("生效时间必须带时区")
    return PolicyRevision(
        revision=revision,
        name=name.strip(),
        effective_at=effective_at.astimezone(timezone.utc),
        rules=validate_rules(rules),
        weights=validate_weights(weights),
        scope=dict(scope or {}),
        note=note.strip(),
    )


class PolicyCatalog:
    """维护策略草稿、发布版本和按时点解析。"""

    def __init__(self) -> None:
        self._revisions: dict[int, PolicyRevision] = {}
        self._drafts: dict[str, PolicyRevision] = {}

    def add_draft(self, key: str, revision: PolicyRevision) -> None:
        if not key.strip():
            raise PolicyValidationError("草稿键不能为空")
        if revision.revision in self._revisions:
            raise PolicyValidationError("已发布版本不能覆盖")
        self._drafts[key] = revision

    def publish(self, key: str, *, expected_revision: int | None = None) -> PolicyRevision:
        revision = self._drafts.get(key)
        if revision is None:
            raise PolicyValidationError("草稿不存在")
        if expected_revision is not None and revision.revision != expected_revision:
            raise PolicyValidationError("草稿版本已变化")
        if self._revisions and revision.revision <= max(self._revisions):
            raise PolicyValidationError("新版本号必须递增")
        self._revisions[revision.revision] = revision
        del self._drafts[key]
        return revision

    def resolve(self, at: datetime, attributes: Mapping[str, str] | None = None) -> PolicyRevision | None:
        if at.tzinfo is None:
            raise PolicyValidationError("解析时间必须带时区")
        candidates = [item for item in self._revisions.values() if item.effective_at <= at.astimezone(timezone.utc)]
        if attributes is not None:
            candidates = [item for item in candidates if item.applies_to(attributes)]
        return max(candidates, key=lambda item: (item.effective_at, item.revision), default=None)

    def compare(self, left: int, right: int, scores: Iterable[Decimal]) -> list[dict[str, Any]]:
        if left not in self._revisions or right not in self._revisions:
            raise PolicyValidationError("比较版本不存在")
        result: list[dict[str, Any]] = []
        for raw_score in scores:
            score = as_decimal(raw_score, "score")
            left_rule = self._revisions[left].rule_for(score)
            right_rule = self._revisions[right].rule_for(score)
            result.append({"score": str(score), "left": left_rule.code if left_rule else None, "right": right_rule.code if right_rule else None, "changed": (left_rule.code if left_rule else None) != (right_rule.code if right_rule else None)})
        return result

    def audit_rows(self) -> list[dict[str, Any]]:
        return [
            {"revision": item.revision, "name": item.name, "effective_at": item.effective_at.isoformat(), "fingerprint": item.fingerprint(), "scope": dict(item.scope)}
            for item in sorted(self._revisions.values(), key=lambda value: value.revision)
        ]
