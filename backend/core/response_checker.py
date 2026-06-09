"""
响应完整性检查器：Agent 生成回复后，自动判断是否需要追问用户补充信息。

触发场景：
  - Agent 回复太模糊、不完整、存在多种解释
  - 用户请求涉及具体数字/日期/名称但 Agent 没有提供
  - Agent 需要用户确认某个关键假设

返回：
  - needs_clarification: bool
  - questions: List[str]  # 追问问题列表
  - reason: str          # 判断理由
"""

from typing import List
from backend.utils.logger import logger

RESPONSE_CHECK_PROMPT = """【重要】你必须始终使用中文回复，不得切换到其他语言。

你是一个响应质量审查员。请判断以下 Agent 回复是否完整、足够回答用户问题。

用户问题：{user_question}

Agent 回复：
---
{agent_response}
---

判断标准（满足任一即认为需要追问）：
1. 回复中有"不确定"、"取决于"、"可能"等模糊表述，且影响核心答案
2. 回复缺少用户问的具体要素（数字、日期、人名、具体步骤等）
3. 用户问题可以有多种解释，但 Agent 只选了一种未说明
4. Agent 遗漏了用户明确要求的内容（如"帮我写代码"但只给了思路）
5. 回复依赖某个未提及的假设（如"假设你使用的是 Python 3"）

请严格按以下 JSON 格式输出，不要输出其他内容：
{{
  "needs_clarification": true或false,
  "reason": "判断理由（中文，30字以内）",
  "questions": ["追问问题1", "追问问题2"]  // 如果不需要追问则为空数组
}}"""


async def check_response_completeness(
    user_question: str,
    agent_response: str,
    llm_backend,
) -> dict:
    """
    检查 Agent 回复是否完整，必要时返回追问问题。

    Args:
        user_question: 用户的原始问题
        agent_response: Agent 的回复内容
        llm_backend: LLM 后端（用于调用检查器）

    Returns:
        dict: {needs_clarification: bool, reason: str, questions: List[str]}
    """
    if not agent_response or len(agent_response.strip()) < 5:
        return {
            "needs_clarification": True,
            "reason": "回复内容过短，可能不完整",
            "questions": ["您能提供更多背景信息吗？这样我可以给出更准确的答案。"]
        }

    try:
        prompt = RESPONSE_CHECK_PROMPT.format(
            user_question=user_question[:500],
            agent_response=agent_response[:1000]
        )
        result = await llm_backend.chat([
            {"role": "user", "content": prompt}
        ])

        import json, re
        # 尝试从结果中提取 JSON
        match = re.search(r'\{[\s\S]*\}', result)
        if match:
            parsed = json.loads(match.group())
            needs = bool(parsed.get("needs_clarification", False))
            questions = parsed.get("questions", [])
            reason = parsed.get("reason", "")
            # 限制最多 3 个问题
            if isinstance(questions, list):
                questions = questions[:3]
            return {
                "needs_clarification": needs,
                "reason": reason,
                "questions": questions
            }
    except Exception as e:
        logger.warning(f"[RESPONSE-CHECK] 检查失败，降级为不追问: {e}")

    return {"needs_clarification": False, "reason": "", "questions": []}


def build_clarification_response(questions: List[str], original_content: str) -> str:
    """
    将追问问题格式化为 Agent 回复。
    放在原回复前面，引导用户补充信息。
    """
    if not questions:
        return original_content

    intro = "为了给出更准确的答案，我需要确认几个问题：\n\n"
    question_items = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
    return intro + question_items + "\n\n---\n\n**我的初步回答（待您补充信息后完善）：**\n\n" + original_content[:500]