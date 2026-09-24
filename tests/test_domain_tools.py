from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.policy_catalog import (
    PolicyRule,
    PolicyValidationError,
    make_revision,
    validate_weights,
)
from app.services.windowing import (
    EventPoint,
    WindowError,
    WindowSpec,
    aggregate_windows,
    decode_cursor,
    encode_cursor,
    page_events,
)


UTC = timezone.utc


def test_policy_validation_and_revision():
    weights = validate_weights({"完整度": "0.4", "标注": Decimal("0.6")})
    assert weights["完整度"] == Decimal("0.4")
    revision = make_revision(
        1,
        "默认策略",
        datetime(2025, 1, 1, tzinfo=UTC),
        [
            PolicyRule("low", "低", Decimal("0"), Decimal("0.5")),
            PolicyRule("high", "高", Decimal("0.5"), Decimal("1.01")),
        ],
        weights,
    )
    assert revision.rule_for(Decimal("0.5")).code == "high"


def test_policy_rejects_invalid_sum():
    with pytest.raises(PolicyValidationError):
        validate_weights({"a": 0.2, "b": 0.2})


def test_window_aggregation_and_minimum_count():
    start = datetime(2025, 1, 1, tzinfo=UTC)
    events = [
        EventPoint("a", start + timedelta(minutes=2), 2),
        EventPoint("b", start + timedelta(minutes=8), 4),
    ]
    spec = WindowSpec(start, start + timedelta(minutes=20), timedelta(minutes=10), timedelta(minutes=10), 2)
    rows = aggregate_windows(events, spec)
    assert rows[0].total == 6
    assert rows[0].complete is True


def test_cursor_binds_query_and_rejects_tampering():
    at = datetime(2025, 1, 1, tzinfo=UTC)
    token = encode_cursor(at, "a", {"scene": 1})
    assert decode_cursor(token, {"scene": 1})[1] == "a"
    with pytest.raises(WindowError):
        decode_cursor(token, {"scene": 2})


def test_page_events_has_stable_continuation():
    start = datetime(2025, 1, 1, tzinfo=UTC)
    events = [EventPoint(str(i), start, i) for i in range(4)]
    first, token = page_events(events, 2, query={"all": True})
    second, end = page_events(events, 2, token, query={"all": True})
    assert [item.key for item in first + second] == ["0", "1", "2", "3"]
    assert end is None
