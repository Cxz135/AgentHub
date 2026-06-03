# app/main.py
import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from backend.db.database import engine, Base
from backend.utils.logger import logger


# 在创建数据库表之前，确保所有模型都已被加载
# 这是解决 NoReferencedTableError 的最终手段
from backend.models.artifact import Artifact
from backend.models.conversation import Conversation
from backend.models.message import Message
from backend.models.user import User
from backend.models.skill import Skill, SkillInstall


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    logger.info("🚀 应用启动中...")
    # 在生产环境中，我们期望数据库表已经由迁移工具（如 Alembic）创建好。
    # 在测试环境中，表的创建由 conftest.py 负责。
    # 因此，在应用生命周期中自动创建表是不推荐的做法。
    Base.metadata.create_all(bind=engine)
    logger.info("✅ 数据库表已创建，应用已就绪")

    yield

    # 关闭
    logger.info("🛑 应用关闭中...")


def create_app() -> FastAPI:
    """
    应用工厂，用于创建并配置 FastAPI 应用实例。
    """
    app = FastAPI(
        title="AgentHub - 多Agent协作平台",
        description="IM 式多Agent聊天系统",
        lifespan=lifespan
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 导入路由
    from backend.app.api import conversations, messages, agents, chat, auth, skills

    app.include_router(conversations.router, prefix="/api/conversations", tags=["Conversations"])
    app.include_router(messages.router, prefix="/api", tags=["Messages"])
    app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
    app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
    app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
    app.include_router(skills.router, prefix="/api/skills", tags=["Skills"])
    
    # 添加健康检查端点以匹配组员的前端
    @app.get("/api/health")
    async def api_health():
        return {"ok": True, "status": "running"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)