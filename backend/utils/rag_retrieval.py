from typing import List, Dict, Any
from backend.rag.vector_store import VectorStoreService

# 全局单例，避免重复初始化向量库
_vector_store = None

def get_vector_store():
    global _vector_store
    if not _vector_store:
        _vector_store = VectorStoreService()
    return _vector_store

def rag_retrieval(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    RAG知识库检索工具类，完全复用你已有的vector_store
    参数：
        query: 用户的问题，要检索的内容
        top_k: 返回的最相关文档数量，默认5
    返回：
        检索到的文档列表，每个元素包含content、source、score三个字段
    """
    try:
        vs = get_vector_store()
        # 调用向量库的原生检索接口，和你现有代码完全兼容
        docs = vs.vector_store.similarity_search_with_score(query, k=top_k)
        results = []
        for doc, score in docs:
            results.append({
                "content": doc.page_content,
                "source": doc.metadata.get("source", "unknown"),
                "score": float(score)
            })
        from backend.utils.logger import logger
        logger.info(f"✅ RAG检索完成，query: {query[:30]}..., 找到{len(results)}条结果")
        # 检测向量库是否为空（全局文档数为0），给 agent 明确提示
        try:
            total_docs = vs.vector_store._collection.count()
            if total_docs == 0 and not results:
                logger.warning(f"[RAG-EMPTY] 知识库中没有任何文档，返回空结果")
        except Exception:
            pass
        return results
    except Exception as e:
        from backend.utils.logger import logger
        logger.error(f"RAG检索失败: {e}")
        return []