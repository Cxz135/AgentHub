"""
ShortTermMemory — 当前对话窗口

包装 memory_strategy.py，提供面向对象接口。
策略：none / sliding_window / summary
后端：纯内存（Python list），不持久化。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.memory.base import BaseMemory, MemoryEntry, MemoryConfig

logger = logging.getLogger("core")

# 粗略 token 估算（复用 memory_strategy.py 的常量）
_TOKEN_RATIO = 2.5


class ShortTermMemory(BaseMemory):
    """
    当前对话的短期上下文窗口。

    使用方式：
        mem = ShortTermMemory(config)
        mem.add_turn("user", "用 Python 写快速排序")
        mem.add_turn("assistant", "以下是 Python 快速排序实现...")
        msgs = await mem.get_context_messages()  # 自动裁剪后的消息列表
        ratio = mem.get_compression_ratio()       # 当前 token 使用率
        await mem.compress(session_agent)         # 触发渐进压缩
    """

    def __init__(
        self,
        config: MemoryConfig = None,
        strategy: str = None,
        window_size: int = None,
    ):
        super().__init__(config)
        self._messages: List[Dict[str, str]] = []
        self.strategy = strategy or self.config.short_term_strategy
        self.window_size = window_size or self.config.short_term_window_size
        self.max_tokens = self.config.short_term_max_tokens

        # 压缩相关
        self._session_agent: Any = None       # SessionMemoryAgent 引用
        self._compression_level: int = 0       # 当前压缩级别 (0=未压缩)
        self._original_message_count: int = 0  # 压缩前的消息数（用于统计）

    # ── 核心操作 ──

    async def add_turn(self, role: str, content: str) -> None:
        """添加一轮对话（user 或 assistant）。"""
        if content:
            self._messages.append({"role": role, "content": str(content)[:8000]})

    async def get_context_messages(self) -> List[dict]:
        """返回裁剪后的消息列表，直接注入 LLM。"""
        if not self._messages:
            return []

        from backend.core.memory_strategy import apply_memory_strategy

        cfg = self._build_strategy_config()
        return await apply_memory_strategy(
            messages=list(self._messages),
            memory_config=cfg,
            llm_invoke=None,
        )

    async def get_last_n(self, n: int) -> List[dict]:
        """返回最近 n 条原始消息（不裁剪）。"""
        return self._messages[-n:] if n > 0 else []

    def token_count(self) -> int:
        """估算当前窗口的 token 数。"""
        total = 0
        for m in self._messages:
            content = m.get("content") or ""
            total += int(len(str(content)) / _TOKEN_RATIO) + 4
        return total

    def get_compression_ratio(self) -> float:
        """返回当前 token 使用率 (0.0 ~ 1.0+)。"""
        if self.max_tokens <= 0:
            return 0.0
        return self.token_count() / self.max_tokens

    def get_compression_level(self) -> int:
        """返回当前压缩级别 (0=未压缩, 1-4=已压缩到某级)。"""
        return self._compression_level

    @property
    def raw_messages(self) -> List[Dict[str, str]]:
        """直接访问内部消息列表（供 SessionMemoryAgent 使用）。"""
        return self._messages

    def set_session_agent(self, agent: Any) -> None:
        """注入 SessionMemoryAgent。"""
        self._session_agent = agent

    async def compress(self, force: bool = False) -> Any:
        """
        触发渐进压缩。

        委托给 SessionMemoryAgent.maybe_compress()。

        Args:
            force: 强制升级到下一压缩级别

        Returns:
            CompressionResult 或 None
        """
        if not self._session_agent:
            logger.debug("[ST-MEM] 无 SessionMemoryAgent，跳过压缩")
            return None

        result = await self._session_agent.maybe_compress(
            short_term=self,
            summary=None,  # SummaryMemory 由 Manager 注入
            force=force,
        )
        if result and result.compressed:
            self._compression_level = result.level
        return result

    async def compress_if_needed(self) -> Any:
        """检查压缩阈值，必要时自动压缩。返回 CompressionResult 或 None。"""
        ratio = self.get_compression_ratio()
        if ratio < 0.5:
            return None
        return await self.compress(force=False)

    # ── 策略 ──

    def set_strategy(self, strategy: str, **params) -> None:
        """切换记忆策略。"""
        self.strategy = strategy
        if "window_size" in params:
            self.window_size = params["window_size"]

    def _build_strategy_config(self) -> Optional[dict]:
        if self.strategy == "none":
            return {"strategy": "none"}
        if self.strategy == "sliding_window":
            return {"strategy": "sliding_window", "window_size": self.window_size}
        if self.strategy == "summary":
            return {
                "strategy": "summary",
                "summary_threshold": self.max_tokens,
            }
        return {"strategy": "sliding_window", "window_size": 10}

    # ── BaseMemory 接口 ──

    async def store(self, entry: MemoryEntry) -> str:
        role = entry.metadata.get("role", "user")
        await self.add_turn(role, entry.content)
        return str(len(self._messages) - 1)

    async def retrieve(self, query: str, limit: int = 5, **filters) -> List[MemoryEntry]:
        # 短期记忆不支持语义检索，返回最近的条目
        recent = self._messages[-limit:]
        return [
            MemoryEntry(
                content=m.get("content", ""),
                memory_type="short_term",
                metadata={"role": m.get("role", "user")},
                entry_id=str(i),
            )
            for i, m in enumerate(recent)
        ]

    async def forget(self, entry_id: str = None, older_than_days: int = None) -> int:
        before = len(self._messages)
        if entry_id is not None:
            idx = int(entry_id)
            if 0 <= idx < len(self._messages):
                self._messages.pop(idx)
        else:
            self._messages = []
        return before - len(self._messages)

    async def clear(self) -> None:
        self._messages = []

    def count(self) -> int:
        return len(self._messages)
