"""
SessionMemoryAgent — 后台会话压缩代理。

在设计上借鉴了 Claude Code 的四级渐进式压缩机制：
    L1 工具结果缓存   (~50% token) → 大体积工具输出精简为关键发现
    L2 微压缩          (~70% token) → 去除冗余闲聊，保留指令和决策
    L3 会话记忆压缩    (~85% token) → 较早轮次生成结构化摘要
    L4 全量压缩        (~95% token) → 仅保留最近 5 轮原文，其余合并为全局会话摘要

核心设计原则：
    - 压缩不是删除，而是用结构化摘要**替换**原始消息
    - 维护独立的 session_summary 平面，增量更新
    - 后台 fire-and-forget 执行，不阻塞主流程

Integration:
    manager = MemoryManager(config)
    agent = SessionMemoryAgent(llm_backend)
    await agent.maybe_compress(short_term, summary)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("core")

# ── 压缩阈值（可配置） ──
DEFAULT_COMPRESSION_THRESHOLDS = {
    1: 0.50,  # L1: 超过 50% token 预算
    2: 0.70,  # L2: 超过 70%
    3: 0.85,  # L3: 超过 85%
    4: 0.95,  # L4: 超过 95%
}

# 每轮保留的原始消息数（L4 全量压缩后）
FULL_COMPACTION_KEEP_TURNS = 5

# token 估算系数（中文 ≈1.5 字/token，英文 ≈4 字/token）
_TOKEN_RATIO = 2.0


# ═══════════════════════════════════════════════════════════════
# 压缩提示词模板
# ═══════════════════════════════════════════════════════════════

COMPRESSION_PROMPTS = {
    1: """你是一个工具输出精简助手。请将以下对话中的大体积工具输出精简为关键发现。

规则：
1. 保留完整的用户消息和 assistant 的自然语言回复
2. 工具调用结果中，只保留关键数据、数字结论、重要链接
3. 删除冗长的日志、堆栈跟踪、重复文本
4. 保留所有错误信息和警告

对话内容：
{messages_text}

请输出精简后的对话，保持原始消息格式 [{{"role": "...", "content": "..."}}]。
直接输出 JSON 数组，不要其他文字。""",

    2: """你是一个对话压缩助手。请对以下对话进行微压缩，去除冗余内容。

规则：
1. 保留所有用户指令和明确的问题描述
2. 保留 assistant 的关键结论和建议
3. 去除问候语、闲聊、重复表述
4. 合并内容相似的连续消息
5. 保留所有错误信息、代码片段、关键数据

对话内容：
{messages_text}

请输出压缩后的对话。直接输出 JSON 数组格式 [{{"role": "...", "content": "..."}}]。""",

    3: """你是一个会话摘要助手。请将以下对话中较早的轮次压缩为结构化摘要。

你需要生成一个 JSON 对象（不是数组），包含以下字段：
- summary: 整体摘要（不超过 300 字），包含对话脉络和关键进展
- key_decisions: 达成的明确结论列表
- active_tasks: 仍在进行中的任务列表
- errors_encountered: 遇到的错误及解决方式列表
- pending_questions: 尚未解决的问题列表
- user_preferences: 对话中体现的用户偏好列表

规则：
1. 优先保留最近 6 轮的原文，压缩更早的轮次
2. 摘要是给后续 LLM 调用看的上下文，要简洁有用
3. 错误信息必须保留具体的错误类型和解决思路
4. 如果某个字段没有内容，返回空数组

对话内容：
{messages_text}

请直接输出 JSON 对象，不要其他文字。""",

    4: """你是一个全局会话摘要助手。请将整场对话压缩为一个全局摘要。

生成一个 JSON 对象，包含：
- global_summary: 全局摘要（不超过 500 字），覆盖对话的完整脉络
- key_outcomes: 已交付的成果列表
- unresolved: 仍未解决的问题
- user_context: 从对话中了解到的用户背景和需求
- suggestions: 对后续对话的建议

对话内容：
{messages_text}

请直接输出 JSON 对象，不要其他文字。""",
}


# ═══════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class CompressionResult:
    """一次压缩操作的结果。"""

    level: int                                    # 压缩级别 (1-4)
    compressed: bool                              # 是否实际执行了压缩
    messages_before: int                          # 压缩前消息数
    messages_after: int                           # 压缩后消息数
    tokens_before: int                            # 压缩前 token 估算
    tokens_after: int                             # 压缩后 token 估算
    summary: Optional[str] = None                 # L3/L4 生成的摘要文本
    structured: Optional[Dict[str, Any]] = None   # L3/L4 的结构化摘要
    error: Optional[str] = None                   # 压缩失败时的错误信息
    compressed_messages: Optional[List[dict]] = None  # L1/L2 压缩后的消息列表


@dataclass
class SessionSummary:
    """跨压缩操作累积的会话摘要平面。"""

    global_summary: str = ""                      # 全局摘要（L4 生成）
    segment_summaries: List[str] = field(default_factory=list)  # L3 段落摘要列表
    key_decisions: List[str] = field(default_factory=list)
    active_tasks: List[str] = field(default_factory=list)
    errors_encountered: List[Dict[str, str]] = field(default_factory=list)
    user_preferences: List[str] = field(default_factory=list)
    total_compressions: int = 0                   # 累计压缩次数
    last_compression_level: int = 0
    compression_savings: int = 0                  # 累计节省的 token

    def to_context_text(self) -> str:
        """生成注入 LLM 上下文的文本。"""
        parts = []
        if self.global_summary:
            parts.append(f"## 会话全局摘要\n{self.global_summary}")
        if self.key_decisions:
            parts.append("## 关键决策\n" + "\n".join(f"- {d}" for d in self.key_decisions[-10:]))
        if self.active_tasks:
            parts.append("## 进行中的任务\n" + "\n".join(f"- {t}" for t in self.active_tasks[-5:]))
        if self.errors_encountered:
            parts.append("## 遇到的错误\n" + "\n".join(
                f"- {e.get('error', '')}: {e.get('resolution', '')}" for e in self.errors_encountered[-5:]
            ))
        if self.user_preferences:
            parts.append("## 用户偏好\n" + "\n".join(f"- {p}" for p in self.user_preferences[-5:]))
        return "\n\n".join(parts) if parts else ""


# ═══════════════════════════════════════════════════════════════
# SessionMemoryAgent
# ═══════════════════════════════════════════════════════════════

class SessionMemoryAgent:
    """
    后台会话压缩代理。

    使用方式:
        agent = SessionMemoryAgent(llm_backend)
        result = await agent.maybe_compress(short_term, summary, max_tokens=8000)

    工作流程:
        1. 估算当前短期记忆的 token 数
        2. 与 max_tokens 比较，判断是否触发压缩
        3. 触发后调用 LLM 执行对应级别的压缩
        4. 更新 ShortTermMemory 的消息列表
        5. 更新 SummaryMemory 的会话摘要平面
    """

    def __init__(
        self,
        llm_backend: Any = None,
        thresholds: Dict[int, float] = None,
        max_tokens: int = 8000,
        enabled: bool = True,
    ):
        self.llm_backend = llm_backend
        self.thresholds = thresholds or DEFAULT_COMPRESSION_THRESHOLDS
        self.max_tokens = max_tokens
        self.enabled = enabled

        # 累积的会话摘要平面
        self._session_summary = SessionSummary()

        # 上一次的压缩级别（防止重复压缩同一级别）
        self._last_level = 0

        # 压缩锁（防止并发压缩）
        self._compressing = False

    # ── 公共接口 ──

    async def maybe_compress(
        self,
        short_term: Any,     # ShortTermMemory 实例
        summary: Any = None, # SummaryMemory 实例
        force: bool = False,
    ) -> CompressionResult:
        """
        检查是否需要压缩，如果需要则执行。

        Args:
            short_term: 短期记忆实例
            summary: 摘要记忆实例（L3/L4 需要）
            force: 强制压缩到下一级别

        Returns:
            CompressionResult
        """
        if not self.enabled or self._compressing:
            return CompressionResult(level=0, compressed=False,
                                     messages_before=0, messages_after=0,
                                     tokens_before=0, tokens_after=0)

        if not self.llm_backend:
            return CompressionResult(level=0, compressed=False,
                                     messages_before=0, messages_after=0,
                                     tokens_before=0, tokens_after=0,
                                     error="无 LLM backend")

        # 获取当前消息和 token 估算
        messages = await short_term.get_context_messages() if hasattr(short_term, 'get_context_messages') else []
        raw_messages = short_term._messages if hasattr(short_term, '_messages') else messages

        current_tokens = self._estimate_tokens(raw_messages)
        token_ratio = current_tokens / self.max_tokens if self.max_tokens > 0 else 0

        # 判断是否需要压缩
        target_level = self._determine_level(token_ratio, force)
        if target_level == 0:
            return CompressionResult(level=0, compressed=False,
                                     messages_before=len(raw_messages),
                                     messages_after=len(raw_messages),
                                     tokens_before=current_tokens,
                                     tokens_after=current_tokens)

        # 执行压缩
        self._compressing = True
        try:
            result = await self._execute_compression(
                level=target_level,
                messages=raw_messages,
                token_ratio=token_ratio,
            )

            # 更新短期记忆
            if result.compressed and hasattr(short_term, '_messages'):
                if result.compressed_messages:
                    short_term._messages = result.compressed_messages

            # 更新会话摘要
            if result.structured:
                self._merge_structured_summary(result.structured)

            # 更新统计
            self._last_level = target_level
            self._session_summary.total_compressions += 1
            self._session_summary.last_compression_level = target_level
            self._session_summary.compression_savings += (result.tokens_before - result.tokens_after)

            logger.info(
                f"[SESSION-AGENT] L{target_level} 压缩完成: "
                f"{result.messages_before}→{result.messages_after} 条消息, "
                f"{result.tokens_before}→{result.tokens_after} tokens "
                f"({(1 - result.tokens_after/max(1,result.tokens_before))*100:.0f}% 节省)"
            )

            return result

        except Exception as e:
            logger.warning(f"[SESSION-AGENT] L{target_level} 压缩失败: {e}")
            return CompressionResult(
                level=target_level, compressed=False,
                messages_before=len(raw_messages), messages_after=len(raw_messages),
                tokens_before=current_tokens, tokens_after=current_tokens,
                error=str(e),
            )
        finally:
            self._compressing = False

    def get_session_summary(self) -> SessionSummary:
        """获取累积的会话摘要平面。"""
        return self._session_summary

    def get_session_context_text(self) -> str:
        """获取会话摘要的上下文文本（注入 LLM）。"""
        return self._session_summary.to_context_text()

    def reset(self) -> None:
        """重置会话摘要（新会话开始时调用）。"""
        self._session_summary = SessionSummary()
        self._last_level = 0

    # ── 内部方法 ──

    def _determine_level(self, token_ratio: float, force: bool = False) -> int:
        """
        根据 token 使用率判断压缩级别。

        返回最高适用的压缩级别（必须 > _last_level 防止重复压缩同一级）。
        """
        if force:
            return min(self._last_level + 1, 4)

        # 从高到低遍历，返回第一个满足条件的（最高级别）
        for level in sorted(self.thresholds.keys(), reverse=True):
            if token_ratio >= self.thresholds[level] and level > self._last_level:
                return level
        return 0

    def _estimate_tokens(self, messages: List[dict]) -> int:
        """估算消息列表的 token 数。"""
        total = 0
        for m in messages:
            content = str(m.get("content", ""))
            total += int(len(content) / _TOKEN_RATIO) + 4  # 4 = role + overhead
        return total

    async def _execute_compression(
        self,
        level: int,
        messages: List[dict],
        token_ratio: float,
    ) -> CompressionResult:
        """执行指定级别的压缩。"""
        if not messages:
            return CompressionResult(
                level=level, compressed=False,
                messages_before=0, messages_after=0,
                tokens_before=0, tokens_after=0,
            )

        tokens_before = self._estimate_tokens(messages)

        # 准备消息文本
        messages_text = self._format_messages(messages, level)

        # 获取提示词
        prompt = COMPRESSION_PROMPTS.get(level)
        if not prompt:
            return CompressionResult(
                level=level, compressed=False,
                messages_before=len(messages), messages_after=len(messages),
                tokens_before=tokens_before, tokens_after=tokens_before,
                error=f"无级别 {level} 的提示词",
            )

        # 调用 LLM
        try:
            response = await self.llm_backend.chat([
                {"role": "user", "content": prompt.format(messages_text=messages_text)}
            ])
            text = response.strip() if isinstance(response, str) else str(response).strip()
        except Exception as e:
            return CompressionResult(
                level=level, compressed=False,
                messages_before=len(messages), messages_after=len(messages),
                tokens_before=tokens_before, tokens_after=tokens_before,
                error=f"LLM 调用失败: {e}",
            )

        # 解析和构建结果
        return self._parse_compression_result(level, text, messages, tokens_before)

    def _format_messages(self, messages: List[dict], level: int) -> str:
        """格式化消息供 LLM 压缩。"""
        # L4 全量压缩：发送所有消息
        # L3 段落压缩：发送除最近 6 条外的消息
        # L1/L2：发送所有消息

        if level == 3:
            # 保留最近 6 条原文，压缩更早的消息
            keep = min(6, len(messages))
            to_compress = messages[:-keep] if len(messages) > keep else []
            if not to_compress:
                return ""
            return "\n".join(
                f"[{m.get('role', '?')}]: {str(m.get('content', ''))[:500]}"
                for m in to_compress
            )

        return "\n".join(
            f"[{m.get('role', '?')}]: {str(m.get('content', ''))[:500]}"
            for m in messages
        )

    def _parse_compression_result(
        self,
        level: int,
        text: str,
        original_messages: List[dict],
        tokens_before: int,
    ) -> CompressionResult:
        """解析 LLM 响应并构建 CompressionResult。"""
        if level <= 2:
            # L1/L2: 返回精简后的消息列表
            compressed_messages = self._parse_json_array(text)
            if not compressed_messages:
                # 解析失败，保留原始消息
                return CompressionResult(
                    level=level, compressed=False,
                    messages_before=len(original_messages),
                    messages_after=len(original_messages),
                    tokens_before=tokens_before,
                    tokens_after=tokens_before,
                    error="无法解析 LLM 响应为消息数组",
                )

            tokens_after = self._estimate_tokens(compressed_messages)
            return CompressionResult(
                level=level,
                compressed=True,
                messages_before=len(original_messages),
                messages_after=len(compressed_messages),
                tokens_before=tokens_before,
                tokens_after=tokens_after,
                compressed_messages=compressed_messages,
            )

        else:
            # L3/L4: 返回结构化摘要
            structured = self._parse_json_object(text)
            if not structured:
                return CompressionResult(
                    level=level, compressed=False,
                    messages_before=len(original_messages),
                    messages_after=len(original_messages),
                    tokens_before=tokens_before,
                    tokens_after=tokens_before,
                    error="无法解析 LLM 响应为 JSON 对象",
                )

            # L4: 只保留最近几轮的原文
            if level == 4:
                keep = min(FULL_COMPACTION_KEEP_TURNS, len(original_messages))
                compressed_count = keep
            else:
                # L3: 保留最近 6 条 + 压缩摘要
                keep = min(6, len(original_messages))
                compressed_count = keep + 1  # +1 为摘要消息

            summary_text = structured.get("summary") or structured.get("global_summary", "")
            tokens_after = int(len(summary_text) / _TOKEN_RATIO) + keep * 100

            return CompressionResult(
                level=level,
                compressed=True,
                messages_before=len(original_messages),
                messages_after=compressed_count,
                tokens_before=tokens_before,
                tokens_after=tokens_after,
                summary=summary_text,
                structured=structured,
            )

    def _merge_structured_summary(self, structured: Dict[str, Any]) -> None:
        """将结构化摘要合并到累积的会话摘要平面。"""
        ss = self._session_summary

        if "global_summary" in structured:
            ss.global_summary = structured["global_summary"]

        if "summary" in structured:
            ss.segment_summaries.append(structured["summary"])

        if "key_decisions" in structured:
            for d in structured["key_decisions"]:
                if d not in ss.key_decisions:
                    ss.key_decisions.append(d)

        if "active_tasks" in structured:
            ss.active_tasks = structured["active_tasks"]

        if "errors_encountered" in structured:
            for e in structured["errors_encountered"]:
                if e not in ss.errors_encountered:
                    ss.errors_encountered.append(e)

        if "user_preferences" in structured:
            for p in structured["user_preferences"]:
                if p not in ss.user_preferences:
                    ss.user_preferences.append(p)

    # ── JSON 解析 ──

    def _parse_json_array(self, text: str) -> Optional[List[dict]]:
        """解析 LLM 响应为 JSON 数组。"""
        strategies = [
            lambda t: re.search(r'```json\s*\n?(.*?)\n?```', t, re.DOTALL),
            lambda t: re.search(r'\[[\s\S]*\]', t),
        ]
        for strategy in strategies:
            match = strategy(text)
            if match:
                try:
                    result = json.loads(match.group(1) if match.lastindex else match.group(0))
                    if isinstance(result, list):
                        return result
                except (json.JSONDecodeError, IndexError):
                    continue
        return None

    def _parse_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        """解析 LLM 响应为 JSON 对象。"""
        strategies = [
            lambda t: re.search(r'```json\s*\n?(.*?)\n?```', t, re.DOTALL),
            lambda t: re.search(r'\{[\s\S]*\}', t),
        ]
        for strategy in strategies:
            match = strategy(text)
            if match:
                try:
                    result = json.loads(match.group(1) if match.lastindex else match.group(0))
                    if isinstance(result, dict):
                        return result
                except (json.JSONDecodeError, IndexError):
                    continue
        return None
