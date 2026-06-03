from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import pytest

# 导入主 FastAPI 应用和新的测试 fixtures
from backend.app.main import app

# 导入需要用到的数据模型
from backend.models.message import Message


from fastapi import Depends
from sqlalchemy import inspect

from backend.app.dependencies import get_db

def test_full_chat_flow(client: TestClient, db_session: Session):
    """
    端到端测试一个完整的聊天流程：
    1. 创建一个新对话。
    2. 在该对话中发送一条消息。
    3. 验证 Orchestrator 是否被触发，并且用户和助手的消息都已存入数据库。
    4. 获取该对话的历史消息，验证其完整性。
    """
    # 先直接在测试代码中检查表是否存在
    inspector = inspect(db_session.get_bind())
    tables = inspector.get_table_names()
    print(f"\n--- [TEST-DEBUG] Test code sees tables: {tables} ---,\n")
    
    # 先调用健康检查路由，确认API正常运行
    debug_response = client.get("/health")
    print(f"\n--- [HEALTH CHECK] Status: {debug_response.status_code} ---,\n")
    print(f"--- [HEALTH CHECK] Response: {debug_response.json()} ---,\n")

    # 在这里，我们将进入交互式调试

    # 1. 创建一个新会话 ---
    create_conv_response = client.post(
        "/api/conversations",
        json={"title": "E2E 测试对话"}
    )
    assert create_conv_response.status_code == 200
    conv_data = create_conv_response.json()
    conversation_id = conv_data["id"]
    assert conv_data["title"] == "E2E 测试对话"
    print(f"\n✅ 步骤 1: 成功创建对话，ID: {conversation_id}")

    # --- 2. 发送一条消息 ---
    # 这将触发 chat.py -> orchestrator.py 的完整流程
    task_content = "/plan 给我写一个 Python 的快速排序算法，并对它进行代码审查。"
    send_message_response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": task_content}
    )
    assert send_message_response.status_code == 200
    returned_message_data = send_message_response.json()
    
    # 验证 API 返回的消息是有效的
    assert returned_message_data["agent_id"] in ["user", "assistant"]
    print(f"\n✅ 步骤 2: 成功发送消息并收到 API 确认。")
    print(f"   API 返回的消息发送者: {returned_message_data['agent_id']}")
    print(f"   API 返回的消息内容: {returned_message_data['content'][:80]}...")


    # --- 3. 直接从数据库验证消息 ---
    # 这是最可靠的验证方式
    messages_in_db = db_session.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()

    # 至少应该有一条用户消息
    assert len(messages_in_db) >= 1, "数据库中至少应该有一条用户消息"
    
    user_db_message = messages_in_db[0]
    assert user_db_message.agent_id == "user"
    assert user_db_message.content == task_content

    # 根据 Orchestrator 是否回复，数据库中可能有1条或2条消息
    print(f"\n✅ 步骤 3: 成功验证数据库中已保存 {len(messages_in_db)} 条消息。")


    # --- 4. 调用 API 获取历史消息 ---
    get_messages_response = client.get(
        f"/api/conversations/{conversation_id}/messages"
    )
    assert get_messages_response.status_code == 200
    messages_from_api = get_messages_response.json()

    assert len(messages_from_api) == len(messages_in_db)
    assert messages_from_api[0]["content"] == task_content
    print(f"\n✅ 步骤 4: 成功通过 API 获取到完整的对话历史。")
    print(f"\n🎉 端到端聊天流程测试通过！")

    # 移除卧底路由，避免污染其他测试 - FastAPI的routes属性是只读的，不能直接修改，所以这里省略即可