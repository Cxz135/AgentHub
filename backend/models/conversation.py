import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, JSON, Integer
from sqlalchemy.orm import relationship
from backend.db.database import Base

class Conversation(Base):
    """
    会话模型，代表一个独立的聊天会话。
    """
    __tablename__ = 'conversations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, default="新会话", nullable=False)  # 会话标题
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 最后活跃时间，用于排序
    is_pinned = Column(Boolean, default=False)  # 是否置顶
    is_archived = Column(Boolean, default=False)  # 是否归档
    mode = Column(String, default="single", nullable=False)  # 会话模式: single(单聊) / group(群聊)
    participants = Column(JSON, default=list)  # 群聊参与者列表，存储agent_ids

    # 建立与 Message 的反向关系
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Conversation(id={self.id}, title='{self.title}')>"