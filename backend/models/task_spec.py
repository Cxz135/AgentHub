from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class TaskSpec(BaseModel):
    step_id: str
    agent_id: str
    prompt: str                # 派发任务的具体指令
    context: Dict[str, Any] = {}   # 从黑板注入的上下文
    expectations: Dict[str, str] = {}  # pass, standard, excellent
    output_format: str = "自然语言"
    max_retries: int = 1
    dependencies: list[str] = []     # 前置步骤的 step_id

    # 量化验收标准，供 QualityChecker 自动检查
    # {"must_include": ["关键词1", ...], "must_not_include": ["禁止词", ...], "min_length": 100, "format_rules": ["有效JSON", ...]}
    acceptance_criteria: Dict[str, Any] = {}

class TaskResult(BaseModel):
    step_id: str
    status: str               # success / partial / failed
    result: str
    findings: str = ""        # 写入黑板的发现
    outputs: Dict[str, Any] = {}

    # ===== 新增字段：边界情况 & Replan 闭环 =====

    # 任务状态机状态：pending / executing / succeeded / failed / retried / skipped
    state: str = "pending"

    # 内容质量评分 0-100，-1 表示未评估
    quality_score: int = -1

    # 评估器备注，记录质量不通过原因等
    evaluator_notes: str = ""