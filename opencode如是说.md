下面是完整的项目评估。

---

# AgentHub 项目评估报告

> **总览**：项目已完成**后端核心骨架 + 一个 LLM 适配器层 + 任务式 Orchestrator**。但**前端是单文件 HTML + 旧 Node.js 双轨运行**，**WebSocket / 产物 / 部署 / 真正的"群聊 IM 流"均未实现**。距离 PRD 里描述的"飞书/微信式 IM Agent 平台"还有相当距离。竞争压力下，**应优先把后端做对做稳，再补前端。**

---

## 一、完成度总览（按 PRD 6 大功能）

| 功能 | 状态 | 完成度 | 关键证据 |
|---|---|---|---|
| **① IM 聊天式交互** | 🟡 部分 | 30% | 后端有 conversation/message 模型 + CRUD API；前端有 UI 但**无 WebSocket**，全部 HTTP 轮询；**@mention 已实现** |
| **② 主 Agent 协调器** | ✅ 强 | 85% | Orchestrator + LangGraph + 5 个 internal agents + 3 个 workflow + 并行/降级/记忆压缩 |
| **③ 多 Agent 接入** | 🟡 部分 | 50% | **2 个 LLM 后端 + 1 个 OpenCode Zen（刚加）**；自建 Agent CRUD + A 档配置 |
| **④ 产物预览与编辑** | 🔴 缺失 | 10% | DB 有 `Artifact` 表 + schema 有 `ArtifactSchema`，**但全链路无 artifact 创建/渲染代码** |
| **⑤ 部署发布** | 🔴 缺失 | 0% | 0 行相关代码 |
| **⑥ 多端支持** | 🟡 部分 | 30% | 仅有 Web 端（且双轨：旧 Node server + 新 FastAPI），无桌面/移动 |

---

## 二、已完成任务的"做得好"与"不足"

### 1. 后端架构（Orchestrator + LangGraph）—— 做得最好的一块 ⭐

**做得好**：
- **1749 行的 Orchestrator** 把 priority-based 路由、@mention、规划、降级、记忆压缩 5 个机制在一个文件里协同工作，确实撑起了"主 Agent 协调器"的体验
- `intermediate_messages` 字段（orchestrator.py:758-782）是 PRD 群聊模式的**关键实现**——前端可以按顺序渲染"规划 → 各 Agent 产出 → 总结"
- LangGraph 的 `checkpointer` + 规划蓝图（`_build_planning_graph`）让多轮迭代有真实持久化

**不足**：
- **1749 行单文件**，没有任何类内职责拆分。`_setup_backends` / `_load_native_skills` / `_register_*` 全部塞在 `__init__` 里。`get_chat_response` 一个方法目测也是几百行。**单元测试几乎不可写**（这也是为什么 `test_custom_agent_loading.py` 失败后没人修）
- **降级到 tongyi 是硬编码**（orchestrator.py:744 等多处），`get_backend("tongyi")` 散落全文。万一以后要改默认后端，要全文搜索替换
- **没有"群聊 vs 单聊"的入口区分**——`Conversation.mode` 字段已建模但 Orchestrator 路由逻辑没用到。**所有会话都走规划路径**（性能浪费，简单对话也要等 5–10s）
- **失败降级会"伪装"成功**（line 749）："⚠️ 复杂任务调度遇到小问题，不过我依然可以帮你解答"——这其实是**用 tongyi 兜底**了。**没告诉用户原 Agent 失败**，属于悄悄降级，对调试不友好
- **没接 OpenCode 的 OpenCodeBackend 已经用 `provider = "opencode"` 注册成功**，但你刚刚加的它目前**没被任何已有 workflow 选用**——它只是"存在"，需要把 `custom_agents.yaml` 里一个 agent 切到 opencode 才有业务感知

### 2. 适配器层（LLMBackend）—— 架构优雅，但**只接了 2 个半** ⭐

**做得好**：
- `LLMBackend` ABC 抽象得**恰到好处**——只暴露 `chat / chat_stream / provider / model_name`，不绑死协议
- **刚加的 OpenCode Zen 一次接入 7 个免费模型**（含 Claude / GPT / DeepSeek 替代品），实际是"2+5"平台覆盖
- 三处接入点（`__init__.py` / `_setup_backends` / `VALID_ADAPTERS`）改动面小，**对新后端友好**

**不足**：
- **每加一个新后端都是复制粘贴**（`deepseek.py` 和 `opencode.py` 95% 雷同）。技术债在 N=3 时已经显形
- **`AgentCapability` 字段**在 `AgentSpec` schema 里是空壳——`capabilities: List[str]` 没有任何后端"上报自己支持什么"。这意味着 PRD 里说的"能力标签"无法真正用于自动派单
- **没有 Claude 原生 API**（Anthropic Messages API）。OpenCode Zen 兜了底，但 PRD 明确写"Claude Code + Codex"——评审老师若较真会问"你直接调过 Anthropic 吗"
- **没有 streaming 取消 / 心跳 / 重连**——chat_stream 跑断就只能等返回或超时

### 3. 自建 Agent（A 档配置）—— 做得对路但**全栈未闭环** ⭐

**做得好**：
- `memory_config` / `planning_config` / `validation_config` 三档 + 严格白名单（`agent_config.py`）——**这种严谨是 PRD 没要求但评审老师会加分的**
- `manage_agent` 工具化（`utils/manage_agent.py`）——Agent Builder 可以自己调用工具建 Agent，**这是 multi-agent 协作的实证**

**不足**：
- **DB 模型和 YAML 种子数据双源**（`custom_agents.yaml` + `CustomAgent` SQL 表），**Orchestrator 启动时只加载 YAML 里的**（orchestrator.py:1337 起的 `_load_custom_agents_from_db` 注释说要加载但实际加载顺序相反）
- **前端创建 Agent 后，刷新页面可能看不到**——DB 写入和 Orchestrator 内存注册没联动。看你 line 1410-1480 之间的代码，估计是手动 reload 才行
- **没有 Agent 版本管理**——A 档配置改了就是覆盖，没 diff/rollback

### 4. 数据模型 —— 70% 完整

**做得好**：
- `Message.mentions: JSON` + `Message.is_pinned` + `Message.meta_data` ——**PRD 里 "回复/引用/pin" 全部预留**
- `Conversation.participants: JSON` —— 群聊实现就靠它
- `Artifact` 表设计合理（type / content / meta_data）

**不足**：
- **Artifact 表是孤儿**：0 处代码写它、0 处代码读它。`Message.meta_data` 才是实际存产物的地方。**两套数据通道并存 → 前端不知道该信哪个**
- `Conversation.participants` 用了 JSON 而不是中间表。**群聊加/删 Agent 时要全文替换**——并发场景会丢更新
- `Message.content` 是 `String`（无限长但 SQL 不友好）。Agent 输出长 Markdown / 长代码会拖慢查询
- **没建索引**：`(conversation_id, created_at)` 没建，消息历史查询会全表扫

### 5. API 层 —— 8 个接口，够用但糙

**做得好**：
- REST 设计规范，JWT 鉴权落地
- `conversations.py` / `messages.py` / `agents.py` 拆分清晰

**不足**：
- **`backend/app/websocket.py` 是 0 字节空文件**——这意味着 PRD 要求的"群聊模式多 Agent 依次回复"在前端只能**等 N 秒后看到一坨**结果。**IM 实时性 = 0**
- `simple_chat` 和 `send_message` 两个端点**功能 80% 重叠**（chat.py:22 vs :130），且前者没有权限校验就改 `orchestrator.db_session`——**有竞态**（多用户并发时一个 session 被另一个用户串改）
- **没有流式响应端点**（`/api/chat/stream` 用 SSE 或 WebSocket）。typing 效果全靠前端假数据
- **没有 Agent 列表 API**——`/api/agents` 是用户自建 agent，但内置 agent（planner/code_reviewer 等）前端只能从某个 magic 接口拿
- **错误码不规范**：很多地方返回 200 + `{"ok": false, "error": ...}`——前端要判 ok 又要判 status code

### 6. 前端（`AgentHub-my flicker/index.html`）—— **大问题区** 🔴

**做得好**：
- 7933 行单文件 SPA，UI 看起来是完整的（IM 列表、聊天气泡、Artifact 卡片、Diff 视图、Agent 创建表单都画了）
- Material Symbols + Tailwind 设计语言统一
- 演示了 `diff-card` 渲染逻辑、`artifact.type === 'chart-line' / 'kpi'` 等真数据格式——**说明 UI 是有数据契约的**

**不足**：
- **0 处 WebSocket / SSE**——纯 HTTP。Agent 回复 5–10s 期间前端一片空白（PRD 强调"打字机效果"）
- **双后端并存**：`server/server.js`（Node/Express，旧）和 FastAPI 是**两套独立 API**。打开 index.html 实际请求的是旧 server，FastAPI 是为了"项目评级"另起炉灶。**两套数据不会同步**——演示时一定会在某个时刻数据对不上
- **API 路径假设错位**：从 index.html 看，它向 `/api/agents` 走的是自己的 server.js（看 server.js 内容），而 FastAPI 的 `/api/agents` 是另一套 schema。**必须二选一切掉一个**，否则 demo 时是"灵异事件"
- **Agent 创建表单**（line 7513 处）的 `llm_adapter` 下拉是写死的 `<option value="claude">Claude</option>`，没有 `opencode` 选项——**OpenCode 刚接进去但前端还没暴露给用户**
- **代码编辑器 / Diff 视图 / 全屏预览**只在 demo 数据里有，**真实运行时是占位**——PRD 核心体验直接掉档
- **没有响应式**：固定 1280px+ 设计，移动端/小屏直接糊

### 7. 测试 —— **0 保障**

- pytest 8 个测试文件，3 个在我介入前就 fail，且无人修复
- 没有任何 E2E / 集成测试
- `test_chat_api_flow.py` 验证"完整 chat 流程"——一旦该 fail，整个 demo 链路就废
- **没有 CI**——没有 GitHub Actions、没有 pre-commit

---

## 三、未开始任务的难度评估（按 PRD 5/6 部分）

### 🔴 难度 🔥🔥🔥 — 高风险，建议砍 P2 或合并

#### 1. **真正的群聊 + WebSocket 实时多 Agent 流式输出**
- **难度 🔥🔥🔥（高）**：要改造 backend 全面支持 WebSocket（当前文件 0 字节）+ 前端重写消息接收逻辑 + 后端用 SSE 或 queue 推送中间消息
- **建议**：先做**单聊 + SSE 流式**（实现简单、视觉差小），群聊体验可降级为"显示规划 + 一次性展示"——**评审老师主要看逻辑对不对，不一定要求 WebSocket**
- **实现路径**：
  - `backend/app/websocket.py` 实现 `WS /ws/conversations/{id}`，每条新消息 push 一次
  - 改 `chat.py` 的 `simple_chat` 改为 `StreamingResponse`（SSE），先把流式打字机做出来
  - 前端 `index.html` 把 `fetch` 改 `EventSource`，IM 流式就 80% 完工

#### 2. **产物（Artifact）从 0 到 1**
- **难度 🔥🔥🔥（中-高）**：后端要把 Artifact 真正"种"在消息上（前缀标识 ```artifact:code``` 或工具调用结果回写），前端要写 Monaco 编辑器集成 / iframe 沙箱
- **建议**：**先做 3 个最有冲击力的卡片**——`code`（语法高亮）、`html_preview`（iframe srcdoc）、`markdown`（marked.js）。**Diff / 部署 / PPT 全砍**也能 demo
- **实现路径**：
  - 改 `BaseAgent.process_message` 返回结构 `{"content": str, "artifacts": [{type, title, content}]}`
  - Orchestrator 聚合时把子 agent 的 artifacts 拼到 `intermediate_messages` 里
  - 前端写一个 `renderArtifact(artifact)` 统一渲染入口
  - 代码块用 highlight.js，HTML 用 `<iframe sandbox srcdoc>`

#### 3. **部署发布**
- **难度 🔥🔥🔥🔥（极高）**：涉及容器化、域名、CORS、生命周期管理——**竞赛时间严重不推荐**
- **建议**：**降级为"打包下载"**——Agent 生成文件 → 后端打成 zip → 前端下载。`backend/utils/file_converter.py` 已有文件处理基础，1 天能出
- **真要部署**：建议用 Vercel / Cloudflare Pages 的 webhook 思路（用户 push 到一个空 GitHub repo），2-3 天

#### 4. **多端支持**
- **难度 🔥🔥🔥🔥**：Electron / Tauri 桌面端各要 3-5 天
- **建议**：**完全砍掉**，在 PRD 里直接删 / 标 P3。竞争项目只看 web 端

### 🟡 难度 🔥🔥 — 中等，可以做

#### 5. **对话列表/置顶/归档/搜索**
- **难度 🔥🔥**：后端已有模型，前端 UI 已画，只缺搜索实现（SQLite FTS5 即可）
- **建议**：**1-2 天**。先把后端加 `GET /api/conversations?search=xxx&archived=true&pinned=true` + 前端把按钮接上

#### 6. **消息操作（回复/引用/重新生成/复制代码）**
- **难度 🔥🔥**：后端需要 `parent_message_id` 字段，前端要写引用的视觉
- **建议**：**砍掉"回复/引用"**（PRD 里没说必须做），**保留"重新生成"和"复制代码"**（1 天）

### 🟢 难度 🔥 — 容易加分

#### 7. **"长上下文 + 手动 pin"**
- **难度 🔥**：后端 `Message.is_pinned` 已有，前端缺 UI；Orchestrator 路由时把 pinned 消息总是带上即可
- **建议**：**0.5 天**，性价比极高

#### 8. **Agent 头像/能力标签**
- **难度 🔥**：后端 schema 加 `icon / tags` 字段，前端列表渲染
- **建议**：**0.5 天**。视觉加分大

---

## 四、行动建议（按竞赛节奏排）

### 🟢 1 周内必做（保住已有成果不崩）

1. **二选一统一后端**：要么把 FastAPI 部署到 8000 端口并改前端 baseURL；要么把 `index.html` 指向 FastAPI 后，把 `server/server.js` 整个删掉。**当前双轨一定在 demo 时炸**
2. **修 3 个 fail 测试**（你做 OpenCode 接入时已经发现根因了）
3. **把 `opencode` 加到前端的 `llm_adapter` 下拉**
4. **打 zip 下载 demo 备份**（保险）

### 🟡 2-3 周冲刺

5. **SSE 流式打字机**（chat.py → StreamingResponse + 前端 EventSource）—— **视觉冲击最大**
6. **3 个 Artifact 卡片**（code / html_preview / markdown）—— **核心体验**
7. **对话列表搜索 + 置顶 + 归档**
8. **加 1 个原生 Claude / OpenAI 适配器**（不依赖 OpenCode Zen）—— 应对评审"你真调过 Claude 吗"

### 🔴 砍掉 / 标 P2

9. 完整 Diff 视图 → **降级为简单高亮 diff**
10. 完整部署 → **降级为 zip 下载**
11. 桌面端 → **完全砍**
12. PPT 浏览 → **完全砍**

---

## 五、风险 & 评审视角

| 风险 | 概率 | 应对 |
|---|---|---|
| **演示时双后端数据对不上** | 🔴 高 | 立刻统一 baseURL |
| **慢响应被吐槽** | 🔴 高 | 必须做 SSE 流式 |
| **"这就是个 chatGPT 套壳"** | 🟡 中 | Artifact 卡片是杀手锏，**必须做出来** |
| **"你怎么证明接了多个平台"** | 🟡 中 | 加 Claude 原生 adapter + 在 UI 显眼处展示 provider |
| **"并发崩了"** | 🟡 中 | 加 1 个并发测试（`test_chat_api_flow` 已经在做） |
| **跑路/通宵** | 🟢 低 | 后端骨架已稳，不会崩 |

---

## 六、立即可做的 3 件事（不需要新设计）

1. **统一后端**（0.5 天）——改前端 baseURL，删 server.js
2. **SSE 流式**（1 天）——后端 `chat.py` 改 `StreamingResponse`，前端 `index.html` 加 `EventSource` 监听
3. **3 个 Artifact 卡片**（1-2 天）——改 `BaseAgent` 返回结构，前端 `renderArtifact` 入口

做完这三件事，**demo 体感会从"普通 chatbot"跳到"AI 协作平台"**，性价比最高。

---

需要我开始动哪一项？或者先把 `chat.py` 改成 SSE 流式（含 Artifact schema）让你看到效果？