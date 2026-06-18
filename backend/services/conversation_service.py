from typing import List, Optional
from sqlalchemy.orm import Session, joinedload

from backend.models.conversation import Conversation
from backend.models.message import Message


class ConversationService:
    """
    封装了所有与会话和消息相关的数据库操作。
    """

    def __init__(self, db: Session):
        self.db = db

    def create_conversation(self, user_id: int, title: str = "新会话", mode: str = "single") -> Conversation:
        """
        创建新的会话。

        Args:
            user_id: 用户 ID
            title: 会话标题
            mode: 会话模式 (single / group)

        Returns:
            新创建的 Conversation 对象。
        """
        new_conv = Conversation(
            user_id=user_id,
            title=title,
            mode=mode
        )
        self.db.add(new_conv)
        self.db.commit()
        self.db.refresh(new_conv)
        return new_conv

    def get_conversation(self, conversation_id: int) -> Optional[Conversation]:
        """
        获取指定会话。

        Args:
            conversation_id: 会话 ID

        Returns:
            Conversation 对象或 None（如果不存在）。
        """
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()

    def get_user_conversations(self, user_id: int, include_archived: bool = False) -> List[Conversation]:
        """
        获取指定用户的所有会话，按最近活跃时间排序。

        Args:
            user_id: 用户 ID
            include_archived: 是否包含已归档的会话

        Returns:
            Conversation 对象列表。
        """
        query = self.db.query(Conversation).filter(Conversation.user_id == user_id)
        if not include_archived:
            query = query.filter(Conversation.is_archived == False)
        return query.order_by(Conversation.last_active_at.desc()).all()

    def update_conversation_title(self, conversation_id: int, title: str) -> Optional[Conversation]:
        """更新会话标题"""
        conv = self.get_conversation(conversation_id)
        if conv:
            conv.title = title
            self.db.commit()
            self.db.refresh(conv)
        return conv

    def archive_conversation(self, conversation_id: int) -> bool:
        """归档会话"""
        conv = self.get_conversation(conversation_id)
        if conv:
            conv.is_archived = True
            self.db.commit()
            return True
        return False

    def unarchive_conversation(self, conversation_id: int) -> bool:
        """取消归档会话"""
        conv = self.get_conversation(conversation_id)
        if conv:
            conv.is_archived = False
            self.db.commit()
            return True
        return False

    def delete_conversation(self, conversation_id: int) -> bool:
        """删除会话及其所有消息"""
        conv = self.get_conversation(conversation_id)
        if not conv:
            return False
        self.db.query(Message).filter(Message.conversation_id == conversation_id).delete()
        self.db.delete(conv)
        self.db.commit()
        return True

    def add_message_to_conversation(
        self,
        conversation_id: int,
        agent_id: str,
        content: str,
        message_type: str = "text",
        metadata: dict = None,
        mentions: list = None
    ) -> Message:
        """
        向会话中添加一条消息。

        Args:
            conversation_id: 会话 ID
            agent_id: 发送者 ID ('user' 或 agent_id)
            content: 消息内容（若是结构化内容会转为 JSON）。
            message_type: 消息类型 (text/code/image/file/webcard)，默认 text。
            metadata: 元数据字典，会合并到消息的 metadata 字段。
            mentions: 提及的 agent ID 列表。

        Returns:
            新创建的 Message 对象。
        """
        from backend.models.message import create_message_content

        structured_content = create_message_content(
            msg_type=message_type,
            content=content,
            **(metadata or {})
        )

        new_message = Message(
            conversation_id=conversation_id,
            agent_id=agent_id,
            content=structured_content,
            meta_data=(metadata or {}),
            mentions=(mentions or [])
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

    def get_conversation_context(
        self,
        conversation_id: int,
        limit: int = 50,
        include_pinned: bool = True
    ) -> List[dict]:
        """
        获取对话上下文，用于传递给 Agent。

        优先返回：
        1. 置顶消息（长期上下文）
        2. 最近的消息（limit 条）

        Args:
            conversation_id: 会话 ID
            limit: 最近消息数量限制
            include_pinned: 是否包含置顶消息作为长期上下文

        Returns:
            消息字典列表 [{"role": "user", "content": "...", "is_pinned": bool}, ...]
        """
        from backend.utils.logger import logger
        logger.info(f"[CONTEXT-SVC] get_conversation_context 开始, conversation_id={conversation_id}, limit={limit}, include_pinned={include_pinned}")

        context = []

        if include_pinned:
            pinned_messages = self.db.query(Message).filter(
                Message.conversation_id == conversation_id,
                Message.is_pinned == True
            ).order_by(Message.created_at.asc()).all()

            for msg in pinned_messages:
                from backend.models.message import parse_message_content
                parsed = parse_message_content(msg.content)
                context.append({
                    "role": msg.agent_id,
                    "content": parsed.get("content", ""),
                    "message_id": msg.id,
                    "is_pinned": True,
                    "message_type": parsed.get("type", "text"),
                    "metadata": parsed.get("metadata", {})
                })

        recent_messages = self.db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.is_pinned == False
        ).order_by(Message.created_at.desc()).limit(limit).all()

        for msg in reversed(recent_messages):
            from backend.models.message import parse_message_content
            parsed = parse_message_content(msg.content)
            context.append({
                "role": msg.agent_id,
                "content": parsed.get("content", ""),
                "message_id": msg.id,
                "is_pinned": False,
                "message_type": parsed.get("type", "text"),
                "metadata": parsed.get("metadata", {})
            })

        logger.info(f"[CONTEXT-SVC] get_conversation_context 返回 {len(context)} 条消息, conversation_id={conversation_id}")
        return context

    def get_pinned_messages(self, conversation_id: int) -> List[Message]:
        """
        获取指定对话的所有置顶消息。

        Args:
            conversation_id: 会话 ID

        Returns:
            置顶的 Message 对象列表
        """
        return self.db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.is_pinned == True
        ).order_by(Message.created_at.desc()).all()

    def toggle_message_pin(self, message_id: int) -> Optional[Message]:
        """
        切换消息的置顶状态。

        Args:
            message_id: 消息 ID

        Returns:
            更新后的 Message 对象或 None
        """
        msg = self.db.query(Message).filter(Message.id == message_id).first()
        if msg:
            msg.is_pinned = not msg.is_pinned
            self.db.commit()
            self.db.refresh(msg)
        return msg

    def rebuild_context_with_long_term_memory(
        self,
        conversation_id: int,
        user_id: int,
        limit: int = 50,
        memory_summary: str = "",
    ) -> List[dict]:
        """
        重建带长期记忆的对话上下文。

        与 get_conversation_context 的区别：
        1. 加载更多历史消息（默认 100 条 vs 50 条）
        2. 跨会话搜索置顶消息（用户维度的长期上下文）
        3. 接受 orchestrator 已加载的 memory_summary（避免异步嵌套）

        Args:
            conversation_id: 会话 ID
            user_id: 用户 ID
            limit: 消息数量限制
            memory_summary: 来自 LangGraph checkpointer 的记忆摘要（由 orchestrator 加载后传入）

        Returns:
            消息字典列表
        """
        from backend.utils.logger import logger
        logger.info(f"[LTM] rebuild_context_with_long_term_memory 开始, conversation_id={conversation_id}, user_id={user_id}, summary_len={len(memory_summary)}")

        context = []

        # 0. 优先注入 orchestrator 已加载的 checkpointer 记忆摘要
        if memory_summary:
            context.insert(0, {
                "role": "system",
                "content": f"【长期记忆摘要】{memory_summary}",
                "message_id": None,
                "is_pinned": True,
                "source": "checkpointer",
                "message_type": "text",
                "metadata": {}
            })

        # 1. 加载当前会话的置顶消息
        pinned_messages = self.db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.is_pinned == True
        ).order_by(Message.created_at.asc()).all()

        for msg in pinned_messages:
            from backend.models.message import parse_message_content
            parsed = parse_message_content(msg.content)
            context.append({
                "role": msg.agent_id,
                "content": parsed.get("content", ""),
                "message_id": msg.id,
                "is_pinned": True,
                "source": "current_conversation",
                "message_type": parsed.get("type", "text"),
                "metadata": parsed.get("metadata", {})
            })

        # 2. 跨会话搜索：加载用户所有会话中的置顶消息作为长期上下文
        user_pinned = self.db.query(Message).join(
            Conversation, Message.conversation_id == Conversation.id
        ).filter(
            Conversation.user_id == user_id,
            Message.is_pinned == True,
            Message.conversation_id != conversation_id
        ).order_by(Message.created_at.desc()).limit(20).all()

        for msg in user_pinned:
            from backend.models.message import parse_message_content
            parsed = parse_message_content(msg.content)
            context.append({
                "role": msg.agent_id,
                "content": parsed.get("content", ""),
                "message_id": msg.id,
                "is_pinned": True,
                "source": f"conversation_{msg.conversation_id}",
                "message_type": parsed.get("type", "text"),
                "metadata": parsed.get("metadata", {})
            })

        # 3. 加载当前会话的最近消息（更多条）
        recent_messages = self.db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.is_pinned == False
        ).order_by(Message.created_at.desc()).limit(max(limit, 100)).all()

        for msg in reversed(recent_messages):
            from backend.models.message import parse_message_content
            parsed = parse_message_content(msg.content)
            context.append({
                "role": msg.agent_id,
                "content": parsed.get("content", ""),
                "message_id": msg.id,
                "is_pinned": False,
                "source": "current_conversation",
                "message_type": parsed.get("type", "text"),
                "metadata": parsed.get("metadata", {})
            })

        logger.info(f"[LTM] rebuild_context_with_long_term_memory 返回 {len(context)} 条消息")
        return context