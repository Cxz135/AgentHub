import json
from typing import List, Dict, Any, Union

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from backend.agents.base_agent import BaseAgent
from backend.core.agent_protocol import AgentResponse, FinalAnswer
from backend.llm.backend import LLMBackend
from backend.models.message import Message
from backend.utils.logger import logger
from backend.config.prompts import get_prompt_loader


class SummarizerAgent(BaseAgent):
    """
    内部摘要 Agent：将对话历史压缩为简洁摘要。
    使用 LLMBackend 进行 LLM 调用。
    """

    def __init__(self, backend: LLMBackend):
        super().__init__("summarizer")
        self.backend = backend
        self.prompt_loader = get_prompt_loader()

    async def process(self, messages: List[Message], context: Dict[str, Any] = None) -> Message:
        # 为满足抽象类要求提供的最小化实现
        # 这个 Agent 的核心逻辑在 process_message 中，由 langgraph 直接调用
        pass

    async def process_message(
            self,
            messages: List[Union[Message, BaseMessage]],
            context: Dict[str, Any] = None
    ) -> AgentResponse:
        """
        接收对话历史，生成一段简洁的摘要。
        能够处理多种消息类型。
        """
        # 1. 准备用于摘要的提示词
        history_lines = []
        for m in messages:
            if isinstance(m, HumanMessage):
                role = "用户"
                content = m.content
            elif isinstance(m, AIMessage):
                role = "助手"
                content = m.content
            elif isinstance(m, Message):
                role = "用户" if not m.agent_id or m.agent_id == "user" else "助手"
                content = m.content
            else:
                logger.warning(f"SummarizerAgent 收到未知消息类型: {type(m)}，将忽略此消息。")
                continue
            history_lines.append(f"{role}: {content}")

        history_text = "\n".join(history_lines)

        # 如果 messages 列表只包含一个 HumanMessage，通常意味着它不是一个对话历史，
        # 而是直接传递过来的、需要处理的文本内容。在这种情况下，我们直接使用其内容。
        if len(messages) == 1 and isinstance(messages[0], HumanMessage):
            system_prompt = self.prompt_loader.get('agent', 'summarizer_single_message')
            prompt = messages[0].content
        else:
            system_prompt = self.prompt_loader.get('agent', 'summarizer_chat_history')
            prompt = self.prompt_loader.get('agent', 'summarizer_prompt', history_text=history_text)

        # 2. 调用大模型生成摘要
        try:
            logger.info("调用 SummarizerAgent 生成对话摘要...")
            response = await self.backend.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ])
            summary_content = response
            logger.info(f"成功生成摘要: {summary_content}")
            return AgentResponse(final_answer=FinalAnswer(content=summary_content))

        except Exception as e:
            logger.error(f"SummarizerAgent 在生成摘要时出错: {e}", exc_info=True)
            error_message = f"生成摘要时出错: {e}"
            return AgentResponse(final_answer=FinalAnswer(content=error_message))