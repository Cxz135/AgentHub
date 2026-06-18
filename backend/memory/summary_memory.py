"""
SummaryMemory — 分层对话摘要

Level:
- "turn"          → 单轮 exchange（2-4 条消息）
- "segment"       → 5-10 轮段落
- "conversation"  → 整场对话

后端：内存 list + 可选 SQL 持久化。
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from backend.memory.base import BaseMemory, MemoryEntry, MemoryConfig

logger = logging.getLogger("core")


class SummaryMemory(BaseMemory):
    """
    分层对话摘要记忆 + 压缩摘要存储。

    原有层级：
        turn → segment → conversation

    新增压缩摘要（来自 SessionMemoryAgent）：
        L1 工具缓存 → L2 微压缩 → L3 段落摘要 → L4 全局摘要

    使用方式：
        sm = SummaryMemory(config)
        sid = await sm.add_turn_summary(messages, conv_id=42)
        await sm.build_segment_summary(conv_id=42, turn_ids=[...])
        ctx = await sm.get_recent_summaries(conv_id=42, level="segment")
        sm.store_compression(compression_result)   # 存储渐进压缩结果
        ctx_text = sm.get_compression_context()    # 获取压缩上下文文本
    """

    def __init__(self, config: MemoryConfig = None):
        super().__init__(config)
        self._turns: List[Dict] = []       # [{turn_id, summary, conv_id, ts}]
        self._segments: List[Dict] = []    # [{segment_id, summary, turn_ids, conv_id, ts}]
        self._conversations: List[Dict] = []  # [{conv_id, summary, ts}]

        # 压缩摘要存储（来自 SessionMemoryAgent）
        self._compression_summaries: List[Dict] = []  # [{level, summary, structured, ts}]
        self._global_summary: str = ""                # L4 全量压缩的全局摘要

    # ── 摘要构建 ──

    async def add_turn_summary(
        self, messages: List[dict], conversation_id: int = 0
    ) -> str:
        """
        为单轮对话生成摘要。

        Returns:
            turn_id
        """
        if not messages:
            return ""

        turn_id = f"turn_{conversation_id}_{len(self._turns)}_{int(time.time())}"
        # 简单摘要：拼接前 200 字
        text = " | ".join(
            f"{m.get('role', '?')}: {str(m.get('content', ''))[:100]}"
            for m in messages[-4:]
        )
        self._turns.append({
            "turn_id": turn_id,
            "summary": text[:500],
            "conversation_id": conversation_id,
            "ts": time.time(),
        })
        logger.debug(f"[SUMMARY-MEM] 添加轮次摘要: {turn_id}")
        return turn_id

    async def build_segment_summary(
        self, conversation_id: int, turn_ids: List[str] = None
    ) -> str:
        """
        合并多个轮次摘要为段落摘要。

        如果有 LLM backend，使用 LLM 生成更高质量的摘要。
        """
        if turn_ids:
            turns = [t for t in self._turns if t["turn_id"] in turn_ids]
        else:
            turns = [t for t in self._turns if t["conversation_id"] == conversation_id]
            turns = turns[-10:]  # 最近 10 轮

        if not turns:
            return ""

        segment_id = f"seg_{conversation_id}_{len(self._segments)}_{int(time.time())}"
        merged = " | ".join(t["summary"] for t in turns)

        # 尝试用 LLM 生成更好的摘要
        summary_text = merged[:800]
        if self.config.llm_backend:
            try:
                prompt = f"请用不超过 150 字总结以下对话段落的关键信息：\n{merged[:2000]}"
                resp = await self.config.llm_backend.chat([
                    {"role": "user", "content": prompt}
                ])
                if isinstance(resp, str) and len(resp.strip()) > 10:
                    summary_text = resp.strip()[:500]
            except Exception as e:
                logger.warning(f"[SUMMARY-MEM] LLM 摘要失败: {e}")

        self._segments.append({
            "segment_id": segment_id,
            "summary": summary_text,
            "turn_ids": [t["turn_id"] for t in turns],
            "conversation_id": conversation_id,
            "ts": time.time(),
        })
        logger.info(f"[SUMMARY-MEM] 段落摘要: {segment_id}, {len(turns)} 轮 → {len(summary_text)} 字")
        return segment_id

    async def build_conversation_summary(self, conversation_id: int) -> str:
        """为整场对话生成摘要。"""
        segments = [s for s in self._segments if s["conversation_id"] == conversation_id]
        if not segments:
            return ""

        conv_id = f"conv_{conversation_id}"
        # 合并所有段落摘要
        merged = " | ".join(s["summary"] for s in segments)
        summary_text = merged[:1000]

        if self.config.llm_backend:
            try:
                prompt = f"请用不超过 300 字总结以下对话的整体内容：\n{merged[:3000]}"
                resp = await self.config.llm_backend.chat([
                    {"role": "user", "content": prompt}
                ])
                if isinstance(resp, str) and len(resp.strip()) > 10:
                    summary_text = resp.strip()[:800]
            except Exception as e:
                logger.warning(f"[SUMMARY-MEM] LLM 对话摘要失败: {e}")

        self._conversations.append({
            "conv_id": conv_id,
            "summary": summary_text,
            "ts": time.time(),
        })
        return conv_id

    # ── 检索 ──

    async def get_recent_summaries(
        self, conversation_id: int = None, level: str = "segment", limit: int = 5
    ) -> List[MemoryEntry]:
        """获取最近的摘要。"""
        if level == "turn":
            pool = self._turns
        elif level == "segment":
            pool = self._segments
        else:
            pool = self._conversations

        if conversation_id is not None:
            pool = [s for s in pool if s.get("conversation_id") == conversation_id]

        recent = pool[-limit:]
        return [
            MemoryEntry(
                content=s.get("summary", ""),
                memory_type="summary",
                importance=0.6,
                entry_id=s.get("turn_id") or s.get("segment_id") or s.get("conv_id", ""),
            )
            for s in recent
        ]

    async def get_context_text(self, conversation_id: int = None) -> str:
        """获取最近的摘要文本（用于注入 prompt）。"""
        entries = await self.get_recent_summaries(conversation_id, level="segment", limit=3)
        if not entries:
            return ""
        return "## 历史对话摘要：\n" + "\n".join(
            f"- {e.content[:300]}" for e in entries
        )

    # ── 压缩摘要存储（SessionMemoryAgent 集成） ──

    def store_compression(self, result: Any) -> None:
        """
        存储一次压缩操作的结果。

        Args:
            result: CompressionResult 对象（来自 SessionMemoryAgent）
        """
        if not result or not result.compressed:
            return

        entry = {
            "level": result.level,
            "summary": result.summary or "",
            "structured": result.structured or {},
            "messages_before": result.messages_before,
            "messages_after": result.messages_after,
            "tokens_before": result.tokens_before,
            "tokens_after": result.tokens_after,
            "ts": time.time(),
        }
        self._compression_summaries.append(entry)

        # L4 全量压缩：更新全局摘要
        if result.level == 4 and result.summary:
            self._global_summary = result.summary

        logger.debug(
            f"[SUMMARY-MEM] 存储 L{result.level} 压缩摘要: "
            f"{result.tokens_before}→{result.tokens_after} tokens"
        )

    def get_compression_summary(self, level: int = None) -> List[Dict]:
        """获取指定级别的压缩摘要。level=None 返回全部。"""
        if level is None:
            return list(self._compression_summaries)
        return [s for s in self._compression_summaries if s["level"] == level]

    def get_latest_compression_level(self) -> int:
        """返回最近一次压缩的级别（0=从未压缩）。"""
        if not self._compression_summaries:
            return 0
        return self._compression_summaries[-1]["level"]

    def get_compression_context(self) -> str:
        """
        获取所有压缩摘要的上下文文本（注入 LLM system prompt）。

        优先级顺序：
        1. L4 全局摘要（如果有）
        2. 最近的 L3 段落摘要（最多 3 段）
        3. 关键决策和错误
        """
        parts = []

        # L4 全局摘要
        if self._global_summary:
            parts.append(f"## 会话全局摘要\n{self._global_summary[:800]}")

        # L3 段落摘要
        l3_summaries = self.get_compression_summary(level=3)
        if l3_summaries:
            recent = l3_summaries[-3:]
            parts.append("## 历史段落摘要\n" + "\n".join(
                f"- {s['summary'][:300]}" for s in recent
            ))

        # 结构化信息
        for s in reversed(self._compression_summaries):
            structured = s.get("structured", {})
            if structured.get("key_decisions"):
                parts.append("## 关键决策\n" + "\n".join(
                    f"- {d}" for d in structured["key_decisions"][-5:]
                ))
                break  # 只取最近一份含 decisions 的

        for s in reversed(self._compression_summaries):
            structured = s.get("structured", {})
            if structured.get("errors_encountered"):
                parts.append("## 遇到的错误\n" + "\n".join(
                    f"- {e if isinstance(e, str) else e.get('error', str(e))}"
                    for e in structured["errors_encountered"][-3:]
                ))
                break

        return "\n\n".join(parts) if parts else ""

    def get_compression_stats(self) -> Dict[str, Any]:
        """获取压缩统计。"""
        if not self._compression_summaries:
            return {"total_compressions": 0, "total_savings": 0, "levels": {}}

        total_savings = sum(
            s["tokens_before"] - s["tokens_after"]
            for s in self._compression_summaries
        )
        by_level = {}
        for s in self._compression_summaries:
            lv = s["level"]
            if lv not in by_level:
                by_level[lv] = 0
            by_level[lv] += 1

        return {
            "total_compressions": len(self._compression_summaries),
            "total_savings": total_savings,
            "levels": by_level,
            "latest_level": self.get_latest_compression_level(),
            "has_global_summary": bool(self._global_summary),
        }

    # ── BaseMemory 接口 ──

    async def store(self, entry: MemoryEntry) -> str:
        conv_id = entry.metadata.get("conversation_id", 0)
        return await self.add_turn_summary(
            [{"role": entry.metadata.get("role", "user"), "content": entry.content}],
            conversation_id=conv_id,
        )

    async def retrieve(self, query: str = "", limit: int = 5, **filters) -> List[MemoryEntry]:
        conv_id = filters.get("conversation_id")
        level = filters.get("level", "segment")
        return await self.get_recent_summaries(conv_id, level, limit)

    async def forget(self, entry_id: str = None, older_than_days: int = None) -> int:
        before = len(self._turns) + len(self._segments) + len(self._conversations)
        if older_than_days:
            cutoff = time.time() - older_than_days * 86400
            self._turns = [t for t in self._turns if t["ts"] > cutoff]
            self._segments = [s for s in self._segments if s["ts"] > cutoff]
            self._conversations = [c for c in self._conversations if c["ts"] > cutoff]
        elif entry_id:
            self._turns = [t for t in self._turns if t["turn_id"] != entry_id]
            self._segments = [s for s in self._segments if s["segment_id"] != entry_id]
        else:
            self._turns.clear()
            self._segments.clear()
            self._conversations.clear()
        after = len(self._turns) + len(self._segments) + len(self._conversations)
        return before - after

    async def clear(self) -> None:
        self._turns.clear()
        self._segments.clear()
        self._conversations.clear()

    def count(self) -> int:
        return len(self._turns) + len(self._segments) + len(self._conversations)
