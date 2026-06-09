import json
import re
from typing import List, Dict, Any

from loguru import logger
from backend.models.message import Message
from backend.agents.base_agent import BaseAgent, AgentResponse, FinalAnswer
from backend.llm.backend import LLMBackend
from backend.config.prompts import get_prompt_loader


class PlannerAgent(BaseAgent):
    """
    内部 Planner Agent：将复杂任务分解为带依赖关系的结构化步骤。
    使用 LLMBackend 进行 LLM 调用。
    """

    def __init__(self, backend: LLMBackend):
        super().__init__("planner")
        self.backend = backend
        self.prompt_loader = get_prompt_loader()

    def _parse_plan_from_response(self, response_str: str) -> List[Dict[str, Any]]:
        """
        从 LLM 的响应字符串中解析出计划，增强了日志和错误处理。
        """
        logger.debug(f"开始解析 LLM 响应，原始文本长度: {len(response_str)}。")
        json_str = ""
        try:
            match = re.search(r"```json\n(.*?)\n```", response_str, re.DOTALL)
            if not match:
                logger.warning(f"响应中未找到 ```json 代码块，将尝试直接解析整个响应。")
                json_str = response_str.strip()
            else:
                logger.info("在响应中成功匹配到 ```json 代码块。")
                json_str = match.group(1).strip()

            plan = json.loads(json_str)
            logger.success(f"成功将响应解析为 JSON，共包含 {len(plan)} 个步骤。")

            return plan

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}。失败的文本: '...{json_str[-200:]}'")
            logger.error(f"完整的原始 LLM 响应: \n---\n{response_str}\n---")
            return []
        except Exception as e:
            logger.opt(exception=True).error(f"解析计划时发生未知错误。")
            logger.error(f"完整的原始 LLM 响应: \n---\n{response_str}\n---")
            return []

    async def process_message(self, messages: List[Message], context: Dict[str, Any] = None) -> AgentResponse:
        """
        接收用户任务，调用 LLM 生成一个 JSON 格式的、带依赖关系的计划。
        """
        logger.info("🚀 PlannerAgent 开始执行任务规划...")
        if not messages:
            logger.error("错误：PlannerAgent 收到的消息列表为空。")
            return AgentResponse(final_answer=FinalAnswer(content="[]"))

        latest_user_message = messages[-1].content
        logger.info(f"🎯 正在分析用户最新请求: '{latest_user_message}'")

        available_agents = context.get("available_agents", [])
        if not available_agents:
            logger.error("错误：PlannerAgent 未在上下文中收到 available_agents = list(orchestrator.agents.keys()")
        agent_list_str = "\n".join([f"- {agent_id}" for agent_id in available_agents])
        skills_prompt = context.get("available_skills_prompt", "暂无可用技能")
        historical_summary = context.get("historical_summary", "")
        history_context = f"\n历史对话摘要：{historical_summary}" if historical_summary else "\n暂无历史对话摘要"

        system_prompt = self.prompt_loader.get('agent', 'planner_system',
            available_agents=agent_list_str,
            skills_prompt=skills_prompt,
            history_context=history_context
        )

        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": latest_user_message}
        ]
        logger.debug(f"构建的 LLM 输入消息: {llm_messages}")
        logger.info("🤖 正在调用大模型生成行动计划...")

        try:
            llm_response_str = await self.backend.chat(llm_messages)
            logger.info("✅ 成功从大模型收到响应。")
            logger.debug(f"LLM 原始响应内容:\n---\n{llm_response_str}\n---")
        except Exception as e:
            logger.opt(exception=True).error("调用大模型时发生严重错误。")
            return AgentResponse(final_answer=FinalAnswer(content="[]"))

        logger.info("🧩 正在解析大模型返回的计划...")
        plan = self._parse_plan_from_response(llm_response_str)

        if not plan:
            logger.error("❌ 计划解析失败，返回空计划。")
            return AgentResponse(final_answer=FinalAnswer(content="[]"))

        logger.success(f"🎉 成功生成并解析行动计划，共 {len(plan)} 个步骤。")
        return AgentResponse(
            final_answer=FinalAnswer(content=json.dumps(plan, ensure_ascii=False, indent=2))
        )

    async def process(self, messages: List[Message], context: Dict[str, Any] = None) -> Message:
        """
        一个兼容旧接口或用于直接返回 Message 对象的备用方法。
        """
        response = await self.process_message(messages, context)
        return Message(
            conversation_id=messages[-1].conversation_id,
            agent_id=self.agent_id,
            content=response.final_answer.content
        )