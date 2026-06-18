"""
记忆框架基类：MemoryEntry, MemoryContext, MemoryConfig, BaseMemory

类型体系：
    MemoryType         — 长期记忆四分类（user / feedback / project / reference）
    MemoryLifecycleStage — 各层记忆生命周期阶段
"""

from __future__ import annotations

import enum
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════

class MemoryType(enum.StrEnum):
    """
    长期记忆四分类（Claude Auto Memory 标准）。

    - user:      用户身份、偏好、沟通风格、通用习惯
    - feedback:  用户明确纠正、禁止事项（必须包含 Why 和 How）
    - project:   项目目标、架构决策、业务规则、历史踩坑
    - reference: 外部文档链接、关键标识符、常用配置、第三方依赖
    """

    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"

    @classmethod
    def from_legacy(cls, legacy_type: str) -> MemoryType:
        """将旧的 memory_type 映射到新分类。"""
        mapping = {
            "fact": cls.PROJECT,
            "decision": cls.PROJECT,
            "preference": cls.USER,
            "user_trait": cls.USER,
        }
        return mapping.get(legacy_type, cls.PROJECT)

    @classmethod
    def valid_values(cls) -> set[str]:
        """返回所有合法值（含旧类型，供检索过滤使用）。"""
        return {t.value for t in cls} | {"fact", "preference", "decision", "user_trait"}


class MemoryLifecycleStage(enum.StrEnum):
    """
    记忆生命周期阶段。

    CREATED   → 刚创建，尚未经过 WriteGuard 验证或人工确认
    ACTIVE    → 正常使用中
    DORMANT   → 超过 30 天未访问，评分降低
    ARCHIVED  → 评分低于阈值，移入归档存储
    DESTROYED → 已永久删除
    """

    CREATED = "created"
    ACTIVE = "active"
    DORMANT = "dormant"
    ARCHIVED = "archived"
    DESTROYED = "destroyed"

    def is_retrievable(self) -> bool:
        """是否仍可被检索。"""
        return self in (MemoryLifecycleStage.CREATED, MemoryLifecycleStage.ACTIVE)

    def is_terminal(self) -> bool:
        """是否为终态（不会再变化）。"""
        return self in (MemoryLifecycleStage.DESTROYED,)


@dataclass
class MemoryEntry:
    """统一的记忆条目，所有子记忆组件共用此结构。"""

    content: str
    memory_type: str = "general"  # 优先使用 MemoryType 四分类: user | feedback | project | reference
    importance: float = 0.5       # 0.0 ~ 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    # 可选：持久化后的 ID
    entry_id: Optional[str] = None

    # 生命周期
    lifecycle_stage: str = "active"  # 见 MemoryLifecycleStage

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "entry_id": self.entry_id,
            "lifecycle_stage": self.lifecycle_stage,
        }

    def is_retrievable(self) -> bool:
        """是否仍可被检索到。"""
        return self.lifecycle_stage in (
            MemoryLifecycleStage.CREATED.value,
            MemoryLifecycleStage.ACTIVE.value,
        )


@dataclass
class MemoryContext:
    """
    MemoryManager.gather_context() 的返回值。

    调用方（如 Orchestrator）直接使用这些字段构建 LLM prompt。
    """

    instructions: str = ""                              # 合并后的系统指令
    short_term_messages: List[dict] = field(default_factory=list)   # 裁剪后的 [{"role":..., "content":...}]
    working_state: dict = field(default_factory=dict)              # 当前任务状态
    summary_context: str = ""                           # 历史对话摘要文本
    long_term_memories: List[MemoryEntry] = field(default_factory=list)  # 语义检索到的长期记忆
    user_profile: str = ""                              # 用户画像摘要文本


@dataclass
class MemoryConfig:
    """MemoryManager 全局配置。"""

    # ShortTermMemory
    short_term_strategy: str = "sliding_window"     # "none" | "sliding_window" | "summary"
    short_term_window_size: int = 10
    short_term_max_tokens: int = 8000

    # LongTermMemory
    long_term_semantic_enabled: bool = True
    long_term_extraction_enabled: bool = True
    long_term_decay_enabled: bool = True
    long_term_retrieval_top_k: int = 5

    # SummaryMemory
    summary_enabled: bool = True

    # WorkingMemory
    working_enabled: bool = True

    # InstructionMemory
    instruction_scopes: List[str] = field(default_factory=lambda: ["global"])

    # WriteGuard（新增）
    write_guard_enabled: bool = True                    # 是否启用写入前过滤
    classification_strict_mode: bool = False            # True=仅接受四分类，False=兼容旧类型

    # SessionMemoryAgent 渐进压缩（新增）
    session_compression_enabled: bool = True            # 是否启用后台会话压缩
    session_compression_max_tokens: int = 8000          # 触发压缩的 token 预算上限
    session_compression_thresholds: Any = None   # 自定义压缩阈值 Dict[int,float]（None=使用默认）

    # 全局开关
    llm_backend: Any = None         # LLM 后端（摘要、提取等需要）
    embed_model: Any = None         # 嵌入模型（语义检索需要）
    db_session: Any = None          # 数据库会话


@dataclass
class GuardResult:
    """MemoryWriteGuard 单条评估结果。"""

    allowed: bool
    rule: str = ""          # 被哪条规则拦截（allowed=False 时有值）
    reason: str = ""        # 拒绝原因的人类可读描述
    score: float = 1.0      # 0.0 ~ 1.0，评估后的重要性修正


class BaseMemory(ABC):
    """所有记忆组件的抽象基类。"""

    def __init__(self, config: MemoryConfig = None):
        self.config = config or MemoryConfig()

    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        """存储一条记忆，返回唯一标识符。"""
        ...

    @abstractmethod
    async def retrieve(
        self, query: str, limit: int = 5, **filters
    ) -> List[MemoryEntry]:
        """检索与 query 最相关的记忆。"""
        ...

    @abstractmethod
    async def forget(self, entry_id: str = None, older_than_days: int = None) -> int:
        """删除/归档记忆，返回删除数量。"""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """清空所有记忆。"""
        ...

    @abstractmethod
    def count(self) -> int:
        """返回记忆总数。"""
        ...
