"""
数据库配置和初始化
"""

import aiosqlite
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent.parent / "fridge.db"

_db: Optional[aiosqlite.Connection] = None


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接"""
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
    return _db


async def init_db():
    """初始化数据库表"""
    db = await get_db()
    
    # 食物表
    await db.execute("""
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            image_url TEXT,
            put_date DATE NOT NULL,
            expiry_date DATE NOT NULL,
            shelf_life_days INTEGER,
            status TEXT DEFAULT 'fresh',
            location TEXT DEFAULT 'fridge',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 食物状态：fresh(新鲜), warning(临期), expired(过期)
    
    # 提醒表
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_id INTEGER NOT NULL,
            user_id TEXT,
            remind_date DATE NOT NULL,
            message TEXT,
            is_sent INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE
        )
    """)
    
    # 食物保质期参考表（内置常见食物保质期）
    await db.execute("""
        CREATE TABLE IF NOT EXISTS shelf_life_reference (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_name TEXT NOT NULL UNIQUE,
            category TEXT,
            fridge_days INTEGER,
            freezer_days INTEGER,
            room_temp_days INTEGER,
            recommended_location TEXT DEFAULT 'fridge',
            storage_tip TEXT
        )
    """)

    cursor = await db.execute("PRAGMA table_info(shelf_life_reference)")
    columns = {row["name"] for row in await cursor.fetchall()}
    if "recommended_location" not in columns:
        await db.execute("ALTER TABLE shelf_life_reference ADD COLUMN recommended_location TEXT DEFAULT 'fridge'")
    if "storage_tip" not in columns:
        await db.execute("ALTER TABLE shelf_life_reference ADD COLUMN storage_tip TEXT")

    await db.execute("""
        DELETE FROM shelf_life_reference
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM shelf_life_reference
            GROUP BY food_name
        )
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_shelf_life_reference_food_name
        ON shelf_life_reference(food_name)
    """)
    
    # 参考表是规则数据，启动时刷新为当前版本，避免旧离谱数据继续影响推荐。
    await db.execute("DELETE FROM shelf_life_reference")
    await db.execute("""
        INSERT INTO shelf_life_reference
        (food_name, category, fridge_days, freezer_days, room_temp_days, recommended_location, storage_tip) VALUES
        ('牛奶', '乳制品', 5, 30, 0, 'fridge', '开封后冷藏并尽快喝完'),
        ('酸奶', '乳制品', 10, 30, 0, 'fridge', '保持冷藏，不建议常温放置'),
        ('鸡蛋', '蛋类', 30, 90, 14, 'fridge', '冷藏更稳定，避免反复温差'),
        ('猪肉', '肉类', 2, 180, 0, 'freezer', '当天不吃建议分装冷冻'),
        ('牛肉', '肉类', 3, 180, 0, 'freezer', '短期冷藏，长期分装冷冻'),
        ('鸡肉', '肉类', 2, 180, 0, 'freezer', '生肉当天不吃建议冷冻'),
        ('鱼', '海鲜', 1, 90, 0, 'freezer', '海鲜易变质，尽量当天吃或冷冻'),
        ('虾', '海鲜', 1, 90, 0, 'freezer', '海鲜易变质，尽量当天吃或冷冻'),
        ('白菜', '蔬菜', 7, 0, 2, 'fridge', '用保鲜袋冷藏，减少失水'),
        ('胡萝卜', '蔬菜', 14, 0, 5, 'fridge', '冷藏保存，避免潮湿霉变'),
        ('西红柿', '蔬菜', 5, 0, 3, 'room', '未切开可阴凉常温，切开后冷藏'),
        ('黄瓜', '蔬菜', 5, 0, 2, 'fridge', '冷藏保存，尽快食用'),
        ('土豆', '蔬菜', 7, 0, 21, 'room', '阴凉避光常温，避免冷藏变甜'),
        ('苹果', '水果', 21, 60, 5, 'fridge', '冷藏延长新鲜度，和易熟水果分开'),
        ('香蕉', '水果', 3, 0, 3, 'room', '常温保存，冷藏会加速表皮变黑'),
        ('橙子', '水果', 14, 60, 7, 'fridge', '冷藏更耐放，常温尽快吃'),
        ('草莓', '水果', 2, 30, 1, 'fridge', '不要清洗后久放，冷藏尽快吃'),
        ('葡萄', '水果', 5, 30, 1, 'fridge', '冷藏保存，吃前再洗'),
        ('面包', '主食', 3, 30, 2, 'room', '短期常温，吃不完切片冷冻'),
        ('米饭', '主食', 2, 14, 0, 'fridge', '熟米饭冷却后及时冷藏'),
        ('面条', '主食', 2, 30, 0, 'fridge', '熟面条冷藏，尽快吃完'),
        ('豆腐', '豆制品', 2, 30, 0, 'fridge', '开封后换水冷藏并尽快食用'),
        ('豆浆', '豆制品', 1, 14, 0, 'fridge', '现磨或开封后当天饮用更稳妥'),
        ('奶酪', '乳制品', 14, 90, 0, 'fridge', '密封冷藏，注意霉变异味'),
        ('黄油', '乳制品', 30, 180, 3, 'fridge', '密封冷藏，避免串味'),
        ('剩菜', '剩菜', 2, 14, 0, 'fridge', '冷却后尽快冷藏，复热要彻底'),
        ('剩菜便当', '剩菜', 2, 14, 0, 'fridge', '按整份熟食管理，建议两天内吃完'),
        ('熟食餐盘', '熟食', 2, 14, 0, 'fridge', '按整份熟食管理，建议两天内吃完'),
        ('熟食拼盘', '熟食', 2, 14, 0, 'fridge', '按整份熟食管理，建议两天内吃完'),
        ('便当', '熟食', 2, 14, 0, 'fridge', '饭菜混合后按熟食处理'),
        ('套餐', '熟食', 2, 14, 0, 'fridge', '整份保存，不按单个配菜拆保质期'),
        ('炒菜', '熟食', 2, 14, 0, 'fridge', '熟菜冷却后及时冷藏'),
        ('炒饭', '熟食', 2, 14, 0, 'fridge', '米饭类熟食建议两天内吃完'),
        ('熟肉', '熟食', 3, 30, 0, 'fridge', '密封冷藏，长期保存可冷冻'),
        ('炖菜', '熟食', 3, 30, 0, 'fridge', '汤汁类冷藏并彻底复热'),
        ('汤', '熟食', 2, 30, 0, 'fridge', '冷却后密封冷藏，复热煮沸'),
        ('生菜', '蔬菜', 3, 0, 1, 'fridge', '叶菜冷藏并尽快食用'),
        ('菠菜', '蔬菜', 3, 0, 1, 'fridge', '叶菜冷藏并尽快食用'),
        ('青椒', '蔬菜', 7, 0, 3, 'fridge', '冷藏保存，避免受潮'),
        ('洋葱', '蔬菜', 14, 0, 21, 'room', '阴凉通风常温保存'),
        ('大蒜', '蔬菜', 30, 0, 30, 'room', '阴凉干燥常温保存'),
        ('姜', '蔬菜', 14, 0, 14, 'room', '阴凉通风，切开后冷藏')
    """)
    
    await db.commit()
    print("✅ 数据库初始化完成")


async def close_db():
    """关闭数据库连接"""
    global _db
    if _db:
        await _db.close()
        _db = None
