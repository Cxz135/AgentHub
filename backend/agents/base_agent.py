from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union

from pydantic import BaseModel


class FinalAnswer(BaseModel):
    """Agent 最终产出的标准格式。"""
    content: str


class AgentResponse(BaseModel):
    """
    Agent process_message 方法返回的标准结构。
    包含最终产出，可扩展以包含中间步骤、工具调用等。
    """
    final_answer: Optional[FinalAnswer] = None


class BaseAgent(ABC):
    """所有 Agent 的基础抽象类。"""

    agent_id: str

    def __init__(self, agent_id: str):
        if not agent_id:
            raise ValueError("agent_id is required for agent initialization.")
        self.agent_id = agent_id

    @abstractmethod
    async def process_message(
        self,
        messages: List[Any],
        context: Dict[str, Any] = None
    ) -> AgentResponse:
        """核心处理逻辑：接收消息历史和上下文，返回 AgentResponse。"""
        pass