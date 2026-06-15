"""
独立评估器（ReplanEvaluator）。

与 Planner 解耦的评估角色，只负责判断"是否需要 replan/降级/重试"，
不负责生成新任务计划。

两层决策链路：
1. 代码规则引擎（内联在 _evaluate_results_node，硬条件判断）
2. ReplanEvaluator.evaluate()（LLM 语义判断，仅在硬条件未触发时调用）

职责边界：
- ReplanEvaluator：判断状态 → 返回 action（retry/replan/degrade/complete）
- PlannerAgent：生成新计划 → 返回 TaskSpec[]
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List, Optional

logger = logging.getLogger("core")


@dataclass
class EvaluationVerdict:
    """评估器返回的判定结论"""
    action: str         # "retry" | "replan" | "degrade" | "complete"
    reason: str         # 评估理由
    confidence: float = 1.0   # 置信度 0.0-1.0


# ========== 硬条件判定函数（纯代码逻辑，不依赖 LLM）==========

def check_hard_replan_conditions(
    quality_reports: dict,
    task_states: dict,
    plan_iteration: int,
    max_replan_limit: int,
    max_task_retries: int,
) -> Optional[EvaluationVerdict]:
    """
    检查硬条件是否触发 replan 或 degrade。

    这些条件纯代码判断，不依赖 LLM，优先级最高。

    Returns:
        EvaluationVerdict 如果硬条件触发，否则 None（需要 LLM 评估）
    """
    # 条件1：重规划次数已达上限 → 强制降级
    if plan_iteration >= max_replan_limit:
        return EvaluationVerdict(
            action="degrade",
            reason=f"重规划次数已达上限（{plan_iteration}/{max_replan_limit}），强制降级",
            confidence=1.0,
        )

    # 条件2：检查是否有硬失败（质量不通过 + 重试已超限）
    hard_failures = []
    for task_id, report in quality_reports.items():
        if isinstance(report, dict):
            if not report.get("passed", True):
                state = task_states.get(task_id, "")
                # 如果已经 retried 过且仍失败 → 硬失败
                if state == "retried":
                    hard_failures.append(task_id)

    if hard_failures:
        return EvaluationVerdict(
            action="replan",
            reason=f"以下任务质量不通过且重试无效: {hard_failures}",
            confidence=0.95,
        )

    # 条件3：所有任务都失败 → replan
    if task_states:
        failed_count = sum(
            1 for s in task_states.values()
            if s in ("failed", "retried", "skipped")
        )
        succeeded_count = sum(
            1 for s in task_states.values()
            if s == "succeeded"
        )
        total = len(task_states)
        if failed_count > 0 and succeeded_count == 0:
            return EvaluationVerdict(
                action="replan",
                reason=f"所有{total}个任务均失败，无可用结果",
                confidence=1.0,
            )

    return None


class ReplanEvaluator:
    """
    独立的评估器 Agent。

    只负责判断"是否需要 replan/降级/重试"，不负责生成新计划。
    新计划生成仍由 PlannerAgent 负责，实现评估与规划解耦。
    """

    def __init__(
        self,
        llm_invoke: Callable[[List[dict]], Awaitable[Any]],
        prompt_loader=None,
    ):
        self.llm_invoke = llm_invoke
        self.prompt_loader = prompt_loader

    async def evaluate(
        self,
        task_content: str,
        valid_results: dict,
        failed_tasks: dict,
        plan_iteration: int,
        max_replan_limit: int,
    ) -> EvaluationVerdict:
        """
        评估当前执行状态，返回下一步 action。

        Args:
            task_content: 原始用户任务目标
            valid_results: 有效完成的结果 {step_id: result_text}
            failed_tasks: 失败的任务 {step_id: {result, reason, retries}}
            plan_iteration: 当前已重规划次数
            max_replan_limit: 最大重规划次数

        Returns:
            EvaluationVerdict 判定结论
        """
        # 如果没有失败任务 → complete
        if not failed_tasks:
            return EvaluationVerdict(
                action="complete",
                reason="所有任务已完成",
                confidence=1.0,
            )

        # 如果已达到重规划上限 → degrade
        if plan_iteration >= max_replan_limit:
            return EvaluationVerdict(
                action="degrade",
                reason=f"重规划次数已达上限（{plan_iteration}/{max_replan_limit}）",
                confidence=1.0,
            )

        # 调用 LLM 做语义评估
        evaluator_prompt = self._build_evaluator_prompt(
            task_content=task_content,
            valid_results=valid_results,
            failed_tasks=failed_tasks,
            replan_count=plan_iteration,
            max_replan=max_replan_limit,
        )

        try:
            resp = await self.llm_invoke([
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": evaluator_prompt},
            ])
            text = resp.strip() if isinstance(resp, str) else str(resp.content).strip()
            return self._parse_verdict(text)
        except Exception as exc:
            logger.error(f"[ReplanEvaluator] LLM 评估异常: {exc}")
            # 降级：如果有失败任务，尝试 replan
            return EvaluationVerdict(
                action="replan",
                reason=f"评估器异常降级: {exc}",
                confidence=0.3,
            )

    def _get_system_prompt(self) -> str:
        """获取评估器系统提示词，优先使用 YAML 配置。"""
        if self.prompt_loader:
            prompt = self.prompt_loader.get('agent', 'evaluator_system')
            if prompt and "Error:" not in prompt:
                return prompt

        # 内联兜底
        return (
            "你是独立的任务执行评估器。你的职责仅限于判断当前执行状态，"
            "决定下一步行动。你不需要生成新任务计划。\n\n"
            "评估标准：\n"
            "1. 如果失败任务可以通过调整指令重试 → retry\n"
            "2. 如果失败源于方案本身不合理，需要重新设计流程 → replan\n"
            "3. 如果多次重规划仍无法解决，应放弃复杂方案 → degrade\n"
            "4. 如果所有任务都已完成 → complete\n\n"
            '严格输出 JSON：{"action": "retry"|"replan"|"degrade"|"complete", '
            '"reason": "理由", "confidence": 0.0-1.0}。禁止输出任何其它文本。'
        )

    def _build_evaluator_prompt(
        self,
        task_content: str,
        valid_results: dict,
        failed_tasks: dict,
        replan_count: int,
        max_replan: int,
    ) -> str:
        """构造评估器 prompt。"""
        valid_summary = ""
        for sid, result in valid_results.items():
            result_str = str(result)[:200]
            valid_summary += f"- 任务{sid}: {result_str}...\n"

        failed_summary = ""
        for sid, info in failed_tasks.items():
            if isinstance(info, dict):
                reason = info.get("reason", info.get("result", "未知"))[:150]
            else:
                reason = str(info)[:150]
            failed_summary += f"- 任务{sid}: {reason}\n"

        return (
            f"【原始任务目标】\n{task_content}\n\n"
            f"【当前状态】重规划次数: {replan_count}/{max_replan}\n\n"
            f"【已完成有效结果】\n{valid_summary if valid_summary else '（无）'}\n"
            f"【失败任务及原因】\n{failed_summary if failed_summary else '（无）'}\n\n"
            "请判断下一步行动。注意：你只负责判断，不负责生成新计划。\n"
            '输出 JSON：{"action": "retry"|"replan"|"degrade"|"complete", '
            '"reason": "...", "confidence": 0.0-1.0}'
        )

    def _parse_verdict(self, text: str) -> EvaluationVerdict:
        """解析 LLM 返回的评估结论。"""
        try:
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                logger.warning(f"[ReplanEvaluator] 无法解析 JSON: {text[:200]}")
                return EvaluationVerdict(
                    action="replan",
                    reason="评估器输出解析失败，降级为重规划",
                    confidence=0.3,
                )
            verdict = json.loads(m.group(0))
            action = verdict.get("action", "replan")
            # 白名单校验 action
            if action not in ("retry", "replan", "degrade", "complete"):
                action = "replan"
            reason = verdict.get("reason", "评估器判定")
            confidence = float(verdict.get("confidence", 0.7))
            confidence = max(0.0, min(1.0, confidence))
            return EvaluationVerdict(action=action, reason=reason, confidence=confidence)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning(f"[ReplanEvaluator] JSON 解析异常: {exc}")
            return EvaluationVerdict(
                action="replan",
                reason=f"解析异常: {exc}",
                confidence=0.3,
            )
