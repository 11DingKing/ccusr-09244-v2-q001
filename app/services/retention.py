"""数据保留、冻结和归档判定的纯领域实现。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterable, Mapping


class RetentionError(ValueError):
    """保留策略参数不合法。"""


class RecordState(str, Enum):
    ACTIVE = "active"
    HELD = "held"
    ELIGIBLE = "eligible"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class RetentionRule:
    rule_id: str
    category: str
    keep_for: timedelta
    priority: int = 0
    enabled: bool = True

    def validate(self) -> "RetentionRule":
        if not self.rule_id.strip() or not self.category.strip():
            raise RetentionError("规则标识和类别不能为空")
        if self.keep_for <= timedelta(0):
            raise RetentionError("保留时长必须为正")
        if self.priority < 0:
            raise RetentionError("优先级不能为负")
        return self


@dataclass(frozen=True)
class Hold:
    hold_id: str
    subject_id: str
    opened_at: datetime
    reason: str
    closed_at: datetime | None = None

    def active_at(self, moment: datetime) -> bool:
        if self.opened_at.tzinfo is None or moment.tzinfo is None:
            raise RetentionError("冻结时间必须带时区")
        current = moment.astimezone(timezone.utc)
        opened = self.opened_at.astimezone(timezone.utc)
        closed = self.closed_at.astimezone(timezone.utc) if self.closed_at else None
        return opened <= current and (closed is None or current < closed)


@dataclass(frozen=True)
class RetentionCandidate:
    subject_id: str
    category: str
    created_at: datetime
    state: RecordState = RecordState.ACTIVE
    rule_id: str | None = None
    hold_ids: tuple[str, ...] = ()

    def age_at(self, moment: datetime) -> timedelta:
        if self.created_at.tzinfo is None or moment.tzinfo is None:
            raise RetentionError("记录时间必须带时区")
        return moment.astimezone(timezone.utc) - self.created_at.astimezone(timezone.utc)


@dataclass(frozen=True)
class ArchiveDecision:
    subject_id: str
    state: RecordState
    rule_id: str | None
    reason: str
    effective_at: datetime


def validate_rules(rules: Iterable[RetentionRule]) -> tuple[RetentionRule, ...]:
    checked = tuple(rule.validate() for rule in rules)
    if len({rule.rule_id for rule in checked}) != len(checked):
        raise RetentionError("规则标识必须唯一")
    if len({rule.category for rule in checked}) != len(checked):
        raise RetentionError("同一类别只能配置一条规则")
    return checked


def choose_rule(rules: Iterable[RetentionRule], category: str) -> RetentionRule | None:
    candidates = [rule for rule in rules if rule.enabled and rule.category == category]
    return max(candidates, key=lambda rule: (rule.priority, rule.keep_for), default=None)


def decide_candidate(
    candidate: RetentionCandidate,
    rules: Iterable[RetentionRule],
    holds: Iterable[Hold],
    moment: datetime,
) -> ArchiveDecision:
    if moment.tzinfo is None:
        raise RetentionError("判断时间必须带时区")
    current = moment.astimezone(timezone.utc)
    if candidate.state == RecordState.ARCHIVED:
        return ArchiveDecision(candidate.subject_id, RecordState.ARCHIVED, candidate.rule_id, "已归档", current)
    active_holds = [hold for hold in holds if hold.subject_id == candidate.subject_id and hold.active_at(current)]
    if active_holds:
        return ArchiveDecision(candidate.subject_id, RecordState.HELD, candidate.rule_id, "存在有效冻结", current)
    rule = choose_rule(rules, candidate.category)
    if rule is None:
        return ArchiveDecision(candidate.subject_id, RecordState.ACTIVE, None, "没有适用策略", current)
    if candidate.age_at(current) >= rule.keep_for:
        return ArchiveDecision(candidate.subject_id, RecordState.ELIGIBLE, rule.rule_id, "达到保留期限", current)
    return ArchiveDecision(candidate.subject_id, RecordState.ACTIVE, rule.rule_id, "尚未达到期限", current)


class RetentionLedger:
    """在内存中维护策略、冻结和决策，供服务层复用。"""

    def __init__(self, rules: Iterable[RetentionRule] = ()) -> None:
        self.rules = list(validate_rules(rules))
        self.holds: dict[str, Hold] = {}
        self.decisions: dict[tuple[str, str], ArchiveDecision] = {}

    def replace_rules(self, rules: Iterable[RetentionRule]) -> None:
        self.rules = list(validate_rules(rules))

    def open_hold(self, hold: Hold) -> Hold:
        if not hold.hold_id or not hold.subject_id or not hold.reason.strip():
            raise RetentionError("冻结需要标识、对象和原因")
        if hold.opened_at.tzinfo is None or (hold.closed_at and hold.closed_at.tzinfo is None):
            raise RetentionError("冻结时间必须带时区")
        existing = self.holds.get(hold.hold_id)
        if existing and existing != hold:
            raise RetentionError("冻结标识已被其他内容使用")
        self.holds[hold.hold_id] = hold
        return hold

    def close_hold(self, hold_id: str, closed_at: datetime) -> Hold:
        if closed_at.tzinfo is None:
            raise RetentionError("解除时间必须带时区")
        hold = self.holds.get(hold_id)
        if hold is None:
            raise RetentionError("冻结不存在")
        if closed_at < hold.opened_at:
            raise RetentionError("解除时间不能早于冻结时间")
        updated = Hold(hold.hold_id, hold.subject_id, hold.opened_at, hold.reason, closed_at)
        self.holds[hold_id] = updated
        return updated

    def decide(self, candidate: RetentionCandidate, moment: datetime) -> ArchiveDecision:
        decision = decide_candidate(candidate, self.rules, self.holds.values(), moment)
        key = (candidate.subject_id, decision.effective_at.isoformat())
        self.decisions[key] = decision
        return decision

    def batch_decide(self, candidates: Iterable[RetentionCandidate], moment: datetime) -> list[ArchiveDecision]:
        ordered = sorted(candidates, key=lambda item: (item.created_at, item.subject_id))
        return [self.decide(candidate, moment) for candidate in ordered]

    def active_holds_for(self, subject_id: str, moment: datetime) -> list[Hold]:
        return sorted((hold for hold in self.holds.values() if hold.subject_id == subject_id and hold.active_at(moment)), key=lambda hold: hold.hold_id)

    def explain(self, subject_id: str, moment: datetime) -> dict[str, object]:
        holds = self.active_holds_for(subject_id, moment)
        decisions = [value for value in self.decisions.values() if value.subject_id == subject_id]
        latest = max(decisions, key=lambda value: value.effective_at, default=None)
        return {"subject_id": subject_id, "holds": [hold.hold_id for hold in holds], "latest": latest.reason if latest else None, "state": latest.state.value if latest else RecordState.ACTIVE.value}


@dataclass(frozen=True)
class RetentionSummary:
    """一批保留决策的稳定摘要。"""

    active: int
    held: int
    eligible: int
    archived: int
    by_rule: Mapping[str, int]

    @property
    def total(self) -> int:
        return self.active + self.held + self.eligible + self.archived

    def as_dict(self) -> dict[str, object]:
        return {
            "active": self.active,
            "held": self.held,
            "eligible": self.eligible,
            "archived": self.archived,
            "total": self.total,
            "by_rule": dict(sorted(self.by_rule.items())),
        }


def summarize_decisions(decisions: Iterable[ArchiveDecision]) -> RetentionSummary:
    counters = {state: 0 for state in RecordState}
    by_rule: dict[str, int] = {}
    for decision in decisions:
        counters[decision.state] += 1
        if decision.rule_id:
            by_rule[decision.rule_id] = by_rule.get(decision.rule_id, 0) + 1
    return RetentionSummary(
        active=counters[RecordState.ACTIVE],
        held=counters[RecordState.HELD],
        eligible=counters[RecordState.ELIGIBLE],
        archived=counters[RecordState.ARCHIVED],
        by_rule=by_rule,
    )


def next_due_at(candidate: RetentionCandidate, rules: Iterable[RetentionRule]) -> datetime | None:
    rule = choose_rule(rules, candidate.category)
    if rule is None or candidate.state == RecordState.ARCHIVED:
        return None
    return candidate.created_at.astimezone(timezone.utc) + rule.keep_for


def partition_candidates(
    candidates: Iterable[RetentionCandidate],
    rules: Iterable[RetentionRule],
    holds: Iterable[Hold],
    moment: datetime,
) -> dict[RecordState, list[RetentionCandidate]]:
    result = {state: [] for state in RecordState}
    rules = tuple(rules)
    holds = tuple(holds)
    for candidate in candidates:
        decision = decide_candidate(candidate, rules, holds, moment)
        result[decision.state].append(candidate)
    for values in result.values():
        values.sort(key=lambda item: (item.created_at, item.subject_id))
    return result


def validate_hold_intervals(holds: Iterable[Hold]) -> tuple[Hold, ...]:
    ordered = sorted(holds, key=lambda item: (item.subject_id, item.opened_at, item.hold_id))
    seen: set[str] = set()
    previous_by_subject: dict[str, Hold] = {}
    for hold in ordered:
        if hold.hold_id in seen:
            raise RetentionError("冻结标识重复")
        if hold.opened_at.tzinfo is None or (hold.closed_at and hold.closed_at.tzinfo is None):
            raise RetentionError("冻结区间必须带时区")
        if hold.closed_at and hold.closed_at < hold.opened_at:
            raise RetentionError("冻结结束时间早于开始时间")
        previous = previous_by_subject.get(hold.subject_id)
        if previous and previous.closed_at is None:
            raise RetentionError("同一对象存在未关闭冻结")
        if previous and previous.closed_at and hold.opened_at < previous.closed_at:
            raise RetentionError("同一对象的冻结区间重叠")
        seen.add(hold.hold_id)
        previous_by_subject[hold.subject_id] = hold
    return tuple(ordered)


def retention_headers(summary: RetentionSummary) -> tuple[tuple[str, str], ...]:
    """为接口导出生成稳定的统计表头。"""
    return (
        ("active", str(summary.active)),
        ("held", str(summary.held)),
        ("eligible", str(summary.eligible)),
        ("archived", str(summary.archived)),
        ("total", str(summary.total)),
    )


def is_deletable(decision: ArchiveDecision) -> bool:
    """只有已确认可归档的记录才允许清理原始载荷。"""
    return decision.state == RecordState.ELIGIBLE and decision.rule_id is not None


def decision_key(decision: ArchiveDecision) -> tuple[str, str]:
    """返回可用于幂等存储的决策键。"""
    return decision.subject_id, decision.effective_at.astimezone(timezone.utc).isoformat()


def sort_decisions(decisions: Iterable[ArchiveDecision]) -> list[ArchiveDecision]:
    """按对象和生效时间稳定排序。"""
    return sorted(decisions, key=lambda item: decision_key(item))


def state_counts(decisions: Iterable[ArchiveDecision]) -> dict[str, int]:
    """将决策数量转换为接口可直接序列化的映射。"""
    summary = summarize_decisions(decisions)
    return {key: value for key, value in retention_headers(summary)}


def can_release(subject_id: str, holds: Iterable[Hold], moment: datetime) -> bool:
    """判断对象在指定时点是否没有有效冻结。"""
    if not subject_id.strip():
        raise RetentionError("对象标识不能为空")
    if moment.tzinfo is None:
        raise RetentionError("判断时间必须带时区")
    return not any(hold.subject_id == subject_id and hold.active_at(moment) for hold in holds)


def active_rule_ids(rules: Iterable[RetentionRule]) -> tuple[str, ...]:
    """返回已启用规则的稳定标识。"""
    return tuple(sorted(rule.rule_id for rule in rules if rule.enabled))


def rule_count(rules: Iterable[RetentionRule]) -> int:
    """返回有效规则数量。"""
    return len(active_rule_ids(rules))
