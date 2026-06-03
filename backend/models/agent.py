from datetime import datetime
from sqlalchemy import Column, String, JSON, Boolean, DateTime
from backend.db.database import Base

class Agent(Base):
    """
    表示一个 Agent 的数据库模型。

    存储了 Agent 的元数据信息，例如它的名字、描述、能力等。
    这与 Agent 的运行时行为 (BaseAgent) 是分离的。
    """
    __tablename__ = "agents"

    # Agent 的唯一 ID，例如 "tongyi", "deepseek"
    # 这将用于 @ 提及和 Orchestrator 的路由
    id = Column(String, primary_key=True)

    # Agent 的显示名称
    name = Column(String, nullable=False, unique=True)

    # Agent 的描述，用于在 UI 中展示或用于其他 Agent 理解其功能
    description = Column(String)

    # Agent 的能力列表，例如 ["code_generation", "image_creation"]
    capabilities = Column(JSON, default=[])

    # Agent 所使用的底层模型名称，例如 "qwen-plus", "deepseek-coder"
    model = Column(String)

    # Agent 的特定配置参数
    parameters = Column(JSON, default={})

    # 是否是用户自定义的 Agent
    is_custom = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)