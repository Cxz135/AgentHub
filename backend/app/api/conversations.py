# app/api/conversations.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.schemas import ConversationCreate, Conversation
from backend.app.dependencies import get_db
from backend.models.conversation import Conversation as ConversationModel
from backend.utils.logger import logger
import uuid

router = APIRouter()

@router.post("", response_model=Conversation)
async def create_conversation(
    req: ConversationCreate,
    db: Session = Depends(get_db)
):
    """创建新对话"""
    from sqlalchemy import inspect
    from backend.db.database import Base
    inspector = inspect(db.get_bind())
    tables = inspector.get_table_names()
    
    # 自修复：如果表不存在，立即创建所有表
    if 'conversations' not in tables:
        logger.warning("[API-DEBUG] Tables not found, creating them now!")
        Base.metadata.create_all(bind=db.get_bind())
        tables = inspector.get_table_names()
        logger.info(f"[API-DEBUG] After creating, tables: {tables}")
    
    logger.info(f"[API-DEBUG] create_conversation sees tables: {tables}")
    
    conv = ConversationModel(
        title=req.title or "新对话",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv) # 获取数据库生成的新 ID 和默认值
    logger.info(f"✅ 新建对话: {conv.id}")
    return conv

@router.get("/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """获取对话详情"""
    conv = db.query(ConversationModel).filter(
        ConversationModel.id == conversation_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conv

@router.get("", response_model=list[Conversation])
async def list_conversations(
    search: str = None,
    include_archived: bool = False,
    db: Session = Depends(get_db)
):
    """列出用户的所有对话，支持搜索、过滤归档、按最近活跃排序，默认按更新时间倒序，旧对话自动折叠"""
    # 注意：旧的 user_id 过滤逻辑已移除，待后续添加用户认证功能
    query = db.query(ConversationModel)
    
    # 过滤归档的对话
    if not include_archived:
        query = query.filter(ConversationModel.is_archived == False)
    
    # 搜索功能
    if search:
        query = query.filter(ConversationModel.title.ilike(f"%{search}%"))
    
    # 先按置顶排序，再按最后活跃时间排序（置顶的永远在前）
    convs = query.order_by(
        ConversationModel.is_pinned.desc(),
        ConversationModel.last_active_at.desc()
    ).all()
    logger.info(f"📋 已获取 {len(convs)} 个对话的列表。")
    return convs

@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """删除指定对话，同时删除其下所有消息"""
    # 先检查对话是否存在
    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == conversation_id
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="对话未找到")
    # 删除对话，级联删除所有消息
    db.delete(conversation)
    db.commit()
    logger.info(f"🗑️ 对话 {conversation_id} 已删除")
    return {"success": True, "message": "对话已成功删除"}