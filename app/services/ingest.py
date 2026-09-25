"""批量入库的幂等支持。

采集端重试时请求体完全相同，因此对每条记录的全部录入字段做规范化哈希，
作为落库的去重键（写入 ``operation_data.content_hash``，带唯一约束）。
哈希持久化在数据库中，服务重启后仍然有效。
"""

import hashlib
import json

from app.schemas.operation import OperationDataCreate


def compute_content_hash(data: OperationDataCreate) -> str:
    """对单条录入请求计算稳定的内容哈希。

    使用 JSON 模式导出（时间字段统一为 ISO 格式）并按键排序序列化，
    保证语义相同的请求体无论何时提交都得到相同的哈希值。
    """
    payload = data.model_dump(mode="json")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
