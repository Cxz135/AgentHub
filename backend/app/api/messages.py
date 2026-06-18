# app/api/messages.py
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.app.schemas import Message as MessageSchema, MessageOperation
from backend.app.dependencies import get_db, get_orchestrator
from backend.models.message import Message as MessageModel, parse_message_content, create_message_content
from backend.models.conversation import Conversation as ConversationModel
from backend.app.api.auth import get_current_user
from backend.models.user import User as UserModel
from backend.utils.logger import logger

router = APIRouter()

class QuoteRequest(BaseModel):
    target_conversation_id: Optional[int] = None


@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageSchema])
async def get_messages_for_conversation(
        conversation_id: int,
        db: Session = Depends(get_db),
        current_user: UserModel = Depends(get_current_user)
):
    """
    获取指定对话的所有历史消息，仅限对话创建者。
    """
    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == conversation_id,
        ConversationModel.user_id == current_user.id
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")

    messages = db.query(MessageModel).filter(
        MessageModel.conversation_id == conversation_id
    ).order_by(MessageModel.created_at.asc()).all()

    logger.info(f"✅ 用户{current_user.id} 为对话 {conversation_id} 检索到 {len(messages)} 条消息。")

    return messages


@router.post("/conversations/{conversation_id}/messages/{message_id}/regenerate")
async def regenerate_message(
        conversation_id: int,
        message_id: int,
        db: Session = Depends(get_db),
        current_user: UserModel = Depends(get_current_user)
):
    """
    重新生成指定消息（仅限 assistant 发送的 AI 消息）。
    会删除原消息，重新调用 orchestrator 生成新消息。
    """
    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == conversation_id,
        ConversationModel.user_id == current_user.id
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")

    message = db.query(MessageModel).filter(
        MessageModel.id == message_id,
        MessageModel.conversation_id == conversation_id
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    if message.agent_id not in ("assistant", "orchestrator") and not message.agent_id.startswith("agent_"):
        raise HTTPException(status_code=400, detail="只能重新生成 AI 消息")

    original_index = message.id

    from backend.services.conversation_service import ConversationService
    conv_service = ConversationService(db)

    history = []
    for msg in conv_service.get_messages(conversation_id):
        if msg.id == message_id:
            continue
        history.append({"role": msg.agent_id, "content": msg.content})

    orchestrator = get_orchestrator()
    if not hasattr(orchestrator, 'db_session') or orchestrator.db_session is None:
        orchestrator.db_session = db

    request_context = {
        "current_user_id": current_user.id,
        "active_skills": []
    }

    new_content = None
    try:
        async for chunk in orchestrator.get_chat_stream(
            conversation_id=conversation_id,
            messages=history,
            request_context=request_context
        ):
            if chunk.get("type") == "final":
                new_content = chunk.get("content", "")
                break
            elif chunk.get("type") == "token":
                new_content = (new_content or "") + chunk.get("content", "")
    except Exception as e:
        logger.error(f"重新生成消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新生成失败: {str(e)}")

    if new_content:
        db.delete(message)
        db.commit()

        new_message = conv_service.add_message_to_conversation(
            conversation_id=conversation_id,
            agent_id="assistant",
            content=new_content
        )

        logger.info(f"🔄 用户{current_user.id} 重新生成了消息 {original_index} -> {new_message.id}")

        return {
            "ok": True,
            "old_message_id": original_index,
            "new_message_id": new_message.id,
            "content": new_content
        }

    raise HTTPException(status_code=500, detail="未能生成新内容")


@router.post("/conversations/{conversation_id}/messages/{message_id}/pin")
async def toggle_message_pin(
        conversation_id: int,
        message_id: int,
        db: Session = Depends(get_db),
        current_user: UserModel = Depends(get_current_user)
):
    """
    切换消息置顶状态
    """
    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == conversation_id,
        ConversationModel.user_id == current_user.id
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")

    message = db.query(MessageModel).filter(
        MessageModel.id == message_id,
        MessageModel.conversation_id == conversation_id
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    message.is_pinned = not message.is_pinned
    db.commit()

    return {"ok": True, "is_pinned": message.is_pinned}


@router.get("/messages/{message_id}/content")
async def get_message_content(
        message_id: int,
        db: Session = Depends(get_db),
        current_user: UserModel = Depends(get_current_user)
):
    """
    获取消息的完整内容，用于展开预览/复制等操作。
    返回解析后的结构化内容。
    """
    message = db.query(MessageModel).filter(
        MessageModel.id == message_id
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == message.conversation_id,
        ConversationModel.user_id == current_user.id
    ).first()
    if not conversation:
        raise HTTPException(status_code=403, detail="无权访问此消息")

    parsed = parse_message_content(message.content)

    return {
        "ok": True,
        "message_id": message_id,
        "type": parsed.get("type", "text"),
        "content": parsed.get("content", ""),
        "metadata": parsed.get("metadata", {}),
        "agent_id": message.agent_id,
        "is_pinned": message.is_pinned,
        "created_at": message.created_at.isoformat() if message.created_at else None
    }


@router.post("/messages/{message_id}/quote")
async def quote_message(
        message_id: int,
        quote_req: QuoteRequest = Body(...),
        db: Session = Depends(get_db),
        current_user: UserModel = Depends(get_current_user)
):
    """
    引用某条消息，在新对话中创建引用内容。
    返回可用于插入到输入框的引用格式。
    """
    message = db.query(MessageModel).filter(
        MessageModel.id == message_id
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == message.conversation_id,
        ConversationModel.user_id == current_user.id
    ).first()
    if not conversation:
        raise HTTPException(status_code=403, detail="无权访问此消息")

    parsed = parse_message_content(message.content)
    content = parsed.get("content", "")

    from backend.models.message import create_quoted_content
    quote_data = create_quoted_content(
        original_message_id=message_id,
        original_agent_id=message.agent_id,
        original_content=content
    )

    return {
        "ok": True,
        "quote": quote_data,
        "display": f"@{message.agent_id}: {content[:80]}{'...' if len(content) > 80 else ''}"
    }