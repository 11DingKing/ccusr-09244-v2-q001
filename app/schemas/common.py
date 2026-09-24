from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime


class RobotModelBase(BaseModel):
    name: str = Field(..., max_length=100, description="机型名称")
    manufacturer: str = Field(..., max_length=100, description="制造商")
    description: Optional[str] = Field(None, description="机型描述")
    capabilities: Optional[Dict[str, Any]] = Field(None, description="能力列表")


class RobotModelCreate(RobotModelBase):
    pass


class RobotModelUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    manufacturer: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None


class RobotModelResponse(RobotModelBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SceneBase(BaseModel):
    name: str = Field(..., max_length=100, description="场景名称")
    category: str = Field(..., max_length=50, description="场景分类（生产制造/餐饮零售等）")
    description: Optional[str] = Field(None, description="场景描述")
    environment_tags: Optional[List[str]] = Field(None, description="环境标签")


class SceneCreate(SceneBase):
    pass


class SceneUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    environment_tags: Optional[List[str]] = None


class SceneResponse(SceneBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class SkillBase(BaseModel):
    name: str = Field(..., max_length=100, description="技能名称")
    category: str = Field(..., max_length=50, description="技能分类")
    description: Optional[str] = Field(None, description="技能描述")


class SkillCreate(SkillBase):
    pass


class SkillUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None


class SkillResponse(SkillBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
