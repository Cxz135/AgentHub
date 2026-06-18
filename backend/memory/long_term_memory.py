"""
LongTermMemory — 长期语义记忆

合并现有 MemoryExtractor + MemoryRetriever + MemoryDecayer + UserProfiler。
后端：SQL（memory_entries 表）+ Chroma（agent_memories_v2 集合）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from backend.memory.base import BaseMemory, MemoryEntry, MemoryConfig

logger = logging.getLogger("core")


class LongTermMemory(BaseMemory):
    """
    长期语义记忆。

    能力：
    - 自动从对话中提取结构化事实（fact/preference/decision/user_trait）
    - Chroma 向量索引支持语义检索
    - Ebbinghaus 衰减 + boost
    - 增量用户画像

    使用方式：
        ltm = LongTermMemory(config)
        ids = await ltm.extract_and_store(messages, user_id=1, conversation_id=42)
        results = await ltm.semantic_search("用户偏好", user_id=1)

    依赖 config 中的：
        - llm_backend: 用于事实提取
        - embed_model: 用于语义检索
        - db_session: 用于 SQL 持久化
    """

    def __init__(self, config: MemoryConfig = None):
        super().__init__(config)
        self._extractor = None
        self._retriever = None
        self._decayer = None
        self._profiler = None
        self._initialized = False

    def _ensure_init(self):
        if self._initialized:
            return
        llm = self.config.llm_backend
        embed = self.config.embed_model
        db = self.config.db_session

        if llm:
            from backend.services.memory_extractor import MemoryExtractor
            self._extractor = MemoryExtractor(llm)

        if embed:
            from backend.services.memory_retriever import MemoryRetriever
            self._retriever = MemoryRetriever(embed)

        if db:
            from backend.services.memory_decayer import MemoryDecayer
            self._decayer = MemoryDecayer(db)

            from backend.services.user_profiler import UserProfiler
            self._profiler = UserProfiler(llm, db)

        self._initialized = True
        if self._retriever or self._extractor:
            logger.info("[LTM] LongTermMemory 初始化完成")

    # ── 事实提取 ──

    async def extract_and_store(
        self,
        messages: List[dict],
        user_id: int,
        conversation_id: int = None,
        agent_id: str = "assistant",
    ) -> List[str]:
        """
        LLM 提取 + 去重 + 持久化。

        Returns:
            新增的记忆 entry_id 列表
        """
        self._ensure_init()
        if not self._extractor or not self.config.long_term_extraction_enabled:
            return []

        entry_ids = []
        try:
            entries = await self._extractor.extract(
                messages=messages,
                user_id=user_id,
                conversation_id=conversation_id,
                agent_id=agent_id,
            )
            if not entries:
                return []

            db = self.config.db_session
            saved = 0
            for entry in entries:
                if self._is_duplicate(entry, user_id):
                    continue
                if db:
                    db.add(entry)
                    db.flush()
                if entry.id and self._retriever:
                    try:
                        self._retriever.index(entry)
                    except Exception as e:
                        logger.warning(f"[LTM] Chroma index 失败: {e}")
                if entry.id:
                    entry_ids.append(f"mem_{entry.id}")
                saved += 1

            if saved > 0 and db:
                db.commit()
                logger.info(f"[LTM] 提取并保存 {saved} 条长期记忆")

            # 异步更新用户画像
            if self._profiler and saved > 0:
                saved_entries = [e for e in entries if e.id]
                if saved_entries:
                    await self._profiler.update(user_id, saved_entries)

            # 定期衰减
            self._maybe_decay(user_id)

        except Exception as e:
            logger.warning(f"[LTM] extract_and_store 失败: {e}")
            try:
                if db:
                    db.rollback()
            except Exception:
                pass

        return entry_ids

    # ── 语义检索 ──

    async def semantic_search(
        self,
        query: str,
        user_id: int,
        top_k: int = None,
        memory_type: str = None,
    ) -> List[MemoryEntry]:
        """
        向量语义检索长期记忆。

        Args:
            query: 查询文本
            user_id: 用户 ID（隔离）
            top_k: 返回数量，默认从 config 取
            memory_type: 可选类型过滤

        Returns:
            相关记忆列表（按相似度降序）
        """
        self._ensure_init()
        if not self._retriever or not self.config.long_term_semantic_enabled:
            return []

        k = top_k or self.config.long_term_retrieval_top_k
        try:
            results = self._retriever.search(
                query=query,
                user_id=user_id,
                top_k=k,
                memory_type=memory_type,
            )
            return [
                MemoryEntry(
                    content=r.get("content", ""),
                    memory_type=r.get("memory_type", "fact"),
                    importance=r.get("importance", 0.5),
                    metadata={"score": r.get("score", 0), "id": r.get("id")},
                    entry_id=f"mem_{r.get('id')}" if r.get("id") else None,
                )
                for r in results
            ]
        except Exception as e:
            logger.warning(f"[LTM] semantic_search 失败: {e}")
            return []

    # ── 用户画像 ──

    async def get_user_profile(self, user_id: int) -> dict:
        """获取用户画像。"""
        self._ensure_init()
        if not self._profiler:
            return {"summary": "", "traits": [], "preferences": {}}
        return self._profiler.get_full_profile(user_id)

    async def get_user_profile_text(self, user_id: int) -> str:
        """获取用户画像的人类可读摘要文本。"""
        self._ensure_init()
        if not self._profiler:
            return ""
        return self._profiler.get_summary(user_id)

    # ── 衰减 ──

    async def apply_decay(self, user_id: int) -> int:
        """执行衰减，返回归档数量。"""
        self._ensure_init()
        if not self._decayer or not self.config.long_term_decay_enabled:
            return 0
        return self._decayer.decay(user_id)

    async def boost(self, entry_id: str) -> None:
        """手动提升记忆。"""
        self._ensure_init()
        if not self._decayer:
            return
        mem_id = int(entry_id.replace("mem_", ""))
        self._decayer.boost(mem_id)

    # ── BaseMemory 接口 ──

    async def store(self, entry: MemoryEntry) -> str:
        msg = [{"role": entry.metadata.get("role", "user"), "content": entry.content}]
        ids = await self.extract_and_store(
            msg, entry.metadata.get("user_id", 0),
            agent_id=entry.metadata.get("agent_id", "agent"),
        )
        return ids[0] if ids else ""

    async def retrieve(self, query: str, limit: int = 5, **filters) -> List[MemoryEntry]:
        return await self.semantic_search(
            query=query,
            user_id=filters.get("user_id", 0),
            top_k=limit,
            memory_type=filters.get("memory_type"),
        )

    async def forget(self, entry_id: str = None, older_than_days: int = None) -> int:
        self._ensure_init()
        db = self.config.db_session
        if not db:
            return 0
        from backend.models.memory import MemoryEntry as ME
        if entry_id:
            mem_id = int(entry_id.replace("mem_", ""))
            entry = db.query(ME).filter(ME.id == mem_id).first()
            if entry:
                entry.is_active = False
                db.commit()
                return 1
        if older_than_days:
            return await self.apply_decay(0)
        return 0

    async def clear(self) -> None:
        self._ensure_init()
        db = self.config.db_session
        if db:
            from backend.models.memory import MemoryEntry as ME
            db.query(ME).delete()
            db.commit()

    def count(self) -> int:
        self._ensure_init()
        if self._retriever:
            return self._retriever.count()
        return 0

    # ── 内部方法 ──

    def _is_duplicate(self, entry, user_id: int) -> bool:
        if not self._retriever or self._retriever.count(user_id) == 0:
            return False
        try:
            existing = self._retriever.search(
                query=entry.content,
                user_id=user_id,
                top_k=1,
                min_similarity=0.92,
            )
            return len(existing) > 0
        except Exception:
            return False

    def _maybe_decay(self, user_id: int):
        """每 10 条新记忆触发一次衰减。"""
        if not self._decayer or not self.config.long_term_decay_enabled:
            return
        try:
            total = self._retriever.count(user_id) if self._retriever else 0
            if total > 0 and total % 10 == 0:
                archived = self._decayer.decay(user_id)
                if archived > 0:
                    logger.info(f"[LTM] 衰减归档 {archived} 条旧记忆")
        except Exception:
            pass
