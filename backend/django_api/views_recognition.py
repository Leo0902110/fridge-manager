import os
from pathlib import Path

from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .helpers import cleanup_temp_path, error_response, parse_request_data, save_temp_upload_to_path, success_response
from app.services.qwen_service import qwen_service


FOOD_CATEGORY_MAP = {
    "白菜": "蔬菜", "青菜": "蔬菜", "菠菜": "蔬菜", "生菜": "蔬菜",
    "胡萝卜": "蔬菜", "土豆": "蔬菜", "西红柿": "蔬菜", "黄瓜": "蔬菜",
    "苹果": "水果", "香蕉": "水果", "橙子": "水果", "葡萄": "水果",
    "菠萝": "水果", "凤梨": "水果", "火龙果": "水果", "木瓜": "水果",
    "西瓜": "水果", "香瓜": "水果", "荔枝": "水果", "番石榴": "水果",
    "芭乐": "水果", "莲雾": "水果",
    "猪肉": "肉类", "牛肉": "肉类", "牛排": "肉类", "羊肉": "肉类",
    "鸡肉": "肉类", "鸡胸肉": "肉类", "鱼": "海鲜", "虾": "海鲜",
    "鸡蛋": "蛋类", "牛奶": "乳制品", "酸奶": "乳制品",
    "豆腐": "豆制品", "米饭": "主食", "面包": "主食",
    "剩菜": "剩菜", "剩饭": "剩菜", "便当": "熟食", "套餐": "熟食",
    "熟食餐盘": "熟食", "炒菜": "熟食", "熟肉": "熟食",
    "炒饭": "熟食", "汤": "熟食", "红烧肉": "熟食", "番茄炒蛋": "熟食",
}


@require_POST
def recognize_image(request):
    image = request.FILES.get("image")
    if not image:
        return error_response("缺少图片文件", status=400)

    temp_path = None
    try:
        temp_path = save_temp_upload_to_path(image)
        if Path(temp_path).exists() and os.getenv("DASHSCOPE_API_KEY"):
            try:
                recognition = qwen_service.recognize_food_image(temp_path)
                if isinstance(recognition, list):
                    recognition = {"mode": "split", "reason": "", "whole_food": None, "foods": recognition}
                foods = recognition.get("foods", [])
                whole_food = recognition.get("whole_food")
                if foods or whole_food:
                    return success_response(
                        data=foods,
                        message=f"成功识别出 {len(foods)} 个可拆分结果（千问 AI）",
                        mode=recognition.get("mode", "split"),
                        mode_reason=recognition.get("reason", ""),
                        whole_food=whole_food,
                    )
            except Exception:
                pass
        return success_response(data=[], message="未配置 AI 或识别失败，请手动输入食物名称")
    except Exception as exc:
        return error_response(f"识别服务异常：{exc}", status=500)
    finally:
        cleanup_temp_path(temp_path)


@require_http_methods(["POST"])
def infer_shelf_life(request):
    payload = parse_request_data(request)
    name = payload.get("name")
    category = payload.get("category")
    location = payload.get("location", "fridge")
    freshness_level = payload.get("freshness_level", "normal")
    freshness_description = payload.get("freshness_description", "")
    if not name or not category:
        return error_response("缺少食物名称或类别", status=400)
    try:
        result = qwen_service.infer_shelf_life(name, category, location, freshness_level, freshness_description)
        return success_response(data=result, message="保质期推理完成")
    except Exception:
        return success_response(data={"days": 7, "reason": "使用默认值"}, message="AI 不可用，使用默认保质期 7 天")


@require_http_methods(["POST"])
def recognize_by_name(request):
    payload = parse_request_data(request)
    name = payload.get("name")
    if not name:
        return success_response(data=[], message="请输入食物名称")
    matched = []
    for food_name, category in FOOD_CATEGORY_MAP.items():
        if name in food_name or food_name in name:
            matched.append({"name": food_name, "confidence": 100.0, "category": category})
    if matched:
        return success_response(data=matched, message=f"找到 {len(matched)} 个匹配结果")
    return success_response(data=[{"name": name, "confidence": 50.0, "category": "其他"}], message="未找到精确匹配，使用通用分类")


@require_GET
def eating_suggestion(request, food_name: str):
    try:
        days_left = int(request.GET.get("days_left", 3))
    except ValueError:
        days_left = 3
    try:
        suggestion = qwen_service.generate_eating_suggestion(food_name, days_left)
    except Exception:
        suggestion = f"{food_name}还有{days_left}天过期，请尽快食用。"
    return success_response(data={"food_name": food_name, "days_left": days_left, "suggestion": suggestion}, message="获取成功")


@require_GET
def categories(request):
    categories_map = {}
    for food, category in FOOD_CATEGORY_MAP.items():
        categories_map.setdefault(category, []).append(food)
    return success_response(data=categories_map, message="获取成功")