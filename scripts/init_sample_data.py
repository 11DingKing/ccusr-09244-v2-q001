"""初始化示例数据的兼容入口。"""

from app.seed_data import init_db, seed_data


if __name__ == "__main__":
    init_db()
    seed_data()
