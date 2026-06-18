"""
MemoryManager — 统一多层记忆框架

使用方式:
    from backend.memory import MemoryManager, MemoryConfig
    from backend.memory import ShortTermMemory, LongTermMemory, InstructionMemory

    config = MemoryConfig(short_term_window_size=10)
    manager = MemoryManager(config)

    # 对话前
    ctx = await manager.gather_context(query="...", user_id=1)

    # 对话后
    await manager.consolidate(messages=[...], response="...", user_id=1, conversation_id=42)
"""

from backend.memory.base import (
    BaseMemory, MemoryEntry, MemoryContext, MemoryConfig,
    MemoryType, MemoryLifecycleStage, GuardResult,
)
from backend.memory.manager import MemoryManager, MemoryStats
from backend.memory.short_term_memory import ShortTermMemory
from backend.memory.instruction_memory import InstructionMemory
from backend.memory.working_memory import WorkingMemory
from backend.memory.summary_memory import SummaryMemory
from backend.memory.long_term_memory import LongTermMemory
from backend.memory.write_guard import MemoryWriteGuard
from backend.memory.lifecycle import LifecycleManager, LifecycleStats
from backend.memory.session_agent import (
    SessionMemoryAgent, CompressionResult, SessionSummary,
)
from backend.memory.blackboard import Blackboard, BlackboardEntry

__all__ = [
    "BaseMemory",
    "MemoryEntry",
    "MemoryContext",
    "MemoryConfig",
    "MemoryType",
    "MemoryLifecycleStage",
    "GuardResult",
    "MemoryManager",
    "MemoryStats",
    "ShortTermMemory",
    "InstructionMemory",
    "WorkingMemory",
    "SummaryMemory",
    "LongTermMemory",
    "MemoryWriteGuard",
    "LifecycleManager",
    "LifecycleStats",
    "SessionMemoryAgent",
    "CompressionResult",
    "SessionSummary",
    "Blackboard",
    "BlackboardEntry",
]
