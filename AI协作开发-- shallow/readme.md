# AI 协作开发 -- Shallow

> 本文档记录与 AI 协作开发过程中的踩坑经验、原则总结与最佳实践。
> 目标：建立可复用的协作规范，避免重复踩坑。

---

## 🤖 AI Agent 路由表（渐进式披露入口）

> **如果你是 AI Agent，在收到用户任务后，按此表确定需要阅读哪些文件。**
> 不需要一次性读取所有文件——根据任务类型按需加载。

| 用户任务类型 | 必须先读（理解规则） | 然后参考（执行指导） | 完成后更新 |
|-------------|---------------------|---------------------|-----------|
| **写新功能** | `spec/tech-stack.md`, `spec/api-contract.md` | `skill/code-generation.md`, `rules/logging.md` | `todo.md` |
| **修改已有代码** | `rules/code-structure.md` | `rules/api-consistency.md`, `rules/testing.md` | `gotcha.md`（如有踩坑） |
| **Debug / 排查问题** | `skill/debugging.md`, `gotcha.md` | `rules/logging.md` | `gotcha.md` |
| **修改 API / 接口** | `spec/api-contract.md`, `rules/api-consistency.md` | `rules/testing.md` | `todo.md` |
| **重构代码** | `rules/code-structure.md` | `rules/testing.md`, `rules/definition-of-done.md` | `todo.md` |
| **写测试** | `rules/testing.md` | `skill/code-generation.md` | — |
| **做技术决策** | `rules/ai-decision.md`, `decisions/` | `spec/tech-stack.md` | `decisions/` |
| **审查代码（PR/变更）** | `skill/code-review.md` | 引用涉及的 `rules/` 文件 | — |
| **新会话开始** | `todo.md`, `deprecated/`, `gotcha.md` | `readme.md`（本文件） | — |
| **标记任务完成** | `rules/definition-of-done.md` | — | `todo.md` |
| **任务模糊不清** | `rules/ai-decision.md`（澄清问题章节） | — | — |

> **原则**：AI Agent 每次只应读取与当前任务强相关的 2-4 个文件。规则文件之间互相独立，不需要全部读完才能开始工作。

---

## 一、为什么需要这套规范？

AI 辅助开发虽然效率极高，但存在以下系统性风险：

1. **黑盒风险**：AI 处理前端任务、复杂逻辑时，开发者往往不知道 AI 做了什么
2. **退化风险**：AI 在多次 debug 失败后，可能绕过检查、降级方案、删除测试
3. **漂移风险**：AI 擅自优化代码结构、移动文件、修改接口语义，导致依赖混乱
4. **知识遗忘**：AI 在会话中会遗忘之前敲定的技术决策，退回到旧方案
5. **日志盲区**：try-catch 写死、日志不详细，导致线上问题难以定位

---

## 二、核心原则（25 条踩坑总结）

### 原则速查表

| ID | 章节 | 原则 | 对应规范 |
|----|------|------|----------|
| PRJ-01 | 项目启动 | 先定技术栈，再写代码 | `spec/tech-stack.md` |
| PRJ-02 | 项目启动 | 先打通 API，再写页面 | `spec/api-contract.md` |
| PRJ-03 | 项目启动 | 清晰的用户链路 | `spec/user-journey.md` |
| PRJ-04 | 项目启动 | 目录职责解耦 | `spec/project-structure.md` |
| DEV-01 | 开发过程 | 详尽的日志 | `rules/logging.md` |
| DEV-02 | 开发过程 | 错误日志不写死 | `rules/logging.md` |
| DEV-03 | 开发过程 | 大模型判断优先 | `rules/ai-decision.md` |
| DEV-04 | 开发过程 | 提示词独立管理 | `spec/prompt-management.md`（待创建） |
| DEV-05 | 开发过程 | 调用计时 | `rules/logging.md` |
| DEV-06 | 开发过程 | 彻底打通才算完成 | `rules/definition-of-done.md` |
| DBG-01 | Debug | 详细日志定位优先 | `skill/debugging.md` |
| DBG-02 | Debug | 避免反复读同一文件 | `skill/debugging.md` |
| DBG-03 | Debug | 同类错误一并检查 | `skill/debugging.md` |
| DBG-04 | Debug | 禁止绕过测试 | `rules/testing.md` |
| DBG-05 | Debug | 禁止悄悄修改语义 | `rules/code-structure.md` |
| DBG-06 | Debug | 禁止擅自优化结构 | `rules/code-structure.md` |
| KNW-01 | 知识管理 | 待办事项持久化 | `spec/knowledge-management.md` |
| KNW-02 | 知识管理 | 废弃方案记录 | `spec/knowledge-management.md` |
| KNW-03 | 知识管理 | 踩坑日志反哺 | `spec/knowledge-management.md` |
| KNW-04 | 知识管理 | 复用优先 | `skill/code-generation.md` |
| AI-01 | AI 约束 | 禁止无确认重构 | `rules/testing.md`, `rules/code-structure.md` |
| AI-02 | AI 约束 | 禁止前端/后端只改一端 | `rules/api-consistency.md` |
| AI-03 | AI 约束 | 清理临时调试代码 | `skill/debugging.md` |
| AI-04 | AI 约束 | 禁止为通过测试而降级 | `rules/testing.md`, `rules/definition-of-done.md` |
| AI-05 | AI 约束 | 必须先问再动手 | `rules/ai-decision.md` |

### 2.1 项目启动阶段

| ID | 原则 | 说明 | 反面案例 |
|----|------|------|----------|
| PRJ-01 | **先定技术栈，再写代码** | 开始全栈项目前，必须与 AI 确定最终技术栈、详细技术文档、前后端接口协议 | 中途从 fpdf2 换 reportlab，浪费半天 debug |
| PRJ-02 | **先打通 API，再写页面** | 项目开始前先把所有 API 用 curl 验证通过 | FastAPI mount 顺序导致 404，前端白白联调 |
| PRJ-03 | **清晰的用户链路** | 工作前必须规划出用户从入口到出口的完整使用链路 | 产物面板渲染路径不清晰，反复排查 |
| PRJ-04 | **目录职责解耦** | 每个目录必须有清晰职责，新增功能不得随意放入已有目录 | orchestrator.py 越来越臃肿，逻辑混杂 |

### 2.2 开发过程规范

| ID | 原则 | 说明 | 反面案例 |
|----|------|------|----------|
| DEV-01 | **详尽的日志** | 每个功能必须在函数开始、关键分支、结束处添加日志。验证失败降级的逻辑必须打日志 | 降级到 fpdf2 时没有 warning 日志，排查不知走了哪个分支 |
| DEV-02 | **错误日志不写死** | `except` 块必须指向直接报错点：`logger.error(f"具体失败: {e}")`，不得写死错误描述 | `logger.error("出错了")` — 线上问题无从查起 |
| DEV-03 | **大模型判断优先** | 能让模型判断自然语言逻辑的，不得加入写死逻辑。如果必须存在，写入 `deprecated/` 并标记 | `if "生成PDF" in user_input` — 用户说"做个报告"就漏了 |
| DEV-04 | **提示词独立管理** | 所有提示词必须写在 YAML 文件，不得和逻辑代码混在一起 | 提示词散落在 5 个 Python 文件中，改一处漏一处 |
| DEV-05 | **调用计时** | 每次调用大模型必须用日志计时 | 不知道哪个模型调用慢，优化无从下手 |
| DEV-06 | **彻底打通才算完成** | 某一链路（如 PDF 生成 → 下载 → 预览）完全跑通前，该任务不算完成 | PDF 生成了但产物面板不显示，以为"做完"了 |

### 2.3 Debug 与维护规范

| ID | 原则 | 说明 | 反面案例 |
|----|------|------|----------|
| DBG-01 | **详细日志定位优先** | 当 AI 多次 debug 找不到问题时，首先增加更详细的日志，而非盲目修改代码 | 不读日志直接改正则，改了 3 次才定位到 emoji 范围问题 |
| DBG-02 | **避免反复读同一文件** | 一次读取至少 100 行，不得反复读取或读空文件 | AI 连续 5 次读取同一个空日志文件 |
| DBG-03 | **同类错误一并检查** | AI 发现错误后，必须顺带检查同类型的错误 | 修复了 artType 但没检查其他 camelCase/snake_case 不匹配 |
| DBG-04 | **禁止绕过测试** | 遇到难以解决的失败，必须输出详细分析报告，禁止修改测试断言或删除测试 | 改 `assert result == "expected"` 为 `assert result is not None` |
| DBG-05 | **禁止悄悄修改语义** | 不得修改已有函数的返回值语义。必须修改时标注 `@breaking-change` | `to_pdf` 返回值从本地路径变成 URL，调用方全炸 |
| DBG-06 | **禁止擅自优化结构** | 任何文件移动、重命名、新增顶层模块，必须先征得用户确认 | AI 把 `_parse_artifacts` 从 orchestrator 移到 utils，循环导入 |

### 2.4 知识管理规范

| ID | 原则 | 说明 | 反面案例 |
|----|------|------|----------|
| KNW-01 | **待办事项持久化** | 与 AI 讨论出多个待办但只能展开一个时，其余写入 `todo.md` | 讨论了 5 个优化点，会话中断后全部遗忘 |
| KNW-02 | **废弃方案记录** | 已废弃的方法或思路必须写入 `deprecated/`，避免 AI 遗忘后倒退 | 新会话中 AI 又提议用 fpdf2（已废弃方案） |
| KNW-03 | **踩坑日志反哺** | 每次解决难缠问题，要求 AI 总结成 `gotcha.md`，后续 AI 遇到相似场景先检索 | emoji 正则问题修了 2 次（第一次没记录教训） |
| KNW-04 | **复用优先** | 实现任何通用功能前，先搜索项目是否已有类似实现 | 项目中已有 file_converter，AI 又写了一个 pdf_util |

### 2.5 AI 特殊行为约束

| ID | 原则 | 说明 | 反面案例 |
|----|------|------|----------|
| AI-01 | **禁止无确认重构** | AI 不得在没有测试用例的情况下"自信"完成重构 | AI 重命名了 3 个文件"觉得更清晰"，引入循环导入 |
| AI-02 | **禁止前端/后端只改一端** | 涉及接口变更的任务，必须同时输出前后端修改计划 | 后端改了 artType 字段，前端还用 art_type，产物面板空白 |
| AI-03 | **清理临时调试代码** | 所有调试用的临时输出必须包含 `#TEMP_DEBUG#`，任务完成后删除 | 遗留了 15 处 `print()` 调试代码 |
| AI-04 | **禁止为通过测试而降级** | AI 不得为了通过测试而修改测试本身、删除测试、或降低原有标准 | 覆盖率不够就把阈值从 80% 改为 50% |
| AI-05 | **必须先问再动手** | 当任务描述模糊或涉及新业务概念时，AI 必须先列出 3-5 个澄清问题 | 用户说"做个报表"，AI 直接实现了 PDF，用户想要的是 Excel |

---

## 三、文档结构

```
AI协作开发-- shallow/
├── readme.md                     # 本文件：总纲、原则、路由表
├── example-manual/               # 可复用的 AI 协作手册模板（可复制到新项目）
│   ├── README.md                 # 模板索引与使用指南
│   ├── spec/                     # 规范文档（项目级、技术级）
│   │   ├── tech-stack.md         # 技术栈定义
│   │   ├── api-contract.md       # 前后端接口协议（含 WebSocket 格式）
│   │   ├── project-structure.md  # 目录职责规范
│   │   ├── user-journey.md       # 用户链路（含 AI 协作元流程）
│   │   └── knowledge-management.md # 知识管理体系
│   ├── skill/                    # 技能文档（AI 能力定义）
│   │   ├── code-generation.md    # 代码生成技能
│   │   ├── debugging.md          # 调试技能
│   │   └── code-review.md        # 代码审查技能
│   ├── rules/                    # 规则文档（行为约束）
│   │   ├── logging.md            # 日志规范
│   │   ├── testing.md            # 测试规范
│   │   ├── ai-decision.md        # AI 决策规范
│   │   ├── code-structure.md     # 代码结构规范（含重构范围约束）
│   │   ├── api-consistency.md    # 接口一致性规范
│   │   └── definition-of-done.md # 完成定义
│   └── templates/                # 空白模板（新项目快速启动）
│       ├── todo-template.md
│       ├── gotcha-template.md
│       ├── deprecated-template.md
│       └── decision-template.md
└── AgentHub-records/             # 当前项目的实际记录（项目特定，不可复用）
    ├── todo.md                   # 项目待办事项
    ├── gotcha.md                 # 项目踩坑日志
    ├── deprecated/               # 项目废弃方案
    └── decisions/                # 项目决策记录
```

---

## 四、如何使用这套规范

### 对于人类开发者

1. **新项目启动**：复制 `example-manual/` 到新项目，按模板填写 `spec/`
2. **开发过程中**：遇到任何决策，先查 `rules/`，再查 `skill/`
3. **Debug 时**：先增加日志，按 `skill/debugging.md` 排查，记录到 `gotcha.md`
4. **会话中断后**：新会话先读取 `todo.md` 和 `gotcha.md`，确保上下文不丢失

### 对于 AI Agent

1. **启动时**：阅读本文件的「AI Agent 路由表」，确定当前任务需要哪些文件
2. **按需加载**：只读取与当前任务相关的 2-4 个文件，不要全量加载
3. **交叉引用**：每个规则文件底部标注了相关文件，可沿引用链深入
4. **记录产出**：完成任务后更新 `todo.md`，有踩坑则更新 `gotcha.md`

---

## 五、渐进式披露设计

本规范体系按以下原则设计，确保 AI Agent 可以高效使用：

| 层级 | 文件 | 何时阅读 | 内容粒度 |
|------|------|----------|----------|
| **L0 - 入口** | `readme.md` | 每次任务开始 | 路由表 + 原则摘要 |
| **L1 - 规范** | `spec/*.md` | 需要了解项目全貌时 | 项目级定义（技术栈、接口、结构） |
| **L2 - 规则** | `rules/*.md` | 执行具体操作时 | 行为约束（该做什么、不该做什么） |
| **L3 - 技能** | `skill/*.md` | 需要方法论指导时 | 执行流程（怎么做、步骤是什么） |
| **L4 - 记录** | `AgentHub-records/` | 会话开始时 | 项目历史（做了什么、踩了什么坑） |

**设计原则**：
- 每个文件自包含：不需要读 A 才能理解 B
- 双向交叉引用：相关文件互相指向，可沿链深入
- 触发条件优先：每个文件开头说明「何时需要读这个文件」
- 禁止全量加载：AI Agent 不应一次读完所有文件

---

> 💡 **提示**：这套规范不是一成不变的。每次项目结束后，应回顾并更新 `AgentHub-records/gotcha.md` 和 `rules/`，让 AI 下次协作时更聪明。
