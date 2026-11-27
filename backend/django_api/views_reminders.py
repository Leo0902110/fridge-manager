from datetime import date, datetime, timedelta

from django.views.decorators.http import require_GET, require_http_methods

from .helpers import build_reminder_policy, error_response, parse_request_data, require_user, success_response
from .models import Food, Reminder


@require_GET
def pending(request):
    user, error = require_user(request)
    if error:
        return error
    rows = [
        {
            "id": item.id,
            "food_id": item.food_id,
            "food_name": item.food.name,
            "expiry_date": item.food.expiry_date.isoformat(),
            "remind_date": item.remind_date.isoformat(),
            "message": item.message,
            "is_sent": bool(item.is_sent),
        }
        for item in Reminder.objects.select_related("food").filter(food__user_id=user.id, is_sent=0, remind_date__lte=date.today()).order_by("remind_date")
    ]
    return success_response(data=rows, count=len(rows), message="获取成功")


@require_http_methods(["POST"])
def check_expiry(request):
    user, error = require_user(request)
    if error:
        return error
    foods = list(Food.objects.filter(user_id=user.id, expiry_date__lte=date.today() + timedelta(days=3)))
    created_count = 0
    for food in foods:
        if not Reminder.objects.filter(food_id=food.id, is_sent=0).exists():
            policy = build_reminder_policy(food)
            Reminder.objects.create(food_id=food.id, user_id=str(user.id), remind_date=policy["remind_date"], message=policy["message"], is_sent=0, created_at=datetime.now())
            created_count += 1
    return success_response(data={"created_count": created_count, "warning_foods": [food.id for food in foods]}, message=f"已创建 {created_count} 条临期提醒")


@require_GET
def strategy(request):
    user, error = require_user(request)
    if error:
        return error
    data = []
    for food in Food.objects.filter(user_id=user.id).order_by("expiry_date"):
        policy = build_reminder_policy(food)
        data.append({
            "food_id": food.id,
            "food_name": food.name,
            "category": food.category,
            "location": food.location,
            "expiry_date": food.expiry_date.isoformat(),
            **policy,
        })
    return success_response(data=data, count=len(data), message="获取成功")


@require_http_methods(["PUT"])
def mark_sent(request, reminder_id: int):
    user, error = require_user(request)
    if error:
        return error
    updated = Reminder.objects.filter(id=reminder_id, food__user_id=user.id).update(is_sent=1)
    if not updated:
        return error_response("提醒不存在", status=404)
    return success_response(message="提醒已标记为已发送")


@require_GET
def history(request):
    user, error = require_user(request)
    if error:
        return error
    try:
        limit = int(request.GET.get("limit", 50))
    except ValueError:
        limit = 50
    rows = [
        {
            "id": item.id,
            "food_id": item.food_id,
            "food_name": item.food.name,
            "remind_date": item.remind_date.isoformat(),
            "message": item.message,
            "is_sent": bool(item.is_sent),
        }
        for item in Reminder.objects.select_related("food").filter(food__user_id=user.id).order_by("-remind_date")[:limit]
    ]
    return success_response(data=rows, message="获取成功")


@require_http_methods(["POST"])
def send_template(request):
    return success_response(
        data=parse_request_data(request),
        message="提醒发送接口（需配置微信 API）",
    )