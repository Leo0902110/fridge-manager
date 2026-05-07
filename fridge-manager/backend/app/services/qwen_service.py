"""
通义千问 AI 服务
支持食物识别、保质期推理、饮食建议
"""

import logging
import os
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, cast

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

try:
    import dashscope
    from dashscope import MultiModalConversation
except ImportError:
    dashscope = None
    MultiModalConversation = None

logger = logging.getLogger(__name__)


class QwenService:
    """通义千问 AI 服务"""
    
    def __init__(self):
        self._warned_missing_sdk = False
        self._warned_missing_key = False
        self._refresh_config()

    def _refresh_config(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.text_model = os.getenv("QWEN_MODEL", "qwen-plus")
        self.vl_model = os.getenv("QWEN_VL_MODEL", "qwen-vl-max")

        if dashscope is None:
            if not self._warned_missing_sdk:
                logger.warning("未安装 dashscope，千问 AI 功能不可用")
                self._warned_missing_sdk = True
            return

        if not self.api_key:
            if not self._warned_missing_key:
                logger.warning("未配置 DASHSCOPE_API_KEY，千问 AI 功能不可用")
                self._warned_missing_key = True
            return

        self._warned_missing_key = False
        dashscope.api_key = self.api_key

    def _is_available(self) -> bool:
        self._refresh_config()
        return dashscope is not None and bool(self.api_key)

    @staticmethod
    def _contains_any(text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _normalize_freshness_level(value: object) -> str:
        text = str(value or "").strip().lower()
        mapping = {
            "fresh": "fresh",
            "good": "fresh",
            "新鲜": "fresh",
            "较新鲜": "fresh",
            "normal": "normal",
            "average": "normal",
            "一般": "normal",
            "普通": "normal",
            "stale": "stale",
            "old": "stale",
            "不新鲜": "stale",
            "欠新鲜": "stale",
            "变软": "stale",
            "萎蔫": "stale",
            "spoiled": "spoiled",
            "bad": "spoiled",
            "腐坏": "spoiled",
            "腐烂": "spoiled",
            "发霉": "spoiled",
            "变质": "spoiled",
        }
        return mapping.get(text, text if text in ("fresh", "normal", "stale", "spoiled") else "normal")

    def _infer_freshness_from_text(self, food: dict) -> str:
        text = "".join(str(food.get(key) or "") for key in ("name", "category", "storage_tip", "freshness_description", "freshness_reason"))
        if self._contains_any(text, ["发霉", "霉斑", "腐烂", "腐坏", "异味", "变质", "黏液", "流汁", "黑斑严重"]):
            return "spoiled"
        if self._contains_any(text, ["不新鲜", "欠新鲜", "萎蔫", "发蔫", "变软", "发皱", "干瘪", "褐变", "黑斑", "碰伤", "熟透", "边缘干"]):
            return "stale"
        if self._contains_any(text, ["较新鲜", "新鲜", "色泽好", "饱满"]):
            return "fresh"
        return "normal"

    def _normalize_freshness_info(self, food: dict) -> str:
        level = self._normalize_freshness_level(food.get("freshness_level") or food.get("freshness"))
        if level == "normal":
            level = self._infer_freshness_from_text(food)

        try:
            score = int(float(food.get("freshness_score") or 0))
        except (TypeError, ValueError):
            score = 0

        if score:
            if score < 30:
                level = "spoiled"
            elif score < 55 and level not in ("spoiled",):
                level = "stale"
            elif score >= 85 and level == "normal":
                level = "fresh"
        else:
            default_scores = {
                "fresh": 90,
                "normal": 70,
                "stale": 45,
                "spoiled": 20,
            }
            score = default_scores[level]

        food["freshness_level"] = level
        food["freshness_score"] = max(0, min(score, 100))
        if not food.get("freshness_description"):
            descriptions = {
                "fresh": "外观看起来新鲜",
                "normal": "外观新鲜度一般",
                "stale": "外观不够新鲜",
                "spoiled": "疑似变质，不建议入库",
            }
            food["freshness_description"] = descriptions[level]
        return level

    def _apply_freshness_adjustment(self, food: dict, days: int) -> int:
        """按视觉新鲜度折减保质期，避免旧食物仍按标准天数推荐。"""
        level = self._normalize_freshness_info(food)
        category = str(food.get("category") or "其他")
        if level == "fresh":
            return max(days, 1)
        if level == "normal":
            return max(1, min(days, round(days * 0.85)))
        if level == "spoiled":
            food["recommended_location"] = "fridge"
            food["storage_tip"] = "疑似变质，建议丢弃"
            return 1

        if category in ("肉类", "海鲜", "乳制品", "豆制品", "熟食", "剩菜"):
            cap = 1
            food["recommended_location"] = "fridge"
            food["storage_tip"] = "不够新鲜，冷藏尽快处理"
        elif category in ("水果", "蔬菜", "主食"):
            cap = 2
            food["storage_tip"] = "不够新鲜，尽快食用"
        else:
            cap = max(1, min(7, round(days * 0.4)))
            food["storage_tip"] = "不够新鲜，尽快食用"
        return max(1, min(days, cap))

    def _normalize_recognition_item(self, food: dict, whole: bool = False) -> dict:
        """把 AI 估算校正到符合日常认知的范围，避免离谱天数直接进入前端。"""
        name = str(food.get("name") or "")
        category = str(food.get("category") or "其他")
        tip = str(food.get("storage_tip") or "")
        freshness_text = f"{food.get('freshness_description') or ''}{food.get('freshness_reason') or ''}"
        text = f"{name}{category}{tip}{freshness_text}"
        location = food.get("recommended_location") if food.get("recommended_location") in ("fridge", "freezer", "room") else "fridge"
        is_opened = self._contains_any(text, ["开封", "已开", "打开", "切开", "切块", "剩余"])

        try:
            days = int(food.get("shelf_life_days") or 0)
        except (TypeError, ValueError):
            days = 0

        if whole or category in ("熟食", "剩菜") or self._contains_any(text, ["熟食", "剩菜", "便当", "饭盒", "套餐", "炒菜", "炒饭", "汤"]):
            location = "fridge"
            days = min(max(days or 2, 1), 3)
            food["storage_tip"] = food.get("storage_tip") or "熟食冷藏，尽快吃完"
        elif self._contains_any(text, ["罐头", "午餐肉罐", "鱼罐", "水果罐", "密封罐"]):
            location = "fridge" if is_opened else "room"
            days = min(max(days or 3, 2), 5) if is_opened else min(max(days or 180, 180), 365)
            food["storage_tip"] = food.get("storage_tip") or ("开封后冷藏尽快吃" if is_opened else "未开封阴凉保存")
        elif self._contains_any(text, ["饼干", "方便面", "泡面", "挂面", "大米", "米", "面粉", "麦片", "燕麦", "坚果", "糖果", "巧克力", "零食", "茶叶", "咖啡", "饮料", "调味", "酱油", "醋"]):
            location = "room"
            days = min(max(days or 90, 30), 365)
            food["storage_tip"] = food.get("storage_tip") or "密封阴凉常温保存"
        elif self._contains_any(text, ["土豆", "洋葱", "大蒜", "姜", "南瓜", "红薯", "地瓜", "山药", "芋头"]):
            location = "room"
            days = min(max(days or 14, 7), 30)
            food["storage_tip"] = food.get("storage_tip") or "阴凉通风常温保存"
        elif self._contains_any(text, ["面包", "吐司"]):
            location = "room"
            days = min(max(days or 3, 1), 5)
            food["storage_tip"] = food.get("storage_tip") or "常温密封，尽快食用"
        elif self._contains_any(text, ["菠萝", "凤梨"]):
            location = "fridge"
            days = min(max(days or 5, 1), 5)
            food["storage_tip"] = food.get("storage_tip") or "切开后冷藏尽快吃"
        elif self._contains_any(text, ["西瓜", "香瓜", "哈密瓜"]):
            location = "fridge"
            days = min(max(days or 3, 1), 4)
            food["storage_tip"] = food.get("storage_tip") or "切开后密封冷藏"
        elif category == "水果":
            if self._contains_any(text, ["苹果"]):
                location = "fridge" if is_opened else "room"
                days = min(max(days or (7 if location == "room" else 14), 5), 21)
            elif self._contains_any(text, ["香蕉"]):
                location = "room"
                days = min(max(days or 3, 1), 4)
            elif self._contains_any(text, ["橙", "橘", "柑", "梨", "柚子", "柠檬", "牛油果", "猕猴桃", "芒果"]):
                location = "fridge" if is_opened else "room"
                days = min(max(days or 5, 2), 10)
            else:
                days = min(max(days or 5, 1), 7)
            food["storage_tip"] = food.get("storage_tip") or "按水果新鲜度保守保存"
        elif category == "海鲜":
            location = "freezer"
            days = min(max(days or 90, 1), 180)
            food["storage_tip"] = food.get("storage_tip") or "不当天吃建议冷冻"
        elif category == "肉类":
            location = "freezer"
            days = min(max(days or 90, 2), 180)
            food["storage_tip"] = food.get("storage_tip") or "分装冷冻更安全"
        elif category == "蔬菜":
            days = min(max(days or 5, 1), 14)
            food["storage_tip"] = food.get("storage_tip") or "冷藏保鲜，尽快食用"
        elif category in ("乳制品", "豆制品"):
            location = "fridge"
            days = min(max(days or 3, 1), 14)

        if not days:
            days = 7

        food["category"] = category
        food["recommended_location"] = location
        days = self._apply_freshness_adjustment(food, days)
        food["shelf_life_days"] = int(days)
        return food
    
    def recognize_food_image(self, image_path: str) -> Dict[str, object]:
        """
        使用 Qwen-VL 识别食物图片
        
        Args:
            image_path: 图片路径或 URL
            
        Returns:
            识别结果，如：{"mode": "whole", "whole_food": {...}, "foods": [...]}
        """
        if not self._is_available():
            raise ValueError("千问 AI 当前不可用")
        
        try:
            # 如果是本地文件，转换为 base64 或 file:// URL
            if Path(image_path).exists():
                image_path = f"file://{image_path}"
            
            # 构造多模态对话请求
            messages = [{
                'role': 'user',
                'content': [
                    {'image': image_path},
                                        {'text': '''请识别这张图片中的可入库食物，并判断应该按“整份入库”还是“拆分入库”。同时先判断食物可见新鲜度，再根据新鲜度、包装状态、是否切开/开封、是否熟食，估算合理保质期，不要机械套用固定数据库。

重要原则：
1. 如果图片是已经烹饪好的盘中餐、便当、饭盒、剩饭剩菜、套餐、拼盘、炒菜配饭等组合熟食，默认 mode 返回 "whole"，把它作为一个整体入库，不要把鸡蛋、西兰花、米饭、面条等配菜拆成独立库存。
2. 如果图片是未加工食材、生鲜、多个独立包装、多个独立水果蔬菜，mode 返回 "split"，每个可单独管理的食物返回一条。
3. 对整份熟食，whole_food 的类别用“熟食”或“剩菜”，冷藏保质期通常为 1-2 天；不确定时 shelf_life_days 返回 2。
4. shelf_life_days 表示在 recommended_location 对应保存方式下的建议天数。请按日常认知估算，并为用户着想：不是所有东西都要冷藏。未开封罐头、密封包装、干货、饼干、方便面、米面、坚果、完整土豆/洋葱/大蒜/南瓜/红薯、香蕉、面包、完整耐放水果等，优先允许 room 常温保存。
5. 高风险食物要保守：切开的菠萝/凤梨冷藏约 3-5 天，不要给 21 天；草莓等浆果 1-3 天；普通新鲜水果 3-7 天；苹果/橙子这类完整耐放水果可 room 或 fridge 更久；生肉/海鲜不当天吃建议 freezer；未开封罐头/密封常温食品可按 room 给 90-365 天，已开封罐头冷藏 2-5 天；熟食/剩菜冷藏 1-3 天。
6. 必须对每个结果返回 freshness_level：fresh/normal/stale/spoiled；freshness_score 为 0-100。判断依据包括颜色暗沉、萎蔫、发皱、软烂、褐变/黑斑、霉斑、汁水渗出、边缘干硬、包装胀气/漏液等。不要把“食物品类的标准保质期”当作当前图片的新鲜度。
7. 先估标准保质期，再按新鲜度折减：fresh 可接近标准；normal 略保守；stale 必须大幅缩短，水果/蔬菜/主食通常 1-2 天，高风险肉类/海鲜/乳制品/熟食通常 1 天；spoiled 返回 1 天并在 storage_tip 写“不建议入库/建议丢弃”。
8. 如果图片里食物看起来已经切开、开封、熟制、混合、汁水多或不够新鲜，要保守缩短天数。不要为了“耐放”给离谱长天数。

以 JSON 格式返回结果：
{
  "mode": "whole 或 split",
  "reason": "为什么这样入库，15字以内",
        "whole_food": {"name": "整份食物名称", "category": "类别（熟食/剩菜/主食/其他）", "confidence": 置信度 0-100, "freshness_level": "fresh/normal/stale/spoiled", "freshness_score": 0-100, "freshness_description": "新鲜度判断，15字以内", "shelf_life_days": 推荐保存方式下的建议天数, "recommended_location": "fridge/freezer/room", "storage_tip": "保存建议，20字以内"},
  "foods": [
                {"name": "可拆分食物名称", "category": "类别（蔬菜/水果/肉类/海鲜/蛋类/乳制品/豆制品/主食/熟食/剩菜/其他）", "confidence": 置信度 0-100, "freshness_level": "fresh/normal/stale/spoiled", "freshness_score": 0-100, "freshness_description": "新鲜度判断，15字以内", "shelf_life_days": 推荐保存方式下的建议天数, "recommended_location": "fridge/freezer/room", "storage_tip": "保存建议，20字以内"}
  ]
}
命名要符合库存管理，而不是菜谱拆料。例如一盘牛排、面、蛋和蔬菜应命名为“牛排面套餐”或“熟食餐盘”；一盒剩饭剩菜命名为“剩菜便当”。只返回 JSON，不要其他文字。如果无法识别，mode 返回 "split"，foods 返回空数组。'''}
                ]
            }]
            
            response = cast(Any, MultiModalConversation).call(
                model=self.vl_model,
                messages=messages,
                result_format='message'
            )
            
            if response.status_code == HTTPStatus.OK:
                content = response.output.choices[0].message.content[0].get('text', '')
                
                # 解析 JSON 结果
                import json
                try:
                    # 清理可能的 markdown 标记
                    content = content.replace('```json', '').replace('```', '').strip()
                    result = json.loads(content)
                    foods = result.get('foods', [])
                    whole_food = result.get('whole_food') or None
                    mode = result.get('mode', 'split')
                    if mode not in ('whole', 'split'):
                        mode = 'split'
                    
                    # 确保 confidence 是数字
                    for food in foods:
                        if 'confidence' in food:
                            food['confidence'] = float(food['confidence'])
                        else:
                            food['confidence'] = 80.0
                        if 'shelf_life_days' in food and food['shelf_life_days'] is not None:
                            food['shelf_life_days'] = int(food['shelf_life_days'])
                        if food.get('recommended_location') not in ('fridge', 'freezer', 'room'):
                            food['recommended_location'] = 'fridge'
                        self._normalize_recognition_item(food)

                    if whole_food:
                        if 'confidence' in whole_food:
                            whole_food['confidence'] = float(whole_food['confidence'])
                        else:
                            whole_food['confidence'] = 80.0
                        if not whole_food.get('category'):
                            whole_food['category'] = '熟食'
                        if 'shelf_life_days' in whole_food and whole_food['shelf_life_days'] is not None:
                            whole_food['shelf_life_days'] = int(whole_food['shelf_life_days'])
                        if whole_food.get('recommended_location') not in ('fridge', 'freezer', 'room'):
                            whole_food['recommended_location'] = 'fridge'
                        self._normalize_recognition_item(whole_food, whole=True)
                    
                    return {
                        "mode": mode,
                        "reason": result.get('reason', ''),
                        "whole_food": whole_food,
                        "foods": foods,
                    }
                except json.JSONDecodeError as e:
                    logger.error(f"解析 AI 识别结果失败：{e}, content: {content}")
                    return {"mode": "split", "reason": "", "whole_food": None, "foods": []}
            else:
                logger.error(f"千问 API 调用失败：{response.code} - {response.message}")
                raise ValueError(f"AI 识别失败：{response.message}")
                
        except Exception as e:
            logger.error(f"食物识别异常：{e}")
            raise
    
    def infer_shelf_life(self, food_name: str, category: str, location: str, freshness_level: str = "normal", freshness_description: str = "") -> dict:
        """
        推理食物保质期
        
        Args:
            food_name: 食物名称
            category: 食物类别
            location: 存放位置 (fridge/freezer/room)
            
        Returns:
            {"days": 保质期天数，"reason": "推理依据"}
        """
        if not self._is_available():
            # 返回默认值
            return {"days": 7, "reason": "未配置 AI，使用默认值"}
        
        try:
            location_map = {
                "fridge": "冷藏",
                "freezer": "冷冻",
                "room": "常温"
            }
            
            prompt = f'''请根据以下信息推理食物的保质期天数：
- 食物名称：{food_name}
- 食物类别：{category}
- 存放位置：{location_map.get(location, "冷藏")}
- 当前可见新鲜度：{self._normalize_freshness_level(freshness_level)}
- 新鲜度描述：{freshness_description or "未提供"}

请先考虑当前新鲜度再给天数：fresh 接近标准；normal 略保守；stale 大幅缩短到 1-2 天；spoiled 只给 1 天并提示不建议入库。

请返回 JSON 格式：
{{
  "days": 保质期天数（整数）,
  "reason": "简短的推理依据（20 字以内）"
}}
只返回 JSON，不要其他文字。'''
            
            messages = [{
                'role': 'user',
                'content': [{'text': prompt}]
            }]
            
            response = cast(Any, dashscope).Generation.call(
                model=self.text_model,
                messages=messages,
                result_format='message'
            )
            
            if response.status_code == HTTPStatus.OK:
                content = response.output.choices[0].message.content
                import json
                try:
                    content = content.replace('```json', '').replace('```', '').strip()
                    result = json.loads(content)
                    return {
                        "days": int(result.get('days', 7)),
                        "reason": result.get('reason', 'AI 推理')
                    }
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"解析保质期结果失败：{e}")
                    return {"days": 7, "reason": "AI 解析失败，使用默认值"}
            else:
                logger.warning(f"保质期推理失败：{response.message}")
                return {"days": 7, "reason": "AI 不可用，使用默认值"}
                
        except Exception as e:
            logger.error(f"保质期推理异常：{e}")
            return {"days": 7, "reason": f"异常：{str(e)}"}
    
    def generate_eating_suggestion(self, food_name: str, days_left: int) -> str:
        """
        生成食用建议
        
        Args:
            food_name: 食物名称
            days_left: 剩余天数
            
        Returns:
            食用建议文本
        """
        if not self._is_available():
            return f"{food_name}还有{days_left}天过期，请尽快食用。"
        
        try:
            prompt = f'''食物"{food_name}"还有{days_left}天过期，请给出一句简短的食用建议（20 字以内）。
例如：
- 建议尽快食用，可用来炒菜或做汤
- 还可以吃 2 天，建议今天吃掉
- 已临期，建议检查是否有异味后再食用'''
            
            messages = [{
                'role': 'user',
                'content': [{'text': prompt}]
            }]
            
            response = cast(Any, dashscope).Generation.call(
                model=self.text_model,
                messages=messages,
                result_format='message'
            )
            
            if response.status_code == HTTPStatus.OK:
                return response.output.choices[0].message.content.strip()
            else:
                return f"{food_name}还有{days_left}天过期，请尽快食用。"
                
        except Exception as e:
            logger.error(f"生成建议失败：{e}")
            return f"{food_name}还有{days_left}天过期，请尽快食用。"


# 全局实例
qwen_service = QwenService()
