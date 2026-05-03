"""
食物数据模型
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
from enum import Enum


class FoodStatus(str, Enum):
    """食物状态"""
    FRESH = "fresh"       # 新鲜
    WARNING = "warning"   # 临期
    EXPIRED = "expired"   # 过期


class FoodLocation(str, Enum):
    """存放位置"""
    FRIDGE = "fridge"     # 冷藏
    FREEZER = "freezer"   # 冷冻
    ROOM = "room"         # 常温


class FoodBase(BaseModel):
    """食物基础模型"""
    name: str = Field(..., description="食物名称")
    category: Optional[str] = Field(None, description="食物类别")
    image_url: Optional[str] = Field(None, description="食物图片 URL")
    location: FoodLocation = Field(default=FoodLocation.FRIDGE, description="存放位置")
    notes: Optional[str] = Field(None, description="备注")


class FoodCreate(FoodBase):
    """创建食物"""
    put_date: date = Field(default_factory=date.today, description="放入日期")
    shelf_life_days: Optional[int] = Field(None, description="保质期天数")


class FoodUpdate(BaseModel):
    """更新食物"""
    name: Optional[str] = None
    status: Optional[FoodStatus] = None
    notes: Optional[str] = None
    location: Optional[FoodLocation] = None


class Food(FoodBase):
    """食物完整模型"""
    id: int
    image_url: Optional[str] = None
    put_date: date
    expiry_date: date
    shelf_life_days: Optional[int] = None
    status: FoodStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FoodListResponse(BaseModel):
    """食物列表响应"""
    success: bool = True
    message: str = "获取成功"
    data: list[Food]
    count: int


class FoodDetailResponse(BaseModel):
    """食物详情响应"""
    success: bool = True
    message: str = "获取成功"
    data: Food


class ShelfLifeReference(BaseModel):
    """保质期参考"""
    food_name: str
    category: Optional[str] = None
    fridge_days: int
    freezer_days: int
    room_temp_days: int
    recommended_location: str = "fridge"
    storage_tip: Optional[str] = None
