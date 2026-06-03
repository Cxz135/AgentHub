import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean, JSON, Integer
from sqlalchemy.orm import relationship
from backend.db.database import Base

class Message(Base):
    """
    消息模型，代表会话中的一条消息。
    """
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey('conversations.id'), nullable=False)
    agent_id = Column(String, nullable=False)  # 发送者ID, 'user' 代表用户
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_pinned = Column(Boolean, default=False)  # 是否固定消息
    mentions = Column(JSON, default=list)  # @提到的agent_ids列表
    meta_data = Column(JSON, default=dict)  # 其他元数据

    # 建立与 Conversation 的关系
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, agent_id='{self.agent_id}', conversation_id={self.conversation_id})>"