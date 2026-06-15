"""
计划复杂度分析器（PlanAnalyzer）。

纯函数模块：从 Planner 输出的 TaskSpec 列表中，
从三个维度分析复杂度，不依赖任何 LLM 调用。

三个维度：
1. 步骤数（Step Count）：1-3=simple, 4-7=moderate, 8+=complex
2. 依赖深度（Dependency Depth）：深度≤1=simple, 深度=2=moderate, 深度≥3=complex
3. 工具/领域多样性（Tool Diversity）：1个=simple, 2-3个=moderate, 4+个=complex

综合判定：取三个维度中的最高级别。
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

logger = logging.getLogger("core")


def analyze_plan_complexity(tasks: list) -> str:
    """
    分析任务计划复杂度，返回 "simple" | "moderate" | "complex"。

    三个维度取最高级别。
    """
    if not tasks:
        return "simple"

    step_count = _compute_step_count(tasks)
    dependency_depth = _compute_dependency_depth(tasks)
    tool_diversity = _compute_tool_diversity(tasks)

    levels = [
        _step_level(step_count),
        _depth_level(dependency_depth),
        _tool_level(tool_diversity),
    ]

    logger.info(
        f"[PlanAnalyzer] steps={step_count}, depth={dependency_depth}, "
        f"tools={tool_diversity} → levels={levels}"
    )

    if "complex" in levels:
        return "complex"
    if "moderate" in levels:
        return "moderate"
    return "simple"


def analyze_plan_detail(tasks: list) -> dict:
    """
    返回详细的分析结果，包含所有维度数据，供调试/日志使用。
    """
    return {
        "step_count": _compute_step_count(tasks),
        "dependency_depth": _compute_dependency_depth(tasks),
        "tool_diversity": _compute_tool_diversity(tasks),
        "agent_ids": _collect_agent_ids(tasks),
        "dependency_graph": _build_dependency_graph(tasks),
        "complexity": analyze_plan_complexity(tasks),
    }


# ========== 维度计算函数 ==========

def _compute_step_count(tasks: list) -> int:
    """子任务总数。"""
    return len(tasks)


def _compute_dependency_depth(tasks: list) -> int:
    """
    计算任务依赖图的最大深度。

    算法：
    1. 构建邻接表 DAG
    2. 对每个入度为 0 的节点做 BFS，记录每个节点的深度
    3. 返回最大深度

    无依赖 → depth=1（纯线性单层）
    依赖链 A→B→C → depth=3
    分支+合并 → 按最长路径算
    """
    graph = _build_dependency_graph(tasks)
    in_degree = _compute_in_degrees(tasks, graph)

    # 拓扑排序 + 深度计算
    queue = deque()
    depth: Dict[str, int] = {}

    for sid in graph:
        if in_degree.get(sid, 0) == 0:
            queue.append(sid)
            depth[sid] = 1

    # 处理孤立节点（无依赖也无被依赖）
    for task in tasks:
        sid = str(task.step_id) if hasattr(task, 'step_id') else str(task.get('step_id', ''))
        if sid not in depth:
            depth[sid] = 1
            if in_degree.get(sid, 0) == 0:
                queue.append(sid)

    while queue:
        current = queue.popleft()
        for neighbor in graph.get(current, []):
            in_degree[neighbor] = in_degree.get(neighbor, 1) - 1
            depth[neighbor] = max(depth.get(neighbor, 1), depth.get(current, 1) + 1)
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    max_depth = max(depth.values()) if depth else 1
    return max_depth


def _compute_tool_diversity(tasks: list) -> int:
    """统计不同 agent_id 的数量作为工具多样性指标。"""
    agent_ids = _collect_agent_ids(tasks)
    return len(agent_ids)


def _collect_agent_ids(tasks: list) -> Set[str]:
    """从任务列表中收���所有唯一的 agent_id。"""
    ids = set()
    for task in tasks:
        if hasattr(task, 'agent_id'):
            aid = str(task.agent_id)
        elif isinstance(task, dict):
            aid = str(task.get('agent_id', ''))
        else:
            continue
        if aid and aid not in ('planner', 'summarizer'):
            ids.add(aid)
    return ids


def _build_dependency_graph(tasks: list) -> Dict[str, List[str]]:
    """
    构建依赖图邻接表。

    Returns:
        {step_id: [依赖它的 step_id 列表]}
        即 edges: dep → task 的方向
    """
    all_ids = set()
    for task in tasks:
        sid = str(task.step_id) if hasattr(task, 'step_id') else str(task.get('step_id', ''))
        all_ids.add(sid)

    graph: Dict[str, List[str]] = {sid: [] for sid in all_ids}

    for task in tasks:
        if hasattr(task, 'step_id'):
            sid = str(task.step_id)
            deps = getattr(task, 'dependencies', []) or []
        elif isinstance(task, dict):
            sid = str(task.get('step_id', ''))
            deps = task.get('dependencies', []) or []
        else:
            continue

        for dep in deps:
            dep_str = str(dep)
            if dep_str in graph:
                graph[dep_str].append(sid)
            else:
                # 依赖的外部节点也登记
                graph[dep_str] = [sid]
                all_ids.add(dep_str)

    return graph


def _compute_in_degrees(tasks: list, graph: Dict[str, List[str]]) -> Dict[str, int]:
    """计算每个节点的入度。"""
    in_degree: Dict[str, int] = defaultdict(int)
    all_ids = set(graph.keys())
    for task in tasks:
        sid = str(task.step_id) if hasattr(task, 'step_id') else str(task.get('step_id', ''))
        all_ids.add(sid)

    for sid in all_ids:
        in_degree.setdefault(sid, 0)

    for node, neighbors in graph.items():
        for neighbor in neighbors:
            in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

    return dict(in_degree)


# ========== 评级映射函数 ==========

def _step_level(count: int) -> str:
    if count <= 3:
        return "simple"
    elif count <= 7:
        return "moderate"
    else:
        return "complex"


def _depth_level(depth: int) -> str:
    if depth <= 1:
        return "simple"
    elif depth == 2:
        return "moderate"
    else:
        return "complex"


def _tool_level(diversity: int) -> str:
    if diversity <= 1:
        return "simple"
    elif diversity <= 3:
        return "moderate"
    else:
        return "complex"
