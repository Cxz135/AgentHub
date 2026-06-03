# models/base.py

import uuid


from datetime import datetime
from sqlalchemy import Column, String, DateTime
from sqlalchemy.ext.declarative import declared_attr
from backend.db.database import Base


class BaseModel(Base):
    """
    所有数据模型的基类，提供了通用的字段和表名生成规则。
    """
    __abstract__ = True  # 表示这是一个抽象基类，SQLAlchemy不会为它创建表

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def __tablename__(cls):
        # 自动将类名转换为小写的表名，例如 "Conversation" -> "conversations"
        return cls.__name__.lower() + "s"


