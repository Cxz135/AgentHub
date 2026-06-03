# core/agent_protocol.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid


class ArtifactModel(BaseModel):
    """
    一个与数据库无关的产物模型，用于在Agent和Orchestrator之间传递。
    """
    type: str
    content: str
    metadata: Dict[str, Any] = {}


class FinalAnswer(BaseModel):
    """
    表示一个直接发送给用户的最终答案。
    """
    content: str
    artifacts: List[ArtifactModel] = []


class ToolCall(BaseModel):
    """
    表示一个Agent希望Orchestrator执行的工具调用（即调用另一个Agent）。
    """
    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex}")
    tool_name: str
    arguments: Dict[str, Any]


class AgentResponse(BaseModel):
    """
    Agent `process_message` 方法的标准返回结构。
    它要么是一个最终答案，要么是一系列的工具调用请求。
    """
    final_answer: Optional[FinalAnswer] = None
    tool_calls: Optional[List[ToolCall]] = None