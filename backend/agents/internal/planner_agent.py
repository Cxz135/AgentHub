import json
import re
from typing import List, Dict, Any

from loguru import logger
from backend.models.message import Message
from backend.agents.base_agent import BaseAgent, AgentResponse, FinalAnswer
from backend.llm.backend import LLMBackend

# 定义新的系统提示词模板，指导 LLM 生成带依赖关系的计划
SYSTEM_PROMPT_TEMPLATE = """【重要】你必须始终使用中文回复，不得切换到其他语言。

你是一个任务规划器。根据用户需求，将任务拆解为子任务列表，每个子任务包含以下字段（JSON数组格式）：

[
  {{
    "step_id": "1",
    "agent_id": "可用的agent_id",
    "prompt": "下发给子Agent的精确指令（要求具体，包含约束条件）",
    "expectations": {{
      "pass": "及格标准",
      "standard": "期望标准",
      "excellent": "优异标准（可选）"
    }},
    "output_format": "期望的输出格式",
    "max_retries": 2,
    "dependencies": []       // 依赖的前置step_id，如["0"]
  }}
]

规则：
1. 可用 agent: {available_agents}
2. {skills_prompt}
   如果任务需要调用工具，必须在子任务的prompt中明确告诉执行agent使用哪个技能，格式为"SKILL_CALL: skill_name method params"
3. 如果子任务需要前面任务的结果，必须在 dependencies 中标明。
4. prompt 应自包含，但可以引用黑板上下文（如"根据之前的查询结果..."），上下文会自动注入。
5. 仅有独立、可并行的任务才不用填写 dependencies。
{history_context}
"""


class PlannerAgent(BaseAgent):
    """
    内部 Planner Agent：将复杂任务分解为带依赖关系的结构化步骤。
    使用 LLMBackend 进行 LLM 调用。
    """

    def __init__(self, backend: LLMBackend):
        super().__init__("planner")
        self.backend = backend

    def _parse_plan_from_response(self, response_str: str) -> List[Dict[str, Any]]:
        """
        从 LLM 的响应字符串中解析出计划，增强了日志和错误处理。
        """
        logger.debug(f"开始解析 LLM 响应，原始文本长度: {len(response_str)}。")
        json_str = ""
        try:
            # 使用正则表达式精确查找 JSON 代码块，以应对 LLM 可能返回的额外文本
            match = re.search(r"```json\n(.*?)\n```", response_str, re.DOTALL)
            if not match:
                logger.warning(f"响应中未找到 ```json 代码块，将尝试直接解析整个响应。")
                # 尝试直接解析，以兼容没有代码块但内容是合法 JSON 的情况
                json_str = response_str.strip()
            else:
                logger.info("在响应中成功匹配到 ```json 代码块。")
                json_str = match.group(1).strip()

            plan = json.loads(json_str)
            logger.success(f"成功将响应解析为 JSON，共包含 {len(plan)} 个步骤。")

            # TODO: 在这里可以添加对计划格式的严格校验 (e.g., using Pydantic)
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

        # 从上下文中获取可用的 Agent 列表，并格式化
        available_agents = context.get("available_agents", [])
        if not available_agents:
            logger.error("错误：PlannerAgent 未在上下文中收到 available_agents = list(orchestrator.agents.keys()")
        agent_list_str = "\n".join([f"- {agent_id}" for agent_id in available_agents])
        # 从context中获取技能列表，和available_agents一样通过参数传入，解耦orchestrator依赖
        skills_prompt = context.get("available_skills_prompt", "暂无可用技能")
        # 注入历史摘要到planner的prompt
        historical_summary = context.get("historical_summary", "")
        history_context = f"\n历史对话摘要：{historical_summary}" if historical_summary else "\n暂无历史对话摘要"
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            available_agents=agent_list_str, 
            skills_prompt=skills_prompt,
            history_context=history_context
        )

        # 构建发送给 LLM 的消息，注入动态生成的系统提示词
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": latest_user_message}
        ]
        logger.debug(f"构建的 LLM 输入消息: {llm_messages}")
        logger.info("🤖 正在调用大模型生成行动计划...")

        # 调用 LLM 生成计划
        try:
            llm_response_str = await self.backend.chat(llm_messages)
            logger.info("✅ 成功从大模型收到响应。")
            logger.debug(f"LLM 原始响应内容:\n---\n{llm_response_str}\n---")
        except Exception as e:
            logger.opt(exception=True).error("调用大模型时发生严重错误。")
            return AgentResponse(final_answer=FinalAnswer(content="[]"))


        # 解析计划
        logger.info("🧩 正在解析大模型返回的计划...")
        plan = self._parse_plan_from_response(llm_response_str)

        if not plan:
            logger.error("❌ 计划解析失败，返回空计划。")
            return AgentResponse(final_answer=FinalAnswer(content="[]"))

        # 将解析后的、格式化的计划包装在 AgentResponse 中返回
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