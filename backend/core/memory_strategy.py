"""
记忆策略运行时（A 档功能）。

在 Orchestrator 把消息列表交给 LLM 之前调用 `apply_memory_strategy`，
对历史消息按 Agent 的 memory_config 做裁剪 / 摘要：

- none           → 仅保留最后一条 user message
- sliding_window → 保留最近 window_size*2 条（user/assistant 各算一条）
- summary        → 估算 token 数；超阈值则调用 LLM 生成系统摘要，
                   把历史替换成一条 system 摘要 + 最近 2 条原文

本层不动 LangGraph checkpointer 中的对话原文，
只对喂给 LLM 的临时 messages 做裁剪。
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, List, Optional

logger = logging.getLogger("core")

# 粗略估算 token 数（中文 ~1 char ≈ 1 token，英文 ~4 char ≈ 1 token，平均按 2.5）
# 不依赖 tiktoken，避免新增重依赖
_TOKEN_RATIO = 2.5


def _estimate_tokens(messages: List[dict]) -> int:
    total = 0
    for m in messages:
        content = m.get("content") or ""
        total += int(len(str(content)) / _TOKEN_RATIO) + 4  # 4 token 开销
    return total


def _default_summary_prompt() -> str:
    return "请用不超过 200 字概括以下对话的关键信息、用户意图和已知结论，便于后续轮次延续上下文。"


async def apply_memory_strategy(
    messages: List[dict],
    memory_config: Optional[dict],
    llm_invoke: Optional[Callable[[List[dict]], Awaitable[Any]]] = None,
) -> List[dict]:
    """
    根据 memory_config 对 messages 做裁剪/摘要。

    Args:
        messages: 原始消息列表，每条形如 {"role": "user"|"assistant"|"system", "content": str}
        memory_config: 来自 db_agent.memory_config，可能为 None
        llm_invoke: 异步 LLM 调用函数 (messages -> str)，仅 summary 策略需要

    Returns:
        裁剪后的 messages（新列表，不修改入参）。
        任何异常都会被吞掉并 fallback 到原始 messages，保证不影响主流程。
    """
    if not memory_config or not isinstance(memory_config, dict):
        return messages

    strategy = str(memory_config.get("strategy", "")).lower()
    if strategy not in ("none", "sliding_window", "summary", ""):
        logger.warning(f"[memory] 未知的记忆策略 '{strategy}'，回退到原始 messages。有效值: none, sliding_window, summary")
        return messages

    try:
        if strategy == "none":
            # 仅保留最后一条 user
            for m in reversed(messages):
                if m.get("role") == "user":
                    logger.info("[memory] strategy=none, keep 1 user message")
                    return [m]
            return messages[-1:]

        if strategy == "sliding_window":
            window_size = int(memory_config.get("window_size", 10))
            keep = window_size * 2  # 每轮 user+assistant 两条
            sliced = messages[-keep:] if len(messages) > keep else messages
            logger.info(
                f"[memory] strategy=sliding_window, window={window_size}, "
                f"messages {len(messages)} → {len(sliced)}"
            )
            return sliced

        if strategy == "summary":
            threshold = int(memory_config.get("summary_threshold", 4000))
            est = _estimate_tokens(messages)
            if est <= threshold:
                logger.info(
                    f"[memory] strategy=summary, tokens {est} <= threshold {threshold}, skip"
                )
                return messages
            if not llm_invoke:
                logger.warning("[memory] strategy=summary 缺少 llm_invoke，回退到原始 messages")
                return messages
            # 摘要历史 = messages 中除最后 2 条以外的部分
            history = messages[:-2] if len(messages) > 2 else messages[:]
            tail = messages[-2:] if len(messages) > 2 else []
            prompt = memory_config.get("summary_prompt") or _default_summary_prompt()
            joined_history = "\n".join(
                f"{m.get('role', 'unknown')}: {str(m.get('content', '')).strip()}"
                for m in history
            )
            summary_messages = [
                {"role": "system", "content": str(prompt)},
                {"role": "user", "content": joined_history},
            ]
            try:
                summary_resp = await llm_invoke(summary_messages)
                summary_text = (
                    summary_resp.strip() if isinstance(summary_resp, str) else str(summary_resp).strip()
                )
            except Exception as exc:
                logger.warning(f"[memory] summary 调用失败，回退到原始 messages: {exc}")
                return messages
            logger.info(
                f"[memory] strategy=summary, tokens {est} > threshold {threshold}, "
                f"summarized {len(history)} → 1 system message"
            )
            return [{"role": "system", "content": f"【历史摘要】{summary_text}"}, *tail]

    except Exception as exc:
        logger.warning(f"[memory] apply 失败，回退到原始 messages（config={memory_config}）: {exc}", exc_info=True)

    return messages
