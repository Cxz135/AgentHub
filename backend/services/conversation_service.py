from typing import List, Optional
from sqlalchemy.orm import Session, joinedload

from backend.models.conversation import Conversation
from backend.models.message import Message

class ConversationService:
    """
    封装了所有与会话和消息相关的数据库操作。
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    def create_conversation(self, title: str = "新会话") -> Conversation:
        """
        创建一个新的会话。

        Args:
            title: 会话的标题。

        Returns:
            新创建的 Conversation 对象。
        """
        new_conversation = Conversation(title=title)
        self.db.add(new_conversation)
        self.db.commit()
        self.db.refresh(new_conversation)
        return new_conversation

    def get_conversation(self, conversation_id: int) -> Optional[Conversation]:
        """
        获取一个会话及其所有消息。
        使用 joinedload 来进行高效的预加载，避免 N+1 查询问题。

        Args:
            conversation_id: 会话的 ID。

        Returns:
            Conversation 对象，如果不存在则返回 None。
        """
        return self.db.query(Conversation).options(
            joinedload(Conversation.messages)
        ).filter(Conversation.id == conversation_id).first()

    def get_all_conversations(self) -> List[Conversation]:
        """
        获取所有会话的列表，按更新时间降序排列。

        Returns:
            Conversation 对象的列表。
        """
        return self.db.query(Conversation).order_by(Conversation.updated_at.desc()).all()

    def add_message_to_conversation(
        self,
        conversation_id: int,
        agent_id: str,
        content: str
    ) -> Message:
        """
        向指定的会话中添加一条新消息。

        Args:
            conversation_id: 会话的 ID。
            agent_id: 发送消息的 Agent ID ('user' 代表用户)。
            content: 消息内容。

        Returns:
            新创建的 Message 对象。
        """
        new_message = Message(
            conversation_id=conversation_id,
            agent_id=agent_id,
            content=content
        )
        self.db.add(new_message)
        self.db.commit()
        self.db.refresh(new_message)
        return new_message

    def get_messages(self, conversation_id: str) -> List[Message]:
        """
        获取指定对话的所有历史消息，并按创建时间升序排列。

        Args:
            conversation_id: 会话的 ID。

        Returns:
            Message 对象的列表。
        """
        return self.db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.asc()).all()