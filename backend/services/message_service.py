from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.message import Message
from backend.models.artifact import Artifact
from backend.utils.logger import logger


def create_message(
    db: Session,
    conversation_id: str,
    agent_id: str,
    content: str,
    artifacts: Optional[List[Artifact]] = None
) -> Message:
    """
    创建一条新消息，并可选择性地附加产物。

    这会自动处理好 Message 和 Artifact 之间的数据库关系。
    """
    logger.info(f"正在为会话 {conversation_id} 创建新消息 (Agent: {agent_id})。")
    db_message = Message(
        conversation_id=conversation_id,
        agent_id=agent_id,
        content=content
    )

    if artifacts:
        logger.info(f"消息附带了 {len(artifacts)} 个产物。")
        # SQLAlchemy 的 back_populates 和 cascade 设置会自动处理好关联
        db_message.artifacts = artifacts

    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    logger.info(f"消息 {db_message.id} 已成功存入数据库。")
    return db_message


def get_messages_by_conversation(db: Session, conversation_id: str) -> List[Message]:
    """
    根据会话 ID 获取所有消息，按时间升序排列。
    """
    return db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.created_at).all()