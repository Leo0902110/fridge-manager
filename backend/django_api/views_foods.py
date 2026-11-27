from datetime import date, datetime, timedelta
import time

from django.db.models import Count
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .helpers import (
    build_recipe_from_foods,
    days_for_location,
    determine_status,
    error_response,
    find_shelf_life_reference,
    generate_ai_recipe_with_timeout,
    parse_request_data,
    recipe_cache_key,
    require_user,
    save_uploaded_image,
    serialize_food,
    success_response,
    _recipe_cache,
    RECIPE_CACHE_TTL_SECONDS,
)
from .models import Food, FoodEvent, ShelfLifeReference


def foods_collection(request):
    if request.method == "GET":
        return list_foods(request)
    if request.method == "POST":
        return create_food(request)
    return error_response("不支持的请求方法", status=405)


def food_item_dispatch(request, food_id: int):
    if request.method == "GET":
        return food_detail(request, food_id)
    if request.method == "PUT":
        return update_food(request, food_id)
    if request.method == "DELETE":
        return delete_food(request, food_id)
    return error_response("不支持的请求方法", status=405)


@require_GET
def list_foods(request):
    user, error = require_user(request)
    if error:
        return error

    status = request.GET.get("status")
    location = request.GET.get("location")
    queryset = Food.objects.filter(user_id=user.id).order_by("expiry_date")
    if status and status not in ("null", "undefined"):
        if status not in {"fresh", "warning", "expired"}:
            return error_response("无效的食物状态", status=422)
        queryset = queryset.filter(status=status)
    if location:
        queryset = queryset.filter(location=location)
    foods = [serialize_food(food) for food in queryset]
    return success_response(data=foods, count=len(foods), message=f"成功获取 {len(foods)} 条记录")


@require_GET
def today_recipe(request):
    user, error = require_user(request)
    if error:
        return error
    foods = [serialize_food(food) for food in Food.objects.filter(user_id=user.id).order_by("expiry_date", "id")]
    cache_key = recipe_cache_key(user.id, foods)
    cached = _recipe_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] <= RECIPE_CACHE_TTL_SECONDS:
        return success_response(data={**cached[1], "cached": True}, message="菜谱生成成功")

    fallback_recipe = build_recipe_from_foods(foods)
    ai_recipe = generate_ai_recipe_with_timeout(fallback_recipe)
    recipe = {**(ai_recipe or fallback_recipe), "cached": False}
    _recipe_cache[cache_key] = (now, recipe)
    return success_response(data=recipe, message="菜谱生成成功")


@require_GET
def food_detail(request, food_id: int):
    user, error = require_user(request)
    if error:
        return error
    food = Food.objects.filter(id=food_id, user_id=user.id).first()
    if not food:
        return error_response("食物不存在", status=404)
    return success_response(data=serialize_food(food), message="获取成功")


@require_http_methods(["POST"])
def create_food(request):
    user, error = require_user(request)
    if error:
        return error
    payload = parse_request_data(request)
    name = str(payload.get("name") or "").strip()
    if not name:
        return error_response("食物名称不能为空", status=422)

    category = payload.get("category") or None
    image_url = payload.get("image_url") or None
    location = payload.get("location") or "fridge"
    notes = payload.get("notes") or None
    put_date = date.fromisoformat(str(payload.get("put_date") or date.today().isoformat()))

    try:
        shelf_life_days = int(payload.get("shelf_life_days")) if payload.get("shelf_life_days") not in (None, "") else None
    except (TypeError, ValueError):
        return error_response("保质期格式不正确", status=422)

    if not shelf_life_days:
        ref = find_shelf_life_reference(name, category)
        shelf_life_days = days_for_location(ref, location) if ref else 7

    expiry_date = put_date + timedelta(days=shelf_life_days)
    status = determine_status(expiry_date, date.today())
    food = Food.objects.create(
        user_id=user.id,
        name=name,
        category=category,
        image_url=image_url,
        put_date=put_date,
        expiry_date=expiry_date,
        shelf_life_days=shelf_life_days,
        status=status,
        location=location,
        notes=notes,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    return success_response(data=serialize_food(food), message="添加成功")


@require_POST
def upload_image(request):
    user, error = require_user(request)
    if error:
        return error
    image = request.FILES.get("image")
    if not image:
        return error_response("缺少图片文件", status=400)
    try:
        image_url = save_uploaded_image(request, image)
    except Exception as exc:
        return error_response(f"图片保存失败：{exc}", status=500)
    return success_response(data={"image_url": image_url}, message="图片上传成功")


@require_http_methods(["PUT"])
def update_food(request, food_id: int):
    user, error = require_user(request)
    if error:
        return error
    food = Food.objects.filter(id=food_id, user_id=user.id).first()
    if not food:
        return error_response("食物不存在", status=404)

    payload = parse_request_data(request)
    if payload.get("name") is not None:
        food.name = payload.get("name")
    if payload.get("status") is not None:
        food.status = payload.get("status")
    if payload.get("notes") is not None:
        food.notes = payload.get("notes")
    if payload.get("location") is not None:
        food.location = payload.get("location")
    if payload.get("shelf_life_days") is not None:
        try:
            food.shelf_life_days = int(payload.get("shelf_life_days"))
        except (TypeError, ValueError):
            return error_response("保质期格式不正确", status=422)
        food.expiry_date = food.put_date + timedelta(days=food.shelf_life_days)
        food.status = determine_status(food.expiry_date, date.today())
    food.updated_at = datetime.now()
    food.save()
    return success_response(data=serialize_food(food), message="更新成功")


@require_http_methods(["DELETE"])
def delete_food(request, food_id: int):
    user, error = require_user(request)
    if error:
        return error
    deleted, _ = Food.objects.filter(id=food_id, user_id=user.id).delete()
    if not deleted:
        return error_response("食物不存在", status=404)
    return success_response(message="删除成功")


@require_POST
def complete_food(request, food_id: int):
    user, error = require_user(request)
    if error:
        return error
    payload = parse_request_data(request)
    event_type = payload.get("action", "eat")
    if event_type not in ("eat", "discard"):
        return error_response("无效的完成类型", status=422)
    food = Food.objects.filter(id=food_id, user_id=user.id).first()
    if not food:
        return error_response("食物不存在", status=404)
    event = FoodEvent.objects.create(
        user_id=user.id,
        food_id=food.id,
        event_type=event_type,
        name=food.name,
        category=food.category,
        image_url=food.image_url,
        put_date=food.put_date,
        expiry_date=food.expiry_date,
        shelf_life_days=food.shelf_life_days,
        location=food.location,
        notes=food.notes,
        created_at=datetime.now(),
    )
    food.delete()
    return success_response(data={"event_id": event.id, "event_type": event_type}, message="已记录")


@require_http_methods(["DELETE"])
def delete_food_event(request, event_id: int):
    user, error = require_user(request)
    if error:
        return error
    deleted, _ = FoodEvent.objects.filter(id=event_id, user_id=user.id).delete()
    if not deleted:
        return error_response("记录不存在", status=404)
    return success_response(message="已撤销")


@require_GET
def overview(request):
    user, error = require_user(request)
    if error:
        return error
    total = Food.objects.filter(user_id=user.id).count()
    status_counts = {item["status"]: item["count"] for item in Food.objects.filter(user_id=user.id).values("status").annotate(count=Count("id"))}
    event_counts = {item["event_type"]: item["count"] for item in FoodEvent.objects.filter(user_id=user.id).values("event_type").annotate(count=Count("id"))}
    today = date.today()
    warning_foods = [serialize_food(food) for food in Food.objects.filter(user_id=user.id, expiry_date__gte=today, expiry_date__lte=today + timedelta(days=3)).order_by("expiry_date")]
    return success_response(
        data={
            "total": total,
            "fresh_count": status_counts.get("fresh", 0),
            "warning_count": status_counts.get("warning", 0),
            "expired_count": status_counts.get("expired", 0),
            "eaten_count": event_counts.get("eat", 0),
            "discarded_count": event_counts.get("discard", 0),
            "total_created_count": total + event_counts.get("eat", 0) + event_counts.get("discard", 0),
            "warning_foods": warning_foods,
        },
        message="获取成功",
    )


@require_GET
def shelf_life_reference(request):
    food_name = request.GET.get("food_name")
    category = request.GET.get("category")
    if food_name:
        ref = find_shelf_life_reference(food_name, category)
        rows = [ref] if ref else []
    elif category:
        rows = list(ShelfLifeReference.objects.filter(category=category).order_by("food_name"))
    else:
        rows = list(ShelfLifeReference.objects.all())
    data = [
        {
            "food_name": item.food_name,
            "category": item.category,
            "fridge_days": item.fridge_days,
            "freezer_days": item.freezer_days,
            "room_temp_days": item.room_temp_days,
            "recommended_location": item.recommended_location,
            "storage_tip": item.storage_tip,
        }
        for item in rows if item
    ]
    return success_response(data=data, message="获取成功")