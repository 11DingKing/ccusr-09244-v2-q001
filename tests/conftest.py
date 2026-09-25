import os
import tempfile

# 在导入应用前指定默认数据库位置，避免在仓库根目录生成 robot_data.db
_TMP_DIR = tempfile.mkdtemp(prefix="robot-data-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DIR}/default.db")
