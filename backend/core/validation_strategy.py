"""
校验策略运行时（A 档功能）。

在 Orchestrator 拿到 LLM 主回答之后调用 `apply_validation_strategy`，
按 Agent 的 validation_config 做后置校验，必要时触发重试。

- none      → 直通
- rules     → 逐条 regex / json_schema 匹配
- llm_judge → 再调一次 LLM 让其评估输出 {"pass":bool,"reason":str}
- 任何失败 + retries_left>0 → 由调用方决定是否重试（本函数只返回 ValidationResult）
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List, Optional

logger = logging.getLogger("core")


@dataclass
class ValidationResult:
    passed: bool
    reasons: List[str] = field(default_factory=list)
    strategy: str = "none"

    @property
    def reason_text(self) -> str:
        return "; ".join(self.reasons) if self.reasons else ""


def _validate_rule_regex(answer: str, rule: dict) -> Optional[str]:
    pattern = rule.get("pattern") or ""
    try:
        if not re.search(pattern, answer, re.MULTILINE | re.DOTALL):
            return rule.get("message") or f"未匹配正则: {pattern[:60]}"
    except re.error as exc:
        return f"正则编译失败: {exc}"
    return None


def _validate_rule_json_schema(answer: str, rule: dict) -> Optional[str]:
    schema = rule.get("schema")
    if not isinstance(schema, dict):
        return rule.get("message") or "json_schema 规则缺少 schema"
    # 尝试解析 answer 为 JSON
    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError as exc:
        return rule.get("message") or f"回答不是合法 JSON: {exc}"
    # 用 jsonschema 库做验证；若环境未装则降级为只校验顶层 type
    try:
        import jsonschema  # type: ignore
        try:
            jsonschema.validate(parsed, schema)
            return None
        except jsonschema.ValidationError as exc:
            return rule.get("message") or f"JSON Schema 校验失败: {exc.message}"
    except ImportError:
        # 降级：只检查顶层 type
        expected_type = schema.get("type")
        type_map = {
            "object": dict, "array": list, "string": str,
            "number": (int, float), "integer": int, "boolean": bool, "null": type(None),
        }
        py_type = type_map.get(expected_type) if expected_type else None
        if py_type and not isinstance(parsed, py_type):
            return rule.get("message") or f"JSON 顶层类型应为 {expected_type}"
        return None


async def _validate_llm_judge(
    answer: str,
    judge_prompt: str,
    llm_invoke: Callable[[List[dict]], Awaitable[Any]],
) -> Optional[str]:
    """让 LLM 评估 answer 是否合格。返回 None=通过，否则返回失败原因。"""
    system_prompt = (
        "你是回答质量评审员。请阅读评估要求与候选回答，"
        '严格输出 JSON：{"pass": true|false, "reason": "简短理由"}。'
        "禁止输出任何其它文本。"
    )
    user_prompt = (
        f"【评估要求】\n{judge_prompt}\n\n"
        f"【候选回答】\n{answer}\n\n"
        '请输出 JSON：{"pass": ..., "reason": "..."}'
    )
    try:
        resp = await llm_invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        text = resp.strip() if isinstance(resp, str) else str(resp).strip()
        # 容忍 ```json fenced 与额外文本
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return f"Judge 输出无法解析为 JSON: {text[:120]}"
        verdict = json.loads(m.group(0))
        if not isinstance(verdict, dict):
            return "Judge 输出不是 JSON 对象"
        if bool(verdict.get("pass")):
            return None
        return str(verdict.get("reason") or "Judge 判定不通过")
    except Exception as exc:
        return f"Judge 调用异常: {exc}"


async def apply_validation_strategy(
    answer: str,
    validation_config: Optional[dict],
    llm_invoke: Optional[Callable[[List[dict]], Awaitable[Any]]] = None,
) -> ValidationResult:
    """
    对主回答执行校验，返回 ValidationResult。
    任何异常都会被吞掉并视为「通过」，避免影响主流程。
    """
    if not validation_config or not isinstance(validation_config, dict):
        return ValidationResult(passed=True, strategy="none")

    strategy = str(validation_config.get("strategy", "")).lower()

    try:
        if strategy == "none" or not strategy:
            return ValidationResult(passed=True, strategy="none")

        if strategy == "rules":
            failures: List[str] = []
            for idx, rule in enumerate(validation_config.get("rules") or []):
                if not isinstance(rule, dict):
                    continue
                rule_type = str(rule.get("type", "")).lower()
                err: Optional[str] = None
                if rule_type == "regex":
                    err = _validate_rule_regex(answer, rule)
                elif rule_type == "json_schema":
                    err = _validate_rule_json_schema(answer, rule)
                if err:
                    failures.append(f"#{idx + 1} {err}")
            if failures:
                logger.info(f"[validation] strategy=rules, {len(failures)} 条失败")
                return ValidationResult(passed=False, reasons=failures, strategy="rules")
            logger.info("[validation] strategy=rules, all passed")
            return ValidationResult(passed=True, strategy="rules")

        if strategy == "llm_judge":
            judge_prompt = str(validation_config.get("judge_prompt") or "").strip()
            if not judge_prompt:
                logger.warning("[validation] llm_judge 缺少 judge_prompt，视为通过")
                return ValidationResult(passed=True, strategy="llm_judge")
            if not llm_invoke:
                logger.warning("[validation] llm_judge 缺少 llm_invoke，视为通过")
                return ValidationResult(passed=True, strategy="llm_judge")
            err = await _validate_llm_judge(answer, judge_prompt, llm_invoke)
            if err:
                logger.info(f"[validation] strategy=llm_judge, failed: {err}")
                return ValidationResult(passed=False, reasons=[err], strategy="llm_judge")
            logger.info("[validation] strategy=llm_judge, passed")
            return ValidationResult(passed=True, strategy="llm_judge")

    except Exception as exc:
        logger.warning(f"[validation] apply 失败，视为通过（config={validation_config}）: {exc}", exc_info=True)

    return ValidationResult(passed=True, strategy=strategy or "none")


def get_max_retries(validation_config: Optional[dict]) -> int:
    """从 validation_config 取出 max_retries，默认 0。"""
    if not validation_config or not isinstance(validation_config, dict):
        return 0
    try:
        return max(0, min(5, int(validation_config.get("max_retries", 0))))
    except (TypeError, ValueError):
        return 0
