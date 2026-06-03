# models/skill.py
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from backend.db.database import Base

class Skill(Base):
    """
    技能模型，存储所有技能的详细信息
    """
    __tablename__ = 'skills'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String, unique=True, nullable=False)           # URL友好的唯一标识
    name = Column(String, nullable=False)                       # 技能名称
    icon = Column(String, default='extension')                  # 图标
    description = Column(Text, default='')                      # 描述
    code = Column(Text, default='')                              # 技能代码
    readme = Column(Text, default='')                            # README文档
    category = Column(String, default='custom')                 # 分类
    author_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # 作者ID
    author_name = Column(String, default='system')               # 作者名称
    is_published = Column(Boolean, default=False)                # 是否发布
    install_count = Column(Integer, default=0)                   # 安装次数
    parent_id = Column(Integer, ForeignKey('skills.id'), nullable=True)  # 父技能ID（用于fork）
    versions = Column(Text, default='[]')                        # 版本历史（JSON字符串）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 建立关系
    author = relationship("User", back_populates="skills")
    
    def __repr__(self):
        return f"<Skill(id={self.id}, slug='{self.slug}', name='{self.name}')>"

class SkillInstall(Base):
    """
    技能安装关联表，记录用户安装的技能
    """
    __tablename__ = 'skill_installs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    skill_id = Column(Integer, ForeignKey('skills.id'), nullable=False)
    installed_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<SkillInstall(user_id={self.user_id}, skill_id={self.skill_id})>"