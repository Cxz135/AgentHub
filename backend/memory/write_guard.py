"""
MemoryWriteGuard — 长期记忆写入前过滤器。

在 MemoryExtractor 提取事实后、持久化前，执行 Claude 官方的 "不许记" 规则。

规则优先级（从高到低）：
    1. sensitive     — 敏感信息（密钥/密码/个人隐私）
    2. temporary     — 一次性临时任务
    3. derivable     — 可从当前上下文直接推导
    4. transient     — 精确到行号/时间戳的瞬时状态
    5. intermediate  — 已完成且不会复用的中间结果
    6. duplicate     — 语义重复的冗余信息
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from backend.memory.base import GuardResult, MemoryEntry, MemoryType

logger = logging.getLogger("core")


# ═══════════════════════════════════════════════════════════════
# 敏感信息检测正则
# ═══════════════════════════════════════════════════════════════

_SENSITIVE_PATTERNS: List[tuple[str, str]] = [
    # (名称, 正则)
    ("API Key (通用)", r'(?:api[_-]?key|apikey|api[_-]?secret)\s*[:=]\s*[\'"]?[a-zA-Z0-9_\-]{20,}'),
    ("API Key (sk-)", r'sk-[a-zA-Z0-9]{20,}'),
    ("JWT Token", r'eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{10,}'),
    ("AWS Access Key", r'AKIA[0-9A-Z]{16}'),
    ("Private Key Header", r'-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----'),
    ("Password Assignment", r'(?:password|passwd|pwd)\s*[:=]\s*[\'"][^\'"]+[\'"]'),
    ("Connection String", r'(?:mongodb|mysql|postgresql|redis)://[^/\s]+:[^/\s]+@'),
    ("Token in Header", r'Authorization\s*:\s*Bearer\s+[a-zA-Z0-9_\-.]{20,}'),
    ("Generic Secret", r'(?:secret|token|credential)\s*[:=]\s*[\'"]?[a-zA-Z0-9_\-]{16,}'),
    ("Chinese ID Card", r'[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]'),
    ("Phone Number", r'1[3-9]\d{9}'),
    ("Email with Password", r'(?:邮箱|email|mail)[\s:：]+[\w.+-]+@[\w-]+\.[\w.-]+.*(?:密码|password|pwd)[\s:：]+\S+'),
]


# ═══════════════════════════════════════════════════════════════
# 临时任务检测正则
# ═══════════════════════════════════════════════════════════════

_TEMPORARY_TIME_PATTERNS = [
    r'(?:今天|明天|后天|下周[一二三四五六日]|下个月|明年)',
    r'(?:今天|明天|后天)(?:早上|上午|中午|下午|晚上|凌晨)?\d{1,2}[点:：]\d{0,2}',
    r'(?:这周|本周|下周|上周)[一二三四五六日]',
    r'\d{1,2}[点:：]\d{2}\s*(?:前|后|左右)',
    r'(?:一会儿|稍后|马上|等[一下]会|改天)',
    r'(?:\d+分钟后|\d+小时后|\d+天后)',
    r'(?:刚刚|刚才|之前|上次)',
]

_TEMPORARY_TASK_VERBS = [
    r'帮我(?:写|做|查|找|翻译|生成|画|改|修|删|加|创建|配置|安装|部署|运行|测试)',
    r'(?:写|做|查|找|翻译|生成|画|改|修|删|加|创建|配置|安装|部署|运行|测试)[一下]?(?:这个|那个|一个|一下)',
    r'(?:能|可以|能否|可不可以)(?:帮|给)我',
    r'(?:请|麻烦)(?:你|您)',
    r'(?:现在|当前|马上|立即)(?:就)?(?:开始|启动|执行)',
]


# ═══════════════════════════════════════════════════════════════
# MemoryWriteGuard
# ═══════════════════════════════════════════════════════════════

@dataclass
class GuardRuleResult:
    """单条规则的评估结果。"""
    passed: bool
    rule_name: str
    reason: str = ""


class MemoryWriteGuard:
    """
    长期记忆写入前过滤引擎。

    使用方式：
        guard = MemoryWriteGuard()
        result = await guard.evaluate(entry, context_messages)
        if result.allowed:
            await long_term_memory.store(entry)

        # 批量评估
        filtered = await guard.evaluate_batch(entries, context_messages)
    """

    def __init__(
        self,
        enabled: bool = True,
        strict_mode: bool = False,
        retriever: Any = None,  # MemoryRetriever，用于语义去重
    ):
        self.enabled = enabled
        self.strict_mode = strict_mode
        self._retriever = retriever

        # 规则执行顺序（优先级从高到低）
        self._rules = [
            ("sensitive", self._check_sensitive),
            ("temporary", self._check_temporary),
            ("derivable", self._check_derivable),
            ("transient", self._check_transient),
            ("intermediate", self._check_intermediate),
            ("duplicate", self._check_duplicate),
        ]

        # 去重缓存（内容哈希 → 首次出现时间）
        self._seen_hashes: Dict[str, float] = {}

    # ── 公共接口 ──

    async def evaluate(
        self,
        entry: MemoryEntry,
        context_messages: Optional[List[dict]] = None,
    ) -> GuardResult:
        """
        评估单条记忆是否应该写入。

        Args:
            entry: 待写入的记忆条目
            context_messages: 当前对话上下文 [{"role":..., "content":...}]

        Returns:
            GuardResult (allowed=True 表示放行)
        """
        if not self.enabled:
            return GuardResult(allowed=True, rule="", reason="WriteGuard disabled")

        for rule_name, rule_fn in self._rules:
            result = await rule_fn(entry, context_messages or [])
            if not result.passed:
                logger.debug(f"[WRITE-GUARD] 拒绝 ({rule_name}): {entry.content[:80]}")
                return GuardResult(
                    allowed=False,
                    rule=rule_name,
                    reason=result.reason,
                    score=0.0,
                )

        # 放行，计算修正后的重要性
        adjusted_score = self._adjust_importance(entry)
        return GuardResult(allowed=True, rule="", reason="", score=adjusted_score)

    async def evaluate_batch(
        self,
        entries: List[MemoryEntry],
        context_messages: Optional[List[dict]] = None,
    ) -> List[MemoryEntry]:
        """
        批量评估并返回过滤后的记忆列表。

        Args:
            entries: 待评估的记忆条目列表
            context_messages: 当前对话上下文

        Returns:
            通过过滤的记忆条目列表（已附加 Guard 评分到 metadata）
        """
        ctx = context_messages or []
        passed = []
        for entry in entries:
            result = await self.evaluate(entry, ctx)
            if result.allowed:
                entry.importance = max(entry.importance, result.score)
                entry.metadata["guard_rule"] = "passed"
                entry.metadata["guard_score"] = result.score
                passed.append(entry)
            else:
                logger.info(
                    f"[WRITE-GUARD] 拦截: rule={result.rule} "
                    f"content={entry.content[:60]}..."
                )
        return passed

    def set_retriever(self, retriever: Any) -> None:
        """注入 MemoryRetriever（用于语义去重）。"""
        self._retriever = retriever

    # ── 规则实现 ──

    async def _check_sensitive(
        self, entry: MemoryEntry, context: List[dict]
    ) -> GuardRuleResult:
        """检测敏感信息。"""
        content = entry.content
        for name, pattern in _SENSITIVE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return GuardRuleResult(
                    passed=False,
                    rule_name="sensitive",
                    reason=f"包含敏感信息 ({name})",
                )
        return GuardRuleResult(passed=True, rule_name="sensitive")

    async def _check_temporary(
        self, entry: MemoryEntry, context: List[dict]
    ) -> GuardRuleResult:
        """检测一次性临时任务。"""
        content = entry.content

        # 同时匹配时间表达式 AND 任务动词 = 临时任务
        has_time = any(
            re.search(p, content) for p in _TEMPORARY_TIME_PATTERNS
        )
        has_task = any(
            re.search(p, content) for p in _TEMPORARY_TASK_VERBS
        )

        if has_time and has_task:
            return GuardRuleResult(
                passed=False,
                rule_name="temporary",
                reason="包含临时时间表达式和任务性动词，为一次性请求",
            )

        # 仅匹配任务动词且为 user 类型（用户请求）= 很可能是临时任务
        if has_task and entry.memory_type == "user":
            return GuardRuleResult(
                passed=False,
                rule_name="temporary",
                reason="用户的一次性任务请求，不是长期偏好",
            )

        return GuardRuleResult(passed=True, rule_name="temporary")

    async def _check_derivable(
        self, entry: MemoryEntry, context: List[dict]
    ) -> GuardRuleResult:
        """检测是否可从当前上下文直接推导。"""
        content = entry.content.strip()

        # 精确匹配：如果已有消息中包含完全相同的内容
        for msg in context:
            msg_content = str(msg.get("content", ""))
            # 跳过 assistant 自己的回复（中间结果可能在 assistant 回复里）
            if msg.get("role") == "assistant":
                continue
            if content and len(content) > 10 and content in msg_content:
                return GuardRuleResult(
                    passed=False,
                    rule_name="derivable",
                    reason="信息已完整存在于当前对话中，无需单独记忆",
                )

        # 子集匹配：如果 entry 是某条消息的子串（且长度 > 20 字）
        if len(content) > 20:
            for msg in context:
                if msg.get("role") == "assistant":
                    continue
                msg_content = str(msg.get("content", ""))
                if len(msg_content) > len(content) and content in msg_content:
                    return GuardRuleResult(
                        passed=False,
                        rule_name="derivable",
                        reason="信息是已有消息的子串，可从上下文推导",
                    )

        return GuardRuleResult(passed=True, rule_name="derivable")

    async def _check_transient(
        self, entry: MemoryEntry, context: List[dict]
    ) -> GuardRuleResult:
        """检测精确到行号/时间戳/代码位置的瞬时状态。"""
        content = entry.content

        # 包含代码行号 + 错误信息
        # 匹配多种行号模式: line 42, L42, 第42行, 行42
        if re.search(r'(?:line|L)\s*\d+|\d+\s*行|第\s*\d+\s*行', content, re.IGNORECASE) and \
           len(content) < 100:
            return GuardRuleResult(
                passed=False,
                rule_name="transient",
                reason="包含具体行号的瞬时错误位置",
            )

        # 精确时间戳
        if re.search(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', content):
            return GuardRuleResult(
                passed=False,
                rule_name="transient",
                reason="包含精确时间戳的瞬时状态",
            )

        return GuardRuleResult(passed=True, rule_name="transient")

    async def _check_intermediate(
        self, entry: MemoryEntry, context: List[dict]
    ) -> GuardRuleResult:
        """检测已完成且不会复用的中间结果。"""
        content = entry.content

        # 检测中间产物标记
        intermediate_markers = [
            r'(?:中间|临时|暂存)(?:结果|数据|文件|输出)',
            r'正在(?:处理|执行|运行|生成|下载|上传)',
            r'步骤\s*\d+\s*[:：]',
            r'(?:尝试|试了)\s*\d+\s*(?:次|个|种)',
        ]

        for marker in intermediate_markers:
            if re.search(marker, content):
                # 检查是否是 assistant 的最终回复的一部分（如果在最终回复里，已经是最终结果了）
                is_in_final = False
                for msg in reversed(context):
                    if msg.get("role") == "assistant":
                        if content[:30] in str(msg.get("content", "")):
                            is_in_final = True
                        break
                if not is_in_final:
                    return GuardRuleResult(
                        passed=False,
                        rule_name="intermediate",
                        reason="中间执行结果，不具长期复用价值",
                    )

        return GuardRuleResult(passed=True, rule_name="intermediate")

    async def _check_duplicate(
        self, entry: MemoryEntry, context: List[dict]
    ) -> GuardRuleResult:
        """检测语义重复（内容哈希 + 可选向量检索）。"""
        content = entry.content.strip()

        # 1. 精确哈希去重（轻量，无外部依赖）
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if content_hash in self._seen_hashes:
            return GuardRuleResult(
                passed=False,
                rule_name="duplicate",
                reason="内容哈希重复，已存在相同记忆",
            )
        self._seen_hashes[content_hash] = entry.timestamp

        # 2. 语义相似度去重（需要 retriever）
        if self._retriever and len(content) > 10:
            try:
                existing = self._retriever.search(
                    query=content,
                    top_k=1,
                    min_similarity=0.92,
                )
                if existing and len(existing) > 0:
                    return GuardRuleResult(
                        passed=False,
                        rule_name="duplicate",
                        reason=f"语义相似度 > 0.92，已有相似记忆: {existing[0].get('content', '')[:50]}",
                    )
            except Exception as e:
                logger.debug(f"[WRITE-GUARD] duplicate 语义检查跳过: {e}")

        return GuardRuleResult(passed=True, rule_name="duplicate")

    # ── 辅助方法 ──

    def _adjust_importance(self, entry: MemoryEntry) -> float:
        """
        根据 memory_type 调整重要性基准。

        参考 Claude 的记忆评分权重：
        - user 明确要求记住 → 0.6 基准（手动 boost 到 1.0）
        - feedback 用户纠正 → 0.9 基准
        - project 架构决策 → 0.8 基准
        - reference 外部引用 → 0.6 基准
        """
        base = entry.importance
        if entry.memory_type == "feedback":
            base = max(base, 0.85)
        elif entry.memory_type == "project":
            base = max(base, 0.7)
        elif entry.memory_type == "user":
            base = max(base, 0.55)
        elif entry.memory_type == "reference":
            base = max(base, 0.5)
        return min(1.0, base)

    def clear_hash_cache(self) -> None:
        """清空哈希缓存（跨会话时调用）。"""
        self._seen_hashes.clear()
