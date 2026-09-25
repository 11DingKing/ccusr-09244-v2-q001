"""初始化示例数据的兼容入口。"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.seed_data import init_db, seed_data


if __name__ == "__main__":
    init_db()
    seed_data()
