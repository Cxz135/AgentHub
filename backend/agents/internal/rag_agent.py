from typing import Dict, Any
from backend.utils.logger import logger
from backend.llm.llm_provider import get_llm
# 调用我们之前写的rag_retrieval工具类Skill
from backend.utils.rag_retrieval import rag_retrieval

class RAGAgent:
    """RAG工作流的核心Agent，负责知识库检索和结果总结"""
    @staticmethod
    async def retrieve(state: Dict[str, Any]) -> Dict[str, Any]:
        """从知识库检索相关内容，是工作流的第一个节点"""
        logger.info("--- [RAGAgent] 开始检索知识库 ---")
        task_content = state.get("task_content", "")
        try:
            # 调用工具类的rag_retrieval，不用自己写检索逻辑
            retrieved_docs = rag_retrieval(query=task_content, top_k=5)
            logger.info(f"✅ 检索到{len(retrieved_docs)}条相关知识库内容")
            # 把检索结果写到state里，传给下一个节点
            return {
                **state,
                "retrieved_docs": retrieved_docs,
                "retrieve_status": "success"
            }
        except Exception as e:
            logger.error(f"知识库检索失败: {e}")
            return {**state, "retrieve_status": "failed", "error": str(e)}

    @staticmethod
    async def summarize(state: Dict[str, Any]) -> Dict[str, Any]:
        """总结检索到的知识库内容，生成最终回答，工作流的最后一个节点"""
        logger.info("--- [RAGAgent] 开始总结知识库内容 ---")
        if state.get("retrieve_status") != "success":
            return {**state, "final_answer": "知识库检索失败，无法生成回答"}
        docs = state["retrieved_docs"]
        docs_text = "\n".join([f"- {doc['content']}" for doc in docs])
        # 调用全局LLM生成回答
        llm = get_llm()
        prompt = f"""基于以下知识库内容，回答用户的问题：
用户问题：{state['task_content']}
知识库内容：
{docs_text}
请用清晰的中文回答，只基于知识库内容，不要编造。"""
        response = llm.invoke(prompt)
        logger.info("✅ RAG工作流执行完成，生成最终回答")
        return {**state, "final_answer": response.content.strip()}