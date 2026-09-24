"""机器人作业记录批量上报的写入链路。

整批请求共享同一个事务边界：先做完全部输入校验与关联资源检查（只读，不落库），
再在同一事务内逐条 flush、最后统一 commit。任何一条失败都会 rollback，
此前 flush 的记录一并撤销，绝不留下部分结果。

成功的批次会以规范化请求内容的指纹作为幂等键持久化；采集端用完全相同的载荷
重试时直接返回首次写入的记录，不再重复落库（指纹入库，服务重启后依然生效）。
"""

import hashlib
import json
from datetime import date, datetime
from typing import Any, List

from sqlalchemy.orm import Session

from app.models import BatchUpload, OperationData, RobotModel, Scene, Skill
from app.schemas.operation import (
    BatchOperationResponse,
    BatchOperationResultItem,
    OperationDataCreate,
    OperationDataResponse,
)


class BatchRequestError(Exception):
    """整批请求失败。phase 标识失败阶段，errors 给出原始输入位置与原因。"""

    def __init__(self, phase: str, message: str, errors: List[dict]):
        super().__init__(message)
        self.phase = phase
        self.message = message
        self.errors = errors


def _json_default(obj: Any):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"无法序列化类型 {type(obj).__name__}")


def compute_fingerprint(data_list: List[OperationDataCreate]) -> str:
    """对规范化后的整批请求内容计算稳定指纹（与字段顺序、Unicode 写法无关）。"""
    payload = [item.model_dump() for item in data_list]
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _existing_batch(db: Session, fingerprint: str) -> BatchUpload | None:
    return (
        db.query(BatchUpload)
        .filter(BatchUpload.request_fingerprint == fingerprint)
        .first()
    )


def _build_response(operations: List[OperationData], *, replayed: bool) -> BatchOperationResponse:
    results = [
        BatchOperationResultItem(
            index=op.batch_seq if op.batch_seq is not None else idx,
            success=True,
            data=OperationDataResponse.model_validate(op),
        )
        for idx, op in enumerate(operations)
    ]
    return BatchOperationResponse(
        total=len(operations),
        success_count=len(operations),
        failure_count=0,
        results=results,
        replayed=replayed,
    )


def create_operation_batch(
    db: Session, data_list: List[OperationDataCreate]
) -> BatchOperationResponse:
    if not data_list:
        raise BatchRequestError(
            "validation", "批量上报内容为空", [{"index": None, "reasons": ["至少提交一条作业记录"]}]
        )

    fingerprint = compute_fingerprint(data_list)

    # 幂等：完全相同的重试直接复用首次结果，不重复写入。
    existing = _existing_batch(db, fingerprint)
    if existing is not None:
        operations = (
            db.query(OperationData)
            .filter(OperationData.batch_id == existing.id)
            .order_by(OperationData.batch_seq)
            .all()
        )
        return _build_response(operations, replayed=True)

    # ---- 阶段一：校验 + 关联资源检查（全部只读，任何一条失败整批拒绝）----
    robot_model_ids = {data.robot_model_id for data in data_list}
    scene_ids = {data.scene_id for data in data_list}
    skill_ids = {data.skill_id for data in data_list}

    valid_robot_models = {
        m.id for m in db.query(RobotModel).filter(RobotModel.id.in_(robot_model_ids)).all()
    }
    valid_scenes = {
        s.id for s in db.query(Scene).filter(Scene.id.in_(scene_ids)).all()
    }
    valid_skills = {
        s.id for s in db.query(Skill).filter(Skill.id.in_(skill_ids)).all()
    }

    errors: List[dict] = []
    for index, data in enumerate(data_list):
        reasons = []
        if data.robot_model_id not in valid_robot_models:
            reasons.append(f"机型ID {data.robot_model_id} 不存在")
        if data.scene_id not in valid_scenes:
            reasons.append(f"场景ID {data.scene_id} 不存在")
        if data.skill_id not in valid_skills:
            reasons.append(f"技能ID {data.skill_id} 不存在")
        if reasons:
            errors.append({"index": index, "reasons": reasons})

    if errors:
        raise BatchRequestError(
            "validation", "批量上报校验失败，整批请求未写入任何记录", errors
        )

    # ---- 阶段二：同一事务内保存全部记录，统一提交 ----
    def _replay_existing():
        # 并发的相同批次可能已抢先提交（唯一指纹冲突）——复用其结果。
        prior = _existing_batch(db, fingerprint)
        if prior is None:
            return None
        rows = (
            db.query(OperationData)
            .filter(OperationData.batch_id == prior.id)
            .order_by(OperationData.batch_seq)
            .all()
        )
        return _build_response(rows, replayed=True)

    batch = BatchUpload(request_fingerprint=fingerprint, total_items=len(data_list))
    db.add(batch)

    try:
        db.flush()  # 取 batch.id；尚未 commit（指纹唯一冲突在此或 commit 时暴露）

        for index, data in enumerate(data_list):
            operation = OperationData(
                batch_id=batch.id,
                batch_seq=index,
                **data.model_dump(),
            )
            db.add(operation)
            try:
                # 仅 flush 到当前事务；失败时靠外层 rollback 撤销本批此前全部写入。
                db.flush()
            except Exception as exc:
                db.rollback()
                replay = _replay_existing()
                if replay is not None:
                    return replay
                raise BatchRequestError(
                    "save",
                    "批量上报保存失败，整批请求已回滚，未写入任何记录",
                    [{"index": index, "reasons": [f"记录写入数据库失败: {exc.orig if getattr(exc, 'orig', None) else exc}"]}],
                ) from exc

        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            replay = _replay_existing()
            if replay is not None:
                return replay
            raise BatchRequestError(
                "save",
                "批量上报提交失败，整批请求已回滚，未写入任何记录",
                [{"index": None, "reasons": [f"事务提交失败: {exc}"]}],
            ) from exc
    except BatchRequestError:
        raise
    except Exception as exc:
        db.rollback()
        replay = _replay_existing()
        if replay is not None:
            return replay
        raise BatchRequestError(
            "save",
            "批量上报保存失败，整批请求已回滚，未写入任何记录",
            [{"index": None, "reasons": [f"批次初始化失败: {exc.orig if getattr(exc, 'orig', None) else exc}"]}],
        ) from exc

    # expire_on_commit 后访问属性会按主键重新加载，会话仍开启。
    operations = (
        db.query(OperationData)
        .filter(OperationData.batch_id == batch.id)
        .order_by(OperationData.batch_seq)
        .all()
    )
    return _build_response(operations, replayed=False)
