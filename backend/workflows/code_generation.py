import logging
from langgraph.graph import StateGraph, END
from typing import Dict, Any

from backend.core.graph_state import GraphState
from backend.workflows.base import BaseWorkflow
from backend.agents.base_agent import BaseAgent
from backend.models.message import Message

logger = logging.getLogger(__name__)

class CodeGenerationWorkflow(BaseWorkflow):
    """
    一个用于处理直接代码生成请求的、预定义的工作流插件。
    """
    command = "/code"

    def __init__(self):
        # 这个字典将在 build_graph 时被填充
        self._agents: Dict[str, BaseAgent] = {}

    def build_graph(self, agents: Dict[str, BaseAgent]) -> StateGraph:
        """构建此工作流的 LangGraph 实例。"""
        self._agents = agents  # 保存 agents 字典，以便节点方法可以使用

        workflow = StateGraph(GraphState)

        # 定义图的节点
        workflow.add_node("execute_code_generation", self._execute_node)
        workflow.add_node("prepare_summary", self._prepare_summary_node)

        # 设置图的流程
        workflow.set_entry_point("execute_code_generation")
        workflow.add_edge("execute_code_generation", "prepare_summary")
        workflow.add_edge("prepare_summary", END)

        # 返回图，但不在此处编译
        return workflow

    async def _execute_node(self, state: GraphState) -> Dict[str, Any]:
        """
        核心执行节点，负责调用 code_generator Agent。
        (此逻辑从 Orchestrator._execute_code_generation_node 迁移而来)
        """
        logger.info("--- [CodeGeneration Workflow] 开始执行代码生成任务 ---")
        task_content = state.get("task_content", "没有提供具体的代码生成任务。")
        agent = self._agents.get("code_generator")

        if not agent:
            logger.error("[CodeGeneration Workflow] 代码生成失败：未找到 'code_generator' Agent。")
            return {"step_results": {"generation": "错误：找不到代码生成器。"}}

        result = await agent.process_message(
            [Message(content=task_content)],
            context={}
        )
        logger.info(f"[CodeGeneration Workflow] 代码生成 Agent 返回结果。")
        return {"step_results": {"generation": result.final_answer.content}}

    async def _prepare_summary_node(self, state: GraphState) -> Dict[str, Any]:
        """
        准备最终总结的节点。
        (此逻辑从 Orchestrator._prepare_summary 迁移并简化而来)
        """
        logger.info("--- [CodeGeneration Workflow] 正在生成最终总结 ---")
        results = state.get("step_results", {})
        generation_result = results.get("generation", "没有生成任何内容。")

        summary = (
            "✅ **代码生成成功**\n\n"
            "以下是生成的代码：\n\n"
            f"```python\n{generation_result}\n```"
        )
        return {"final_summary": summary}

# 导出一个该工作流的单例，以便注册中心可以发现和使用
workflow = CodeGenerationWorkflow()