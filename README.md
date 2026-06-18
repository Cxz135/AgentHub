<div align="center">

# 🤖 AgentHub

**多 Agent 协作平台 — 让多个 AI Agent 协同完成复杂任务**

用自然语言 @mention 不同的专业 Agent，由智能编排器自动协调分工，实现从简单问答到复杂多步骤任务的自动化协作。

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-vector-7B5EA7)](https://www.trychroma.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#-license)

</div>

---

## 👥 作者

本项目由两人协作完成：

| 成员 | GitHub | 负责内容 |
|------|--------|----------|
| **Cxz135** | [@Cxz135](https://github.com/Cxz135) | 后端开发（全部 `backend/` 模块）、Agent 系统开发、技术文档 |
| **Amory-ZDF** | [@Amory-ZDF](https://github.com/Amory-ZDF) | 前端开发（全部 `AgentHub-my flicker/` 目录）、产品需求文档 |

### 后端负责内容（[@Cxz135](https://github.com/Cxz135)）

- **Orchestrator 编排器**：消息路由决策引擎（5 级优先级）、动态规划调度、ReAct 工具调用、Agent Fallback 降级链
- **Agent 系统**：BaseAgent/CustomAgent 抽象、内置 Agent（Planner/Summarizer/CodeAnalyzer/RAG/Report/Vulnerability/AgentBuilder）、自定义 Agent CRUD、A-Tier 可配置（记忆/规划/校验三策略独立可配）
- **记忆框架**：5 层记忆体系（指令记忆 / 短期记忆 / 工作记忆 / 摘要记忆 / 长期语义记忆）、LLM 驱动事实提取、ChromaDB 语义检索、艾宾浩斯衰减、用户画像
- **LLM 后端层**：统一抽象接口（`LLMBackend`）、三后端实现（Tongyi/DeepSeek/OpenCode）、启动健康检查、流式/非流式双模式
- **LangGraph 工作流**：动态规划图（execute → evaluate → replan → summarize）、固定工作流（RAG/CodeReview）、ReplanEvaluator 两层决策
- **RAG 知识库**：ChromaDB 向量存储 + DashScopeEmbeddings 嵌入、文档 MD5 去重、RecursiveCharacterTextSplitter 分块
- **Skill 系统**：双轨 Skill（工具类/能力类）、Skill 市场（发布/安装/Fork/版本管理）
- **API 层**：FastAPI REST API + SSE 流式 + JWT 鉴权
- **数据库模型**：SQLAlchemy ORM、9 张业务表、启动时自动 Schema 迁移
- **工具函数**：web_search（搜索结果清洗提纯）、rag_retrieval、file_converter、manage_agent、manage_skill、code_scanner

### 前端负责内容（[@Amory-ZDF](https://github.com/Amory-ZDF)）

- 单页应用（`AgentHub-my flicker/index.html`，约 417KB）
- 16 个 JS 模块：聊天界面、会话管理、Agent 管理、Skill 市场、知识库面板、SSE 流式客户端、WebSocket 客户端等
- Tailwind CSS + Material Design 主题
- 技术栈：原生 HTML/JS + Tailwind CSS (CDN) + Material Symbols + pdf.js/mammoth.js/SheetJS

---

## 📖 目录

- [项目简介](#-项目简介)
- [核心特性](#-核心特性)
- [技术栈](#-技术栈)
- [架构概览](#-架构概览)
- [目录结构](#-目录结构)
- [快速开始](#-快速开始)
- [致谢与文档](#-致谢与文档)
- [License](#-license)

---

## 🌟 项目简介

**AgentHub** 是一个面向复杂任务自动化的多 Agent 协作平台。

不同于传统的「单 Agent 对话」模式，AgentHub 的一大特色是 **智能编排器（Orchestrator）** 作为中央大脑——接收用户消息后自动判断任务复杂度，然后将任务路由到最合适的处理路径：简单问题直接回复，中等复杂度交给专家 Agent，复杂任务则由 PlannerAgent 自动拆解为子任务并通过 LangGraph 并行调度执行。

核心亮点：
- 🧠 **智能路由**：5 级优先级决策链，支持 @mention 多 Agent 群聊、关键词触发固定工作流、LLM 复杂度分类动态规划
- 🔄 **动态规划**：LangGraph StateGraph 驱动的任务分解 → 并行执行 → 评估 → 重规划 → 汇总闭环
- 🧩 **记忆系统**：5 层记忆框架，LLM 驱动的事实提取 + ChromaDB 语义检索 + 艾宾浩斯衰减，实现跨会话的个性化体验
- 🔌 **多 LLM 后端**：Tongyi(Qwen) / DeepSeek / OpenCode 三后端统一抽象，支持 fallback 降级链
- 🛠️ **双轨 Skill**：工具类 Skill（可执行函数 + LangChain Tool + ReAct 循环）+ 能力类 Skill（Markdown Prompt 注入）

> 详细产品需求见 [`AgentHub — 多 Agent 协作平台 · 产品需求文档.md`](./AgentHub%20—%20多%20Agent%20协作平台%20·%20产品需求文档.md)（Amory-ZDF 撰写）。
> 详细技术架构见 [`AgentHub_技术文档.md`](./AgentHub_技术文档.md)（Cxz135 撰写）。

---

## ✨ 核心特性

- 🎯 **智能编排**：5 级优先级路由 — @mention → Agent 管理 → 工作流匹配 → 复杂度分类 → 默认聊天
- 🤝 **多 Agent 协作**：PlannerAgent 拆解任务 → 并行/串行子任务执行 → ReplanEvaluator 两层决策（硬条件 + LLM 语义）→ Summarizer 汇总
- 🧩 **5 层记忆**：指令记忆 / 短期记忆（滑动窗口/摘要压缩）/ 工作记忆 / 摘要记忆 / 长期语义记忆（ChromaDB + DashScopeEmbeddings）
- 🔄 **ReAct 工具调用**：LangChain Tool 封装，支持 web_search、rag_retrieval、file_converter、scan_vulnerabilities 等
- 🛒 **Skill 市场**：工具类 + 能力类双轨 Skill，支持 Fork / 发布 / 安装 / 版本管理
- 📚 **RAG 知识库**：ChromaDB 向量存储，支持 PDF/TXT 上传，MD5 去重，语义检索
- ⚙️ **A-Tier 配置**：每个 Agent 独立配置记忆策略（none/sliding_window/summary）、规划模式（direct/react/plan_execute）、校验策略（none/rules/llm_judge）
- 🔐 **JWT 鉴权**：Email + 密码注册登录，bcrypt 哈希
- 📡 **流式输出**：SSE 流式 + 打字机效果，支持 intermediate 进度消息和 artifact 产出物推送
- 🛡️ **容错降级**：LLM 后端启动健康检查 + Agent Fallback 链 + Replan 硬上限 + 工作流失败降级

---

## 🛠 技术栈

### 后端
| 技术 | 用途 |
|------|------|
| FastAPI | Web 框架（异步高性能） |
| LangGraph | Agent 编排引擎（StateGraph + 条件边 + Checkpointer） |
| LangChain | Tool 封装 + ReAct AgentExecutor |
| SQLAlchemy | ORM（支持 SQLite/PostgreSQL） |
| SQLite | 主数据库（agenthub.db）+ Checkpointer（agenthub_memory.sqlite） |
| ChromaDB | 向量存储（RAG 文档 + 长期记忆） |
| DashScopeEmbeddings | 文本嵌入（text-embedding-v4） |
| httpx | 异步 HTTP 客户端（LLM API 调用） |
| PyJWT / passlib | JWT 签发与 bcrypt 密码哈希 |
| PyYAML | Prompt 模板管理 |

### LLM 后端
| 后端 | 模型 | 用途 |
|------|------|------|
| Tongyi (DashScope) | qwen-plus / qwen-long | 默认后端，中文优化 |
| DeepSeek | deepseek-chat / deepseek-coder | 代码生成与审查 |
| OpenCode Zen | deepseek-v4-flash-free / big-pickle 等 7 款 | 免费档，demo/轻量使用 |

### 前端
| 技术 | 用途 |
|------|------|
| 原生 HTML + JavaScript | 单页应用，16 个 JS 模块 |
| Tailwind CSS (CDN) | 样式系统 |
| Material Symbols | 图标 |
| pdf.js / mammoth.js / SheetJS | 客户端文档解析 |

---

## 🏗 架构概览

```
用户 → FastAPI (REST/SSE)
         │
         ├─ /api/chat ──── Orchestrator (中央编排器) ─── Agent 注册表
         ├─ /api/agents                              ├── 工作流注册表
         ├─ /api/skills                              ├── LLM 后端池
         ├─ /api/knowledge                           └── Skill 仓库
         ├─ /api/memory
         └─ /api/missions                                  │
                                                           │
         ┌─────────────────────────────────────────────────┤
         │                                                 │
         ▼                                                 ▼
  路由决策引擎                                       LangGraph
  ├─ 1. @mention 检测                               ├─ 动态规划图
  ├─ 2. Agent 管理请求                               │   execute_tasks
  ├─ 3. 工作流关键词匹配                              │   → evaluate_results
  ├─ 4. LLM 复杂度分类                               │   → replan/degrade
  │   ├─ complex → PlannerAgent + LangGraph          │   → generate_summary
  │   ├─ moderate → 专家 Agent                      ├─ RAG 工作流
  │   └─ simple → 直接 LLM 回复                      └─ CodeReview 工作流
  └─ 5. 默认聊天
```

---

## 📂 目录结构

```
AgentHub/
├── backend/                          # Python 后端（Cxz135）
│   ├── app/                          # FastAPI 应用层
│   │   ├── main.py                   # 入口 + 生命周期管理
│   │   ├── api/                      # API 路由
│   │   │   ├── chat.py               # 聊天核心 (POST + SSE 流式)
│   │   │   ├── auth.py               # 用户认证 (JWT)
│   │   │   ├── agents.py             # Agent CRUD + AI 提示词优化
│   │   │   ├── conversations.py      # 会话管理
│   │   │   ├── messages.py           # 消息管理
│   │   │   ├── skills.py             # Skill 市场 (Fork/发布/安装)
│   │   │   ├── knowledge.py          # RAG 知识库 (上传/搜索/删除)
│   │   │   ├── attachments.py        # 文件上传
│   │   │   └── artifacts_api.py      # 产物管理
│   │   ├── dependencies.py           # 依赖注入
│   │   └── schemas.py                # Pydantic Schema
│   ├── agents/                       # Agent 系统
│   │   ├── base_agent.py             # BaseAgent 抽象类
│   │   ├── custom_agent.py           # CustomAgent (用户自定义)
│   │   └── internal/                 # 内置 Agent
│   │       ├── planner_agent.py      # 任务规划 + JSON 计划生成
│   │       ├── summarizer_agent.py   # 内容摘要
│   │       ├── code_analyzer_agent.py
│   │       ├── rag_agent.py
│   │       ├── report_generator_agent.py
│   │       └── vulnerability_scanner_agent.py
│   ├── core/                         # 核心编排
│   │   ├── orchestrator.py           # 中央编排器 (主要入口)
│   │   ├── graph_state.py            # LangGraph GraphState 定义
│   │   ├── memory_strategy.py        # 记忆策略 (none/sliding_window/summary)
│   │   ├── validation_strategy.py    # 校验策略 (none/rules/llm_judge)
│   │   ├── replan_evaluator.py       # 重规划评估器 (两层决策)
│   │   ├── plan_analyzer.py          # 计划复杂度分析器 (三维度)
│   │   ├── quality_checker.py        # 输出质量检查 (must_include/must_not_include)
│   │   ├── response_checker.py       # 响应完整性检查
│   │   ├── agent_protocol.py         # Agent 通信协议
│   │   └── config.py                 # 全局配置常量
│   ├── memory/                       # 5 层记忆框架
│   │   ├── manager.py                # MemoryManager (中央编排)
│   │   ├── base.py                   # 抽象基类 + 数据结构
│   │   ├── instruction_memory.py     # 指令记忆 (系统约束)
│   │   ├── short_term_memory.py      # 短期记忆 (对话窗口)
│   │   ├── working_memory.py         # 工作记忆 (任务状态)
│   │   ├── summary_memory.py         # 摘要记忆 (历史压缩)
│   │   └── long_term_memory.py       # 长期语义记忆 (ChromaDB)
│   ├── services/                     # 业务服务
│   │   ├── memory_service.py         # 记忆编排 (augment_context + on_conversation_turn)
│   │   ├── memory_extractor.py       # LLM 驱动事实提取 (fact/preference/decision/user_trait)
│   │   ├── memory_retriever.py       # ChromaDB 语义检索
│   │   ├── memory_decayer.py         # 艾宾浩斯衰减
│   │   ├── user_profiler.py          # 用户画像
│   │   ├── conversation_service.py
│   │   └── message_service.py
│   ├── llm/                          # LLM 后端层
│   │   ├── backend.py                # LLMBackend 抽象接口
│   │   └── backends/
│   │       ├── tongyi_backend.py     # 阿里云 Tongyi/Qwen
│   │       ├── deepseek.py           # DeepSeek
│   │       └── opencode.py           # OpenCode Zen (7 款免费模型)
│   ├── rag/                          # RAG 知识库
│   │   └── vector_store.py           # ChromaDB + DashScopeEmbeddings
│   ├── workflows/                    # 工作流定义
│   │   ├── rag_workflow.py           # RAG (retrieve → summarize)
│   │   └── code_review_workflow.py   # CodeReview (analyze → scan → report)
│   ├── models/                       # ORM 数据模型
│   ├── skills/                       # 能力类 Skill (Markdown)
│   ├── utils/                        # 工具函数
│   │   ├── web_search.py             # 网络搜索 (清洗管道 + 去重排序)
│   │   ├── rag_retrieval.py          # RAG 检索
│   │   ├── file_converter.py         # 文件转换
│   │   ├── manage_agent.py           # Agent 管理工具
│   │   ├── manage_skill.py           # Skill 管理工具
│   │   └── code_scanner.py           # 漏洞扫描
│   ├── config/                       # 配置文件
│   │   ├── chroma.yaml               # ChromaDB 参数
│   │   ├── custom_agents.yaml        # 5 个预置 Agent 定义
│   │   └── prompts/                  # YAML Prompt 模板库
│   ├── db/                           # 数据库引擎
│   └── test/                         # 测试文件
├── AgentHub-my flicker/              # 前端 SPA（Amory-ZDF）
│   ├── index.html                    # 主页面 (约 417KB)
│   ├── js/                           # 16 个 JS 模块
│   │   ├── chat.js                   # 聊天核心逻辑
│   │   ├── dashboard.js              # 控制面板
│   │   ├── agent_detail.js           # Agent 详情页
│   │   ├── skill_detail.js           # Skill 详情页
│   │   ├── knowledge.js              # 知识库管理
│   │   ├── sse.js                    # SSE 流式客户端
│   │   ├── websocket.js              # WebSocket 客户端
│   │   └── ...                       # 其他模块
│   └── stitch_agenthub_design_system/
├── chroma_db/                        # ChromaDB 向量存储数据
├── data/                             # 上传的知识库文件
├── AgentHub_技术文档.md               # 技术文档（Cxz135）
└── AgentHub — ...产品需求文档.md       # PRD（Amory-ZDF）
```

---

## 🚀 快速开始

### 环境要求
- Python 3.10+
- pip

### 安装与启动

```bash
# 1. 进入后端目录
cd backend

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量（创建 .env 文件）
cat > .env << EOF
DEEPSEEK_API_KEY=your_deepseek_api_key
DASHSCOPE_API_KEY=your_dashscope_api_key
JWT_SECRET=your_jwt_secret
WEBSEARCH_API_KEY=your_bce_api_key
OPENCODE_API_KEY=your_opencode_api_key
MEMORY_ENABLED=true
EOF

# 4. 启动服务（默认端口 8000，同时托管前端）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

打开浏览器访问 👉 **http://localhost:8000**

> 💡 服务首次启动会自动：建表、迁移缺失列、种子数据写入、Orchestrator 初始化（LLM 后端健康检查 + Agent 注册 + 工作流加载）。

### 配置说明

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `DASHSCOPE_API_KEY` | 阿里云 DashScope (Qwen) API Key | - |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | - |
| `OPENCODE_API_KEY` | OpenCode Zen API Key | - |
| `JWT_SECRET` | JWT 签名密钥 | - |
| `WEBSEARCH_API_KEY` | 百度搜索 API Key (千帆) | - |
| `MEMORY_ENABLED` | 是否启用多层记忆 | `false` |
| `DATABASE_URL` | 数据库连接字符串 | `sqlite:///./agenthub.db` |

---

## 📚 致谢与文档

- [`AgentHub_技术文档.md`](./AgentHub_技术文档.md) — 完整技术架构文档（Cxz135）
- [`AgentHub — 多 Agent 协作平台 · 产品需求文档.md`](./AgentHub%20—%20多%20Agent%20协作平台%20·%20产品需求文档.md) — PRD（Amory-ZDF）
- [`AgentHub- 多Agent协作平台设计.pdf`](./AgentHub-%20多Agent协作平台设计.pdf) — 设计稿

---

## 📄 License

MIT © 2025 [@Cxz135](https://github.com/Cxz135) & [@Amory-ZDF](https://github.com/Amory-ZDF)

---

<div align="center">

如果这个项目对你有启发，欢迎点亮 ⭐ Star

</div>
