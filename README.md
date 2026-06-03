<div align="center">

# 🤖 AgentHub

**以「Agent 集群」为单位的多 Agent 协作工作台**

每个 Mission 封装一类重复性任务的稳定班底（Agent + Skill），用户进入模块后用自然语言反复执行任务、迭代班底，所有编辑都在模块内原地完成。

[![Node.js](https://img.shields.io/badge/Node.js-%3E%3D18-339933?logo=node.js&logoColor=white)](https://nodejs.org/)
[![Express](https://img.shields.io/badge/Express-4.21-000000?logo=express&logoColor=white)](https://expressjs.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-CDN-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#-license)
[![Status](https://img.shields.io/badge/status-WIP-orange)]()

</div>

---

## 📖 目录

- [项目简介](#-项目简介)
- [核心特性](#-核心特性)
- [技术栈](#-技术栈)
- [目录结构](#-目录结构)
- [快速开始](#-快速开始)
- [Roadmap](#-roadmap)
- [致谢与文档](#-致谢与文档)
- [License](#-license)

---

## 🌟 项目简介

**AgentHub** 是一个面向「重复性任务自动化」的多 Agent 协作平台 Demo。

不同于传统的「单聊单 Agent」模式，AgentHub 将一类任务所需的 **Agent 班底 + Skill 工具集** 封装为一个 **Mission 模块**——用户进入模块后即可用自然语言反复触发任务，并在使用过程中不断迭代班底配置。所有编辑（增删 Agent、调整 Skill、修订知识库）都在模块内原地完成，无需切换页面。

> 详细的产品需求与交互定义见仓库内 [`AgentHub — 多 Agent 协作平台 · 产品需求文档.md`](./AgentHub%20—%20多%20Agent%20协作平台%20·%20产品需求文档.md)。

## ✨ 核心特性

- 🎯 **Mission 班底**：将「Agent + Skill + 知识库 + Prompt」打包为可复用的任务模块
- 🛒 **Skill 市场**：内置 demo skills（新闻摘要、KPI 抽取、SQL 查询、翻译、会议纪要等），支持 Fork / 发布 / 安装 / 版本回滚
- 📚 **本地知识库解析**：浏览器端直接解析 **PDF / DOCX / XLSX**（pdf.js + mammoth + SheetJS），无需上传服务器
- 🔐 **JWT 鉴权**：Email + 密码注册登录，bcrypt 哈希，Token TTL 7 天
- 💾 **零依赖部署**：SQLite（better-sqlite3 同步 API + WAL 模式），单一可执行进程同时托管前端与 API
- 🎨 **Material Design 主题**：基于 Stitch 设计系统的暖色调配色，支持 light / dark 切换
- 📦 **单文件前端**：所有 UI 与状态逻辑集中在 `index.html`，便于审阅与二次定制

## 🛠 技术栈

### 前端
| 技术 | 用途 |
| --- | --- |
| 原生 HTML + JavaScript | 单页应用，无构建步骤 |
| Tailwind CSS (CDN) | 样式系统 + 主题 token |
| Material Symbols | 图标 |
| pdf.js / mammoth.js / xlsx (SheetJS) | 客户端文档解析 |

### 后端
| 技术 | 用途 |
| --- | --- |
| Express 4 | HTTP 框架 |
| better-sqlite3 | 同步 SQLite 驱动（WAL 模式） |
| bcryptjs | 密码哈希 |
| jsonwebtoken | JWT 签发与校验 |
| cors | 跨域 |

## 📂 目录结构

```
AgentHub/
├── index.html                                  # 单页前端（UI + 状态机 + 文档解析）
├── server/
│   ├── server.js                               # Express API + 静态托管入口
│   ├── db.js                                   # SQLite 建表 + 内置 demo skills 种子
│   ├── data.sqlite                             # SQLite 数据文件（首次运行自动生成）
│   └── package.json
├── stitch_agenthub_design_system/              # Stitch 设计系统输出（视觉规格参考）
├── AgentHub — ……产品需求文档.md                # PRD
└── README.md                                   # 当前文件
```

## 🚀 快速开始

### 环境要求
- Node.js ≥ 18
- npm（或 pnpm / yarn）

### 安装与启动

```bash
# 1. 进入后端目录
cd server

# 2. 安装依赖
npm install

# 3. 启动服务（默认端口 3030，同时托管前端 index.html）
npm start
```

打开浏览器访问 👉 **http://localhost:3030**

> 💡 服务首次启动会自动建表，并向 `skills` 表写入一批官方 demo（news_summary / stock_kpi_extract / image_caption / sql_query / translate_zh_en / meeting_minutes …）。

### 配置说明
当前 Demo 阶段以下参数硬编码于 `server/server.js`，生产部署时建议改为环境变量：

| 项 | 默认值 |
| --- | --- |
| `PORT` | `3030` |
| `JWT_SECRET` | `agenthub-demo-secret-change-in-production` |
| `TOKEN_TTL` | `7d` |

## 🗺 Roadmap

参考 PRD 的 P0 / P1 / P2 划分：

- [x] **P0** — 注册登录、Skill 市场 / 个人库 CRUD、Fork & Publish、Token 鉴权
- [x] **P0** — 客户端 PDF / DOCX / XLSX 知识库解析
- [ ] **P1** — Mission 模板库、Agent 班底可视化编辑
- [ ] **P1** — Skill 版本 Diff 与一键回滚 UI
- [ ] **P2** — 多 Agent 协作运行时、第三方 Agent 平台接入
- [ ] **P2** — 任务执行流可观测性（Trace / Log / Cost）

## 📚 致谢与文档

- [`AgentHub — 多 Agent 协作平台 · 产品需求文档.md`](./AgentHub%20—%20多%20Agent%20协作平台%20·%20产品需求文档.md) · 完整 PRD
- [`AgentHub- 多Agent协作平台设计.pdf`](./AgentHub-%20多Agent协作平台设计.pdf) · 设计稿
- `stitch_agenthub_design_system/` · Stitch 视觉规格

## 📄 License

MIT © 2025 [@zhangdifei03](https://github.com/zhangdifei03)

---

<div align="center">

如果这个项目对你有启发，欢迎点亮 ⭐ Star

</div>
