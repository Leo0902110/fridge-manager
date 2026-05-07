"""
食物管理 API
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request, Body
import asyncio
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from typing import Optional
from uuid import uuid4
import aiosqlite
import os
import shutil
import time

from app.db.database import get_db
from app.api.auth import get_current_user
from app.models.food import (
    FoodCreate, FoodUpdate, Food, FoodStatus,
    FoodListResponse, FoodDetailResponse, ShelfLifeReference
)
from app.services.qwen_service import qwen_service

router = APIRouter()
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
RECIPE_CACHE_TTL_SECONDS = int(os.getenv("RECIPE_CACHE_TTL_SECONDS", "600"))
RECIPE_AI_TIMEOUT_SECONDS = float(os.getenv("RECIPE_AI_TIMEOUT_SECONDS", "6"))
_recipe_cache: dict[str, tuple[float, dict]] = {}


def row_to_food(row: aiosqlite.Row) -> Food:
    return Food.model_validate(dict(row))


def build_public_upload_url(request: Request, filename: str) -> str:
    """生成可被小程序访问的上传图片地址。正式环境优先使用 HTTPS 公网域名。"""
    public_base_url = os.getenv("API_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public_base_url:
        return f"{public_base_url}/uploads/{filename}"

    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}/uploads/{filename}"

    return str(request.base_url.replace(path=f"uploads/{filename}", query=""))


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
            "水果": "常见水果",
        }
        default_name = category_defaults.get(category)
        if default_name:
            cursor = await db.execute(
                "SELECT * FROM shelf_life_reference WHERE food_name = ?",
                (default_name,)
            )
            return await cursor.fetchone()

    return None


def parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def recipe_role(category: Optional[str]) -> str:
    if category in ("肉类", "海鲜", "蛋类", "豆制品"):
        return "protein"
    if category in ("蔬菜", "水果"):
        return "fresh"
    if category in ("主食",):
        return "staple"
    if category in ("熟食", "剩菜"):
        return "cooked"
    return "other"


def recipe_cache_key(user_id: int, foods: list[dict]) -> str:
    payload = [
        {
            "id": food.get("id"),
            "name": food.get("name"),
            "category": food.get("category"),
            "location": food.get("location"),
            "expiry_date": str(food.get("expiry_date")),
            "updated_at": str(food.get("updated_at")),
        }
        for food in foods
    ]
    raw = json.dumps({"user_id": user_id, "foods": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def generate_ai_recipe_with_timeout(fallback_recipe: dict) -> Optional[dict]:
    ingredients = fallback_recipe.get("ingredients", [])
    if not ingredients:
        return None

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                qwen_service.generate_recipe_from_inventory,
                ingredients,
                fallback_recipe.get("expired_warnings", []),
            ),
            timeout=RECIPE_AI_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return None
    except Exception:
        return None


def build_recipe_from_foods(foods: list[dict]) -> dict:
    today = date.today()
    candidates = []
    expired = []

    for food in foods:
        expiry_date = parse_date(food["expiry_date"])
        days_left = (expiry_date - today).days
        enriched = {
            **food,
            "days_left": days_left,
            "role": recipe_role(food.get("category")),
        }
        if days_left < 0:
            expired.append(enriched)
        elif food.get("location") != "freezer" or days_left <= 3:
            candidates.append(enriched)

    candidates.sort(key=lambda item: (
        item["days_left"],
        0 if item["role"] == "cooked" else 1,
        item.get("id", 0),
    ))

    urgent = [item for item in candidates if item["days_left"] <= 3 or item["role"] == "cooked"]
    pool = urgent or candidates
    selected = pool[:5]

    if not selected:
        freezer = [food for food in foods if food.get("location") == "freezer"]
        selected = freezer[:3]

    if not selected:
        return {
            "title": "先添加食材",
            "subtitle": "冰箱里还没有可用于生成菜谱的食物。",
            "priority": "empty",
            "ingredients": [],
            "steps": [],
            "tips": ["添加食物后，这里会优先使用临期食材生成菜谱。"],
            "expired_warnings": [],
            "source": "rule",
        }

    names = [item["name"] for item in selected]
    cooked = [item for item in selected if item["role"] == "cooked"]
    protein = [item for item in selected if item["role"] == "protein"]
    fresh = [item for item in selected if item["role"] == "fresh"]
    fruits = [item for item in fresh if item.get("category") == "水果"]
    vegetables = [item for item in fresh if item.get("category") == "蔬菜"]
    staple = [item for item in selected if item["role"] == "staple"]

    if cooked:
        title = f"{cooked[0]['name']}快手加热餐"
        method = "复热"
    elif protein and vegetables:
        title = f"{protein[0]['name']}炒{vegetables[0]['name']}"
        method = "快炒"
    elif fresh and len(fruits) == len(fresh) and not protein:
        title = f"{fruits[0]['name']}水果碗"
        method = "冷食"
    elif protein:
        title = f"{protein[0]['name']}煎烤便餐"
        method = "煎烤"
    elif fresh:
        title = f"{fresh[0]['name']}清爽小菜"
        method = "凉拌或快炒"
    else:
        title = f"{names[0]}简餐"
        method = "组合"

    ingredients = [
        {
            "id": item["id"],
            "name": item["name"],
            "category": item.get("category") or "其他",
            "days_left": item["days_left"],
            "reason": "今天优先" if item["days_left"] <= 0 else f"{item['days_left']}天内处理",
        }
        for item in selected
    ]

    cooking_items = cooked or protein + vegetables + staple or vegetables or fresh or selected
    cooking_names = [item["name"] for item in cooking_items[:3]]

    if method == "冷食":
        steps = [
            f"先处理 {', '.join(cooking_names)}，检查是否有软烂、异味或霉点。",
            "冲洗后沥干，切成适口大小。",
            "直接做水果碗；家里有酸奶、燕麦或坚果时可以少量搭配。",
        ]
    else:
        steps = [
            f"先处理 {cooking_names[0]}，检查气味和状态，过期或异常的不要食用。",
            f"把 {', '.join(cooking_names)} 切成适口大小，按易熟程度分开放。",
            f"用{method}方式完成主菜，熟食和剩菜需要彻底加热。",
        ]

    if staple and method != "冷食":
        steps.append(f"搭配 {staple[0]['name']} 做主食，优先把临期食材吃完。")
    elif method != "冷食":
        steps.append("可以搭配米饭、面包或面条，做成一顿完整简餐。")
    else:
        steps.append("水果类临期时不建议加热久放，今天吃掉口感最好。")

    if fruits and method != "冷食":
        steps.append(f"{fruits[0]['name']}不放进主菜，作为饭后水果或单独水果碗今天吃掉。")

    expired_warnings = [
        f"{item['name']}已过期{abs(item['days_left'])}天，请先检查并清理。"
        for item in expired[:3]
    ]

    return {
        "title": title,
        "subtitle": f"优先消耗：{'、'.join(names[:4])}",
        "priority": "urgent" if any(item["days_left"] <= 1 for item in selected) else "normal",
        "ingredients": ingredients,
        "steps": steps,
        "tips": [
            "熟食和剩菜复热要彻底。",
            "临期食材优先使用，冷冻食材不必抢在今天处理。",
            "水果和肉类不硬凑成菜，不适合烹饪搭配时单独食用。",
        ],
        "expired_warnings": expired_warnings,
        "source": "rule",
    }


@router.get("", response_model=FoodListResponse)
async def list_foods(
    status: Optional[str] = None,
    location: Optional[str] = None,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取食物列表"""
    query = "SELECT * FROM foods WHERE user_id = ?"
    params = [current_user["id"]]
    
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
    
    foods = [row_to_food(row) for row in rows]
    
    return FoodListResponse(
        data=foods,
        count=len(foods),
        message=f"成功获取 {len(foods)} 条记录"
    )


@router.get("/recipe/today")
async def get_today_recipe(
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """根据当前用户的库存和过期时间生成一份今日菜谱。"""
    cursor = await db.execute(
        """
        SELECT *
        FROM foods
        WHERE user_id = ?
        ORDER BY expiry_date ASC, id ASC
        """,
        (current_user["id"],),
    )
    foods = [dict(row) for row in await cursor.fetchall()]
    cache_key = recipe_cache_key(current_user["id"], foods)
    cached = _recipe_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] <= RECIPE_CACHE_TTL_SECONDS:
        recipe = {
            **cached[1],
            "cached": True,
        }
        return {
            "success": True,
            "data": recipe,
            "message": "菜谱生成成功",
        }

    fallback_recipe = build_recipe_from_foods(foods)
    ai_recipe = await generate_ai_recipe_with_timeout(fallback_recipe)
    recipe = {
        **(ai_recipe or fallback_recipe),
        "cached": False,
    }
    _recipe_cache[cache_key] = (now, recipe)

    return {
        "success": True,
        "data": recipe,
        "message": "菜谱生成成功",
    }


@router.get("/{food_id}", response_model=FoodDetailResponse)
async def get_food(
    food_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取单个食物详情"""
    cursor = await db.execute(
        "SELECT * FROM foods WHERE id = ? AND user_id = ?",
        (food_id, current_user["id"]),
    )
    row = await cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="食物不存在")
    
    return FoodDetailResponse(data=row_to_food(row))


@router.post("", response_model=FoodDetailResponse)
async def create_food(
    food: FoodCreate,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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
        INSERT INTO foods (user_id, name, category, image_url, put_date, expiry_date, shelf_life_days, status, location, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        current_user["id"],
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
    cursor = await db.execute(
        "SELECT * FROM foods WHERE id = ? AND user_id = ?",
        (food_id, current_user["id"]),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="食物创建失败")
    
    return FoodDetailResponse(
        data=row_to_food(row),
        message="添加成功"
    )


@router.post("/upload-image")
async def upload_food_image(
    request: Request,
    image: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
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

    image_url = build_public_upload_url(request, filename)
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
    current_user: dict = Depends(get_current_user),
):
    """更新食物信息"""
    # 检查是否存在
    cursor = await db.execute(
        "SELECT * FROM foods WHERE id = ? AND user_id = ?",
        (food_id, current_user["id"]),
    )
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
    
    params.append(current_user["id"])
    query = f"UPDATE foods SET {', '.join(updates)} WHERE id = ? AND user_id = ?"
    await db.execute(query, params)
    await db.commit()
    
    # 获取更新后的食物
    cursor = await db.execute(
        "SELECT * FROM foods WHERE id = ? AND user_id = ?",
        (food_id, current_user["id"]),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="食物不存在")
    
    return FoodDetailResponse(data=row_to_food(row))


@router.delete("/{food_id}")
async def delete_food(
    food_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除食物"""
    cursor = await db.execute(
        "DELETE FROM foods WHERE id = ? AND user_id = ?",
        (food_id, current_user["id"]),
    )
    await db.commit()
    
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="食物不存在")
    
    return {"success": True, "message": "删除成功"}


@router.post("/{food_id}/complete")
async def complete_food(
    food_id: int,
    payload: dict = Body(default={}),
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """标记食物已处理，并保留一条历史事件用于统计。"""
    event_type = payload.get("action", "eat")
    if event_type not in ("eat", "discard"):
        raise HTTPException(status_code=422, detail="无效的完成类型")

    cursor = await db.execute(
        "SELECT * FROM foods WHERE id = ? AND user_id = ?",
        (food_id, current_user["id"]),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="食物不存在")

    cursor = await db.execute(
        """
        INSERT INTO food_events (
            user_id, food_id, event_type, name, category, image_url, put_date,
            expiry_date, shelf_life_days, location, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            current_user["id"],
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

    await db.execute(
        "DELETE FROM foods WHERE id = ? AND user_id = ?",
        (food_id, current_user["id"]),
    )
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
    current_user: dict = Depends(get_current_user),
):
    """撤销完成事件。"""
    cursor = await db.execute(
        "DELETE FROM food_events WHERE id = ? AND user_id = ?",
        (event_id, current_user["id"]),
    )
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"success": True, "message": "已撤销"}


@router.get("/stats/overview")
async def get_overview(
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取冰箱概览统计"""
    today = date.today()
    
    # 总数
    cursor = await db.execute("SELECT COUNT(*) as total FROM foods WHERE user_id = ?", (current_user["id"],))
    total_row = await cursor.fetchone()
    total = total_row["total"] if total_row else 0
    
    # 各状态数量
    cursor = await db.execute("""
        SELECT status, COUNT(*) as count 
        FROM foods 
        WHERE user_id = ?
        GROUP BY status
    """, (current_user["id"],))
    status_counts = {row["status"]: row["count"] for row in await cursor.fetchall()}

    cursor = await db.execute("""
        SELECT event_type, COUNT(*) as count
        FROM food_events
        WHERE user_id = ?
        GROUP BY event_type
    """, (current_user["id"],))
    event_counts = {row["event_type"]: row["count"] for row in await cursor.fetchall()}
    eaten_count = event_counts.get("eat", 0)
    discarded_count = event_counts.get("discard", 0)
    
    # 临期食物（3 天内过期）
    cursor = await db.execute("""
        SELECT * FROM foods 
        WHERE user_id = ? AND expiry_date BETWEEN date(?) AND date(?, '+3 days')
        ORDER BY expiry_date ASC
    """, (current_user["id"], today.isoformat(), today.isoformat()))
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
