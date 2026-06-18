# AgentHub 项目指南

## 项目结构

```
AgentHub_/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/             # API 路由
│   │   │   ├── attachments.py    # 文件上传/下载/网页预览
│   │   │   ├── auth.py           # 认证 (注册/登录)
│   │   │   ├── chat.py           # 聊天接口
│   │   │   ├── conversations.py  # Mission/对话管理
│   │   │   ├── messages.py       # 消息操作 (pin/regenerate/quote)
│   │   │   ├── websocket.py      # WebSocket 流式聊天
│   │   │   └── ...
│   │   ├── main.py          # 应用入口 (CORS/数据库修复/路由挂载)
│   │   └── schemas.py       # Pydantic 模型
│   ├── core/                # 核心编排器 (Orchestrator)
│   ├── models/              # SQLAlchemy 模型
│   ├── services/            # 业务逻辑 (ConversationService)
│   └── utils/               # 工具函数 (file_converter.py)
├── AgentHub-my flicker/   # 前端单页应用
│   ├── index.html           # HTML 入口 (已重构为模块化)
│   └── js/                  # 前端 JS 模块
│       ├── utils.js         # 工具函数 ($, escapeHTML, etc.)
│       ├── state.js         # 全局状态 + SideNav/TopBar
│       ├── dashboard.js     # 仪表盘渲染
│       ├── chat.js          # 聊天核心 (气泡/输入/产物/下载)
│       ├── editor_panel.js  # 右侧编辑器面板
│       ├── chat_modals.js   # 聊天相关弹窗
│       ├── pages.js         # Agents/Skills/Settings 页面
│       ├── agent_detail.js  # Agent 详情页
│       ├── skill_detail.js  # Skill 详情页
│       ├── version_diff.js  # 版本对比
│       ├── knowledge.js     # 知识库 (RAG) 全功能
│       ├── settings_quickrun.js  # 设置/快速运行
│       ├── chat_interactions.js  # 发送消息/mention/群聊
│       ├── sse.js           # SSE 流解析
│       ├── websocket.js     # WebSocket 连接管理
│       └── api_auth.js      # API 封装 + 认证 + 初始化
```

## 启动方式

```bash
# 后端
cd backend
PYTHONPATH=/Users/henryjin/PycharmProjects/AgentHub_ python -m uvicorn app.main:app --port 8000 --reload

# 前端
# 直接访问 http://localhost:8000 (后端已挂载静态文件)
```

## 近期修改记录

### 2026-06-10 功能修复与重构

#### 1. 消息实时 Pin (置顶)
- **前端**：`renderMessageActions` 中新增 pin/unpin 按钮，调用 `toggleMessagePin(dbId, idx)`
- **后端**：`POST /api/conversations/{id}/messages/{id}/pin` 已存在并正常工作
- **状态**：`openMission` 加载历史消息时保留 `isPinned` 字段
- **广播**：pin 后通过 WebSocket 发送 `pin_update` 事件（多标签页同步）

#### 2. 文件下载（认证）
- **新增端点**：`GET /api/attachments/{user_id}/{filename}/download`
- **权限**：仅允许文件所有者下载（检查 `current_user.id == user_id`）
- **防遍历**：`realpath` 检查确保文件在 `UPLOAD_DIR` 内
- **前端**：附件卡片点击调用 `downloadAttachment(url, name)`，使用 `fetch` + `Blob` 下载，失败则降级到 `window.open`

#### 3. Mentions 持久化
- **问题**：`messages.mentions` 列从未被写入
- **修复**：`websocket.py` 和 `chat.py` 在保存用户消息时，解析 `@AgentName` 正则匹配，与 `conversation.squad_config.agents` 比对，将匹配到的 agent ID 存入 `mentions` 列
- **正则**：`r'@([\w\u4e00-\u9fa5]+)'` 匹配中/英文 agent 名
- **前端**：`openMission` 加载历史消息时保留 `mentions` 字段

#### 4. 数据库自动修复
- **问题**：旧数据库缺少 `messages.is_pinned/mentions/meta_data` 和 `conversations.last_active_at/is_pinned/is_archived/mode/participants`
- **修复**：`main.py` 的 `lifespan` 中自动 `ALTER TABLE` 添加缺失列
- **注意**：SQLite 限制，`DATETIME` 列不能加 `DEFAULT CURRENT_TIMESTAMP`，已改为不加默认值

#### 5. 前端 HTML 重构
- **从**：单文件 `index.html` (~9800 行)
- **到**：`index.html` (HTML 壳 + 外部 JS 引用) + `js/` 目录 (16 个模块)
- **模块划分**：
  1. `utils.js` - 基础工具
  2. `state.js` - 全局状态 + 导航栏
  3. `dashboard.js` - 仪表盘
  4. `chat.js` - 聊天渲染 + 产物面板 + 下载
  5. `editor_panel.js` - 右侧编辑器
  6. `chat_modals.js` - 弹窗组件
  7. `pages.js` - Agents/Skills 页面
  8. `agent_detail.js` - Agent 详情
  9. `skill_detail.js` - Skill 详情
  10. `version_diff.js` - 版本对比
  11. `knowledge.js` - 知识库
  12. `settings_quickrun.js` - 设置
  13. `chat_interactions.js` - 消息发送/mention/群聊
  14. `sse.js` - SSE 流
  15. `websocket.js` - WebSocket
  16. `api_auth.js` - API + 认证 + 初始化

#### 6. Squad Config 修复
- **问题**：`create_mission` 读取 `mission_in.get("squad")`，但前端传入 `squad_config`
- **修复**：改为 `mission_in.get("squad_config") or mission_in.get("squad", {})`

## 关键 API 端点

| 功能 | 端点 | 方法 |
|------|------|------|
| 注册 | `/api/register` | POST |
| 登录 | `/api/login` | POST |
| Mission 列表 | `/api/missions` | GET |
| 创建 Mission | `/api/missions` | POST |
| Mission 置顶 | `/api/missions/{id}/pin` | PUT |
| 消息列表 | `/api/chat/{conv_id}/messages` | GET |
| 消息置顶 | `/api/conversations/{id}/messages/{msg_id}/pin` | POST |
| 重新生成 | `/api/messages/{id}/regenerate` | POST |
| 引用 | `/api/messages/{id}/quote` | POST |
| 文件上传 | `/api/upload` | POST |
| 文件下载 | `/api/attachments/{uid}/{filename}/download` | GET |
| 网页预览 | `/api/preview` | POST |
| WebSocket | `/ws/{conversation_id}` | WS |

## 数据库 Schema

### conversations
- `id` (INTEGER, PK)
- `user_id` (INTEGER, FK)
- `title` (VARCHAR)
- `created_at/updated_at/last_active_at` (DATETIME)
- `is_pinned/is_archived` (BOOLEAN)
- `mode` (VARCHAR, default='single')
- `participants` (JSON)
- `squad_config` (JSON)

### messages
- `id` (INTEGER, PK)
- `conversation_id` (INTEGER, FK)
- `agent_id` (VARCHAR)
- `content` (VARCHAR, JSON 字符串)
- `message_type` (VARCHAR)
- `meta_data` (JSON)
- `is_pinned` (BOOLEAN)
- `mentions` (JSON)
- `created_at/updated_at` (DATETIME)

## 注意事项

1. **前端重构后**：所有 JS 文件必须按正确顺序加载（`utils.js` → `state.js` → ... → `api_auth.js`）
2. **DOMContentLoaded**：`api_auth.js` 末尾监听 `DOMContentLoaded`，调用 `bootstrapAuth()` 和 `render()`
3. **全局变量**：`state`, `getMission()`, `getRun()`, `API_BASE`, `WS_BASE` 等均为全局变量
4. **文件上传**：限制 20MB，支持图片/文档/音视频/压缩包
5. **产物过滤**：同消息多代码块只取最大（≥5行），单一代码块≥3行才纳入产物面板
