"""旧库结构升级测试：已存在的 operation_data 表应补上 content_hash 列与唯一索引。"""

from sqlalchemy import create_engine

from app.database import ensure_schema_upgrades


def test_ensure_schema_upgrades_adds_content_hash(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path}/old.db", connect_args={"check_same_thread": False}
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE operation_data (
                id INTEGER PRIMARY KEY,
                robot_model_id INTEGER NOT NULL,
                scene_id INTEGER NOT NULL,
                skill_id INTEGER NOT NULL,
                robot_serial VARCHAR(100),
                motion_trajectory JSON NOT NULL,
                perception_records JSON NOT NULL,
                grasp_result JSON,
                timestamp_start DATETIME NOT NULL,
                timestamp_end DATETIME NOT NULL,
                duration_ms INTEGER,
                environment_conditions JSON,
                hardware_status JSON,
                quality_score FLOAT,
                completeness_score FLOAT,
                data_grade VARCHAR(10),
                created_at DATETIME
            )
            """
        )
        conn.exec_driver_sql(
            """
            INSERT INTO operation_data
                (robot_model_id, scene_id, skill_id, motion_trajectory,
                 perception_records, timestamp_start, timestamp_end)
            VALUES (1, 1, 1, '{}', '{}', '2026-01-01 00:00:00', '2026-01-01 00:01:00')
            """
        )

    monkeypatch.setattr("app.database.engine", engine)
    ensure_schema_upgrades()

    with engine.connect() as conn:
        columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(operation_data)")
        }
        assert "content_hash" in columns
        # 已有数据保留，且历史行的 content_hash 为空（不参与去重）
        row = conn.exec_driver_sql(
            "SELECT COUNT(*), COUNT(content_hash) FROM operation_data"
        ).first()
        assert tuple(row) == (1, 0)

    # 重复执行应保持幂等
    ensure_schema_upgrades()
