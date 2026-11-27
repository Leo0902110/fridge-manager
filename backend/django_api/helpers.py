"""Shared helpers for Django API views."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import secrets
import shutil
import tempfile
from typing import Optional

import httpx
from django.http import JsonResponse

from app.services.qwen_service import qwen_service
from .models import Food, FoodEvent, Reminder, ShelfLifeReference, UserSession, WeChatUser


UPLOAD_DIR = Path(
    os.getenv(
        "UPLOAD_DIR",
        os.getenv("MEDIA_ROOT", str(Path(__file__).resolve().parents[1] / "uploads")),
    )
)
WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
RECIPE_AI_TIMEOUT_SECONDS = float(os.getenv("RECIPE_AI_TIMEOUT_SECONDS", "6"))
RECIPE_CACHE_TTL_SECONDS = int(os.getenv("RECIPE_CACHE_TTL_SECONDS", "600"))
_recipe_cache: dict[str, tuple[float, dict]] = {}


def success_response(data=None, message: str = "成功", status: int = 200, **extra):
    payload = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return JsonResponse(payload, status=status)


def error_response(message: str, status: int = 400):
    return JsonResponse({"detail": message, "message": message, "success": False}, status=status)


def parse_request_data(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
    if request.method in ("POST", "PUT", "PATCH"):
        return request.POST.dict()
    return request.GET.dict()


def to_iso(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def serialize_food(food: Food) -> dict:
    return {
        "id": food.id,
        "name": food.name,
        "category": food.category,
        "image_url": food.image_url,
        "put_date": to_iso(food.put_date),
        "expiry_date": to_iso(food.expiry_date),
        "shelf_life_days": food.shelf_life_days,
        "status": food.status,
        "location": food.location,
        "notes": food.notes,
        "created_at": to_iso(food.created_at),
        "updated_at": to_iso(food.updated_at),
    }


def is_local_request(request) -> bool:
    host = request.get_host().split(":")[0]
    client_host = request.META.get("REMOTE_ADDR", "")
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    return host in local_hosts or client_host in local_hosts


def allow_dev_login() -> bool:
    return os.getenv("ALLOW_DEV_LOGIN", "false").strip().lower() in ("1", "true", "yes", "on")


def get_session_expire_days() -> int:
    try:
        return int(os.getenv("AUTH_TOKEN_EXPIRE_DAYS", "30"))
    except ValueError:
        return 30


def exchange_code_for_openid(code: str, request) -> dict:
    appid = os.getenv("WECHAT_APPID", "").strip()
    secret = os.getenv("WECHAT_APP_SECRET", "").strip()

    if allow_dev_login():
        return {"openid": os.getenv("DEV_OPENID", "local-dev-openid")}

    if not appid or not secret:
        if is_local_request(request):
            return {"openid": os.getenv("DEV_OPENID", "local-dev-openid")}
        raise ValueError("未配置 WECHAT_APPID / WECHAT_APP_SECRET")

    response = httpx.get(
        WECHAT_CODE2SESSION_URL,
        params={
            "appid": appid,
            "secret": secret,
            "js_code": code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("errcode"):
        raise PermissionError(data.get("errmsg") or "微信登录失败")
    if not data.get("openid"):
        raise PermissionError("微信登录失败：未返回 openid")
    return data


def upsert_user(openid: str, unionid: Optional[str] = None) -> WeChatUser:
    user = WeChatUser.objects.filter(openid=openid).first()
    if user:
        if unionid and user.unionid != unionid:
            user.unionid = unionid
            user.updated_at = datetime.now()
            user.save(update_fields=["unionid", "updated_at"])
        return user

    return WeChatUser.objects.create(
        openid=openid,
        unionid=unionid,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def create_session(user: WeChatUser) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=get_session_expire_days())
    UserSession.objects.create(token=token, user=user, expires_at=expires_at, created_at=datetime.now())
    return token, expires_at.strftime("%Y-%m-%d %H:%M:%S")


def get_current_user(request):
    authorization = request.headers.get("Authorization") or request.META.get("HTTP_AUTHORIZATION")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "", 1).strip()
    session = (
        UserSession.objects.select_related("user")
        .filter(token=token, expires_at__gt=datetime.now())
        .first()
    )
    return session.user if session else None


def require_user(request):
    user = get_current_user(request)
    if not user:
        return None, error_response("登录已过期，请重新进入小程序", status=401)
    return user, None


def build_public_upload_url(request, filename: str) -> str:
    public_base_url = os.getenv("API_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public_base_url:
        return f"{public_base_url}/uploads/{filename}"

    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}/uploads/{filename}"

    return request.build_absolute_uri(f"/uploads/{filename}")


def save_uploaded_image(request, image) -> str:
    suffix = Path(getattr(image, "name", "") or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        suffix = ".jpg"
    filename = f"{secrets.token_hex(16)}{suffix}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / filename
    with file_path.open("wb") as output:
        for chunk in image.chunks():
            output.write(chunk)
    return build_public_upload_url(request, filename)


def parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def determine_status(expiry_date: date, today: date) -> str:
    days_left = (expiry_date - today).days
    if days_left < 0:
        return "expired"
    if days_left <= 3:
        return "warning"
    return "fresh"


def days_for_location(ref: ShelfLifeReference, location: str) -> int:
    if location == "freezer":
        days = ref.freezer_days
    elif location == "room":
        days = ref.room_temp_days
    else:
        days = ref.fridge_days
    return days or ref.fridge_days or ref.freezer_days or ref.room_temp_days or 1


def find_shelf_life_reference(food_name: str, category: Optional[str] = None) -> Optional[ShelfLifeReference]:
    ref = ShelfLifeReference.objects.filter(food_name=food_name).first()
    if ref:
        return ref

    refs = list(ShelfLifeReference.objects.all())
    for candidate in sorted(refs, key=lambda item: len(item.food_name), reverse=True):
        if food_name in candidate.food_name or candidate.food_name in food_name:
            return candidate

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
            return ShelfLifeReference.objects.filter(food_name=default_name).first()
    return None


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
    import hashlib

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


def build_recipe_from_foods(foods: list[dict]) -> dict:
    today = date.today()
    candidates = []
    expired = []

    for food in foods:
        expiry_date = parse_date(food["expiry_date"])
        days_left = (expiry_date - today).days
        enriched = {**food, "days_left": days_left, "role": recipe_role(food.get("category"))}
        if days_left < 0:
            expired.append(enriched)
        elif food.get("location") != "freezer" or days_left <= 3:
            candidates.append(enriched)

    candidates.sort(key=lambda item: (item["days_left"], 0 if item["role"] == "cooked" else 1, item.get("id", 0)))
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

    expired_warnings = [f"{item['name']}已过期{abs(item['days_left'])}天，请先检查并清理。" for item in expired[:3]]
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


def generate_ai_recipe_with_timeout(fallback_recipe: dict) -> Optional[dict]:
    ingredients = fallback_recipe.get("ingredients", [])
    if not ingredients:
        return None
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            qwen_service.generate_recipe_from_inventory,
            ingredients,
            fallback_recipe.get("expired_warnings", []),
        )
        try:
            return future.result(timeout=RECIPE_AI_TIMEOUT_SECONDS)
        except FutureTimeoutError:
            return None
        except Exception:
            return None


def build_reminder_policy(food) -> dict:
    name = food.name
    category = food.category or "其他"
    location = food.location
    days_left = (food.expiry_date - date.today()).days
    location_text = {"fridge": "冷藏", "freezer": "冷冻", "room": "常温"}.get(location, "")

    if days_left < 0:
        return {"level": "expired", "remind_date": date.today(), "message": f"⚠️ 警报：【{name}】已过期，为了健康请及时清理并记录。"}
    if category in ("熟食", "剩菜") and location == "fridge":
        return {"level": "eat-tonight", "remind_date": date.today() + timedelta(days=1), "message": f"昨天的【{name}】还在冰箱，建议今晚解决掉哦！"}
    if category in ("肉类", "海鲜") and location == "fridge":
        return {"level": "cook-soon", "remind_date": date.today() + timedelta(days=2), "message": f"【{location_text}{name}】明天就临期了，今晚要不要安排一下？"}
    if category in ("水果", "蔬菜"):
        return {"level": "best-taste", "remind_date": max(date.today(), food.expiry_date - timedelta(days=1)), "message": f"您的【{name}】快不新鲜啦，赶快吃掉享受最佳口感。"}
    return {"level": "default", "remind_date": max(date.today(), food.expiry_date - timedelta(days=1)), "message": f"【{name}】快到期了，请尽快处理。"}


def save_temp_upload_to_path(image_file) -> str:
    temp_dir = tempfile.mkdtemp()
    suffix = Path(getattr(image_file, "name", "") or "upload.jpg").suffix or ".jpg"
    temp_path = Path(temp_dir) / f"upload{suffix}"
    with temp_path.open("wb") as output:
        for chunk in image_file.chunks():
            output.write(chunk)
    return str(temp_path)


def cleanup_temp_path(temp_path: Optional[str]) -> None:
    if temp_path and os.path.exists(temp_path):
        shutil.rmtree(os.path.dirname(temp_path), ignore_errors=True)