"""
提醒通知 API
支持微信订阅消息
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import date, timedelta
from pydantic import BaseModel
from typing import Optional
import aiosqlite

from app.db.database import get_db

router = APIRouter()


class ReminderCreate(BaseModel):
    """创建提醒"""
    food_id: int
    remind_date: date
    message: str


class Reminder(BaseModel):
    """提醒模型"""
    id: int
    food_id: int
    remind_date: date
    message: str
    is_sent: bool
    created_at: str


@router.get("/pending")
async def get_pending_reminders(
    db: aiosqlite.Connection = Depends(get_db),
):
    """获取待发送的提醒"""
    today = date.today()
    
    cursor = await db.execute("""
        SELECT r.*, f.name as food_name, f.expiry_date
        FROM reminders r
        JOIN foods f ON r.food_id = f.id
        WHERE r.is_sent = 0 AND r.remind_date <= ?
        ORDER BY r.remind_date ASC
    """, (today.isoformat(),))
    
    rows = await cursor.fetchall()
    
    return {
        "success": True,
        "data": [dict(row) for row in rows],
        "count": len(rows),
    }


@router.post("/check-expiry")
async def check_and_create_expiry_reminders(
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    检查即将过期的食物并创建提醒
    
    自动为 3 天内过期的食物创建提醒
    """
    today = date.today()
    warning_date = today + timedelta(days=3)
    
    # 查找 3 天内过期的食物
    cursor = await db.execute("""
        SELECT * FROM foods
        WHERE expiry_date BETWEEN ? AND ?
        AND status != 'expired'
    """, (today.isoformat(), warning_date.isoformat()))
    
    foods = await cursor.fetchall()
    created_count = 0
    
    for food in foods:
        # 检查是否已有提醒
        cursor = await db.execute(
            "SELECT id FROM reminders WHERE food_id = ? AND is_sent = 0",
            (food["id"],)
        )
        existing = await cursor.fetchone()
        
        if not existing:
            # 创建提醒
            days_left = (food["expiry_date"] - today).days
            message = f"⚠️ {food['name']} 还有 {days_left} 天过期，请尽快食用！"
            
            await db.execute("""
                INSERT INTO reminders (food_id, remind_date, message)
                VALUES (?, ?, ?)
            """, (food["id"], today.isoformat(), message))
            created_count += 1
    
    await db.commit()
    
    return {
        "success": True,
        "message": f"已创建 {created_count} 条临期提醒",
        "data": {
            "created_count": created_count,
            "warning_foods": [dict(f) for f in foods],
        },
    }


@router.put("/{reminder_id}/send")
async def mark_reminder_sent(
    reminder_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    """标记提醒已发送"""
    await db.execute(
        "UPDATE reminders SET is_sent = 1 WHERE id = ?",
        (reminder_id,)
    )
    await db.commit()
    
    return {"success": True, "message": "提醒已标记为已发送"}


@router.get("/history")
async def get_reminder_history(
    limit: int = 50,
    db: aiosqlite.Connection = Depends(get_db),
):
    """获取提醒历史"""
    cursor = await db.execute("""
        SELECT r.*, f.name as food_name
        FROM reminders r
        JOIN foods f ON r.food_id = f.id
        ORDER BY r.remind_date DESC
        LIMIT ?
    """, (limit,))
    
    rows = await cursor.fetchall()
    
    return {
        "success": True,
        "data": [dict(row) for row in rows],
    }


@router.post("/wechat/template")
async def send_wechat_reminder(
    user_id: str,
    template_id: str,
    food_name: str,
    expiry_date: date,
    days_left: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    发送微信订阅消息提醒
    
    需要在微信公众平台配置订阅消息模板
    模板示例:
    - thing1: 食物名称
    - date2: 过期时间
    - thing3: 提醒内容
    """
    # 这里需要接入微信 API
    # 由于需要 access_token 和具体的模板配置
    # 实际使用时需要完善这部分代码
    
    return {
        "success": True,
        "message": "提醒发送接口（需配置微信 API）",
        "data": {
            "user_id": user_id,
            "food_name": food_name,
            "expiry_date": expiry_date.isoformat(),
            "days_left": days_left,
        },
    }
