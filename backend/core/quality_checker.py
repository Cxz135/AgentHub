"""
内容质量评估器（QualityChecker）。

对每个子任务执行结果做两层质量评估：
1. 规则引擎（代码判定，不消耗 LLM）：空内容、异常关键词、长度过短、格式校验
2. LLM 轻量评估（仅在规则引擎标记可疑时）：完整性、相关性、可用性

复用 `backend/core/validation_strategy.py` 中的 `_validate_llm_judge` 模式。

触发时机：每个子任务执行完成后，写入 step_results 之前调用。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List, Optional

from backend.core.config import QUALITY_THRESHOLD, ENABLE_QUALITY_CHECK

logger = logging.getLogger("core")


@dataclass
class QualityReport:
    """单个子任务的质量评估报告"""
    task_id: str
    passed: bool
    score: int = 0                # 0-100
    reasons: List[str] = field(default_factory=list)
    strategy: str = "none"        # "rules" | "llm_judge" | "none"
    dimension_scores: dict = field(default_factory=dict)  # {completeness, relevance, usability}

    @property
    def reason_text(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "通过"


# 异常关键词模式：匹配常见错误/截断/混乱输出
_EXCEPTION_KEYWORDS = [
    r"执行失败",
    r"执行出错",
    r"发生错误",
    r"Error:",
    r"Exception:",
    r"Traceback",
    r"timeout",
    r"connection refused",
    r"rate limit",
    r"token limit",
    r"抱歉.*无法",
    r"作为AI.*无法",
    r"\[截断\]",
    r"\[truncated\]",
]

# 合并为一个编译后的正则
_EXCEPTION_PATTERN = re.compile("|".join(_EXCEPTION_KEYWORDS), re.IGNORECASE)


def _check_empty(result: str) -> Optional[str]:
    """检查结果是否为空或仅空白。"""
    if not result or not result.strip():
        return "结果为空或仅包含空白字符"
    return None


def _check_too_short(result: str, min_length: int = 20) -> Optional[str]:
    """检查结果是否过短（可能为截断或无效输出）。"""
    stripped = result.strip()
    if len(stripped) < min_length:
        return f"结果过短（{len(stripped)}字符），可能为截断或无效输出"
    return None


def _check_exception_keywords(result: str) -> Optional[str]:
    """检查是否包含异常/错误关键词。"""
    match = _EXCEPTION_PATTERN.search(result)
    if match:
        return f"结果包含异常标记: {match.group()}"
    return None


def _check_format_compliance(result: str, expected_format: str) -> Optional[str]:
    """检查输出格式是否符合预期（如 JSON 任务要求返回 JSON）。"""
    if expected_format.lower() in ("json", "json_object", "application/json"):
        try:
            # 尝试提取 JSON
            m = re.search(r"```json\s*\n(.*?)\n```", result, re.DOTALL)
            if m:
                json.loads(m.group(1))
            else:
                json.loads(result.strip())
        except json.JSONDecodeError:
            return "期望 JSON 格式，但返回内容无法解析为有效 JSON"
    return None


class QualityChecker:
    """
    内容质量评估器。

    两层评估策略：
    1. 规则引擎：空内容、异常关键词、长度过短、格式校验 → 直接判定
    2. LLM 轻量评估：仅在规则引擎标记可疑时调用，评估完整性/相关性/可用性
    """

    def __init__(
        self,
        llm_invoke: Optional[Callable[[List[dict]], Awaitable[Any]]] = None,
        quality_threshold: int = QUALITY_THRESHOLD,
        enable: bool = ENABLE_QUALITY_CHECK,
    ):
        self.llm_invoke = llm_invoke
        self.quality_threshold = quality_threshold
        self.enable = enable

    async def assess(
        self,
        task_id: str,
        result: str,
        task_prompt: str = "",
        expected_format: str = "自然语言",
    ) -> QualityReport:
        """
        对单个子任务结果做质量评估。

        Args:
            task_id: 子任务 ID
            result: 子任务执行结果文本
            task_prompt: 原始任务指令（用于 LLM 评估上下文）
            expected_format: 期望的输出格式

        Returns:
            QualityReport 评估报告
        """
        if not self.enable:
            return QualityReport(task_id=task_id, passed=True, score=100, strategy="none")

        # ===== 第一层：规则引擎 =====
        failures: List[str] = []

        err = _check_empty(result)
        if err:
            failures.append(err)
            # 空结果是硬失败，无需继续检查
            logger.info(f"[QualityChecker] 任务{task_id} 规则引擎判定失败: {err}")
            return QualityReport(
                task_id=task_id,
                passed=False,
                score=0,
                reasons=failures,
                strategy="rules",
            )

        err = _check_too_short(result)
        if err:
            failures.append(err)

        err = _check_exception_keywords(result)
        if err:
            failures.append(err)

        err = _check_format_compliance(result, expected_format)
        if err:
            failures.append(err)

        # 规则引擎全部通过 → 直接判定合格
        if not failures:
            logger.debug(f"[QualityChecker] 任务{task_id} 规则引擎通过")
            return QualityReport(
                task_id=task_id,
                passed=True,
                score=85,  # 规则通过给一个基础分
                reasons=[],
                strategy="rules",
            )

        # 规则引擎标记可疑 → 若规则已足够判定为硬失败（空内容除外），则直接返回
        # 对于非空但有多项规则失败的，视为硬失败
        hard_failures = [f for f in failures if "结果为空" not in f and "结果过短" not in f]
        if len(hard_failures) >= 2:
            logger.info(f"[QualityChecker] 任务{task_id} 多项规则失败，直接判定不通过: {failures}")
            return QualityReport(
                task_id=task_id,
                passed=False,
                score=20,
                reasons=failures,
                strategy="rules",
            )

        # ===== 第二层：LLM 轻量评估 =====
        if not self.llm_invoke:
            # 无 LLM 可用 → 规则引擎结果即为最终结果
            passed = len(failures) <= 1  # 只有一项规则失败时宽容通过
            logger.info(f"[QualityChecker] 任务{task_id} 无LLM可用，规则判定: passed={passed}, reasons={failures}")
            return QualityReport(
                task_id=task_id,
                passed=passed,
                score=50 if passed else 30,
                reasons=failures,
                strategy="rules",
            )

        llm_result = await self._llm_assess(task_id, result, task_prompt)
        if llm_result is None:
            # LLM 评估失败 → 降级为规则引擎结果
            logger.warning(f"[QualityChecker] 任务{task_id} LLM评估失败，降级为规则判定")
            return QualityReport(
                task_id=task_id,
                passed=len(failures) <= 1,
                score=50,
                reasons=failures + ["LLM评估降级"],
                strategy="rules",
            )

        # 合并规则引擎和 LLM 评估结果
        all_reasons = failures + [r for r in llm_result.get("reasons", []) if r]
        score = llm_result.get("score", 50)
        passed = score >= self.quality_threshold and llm_result.get("pass", False)

        logger.info(
            f"[QualityChecker] 任务{task_id} 综合评估: passed={passed}, "
            f"score={score}, rules_failures={len(failures)}, "
            f"llm_pass={llm_result.get('pass')}"
        )

        return QualityReport(
            task_id=task_id,
            passed=passed,
            score=score,
            reasons=all_reasons,
            strategy="llm_judge",
            dimension_scores={
                "completeness": llm_result.get("completeness", 0),
                "relevance": llm_result.get("relevance", 0),
                "usability": llm_result.get("usability", 0),
            },
        )

    async def _llm_assess(
        self, task_id: str, result: str, task_prompt: str
    ) -> Optional[dict]:
        """LLM 轻量评估子任务结果质量。"""
        system_prompt = (
            "你是子任务结果质量评审员。请评估候选回答的质量，"
            "从完整性（是否完整回答问题）、相关性（是否偏离目标）、"
            "可用性（是否可被后续任务直接使用）三个维度打分。"
            '严格输出 JSON：{"pass": true|false, "score": 0-100, '
            '"completeness": 0-100, "relevance": 0-100, "usability": 0-100, '
            '"reasons": ["理由1", ...]}。禁止输出任何其它文本。'
        )
        task_context = f"\n【任务指令】\n{task_prompt[:500]}" if task_prompt else ""
        user_prompt = (
            f"【候选回答（前1000字）】\n{result[:1000]}{task_context}\n\n"
            '请输出 JSON：{"pass": ..., "score": ..., "completeness": ..., '
            '"relevance": ..., "usability": ..., "reasons": [...]}'
        )
        try:
            resp = await self.llm_invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ])
            text = resp.strip() if isinstance(resp, str) else str(resp.content).strip()
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                logger.warning(f"[QualityChecker] LLM 输出无法解析为 JSON: {text[:200]}")
                return None
            verdict = json.loads(m.group(0))
            if not isinstance(verdict, dict):
                return None
            return verdict
        except Exception as exc:
            logger.warning(f"[QualityChecker] LLM 评估异常: {exc}")
            return None
