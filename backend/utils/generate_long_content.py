"""
长内容生成工具（generate_long_content）。

当 Agent 在 ReAct 循环中需要生成长文档/报告/代码时调用此工具。
内部直接调用 LLM，不受 ReAct 迭代限制，解决长输出被截断的问题。

工作流程：
1. 基于 topic + context 生成结构化大纲
2. 根据大纲一次性生成完整正文
3. 返回完整内容给 Agent
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("core")

# 在注册时注入，避免循环导入
_llm_backend = None


def set_llm_backend(backend):
    """由 Orchestrator 在初始化时注入 LLM 后端。"""
    global _llm_backend
    _llm_backend = backend


def generate_long_content(
    topic: str,
    context: str = "",
    outline_hints: str = "",
    format_type: str = "markdown",
) -> str:
    """
    生成长内容——先大纲、再正文，一次性输出完整结果。

    Args:
        topic: 文档主题/标题
        context: 可用参考资料（黑板上下文、搜索结果摘要等）
        outline_hints: 大纲提示（如"需包含背景、排查步骤、修复方案、FAQ四部分"）
        format_type: 输出格式（markdown / json / code / text）

    Returns:
        完整的生成内容
    """
    if not _llm_backend:
        return "错误：generate_long_content 未初始化 LLM 后端"

    # Phase 1: 生成大纲
    outline_prompt = (
        f"你是一个内容策划专家。请为以下主题设计一个简明大纲（仅输出章节/段落标题列表，不要详细内容）：\n\n"
        f"主题：{topic}\n"
    )
    if context:
        outline_prompt += f"\n参考资料：{context[:2000]}\n"
    if outline_hints:
        outline_prompt += f"\n大纲提示：{outline_hints}\n"
    outline_prompt += "\n请输出大纲（纯文本，每行一个章节标题，以 # 开头）："

    try:
        resp = _llm_backend.chat_sync([{"role": "user", "content": outline_prompt}])
        outline = resp.strip() if isinstance(resp, str) else str(resp.content).strip()
        logger.info(f"[generate_long_content] 大纲生成完成，长度: {len(outline)}")
    except Exception as e:
        logger.warning(f"[generate_long_content] 大纲生成失败，跳过: {e}")
        outline = ""

    # Phase 2: 根据大纲生成正文
    content_prompt = (
        f"你是一个专业的内容创作者。请根据以下信息生成完整的{format_type}格式内容。\n"
        f"字数不限，内容要详实、结构化、可直接交付。\n\n"
        f"主题：{topic}\n\n"
    )
    if outline:
        content_prompt += f"请严格按以下大纲组织内容：\n\n{outline}\n\n"
    if context:
        content_prompt += f"参考资料（请充分参考并引用）：\n{context[:3000]}\n\n"
    content_prompt += (
        f"请直接输出完整的{format_type}格式内容，不要输出\"以下是生成的内容\"等前缀。"
    )

    try:
        resp = _llm_backend.chat_sync([{"role": "user", "content": content_prompt}])
        content = resp.strip() if isinstance(resp, str) else str(resp.content).strip()
        logger.info(f"[generate_long_content] 正文生成完成，长度: {len(content)}")
        return content
    except Exception as e:
        logger.error(f"[generate_long_content] 正文生成失败: {e}")
        return f"长内容生成失败: {e}"


def generate_long_content_async(topic: str, context: str = "", outline_hints: str = "",
                                 format_type: str = "markdown") -> str:
    """同步包装器（供 LangChain Tool 调用）。"""
    return generate_long_content(topic, context, outline_hints, format_type)
