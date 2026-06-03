import uuid
from datetime import datetime
from sqlalchemy import Column, String, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from backend.db.database import Base

class Artifact(Base):
    """
    表示由Agent生成的一个产物，例如代码、文档、预览URL等。
    """
    __tablename__ = 'artifacts'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String, ForeignKey("messages.id"), nullable=False)
    message = relationship("Message")

    # 产物类型，例如 "code", "diff", "preview_url", "file"
    type = Column(String, nullable=False)

    # 产物的内容或引用
    content = Column(String)

    # 产物的元数据，例如文件名、语言类型等
    meta_data = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)