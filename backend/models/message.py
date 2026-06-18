import uuid
import json
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean, JSON, Integer, Text
from sqlalchemy.orm import relationship
from backend.db.database import Base


class MessageType:
    TEXT = "text"
    CODE = "code"
    IMAGE = "image"
    FILE = "file"
    WEBCARD = "webcard"
    ALL_TYPES = [TEXT, CODE, IMAGE, FILE, WEBCARD]


class Message(Base):
    """
    消息模型，代表会话中的一条消息。

    内容格式（存为 JSON string 在 content 字段）：
    {
        "type": "text" | "code" | "image" | "file" | "webcard",
        "content": "主内容",
        "metadata": { ... }
    }
    """
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey('conversations.id'), nullable=False)
    agent_id = Column(String, nullable=False)  # 发送者ID, 'user' 代表用户
    content = Column(Text, nullable=False)  # JSON 格式：{type, content, metadata}
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_pinned = Column(Boolean, default=False)  # 是否固定消息
    mentions = Column(JSON, default=list)  # @提到的agent_ids列表
    meta_data = Column(JSON, default=dict)  # 其他元数据

    # 建立与 Conversation 的关系
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, agent_id='{self.agent_id}', conversation_id={self.conversation_id})>"

    def get_structured_content(self) -> dict:
        """解析 content 为结构化对象"""
        try:
            return json.loads(self.content)
        except (json.JSONDecodeError, TypeError):
            return {"type": MessageType.TEXT, "content": self.content, "metadata": {}}

    def set_structured_content(self, msg_type: str, content: str, metadata: dict = None):
        """设置结构化内容"""
        self.content = json.dumps({
            "type": msg_type,
            "content": content,
            "metadata": metadata or {}
        }, ensure_ascii=False)

    @property
    def message_type(self) -> str:
        """获取消息类型"""
        return self.get_structured_content().get("type", MessageType.TEXT)

    @property
    def plain_text(self) -> str:
        """获取纯文本内容（用于搜索/预览）"""
        return self.get_structured_content().get("content", "")


def create_message_content(
    msg_type: str,
    content: str,
    language: str = None,
    filename: str = None,
    url: str = None,
    alt: str = None,
    name: str = None,
    size: int = None,
    mime_type: str = None,
    title: str = None,
    description: str = None,
    image: str = None,
    provider: str = None,
    **extra
) -> str:
    """
    创建结构化消息内容的 JSON 字符串

    Args:
        msg_type: 消息类型 (text/code/image/file/webcard)
        content: 主内容
        language: 代码语言 (code 类型)
        filename: 文件名 (code 类型)
        url: 资源URL (image/file/webcard)
        alt: 图片描述 (image 类型)
        name: 文件名 (file 类型)
        size: 文件大小字节 (file 类型)
        mime_type: MIME类型 (file 类型)
        title: 卡片标题 (webcard 类型)
        description: 卡片描述 (webcard 类型)
        image: 卡片图片URL (webcard 类型)
        provider: 来源提供者 (webcard 类型)
        **extra: 其他元数据
    """
    metadata = {k: v for k, v in {
        "language": language,
        "filename": filename,
        "url": url,
        "alt": alt,
        "name": name,
        "size": size,
        "mime_type": mime_type,
        "title": title,
        "description": description,
        "image": image,
        "provider": provider,
        **extra
    }.items() if v is not None}

    return json.dumps({
        "type": msg_type,
        "content": content,
        "metadata": metadata
    }, ensure_ascii=False)


def parse_message_content(content_json: str) -> dict:
    """解析消息内容 JSON，支持旧格式兼容"""
    if not content_json:
        return {"type": MessageType.TEXT, "content": "", "metadata": {}}

    try:
        parsed = json.loads(content_json)
        if isinstance(parsed, dict) and "type" in parsed:
            return parsed
        return {"type": MessageType.TEXT, "content": str(parsed), "metadata": {}}
    except (json.JSONDecodeError, TypeError):
        return {"type": MessageType.TEXT, "content": str(content_json), "metadata": {}}


def extract_code_content(content_json: str) -> str:
    """
    从消息内容中提取纯文本/代码内容，用于复制等操作。
    
    Returns:
        提取的内容字符串
    """
    parsed = parse_message_content(content_json)
    return parsed.get("content", "")


def create_quoted_content(
    original_message_id: int,
    original_agent_id: str,
    original_content: str,
    quote_text: str = None
) -> dict:
    """
    创建引用内容结构
    
    Args:
        original_message_id: 被引用消息的 ID
        original_agent_id: 被引用消息的发送者
        original_content: 被引用消息的原文
        quote_text: 引用时截取的文本（可选，默认使用原文前100字）
    """
    return {
        "quoted_message_id": original_message_id,
        "quoted_agent_id": original_agent_id,
        "quoted_text": quote_text or (original_content[:100] + "..." if len(original_content) > 100 else original_content),
        "original_content": original_content
    }