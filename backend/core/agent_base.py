# core/agent_base.py


from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Dict, Any, AsyncGenerator, Optional
from dataclasses import dataclass


@dataclass
class AgentResponse:
    """Agent 响应"""
    content: str
    artifacts: List[Dict[str, Any]] = None
    metadata: Dict[str, Any] = None


class IAgent(ABC):
    """Agent 标准接口"""

    name: str
    capabilities: List[str]
    model: str
    timeout: int = 30

    @abstractmethod
    async def execute(
            self,
            task: str,
            context: Optional[Dict] = None
    ) -> AgentResponse:
        """执行任务（完整响应）"""
        pass

    @abstractmethod
    async def stream_execute(
            self,
            task: str,
            context: Optional[Dict] = None
    ) -> AsyncGenerator[str, None]:
        """流式执行（逐词输出）"""
        pass

    def get_spec(self):
        """返回 Agent 规范（用于 Orchestrator 分派）"""
        return {
            "id": self.name,
            "name": self.name,
            "capabilities": self.capabilities,
            "model": self.model,
            "timeout": self.timeout
        }