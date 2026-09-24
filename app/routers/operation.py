from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.database import get_db
from app.models import OperationData, RobotModel, Scene, Skill, Annotation
from app.schemas.operation import (
    OperationDataCreate, OperationDataUpdate, OperationDataResponse,
    OperationDataListResponse, BatchOperationResponse, BatchOperationResultItem,
    AnnotationCreate, AnnotationUpdate, AnnotationResponse
)

router = APIRouter()


@router.get("/operations", response_model=OperationDataListResponse, tags=["作业数据"])
def list_operation_data(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    robot_model_id: Optional[int] = Query(None, description="机型ID过滤"),
    scene_id: Optional[int] = Query(None, description="场景ID过滤"),
    skill_id: Optional[int] = Query(None, description="技能ID过滤"),
    robot_serial: Optional[str] = Query(None, description="机器人序列号过滤"),
    data_grade: Optional[str] = Query(None, description="数据等级过滤"),
    is_annotated: Optional[bool] = Query(None, description="是否已标注"),
    is_success: Optional[bool] = Query(None, description="标注成功/失败"),
    failure_category: Optional[str] = Query(None, description="失败大类过滤"),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size

    query = db.query(OperationData)

    if robot_model_id:
        query = query.filter(OperationData.robot_model_id == robot_model_id)
    if scene_id:
        query = query.filter(OperationData.scene_id == scene_id)
    if skill_id:
        query = query.filter(OperationData.skill_id == skill_id)
    if robot_serial:
        query = query.filter(OperationData.robot_serial == robot_serial)
    if data_grade:
        query = query.filter(OperationData.data_grade == data_grade)

    if is_annotated is not None or is_success is not None or failure_category:
        query = query.outerjoin(Annotation, OperationData.id == Annotation.operation_data_id)
        if is_annotated is True:
            query = query.filter(Annotation.id.isnot(None))
        elif is_annotated is False:
            query = query.filter(Annotation.id.is_(None))
        if is_success is not None:
            query = query.filter(Annotation.is_success == is_success)
        if failure_category:
            query = query.filter(Annotation.failure_category == failure_category)

    total = query.count()
    items = query.order_by(OperationData.created_at.desc()).offset(skip).limit(page_size).all()

    return OperationDataListResponse(
        total=total,
        items=items,
        page=page,
        page_size=page_size
    )


@router.get("/operations/{operation_id}", response_model=OperationDataResponse, tags=["作业数据"])
def get_operation_data(operation_id: int, db: Session = Depends(get_db)):
    data = db.query(OperationData).filter(OperationData.id == operation_id).first()
    if not data:
        raise HTTPException(status_code=404, detail="作业数据不存在")
    return data


@router.post("/operations", response_model=OperationDataResponse, tags=["作业数据"])
def create_operation_data(data: OperationDataCreate, db: Session = Depends(get_db)):
    robot_model = db.query(RobotModel).filter(RobotModel.id == data.robot_model_id).first()
    if not robot_model:
        raise HTTPException(status_code=400, detail="机型不存在")
    scene = db.query(Scene).filter(Scene.id == data.scene_id).first()
    if not scene:
        raise HTTPException(status_code=400, detail="场景不存在")
    skill = db.query(Skill).filter(Skill.id == data.skill_id).first()
    if not skill:
        raise HTTPException(status_code=400, detail="技能不存在")

    operation = OperationData(**data.model_dump())
    db.add(operation)
    db.commit()
    db.refresh(operation)
    return operation


@router.post("/operations/batch", response_model=BatchOperationResponse, tags=["作业数据"])
def create_operation_data_batch(data_list: List[OperationDataCreate], db: Session = Depends(get_db)):
    total = len(data_list)
    results: List[BatchOperationResultItem] = []
    success_count = 0
    failure_count = 0

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

    for index, data in enumerate(data_list):
        errors = []
        if data.robot_model_id not in valid_robot_models:
            errors.append(f"机型ID {data.robot_model_id} 不存在")
        if data.scene_id not in valid_scenes:
            errors.append(f"场景ID {data.scene_id} 不存在")
        if data.skill_id not in valid_skills:
            errors.append(f"技能ID {data.skill_id} 不存在")

        if errors:
            failure_count += 1
            results.append(BatchOperationResultItem(
                index=index,
                success=False,
                error="; ".join(errors)
            ))
            continue

        try:
            operation = OperationData(**data.model_dump())
            db.add(operation)
            db.flush()
            db.refresh(operation)
            db.commit()
            success_count += 1
            results.append(BatchOperationResultItem(
                index=index,
                success=True,
                data=operation
            ))
        except Exception as e:
            db.rollback()
            failure_count += 1
            results.append(BatchOperationResultItem(
                index=index,
                success=False,
                error=str(e)
            ))

    return BatchOperationResponse(
        total=total,
        success_count=success_count,
        failure_count=failure_count,
        results=results
    )


@router.put("/operations/{operation_id}", response_model=OperationDataResponse, tags=["作业数据"])
def update_operation_data(operation_id: int, data: OperationDataUpdate, db: Session = Depends(get_db)):
    operation = db.query(OperationData).filter(OperationData.id == operation_id).first()
    if not operation:
        raise HTTPException(status_code=404, detail="作业数据不存在")
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(operation, field, value)
    db.commit()
    db.refresh(operation)
    return operation


@router.delete("/operations/{operation_id}", tags=["作业数据"])
def delete_operation_data(operation_id: int, db: Session = Depends(get_db)):
    operation = db.query(OperationData).filter(OperationData.id == operation_id).first()
    if not operation:
        raise HTTPException(status_code=404, detail="作业数据不存在")
    db.delete(operation)
    db.commit()
    return {"message": "删除成功"}


@router.get("/operations/{operation_id}/annotation", response_model=AnnotationResponse, tags=["标注管理"])
def get_annotation_by_operation(operation_id: int, db: Session = Depends(get_db)):
    annotation = db.query(Annotation).filter(Annotation.operation_data_id == operation_id).first()
    if not annotation:
        raise HTTPException(status_code=404, detail="该作业数据尚未标注")
    return annotation


@router.get("/annotations", response_model=List[AnnotationResponse], tags=["标注管理"])
def list_annotations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    is_success: Optional[bool] = Query(None, description="是否成功"),
    failure_category: Optional[str] = Query(None, description="失败大类"),
    review_status: Optional[str] = Query(None, description="审核状态"),
    annotator: Optional[str] = Query(None, description="标注人"),
    db: Session = Depends(get_db)
):
    query = db.query(Annotation)
    if is_success is not None:
        query = query.filter(Annotation.is_success == is_success)
    if failure_category:
        query = query.filter(Annotation.failure_category == failure_category)
    if review_status:
        query = query.filter(Annotation.review_status == review_status)
    if annotator:
        query = query.filter(Annotation.annotator == annotator)
    return query.order_by(Annotation.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/annotations/{annotation_id}", response_model=AnnotationResponse, tags=["标注管理"])
def get_annotation(annotation_id: int, db: Session = Depends(get_db)):
    annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=404, detail="标注记录不存在")
    return annotation


@router.post("/annotations", response_model=AnnotationResponse, tags=["标注管理"])
def create_annotation(data: AnnotationCreate, db: Session = Depends(get_db)):
    operation = db.query(OperationData).filter(OperationData.id == data.operation_data_id).first()
    if not operation:
        raise HTTPException(status_code=400, detail="作业数据不存在")
    existing = db.query(Annotation).filter(Annotation.operation_data_id == data.operation_data_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="该作业数据已存在标注记录，请使用更新接口")

    if not data.is_success and not data.failure_category:
        raise HTTPException(status_code=400, detail="标注失败时必须指定失败大类")

    annotation = Annotation(**data.model_dump())
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return annotation


@router.put("/annotations/{annotation_id}", response_model=AnnotationResponse, tags=["标注管理"])
def update_annotation(annotation_id: int, data: AnnotationUpdate, db: Session = Depends(get_db)):
    annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=404, detail="标注记录不存在")
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(annotation, field, value)
    db.commit()
    db.refresh(annotation)
    return annotation


@router.delete("/annotations/{annotation_id}", tags=["标注管理"])
def delete_annotation(annotation_id: int, db: Session = Depends(get_db)):
    annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=404, detail="标注记录不存在")
    db.delete(annotation)
    db.commit()
    return {"message": "删除成功"}


FAILURE_CATEGORIES = [
    {"category": "感知异常", "subcategories": ["视觉识别失败", "深度传感器异常", "目标丢失", "光照不足"]},
    {"category": "运动控制异常", "subcategories": ["轨迹偏差超限", "关节超限", "碰撞检测触发", "速度异常"]},
    {"category": "抓取异常", "subcategories": ["抓取力不足", "物体滑脱", "姿态错误", "真空吸盘失效"]},
    {"category": "环境干扰", "subcategories": ["粉尘干扰", "温度异常", "振动干扰", "电磁干扰"]},
    {"category": "硬件故障", "subcategories": ["电机故障", "编码器异常", "通信中断", "电源异常"]},
    {"category": "其他", "subcategories": ["未知错误", "人为干预"]}
]


@router.get("/failure-categories", tags=["标注管理"])
def get_failure_categories():
    return FAILURE_CATEGORIES
