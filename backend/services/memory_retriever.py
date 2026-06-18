"""
记忆检索器 — Chroma 向量存储的语义搜索封装。

集合：
- agent_memories: 语义记忆条目
- episodic_memories: 对话摘要（后续阶段实现）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core")


class _ChromaEmbeddingAdapter:
    """
    将 LangChain 嵌入模型适配为 ChromaDB 兼容的 EmbeddingFunction 接口。

    不继承 chromadb.EmbeddingFunction（避免版本兼容问题），
    仅实现 ChromaDB 运行时所需的 __call__ 接口。
    """

    def __init__(self, lc_embed_model: Any):
        self._model = lc_embed_model

    def __call__(self, input: List[str]) -> List[List[float]]:
        # ChromaDB v1.5.x 将 input 作为 List[str] 传入
        if not input:
            return []
        return self._model.embed_documents(input)


class MemoryRetriever:
    """
    封装 Chroma 集合用于记忆的语义检索。

    复用项目中已有的 LangChain 嵌入模型（DashScopeEmbeddings）。
    """

    def __init__(self, embed_model: Any):
        # 适配 LangChain embeddings → ChromaDB EmbeddingFunction
        self._embed_fn = _ChromaEmbeddingAdapter(embed_model)
        self._memory_collection = None
        self._episodic_collection = None

    def _get_memory_collection(self):
        if self._memory_collection is None:
            import chromadb
            from chromadb.config import Settings

            client = chromadb.PersistentClient(
                path="./chroma_db",
                settings=Settings(anonymized_telemetry=False),
            )
            # 不传 embedding_function：手动计算向量后传入，避免 ChromaDB 序列化问题
            self._memory_collection = client.get_or_create_collection(
                name="agent_memories_v2",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("[MEMORY-RETRIEVE] Chroma 集合 'agent_memories_v2' 已就绪")
        return self._memory_collection

    def _get_episodic_collection(self):
        if self._episodic_collection is None:
            import chromadb
            from chromadb.config import Settings

            client = chromadb.PersistentClient(
                path="./chroma_db",
                settings=Settings(anonymized_telemetry=False),
            )
            self._episodic_collection = client.get_or_create_collection(
                name="episodic_memories_v2",
                metadata={"hnsw:space": "cosine"},
            )
        return self._episodic_collection

    def index(self, memory_entry) -> None:
        """
        将 MemoryEntry 嵌入并存入 Chroma。
        手动计算 embedding，不依赖 Chroma 的 embedding_function。
        """
        if not memory_entry.id:
            logger.warning("[MEMORY-RETRIEVE] index 失败: memory_entry 缺少 id")
            return

        try:
            # 手动计算向量
            embeddings = self._embed_fn([memory_entry.content])
            collection = self._get_memory_collection()
            collection.add(
                ids=[f"mem_{memory_entry.id}"],
                documents=[memory_entry.content],
                embeddings=embeddings,
                metadatas=[{
                    "user_id": str(memory_entry.user_id),
                    "memory_type": memory_entry.memory_type,
                    "importance": memory_entry.importance,
                    "memory_entry_id": memory_entry.id,
                    "conversation_id": memory_entry.conversation_id or 0,
                }],
            )
        except Exception as e:
            logger.warning(f"[MEMORY-RETRIEVE] index 失败: {e}")

    def search(
        self,
        query: str,
        user_id: int,
        top_k: int = 5,
        memory_type: Optional[str] = None,
        min_similarity: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        语义检索记忆。

        Args:
            query: 搜索查询（通常是用户的当前消息）
            user_id: 用户 ID，用于隔离
            top_k: 返回的最大结果数
            memory_type: 可选类型过滤
            min_similarity: 最低相似度阈值（0-1）

        Returns:
            [{"id": 1, "content": "...", "memory_type": "fact", "importance": 0.8, "score": 0.95}, ...]
        """
        try:
            collection = self._get_memory_collection()

            # 手动计算查询向量
            query_embedding = self._embed_fn([query])

            # 构建过滤条件
            where = {"user_id": str(user_id)}
            if memory_type:
                where["memory_type"] = memory_type

            results = collection.query(
                query_embeddings=query_embedding,
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )

            if not results or not results.get("documents") or not results["documents"][0]:
                return []

            memories = []
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            distances = results["distances"][0]

            for doc, meta, dist in zip(docs, metas, distances):
                # Chroma 返回距离（越小越相似），转换为相似度分数
                similarity = 1.0 / (1.0 + dist) if dist is not None else 1.0
                if min_similarity > 0 and similarity < min_similarity:
                    continue
                memories.append({
                    "id": meta.get("memory_entry_id"),
                    "content": doc,
                    "memory_type": meta.get("memory_type", "fact"),
                    "importance": meta.get("importance", 0.5),
                    "score": round(similarity, 4),
                })

            logger.debug(
                f"[MEMORY-RETRIEVE] search: query='{query[:30]}...', "
                f"user_id={user_id}, results={len(memories)}"
            )
            return memories
        except Exception as e:
            logger.warning(f"[MEMORY-RETRIEVE] search 失败: {e}")
            return []

    def delete_by_memory_id(self, memory_id: int) -> None:
        """从 Chroma 中删除指定记忆的向量。"""
        try:
            collection = self._get_memory_collection()
            collection.delete(ids=[f"mem_{memory_id}"])
        except Exception as e:
            logger.warning(f"[MEMORY-RETRIEVE] delete 失败: {e}")

    def count(self, user_id: Optional[int] = None) -> int:
        """统计集合中的记忆数量。"""
        try:
            collection = self._get_memory_collection()
            if user_id is not None:
                results = collection.get(where={"user_id": str(user_id)})
                return len(results["ids"]) if results else 0
            return collection.count()
        except Exception:
            return 0
