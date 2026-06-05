from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from loguru import logger
from sqlalchemy.orm import Session
from typing import List, Dict, Optional

from backend.app.dependencies import get_db, get_orchestrator
from backend.app.schemas import Message as MessageSchema, MessageCreate
from backend.app.api.auth import get_current_user
from backend.models.user import User as UserModel
from backend.services.conversation_service import ConversationService

router = APIRouter()

# 前端发送的聊天请求模型
class ChatRequest(BaseModel):
    message: str
    agent: Optional[Dict] = None
    mission: Optional[Dict] = None

# 简单的直接聊天接口，供前端调用
@router.post("")
async def simple_chat(
    chat_req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """简单的聊天接口，直接处理前端发送的消息（需登录），自动持久化消息到数据库"""
    logger.info(f"[SIMPLE-CHAT] 用户{current_user.id} 收到消息: {chat_req.message}")

    orchestrator = get_orchestrator()
    if not hasattr(orchestrator, 'db_session') or orchestrator.db_session is None:
        orchestrator.db_session = db

    conv_service = ConversationService(db)

    # 从 mission 中提取 conversation_id
    conversation_id = None
    if chat_req.mission and chat_req.mission.get('id'):
        try:
            mission_id = chat_req.mission['id']  # 格式 "mis_123"
            conversation_id = int(mission_id.replace('mis_', ''))
        except (ValueError, AttributeError):
            conversation_id = None

    # 如果有 mission 上下文，将用户消息持久化
    if conversation_id:
        conversation = conv_service.get_conversation(conversation_id)
        if conversation and conversation.user_id == current_user.id:
            conv_service.add_message_to_conversation(
                conversation_id=conversation_id,
                agent_id="user",
                content=chat_req.message
            )
            logger.info(f"[SIMPLE-CHAT] 用户消息已存入 conversation {conversation_id}")
        else:
            logger.warning(f"[SIMPLE-CHAT] 对话 {conversation_id} 不存在或不属于当前用户")
            conversation_id = None

    try:
        # 构建消息历史（包含历史消息 + 当前消息）
        all_messages = []
        if conversation_id:
            history = conv_service.get_messages(conversation_id)
            for msg in history:
                all_messages.append({"role": msg.agent_id, "content": msg.content})
        else:
            all_messages = [{"role": "user", "content": chat_req.message}]

        reply_content = None
        intermediate_messages = []
        if hasattr(orchestrator, 'get_chat_response'):
            temp_conv_id = conversation_id or 0
            response = await orchestrator.get_chat_response(
                conversation_id=temp_conv_id,
                messages=all_messages
            )
            if isinstance(response, dict) and "content" in response:
                reply_content = response["content"]
            # 检查是否包含中间消息（子Agent依次回复）
            if isinstance(response, dict) and "intermediate_messages" in response:
                intermediate_messages = response["intermediate_messages"]

        if reply_content is None:
            reply_content = f"你好！我收到了你的消息：'{chat_req.message}'。当前Agent: {chat_req.agent.get('name', '未知Agent') if chat_req.agent else '未指定Agent'}。"

        # 将 AI 回复持久化到数据库
        if conversation_id:
            agent_id = chat_req.agent.get('id', 'assistant') if chat_req.agent else 'assistant'
            conv_service.add_message_to_conversation(
                conversation_id=conversation_id,
                agent_id=agent_id,
                content=reply_content
            )
            logger.info(f"[SIMPLE-CHAT] AI 回复已存入 conversation {conversation_id}")

            # 如果有中间消息（子Agent依次回复），也存入数据库
            for msg in intermediate_messages:
                conv_service.add_message_to_conversation(
                    conversation_id=conversation_id,
                    agent_id=msg.get("agent_id", "agent"),
                    content=msg.get("content", "")
                )
                logger.info(f"[SIMPLE-CHAT] 中间消息已存入数据库，Agent: {msg.get('agent_id', 'agent')}")

        return {"ok": True, "reply": reply_content, "intermediate_messages": intermediate_messages}

    except Exception as e:
        logger.error(f"[SIMPLE-CHAT] 处理消息出错: {e}")
        return {"ok": False, "error": str(e), "reply": f"处理出错: {str(e)}"}


@router.get("/{conversation_id}/messages", response_model=List[MessageSchema])
async def get_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """获取某个会话的所有消息，仅限创建者"""
    conv_service = ConversationService(db)
    conversation = conv_service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="会话未找到")
    if conversation.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看其他用户的会话")
    return conversation.messages


@router.post("/{conversation_id}/messages", response_model=MessageSchema)
async def send_message(
    conversation_id: int,
    message_in: MessageCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    在指定会话中发送新消息，并触发 Orchestrator 工作流。
    仅限会话创建者操作。
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

    # 1. 验证对话是否存在且属于当前用户
    conversation = conv_service.get_conversation(conversation_id)
    if not conversation:
        logger.warning(f"[CHAT API] 对话 {conversation_id} 未找到。")
        raise HTTPException(status_code=404, detail="会话未找到")
    if conversation.user_id != current_user.id:
        logger.warning(f"[CHAT API] 用户{current_user.id} 无权访问对话 {conversation_id}")
        raise HTTPException(status_code=403, detail="无权访问其他用户的会话")

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

        # 先保存中间消息（子Agent依次回复），确保前端的消息顺序正确
        if "intermediate_messages" in final_state:
            for msg in final_state["intermediate_messages"]:
                conv_service.add_message_to_conversation(
                    conversation_id=conversation_id,
                    agent_id=msg.get("agent_id", "agent"),
                    content=msg.get("content", "")
                )
                logger.info(f"[CHAT API] 中间消息已存入数据库，Agent: {msg.get('agent_id', 'agent')}")

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