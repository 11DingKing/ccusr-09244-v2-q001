"""按业务时间处理记录窗口和可恢复游标。"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Iterable, Sequence


class WindowError(ValueError):
    """窗口或游标不符合约束。"""


@dataclass(frozen=True)
class EventPoint:
    key: str
    happened_at: datetime
    value: float
    group: str = ""

    def normalized(self) -> "EventPoint":
        if self.happened_at.tzinfo is None:
            raise WindowError("事件时间必须带时区")
        return EventPoint(self.key, self.happened_at.astimezone(timezone.utc), float(self.value), self.group)


@dataclass(frozen=True)
class WindowSpec:
    start: datetime
    end: datetime
    width: timedelta
    step: timedelta
    minimum_count: int = 1

    def validate(self) -> "WindowSpec":
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise WindowError("窗口边界必须带时区")
        if self.start >= self.end or self.width <= timedelta(0) or self.step <= timedelta(0):
            raise WindowError("窗口范围和步长必须为正")
        if self.minimum_count < 0:
            raise WindowError("最小样本数不能为负")
        if self.width > self.end - self.start:
            raise WindowError("窗口宽度不能超过查询范围")
        return self


@dataclass(frozen=True)
class WindowResult:
    start: datetime
    end: datetime
    keys: tuple[str, ...]
    total: float
    count: int
    complete: bool

    @property
    def average(self) -> float | None:
        return self.total / self.count if self.count else None


def sort_events(events: Iterable[EventPoint]) -> list[EventPoint]:
    normalized = [event.normalized() for event in events]
    if len({event.key for event in normalized}) != len(normalized):
        raise WindowError("事件键必须唯一")
    return sorted(normalized, key=lambda event: (event.happened_at, event.key))


def build_windows(spec: WindowSpec) -> list[tuple[datetime, datetime]]:
    spec.validate()
    start = spec.start.astimezone(timezone.utc)
    end = spec.end.astimezone(timezone.utc)
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor + spec.width <= end:
        windows.append((cursor, cursor + spec.width))
        cursor += spec.step
    return windows


def aggregate_windows(events: Sequence[EventPoint], spec: WindowSpec) -> list[WindowResult]:
    ordered = sort_events(events)
    results: list[WindowResult] = []
    for start, end in build_windows(spec):
        members = [event for event in ordered if start <= event.happened_at < end]
        results.append(WindowResult(start, end, tuple(event.key for event in members), sum(event.value for event in members), len(members), len(members) >= spec.minimum_count))
    return results


def incremental_windows(events: Sequence[EventPoint], spec: WindowSpec, changed_at: datetime) -> list[WindowResult]:
    if changed_at.tzinfo is None:
        raise WindowError("变更时间必须带时区")
    changed = changed_at.astimezone(timezone.utc)
    return [item for item in aggregate_windows(events, spec) if item.start <= changed < item.end]


def encode_cursor(sort_key: datetime, identity: str, query: dict[str, Any]) -> str:
    if sort_key.tzinfo is None or not identity:
        raise WindowError("游标需要带时区的排序时间和标识")
    payload = {"at": sort_key.astimezone(timezone.utc).isoformat(), "id": identity, "query": query}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    payload["digest"] = sha256(raw).hexdigest()[:16]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def decode_cursor(token: str, query: dict[str, Any]) -> tuple[datetime, str]:
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        digest = payload.pop("digest")
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        if sha256(raw).hexdigest()[:16] != digest or payload["query"] != query:
            raise WindowError("游标与查询条件不匹配")
        at = datetime.fromisoformat(payload["at"])
        if at.tzinfo is None:
            raise WindowError("游标时间缺少时区")
        return at.astimezone(timezone.utc), str(payload["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise WindowError("游标格式无效") from exc


def page_events(events: Sequence[EventPoint], limit: int, cursor: str | None = None, query: dict[str, Any] | None = None) -> tuple[list[EventPoint], str | None]:
    if limit < 1 or limit > 500:
        raise WindowError("分页大小必须位于一到五百之间")
    query = dict(query or {})
    ordered = sort_events(events)
    if cursor:
        at, identity = decode_cursor(cursor, query)
        ordered = [event for event in ordered if (event.happened_at, event.key) > (at, identity)]
    page = ordered[:limit]
    if len(ordered) <= limit:
        return page, None
    last = page[-1]
    return page, encode_cursor(last.happened_at, last.key, query)
