from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.orm import Session
from typing import List, Dict

from backend.app.dependencies import get_db, get_orchestrator
from backend.app.schemas import Message as MessageSchema, MessageCreate
from backend.services.conversation_service import ConversationService

router = APIRouter()


@router.get("/{conversation_id}/messages", response_model=List[MessageSchema])
async def get_messages(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """获取某个会话的所有消息"""
    conv_service = ConversationService(db)
    conversation = conv_service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="会话未找到")
    return conversation.messages


@router.post("/{conversation_id}/messages", response_model=MessageSchema)
async def send_message(
    conversation_id: int,
    message_in: MessageCreate,
    db: Session = Depends(get_db)
):
    """
    在指定会话中发送新消息，并触发 Orchestrator 工作流。
    Orchestrator 将负责处理记忆、执行任务并返回最终结果。
    """
    from sqlalchemy import inspect
    inspector = inspect(db.get_bind())
    tables = inspector.get_table_names()
    logger.info(f"[CHAT-API-DEBUG] send_message sees tables: {tables}")
    logger.info(f"[CHAT API] 收到向对话 {conversation_id} 发送新消息的请求。")
    logger.debug(f"[CHAT API] 请求体: {message_in.model_dump_json(indent=2)}")

    # 创建Orchestrator时传入数据库会话，让它能实时写入子Agent的消息
    orchestrator = get_orchestrator()
    # 如果是第一次设置db_session，就赋值
    if not hasattr(orchestrator, 'db_session') or orchestrator.db_session is None:
        orchestrator.db_session = db
    conv_service = ConversationService(db)

    # 1. 验证对话是否存在
    if not conv_service.get_conversation(conversation_id):
        logger.warning(f"[CHAT API] 对话 {conversation_id} 未找到。")
        raise HTTPException(status_code=404, detail="会话未找到")

    # 2. 将用户消息存入数据库
    # 这是必要的，以便前端可以立即显示用户的消息
    user_message = conv_service.add_message_to_conversation(
        conversation_id=conversation_id,
        agent_id="user",
        content=message_in.content
    )
    logger.info(f"[CHAT API] 用户消息已存入数据库，消息 ID: {user_message.id}。")

    # 3. 调用 Orchestrator 处理任务
    # 我们需要传递完整的消息历史，而不仅仅是当前内容
    logger.info(f"[CHAT API] 准备调用 Orchestrator...")
    try:
        # 获取完整的消息历史
        messages_history = conv_service.get_messages(conversation_id)
        logger.info(f"[CHAT API] 从数据库获取到 {len(messages_history)} 条历史消息")
        
        messages_for_orchestrator = [
            {"role": msg.agent_id, "content": msg.content} for msg in messages_history
        ]
        logger.info(f"[CHAT API] 传递给Orchestrator的消息: {messages_for_orchestrator}")

        final_state = await orchestrator.get_chat_response(
            conversation_id=conversation_id,
            messages=messages_for_orchestrator
        )
        logger.info("[CHAT API] 成功收到 Orchestrator 的响应。")
        logger.debug(f"[CHAT API] Orchestrator 最终状态类型: {type(final_state)}")
        logger.debug(f"[CHAT API] Orchestrator 最终状态: {final_state}")

    except Exception as e:
        logger.opt(exception=True).error("[CHAT API] 调用 Orchestrator 时发生严重错误，完整异常信息:")
        import traceback
        logger.error(f"[CHAT API] Stack trace: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error processing message with Orchestrator: {str(e)}")

    # 4. 将 Orchestrator 的响应存入数据库
    if final_state is None:
        logger.error("[CHAT API] Orchestrator 返回了 None!")
        return user_message
        
    if isinstance(final_state, dict) and "content" in final_state and "agent_id" in final_state:
        logger.info("[CHAT API] 正在将 Agent 的回复存入数据库...")
        agent_message = conv_service.add_message_to_conversation(
            conversation_id=conversation_id,
            agent_id=final_state["agent_id"],
            content=final_state["content"]
        )
        logger.success(f"[CHAT API] Agent 消息已成功存入数据库，消息 ID: {agent_message.id}。")
        return agent_message
    else:
        logger.warning("[CHAT API] Orchestrator 返回的格式不正确，不创建 Agent 消息。")
        if isinstance(final_state, dict):
            logger.warning(f"[CHAT API] final_state的所有键: {list(final_state.keys())}")
        logger.warning(f"[CHAT API] final_state 完整内容: {final_state}")
        return user_message