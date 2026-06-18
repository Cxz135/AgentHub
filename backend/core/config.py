"""
AgentHub 配置模块

集中管理所有硬编码常量，解决代码中的硬编码问题。
所有配置项可通过环境变量覆盖。
"""

import os
from typing import Optional

# ========== 工作流配置 ==========

WORKFLOW_TRIGGER_THRESHOLD: int = 6
"""
工作流自动匹配阈值。
当用户输入匹配的关键词得分超过此阈值时，触发固定工作流。
"""

# ========== Agent 配置 ==========

DEFAULT_MAX_ITERATIONS: int = 10
"""
Agent 执行的最大迭代次数（用于 ReAct 循环）。
"""

DEFAULT_MAX_RETRIES: int = 2
"""
Agent 验证失败后的最大重试次数。
"""

QUALITY_THRESHOLD: int = 60
ENABLE_QUALITY_CHECK: bool = True

REACT_MAX_ITERATIONS: int = 3
"""
ReAct AgentExecutor 的最大迭代次数。
注意：这个值比较小，因为每次迭代都涉及 LLM 调用。
"""

# ========== LLM 配置 ==========

LLM_HEALTH_CHECK_TIMEOUT: int = 8
"""
LLM 后端健康检查的超时时间（秒）。
"""

DEFAULT_TEMPERATURE: float = 0.7
"""
LLM 默认温度参数。
"""

DEFAULT_MAX_TOKENS: int = 8192
"""
LLM 默认最大生成 token 数。
"""

# ========== 流式输出配置 ==========

TOKEN_CHUNK_SIZE: int = 8
"""
模拟打字机效果时，每块输出的字符数。
用于 SSE 流式降级时模拟 token 发送。
"""

TOKEN_DELAY_MS: int = 15
"""
模拟打字机效果时，每块发送后的延迟（毫秒）。
"""

# ========== 记忆策略配置 ==========

DEFAULT_MEMORY_STRATEGY: str = "sliding_window"
"""
内置 Agent 的默认记忆策略。
可选值: none, sliding_window, summary
"""

DEFAULT_SLIDING_WINDOW_SIZE: int = 10
"""
sliding_window 策略的默认窗口大小。
"""

DEFAULT_SUMMARY_THRESHOLD: int = 4000
"""
summary 策略的默认 token 阈值。
"""
MAX_REPLAN_LIMIT: int = 2
MAX_TASK_RETRIES: int = 3
# ========== 数据库配置 ==========

MEMORY_DB_NAME: str = "agenthub_memory.sqlite"
"""
LangGraph checkpointer 使用的 SQLite 数据库文件名。
"""

# ========== Skill 配置 ==========

SKILL_PROMPT_TEMPLATE: str = """【重要】你必须始终使用中文回复，不得切换到其他语言。
当前日期：{date}

用户问题：{input}

请使用以下工具完成任务：
{available_tools}

完成后输出 Final Answer: 你的回答"""

# ========== 错误消息配置 ==========

ERROR_TOOL_NOT_FOUND: str = "错误：工具 '{tool}' 不存在，可用工具：{available}"
ERROR_TOOL_FAILED: str = "错误：工具执行失败：{error}"
ERROR_MODEL_EMPTY: str = "错误：模型返回内容为空，请重试"

# ========== 辅助函数 ==========

def get_date_now() -> str:
    """获取当前日期的中文格式"""
    from datetime import datetime
    return datetime.now().strftime('%Y年%m月%d日')

def mask_api_key(key: str) -> str:
    """掩码 API Key，仅显示前后各4个字符"""
    if not key or len(key) < 10:
        return "empty"
    return f"{key[:6]}...{key[-4:]}"