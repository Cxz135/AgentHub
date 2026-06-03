from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


# ====================
# 基础模型 (用于响应)
# ====================

class Message(BaseModel):
    id: int
    conversation_id: int
    agent_id: str
    content: str
    created_at: datetime

    class Config:
            from_attributes = True


class Conversation(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[Message] = [] # 可以在获取单个会话时填充

    class Config:
        from_attributes = True


# ====================
# 创建模型 (用于请求)
# ====================

class MessageCreate(BaseModel):
    """用于在聊天中创建新消息的 Schema。"""
    content: str


class ConversationCreate(BaseModel):
    """用于创建新会话的 Schema。"""
    title: Optional[str] = "新会话"

# ====================
# 遗留或特定用途模型 (暂时保留)
# ====================

class CustomAgent(BaseModel):
    id: int
    name: str
    agent_id: str
    system_prompt: str
    llm_adapter: str
    tools: list[str] = []
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class CustomAgentCreate(BaseModel):
    """用于创建自定义Agent的Schema"""
    name: str
    system_prompt: str
    llm_adapter: str = "tongyi"
    tools: list[str] = []


class ArtifactSchema(BaseModel):
    type: str  # "code", "preview", "diff"
    title: Optional[str] = None
    content: str
    content: str


class AgentCapability(BaseModel):
    name: str
    description: str


class AgentSpec(BaseModel):
    id: str
    name: str
    description: str
    capabilities: List[str]  # ["code-generation", "review"]
    model: str  # "claude-3" / "gpt-4"
    parameters: dict = {}

# ====================
# 用户认证相关模型
# ====================
class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    is_active: bool
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[int] = None

# ====================
# 技能相关模型
# ====================
class SkillBase(BaseModel):
    slug: str
    name: str
    icon: str = 'extension'
    description: str = ''
    code: str = ''
    readme: str = ''
    category: str = 'custom'

class SkillCreate(SkillBase):
    publish: bool = False

class SkillResponse(SkillBase):
    id: int
    author_id: Optional[int]
    author_name: str
    is_published: bool
    install_count: int
    created_at: datetime
    updated_at: datetime
    isMine: Optional[bool] = None
    isInstalled: Optional[bool] = None
    
    class Config:
        from_attributes = True