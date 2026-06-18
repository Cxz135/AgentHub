"""
多层记忆框架数据模型。

- MemoryEntry: 语义记忆条目（事实、偏好、决策、用户特征）
- UserProfile:  用户画像（跨会话累积）
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, JSON, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.db.database import Base


class MemoryEntry(Base):
    """
    语义记忆条目。

    由 MemoryExtractor 从对话中自动提取，存储为结构化事实。
    同时写入 Chroma (agent_memories 集合) 以支持语义检索。
    """
    __tablename__ = 'memory_entries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    agent_id = Column(String, nullable=True)  # 哪个 Agent 生成/观察到这条记忆
    conversation_id = Column(Integer, ForeignKey('conversations.id'), nullable=True)  # 来源对话

    # 记忆类型: fact / preference / decision / user_trait
    memory_type = Column(String(32), nullable=False, default='fact', index=True)

    # 记忆内容
    content = Column(Text, nullable=False)

    # 重要性 0.0-1.0，LLM 提取时打分
    importance = Column(Float, default=0.5)

    # LLM 提取时的置信度 0.0-1.0
    confidence = Column(Float, default=0.7)

    # 检索次数（用于衰减计算中的 boost）
    access_count = Column(Integer, default=0)

    # 衰减因子（由 MemoryDecayer 定期更新）
    decay_factor = Column(Float, default=1.0)

    # 元数据：source_message_ids, related_memory_ids 等
    meta_data = Column(JSON, default=dict)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 软删除
    is_active = Column(Boolean, default=True)

    @property
    def effective_score(self) -> float:
        """有效记忆分数 = 重要性 × 衰减因子"""
        return self.importance * self.decay_factor


class UserProfile(Base):
    """
    用户画像：从所有语义记忆中累积的持久化用户模型。

    每次提取新记忆后，由 UserProfiler 增量更新。
    """
    __tablename__ = 'user_profiles'

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)

    # 人类可读的摘要文本（注入系统 prompt）
    summary_text = Column(Text, default='')

    # 结构化特征: [{"trait": "prefers_bullet_points", "confidence": 0.9}, ...]
    traits_json = Column(JSON, default=list)

    # 键值偏好: {"preferred_language": "zh-CN", "code_style": "concise"}
    preferences_json = Column(JSON, default=dict)

    # 最后更新时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
