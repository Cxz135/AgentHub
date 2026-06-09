# AgentHub - 多Agent协作平台 技术文档

**版本**：v1.0
**更新日期**：2026-06-09
**文档类型**：技术架构文档
**目标读者**：后端开发工程师 / 智能体开发程序员（3年经验）

---

## 1. 项目概述

### 1.1 项目定位

AgentHub 是一个基于 IM 聊天范式的多 Agent 协作平台。用户通过自然语言与不同 AI Agent 交互，完成复杂任务自动化。核心场景包括：

- **单聊模式**：1v1 与单个 Agent 对话，适合明确任务（如代码生成、文档处理）
- **群聊模式**：@多个 Agent，由 Orchestrator 自动协调分工，多 Agent 依次回复
- **上下文连续**：每个对话保持完整聊天历史，支持多轮迭代修改
- **产物内联**：Agent 回复可内联展示代码 Diff、网页预览卡片、文件附件等富媒体

### 1.2 技术选型

| 层级 | 技术选型 | 选型理由 |
|------|----------|----------|
| Web 框架 | FastAPI (Python) | 异步高性能，自动 OpenAPI 文档，与 LangChain/LangGraph 无缝集成 |
| ORM | SQLAlchemy | 抽象数据库差异，支持多种数据库，迁移方便 |
| 数据库 | SQLite | 零依赖部署，适合竞赛项目本地服务器场景 |
| 工作流编排 | LangGraph | 基于 LangChain 的有状态图计算，支持检查点持久化、条件分支、并行调度 |
| LLM 适配 | 统一抽象层 | 通过 `LLMBackend` 抽象接口，屏蔽不同 API 差异，支持灵活扩展 |
| 认证 | JWT + bcrypt | 成熟稳定的 Token 认证方案，bcrypt 密码哈希 |
| 日志 | Loguru | 结构化日志，支持多输出目标，配置简单 |

### 1.3 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端 (HTML/JS)                                   │
│                   localhost:8000 静态托管 / 或独立前端服务                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        │ HTTP/REST + SSE
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FastAPI (端口 8000)                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  /api/chat   │  │ /api/missions│  │ /api/agents  │  │ /api/skills  │     │
│  │   聊天核心    │  │   会话管理    │  │   Agent管理   │  │   技能市场    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Orchestrator (核心协调器)                            │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        消息路由决策引擎                               │    │
│  │  1. @mention 路由 → 直接调用指定 Agent                              │    │
│  │  2. Agent 管理请求 → agent_builder                                  │    │
│  │  3. 固定工作流匹配 → RAG/CodeReview (关键词触发)                    │    │
│  │  4. 复杂任务 → PlannerAgent 动态规划 + LangGraph 执行               │    │
│  │  5. 普通聊天 → 默认 LLM 直接回复                                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Agent注册表  │  │ 工作流注册表  │  │ LLM后端注册表 │  │ Skill注册表   │         │
│  │ (agents)    │  │ (workflows) │  │ (backends) │  │ (skills)    │         │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────────────────────┘
          │                  │                    │                  │
          ▼                  ▼                    ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  内置Agent池     │ │  LangGraph      │ │   LLM 后端池     │ │   Skill 系统    │
│  - planner      │ │  planning_graph │ │   - tongyi      │ │   - native      │
│  - summarizer   │ │  (动态规划)      │ │   - deepseek    │ │   - tool        │
│  - code_analyzer│ │                 │ │   - opencode    │ │                 │
│  - rag_agent    │ │  固定工作流:     │ │                 │ │   工具:         │
│  - report_gen   │ │  - RAG workflow │ │                 │ │   - web_search  │
│  - vuln_scanner │ │  - CodeReview   │ │                 │ │   - file_conv   │
│  - agent_builder│ │                 │ │                 │ │   - rag_retriev │
│  + 自定义Agent   │ │                 │ │                 │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘
          │                  │                    │                  │
          ▼                  ▼                    ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  SQLAlchemy     │ │  AsyncSqlite    │ │   httpx         │ │   LangChain     │
│  ORM Models     │ │  Checkpoint     │ │   异步HTTP客户端  │ │   Tool 封装      │
└─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘
          │                  │                    │                  │
          ▼                  ▼                    ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   SQLite        │ │  agenthub_memory│ │  外部 LLM API   │ │   文件系统/网络  │
│   agenthub.db   │ │  .sqlite        │ │  - DashScope   │ │                 │
└─────────────────┘ └─────────────────┘ │  - DeepSeek    │ │                 │
                                        │  - OpenCode    │ │                 │
                                        └─────────────────┘ └─────────────────┘
```

---

## 2. 核心模块详解

### 2.1 Orchestrator（核心协调器）

**文件位置**：`backend/core/orchestrator.py`（2491 行）

#### 2.1.1 设计目标

Orchestrator 是整个系统的心脏，负责：
1. 统一管理所有 Agent、工作流、LLM 后端、Skill
2. 接收用户消息，自主判断请求类型并路由
3. 协调多个 Agent 协作完成复杂任务
4. 管理对话记忆和工作流状态

#### 2.1.2 初始化流程

```python
def __init__(self, db_session=None):
    # 0. 注册所有 LLM 后端（统一适配器层的基础）
    self._setup_backends()
    # 0.5 健康检查：移除超时/不可用的后端
    self._health_check_backends()
    # 1. 加载所有 Skill（工具类）
    self._load_native_skills()
    self._register_builtin_tool_skills()
    # 2. 注册所有核心 Agent
    self._setup_agents()
    # 3. 注册所有工作流（内置+自定义）
    self._register_builtin_workflows()
    self._register_workflows()
    # 4. 定义动态规划工作流的蓝图
    self.planning_graph_builder = self._build_planning_graph()
    # 5. 加载数据库里的自定义 Agent
    self._load_custom_agents_from_db()
```

#### 2.1.3 消息路由决策树

```
get_chat_response()
│
├─ 1. @mention 检测
│   ├─ 单个 @ → _handle_mention()
│   └─ 多个 @ → _handle_multiple_mentions()
│
├─ 2. Agent 管理请求（LLM 分类器判断）
│   └─ _handle_agent_management_request()
│
├─ 3. 自动匹配固定工作流（关键词打分）
│   └─ _handle_workflow_command()
│
├─ 4. 复杂度路由
│   ├─ complex → _handle_plan_command() (PlannerAgent + LangGraph)
│   ├─ moderate → _handle_default_chat() (直接执行)
│   └─ simple → _handle_simple_chat() (Orchestrator 直接回复)
│
├─ 5. Skill 调用请求（正则解析）
│
├─ 6. 系统查询（列表/帮助等）
│
└─ 7. 默认：普通聊天
```

#### 2.1.4 LLM 后端管理

```python
def _setup_backends(self):
    # 注册多个 LLM 后端
    self.llm_backends["tongyi"] = TongyiBackend(model="qwen-plus")
    self.llm_backends["deepseek"] = DeepSeekBackend(model="deepseek-chat")
    self.llm_backends["opencode"] = OpenCodeBackend(...)

def _health_check_backends(self, timeout: int = 8):
    # 启动时同步健康检查，移除不可用后端
    for name, backend in self.llm_backends.items():
        try:
            resp = client.post(base_url, ...)
            backend._healthy = resp.status_code == 200
        except:
            backend._healthy = False
            del self.llm_backends[name]
```

#### 2.1.5 Skill 调用机制

```python
async def call_skill(self, skill_name: str, method: str = None, input_content: str = None):
    # 工具类 Skill（Python 函数）
    if method and f"{skill_name}.{method}" in self.tool_skills:
        return self.tool_skills[f"{skill_name}.{method}"](input_content)
    # 能力类 Skill（MD 文件，纯自然语言）
    if skill_name in self.native_skills:
        full_prompt = f"{self.native_skills[skill_name]}\n\n### 待处理输入\n{input_content}"
        return await self.get_backend("tongyi").chat([{"role": "user", "content": full_prompt}])
```

**Skill 调用格式**（大模型输出）：
- 能力类：`【调用Skill: web_search，输入内容: "搜索关键词"】`
- 工具类：`【调用Skill: file_converter，方法: pdf_to_markdown，输入内容: "..."】`

---

### 2.2 LLM 后端适配层

**文件位置**：`backend/llm/`

#### 2.2.1 抽象接口

```python
class LLMBackend(ABC):
    provider: str          # "tongyi" / "deepseek" / "opencode"
    model_name: str        # "qwen-plus" / "deepseek-coder" / ...

    @abstractmethod
    async def chat(self, messages, temperature, max_tokens, stop) -> str:
        """统一的非流式调用接口"""

    @abstractmethod
    async def chat_stream(self, messages, ...) -> AsyncGenerator[str, None]:
        """统一的流式调用接口"""
```

#### 2.2.2 DeepSeek 后端实现

```python
class DeepSeekBackend(LLMBackend):
    def __init__(self, model="deepseek-chat", api_key=None,
                 base_url="https://api.deepseek.com/v1/chat/completions"):
        ...

    async def chat_stream(self, messages, ...):
        payload = {"model": self.model_name, "messages": messages, "stream": True}
        async with client.stream("POST", self.base_url, json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    delta = data["choices"][0].get("delta", {})
                    yield delta.get("content", "")
```

**设计亮点**：统一抽象层使得新增 LLM 后端只需实现 `chat()` 和 `chat_stream()` 两个方法，无需修改上层业务逻辑。

---

### 2.3 Agent 系统

**文件位置**：`backend/agents/`

#### 2.3.1 BaseAgent 抽象

```python
class BaseAgent(ABC):
    agent_id: str

    @abstractmethod
    async def process_message(self, messages, context) -> AgentResponse:
        """核心处理逻辑"""
        pass

class AgentResponse(BaseModel):
    final_answer: Optional[FinalAnswer] = None
```

#### 2.3.2 CustomAgent（用户自定义 Agent）

```python
class CustomAgent(BaseAgent):
    def __init__(self, agent_id, system_prompt, llm_backend,
                 name=None, validation_config=None):
        self.system_prompt = system_prompt
        self.backend = llm_backend
        self.validation_config = validation_config

    async def process_message(self, messages, context) -> AgentResponse:
        full_messages = [{"role": "system", "content": self.system_prompt}]
        # 追加历史消息
        for m in messages:
            full_messages.append({"role": m.role, "content": m.content})
        content = await self.backend.chat(full_messages)
        return AgentResponse(final_answer=FinalAnswer(content=content))
```

#### 2.3.3 内置 Agent

| Agent | 职责 | 核心逻辑 |
|-------|------|----------|
| `planner` | 任务分解 | 调用 LLM 生成带依赖关系的 JSON 计划 |
| `summarizer` | 内容摘要 | 长文本压缩摘要 |
| `code_analyzer` | 代码分析 | AST 解析 + 静态分析 |
| `rag_agent` | 知识库问答 | 向量检索 + LLM 生成 |
| `report_generator` | 报告生成 | 模板填充 + 格式化输出 |
| `vulnerability_scanner` | 漏洞扫描 | 安全规则匹配 |
| `agent_builder` | Agent 创建/修改 | 工具调用管理数据库 |

---

### 2.4 PlannerAgent（任务规划器）

**文件位置**：`backend/agents/internal/planner_agent.py`

#### 2.4.1 系统提示词模板

```python
SYSTEM_PROMPT_TEMPLATE = """你是一个任务规划器。根据用户需求，将任务拆解为子任务列表：

[
  {{
    "step_id": "1",
    "agent_id": "可用的agent_id",
    "prompt": "下发给子Agent的精确指令",
    "expectations": {{
      "pass": "及格标准",
      "standard": "期望标准"
    }},
    "dependencies": ["0"]  // 依赖的前置step_id
  }}
]

规则：
1. 可用 agent: {available_agents}
2. 如果任务需要调用工具，必须在prompt中明确告诉执行agent使用哪个技能
3. 如果子任务需要前面任务的结果，必须在 dependencies 中标明
"""
```

#### 2.4.2 计划解析逻辑

```python
def _parse_plan_from_response(self, response_str: str) -> List[Dict]:
    # 使用正则表达式精确查找 JSON 代码块
    match = re.search(r"```json\n(.*?)\n```", response_str, re.DOTALL)
    if not match:
        json_str = response_str.strip()
    else:
        json_str = match.group(1).strip()
    plan = json.loads(json_str)
    return plan
```

**设计亮点**：PlannerAgent 通过 LLM 自动生成结构化计划，支持任务依赖图，比固定模板更灵活，可适应多种复杂任务场景。

---

### 2.5 LangGraph 工作流编排

**文件位置**：`backend/core/graph_state.py`

#### 2.5.1 GraphState 定义

```python
class GraphState(TypedDict):
    task_content: str              # 任务原始内容
    plan_data: Dict[str, Any]       # Planner 生成的计划
    tasks: List[TaskSpec]           # 任务规格列表
    step_results: Dict[int, Any]    # 按步骤编号存储执行结果
    final_summary: str              # 最终总结报告
    conversation_id: str           # 会话 ID
    next_steps_to_execute: List[int]# 下一个要执行的步骤编号
    messages: List[BaseMessage]    # AI 对话历史
    memory_summary: str             # 历史摘要（压缩）
    agent_outputs: List[Dict]       # 各子 Agent 输出（前端展示用）
    shared_workspace: dict          # 共享工作空间
```

#### 2.5.2 动态规划工作流图

```python
def _build_planning_graph(self) -> StateGraph:
    workflow = StateGraph(GraphState)

    # 节点定义
    workflow.add_node("planner", self._plan_node)
    workflow.add_node("executor", self._execute_node)
    workflow.add_node("aggregator", self._aggregate_node)
    workflow.add_node("summarizer", self._summarize_node)

    # 边定义
    workflow.add_edge("planner", "executor")
    workflow.add_edge("executor", "aggregator")
    workflow.add_edge("aggregator", "summarizer")
    workflow.add_edge("summarizer", END)

    workflow.set_entry_point("planner")
    return workflow.compile(checkpointer=AsyncSqliteSaver)
```

#### 2.5.3 固定工作流示例

**代码审查工作流**（`backend/workflows/code_review_workflow.py`）：

```python
class CodeReviewWorkflow:
    @staticmethod
    def build() -> StateGraph:
        workflow = StateGraph(GraphState)
        # 节点1：代码静态分析
        workflow.add_node("analyze_code", CodeAnalyzerAgent.analyze)
        # 节点2：漏洞扫描
        workflow.add_node("scan_vulnerabilities", VulnerabilityScannerAgent.scan)
        # 节点3：生成审查报告
        workflow.add_node("generate_report", ReportGeneratorAgent.generate)
        # 固定流程
        workflow.add_edge("analyze_code", "scan_vulnerabilities")
        workflow.add_edge("scan_vulnerabilities", "generate_report")
        workflow.add_edge("generate_report", END)
        workflow.set_entry_point("analyze_code")
        return workflow.compile()
```

**工作流自动匹配**（关键词打分）：

```python
WORKFLOW_TRIGGER_THRESHOLD = 6

def _auto_match_workflow(self, content: str) -> str | None:
    for workflow_id, workflow_info in self.workflows.items():
        score = 0
        for keyword in workflow_info["keywords"]:
            if keyword.lower() in content.lower():
                score += 1
        if score > WORKFLOW_TRIGGER_THRESHOLD:
            return workflow_id
    return None
```

---

### 2.6 记忆策略（Memory Strategy）

**文件位置**：`backend/core/memory_strategy.py`

#### 2.6.1 三种策略

```python
async def apply_memory_strategy(messages, memory_config, llm_invoke=None):
    strategy = memory_config.get("strategy", "")

    if strategy == "none":
        # 仅保留最后一条 user message
        return [messages[-1]]

    if strategy == "sliding_window":
        window_size = memory_config.get("window_size", 10)
        keep = window_size * 2
        return messages[-keep:]

    if strategy == "summary":
        threshold = memory_config.get("summary_threshold", 4000)
        est = _estimate_tokens(messages)
        if est <= threshold:
            return messages
        # 摘要历史消息，保留最近 2 条
        history = messages[:-2]
        summary_resp = await llm_invoke(summary_messages)
        return [{"role": "system", "content": f"【历史摘要】{summary_resp}"}, *messages[-2:]]
```

**设计亮点**：记忆策略与主工作流解耦，可按 Agent 独立配置，实现个性化上下文管理。

---

### 2.7 校验策略（Validation Strategy）

**文件位置**：`backend/core/validation_strategy.py`

#### 2.7.1 三种策略

| 策略 | 说明 | 实现方式 |
|------|------|----------|
| `none` | 不校验 | 直接返回 |
| `rules` | 规则校验 | 正则表达式 / JSON Schema |
| `llm_judge` | LLM 评判 | 调用 LLM 判断回答质量 |

```python
async def apply_validation_strategy(output_text, validation_config, llm_invoke):
    strategy = validation_config.get("strategy", "")

    if strategy == "rules":
        rules = validation_config.get("rules", [])
        for rule in rules:
            if rule["type"] == "regex" and not re.search(rule["pattern"], output_text):
                return ValidationResult(passed=False, reason_text=rule["message"])

    if strategy == "llm_judge":
        judge_prompt = validation_config.get("judge_prompt", "")
        judge_messages = [
            {"role": "system", "content": judge_prompt},
            {"role": "user", "content": output_text}
        ]
        judge_result = await llm_invoke(judge_messages)
        # 解析判断结果...
```

---

### 2.8 Chat API 与 SSE 流式

**文件位置**：`backend/app/api/chat.py`

#### 2.8.1 核心端点

```
POST /api/chat                      # 普通聊天（非流式）
POST /api/chat/stream               # SSE 流式聊天
GET  /api/chat/{id}/messages       # 获取会话消息
POST /api/chat/{id}/messages       # 在会话中发送消息
```

#### 2.8.2 SSE 事件协议

```python
async def _chat_stream_impl(req: ChatStreamRequest, current_user):
    """
    SSE 事件类型：
    - user_message_saved : 用户消息已落库
    - intermediate       : 子 Agent 输出
    - token              : LLM 流式 token
    - artifact           : 产物卡片
    - thinking           : Agent 思考状态
    - final              : 最终回复
    - error              : 错误信息
    - done               : 终止信号
    """
    yield _sse("user_message_saved", {...})

    # 尝试流式，降级到一次性
    if hasattr(orchestrator, "get_chat_stream"):
        async for chunk in orchestrator.get_chat_stream(...):
            yield _sse(chunk["type"], chunk)
    else:
        response = await orchestrator.get_chat_response(...)
        # 模拟打字机效果
        for tok in tokens:
            yield _sse("token", {"content": tok})
            await asyncio.sleep(0.015)

    yield _sse("final", {...})
    yield _sse("done", {})
```

#### 2.8.3 已知问题：流式输出不稳定

**问题描述**：SSE 流式输出时常出现问题，表现为：
1. 前端无法稳定接收流式 token
2. 经常降级到一次性返回 + 模拟打字机效果

**根本原因**：`Orchestrator.get_chat_response()` 内部调用 LangGraph 的 `astream()` 时，真正的 LLM token 流未被正确提取和转发。

**当前 workaround**：检测到流式异常时，自动降级为一次性返回，并模拟 `~15ms/chunk` 的打字机效果。

**改进方向**：
1. 实现真正的 WebSocket 双向通信
2. 在 LangGraph 节点中正确提取和转发 LLM stream token
3. 添加流式状态管理和错误重试机制

---

### 2.9 数据库模型

**文件位置**：`backend/models/`

#### 2.9.1 ER 图

```
users (1) ─────────────< (N) conversations
  │                           │
  │                           │ (1)
  │                           │
  └──< (N) custom_agents    messages
          │                      │
          │                      │
          └──< (N) skill_installs
                  │
                  │
            skills (1) ─────────┤ (N) skill_installs
                  │
                  │
            skills (1) ──< (N) skills (parent_id, for fork)
```

#### 2.9.2 核心表结构

**conversations（会话表）**
```python
class Conversation(Base):
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    title = Column(String, default="新会话")
    mode = Column(String, default="single")  # single / group
    participants = Column(JSON, default=list)  # 群聊参与者
    squad_config = Column(JSON, default=dict)  # Mission 班底配置
    is_pinned = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
```

**messages（消息表）**
```python
class Message(Base):
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, Foreign_key)
    agent_id = Column(String)  # 'user' / 'assistant' / agent_id
    content = Column(String)
    mentions = Column(JSON, default=list)  # @到的 agent_ids
    meta_data = Column(JSON, default=dict)
    is_pinned = Column(Boolean, default=False)
```

**custom_agents（自定义 Agent 表）**
```python
class CustomAgent(Base):
    id = Column(Integer, primary_key=True)
    name = Column(String)
    agent_id = Column(String, unique=True)  # 运行时 ID
    user_id = Column(Integer, ForeignKey('users.id'))
    system_prompt = Column(String)
    llm_adapter = Column(String, default="tongyi")
    tools = Column(JSON, default=list)
    # A 档：per-Agent 配置
    memory_config = Column(JSON, nullable=True)
    planning_config = Column(JSON, nullable=True)
    validation_config = Column(JSON, nullable=True)
```

**skills（技能表）**
```python
class Skill(Base):
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True)
    name = Column(String)
    code = Column(Text)  # 技能代码
    readme = Column(Text)  # 技能文档
    category = Column(String, default='custom')
    author_id = Column(Integer, ForeignKey('users.id'))
    is_published = Column(Boolean, default=False)
    versions = Column(Text, default='[]')  # JSON
    parent_id = Column(Integer, ForeignKey('skills.id'))  # Fork
```

---

## 3. API 设计

### 3.1 RESTful API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| GET | `/api/missions` | 获取会话列表 |
| POST | `/api/missions` | 创建新会话 |
| GET | `/api/missions/{id}` | 获取会话详情 |
| DELETE | `/api/missions/{id}` | 删除会话 |
| GET | `/api/chat/{id}/messages` | 获取消息历史 |
| POST | `/api/chat` | 发送消息（普通） |
| POST | `/api/chat/stream` | 发送消息（SSE 流式） |
| GET | `/api/agents` | 获取 Agent 列表 |
| POST | `/api/agents` | 创建自定义 Agent |
| PUT | `/api/agents/{id}` | 更新 Agent |
| DELETE | `/api/agents/{id}` | 删除 Agent |
| GET | `/api/skills` | 获取技能列表 |
| POST | `/api/skills` | 创建技能 |
| POST | `/api/skills/{id}/fork` | Fork 技能 |
| POST | `/api/skills/{id}/publish` | 发布技能 |
| GET | `/api/knowledge` | 获取知识库列表 |
| POST | `/api/knowledge` | 上传知识库文件 |

### 3.2 认证机制

**JWT Token 流程**：
1. 用户注册/登录 → 后端验证 → 返回 JWT Token
2. 前端将 Token 存入 localStorage
3. 后续请求在 Header 中携带：`Authorization: Bearer <token>`
4. Token TTL = 7 天

**依赖注入**：
```python
async def get_current_user(token: str = Depends(JWTBearer())):
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    user = db.query(User).filter(User.id == payload["sub"]).first()
    return user
```

---

## 4. 前端集成

### 4.1 静态托管

FastAPI 直接托管前端静态文件：

```python
from fastapi.staticfiles import StaticFiles

frontend_dir = os.path.abspath(os.path.join(__file__, '..', '..', 'AgentHub-my flicker'))
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
```

### 4.2 SSE 客户端实现

```javascript
async function sendMessage(message, conversationId) {
    const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            message,
            conversation_id: conversationId,
            agent: selectedAgent
        })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split('\n\n');

        for (const line of lines) {
            if (line.startsWith('event: ')) {
                const eventType = line.split('\n')[0].replace('event: ', '');
                const data = JSON.parse(line.split('data: ')[1]);
                handleSSEEvent(eventType, data);
            }
        }
    }
}

function handleSSEEvent(type, data) {
    switch(type) {
        case 'token':
            appendToken(data.content);
            break;
        case 'intermediate':
            appendAgentMessage(data.agent_id, data.content);
            break;
        case 'artifact':
            renderArtifactCard(data);
            break;
        case 'done':
            finishResponse();
            break;
    }
}
```

---

## 5. 技术亮点与创新点

### 5.1 统一适配器层

通过 `LLMBackend` 抽象接口，屏蔽了不同 LLM API 的差异，使得：
- 切换 LLM 后端只需修改配置
- 新增 LLM 后端只需实现两个方法
- 业务代码与具体 LLM 解耦

### 5.2 动态规划 + 静态工作流双轨制

- **动态规划**：复杂任务由 PlannerAgent 自动拆解，通过 LangGraph 执行
- **固定工作流**：简单任务通过关键词匹配直接路由到预设工作流

这种设计平衡了灵活性与性能，避免复杂任务也走固定流程的笨拙。

### 5.3 多层次 Skill 系统

- **能力类 Skill**（MD 文件）：纯自然语言描述，可自定义，通过 prompt 拼装调用
- **工具类 Skill**（Python 函数）：可执行代码，注册为 LangChain Tool，支持 ReAct 循环

两种 Skill 各有优势，可按场景选择。

### 5.4 per-Agent 精细化配置

自定义 Agent 支持独立配置：
- `memory_config`：上下文记忆策略（none/sliding_window/summary）
- `planning_config`：规划模式（direct/react/plan_execute）
- `validation_config`：输出校验规则（none/rules/llm_judge）

这使得不同 Agent 可以有不同的行为特性，提高系统灵活性。

### 5.5 失败降级机制

```python
try:
    final_state = await app.astream(initial_state, config=config)
except Exception as e:
    # 降级：直接调用 LLM 生成基础回答
    fallback_response = await self.get_backend("tongyi").chat([
        {"role": "user", "content": f"用户的问题是：{task_content}..."}
    ])
    return {"content": f"⚠️ 复杂任务调度遇到小问题，不过我依然可以帮你解答：\n{fallback_response}"}
```

---

## 6. 已实现功能 vs 未实现功能

### 6.1 P0 核心功能（已实现）

| 功能 | 状态 | 说明 |
|------|------|------|
| 注册/登录 | ✅ | JWT + bcrypt |
| 会话管理 | ✅ | CRUD + 置顶/归档 |
| IM 聊天 | ✅ | 单聊/群聊 |
| @mention | ✅ | 多 Agent 路由 |
| 上下文连续 | ✅ | 消息历史传递 |
| 多 Agent 协作 | ✅ | Orchestrator 协调 |
| 产物内联 | ✅ | 文本/代码/卡片 |
| 动态规划 | ✅ | PlannerAgent + LangGraph |
| 固定工作流 | ✅ | RAG / CodeReview |
| 自定义 Agent | ✅ | system_prompt + tools |
| Skill 市场 | ✅ | Fork/Publish/Install |
| 知识库 | ✅ | Chroma 向量存储 |
| SSE 流式 | ✅ | 基础可用 |

### 6.2 P1 功能（部分实现）

| 功能 | 状态 | 说明 |
|------|------|------|
| 部署发布 | ⚠️ | 基础卡片，无实际部署 |
| Diff 视图 | ❌ | 未实现 |
| 版本历史 | ❌ | 未实现 |
| 局部修改 | ❌ | 未实现 |

### 6.3 P2 功能（未实现）

| 功能 | 状态 | 说明 |
|------|------|------|
| 桌面端 | ❌ | - |
| 移动端 | ❌ | - |
| 实时协作编辑 | ❌ | - |
| 容器化部署 | ❌ | - |

---

## 7. 已知问题与改进方向

### 7.1 流式输出不稳定

**问题**：`/api/chat/stream` 端点的 SSE 流式输出时常出现问题

**原因**：
1. `Orchestrator.get_chat_response()` 返回的是完整内容，不是流式 generator
2. LangGraph 的 `astream()` 输出的是中间状态，不是 LLM token 流
3. 当前实现是"伪流式"，真正的 token 流未正确提取

**改进方案**：
1. 实现 WebSocket 双向通信，支持真正的实时流
2. 在 LangGraph 节点中提取 LLM 的 `chat_stream()` token 并转发
3. 添加流式状态管理和错误重试机制

### 7.2 其他改进方向

| 方向 | 说明 |
|------|------|
| 数据库迁移 | 引入 Alembic 进行数据库版本管理 |
| 缓存层 | 引入 Redis 缓存热点数据 |
| 监控 | 添加 Prometheus metrics |
| 测试 | 补充单元测试和集成测试覆盖率 |

---

## 8. 部署指南

### 8.1 环境要求

- Python 3.10+
- SQLite（内置，无需单独安装）

### 8.2 配置

在项目根目录创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=your_api_key
DASHSCOPE_API_KEY=your_api_key
JWT_SECRET=your_jwt_secret
WEBSEARCH_API_KEY=your_bce_api_key
OPENCODE_API_KEY=your_opencode_api_key
```

### 8.3 启动

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 8.4 数据库初始化

应用启动时自动：
1. 创建 SQLite 数据库文件 `agenthub.db`
2. 创建所有表
3. 检查并修复缺失的列（SQLite 的 `create_all` 不会给已有表加新列）
4. 迁移无主的 agents/missions 到第一个用户（兼容旧数据）
5. 写入技能种子数据

---

## 9. 架构设计原则

| 原则 | 体现 |
|------|------|
| **单一职责** | 每个模块只负责一件事（Orchestrator 管路由，Agent 管执行，LLMBackend 管通信） |
| **开闭原则** | 新增 LLM 后端只需实现接口，不修改现有代码 |
| **依赖倒置** | 上层业务依赖抽象接口 `LLMBackend`，不依赖具体实现 |
| **里氏替换** | 任何 `LLMBackend` 子类都可以被替换使用 |
| **接口隔离** | `BaseAgent` 只暴露 `process_message()` 一个方法 |

---

## 10. 总结

AgentHub 是一个设计良好的多 Agent 协作平台，具有以下特点：

1. **清晰的架构分层**：从 API 到 Orchestrator 到 Agent 到 LLMBackend，层次分明
2. **灵活的扩展性**：通过抽象接口和注册表模式，支持轻松扩展
3. **完善的路由机制**：多层次决策树支持各种场景的消息路由
4. **健壮的容错**：失败降级机制保证系统不会完全崩溃

核心创新点在于：
- **动态规划 + 固定工作流双轨制**：平衡灵活性与性能
- **多层次 Skill 系统**：能力类 + 工具类满足不同场景
- **per-Agent 精细化配置**：memory/planning/validation 独立可配

主要待改进问题是 **SSE 流式输出的稳定性**，建议后续引入 WebSocket 或修复 LangGraph 流式 token 提取逻辑。

---

*文档版本：v1.0 | 更新日期：2026-06-09*