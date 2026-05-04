"""
Fridge Manager Backend API - Main Entry Point
冰箱管家后端 API - 主入口
"""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

load_dotenv(Path(__file__).resolve().with_name(".env"))

from app.db.database import init_db
from app.api import auth, foods, recognition, reminders


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    await init_db()
    try:
        yield
    finally:
        # 关闭时清理资源
        pass


app = FastAPI(
    lifespan=lifespan,
    title="🧊 冰箱管家 API",
    description="""
## Fridge Manager - 智能冰箱食物管理

### 功能:
- **食物识别**: 拍照 AI 识别食物类型
- **保质期管理**: 智能推理临期时间
- **提醒通知**: 到期前微信通知
- **库存管理**: 可视化冰箱状态
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 配置 - 允许小程序访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://servicewechat.com",  # 微信小程序
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

uploads_dir = Path(__file__).resolve().with_name("uploads")
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# 注册路由
app.include_router(auth.router, prefix="/api/v1/auth", tags=["用户登录"])
app.include_router(foods.router, prefix="/api/v1/foods", tags=["食物管理"])
app.include_router(recognition.router, prefix="/api/v1/recognition", tags=["AI 识别"])
app.include_router(reminders.router, prefix="/api/v1/reminders", tags=["提醒通知"])


@app.get("/", tags=["root"])
async def root():
    """根路径 - API 健康检查"""
    return {
        "message": "🧊 欢迎使用冰箱管家 API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "fridge-manager-api",
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
