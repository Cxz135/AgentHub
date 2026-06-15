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

# ========== Replan 与重试配置 ==========

MAX_REPLAN_LIMIT: int = 2
"""
最大重规划次数。超过此次数后强制进入降级模式，防止无限循环 Replan。
可通过环境变量 MAX_REPLAN_LIMIT 覆盖。
"""

QUALITY_THRESHOLD: int = 50
"""
内容质量评分阈值（0-100）。
子任务结果质量评分低于此值视为不通过，触发重试或重规划。
可通过环境变量 QUALITY_THRESHOLD 覆盖。
"""

MAX_TASK_RETRIES: int = 3
"""
单个子任务最大重试次数（包含首次执行）。
可通过环境变量 MAX_TASK_RETRIES 覆盖。
"""

ENABLE_QUALITY_CHECK: bool = True
"""
是否启用内容质量检查特性开关。
设置为 False 可降级为仅依赖异常判断的旧行为。
可通过环境变量 ENABLE_QUALITY_CHECK 覆盖。
"""


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name, str(default)).lower()
    return val in ("1", "true", "yes", "on")


# 从环境变量覆盖默认值
MAX_REPLAN_LIMIT = _env_int("MAX_REPLAN_LIMIT", MAX_REPLAN_LIMIT)
QUALITY_THRESHOLD = _env_int("QUALITY_THRESHOLD", QUALITY_THRESHOLD)
MAX_TASK_RETRIES = _env_int("MAX_TASK_RETRIES", MAX_TASK_RETRIES)
ENABLE_QUALITY_CHECK = _env_bool("ENABLE_QUALITY_CHECK", ENABLE_QUALITY_CHECK)


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