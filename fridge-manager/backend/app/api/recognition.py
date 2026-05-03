"""
AI 食物识别 API
支持通义千问和百度 AI
"""

from fastapi import APIRouter, HTTPException, Form, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
import os
from pathlib import Path
import tempfile
import shutil

from app.services.qwen_service import qwen_service

router = APIRouter()

# 百度 AI 配置（备用）
BAIDU_API_KEY = os.getenv("BAIDU_API_KEY", "")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "")


class RecognitionResult(BaseModel):
    """识别结果"""
    name: str
    confidence: float
    category: Optional[str] = None
    reason: Optional[str] = None
    shelf_life_days: Optional[int] = None
    recommended_location: Optional[str] = None
    storage_tip: Optional[str] = None


class RecognitionResponse(BaseModel):
    """识别响应"""
    success: bool
    message: str
    data: Optional[List[RecognitionResult]] = None
    mode: Optional[str] = None
    mode_reason: Optional[str] = None
    whole_food: Optional[RecognitionResult] = None
    shelf_life: Optional[dict] = None


# 常见食物分类映射（备用）
FOOD_CATEGORY_MAP = {
    "白菜": "蔬菜", "青菜": "蔬菜", "菠菜": "蔬菜", "生菜": "蔬菜",
    "胡萝卜": "蔬菜", "土豆": "蔬菜", "西红柿": "蔬菜", "黄瓜": "蔬菜",
    "苹果": "水果", "香蕉": "水果", "橙子": "水果", "葡萄": "水果",
    "猪肉": "肉类", "牛肉": "肉类", "鸡肉": "肉类",
    "鱼": "海鲜", "虾": "海鲜",
    "鸡蛋": "蛋类", "牛奶": "乳制品", "酸奶": "乳制品",
    "豆腐": "豆制品", "米饭": "主食", "面包": "主食",
    "剩菜": "剩菜", "剩饭": "剩菜", "炒菜": "熟食", "熟肉": "熟食",
    "炒饭": "熟食", "汤": "熟食", "红烧肉": "熟食", "番茄炒蛋": "熟食",
}


@router.post("/image", response_model=RecognitionResponse)
async def recognize_food_image(image: UploadFile = File(...)):
    """
    识别食物图片
    
    优先使用通义千问 Qwen-VL，如未配置则使用百度 AI
    """
    temp_path = None
    
    try:
        # 保存临时文件
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, image.filename)
        
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(image.file, f)
        
        # 优先使用千问 AI
        if os.getenv("DASHSCOPE_API_KEY"):
            try:
                recognition = qwen_service.recognize_food_image(temp_path)
                if isinstance(recognition, list):
                    recognition = {"mode": "split", "reason": "", "whole_food": None, "foods": recognition}
                foods = recognition.get("foods", [])
                whole_food = recognition.get("whole_food")
                
                if foods or whole_food:
                    results = [
                        RecognitionResult(
                            name=f.get('name', '未知食物'),
                            confidence=f.get('confidence', 80.0),
                            category=f.get('category', '其他'),
                            shelf_life_days=f.get('shelf_life_days'),
                            recommended_location=f.get('recommended_location'),
                            storage_tip=f.get('storage_tip'),
                        )
                        for f in foods
                    ]
                    whole_result = None
                    if whole_food:
                        whole_result = RecognitionResult(
                            name=whole_food.get('name', '熟食餐盘'),
                            confidence=whole_food.get('confidence', 80.0),
                            category=whole_food.get('category', '熟食'),
                            shelf_life_days=whole_food.get('shelf_life_days', 2),
                            recommended_location=whole_food.get('recommended_location', 'fridge'),
                            storage_tip=whole_food.get('storage_tip'),
                        )
                    
                    return RecognitionResponse(
                        success=True,
                        message=f"成功识别出 {len(results)} 个可拆分结果（千问 AI）",
                        data=results,
                        mode=recognition.get("mode", "split"),
                        mode_reason=recognition.get("reason", ""),
                        whole_food=whole_result,
                    )
            except Exception as e:
                # 降级到百度 AI 或返回错误
                pass
        
        # 如果没有配置千问或识别失败
        return RecognitionResponse(
            success=True,
            message="未配置 AI 或识别失败，请手动输入食物名称",
            data=[],
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"识别服务异常：{str(e)}")
    finally:
        # 清理临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                shutil.rmtree(os.path.dirname(temp_path))
            except:
                pass


@router.post("/infer-shelf-life")
async def infer_shelf_life(
    name: str = Form(...),
    category: str = Form(...),
    location: str = Form("fridge"),
):
    """
    推理食物保质期
    
    使用千问 AI 智能推理
    """
    try:
        result = qwen_service.infer_shelf_life(name, category, location)
        
        return {
            "success": True,
            "data": result,
            "message": "保质期推理完成",
        }
    except Exception as e:
        # 返回默认值
        return {
            "success": True,
            "data": {"days": 7, "reason": "使用默认值"},
            "message": "AI 不可用，使用默认保质期 7 天",
        }


@router.post("/name", response_model=RecognitionResponse)
async def recognize_food_by_name(name: str = Form(...)):
    """
    根据食物名称查询类别
    """
    # 查找匹配的食物
    matched = []
    for food_name, category in FOOD_CATEGORY_MAP.items():
        if name in food_name or food_name in name:
            matched.append(RecognitionResult(
                name=food_name,
                confidence=100.0,
                category=category,
            ))
    
    if matched:
        return RecognitionResponse(
            success=True,
            message=f"找到 {len(matched)} 个匹配结果",
            data=matched,
        )
    
    # 未找到精确匹配
    return RecognitionResponse(
        success=True,
        message="未找到精确匹配，使用通用分类",
        data=[RecognitionResult(name=name, confidence=50.0, category="其他")],
    )


@router.get("/suggestion/{food_name}")
async def get_eating_suggestion(food_name: str, days_left: int = 3):
    """
    获取食用建议
    
    使用千问 AI 生成
    """
    try:
        suggestion = qwen_service.generate_eating_suggestion(food_name, days_left)
        
        return {
            "success": True,
            "data": {
                "food_name": food_name,
                "days_left": days_left,
                "suggestion": suggestion,
            },
        }
    except Exception as e:
        return {
            "success": True,
            "data": {
                "suggestion": f"{food_name}还有{days_left}天过期，请尽快食用。",
            },
        }


@router.get("/categories")
async def get_food_categories():
    """获取所有支持的食物类别"""
    categories = {}
    for food, category in FOOD_CATEGORY_MAP.items():
        if category not in categories:
            categories[category] = []
        categories[category].append(food)
    
    return {
        "success": True,
        "data": categories,
    }
