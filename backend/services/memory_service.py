"""
多层记忆框架 — 中央编排器 [DEPRECATED]

⚠️ 此模块已被 MemoryManager (backend/memory/manager.py) 取代。
   新代码请直接使用:
       from backend.memory import MemoryManager, MemoryConfig
       manager = MemoryManager(config)

   迁移指南:
       MemoryService.augment_context(...)   → MemoryManager.gather_context(...)
       MemoryService.on_conversation_turn()  → MemoryManager.consolidate(...)
       MemoryService.list_memories(...)      → MemoryManager.list_entries(...)
       MemoryService.get_memory(...)         → MemoryManager.get_entry(...)
       MemoryService.update_memory(...)      → MemoryManager.update_entry(...)
       MemoryService.delete_memory(...)      → MemoryManager.delete_entry(...)
       MemoryService.boost_memory(...)       → MemoryManager.boost_entry(...)
       MemoryService.get_stats(...)          → MemoryManager.get_stats(...)

在 Orchestrator 路由管线中的注入点：
1. 前置：augment_context() → 语义检索相关记忆，注入 system prompt
2. 后置：on_conversation_turn() → 提取事实 → 持久化 → 更新画像 → 衰减

特性开关：MEMORY_ENABLED 环境变量。未设置时 self.memory_service = None。
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.services.memory_extractor import MemoryExtractor
from backend.services.memory_retriever import MemoryRetriever
from backend.services.memory_decayer import MemoryDecayer
from backend.services.user_profiler import UserProfiler

logger = logging.getLogger("core")


class MemoryService:
    """
    多层记忆中央编排器。

    使用方式：
      svc = MemoryService(db_session, llm_backend, embed_model)
      # 前置：增强上下文
      ctx = await svc.augment_context(user_id, query, conversation_id)
      # 后置：提取并持久化新记忆
      asyncio.create_task(svc.on_conversation_turn(user_id, conv_id, messages, agent_id))
    """

    def __init__(
        self,
        db_session: Session,
        llm_backend: Any,
        embed_model: Any,
    ):
        warnings.warn(
            "MemoryService is deprecated. Use MemoryManager from backend.memory instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.db = db_session
        self.llm_backend = llm_backend
        self.embed_model = embed_model

        # 子服务（延迟初始化，避免在 __init__ 中触发 Chroma 连接）
        self._extractor: Optional[MemoryExtractor] = None
        self._retriever: Optional[MemoryRetriever] = None
        self._decayer: Optional[MemoryDecayer] = None
        self._profiler: Optional[UserProfiler] = None

        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        self._extractor = MemoryExtractor(self.llm_backend)
        self._retriever = MemoryRetriever(self.embed_model)
        self._decayer = MemoryDecayer(self.db)
        self._profiler = UserProfiler(self.llm_backend, self.db)
        self._initialized = True
        logger.info("[MEMORY-SVC] 多层记忆服务初始化完成")

    # ── 前置：语义检索增强上下文 ──

    async def augment_context(
        self,
        user_id: int,
        current_query: str,
        conversation_id: Optional[int] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """
        在 LLM 调用前，检索相关记忆。

        Returns:
            {
                "memories": [{"type": "fact", "content": "...", "importance": 0.8}, ...],
                "profile_summary": "用户是高级Python开发者，偏好React...",
            }
        """
        self._ensure_initialized()
        result: Dict[str, Any] = {"memories": [], "profile_summary": ""}

        try:
            # 1. 语义检索
            memories = self._retriever.search(
                query=current_query,
                user_id=user_id,
                top_k=limit,
            )
            result["memories"] = [
                {
                    "type": m.get("memory_type", "fact"),
                    "content": m.get("content", ""),
                    "importance": m.get("importance", 0.5),
                    "id": m.get("id"),
                }
                for m in memories
            ]
            # 更新访问计数
            for m in memories:
                if m.get("id"):
                    self._decayer.boost(m["id"])

            # 2. 用户画像
            profile = self._profiler.get_summary(user_id)
            result["profile_summary"] = profile or ""

            logger.info(
                f"[MEMORY-SVC] augment_context: {len(memories)} 条相关记忆, "
                f"profile_len={len(profile)}"
            )
        except Exception as e:
            logger.warning(f"[MEMORY-SVC] augment_context 失败（非致命）: {e}")

        return result

    # ── 后置：提取 + 持久化 + 衰减 ──

    async def on_conversation_turn(
        self,
        user_id: int,
        conversation_id: int,
        messages: List[Dict[str, str]],
        agent_id: str = "assistant",
    ) -> int:
        """
        对话轮次完成后调用（fire-and-forget）。

        1. LLM 提取事实 → MemoryEntry 列表
        2. 去重 + 持久化到 SQL 和 Chroma
        3. 增量更新用户画像
        4. 衰减旧记忆

        Returns:
            新提取的记忆数量
        """
        self._ensure_initialized()

        if not messages:
            return 0

        # 标准化消息格式（兼容 dict 和 Message 对象）
        normalized = []
        for m in messages[-6:]:  # 只分析最近 6 条
            if isinstance(m, dict):
                role = m.get("role") or m.get("agent_id", "unknown")
                content = m.get("content", "")
            elif hasattr(m, "role") and hasattr(m, "content"):
                role = m.role
                content = m.content
            elif hasattr(m, "agent_id") and hasattr(m, "content"):
                role = m.agent_id
                content = m.content
            else:
                role = "unknown"
                content = str(m)[:300]
            if content:
                normalized.append({"role": role, "content": str(content)[:500]})

        if not normalized:
            return 0

        try:
            # 1. 提取
            extracted = await self._extractor.extract(
                messages=normalized,
                user_id=user_id,
                conversation_id=conversation_id,
                agent_id=agent_id,
            )
            if not extracted:
                return 0

            # 2. 去重 + 持久化
            saved_count = 0
            for entry in extracted:
                if self._is_duplicate(entry, user_id):
                    continue
                self.db.add(entry)
                self.db.flush()
                if entry.id:
                    try:
                        self._retriever.index(entry)
                    except Exception as e:
                        logger.warning(f"[MEMORY-SVC] Chroma index 失败: {e}")
                saved_count += 1

            if saved_count > 0:
                self.db.commit()
                logger.info(f"[MEMORY-SVC] 持久化 {saved_count} 条新记忆")
            else:
                self.db.rollback()
                return 0

            # 3. 更新用户画像
            saved_entries = [e for e in extracted if e.id]
            if saved_entries:
                await self._profiler.update(user_id, saved_entries)

            # 4. 衰减旧记忆（每 10 条新记忆触发一次）
            try:
                from backend.models.memory import MemoryEntry as ME
                total = self.db.query(ME).filter(
                    ME.user_id == user_id,
                    ME.is_active == True,
                ).count()
                if total > 0 and total % 10 == 0:
                    archived = self._decayer.decay(user_id)
                    if archived > 0:
                        logger.info(f"[MEMORY-SVC] 衰减归档了 {archived} 条旧记忆")
            except Exception as e:
                logger.debug(f"[MEMORY-SVC] 衰减检查跳过: {e}")

            return saved_count
        except Exception as e:
            logger.warning(f"[MEMORY-SVC] on_conversation_turn 失败（非致命）: {e}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return 0

    def _is_duplicate(self, entry, user_id: int) -> bool:
        """检查是否与已有记忆重复（基于向量相似度）。"""
        try:
            # 快速检查：如果用户尚无任何记忆，直接跳过检索
            if self._retriever.count(user_id) == 0:
                return False
            existing = self._retriever.search(
                query=entry.content,
                user_id=user_id,
                top_k=1,
                min_similarity=0.92,
            )
            return len(existing) > 0
        except Exception:
            return False

    # ── 用户面 API ──

    def list_memories(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        memory_type: Optional[str] = None,
        sort_by: str = "importance",
    ) -> Dict[str, Any]:
        """分页列出用户的所有记忆。"""
        self._ensure_initialized()
        from backend.models.memory import MemoryEntry as ME

        query = self.db.query(ME).filter(
            ME.user_id == user_id,
            ME.is_active == True,
        )
        if memory_type:
            query = query.filter(ME.memory_type == memory_type)

        total = query.count()

        if sort_by == "importance":
            query = query.order_by(ME.importance.desc())
        elif sort_by == "recent":
            query = query.order_by(ME.created_at.desc())
        elif sort_by == "access_count":
            query = query.order_by(ME.access_count.desc())

        entries = query.offset((page - 1) * page_size).limit(page_size).all()

        return {
            "entries": [
                {
                    "id": e.id,
                    "memory_type": e.memory_type,
                    "content": e.content,
                    "importance": e.importance,
                    "confidence": e.confidence,
                    "access_count": e.access_count,
                    "decay_factor": e.decay_factor,
                    "effective_score": e.effective_score,
                    "conversation_id": e.conversation_id,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in entries
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_memory(self, memory_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        from backend.models.memory import MemoryEntry as ME

        entry = self.db.query(ME).filter(
            ME.id == memory_id,
            ME.user_id == user_id,
        ).first()
        if not entry:
            return None
        return {
            "id": entry.id,
            "memory_type": entry.memory_type,
            "content": entry.content,
            "importance": entry.importance,
            "confidence": entry.confidence,
            "decay_factor": entry.decay_factor,
            "effective_score": entry.effective_score,
            "meta_data": entry.meta_data,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }

    def update_memory(self, memory_id: int, user_id: int, updates: dict) -> bool:
        from backend.models.memory import MemoryEntry as ME

        entry = self.db.query(ME).filter(
            ME.id == memory_id,
            ME.user_id == user_id,
        ).first()
        if not entry:
            return False

        if "content" in updates:
            entry.content = updates["content"]
        if "importance" in updates:
            entry.importance = max(0.0, min(1.0, float(updates["importance"])))
        if "memory_type" in updates:
            entry.memory_type = updates["memory_type"]

        self.db.commit()
        return True

    def delete_memory(self, memory_id: int, user_id: int) -> bool:
        """软删除记忆。"""
        from backend.models.memory import MemoryEntry as ME

        entry = self.db.query(ME).filter(
            ME.id == memory_id,
            ME.user_id == user_id,
        ).first()
        if not entry:
            return False
        entry.is_active = False
        self.db.commit()
        # 从 Chroma 中移除
        try:
            self._retriever.delete_by_memory_id(memory_id)
        except Exception:
            pass
        return True

    def boost_memory(self, memory_id: int, user_id: int) -> bool:
        """手动提升记忆：重置衰减 + 增加访问计数。"""
        from backend.models.memory import MemoryEntry as ME

        entry = self.db.query(ME).filter(
            ME.id == memory_id,
            ME.user_id == user_id,
        ).first()
        if not entry:
            return False
        self._decayer.boost(memory_id)
        self.db.commit()
        return True

    def get_profile(self, user_id: int) -> Dict[str, Any]:
        self._ensure_initialized()
        return self._profiler.get_full_profile(user_id)

    def get_stats(self, user_id: int) -> Dict[str, Any]:
        from backend.models.memory import MemoryEntry as ME

        entries = self.db.query(ME).filter(
            ME.user_id == user_id,
            ME.is_active == True,
        ).all()

        by_type = {}
        for e in entries:
            by_type[e.memory_type] = by_type.get(e.memory_type, 0) + 1

        avg_importance = (
            sum(e.importance for e in entries) / len(entries) if entries else 0
        )

        return {
            "total": len(entries),
            "by_type": by_type,
            "avg_importance": round(avg_importance, 3),
            "avg_confidence": round(
                sum(e.confidence for e in entries) / len(entries), 3
            ) if entries else 0,
        }


def create_memory_service(
    db_session: Session,
    llm_backend: Any,
    embed_model: Any = None,
) -> Optional[MemoryService]:
    """
    工厂函数：根据特性开关创建 MemoryService。

    环境变量 MEMORY_ENABLED=true 时启用。
    """
    import os
    enabled = os.getenv("MEMORY_ENABLED", "").lower() in ("1", "true", "yes")
    if not enabled:
        logger.info("[MEMORY-SVC] MEMORY_ENABLED 未设置，多层记忆服务未启用")
        return None

    if embed_model is None:
        try:
            from backend.rag.vector_store import EmbeddingsFactory
            embed_model = EmbeddingsFactory().generator()
        except Exception as e:
            logger.warning(f"[MEMORY-SVC] 无法创建嵌入模型: {e}")
            return None

    logger.info("[MEMORY-SVC] 正在创建多层记忆服务...")
    return MemoryService(
        db_session=db_session,
        llm_backend=llm_backend,
        embed_model=embed_model,
    )
