"""批量录入接口的原子性与幂等性测试。

覆盖场景：
- 混合有效/无效数据：整批拒绝，不留部分结果，错误指出原始位置与原因
- 关联对象不存在：400 并列出全部问题位置
- 提交阶段异常：整体回滚，无残留
- 服务重启后完全相同重试：幂等命中，不重复落库
- 单条录入接口行为保持不变
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.models import OperationData, RobotModel, Scene, Skill
from main import app

BATCH_URL = "/api/v1/operations/batch"
SINGLE_URL = "/api/v1/operations"


def _make_session_factory(db_path):
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)


@pytest.fixture()
def env(tmp_path):
    db_path = tmp_path / "test.db"
    engine, session_factory = _make_session_factory(db_path)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = session_factory()
    db.add(RobotModel(id=1, name="RM-65A", manufacturer="RealMotion"))
    db.add(Scene(id=1, name="电子装配线", category="生产制造"))
    db.add(Skill(id=1, name="精密抓取", category="抓取"))
    db.commit()
    db.close()

    holder = SimpleNamespace(
        client=TestClient(app),
        db_path=db_path,
        engine=engine,
        session_factory=session_factory,
    )
    yield holder

    app.dependency_overrides.clear()
    holder.engine.dispose()


def restart_service(env):
    """模拟服务重启：丢弃全部连接，用同一数据库文件重建引擎与会话工厂。"""
    env.engine.dispose()
    engine, session_factory = _make_session_factory(env.db_path)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    env.engine = engine
    env.session_factory = session_factory


def make_item(serial="RB-001", start="2026-09-25T08:00:00Z", **overrides):
    item = {
        "robot_model_id": 1,
        "scene_id": 1,
        "skill_id": 1,
        "robot_serial": serial,
        "motion_trajectory": {"points": [[0, 0, 0], [1, 1, 1]]},
        "perception_records": {"frames": 12},
        "grasp_result": {"success": True},
        "timestamp_start": start,
        "timestamp_end": "2026-09-25T08:05:00Z",
        "duration_ms": 300000,
        "environment_conditions": {"temperature": 25},
        "hardware_status": {"battery": 0.9},
    }
    item.update(overrides)
    return item


def operation_rows(env):
    db = env.session_factory()
    try:
        return db.query(OperationData).order_by(OperationData.id).all()
    finally:
        db.close()


def test_all_valid_batch_commits_atomically(env):
    payload = [make_item(serial=f"RB-00{i}") for i in range(3)]
    resp = env.client.post(BATCH_URL, json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["success_count"] == 3
    assert body["failure_count"] == 0
    assert [r["index"] for r in body["results"]] == [0, 1, 2]
    assert all(r["success"] for r in body["results"])
    assert all(r["deduplicated"] is False for r in body["results"])

    rows = operation_rows(env)
    assert len(rows) == 3
    assert [r["data"]["id"] for r in body["results"]] == [row.id for row in rows]
    assert all(row.content_hash for row in rows)


def test_mixed_valid_and_invalid_rejects_whole_batch(env):
    payload = [
        make_item(serial="RB-101"),
        make_item(serial="RB-102", scene_id=999),
        make_item(serial="RB-103"),
    ]
    resp = env.client.post(BATCH_URL, json=payload)

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["item_errors"] == [
        {"index": 1, "errors": ["场景ID 999 不存在"]}
    ]
    # 原子边界：有效记录也不允许留下部分结果
    assert operation_rows(env) == []


def test_missing_references_report_all_positions(env):
    payload = [
        make_item(serial="RB-201", robot_model_id=404),
        make_item(serial="RB-202", scene_id=405, skill_id=406),
        make_item(serial="RB-203"),
    ]
    resp = env.client.post(BATCH_URL, json=payload)

    assert resp.status_code == 400
    item_errors = resp.json()["detail"]["item_errors"]
    assert item_errors == [
        {"index": 0, "errors": ["机型ID 404 不存在"]},
        {"index": 1, "errors": ["场景ID 405 不存在", "技能ID 406 不存在"]},
    ]
    assert operation_rows(env) == []


def test_duplicate_within_batch_rejected(env):
    payload = [make_item(serial="RB-301"), make_item(serial="RB-301")]
    resp = env.client.post(BATCH_URL, json=payload)

    assert resp.status_code == 400
    item_errors = resp.json()["detail"]["item_errors"]
    assert item_errors[0]["index"] == 1
    assert "第 0 条" in item_errors[0]["errors"][0]
    assert operation_rows(env) == []


def test_commit_failure_rolls_back_everything(env, monkeypatch):
    def failing_commit(self):
        raise SQLAlchemyError("模拟提交阶段异常")

    monkeypatch.setattr(Session, "commit", failing_commit)

    payload = [make_item(serial=f"RB-40{i}") for i in range(3)]
    resp = env.client.post(BATCH_URL, json=payload)

    assert resp.status_code == 500
    assert "整批已回滚" in resp.json()["detail"]
    assert operation_rows(env) == []


def test_identical_retry_after_restart_is_idempotent(env):
    payload = [make_item(serial=f"RB-50{i}") for i in range(3)]

    first = env.client.post(BATCH_URL, json=payload)
    assert first.status_code == 200
    first_ids = [r["data"]["id"] for r in first.json()["results"]]
    assert len(operation_rows(env)) == 3

    restart_service(env)

    retry = env.client.post(BATCH_URL, json=payload)
    assert retry.status_code == 200
    body = retry.json()
    assert body["success_count"] == 3
    assert body["failure_count"] == 0
    assert all(r["deduplicated"] for r in body["results"])
    assert [r["data"]["id"] for r in body["results"]] == first_ids

    # 重启后的完全相同重试没有产生任何新行
    rows = operation_rows(env)
    assert len(rows) == 3
    assert [row.id for row in rows] == first_ids


def test_partial_overlap_retry_only_inserts_new_records(env):
    item_a = make_item(serial="RB-601")
    item_b = make_item(serial="RB-602")
    item_c = make_item(serial="RB-603")

    assert env.client.post(BATCH_URL, json=[item_a, item_b]).status_code == 200

    resp = env.client.post(BATCH_URL, json=[item_b, item_c])
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["deduplicated"] is True
    assert results[1]["deduplicated"] is False

    rows = operation_rows(env)
    assert len(rows) == 3
    assert results[0]["data"]["id"] == rows[1].id


def test_single_create_behavior_unchanged(env):
    valid = make_item(serial="RB-701")
    resp = env.client.post(SINGLE_URL, json=valid)
    assert resp.status_code == 200
    assert resp.json()["robot_serial"] == "RB-701"

    missing_ref = env.client.post(SINGLE_URL, json=make_item(serial="RB-702", skill_id=999))
    assert missing_ref.status_code == 400
    assert missing_ref.json()["detail"] == "技能不存在"

    # 单条接口保持现有行为：不做内容去重，相同内容重复提交仍各自落库
    again = env.client.post(SINGLE_URL, json=valid)
    assert again.status_code == 200
    rows = operation_rows(env)
    assert len(rows) == 2
    assert all(row.content_hash is None for row in rows)
