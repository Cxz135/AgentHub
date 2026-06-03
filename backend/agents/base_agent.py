from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from pydantic import BaseModel

from backend.llm.base_llm import BaseLLM
from backend.models.message import Message


class FinalAnswer(BaseModel):
    """
    Agent 最终产出的标准格式。
    """
    content: str


class AgentResponse(BaseModel):
    """
    Agent process_message 方法返回的标准结构。
    它主要包含最终产出，未来可以扩展以包含中间步骤、工具调用等。
    """
    final_answer: Optional[FinalAnswer] = None


class BaseAgent(ABC):
    """
    所有 Agent 的基础抽象类。
    它定义了所有 Agent 都必须拥有的属性和必须实现的方法。
    """
    agent_id: str

    def __init__(self, agent_id: str):
        """
        每个 Agent 在初始化时都必须拥有一个唯一的 agent_id。
        """
        if not agent_id:
            raise ValueError("agent_id is required for agent initialization.")
        self.agent_id = agent_id

    @abstractmethod
    async def process_message(self, messages: List[Message], context: Dict[str, Any] = None) -> AgentResponse:
        """
        所有 Agent 的核心处理逻辑。
        它接收消息历史和上下文，并返回一个 AgentResponse 对象。
        """
        pass

    @abstractmethod
    async def process(self, messages: List[Message], context: Dict[str, Any] = None) -> Message:
        """
        一个兼容旧接口或用于直接返回 Message 对象的备用方法。
        在我们的新流程中，主要使用 process_message。
        """
        pass