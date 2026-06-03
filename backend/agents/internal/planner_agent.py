import json
import re
from typing import List, Dict, Any

from loguru import logger

from backend.agents.base_agent import BaseAgent, AgentResponse, FinalAnswer
from backend.models.message import Message

# 定义新的系统提示词模板，指导 LLM 生成带依赖关系的计划
SYSTEM_PROMPT_TEMPLATE = """
你是一个 AI 项目规划师。你的任务是将一个复杂的用户请求拆解成一个由多个步骤组成的执行计划。
你需要识别任务之间的依赖关系，以便它们可以被并行执行。

**你必须从以下可用 Agent 列表中选择执行每个步骤的 Agent:**
{available_agents}

请根据用户的请求，输出一个 JSON 格式的执行计划。
这个计划是一个列表，列表中的每个对象代表一个步骤。

每个步骤对象必须包含以下字段:
- "step_id": 一个唯一的整数，从 1 开始。
- "agent_id": 执行此步骤的 Agent 的 ID。
- "prompt": 指向该 Agent 的具体指令。
- "dependencies": 一个列表，包含此步骤所依赖的所有前置步骤的 "step_id"。如果一个步骤没有依赖，请使用一个空列表 `[]`。

**示例格式:**
```json
[
  {{
    "step_id": 1,
    "agent_id": "tongyi",
    "prompt": "写一个 Python 函数，实现斐波那契数列。",
    "dependencies": []
  }},
  {{
    "step_id": 2,
    "agent_id": "deepseek",
    "prompt": "审查步骤 1 中生成的斐波那契函数代码。",
    "dependencies": [1]
  }}
]
```

现在，请根据用户的请求生成计划。
"""


class PlannerAgent(BaseAgent):
    """
    一个内部 Agent，专门负责将用户的复杂任务分解为结构化的、可执行的步骤。
    它的核心逻辑是调用其持有的 LLM 来生成计划。
    """

    def __init__(self, model: Any):
        super().__init__("planner")
        self.model = model

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
            logger.error("错误：PlannerAgent 未在上下文中收到 available_agents 列表。")
            return AgentResponse(final_answer=FinalAnswer(content="[]"))

        agent_list_str = "\n".join([f"- {agent_id}" for agent_id in available_agents])
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(available_agents=agent_list_str)

        # 构建发送给 LLM 的消息，注入动态生成的系统提示词
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": latest_user_message}
        ]
        logger.debug(f"构建的 LLM 输入消息: {llm_messages}")
        logger.info("🤖 正在调用大模型生成行动计划...")

        # 调用 LLM 生成计划
        try:
            llm_response_str = await self.model.invoke(llm_messages)
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