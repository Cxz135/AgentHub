"""
记忆提取器 — LLM 驱动的结构化事实提取。

从对话轮次中提取：fact / preference / decision / user_trait。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core")

EXTRACTION_PROMPT = """你是一个信息提取助手。请从以下对话中提取值得长期保存的关键信息。

对于每条信息，输出一个 JSON 对象，包含以下字段：
- type: 信息类型，必须是以下四类之一：
  * user — 用户身份、技术偏好、沟通风格、长期习惯。必须是用户**明确表达**的长期特征。
    示例: "用户偏好使用函数式编程风格"、"用户是高级 Python 开发者"、"用户喜欢简洁的中文回复"
    反例: "用户让我用 Python 写排序算法"（这是临时任务请求，不是偏好！）
  * feedback — 用户明确纠正 AI 的表述或行为。必须包含 Why 和 How。
    示例: "用户说不应该用 pandas，数据量小时直接用原生 Python 更快"、"用户纠正：回复不要太啰嗦，直接给结论"
    反例: "用户说这次不用数据库"（这是临时决策，不是纠正）
  * project — 项目的架构决策、业务规则、技术约束、历史踩坑。跨任务有效。
    示例: "项目使用 FastAPI + SQLAlchemy 架构"、"决定使用 Chroma 作为向量数据库"、"上次部署时因为端口冲突踩了坑"
  * reference — 外部链接、API 端点、配置参数、第三方库名称和版本。只存标识符，不存完整内容。
    示例: "用户的项目部署在 https://api.example.com"、"使用 dashscope 0.9.0 版本"、"参考文档: LangGraph 官方教程"

- content: 信息内容（简洁中文，不超过 80 字）。必须是独立可理解的，不依赖对话上下文。
- importance: 重要性 0.0-1.0（这条信息对后续对话有多重要）。
  评分参考：
  - 用户明确要求记住的信息 → 0.9~1.0
  - 用户的纠正和反馈 → 0.8~0.95
  - 项目的架构决策和业务规则 → 0.7~0.9
  - 历史踩坑和解决方案 → 0.6~0.8
  - 通用偏好和习惯 → 0.5~0.7
  - 外部引用和配置 → 0.5~0.7
- confidence: 置信度 0.0-1.0（你有多确定这条信息是正确的）

重要规则：
1. 只提取有长期价值的信息，忽略临时闲聊和问候
2. 不要提取可以从对话上下文直接推断的显而易见的信息
3. 如果没有值得保存的信息，返回空数组 []
4. 每条信息的 content 必须独立可理解，不依赖对话上下文
5. **关键区分**：
   - "把这段代码换成 Java" → 这是临时任务请求，不是语言偏好。不提取。
   - "我更喜欢用 Java" → 这是语言偏好。提取为 user。
   - "用 Python 重写" → 这是临时任务请求，不是偏好。不提取。
   - "我习惯用函数式风格" → 这是编程风格偏好。提取为 user。
   - 用户要求用某种语言实现某个算法 → 这是任务请求，不提取。
6. 只有用户**明确表达**偏好、习惯、倾向时，才提取为 user。单个代码转换请求不构成偏好。
7. feedback 类型必须包含用户指出的问题（Why）和建议的改进（How）。
8. 敏感信息（密码、API 密钥、身份证号、手机号）绝对不要提取。
9. 精确到行号、时间戳的瞬时错误信息不要提取。

输出格式：严格输出 JSON 数组，不要包含任何其他文字。
```json
[
  {{"type": "user", "content": "...", "importance": 0.8, "confidence": 0.95}},
  {{"type": "feedback", "content": "...", "importance": 0.9, "confidence": 0.9}},
  {{"type": "project", "content": "...", "importance": 0.85, "confidence": 0.95}},
  {{"type": "reference", "content": "...", "importance": 0.6, "confidence": 0.9}}
]
```

对话内容：
{conversation_text}
"""


class MemoryExtractor:
    """使用 LLM 从对话中提取结构化记忆。"""

    MIN_CONFIDENCE = 0.6  # 低于此置信度的记忆不保存

    # 合法的记忆类型（新四分类 + 兼容旧类型）
    VALID_TYPES = {"user", "feedback", "project", "reference",
                   "fact", "preference", "decision", "user_trait"}

    # 旧类型 → 新类型映射
    _LEGACY_TYPE_MAP = {
        "fact": "project",
        "decision": "project",
        "preference": "user",
        "user_trait": "user",
    }

    def __init__(self, llm_backend: Any, write_guard: Any = None):
        self.llm_backend = llm_backend
        self._write_guard = write_guard  # 可选的 MemoryWriteGuard

    def set_write_guard(self, guard: Any) -> None:
        """注入 MemoryWriteGuard。"""
        self._write_guard = guard

    async def extract(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        conversation_id: Optional[int] = None,
        agent_id: str = "assistant",
    ) -> List[Any]:
        """
        从消息列表中提取结构化记忆。

        Args:
            messages: 最近的消息列表 [{"role": "user"/"assistant", "content": "..."}]
            user_id: 用户 ID
            conversation_id: 来源对话 ID
            agent_id: 产生回复的 Agent ID

        Returns:
            MemoryEntry 对象列表（尚未持久化，已通过 WriteGuard 过滤）
        """
        if not messages:
            return []

        # 构建对话文本
        conversation_text = "\n".join(
            f"{m.get('role', 'unknown')}: {str(m.get('content', ''))[:300]}"
            for m in messages[-6:]  # 最多分析最近 6 条
        )

        try:
            prompt = EXTRACTION_PROMPT.format(conversation_text=conversation_text)
            response = await self.llm_backend.chat([
                {"role": "user", "content": prompt}
            ])
            text = response.strip() if isinstance(response, str) else str(response).strip()
        except Exception as e:
            logger.warning(f"[MEMORY-EXTRACT] LLM 调用失败: {e}")
            return []

        # 解析 JSON
        raw_entries = self._parse_response(text)
        if not raw_entries:
            return []

        # 构建 MemoryEntry 对象
        from backend.models.memory import MemoryEntry

        results = []
        for item in raw_entries:
            if not isinstance(item, dict):
                continue

            mem_type = str(item.get("type", "project")).lower()
            if mem_type not in self.VALID_TYPES:
                logger.debug(f"[MEMORY-EXTRACT] 跳过非法类型: {mem_type}")
                continue

            confidence = float(item.get("confidence", 0.5))
            if confidence < self.MIN_CONFIDENCE:
                continue

            importance = max(0.0, min(1.0, float(item.get("importance", 0.5))))
            content = str(item.get("content", "")).strip()
            if not content or len(content) < 3:
                continue

            # 旧类型映射 + 新类型标准化
            legacy_type = mem_type
            if mem_type in self._LEGACY_TYPE_MAP:
                canonical_type = self._LEGACY_TYPE_MAP[mem_type]
            else:
                canonical_type = mem_type  # 已经是新四分类之一

            entry = MemoryEntry(
                user_id=user_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                memory_type=canonical_type,  # 标准化后的类型
                content=content[:500],
                importance=importance,
                confidence=confidence,
                meta_data={
                    "source_messages_count": len(messages),
                    "extraction_method": "llm",
                    "legacy_type": legacy_type,  # 保留原始类型
                },
            )
            results.append(entry)

        # ── WriteGuard 过滤 ──
        if self._write_guard and results:
            before = len(results)
            results = await self._write_guard.evaluate_batch(results, messages)
            filtered = before - len(results)
            if filtered > 0:
                logger.info(f"[MEMORY-EXTRACT] WriteGuard 过滤: {before} → {len(results)} ({filtered} 条拦截)")

        logger.info(f"[MEMORY-EXTRACT] 从 {len(messages)} 条消息中提取了 {len(results)} 条记忆")
        return results

    def _parse_response(self, text: str) -> List[Dict[str, Any]]:
        """从 LLM 响应中解析 JSON 数组。"""
        # 尝试多种解析策略
        strategies = [
            # 策略 1: ```json ... ``` 代码块
            lambda t: re.search(r'```json\s*\n?(.*?)\n?```', t, re.DOTALL),
            # 策略 2: 直接 JSON 数组
            lambda t: re.search(r'\[[\s\S]*\]', t),
        ]

        for strategy in strategies:
            match = strategy(text)
            if match:
                try:
                    parsed = json.loads(match.group(1) if match.lastindex else match.group(0))
                    if isinstance(parsed, list):
                        return parsed
                except (json.JSONDecodeError, IndexError):
                    continue

        logger.debug(f"[MEMORY-EXTRACT] 无法解析 LLM 响应: {text[:200]}")
        return []
