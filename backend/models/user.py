# models/user.py
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Integer
from sqlalchemy.orm import relationship
from backend.db.database import Base

class User(Base):
    """
    用户模型，存储用户账号信息
    """
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)  # 用户名
    email = Column(String, unique=True, nullable=False)     # 邮箱
    password_hash = Column(String, nullable=False)          # 密码哈希
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)               # 是否活跃
    
    # 与技能的关系：一个用户可以创建多个技能
    skills = relationship("Skill", back_populates="author")
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"