from typing import Dict, Any
from backend.utils.logger import logger
from backend.llm.llm_provider import get_llm
from backend.utils.rag_retrieval import rag_retrieval
from backend.config.prompts import get_prompt_loader

class RAGAgent:
    """RAG工作流的核心Agent，负责知识库检索和结果总结"""
    @staticmethod
    async def retrieve(state: Dict[str, Any]) -> Dict[str, Any]:
        """从知识库检索相关内容，是工作流的第一个节点"""
        logger.info("--- [RAGAgent] 开始检索知识库 ---")
        task_content = state.get("task_content", "")
        try:
            retrieved_docs = rag_retrieval(query=task_content, top_k=5)
            logger.info(f"✅ 检索到{len(retrieved_docs)}条相关知识库内容")
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
        llm = get_llm()
        prompt_loader = get_prompt_loader()
        prompt = prompt_loader.get('agent', 'rag_prompt',
            task_content=state['task_content'],
            docs_text=docs_text
        )
        response = llm.invoke(prompt)
        logger.info("✅ RAG工作流执行完成，生成最终回答")
        return {**state, "final_answer": response.content.strip()}