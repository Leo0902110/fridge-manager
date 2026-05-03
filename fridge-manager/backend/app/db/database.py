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
            room_temp_days INTEGER
        )
    """)

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
    
    # 插入常见食物保质期数据
    await db.execute("""
        INSERT OR IGNORE INTO shelf_life_reference (food_name, category, fridge_days, freezer_days, room_temp_days) VALUES
        ('牛奶', '乳制品', 7, 30, 1),
        ('酸奶', '乳制品', 14, 30, 2),
        ('鸡蛋', '蛋类', 30, 60, 7),
        ('猪肉', '肉类', 3, 180, 1),
        ('牛肉', '肉类', 5, 365, 1),
        ('鸡肉', '肉类', 2, 180, 1),
        ('鱼', '海鲜', 2, 180, 1),
        ('虾', '海鲜', 2, 180, 1),
        ('白菜', '蔬菜', 7, 0, 3),
        ('胡萝卜', '蔬菜', 14, 0, 7),
        ('西红柿', '蔬菜', 7, 0, 5),
        ('黄瓜', '蔬菜', 7, 0, 3),
        ('土豆', '蔬菜', 14, 0, 30),
        ('苹果', '水果', 30, 180, 7),
        ('香蕉', '水果', 7, 0, 3),
        ('橙子', '水果', 14, 0, 7),
        ('草莓', '水果', 3, 30, 1),
        ('葡萄', '水果', 7, 30, 2),
        ('面包', '主食', 7, 30, 3),
        ('米饭', '主食', 2, 30, 1),
        ('面条', '主食', 3, 90, 1),
        ('豆腐', '豆制品', 3, 30, 1),
        ('豆浆', '豆制品', 2, 30, 1),
        ('奶酪', '乳制品', 14, 180, 3),
        ('黄油', '乳制品', 30, 365, 7),
        ('剩菜', '剩菜', 2, 14, 0),
        ('剩菜便当', '剩菜', 2, 14, 0),
        ('熟食餐盘', '熟食', 2, 14, 0),
        ('熟食拼盘', '熟食', 2, 14, 0),
        ('便当', '熟食', 2, 14, 0),
        ('套餐', '熟食', 2, 14, 0),
        ('炒菜', '熟食', 2, 14, 0),
        ('炒饭', '熟食', 2, 30, 0),
        ('熟肉', '熟食', 3, 30, 0),
        ('炖菜', '熟食', 3, 30, 0),
        ('汤', '熟食', 2, 30, 0),
        ('生菜', '蔬菜', 5, 0, 2),
        ('菠菜', '蔬菜', 5, 0, 2),
        ('青椒', '蔬菜', 7, 0, 5),
        ('洋葱', '蔬菜', 30, 0, 30),
        ('大蒜', '蔬菜', 30, 0, 30),
        ('姜', '蔬菜', 14, 0, 14)
    """)
    
    await db.commit()
    print("✅ 数据库初始化完成")


async def close_db():
    """关闭数据库连接"""
    global _db
    if _db:
        await _db.close()
        _db = None
