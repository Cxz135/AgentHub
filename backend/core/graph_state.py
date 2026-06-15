from typing import Dict, Any, TypedDict, List
from backend.models.task_spec import TaskSpec
from backend.models.task_spec import TaskResult
from langchain_core.messages import BaseMessage

# 注册自定义类型到 LangGraph msgpack 序列化，消除 "Deserializing unregistered type" 警告
import langgraph.checkpoint.serde.jsonplus as jsonplus_serde
from backend.core.task_status import TaskState, OrchestratorState

try:
    jsonplus_serde.allowed_msgpack_types.add(('backend.models.task_spec', 'TaskSpec'))
    jsonplus_serde.allowed_msgpack_types.add(('backend.core.task_status', 'TaskState'))
    jsonplus_serde.allowed_msgpack_types.add(('backend.core.task_status', 'OrchestratorState'))
except Exception:
    pass  # 如果 API 变化不阻塞启动


class GraphState(TypedDict):
    """
    表示 LangGraph 工作流状态的 TypedDict。
    它在图的节点之间传递，并由每个节点更新。
    """
    # 对于简单的、非计划驱动的工作流，直接存储任务内容
    task_content: str

    # Planner 生成的原始计划
    plan_data: Dict[str, Any]

    tasks: List[TaskSpec]

    step_id: TaskResult

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

    plan_iteration: int

    shared_workspace: dict

    # 收集每个子 Agent 的执行结果，供前端展示 Agent 依次回复
    agent_outputs: List[Dict[str, str]]

    # ===== 新增字段：边界情况 & Replan 闭环 =====

    # 每个子任务的状态跟踪 {step_id: "succeeded" | "failed" | "retried" | "skipped"}
    task_states: Dict[str, str]

    # 重规划上下文：显式区分三类结果供 ReplanEvaluator 和 Planner 使用
    # {
    #   "valid_results": {step_id: result, ...},     # 保留+复用
    #   "failed_tasks": {step_id: {result, reason}},  # 失败原因
    #   "discarded_tasks": [step_id, ...]             # 废弃节点
    # }
    replan_context: Dict[str, Any]

    # 每个子任务的质量评估报告 {step_id: {"passed": bool, "score": int, "reasons": [...]}}
    quality_reports: Dict[str, Any]

    # 全局编排状态 "idle" | "init" | "running" | "retry" | "replan" | "degrade" | "success" | "failed"
    orchestrator_state: str