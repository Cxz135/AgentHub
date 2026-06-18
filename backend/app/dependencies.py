#dependencies.py

from backend.core.orchestrator import Orchestrator
from backend.utils.logger import logger
from backend.core.orchestrator import Orchestrator
from backend.utils.logger import logger
from backend.db.database import SessionLocal

def get_db():
    """
    FastAPI 依赖项，用于获取数据库会话。
    确保每个请求都有一个独立的会话，并在请求结束后关闭。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 全局 Orchestrator 实例
# 在大型应用中，你可能会使用更复杂的生命周期管理
# 但对于当前阶段，一个简单的全局实例是清晰和高效的
_orchestrator_instance = None


def get_orchestrator() -> Orchestrator:
    """
    FastAPI 依赖项，用于获取全局唯一的 Orchestrator 实例。
    如果实例不存在，则创建它。

    注意：Orchestrator 创建时不传入持久化 db_session。
    每个请求通过 chat.py / websocket.py 独立注入 request-scoped session，
    避免全局 session 过期或跨请求污染。
    """
    global _orchestrator_instance
    if _orchestrator_instance is None:
        logger.info("正在创建全局 Orchestrator 实例...")
        _orchestrator_instance = Orchestrator()
        logger.info("Orchestrator 实例创建完成。")

    return _orchestrator_instance