"""
微信小程序登录与会话鉴权
"""

from datetime import datetime, timedelta
import os
import secrets
from typing import Optional

import aiosqlite
import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.database import get_db


router = APIRouter()
WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class LoginRequest(BaseModel):
    code: str = Field(..., min_length=1)


def get_session_expire_days() -> int:
    try:
        return int(os.getenv("AUTH_TOKEN_EXPIRE_DAYS", "30"))
    except ValueError:
        return 30


def allow_dev_login() -> bool:
    return os.getenv("ALLOW_DEV_LOGIN", "false").strip().lower() in ("1", "true", "yes", "on")


def is_local_request(request: Request) -> bool:
    host = request.headers.get("host", "").split(":")[0]
    client_host = request.client.host if request.client else ""
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    return host in local_hosts or client_host in local_hosts


async def exchange_code_for_openid(code: str, request: Request) -> dict:
    appid = os.getenv("WECHAT_APPID", "").strip()
    secret = os.getenv("WECHAT_APP_SECRET", "").strip()

    if allow_dev_login():
        return {"openid": os.getenv("DEV_OPENID", "local-dev-openid")}

    if not appid or not secret:
        if is_local_request(request):
            return {"openid": os.getenv("DEV_OPENID", "local-dev-openid")}
        raise HTTPException(status_code=500, detail="未配置 WECHAT_APPID / WECHAT_APP_SECRET")

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            WECHAT_CODE2SESSION_URL,
            params={
                "appid": appid,
                "secret": secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
    response.raise_for_status()
    data = response.json()
    if data.get("errcode"):
        raise HTTPException(status_code=401, detail=data.get("errmsg") or "微信登录失败")
    if not data.get("openid"):
        raise HTTPException(status_code=401, detail="微信登录失败：未返回 openid")
    return data


async def upsert_user(db: aiosqlite.Connection, openid: str, unionid: Optional[str] = None) -> aiosqlite.Row:
    await db.execute(
        """
        INSERT INTO users (openid, unionid)
        VALUES (?, ?)
        ON CONFLICT(openid) DO UPDATE SET
            unionid = COALESCE(excluded.unionid, users.unionid),
            updated_at = CURRENT_TIMESTAMP
        """,
        (openid, unionid),
    )
    cursor = await db.execute("SELECT * FROM users WHERE openid = ?", (openid,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="用户创建失败")
    return row


async def create_session(db: aiosqlite.Connection, user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(days=get_session_expire_days())).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "INSERT INTO user_sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at),
    )
    await db.commit()
    return token, expires_at


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    session = await exchange_code_for_openid(payload.code, request)
    user = await upsert_user(db, session["openid"], session.get("unionid"))
    token, expires_at = await create_session(db, user["id"])
    return {
        "success": True,
        "data": {
            "token": token,
            "expires_at": expires_at,
            "user": {
                "id": user["id"],
                "openid": user["openid"],
            },
        },
    }


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")

    token = authorization.replace("Bearer ", "", 1).strip()
    cursor = await db.execute(
        """
        SELECT u.*
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = ? AND datetime(s.expires_at) > datetime('now')
        """,
        (token,),
    )
    user = await cursor.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期，请重新进入小程序")
    return dict(user)


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {
        "success": True,
        "data": {
            "id": current_user["id"],
            "openid": current_user["openid"],
        },
    }


@router.post("/logout")
async def logout(
    authorization: Optional[str] = Header(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
        await db.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        await db.commit()
    return {"success": True, "message": "已退出"}