# 示例手册索引

本目录包含了一套完整的 AI 协作开发规范模板，可直接复制到新项目中使用。

> **🤖 给 AI Agent**：这是模板目录。当前项目的实际记录在 `../AgentHub-records/`。如需了解项目历史和踩坑记录，请先读那里。

---

## 目录结构

```
example-manual/
├── README.md                     # 本文件：模板索引与使用指南
├── spec/                         # 规范文档（定义"是什么"）
│   ├── tech-stack.md             # 技术栈定义 — 新项目启动时填
│   ├── api-contract.md           # 前后端接口协议（含 WebSocket 格式） — 涉及 API 时读
│   ├── project-structure.md      # 目录职责规范 — 新增模块/移动文件时读
│   ├── user-journey.md           # 用户链路（含 AI 协作元流程） — 新功能开发前读
│   └── knowledge-management.md   # 知识管理体系 — 会话开始/结束时读
├── skill/                        # 技能文档（定义"怎么做"）
│   ├── code-generation.md        # 代码生成技能 — 写新代码时读
│   ├── debugging.md              # 调试技能 — 排查问题时读
│   └── code-review.md            # 代码审查技能 — 审查 PR/变更时读
├── rules/                        # 规则文档（定义"不能做什么"）
│   ├── logging.md                # 日志规范 — 任何代码修改时读
│   ├── testing.md                # 测试规范 — 写/改测试时读
│   ├── ai-decision.md            # AI 决策规范 — 加判断逻辑时读
│   ├── code-structure.md         # 代码结构规范 — 移动文件/重构时读
│   ├── api-consistency.md        # 接口一致性规范 — 改 API 时读
│   └── definition-of-done.md     # 完成定义 — 标记任务完成时读
└── templates/                    # 空白模板（新项目快速启动）
    ├── todo-template.md          # 待办事项模板
    ├── gotcha-template.md        # 踩坑日志模板（含速查索引）
    ├── deprecated-template.md    # 废弃方案模板
    └── decision-template.md      # 决策记录模板
```

---

## 📍 使用方式

### 新项目启动

1. 复制 `example-manual/` 到新项目
2. 根据项目需求填写 `spec/tech-stack.md`
3. 定义 `spec/api-contract.md`
4. 规划 `spec/user-journey.md`
5. 确认 `spec/project-structure.md`

### 开发过程中（按任务类型）

| 任务类型 | 先读 | 再读 | 产出 |
|----------|------|------|------|
| 写新功能 | `spec/tech-stack.md`, `spec/api-contract.md` | `skill/code-generation.md`, `rules/logging.md` | 代码 + 日志 + 测试 |
| 修改已有代码 | `rules/code-structure.md` | `rules/api-consistency.md`, `rules/testing.md` | 修改 + 自审查 |
| Debug | `skill/debugging.md`, `../AgentHub-records/gotcha.md` | `rules/logging.md` | 修复 + gotcha 记录 |
| 改 API | `spec/api-contract.md`, `rules/api-consistency.md` | `rules/testing.md` | 两端修改 + curl 验证 |
| 重构 | `rules/code-structure.md` | `rules/testing.md`, `rules/definition-of-done.md` | 影响分析 + 分步执行 |
| 写测试 | `rules/testing.md` | `skill/code-generation.md` | 测试 + 反例验证 |
| 审查代码 | `skill/code-review.md` | 涉及的 `rules/` | 审查报告 |
| 做决策 | `rules/ai-decision.md`, `../AgentHub-records/decisions/` | `spec/tech-stack.md` | 决策记录 |

### 会话中断后

- 新会话先读取 `../AgentHub-records/todo.md`
- 检查 `../AgentHub-records/deprecated/` 了解废弃方案
- 检查 `../AgentHub-records/gotcha.md` 了解踩坑记录（先看速查索引）
- 查看 `../AgentHub-records/decisions/` 了解决策记录

---

## 🔗 文件间依赖关系

> 以下关系图帮助理解文件的互相引用。箭头方向 = "需要参考"。

```
readme.md (总入口，含路由表)
  ├── spec/
  │   ├── tech-stack.md ────────────── 被 code-generation 引用
  │   ├── api-contract.md ──────────── 被 api-consistency 引用
  │   ├── project-structure.md ─────── 被 code-structure 引用
  │   ├── user-journey.md ──────────── 被 definition-of-done 引用
  │   └── knowledge-management.md ──── 被所有文件引用（todo/gotcha 管理）
  ├── skill/
  │   ├── code-generation.md ───────── 引用 rules/logging, rules/testing
  │   ├── debugging.md ─────────────── 引用 rules/logging
  │   └── code-review.md ───────────── 引用所有 rules/ 文件
  └── rules/
      ├── logging.md ───────────────── 被 code-generation, debugging 引用
      ├── testing.md ───────────────── 被 code-review, definition-of-done 引用
      ├── ai-decision.md ───────────── 独立 / 被 code-review 引用
      ├── code-structure.md ────────── 独立 / 被 code-review 引用
      ├── api-consistency.md ───────── 独立 / 被 code-review 引用
      └── definition-of-done.md ────── 独立 / 被 code-review 引用
```

---

## 扩展建议

### 添加新技能

1. 在 `skill/` 目录创建新文件
2. 在文件头部标注：`> **📎 何时读此文件**: [触发条件]`
3. 定义技能名称、描述、触发条件
4. 编写详细流程
5. 添加示例
6. 在文件底部添加相关文件交叉引用
7. 更新本 README 的文件列表和依赖关系图

### 添加新规则

1. 在 `rules/` 目录创建新文件
2. 在文件头部标注：`> **📎 何时读此文件**: [触发条件]`
3. 定义规则名称、说明
4. 列出禁止行为
5. 提供正确示例
6. 添加检查清单
7. 在文件底部添加相关文件交叉引用
8. 更新 `skill/code-review.md` 中的审查清单
9. 更新本 README 的文件列表和依赖关系图

### 更新规范

- 每次项目结束后回顾
- 更新 `spec/` 目录
- 记录新的踩坑经验到 `../AgentHub-records/gotcha.md`
- 更新 `../AgentHub-records/todo.md`

---

## 示例：快速启动新项目

```bash
# 1. 复制规范模板
mkdir -p new-project/AI协作开发
cp -r example-manual/* new-project/AI协作开发/

# 2. 复制空白模板作为初始记录文件
cp new-project/AI协作开发/templates/todo-template.md new-project/AI协作开发/../todo.md
cp new-project/AI协作开发/templates/gotcha-template.md new-project/AI协作开发/../gotcha.md
mkdir -p new-project/AI协作开发/../deprecated new-project/AI协作开发/../decisions

# 3. 填写技术栈
vim new-project/AI协作开发/spec/tech-stack.md

# 4. 定义接口
vim new-project/AI协作开发/spec/api-contract.md

# 5. 规划用户链路
vim new-project/AI协作开发/spec/user-journey.md

# 6. 开始开发
# 每次开发前阅读相关规范和技能
```

---

> 💡 **提示**：这套规范不是一成不变的。每个项目结束后，都应回顾并更新。
