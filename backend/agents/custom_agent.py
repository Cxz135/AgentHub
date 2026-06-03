from typing import List, Dict, Any, Union
from langchain_core.messages import SystemMessage, BaseMessage

from backend.agents.base_agent import BaseAgent, AgentResponse, FinalAnswer
from backend.models.message import Message
from backend.utils.logger import logger


class CustomAgent(BaseAgent):
    """
    一个通用的、可配置的 Agent 执行器。
    它的行为由传入的 system_prompt 和一个底层的 LLM Adapter 决定。
    这个类本身不包含任何具体的业务逻辑，它只负责根据配置调用 LLM。
    """

    def __init__(self, agent_id: str, system_prompt: str, llm_adapter: BaseAgent):
        """
        初始化 CustomAgent。

        Args:
            agent_id: 此自定义 Agent 的唯一标识符。
            system_prompt: 定义此 Agent 角色和行为的系统提示词。
            llm_adapter: 一个具体的 LLM 适配器实例 (如 DeepSeekAdapter), 用于实际调用 LLM。
        """
        super().__init__(agent_id)
        self.system_prompt = system_prompt
        self.llm_adapter = llm_adapter
        logger.info(f"通用 Agent '{self.agent_id}' 已创建，使用适配器: {self.llm_adapter.__class__.__name__}")

    async def process(self, messages: List[Message], context: Dict[str, Any] = None) -> Message:
        # 为满足抽象类要求提供的最小化实现
        # 这个 Agent 的核心逻辑在 process_message 中
        pass

    async def process_message(
            self,
            messages: List[Union[Message, BaseMessage]],
            context: Dict[str, Any] = None
    ) -> AgentResponse:
        """
        处理消息的核心逻辑。

        1. 将 system_prompt 添加到消息历史的开头。
        2. 调用底层的 llm_adapter 来获取回复。
        3. 返回一个标准的 AgentResponse。
        """
        if not self.llm_adapter:
            error_msg = f"CustomAgent '{self.agent_id}' 没有配置 LLM 适配器。"
            logger.error(error_msg)
            return AgentResponse(final_answer=FinalAnswer(content=error_msg))

        # 构造带有系统提示词的新消息列表
        # 我们创建一个新列表，以避免修改原始的 state
        system_message = SystemMessage(content=self.system_prompt)
        # 将系统消息放在最前面
        full_messages = [system_message] + messages

        logger.debug(f"CustomAgent '{self.agent_id}' 正在使用其 system_prompt 调用底层适配器。")

        # 使用注入的 llm_adapter 来处理完整的消息列表
        # CustomAgent 将自己的身份和行为(system_prompt)委托给了底层适配器来执行
        return await self.llm_adapter.process_message(full_messages, context)

    @classmethod
    def from_config(cls, agent_id: str, config: Dict[str, Any], llm_adapter: BaseAgent) -> "CustomAgent":
        """
        一个工厂方法，用于从配置字典和适配器实例创建 CustomAgent。
        """
        system_prompt = config.get("system_prompt", "你是一个乐于助人的AI助手。")
        return cls(agent_id=agent_id, system_prompt=system_prompt, llm_adapter=llm_adapter)