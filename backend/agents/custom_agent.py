from typing import List, Dict, Any, Union, Optional

from backend.agents.base_agent import BaseAgent, AgentResponse, FinalAnswer
from backend.llm.backend import LLMBackend
from backend.utils.logger import logger


class CustomAgent(BaseAgent):
    """
    可配置的通用 Agent。
    行为由 system_prompt + LLMBackend 决定，不再包装另一个 Agent。
    """

    def __init__(
        self,
        agent_id: str,
        system_prompt: str,
        llm_backend: LLMBackend,
        name: str = None,
        validation_config: dict = None,
    ):
        super().__init__(agent_id)
        self.name = name or agent_id
        self.system_prompt = system_prompt
        self.backend = llm_backend
        self.validation_config = validation_config or {}
        logger.info(
            f"CustomAgent '{self.agent_id}' 已创建，后端: {self.backend.provider}/{self.backend.model_name}, validation_config={self.validation_config}"
        )

    async def process_message(
        self,
        messages: List[Any],
        context: Dict[str, Any] = None,
    ) -> AgentResponse:
        if not self.backend or not self.backend.api_key_status:
            error_msg = f"CustomAgent '{self.agent_id}' 的 LLM 后端未正确配置。"
            logger.error(error_msg)
            return AgentResponse(final_answer=FinalAnswer(content=error_msg))

        # 构造完整的消息列表：system prompt + 历史消息
        full_messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        for m in messages:
            if hasattr(m, "role") and hasattr(m, "content"):
                full_messages.append({"role": m.role, "content": m.content})
            elif hasattr(m, "agent_id") and hasattr(m, "content"):
                role = "user" if m.agent_id == "user" else "assistant"
                full_messages.append({"role": role, "content": m.content})
            elif isinstance(m, dict) and "role" in m and "content" in m:
                full_messages.append(m)
            else:
                full_messages.append({"role": "user", "content": str(m)})

        logger.debug(f"CustomAgent '{self.agent_id}' 调用后端 {self.backend.provider}")
        try:
            content = await self.backend.chat(full_messages)
            return AgentResponse(final_answer=FinalAnswer(content=content))
        except Exception as e:
            logger.error(f"CustomAgent '{self.agent_id}' 调用失败: {e}")
            return AgentResponse(
                final_answer=FinalAnswer(content=f"处理消息时出错: {e}")
            )

    @classmethod
    def from_config(
        cls,
        agent_id: str,
        system_prompt: str,
        llm_backend: LLMBackend,
        name: str = None,
    ) -> "CustomAgent":
        return cls(
            agent_id=agent_id,
            system_prompt=system_prompt,
            llm_backend=llm_backend,
            name=name,
        )