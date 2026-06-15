"""
任务状态枚举与有限状态机（FSM）定义。

定义 Orchestrator 全局状态和子 Agent 单体状态，
提供状态流转校验，防止非法状态跳转。
"""

from __future__ import annotations

import enum
from typing import Set, Dict


class OrchestratorState(enum.StrEnum):
    """全局顶层状态 —— Orchestrator 持有"""
    IDLE = "idle"            # 空闲，等待用户输入
    INIT = "init"            # 任务初始化，拆解原子子任务
    RUNNING = "running"      # 正常执行，分发任务给子 Agent
    RETRY = "retry"          # 局部重试，仅针对当前失败节点
    REPLAN = "replan"        # 重规划，推翻原有任务链路
    DEGRADE = "degrade"      # 降级执行，放弃复杂流程切换简易方案
    SUCCESS = "success"      # 全流程结束，汇总结果
    FAILED = "failed"        # 失败终止，多次重试/重规划/降级后仍无法执行


class TaskState(enum.StrEnum):
    """子 Agent 单体状态 —— 每个子任务独立"""
    PENDING = "pending"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRIED = "retried"
    SKIPPED = "skipped"      # 重规划后废弃的旧任务


# ========== 状态流转规则（FSM）==========

# 全局状态合法流转表：from_state → {合法 to_state 集合}
ORCHESTRATOR_TRANSITIONS: Dict[OrchestratorState, Set[OrchestratorState]] = {
    OrchestratorState.IDLE:    {OrchestratorState.INIT},
    OrchestratorState.INIT:    {OrchestratorState.RUNNING, OrchestratorState.FAILED},
    OrchestratorState.RUNNING: {
        OrchestratorState.RETRY,
        OrchestratorState.REPLAN,
        OrchestratorState.SUCCESS,
        OrchestratorState.FAILED,
    },
    OrchestratorState.RETRY:  {OrchestratorState.RUNNING, OrchestratorState.REPLAN, OrchestratorState.FAILED},
    OrchestratorState.REPLAN: {OrchestratorState.RUNNING, OrchestratorState.DEGRADE, OrchestratorState.FAILED},
    OrchestratorState.DEGRADE: {OrchestratorState.SUCCESS, OrchestratorState.FAILED},
    OrchestratorState.SUCCESS: set(),   # 终态
    OrchestratorState.FAILED:  set(),   # 终态
}


def can_transition(current: OrchestratorState, target: OrchestratorState) -> bool:
    """校验全局状态是否可以从 current 流转到 target。"""
    allowed = ORCHESTRATOR_TRANSITIONS.get(current, set())
    return target in allowed


def is_terminal(state: OrchestratorState) -> bool:
    """是否为终态（不可再流转）。"""
    return state in (OrchestratorState.SUCCESS, OrchestratorState.FAILED)


# 子任务状态合法流转表
TASK_TRANSITIONS: Dict[TaskState, Set[TaskState]] = {
    TaskState.PENDING:    {TaskState.EXECUTING, TaskState.SKIPPED},
    TaskState.EXECUTING:  {TaskState.SUCCEEDED, TaskState.FAILED},
    TaskState.FAILED:     {TaskState.RETRIED, TaskState.SKIPPED},
    TaskState.RETRIED:    {TaskState.EXECUTING},   # 重试后重新进入执行
    TaskState.SUCCEEDED:   set(),                   # 终态
    TaskState.SKIPPED:     set(),                   # 终态
}


def is_failed_state(state: TaskState) -> bool:
    """判断子任务是否处于失败相关的状态。"""
    return state in (TaskState.FAILED, TaskState.RETRIED)
