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
    content: str  # JSON 格式：{type, content, metadata}
    created_at: datetime
    message_type: Optional[str] = "text"  # text/code/image/file/webcard
    meta_data: Optional[dict] = {}  # 包含: quoted_message_id, regenerate_count, is_expanded 等
    is_pinned: Optional[bool] = False
    mentions: Optional[List[int]] = []

    class Config:
        from_attributes = True
        populate_by_name = True


class MessageOperation(BaseModel):
    """消息操作请求"""
    action: str  # "quote" | "regenerate" | "copy" | "expand"
    message_id: Optional[int] = None
    quoted_message_id: Optional[int] = None  # 引用时指定
    regenerate_params: Optional[dict] = None  # 重新生成参数


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
    icon: str = "smart_toy"
    description: str = ""
    system_prompt: str
    llm_adapter: str
    tools: list[str] = []
    # A 档新增：3 类配置字段（前端 GET 详情时读取）
    memory_config: Optional[dict] = None
    planning_config: Optional[dict] = None
    validation_config: Optional[dict] = None
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class CustomAgentCreate(BaseModel):
    """用于创建/更新自定义Agent的Schema"""
    name: str
    icon: str = "smart_toy"
    description: str = ""
    system_prompt: str
    llm_adapter: str = "tongyi"
    tools: list[str] = []
    # A 档新增：3 类配置字段（前端保存详情时写入）
    memory_config: Optional[dict] = None
    planning_config: Optional[dict] = None
    validation_config: Optional[dict] = None


class ArtifactSchema(BaseModel):
    type: str  # "code", "preview", "diff"
    title: Optional[str] = None
    content: str
    content: str


class ChatStreamRequest(BaseModel):
    """SSE 流式聊天请求"""
    message: str
    conversation_id: Optional[int] = None
    agent: Optional[dict] = None  # {id, name, llm_adapter, model_name, system_prompt}
    active_skills: Optional[List[str]] = []  # 用户启用的 Skill 列表


class IntermediateMessage(BaseModel):
    agent_id: str
    content: str
    type: Optional[str] = None  # "plan" / "output" / "summary"


class StreamFinal(BaseModel):
    message_id: int
    agent_id: str
    content: str
    intermediate_messages: List[IntermediateMessage] = []
    artifacts: List[ArtifactSchema] = []


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
    """用户登录 - 使用 email 而非 username，与前端一致"""
    email: str
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


class AuthResponse(BaseModel):
    """认证接口返回模型 - 匹配前端期望格式"""
    ok: bool = True
    user: dict
    token: str

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
    authorId: Optional[int] = None
    authorName: str = ''
    isPublished: bool = False
    installCount: int = 0
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    isMine: Optional[bool] = None
    isInstalled: Optional[bool] = None
    versions: Optional[list] = None

    class Config:
        from_attributes = True