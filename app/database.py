from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema_upgrades():
    """对已存在的 SQLite 库做轻量结构升级（create_all 不会修改已有表）。"""
    with engine.begin() as conn:
        columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(operation_data)")
        }
        if columns and "content_hash" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE operation_data ADD COLUMN content_hash VARCHAR(64)"
            )
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_operation_data_content_hash "
            "ON operation_data (content_hash)"
        )
