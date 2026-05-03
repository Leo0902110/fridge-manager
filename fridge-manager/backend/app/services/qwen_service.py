"""
通义千问 AI 服务
支持食物识别、保质期推理、饮食建议
"""

import logging
import os
from http import HTTPStatus
from pathlib import Path
from typing import Dict

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
                    {'text': '''请识别这张图片中的可入库食物，并判断应该按“整份入库”还是“拆分入库”。

重要原则：
1. 如果图片是已经烹饪好的盘中餐、便当、饭盒、剩饭剩菜、套餐、拼盘、炒菜配饭等组合熟食，默认 mode 返回 "whole"，把它作为一个整体入库，不要把鸡蛋、西兰花、米饭、面条等配菜拆成独立库存。
2. 如果图片是未加工食材、生鲜、多个独立包装、多个独立水果蔬菜，mode 返回 "split"，每个可单独管理的食物返回一条。
3. 对整份熟食，whole_food 的类别用“熟食”或“剩菜”，冷藏保质期通常为 1-2 天；不确定时 shelf_life_days 返回 2。

以 JSON 格式返回结果：
{
  "mode": "whole 或 split",
  "reason": "为什么这样入库，15字以内",
  "whole_food": {"name": "整份食物名称", "category": "类别（熟食/剩菜/主食/其他）", "confidence": 置信度 0-100, "shelf_life_days": 冷藏建议天数},
  "foods": [
    {"name": "可拆分食物名称", "category": "类别（蔬菜/水果/肉类/海鲜/蛋类/乳制品/豆制品/主食/熟食/剩菜/其他）", "confidence": 置信度 0-100, "shelf_life_days": 冷藏建议天数}
  ]
}
命名要符合库存管理，而不是菜谱拆料。例如一盘牛排、面、蛋和蔬菜应命名为“牛排面套餐”或“熟食餐盘”；一盒剩饭剩菜命名为“剩菜便当”。只返回 JSON，不要其他文字。如果无法识别，mode 返回 "split"，foods 返回空数组。'''}
                ]
            }]
            
            response = MultiModalConversation.call(
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

                    if whole_food:
                        if 'confidence' in whole_food:
                            whole_food['confidence'] = float(whole_food['confidence'])
                        else:
                            whole_food['confidence'] = 80.0
                        if not whole_food.get('category'):
                            whole_food['category'] = '熟食'
                        if 'shelf_life_days' in whole_food and whole_food['shelf_life_days'] is not None:
                            whole_food['shelf_life_days'] = int(whole_food['shelf_life_days'])
                    
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
    
    def infer_shelf_life(self, food_name: str, category: str, location: str) -> dict:
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
            
            response = dashscope.Generation.call(
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
            
            response = dashscope.Generation.call(
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
