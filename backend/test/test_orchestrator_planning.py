import pytest
from backend.core.orchestrator import Orchestrator
from backend.models.conversation import Conversation

# 标记整个模块为异步测试
pytestmark = pytest.mark.asyncio

async def test_orchestrator_planning_flow(db_session):
    """
    测试 Orchestrator 在接收到 /plan 指令时，是否能成功执行完整的规划、
    执行和总结流程。
    """
    orchestrator = Orchestrator()
    
    conversation = Conversation(title="规划流程测试")
    db_session.add(conversation)
    db_session.commit()
    conversation_id = str(conversation.id)
    task_content = "/plan 请帮我写一个 FastAPI 的 hello world 应用，并对代码进行审查。"

    messages = [{"role": "user", "content": task_content}]

    final_state = await orchestrator.get_chat_response(
        conversation_id=conversation_id,
        messages=messages
    )

    final_summary = final_state.get("content")
    assert final_summary is not None, "最终状态应包含 content"
    assert "计划执行总结" in final_summary, "返回内容应包含'计划执行总结'字样"
    assert "✅ **步骤 1 (tongyi)**" in final_summary, "总结应包含步骤1 (tongyi) 成功的信息"
    assert "✅ **步骤 2 (deepseek)**" in final_summary, "总结应包含步骤2 (deepseek) 成功的信息"
    assert "FastAPI" in final_summary, "总结应包含任务相关内容"


async def test_orchestrator_empty_task_content():
    """
    测试当用户只输入 /plan 而没有提供具体任务时，Orchestrator 是否能正确处理。
    """
    orchestrator = Orchestrator()
    conversation_id = "test_empty_task_456"
    task_content = "/plan  "  # 空或只包含空格的内容
    messages = [{"role": "user", "content": task_content}]

    final_state = await orchestrator.get_chat_response(
        conversation_id=conversation_id,
        messages=messages
    )
    
    final_summary = final_state.get("content")
    assert "请输入需要规划的具体任务" in final_summary


async def test_orchestrator_simple_task(db_session):
    """
    测试 Orchestrator 处理一个简单的、非指令的聊天消息。
    """
    orchestrator = Orchestrator()
    
    conversation = Conversation(title="简单任务测试")
    db_session.add(conversation)
    db_session.commit()
    conversation_id = str(conversation.id)
    task_content = "你好，你是谁？"
    messages = [{"role": "user", "content": task_content}]

    final_state = await orchestrator.get_chat_response(
        conversation_id=conversation_id,
        messages=messages
    )

    final_summary = final_state.get("content")
    assert final_summary is not None
    # 默认应该由主聊天 Agent (tongyi) 回复
    assert len(final_summary) > 0
    assert final_state.get("agent_id") == "tongyi"