from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RobotModel, Scene, Skill
from app.schemas.common import (
    RobotModelCreate, RobotModelUpdate, RobotModelResponse,
    SceneCreate, SceneUpdate, SceneResponse,
    SkillCreate, SkillUpdate, SkillResponse
)

router = APIRouter()


@router.get("/robot-models", response_model=List[RobotModelResponse], tags=["基础资源"])
def list_robot_models(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db)
):
    query = db.query(RobotModel)
    if keyword:
        query = query.filter(
            (RobotModel.name.contains(keyword)) |
            (RobotModel.manufacturer.contains(keyword))
        )
    return query.offset(skip).limit(limit).all()


@router.get("/robot-models/{model_id}", response_model=RobotModelResponse, tags=["基础资源"])
def get_robot_model(model_id: int, db: Session = Depends(get_db)):
    model = db.query(RobotModel).filter(RobotModel.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="机型不存在")
    return model


@router.post("/robot-models", response_model=RobotModelResponse, tags=["基础资源"])
def create_robot_model(data: RobotModelCreate, db: Session = Depends(get_db)):
    existing = db.query(RobotModel).filter(RobotModel.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="机型名称已存在")
    model = RobotModel(**data.model_dump())
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


@router.put("/robot-models/{model_id}", response_model=RobotModelResponse, tags=["基础资源"])
def update_robot_model(model_id: int, data: RobotModelUpdate, db: Session = Depends(get_db)):
    model = db.query(RobotModel).filter(RobotModel.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="机型不存在")
    update_data = data.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != model.name:
        existing = db.query(RobotModel).filter(RobotModel.name == update_data["name"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="机型名称已存在")
    for field, value in update_data.items():
        setattr(model, field, value)
    db.commit()
    db.refresh(model)
    return model


@router.delete("/robot-models/{model_id}", tags=["基础资源"])
def delete_robot_model(model_id: int, db: Session = Depends(get_db)):
    model = db.query(RobotModel).filter(RobotModel.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="机型不存在")
    db.delete(model)
    db.commit()
    return {"message": "删除成功"}


@router.get("/scenes", response_model=List[SceneResponse], tags=["基础资源"])
def list_scenes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    category: Optional[str] = Query(None, description="场景分类"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db)
):
    query = db.query(Scene)
    if category:
        query = query.filter(Scene.category == category)
    if keyword:
        query = query.filter(
            (Scene.name.contains(keyword)) |
            (Scene.description.contains(keyword))
        )
    return query.offset(skip).limit(limit).all()


@router.get("/scenes/{scene_id}", response_model=SceneResponse, tags=["基础资源"])
def get_scene(scene_id: int, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    return scene


@router.post("/scenes", response_model=SceneResponse, tags=["基础资源"])
def create_scene(data: SceneCreate, db: Session = Depends(get_db)):
    existing = db.query(Scene).filter(Scene.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="场景名称已存在")
    scene = Scene(**data.model_dump())
    db.add(scene)
    db.commit()
    db.refresh(scene)
    return scene


@router.put("/scenes/{scene_id}", response_model=SceneResponse, tags=["基础资源"])
def update_scene(scene_id: int, data: SceneUpdate, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    update_data = data.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != scene.name:
        existing = db.query(Scene).filter(Scene.name == update_data["name"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="场景名称已存在")
    for field, value in update_data.items():
        setattr(scene, field, value)
    db.commit()
    db.refresh(scene)
    return scene


@router.delete("/scenes/{scene_id}", tags=["基础资源"])
def delete_scene(scene_id: int, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    db.delete(scene)
    db.commit()
    return {"message": "删除成功"}


@router.get("/skills", response_model=List[SkillResponse], tags=["基础资源"])
def list_skills(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    category: Optional[str] = Query(None, description="技能分类"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db)
):
    query = db.query(Skill)
    if category:
        query = query.filter(Skill.category == category)
    if keyword:
        query = query.filter(
            (Skill.name.contains(keyword)) |
            (Skill.description.contains(keyword))
        )
    return query.offset(skip).limit(limit).all()


@router.get("/skills/{skill_id}", response_model=SkillResponse, tags=["基础资源"])
def get_skill(skill_id: int, db: Session = Depends(get_db)):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    return skill


@router.post("/skills", response_model=SkillResponse, tags=["基础资源"])
def create_skill(data: SkillCreate, db: Session = Depends(get_db)):
    existing = db.query(Skill).filter(Skill.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="技能名称已存在")
    skill = Skill(**data.model_dump())
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


@router.put("/skills/{skill_id}", response_model=SkillResponse, tags=["基础资源"])
def update_skill(skill_id: int, data: SkillUpdate, db: Session = Depends(get_db)):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    update_data = data.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != skill.name:
        existing = db.query(Skill).filter(Skill.name == update_data["name"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="技能名称已存在")
    for field, value in update_data.items():
        setattr(skill, field, value)
    db.commit()
    db.refresh(skill)
    return skill


@router.delete("/skills/{skill_id}", tags=["基础资源"])
def delete_skill(skill_id: int, db: Session = Depends(get_db)):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    db.delete(skill)
    db.commit()
    return {"message": "删除成功"}
