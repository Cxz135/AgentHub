import os
from typing import List, Dict, Any, Union
import openai
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage

from backend.agents.base_agent import BaseAgent, AgentResponse, FinalAnswer
from backend.models.message import Message
from backend.utils.logger import logger


class DeepSeekAdapter(BaseAgent):
    """
    一个适配器，用于调用 DeepSeek 的模型。
    它使用了与 OpenAI 兼容的 API 接口。
    """

    def __init__(self, agent_id: str, config: Dict[str, Any]):
        super().__init__(agent_id)
        try:
            api_key = os.environ.get("DEEPSEEK_API_KEY") or config.get("api_key")
            if not api_key:
                raise ValueError("DEEPSEEK_API_KEY 未设置。")

            self.client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com/v1"
            )
            self.model_name = config.get("model_name", "deepseek-coder")
        except Exception as e:
            logger.error(f"初始化 DeepSeekAdapter 失败: {e}")
            raise

    def _format_history(self, messages: List[Union[Message, BaseMessage]]) -> List[Dict[str, Any]]:
        """
        将混合的消息列表转换为 OpenAI API 的格式。
        能够同时处理自定义的 Message 对象和 LangChain 的 BaseMessage。
        """
        formatted = []
        for msg in messages:
            content = msg.content
            if isinstance(msg, HumanMessage):
                role = "user"
            elif isinstance(msg, AIMessage):
                role = "assistant"
            elif isinstance(msg, SystemMessage):
                role = "system"
            elif isinstance(msg, Message):
                # 兼容旧的 Message 对象
                role = "user" if not msg.agent_id or msg.agent_id == "user" else "assistant"
            else:
                # 对于无法识别的类型，记录一个警告并尝试将其视为用户消息
                logger.warning(f"收到无法识别的消息类型: {type(msg)}，将尝试作为用户消息处理。")
                role = "user"

            formatted.append({"role": role, "content": content})
        return formatted

    async def process_message(
        self,
        messages: List[Union[Message, BaseMessage]],
        context: Dict[str, Any] = None
    ) -> AgentResponse:
        """
        调用 DeepSeek API 并返回一个 Message 对象。
        """
        if not messages:
            return AgentResponse(final_answer=FinalAnswer(content="没有收到任何消息。"))

        # conversation_id 只有在 Message 对象中才有，这里可以安全地移除
        # conversation_id = messages[-1].conversation_id if isinstance(messages[-1], Message) else "N/A"
        formatted_history = self._format_history(messages)

        try:
            logger.info(f"向 DeepSeek ({self.model_name}) 发送请求...")

            chat_completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=formatted_history,
                max_tokens=2048,
                stream=False
            )

            response_content = chat_completion.choices[0].message.content
            logger.info("成功收到 DeepSeek 的回复。")
            logger.info(f"DeepSeek回复: {response_content}")
            return AgentResponse(final_answer=FinalAnswer(content=response_content))
        except Exception as e:
            logger.error(f"调用 DeepSeek API 时出错: {e}")
            error_message = f"抱歉，调用 DeepSeek API 时遇到错误: {e}"
            return AgentResponse(final_answer=FinalAnswer(content=error_message))

    async def process(self, messages: List[Message], context: Dict[str, Any] = None) -> Message:
        # 为满足抽象类要求提供的最小化实现
        pass

    @classmethod
    def from_config(cls, agent_id: str, config: Dict[str, Any]) -> "BaseAgent":
        return cls(agent_id=agent_id, config=config)