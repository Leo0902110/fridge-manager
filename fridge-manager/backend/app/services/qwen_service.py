"""
通义千问 AI 服务
支持食物识别、保质期推理、饮食建议
"""

import json
import logging
import os
import copy
import hashlib
import re
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, Optional, cast

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

dashscope: Any = None
MultiModalConversation: Any = None

logger = logging.getLogger(__name__)

MAIN_FOOD_TERMS = {
    "牛肉", "猪肉", "鸡肉", "鸡腿", "牛排", "羊肉", "鱼", "虾",
    "鸡蛋", "豆腐", "牛奶", "酸奶", "米饭", "面条", "面包",
    "白菜", "胡萝卜", "西红柿", "番茄", "黄瓜", "土豆", "生菜",
    "菠菜", "青椒", "洋葱", "苹果", "香蕉", "橙子", "草莓", "葡萄",
}


class QwenService:
    """通义千问 AI 服务"""
    
    def __init__(self):
        self._warned_missing_sdk = False
        self._warned_missing_key = False
        self._recognition_cache: dict[str, Dict[str, object]] = {}
        self._refresh_config()

    def _refresh_config(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.text_model = os.getenv("QWEN_MODEL", "qwen-plus")
        self.recipe_model = os.getenv("QWEN_RECIPE_MODEL", self.text_model)
        self.vl_model = os.getenv("QWEN_VL_MODEL", "qwen-vl-max")

        if not self.api_key:
            if not self._warned_missing_key:
                logger.warning("未配置 DASHSCOPE_API_KEY，千问 AI 功能不可用")
                self._warned_missing_key = True
            return

        self._warned_missing_key = False

    def _ensure_dashscope_loaded(self) -> bool:
        """按需加载 dashscope，避免服务启动时被 SDK 导入阻塞。"""
        global dashscope, MultiModalConversation
        if dashscope is not None and MultiModalConversation is not None:
            dashscope.api_key = self.api_key
            return True
        try:
            import dashscope as dashscope_module
            from dashscope import MultiModalConversation as conversation_module
        except ImportError:
            if not self._warned_missing_sdk:
                logger.warning("未安装 dashscope，千问 AI 功能不可用")
                self._warned_missing_sdk = True
            return False
        dashscope = dashscope_module
        MultiModalConversation = conversation_module
        dashscope.api_key = self.api_key
        self._warned_missing_sdk = False
        return True

    def _is_available(self) -> bool:
        self._refresh_config()
        return bool(self.api_key) and self._ensure_dashscope_loaded()

    @staticmethod
    def _contains_any(text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _contains_unnegated_keyword(text: str, keywords: list[str]) -> bool:
        if not text:
            return False

        negation_markers = (
            "无", "没有", "未见", "未发现", "未观察到", "未闻到",
            "并无", "无明显", "没有明显", "未出现",
        )
        clauses = re.split(r"[，。；;,.、\n]+", text)
        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue
            for keyword in keywords:
                start = 0
                while True:
                    index = clause.find(keyword, start)
                    if index < 0:
                        break
                    prefix = clause[max(0, index - 8):index]
                    if not any(marker in prefix for marker in negation_markers):
                        return True
                    start = index + len(keyword)
        return False

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
        text = "".join(str(food.get(key) or "") for key in ("freshness_description", "freshness_reason", "freshness_evidence"))
        if self._contains_unnegated_keyword(text, [
            "发霉", "霉斑", "霉点", "腐烂", "腐坏", "烂了", "烂洞", "黑洞",
            "异味", "黏液", "流汁", "汁水渗出", "黑斑严重", "大面积黑斑",
            "明显黑斑", "深色凹陷", "发黑凹陷", "软烂", "腐烂洞",
        ]):
            return "spoiled"
        if self._contains_unnegated_keyword(text, ["不新鲜", "欠新鲜", "萎蔫", "发蔫", "变软", "发皱", "干瘪", "褐变", "黑斑", "碰伤", "熟透", "边缘干"]):
            return "stale"
        if self._contains_any(text, ["较新鲜", "新鲜", "色泽好", "饱满"]):
            return "fresh"
        return "normal"

    @staticmethod
    def _freshness_level_from_score(score: int) -> str:
        if score < 20:
            return "spoiled"
        if score < 40:
            return "stale"
        if score < 60:
            return "normal"
        return "fresh"

    def _normalize_freshness_info(self, food: dict) -> str:
        level = self._normalize_freshness_level(food.get("freshness_level") or food.get("freshness"))
        inferred_level = self._infer_freshness_from_text(food)

        try:
            score = int(float(food.get("freshness_score") or 0))
        except (TypeError, ValueError):
            score = 0

        if score:
            level = self._freshness_level_from_score(score)
            if inferred_level == "spoiled":
                level = "spoiled"
        else:
            default_scores = {
                "fresh": 80,
                "normal": 50,
                "stale": 30,
                "spoiled": 10,
            }
            if inferred_level == "spoiled":
                level = "spoiled"
            elif level == "normal":
                level = inferred_level
            score = default_scores[level]

        food["freshness_level"] = level
        food["freshness_score"] = max(0, min(score, 100))
        descriptions = {
            "fresh": "外观看起来新鲜",
            "normal": "外观新鲜度一般",
            "stale": "外观不够新鲜",
            "spoiled": "疑似变质，不建议入库",
        }
        if not food.get("freshness_description") or (level != "spoiled" and self._contains_any(str(food.get("freshness_description") or ""), ["疑似变质", "变质", "建议丢弃"])):
            food["freshness_description"] = descriptions[level]
        if level != "spoiled" and self._contains_any(str(food.get("storage_tip") or ""), ["疑似变质", "不建议入库", "建议丢弃", "丢弃"]):
            food["storage_tip"] = ""
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
            cache_key = ""
            if Path(image_path).exists():
                cache_key = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
                if cache_key in self._recognition_cache:
                    return copy.deepcopy(self._recognition_cache[cache_key])

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
6. 新鲜度必须按固定扣分表评分，不要凭感觉给标签。先从 100 分开始，只根据图片中清楚可见的缺陷扣分：
   - 无明显缺陷或只是正常成熟/正常切面/正常反光/果皮天然斑点：扣 0-15 分。
   - 轻微压痕、轻微褐变、轻微干边、轻微发软：扣 20-35 分。
   - 明显萎蔫、明显发皱、较多褐变/黑斑、明显软塌但没有腐烂霉斑：扣 40-60 分。
   - 黑洞、烂洞、霉斑、腐烂、软烂渗汁、异味迹象、包装胀气/漏液：扣 80-100 分。
7. freshness_score 与 freshness_level 必须严格对应：0-19 spoiled，20-39 stale，40-59 normal，60-100 fresh。普通成熟香蕉、完整水果、正常切开的水果通常应为 fresh；不要把切面反光、红色果肉、香蕉正常黄色果皮当作变质。
8. freshness_description 必须写清楚可见证据，例如“外观完整”“正常切面”“轻微褐变”“有烂洞”。如果没有看到黑洞、烂洞、霉斑、渗汁，不要写“疑似变质”。优先用正向描述，如“外观完整”“汤色正常”“表面干爽”，不要写“无霉斑”“无渗汁”“无异味”这类否定式短语。
9. 先估标准保质期，再按新鲜度折减：fresh 可接近标准；normal 略保守；stale 大幅缩短，水果/蔬菜/主食通常 1-2 天，高风险肉类/海鲜/乳制品/熟食通常 1 天；spoiled 返回 1 天并在 storage_tip 写“不建议入库/建议丢弃”。
10. 如果图片里食物看起来已经切开、开封、熟制、混合、汁水多或不够新鲜，要保守缩短天数。不要为了“耐放”给离谱长天数。

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
                result_format='message',
                temperature=0,
                top_p=0.1,
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
                    
                    normalized_result = {
                        "mode": mode,
                        "reason": result.get('reason', ''),
                        "whole_food": whole_food,
                        "foods": foods,
                    }
                    if cache_key:
                        self._recognition_cache[cache_key] = copy.deepcopy(normalized_result)
                        if len(self._recognition_cache) > 64:
                            self._recognition_cache.pop(next(iter(self._recognition_cache)))
                    return normalized_result
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

    def generate_recipe_from_inventory(self, ingredients: list[dict], expired_warnings: list[str]) -> Optional[dict]:
        """根据库存和过期时间生成合理菜谱。失败时返回 None，由调用方使用规则兜底。"""
        if not self._is_available() or not ingredients:
            return None

        inventory_lines = []
        for item in ingredients:
            days_left = item.get("days_left")
            if days_left is None:
                freshness = "未知到期时间"
            elif days_left < 0:
                freshness = f"已过期{abs(days_left)}天"
            elif days_left == 0:
                freshness = "今天到期"
            else:
                freshness = f"剩{days_left}天"
            inventory_lines.append(
                f"- {item.get('name')}｜{item.get('category') or '其他'}｜{freshness}"
            )

        prompt = f'''你是家庭冰箱食材管家。请只基于“冰箱现有食物”和过期时间，生成一份合理、家常、可执行的今日菜谱。

冰箱中优先处理的食物：
{chr(10).join(inventory_lines)}

过期提醒：
{chr(10).join(expired_warnings) if expired_warnings else "无"}

设计原则：
1. 不要把不适合一起烹饪的食材硬凑成一道菜，例如鸡腿和草莓不能生成“鸡腿炒草莓”。
2. 水果可以作为水果碗、饭后水果、酸奶水果杯；如果与肉类不搭，应放在搭配建议里，不要放进主菜名。
3. 肉类、蛋类、豆制品优先作为主菜蛋白；蔬菜可做配菜；主食可作为搭配。
4. 已过期食物只能提醒检查/清理，不要作为菜谱食材。
5. 只允许使用上方列表里的主要食材。可以使用油盐酱醋、葱姜蒜等基础调料，但菜名和步骤里不要虚构新的蔬菜、肉、水果、主食。
6. 菜名要像真实家常菜，步骤 3-5 步，每步简短。

只返回 JSON，不要 Markdown：
{{
  "title": "菜名",
  "subtitle": "为什么今天推荐这份菜，20字以内",
  "priority": "urgent 或 normal",
  "ingredients": [
    {{"id": 数字ID, "name": "食物名", "category": "类别", "days_left": 剩余天数, "reason": "处理原因"}}
  ],
  "steps": ["步骤1", "步骤2", "步骤3"],
  "tips": ["提示1", "提示2"],
  "expired_warnings": ["过期提醒"],
  "source": "ai"
}}

可用食材原始 JSON：
{json.dumps(ingredients, ensure_ascii=False)}
'''

        try:
            response = cast(Any, dashscope).Generation.call(
                model=self.recipe_model,
                messages=[{
                    'role': 'user',
                    'content': [{'text': prompt}]
                }],
                result_format='message'
            )

            if response.status_code != HTTPStatus.OK:
                logger.warning(f"AI 菜谱生成失败：{response.message}")
                return None

            content = response.output.choices[0].message.content
            content = content.replace('```json', '').replace('```', '').strip()
            recipe = json.loads(content)

            valid_ids = {item.get("id") for item in ingredients}
            selected = []
            for item in recipe.get("ingredients", []):
                if item.get("id") in valid_ids:
                    selected.append(item)

            if not recipe.get("title") or not selected or not recipe.get("steps"):
                return None

            allowed_names = {str(item.get("name", "")) for item in ingredients}
            allowed_text = " ".join(allowed_names)
            recipe_text = " ".join([
                str(recipe.get("title", "")),
                " ".join(str(step) for step in recipe.get("steps", [])),
                " ".join(str(tip) for tip in recipe.get("tips", [])),
            ])
            for term in MAIN_FOOD_TERMS:
                if term in recipe_text and term not in allowed_text:
                    logger.warning(f"AI 菜谱包含库存外主要食材：{term}")
                    return None

            recipe["ingredients"] = selected
            recipe["tips"] = recipe.get("tips") or ["临期食材优先处理，异常气味或霉变不要食用。"]
            recipe["expired_warnings"] = recipe.get("expired_warnings") or expired_warnings
            recipe["priority"] = recipe.get("priority") if recipe.get("priority") in ("urgent", "normal") else "normal"
            recipe["source"] = "ai"
            return recipe
        except Exception as e:
            logger.error(f"生成库存菜谱异常：{e}")
            return None


# 全局实例
qwen_service = QwenService()
