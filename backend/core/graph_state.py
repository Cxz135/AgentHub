from typing import Dict, Any, TypedDict, List
from langchain_core.messages import BaseMessage


class GraphState(TypedDict):
    """
    表示 LangGraph 工作流状态的 TypedDict。
    它在图的节点之间传递，并由每个节点更新。
    """
    # 对于简单的、非计划驱动的工作流，直接存储任务内容
    task_content: str

    # Planner 生成的原始计划
    plan_data: Dict[str, Any]


    # 按步骤编号存储的执行结果
    # 例如: {1: "代码生成结果...", 2: "代码审查结果..."}
    step_results: Dict[int, Any]

    # 最终要返回给用户的总结报告
    final_summary: str

    # 当前的会话 ID
    conversation_id: str

    # 下一个要执行的步骤编号列表
    next_steps_to_execute: List[int]

    # 每个 Agent 执行后产生的消息列表，作为短期记忆
    messages: List[BaseMessage]

    # 用于存放 AI 对话历史的压缩摘要，供后续任务参考
    memory_summary: str