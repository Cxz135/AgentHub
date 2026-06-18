# app/main.py

import os
from dotenv import load_dotenv, find_dotenv

# 自动往上搜索 .env 文件（不管从哪个目录启动都能找到）
dotenv_path = find_dotenv(usecwd=True)
load_dotenv(dotenv_path)
if not dotenv_path:
    print("⚠️ 未找到 .env 文件，API keys 可能未加载")

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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
from backend.models.custom_agent import CustomAgent
from backend.models.memory import MemoryEntry, UserProfile


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    logger.info("🚀 应用启动中...")
    # 在生产环境中，我们期望数据库表已经由迁移工具（如 Alembic）创建好。
    # 在测试环境中，表的创建由 conftest.py 负责。
    # 因此，在应用生命周期中自动创建表是不推荐的做法。
    Base.metadata.create_all(bind=engine)
    # 检查并修复缺失的列（SQLite 的 create_all 不会给已有表加新列）
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        columns = [c['name'] for c in inspector.get_columns('conversations')]
        if 'squad_config' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN squad_config JSON DEFAULT '{}'"))
                conn.commit()
                logger.info("✅ 已添加缺失列: conversations.squad_config")
        # 检查 custom_agents 表是否有 icon 和 description 列
        ca_columns = [c['name'] for c in inspector.get_columns('custom_agents')]
        if 'icon' not in ca_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE custom_agents ADD COLUMN icon VARCHAR DEFAULT 'smart_toy'"))
                conn.commit()
                logger.info("✅ 已添加缺失列: custom_agents.icon")
        if 'description' not in ca_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE custom_agents ADD COLUMN description VARCHAR DEFAULT ''"))
                conn.commit()
                logger.info("✅ 已添加缺失列: custom_agents.description")
        # A 档：检查 custom_agents 表是否有 memory_config / planning_config / validation_config 列
        # SQLite 的 create_all 不会给已有表加新列，需要手动 ALTER
        for col_name in ('memory_config', 'planning_config', 'validation_config'):
            if col_name not in ca_columns:
                with engine.connect() as conn:
                    # SQLite JSON 列实际上以 TEXT 形式存储，SQLAlchemy 读写时会做 JSON 序列化
                    conn.execute(text(f"ALTER TABLE custom_agents ADD COLUMN {col_name} JSON DEFAULT NULL"))
                    conn.commit()
                    logger.info(f"✅ 已添加缺失列: custom_agents.{col_name}")
        # 检查 custom_agents 表是否有 user_id 列
        if 'user_id' not in ca_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE custom_agents ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                conn.commit()
                logger.info("✅ 已添加缺失列: custom_agents.user_id")
        # 检查 conversations 表是否有缺失列
        conv_columns = [c['name'] for c in inspector.get_columns('conversations')]
        if 'user_id' not in conv_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                conn.commit()
                logger.info("✅ 已添加缺失列: conversations.user_id")
        if 'last_active_at' not in conv_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN last_active_at DATETIME"))
                conn.commit()
                logger.info("✅ 已添加缺失列: conversations.last_active_at")
        if 'is_pinned' not in conv_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN is_pinned BOOLEAN DEFAULT 0"))
                conn.commit()
                logger.info("✅ 已添加缺失列: conversations.is_pinned")
        if 'is_archived' not in conv_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN is_archived BOOLEAN DEFAULT 0"))
                conn.commit()
                logger.info("✅ 已添加缺失列: conversations.is_archived")
        if 'mode' not in conv_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN mode VARCHAR DEFAULT 'single'"))
                conn.commit()
                logger.info("✅ 已添加缺失列: conversations.mode")
        if 'participants' not in conv_columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN participants JSON DEFAULT '[]'"))
                conn.commit()
                logger.info("✅ 已添加缺失列: conversations.participants")
        # 检查 messages 表列
        try:
            msg_columns = [c['name'] for c in inspector.get_columns('messages')]
            if 'is_pinned' not in msg_columns:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE messages ADD COLUMN is_pinned BOOLEAN DEFAULT 0"))
                    conn.commit()
                    logger.info("✅ 已添加缺失列: messages.is_pinned")
            if 'mentions' not in msg_columns:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE messages ADD COLUMN mentions JSON DEFAULT '[]'"))
                    conn.commit()
                    logger.info("✅ 已添加缺失列: messages.mentions")
            if 'meta_data' not in msg_columns:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE messages ADD COLUMN meta_data JSON DEFAULT '{}'"))
                    conn.commit()
                    logger.info("✅ 已添加缺失列: messages.meta_data")
            if 'updated_at' not in msg_columns:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE messages ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
                    conn.commit()
                    logger.info("✅ 已添加缺失列: messages.updated_at")
        except Exception as e:
            logger.warning(f"⚠️ 检查/修复 messages 表列时出错: {e}")
        # 检查 artifacts 表是否有 conversation_id 列
        try:
            art_columns = [c['name'] for c in inspector.get_columns('artifacts')]
            if 'conversation_id' not in art_columns:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE artifacts ADD COLUMN conversation_id INTEGER"))
                    conn.commit()
                    logger.info("✅ 已添加缺失列: artifacts.conversation_id")
        except Exception:
            pass  # 表可能还不存在
        # 检查 messages 表是否有 importance 列（多层记忆框架）
        try:
            msg_columns_v2 = [c['name'] for c in inspector.get_columns('messages')]
            if 'importance' not in msg_columns_v2:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE messages ADD COLUMN importance REAL DEFAULT 0.5"))
                    conn.commit()
                    logger.info("✅ 已添加缺失列: messages.importance")
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"⚠️ 检查/修复数据库列时出错: {e}")
    # 迁移无主的 agents/missions 到第一个用户（兼容旧数据）
    try:
        from backend.db.database import SessionLocal
        db_migrate = SessionLocal()
        first_user = db_migrate.query(User).order_by(User.id).first()
        if first_user:
            orphan_agents = db_migrate.query(CustomAgent).filter(CustomAgent.user_id == None).all()
            for agent in orphan_agents:
                agent.user_id = first_user.id
                logger.info(f"🔄 迁移无主Agent '{agent.name}' 到用户 {first_user.username}")
            orphan_convs = db_migrate.query(Conversation).filter(Conversation.user_id == None).all()
            for conv in orphan_convs:
                conv.user_id = first_user.id
                logger.info(f"🔄 迁移无主Mission '{conv.title}' 到用户 {first_user.username}")
            if orphan_agents or orphan_convs:
                db_migrate.commit()
                logger.info(f"✅ 无主数据迁移完成: {len(orphan_agents)} 个Agent, {len(orphan_convs)} 个Mission")
        db_migrate.close()
    except Exception as e:
        logger.warning(f"⚠️ 迁移无主数据时出错: {e}")
    # 将 skills/*.md 原生技能写入数据库（种子数据）
    try:
        from backend.db.database import SessionLocal
        from backend.app.api.skills import seed_native_skills_to_db
        db = SessionLocal()
        seed_native_skills_to_db(db)
        db.close()
    except Exception as e:
        logger.warning(f"⚠️ 写入技能种子数据时出错: {e}")
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
        allow_origins=["http://localhost:7065", "http://localhost:3030", "http://localhost:8000", "http://localhost:8080", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 导入路由
    from backend.app.api import conversations, messages, agents, chat, auth, skills, knowledge, websocket, attachments, artifacts_api, memory

    app.include_router(conversations.router, prefix="/api/missions", tags=["Missions"])
    app.include_router(messages.router, prefix="/api", tags=["Messages"])
    app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
    app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
    # 移除auth和skills的前缀，让接口路径与前端一致
    app.include_router(auth.router, prefix="/api", tags=["Authentication"])
    app.include_router(skills.router, prefix="/api/skills", tags=["Skills"])
    app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Knowledge"])
    app.include_router(attachments.router, prefix="/api", tags=["Attachments"])
    app.include_router(artifacts_api.router, prefix="/api", tags=["Artifacts"])
    app.include_router(memory.router, prefix="/api", tags=["Memory"])
    # WebSocket 路由
    app.include_router(websocket.router, tags=["WebSocket"])

    # 添加健康检查端点以匹配组员的前端
    @app.get("/api/health")
    async def api_health():
        return {"ok": True, "status": "running"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    # 调试：打印所有注册的路由
    print("\n=== 所有注册的路由 ===")
    for route in app.routes:
        if hasattr(route, 'path'):
            print(f"{route.path} -> {route.name}")
    print("======================\n")

    # 附件静态文件访问（必须在前端 / 挂载之前，否则会被前端截获）
    if os.path.isdir(attachments.UPLOAD_DIR):
        app.mount("/attachments", StaticFiles(directory=attachments.UPLOAD_DIR), name="attachments")
    else:
        os.makedirs(attachments.UPLOAD_DIR, exist_ok=True)
        app.mount("/attachments", StaticFiles(directory=attachments.UPLOAD_DIR), name="attachments")
    print(f"✅ 附件静态文件已挂载: {attachments.UPLOAD_DIR}")

    # 静态托管前端（必须放最后，确保 API 路由优先级更高）
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'AgentHub-my flicker'))
    if os.path.isdir(frontend_dir):
        try:
            app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
            print(f"✅ 前端静态文件已挂载: {frontend_dir}")
        except Exception as e:
            print(f"⚠️ 挂载前端失败（可忽略，不影响 API）: {e}")

    return app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)