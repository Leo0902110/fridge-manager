#!/usr/bin/env python3
"""
测试通义千问 AI 服务
"""

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.qwen_service import qwen_service


def test_shelf_life_inference():
    """测试保质期推理"""
    print("\n=== 测试保质期推理 ===")
    
    test_cases = [
        ("苹果", "水果", "fridge"),
        ("牛奶", "乳制品", "fridge"),
        ("猪肉", "肉类", "freezer"),
        ("面包", "主食", "room"),
    ]
    
    for name, category, location in test_cases:
        result = qwen_service.infer_shelf_life(name, category, location)
        location_name = {"fridge": "冷藏", "freezer": "冷冻", "room": "常温"}.get(location, location)
        print(f"{name} ({category}, {location_name}): {result['days']}天 - {result['reason']}")


def test_eating_suggestion():
    """测试食用建议生成"""
    print("\n=== 测试食用建议 ===")
    
    test_cases = [
        ("苹果", 3),
        ("牛奶", 1),
        ("猪肉", 0),
    ]
    
    for name, days in test_cases:
        suggestion = qwen_service.generate_eating_suggestion(name, days)
        print(f"{name} (还剩{days}天): {suggestion}")


def main():
    """主函数"""
    # 检查 API Key
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    
    if not api_key:
        print("❌ 未配置 DASHSCOPE_API_KEY")
        print("\n请先配置环境变量:")
        print("  export DASHSCOPE_API_KEY=sk-your-key")
        print("\n或在 .env 文件中配置:")
        print("  DASHSCOPE_API_KEY=sk-your-key")
        return 1
    
    print(f"✅ API Key 已配置：{api_key[:10]}...")
    
    try:
        test_shelf_life_inference()
        test_eating_suggestion()
        
        print("\n✅ 所有测试完成！")
        return 0
        
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
