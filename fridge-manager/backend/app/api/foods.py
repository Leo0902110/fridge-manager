"""
食物管理 API
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request, Body
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4
import aiosqlite
import shutil

from app.db.database import get_db
from app.models.food import (
    FoodCreate, FoodUpdate, Food, FoodStatus,
    FoodListResponse, FoodDetailResponse, ShelfLifeReference
)

router = APIRouter()
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


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


def days_for_location(ref: aiosqlite.Row, location: str) -> int:
    """根据保存位置选择参考保质期。0 表示不推荐该保存方式，回退到冷藏。"""
    if location == "freezer":
        days = ref["freezer_days"]
    elif location == "room":
        days = ref["room_temp_days"]
    else:
        days = ref["fridge_days"]
    return days or ref["fridge_days"] or ref["freezer_days"] or ref["room_temp_days"] or 1


async def find_shelf_life_reference(
    db: aiosqlite.Connection,
    food_name: str,
    category: Optional[str] = None,
) -> Optional[aiosqlite.Row]:
    """优先按名称精确/模糊匹配，再按类别给一个保守默认。"""
    cursor = await db.execute(
        "SELECT * FROM shelf_life_reference WHERE food_name = ?",
        (food_name,)
    )
    ref = await cursor.fetchone()
    if ref:
        return ref

    cursor = await db.execute(
        """
        SELECT *
        FROM shelf_life_reference
        WHERE ? LIKE '%' || food_name || '%' OR food_name LIKE '%' || ? || '%'
        ORDER BY LENGTH(food_name) DESC
        LIMIT 1
        """,
        (food_name, food_name)
    )
    ref = await cursor.fetchone()
    if ref:
        return ref

    if category:
        category_defaults = {
            "熟食": "熟食餐盘",
            "剩菜": "剩菜",
            "肉类": "猪肉",
            "海鲜": "鱼",
            "蛋类": "鸡蛋",
            "乳制品": "牛奶",
            "豆制品": "豆腐",
            "主食": "米饭",
            "蔬菜": "白菜",
            "水果": "苹果",
        }
        default_name = category_defaults.get(category)
        if default_name:
            cursor = await db.execute(
                "SELECT * FROM shelf_life_reference WHERE food_name = ?",
                (default_name,)
            )
            return await cursor.fetchone()

    return None


@router.get("", response_model=FoodListResponse)
async def list_foods(
    status: Optional[str] = None,
    location: Optional[str] = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    """获取食物列表"""
    query = "SELECT * FROM foods WHERE 1=1"
    params = []
    
    if status and status not in ("null", "undefined"):
        valid_statuses = {item.value for item in FoodStatus}
        if status not in valid_statuses:
            raise HTTPException(status_code=422, detail="无效的食物状态")
        query += " AND status = ?"
        params.append(status)
    
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
        ref = await find_shelf_life_reference(db, food.name, food.category)
        if ref:
            shelf_life_days = days_for_location(ref, food.location.value)
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
        food.image_url,
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


@router.post("/upload-image")
async def upload_food_image(
    request: Request,
    image: UploadFile = File(...),
):
    """上传食物裁剪图，返回可保存到食物记录的 URL"""
    suffix = Path(image.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        suffix = ".jpg"

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{suffix}"
    file_path = UPLOAD_DIR / filename

    try:
        with file_path.open("wb") as f:
            shutil.copyfileobj(image.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图片保存失败：{str(e)}")

    image_url = str(request.base_url.replace(path=f"uploads/{filename}", query=""))
    return {
        "success": True,
        "data": {
            "image_url": image_url,
        },
        "message": "图片上传成功",
    }


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
    if food_update.shelf_life_days is not None:
        updates.append("shelf_life_days = ?")
        params.append(food_update.shelf_life_days)
        put_date = date.fromisoformat(str(row["put_date"]))
        expiry_date = await calculate_expiry_date(
            put_date,
            food_update.shelf_life_days,
            food_update.location.value if food_update.location else row["location"],
        )
        status = await determine_status(expiry_date, date.today())
        updates.append("expiry_date = ?")
        params.append(expiry_date.isoformat())
        updates.append("status = ?")
        params.append(status.value)
    
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


@router.post("/{food_id}/complete")
async def complete_food(
    food_id: int,
    payload: dict = Body(default={}),
    db: aiosqlite.Connection = Depends(get_db),
):
    """标记食物已处理，并保留一条历史事件用于统计。"""
    event_type = payload.get("action", "eat")
    if event_type not in ("eat", "discard"):
        raise HTTPException(status_code=422, detail="无效的完成类型")

    cursor = await db.execute("SELECT * FROM foods WHERE id = ?", (food_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="食物不存在")

    cursor = await db.execute(
        """
        INSERT INTO food_events (
            food_id, event_type, name, category, image_url, put_date,
            expiry_date, shelf_life_days, location, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["id"],
            event_type,
            row["name"],
            row["category"],
            row["image_url"],
            row["put_date"],
            row["expiry_date"],
            row["shelf_life_days"],
            row["location"],
            row["notes"],
        ),
    )
    event_id = cursor.lastrowid

    await db.execute("DELETE FROM foods WHERE id = ?", (food_id,))
    await db.commit()

    return {
        "success": True,
        "data": {"event_id": event_id, "event_type": event_type},
        "message": "已记录",
    }


@router.delete("/events/{event_id}")
async def delete_food_event(
    event_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    """撤销完成事件。"""
    cursor = await db.execute("DELETE FROM food_events WHERE id = ?", (event_id,))
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"success": True, "message": "已撤销"}


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

    cursor = await db.execute("""
        SELECT event_type, COUNT(*) as count
        FROM food_events
        GROUP BY event_type
    """)
    event_counts = {row["event_type"]: row["count"] for row in await cursor.fetchall()}
    eaten_count = event_counts.get("eat", 0)
    discarded_count = event_counts.get("discard", 0)
    
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
            "eaten_count": eaten_count,
            "discarded_count": discarded_count,
            "total_created_count": total + eaten_count + discarded_count,
            "warning_foods": warning_foods,
        }
    }


@router.get("/reference/shelf-life")
async def get_shelf_life_reference(
    food_name: Optional[str] = None,
    category: Optional[str] = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    """获取保质期参考数据"""
    if food_name:
        ref = await find_shelf_life_reference(db, food_name, category)
        rows = [ref] if ref else []
    elif category:
        cursor = await db.execute(
            "SELECT * FROM shelf_life_reference WHERE category = ? ORDER BY food_name",
            (category,)
        )
        rows = await cursor.fetchall()
    else:
        cursor = await db.execute("SELECT * FROM shelf_life_reference")
        rows = await cursor.fetchall()
    
    return {
        "success": True,
        "data": [dict(row) for row in rows]
    }
