"""
食物管理 API
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import date, timedelta
from typing import Optional
import aiosqlite

from app.db.database import get_db
from app.models.food import (
    FoodCreate, FoodUpdate, Food, FoodStatus,
    FoodListResponse, FoodDetailResponse, ShelfLifeReference
)

router = APIRouter()


async def calculate_expiry_date(put_date: date, shelf_life_days: int, location: str) -> date:
    """计算过期日期"""
    return put_date + timedelta(days=shelf_life_days)


async def determine_status(expiry_date: date, today: date) -> FoodStatus:
    """根据过期日期判断状态"""
    days_left = (expiry_date - today).days
    if days_left < 0:
        return FoodStatus.EXPIRED
    elif days_left <= 3:
        return FoodStatus.WARNING
    return FoodStatus.FRESH


@router.get("", response_model=FoodListResponse)
async def list_foods(
    status: Optional[FoodStatus] = None,
    location: Optional[str] = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    """获取食物列表"""
    query = "SELECT * FROM foods WHERE 1=1"
    params = []
    
    if status:
        query += " AND status = ?"
        params.append(status.value)
    
    if location:
        query += " AND location = ?"
        params.append(location)
    
    query += " ORDER BY expiry_date ASC"
    
    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    
    foods = [dict(row) for row in rows]
    
    return FoodListResponse(
        data=foods,
        count=len(foods),
        message=f"成功获取 {len(foods)} 条记录"
    )


@router.get("/{food_id}", response_model=FoodDetailResponse)
async def get_food(
    food_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    """获取单个食物详情"""
    cursor = await db.execute("SELECT * FROM foods WHERE id = ?", (food_id,))
    row = await cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="食物不存在")
    
    return FoodDetailResponse(data=dict(row))


@router.post("", response_model=FoodDetailResponse)
async def create_food(
    food: FoodCreate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """添加新食物"""
    today = date.today()
    
    # 如果没有指定期限，查询参考表
    shelf_life_days = food.shelf_life_days
    if not shelf_life_days:
        cursor = await db.execute(
            "SELECT fridge_days, freezer_days, room_temp_days FROM shelf_life_reference WHERE food_name = ?",
            (food.name,)
        )
        ref = await cursor.fetchone()
        if ref:
            if food.location == "fridge":
                shelf_life_days = ref["fridge_days"]
            elif food.location == "freezer":
                shelf_life_days = ref["freezer_days"]
            else:
                shelf_life_days = ref["room_temp_days"]
        else:
            # 默认 7 天
            shelf_life_days = 7
    
    expiry_date = await calculate_expiry_date(food.put_date, shelf_life_days, food.location)
    status = await determine_status(expiry_date, today)
    
    cursor = await db.execute("""
        INSERT INTO foods (name, category, image_url, put_date, expiry_date, shelf_life_days, status, location, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        food.name,
        food.category,
        None,
        food.put_date,
        expiry_date,
        shelf_life_days,
        status.value,
        food.location.value,
        food.notes,
    ))
    
    await db.commit()
    food_id = cursor.lastrowid
    
    # 获取刚插入的食物
    cursor = await db.execute("SELECT * FROM foods WHERE id = ?", (food_id,))
    row = await cursor.fetchone()
    
    return FoodDetailResponse(
        data=dict(row),
        message="添加成功"
    )


@router.put("/{food_id}", response_model=FoodDetailResponse)
async def update_food(
    food_id: int,
    food_update: FoodUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """更新食物信息"""
    # 检查是否存在
    cursor = await db.execute("SELECT * FROM foods WHERE id = ?", (food_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="食物不存在")
    
    # 构建更新字段
    updates = []
    params = []
    
    if food_update.name is not None:
        updates.append("name = ?")
        params.append(food_update.name)
    if food_update.status is not None:
        updates.append("status = ?")
        params.append(food_update.status.value)
    if food_update.notes is not None:
        updates.append("notes = ?")
        params.append(food_update.notes)
    if food_update.location is not None:
        updates.append("location = ?")
        params.append(food_update.location.value)
    
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(food_id)
    
    query = f"UPDATE foods SET {', '.join(updates)} WHERE id = ?"
    await db.execute(query, params)
    await db.commit()
    
    # 获取更新后的食物
    cursor = await db.execute("SELECT * FROM foods WHERE id = ?", (food_id,))
    row = await cursor.fetchone()
    
    return FoodDetailResponse(data=dict(row))


@router.delete("/{food_id}")
async def delete_food(
    food_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    """删除食物"""
    cursor = await db.execute("DELETE FROM foods WHERE id = ?", (food_id,))
    await db.commit()
    
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="食物不存在")
    
    return {"success": True, "message": "删除成功"}


@router.get("/stats/overview")
async def get_overview(
    db: aiosqlite.Connection = Depends(get_db),
):
    """获取冰箱概览统计"""
    today = date.today()
    
    # 总数
    cursor = await db.execute("SELECT COUNT(*) as total FROM foods")
    total = (await cursor.fetchone())["total"]
    
    # 各状态数量
    cursor = await db.execute("""
        SELECT status, COUNT(*) as count 
        FROM foods 
        GROUP BY status
    """)
    status_counts = {row["status"]: row["count"] for row in await cursor.fetchall()}
    
    # 临期食物（3 天内过期）
    cursor = await db.execute("""
        SELECT * FROM foods 
        WHERE expiry_date BETWEEN date(?) AND date(?, '+3 days')
        ORDER BY expiry_date ASC
    """, (today.isoformat(), today.isoformat()))
    warning_foods = [dict(row) for row in await cursor.fetchall()]
    
    return {
        "success": True,
        "data": {
            "total": total,
            "fresh_count": status_counts.get("fresh", 0),
            "warning_count": status_counts.get("warning", 0),
            "expired_count": status_counts.get("expired", 0),
            "warning_foods": warning_foods,
        }
    }


@router.get("/reference/shelf-life")
async def get_shelf_life_reference(
    food_name: Optional[str] = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    """获取保质期参考数据"""
    if food_name:
        cursor = await db.execute(
            "SELECT * FROM shelf_life_reference WHERE food_name LIKE ?",
            (f"%{food_name}%",)
        )
    else:
        cursor = await db.execute("SELECT * FROM shelf_life_reference")
    
    rows = await cursor.fetchall()
    
    return {
        "success": True,
        "data": [dict(row) for row in rows]
    }
