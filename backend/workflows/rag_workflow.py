from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, HumanMessage
from backend.core.graph_state import GraphState
from backend.agents.internal.rag_agent import RAGAgent  # 你原有的RAG工具Agent

class RAGWorkflow:
    """固定的知识库问答工作流：/rag 命令触发，完全符合langgraph的写法"""
    @staticmethod
    def build() -> StateGraph:
        workflow = StateGraph(GraphState)
        # 节点1：检索知识库
        workflow.add_node("retrieve_knowledge", RAGAgent.retrieve)
        # 节点2：总结检索到的内容
        workflow.add_node("summarize_content", RAGAgent.summarize)
        # 边：检索完自动进入总结
        workflow.add_edge("retrieve_knowledge", "summarize_content")
        # 总结完结束
        workflow.add_edge("summarize_content", END)
        # 入口节点
        workflow.set_entry_point("retrieve_knowledge")
        return workflow.compile()