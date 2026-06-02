# AgentHub — 多 Agent 协作平台 · 产品需求文档

# AgentHub — 多 Agent 协作平台 · 产品需求文档

## 目录

1. 产品概述

2. 目标用户与场景

3. 核心概念模型

4. 用户旅程

5. 信息架构与导航

6. 布局与界面规范

7. 关键交互流

8. UX 设计细则

9. 功能模块（P0 / P1 / P2）

10. 内置 Mission 模板库

11. Skill 系统

12. Agent 平台接入

13. 架构与技术选型

14. 视觉规格（Stitch Prompts）

## 1\. 产品概述

### 1\.1 一句话定义

**AgentHub 是以\&\#34;Agent 集群\&\#34;为单位的协作工作台。每个 Mission 封装一类重复性任务的稳定班底（Agent \+ Skill），用户进入模块后用自然语言反复执行任务、迭代班底，所有编辑都在模块内原地完成。**



### 1\.2 产品信念

- **Agent 是任务的下属，不是用户的联系人。** 同一类工作角色（如\&\#34;数据分析师\&\#34;）在不同任务里需要不同的人格、Skill 与上下文，把它抽象成跨场景稳定的\&\#34;联系人\&\#34;是错误的。Agent 必须挂在任务里。

- **以 Agent 集群为导向，不以单次任务为导向。** 用户进入一个 Mission，等于走进一间装备好的办公室；不是每次重新装修。

- **编辑即工作，不切后台。** 自然语言修改 Agent 的能力贯穿任务全过程；编辑动作和工作动作共享同一个界面。

- **Run 是不可改写的执行实例。** 班底改动属于 Mission 级，Run 启动时拍快照保证可复现。

### 1\.3 与同类产品的差异锚点



|产品|核心范式|AgentHub 差异|
|---|---|---|
|飞书智能伙伴 / Slack AI|Agent = IM 联系人|AgentHub：Agent 是 Mission 的下属，跟随任务变形|
|扣子 / Dify|工作流编排（节点连线）|AgentHub：保留对话语义，节点心智隐藏在班底卡片背后|
|Claude\.ai / ChatGPT|单 Agent 对话|AgentHub：多 Agent 在同一 Mission 协作，自然语言迭代班底|
|Cursor / Claude Code|代码场景的 AI 协作|AgentHub：通用任务工作台，且强调班底的长期复用|



## 2\. 目标用户与场景

### 2\.1 目标用户



|用户类型|核心诉求|画像|
|---|---|---|
|**效率型知识工作者**|把重复性脑力任务标准化|分析师、研究员、运营、内容创作者|
|**AI 工程师 / 极客**|搭建自己的 Agent 班底，深度定制|工程师、创业者、技术博主|
|**团队 Lead**|沉淀部门标准操作流程为可复用模块|产品经理、市场负责人|



### 2\.2 高频使用场景



|场景|频率|偏好路径|
|---|---|---|
|财报季分析多家公司|周/月|Mission 模板 \+ 反复 Run|
|PR 代码审查|日|Mission（团队共用）\+ 群聊 @|
|竞品周报|周|模板拉起 \+ Quick Run 试探|
|临时读 PDF / 翻译文档|日|Quick Run|
|自定义垂直领域工作流|一次性投入|AI 引导建模块 \+ Skill 自建|



## 3\. 核心概念模型

### 3\.1 实体关系

```Plain Text
User
 └── Workspace
      ├── Quick Run（轻入口，不属于任何 Mission）
      └── Mission[]（工作模块 / Agent 集群）
           ├── 班底配置（Mission 级，稳定权威源）
           │    ├── Agent[]（system_prompt / skills / model / role）
           │    ├── Skill_Library（模块启用的 Skill）
           │    └── Coordinator 配置
           ├── Template_Origin（可选：基于哪个模板创建）
           └── Run[]（单次执行历史）
                ├── squad_snapshot（启动时刻的班底只读快照）
                ├── conversation
                └── artifacts
```



### 3\.2 实体定义



|实体|性质|生命周期|班底可改|
|---|---|---|---|
|**Mission**|长期工作模块|长期|是（影响后续所有 Run）|
|**Run**|单次执行实例|一次性|否（启动时拍快照）|
|**Quick Run**|临时工作空间，不属于任何 Mission|一次性|用通用班底，不暴露编辑|
|**Agent**|Mission 内的工作单元|跟随 Mission|自然语言或手动可改|
|**Skill**|Agent 能力组件|平台级 \+ Mission 级启用|Mission 内可启用/禁用|
|**Coordinator**|模块级常驻协调 Agent|跟随 Mission|自动配置，可手动调|



### 3\.3 不变量

- Run 启动时复制 Mission\.squad → Run\.squad\_snapshot，**纯拷贝、非引用**。

- Mission\.squad 修改不影响已有 Run。

- Quick Run 跑完可显式\&\#34;保存为 Mission\&\#34;，否则保留在临时区。

- Coordinator 在每个 Mission 内唯一，不可删除。

## 4\. 用户旅程

### 4\.1 新用户首次使用（onboarding）

```Plain Text
首次登录
  ↓
Empty-state Dashboard 展示三类选项：
  · 6 个推荐模板（卡片）
  · "AI 帮我搭建一个" 引导框
  · "试试 Quick Run" 轻入口
  ↓
路径分支：
  ① 选模板 → 班底就位 → 立即执行任务
  ② AI 引导 → 描述需求 → 班底提案 → 接受 → 立即执行
  ③ Quick Run → 直接对话 → 跑完后引导沉淀
  ↓
首次任务完成
  ↓
出现"班底导览"提示：
  "你现在已经有了一个 Mission，里面有 X 个 Agent。
   随时可以在右侧编辑区或对话框里调整他们。"
```



**关键 UX 原则**：

- 新用户在 60 秒内看到第一个任务结果

- 不强制 onboarding 教程，所有引导融入实际任务流

- 第一次任务用模板路径成功率最高，因此默认聚焦模板

### 4\.2 老用户日常工作流

```Plain Text
打开应用 → 看到熟悉的 Mission 列表
  ↓
点击 Mission（如"财报分析"）
  ↓
进入工作台 → 班底已就位
  ↓
点击 [+ New Run] 或直接在底部输入框输入任务描述
  ↓
对话流展开，Agent 协作产出
  ↓
（可选）发现某个 Agent 输出不理想：
  - 在对话框对 Coordinator 说："让数据分析师改用 Tufte 风格"
  - 弹出 diff 预览 → Apply
  - 当前 Run 不受影响（已快照），下个 Run 生效
  ↓
（可选）需要多个 Agent 并行讨论：
  - 在对话框 @数据分析师 @报告撰写师，让两人对同一份数据给出不同视角
  - 群聊模式开启，两个 Agent 依次回复
  ↓
任务完成 → 产物自动归档到 Run
```



### 4\.3 班底沉淀路径

```Plain Text
Quick Run（试水）
  ↓ "Save as Mission"
Mission（v1 班底）
  ↓ 用 N 次后自然语言迭代
Mission（v2 班底）
  ↓ "Save as Template"（私有模板，P1）
个人模板库
  ↓ "Publish"（公开，P2）
社区模板市场
```



## 5\. 信息架构与导航

### 5\.1 全站信息架构

```Plain Text
AgentHub
├── Workspace
│   ├── Dashboard（Mission 总览）
│   ├── Quick Run（临时工作空间）
│   ├── Mission Workspace
│   │   ├── Conversation（中心对话）
│   │   ├── Output Panel（产物预览）
│   │   ├── Agents Editor（右侧 Tab 1）
│   │   ├── Skills Editor（右侧 Tab 2）
│   │   ├── Settings（右侧 Tab 3）
│   │   └── Run History（左侧导航嵌套）
│   └── Template Gallery（建 Mission 入口）
└── User Settings
    ├── Account
    ├── Connected Agent Platforms（Claude Code / Codex / OpenCode）
    ├── Custom Skills（用户自建）
    └── Billing
```



### 5\.2 主导航层级

- **一级**：Workspace（多工作区，P1 团队场景）

- **二级**：Mission 列表 \+ Quick Run（左侧导航）

- **三级**：Mission 内的 Run 列表（左侧导航嵌套）

### 5\.3 内容查找路径



|用户意图|查找路径|
|---|---|
|找一个之前跑过的任务|左导航 → 找 Mission → 展开 Run 列表 → 点击|
|复用一次跑得好的班底|Mission Settings → \&\#34;Save as Template\&\#34; → 模板库可见|
|看自己有哪些 Skill|右侧 Tab → Skills → 全局 \+ 模块级两层视图|
|看 Agent 的当前配置|右侧 Tab → Agents → 点击卡片展开|



## 6\. 布局与界面规范

### 6\.1 整体三栏结构

```Plain Text
┌──────────────────────────────────────────────────────────────────┐
│ Top Bar 52px                                                       │
│ [Workspace] / [Mission Name]    [+ New Run] [Settings]            │
├──────────┬────────────────────────────────────┬─────────────────┤
│  Left    │      Center                          │ Right Editor    │
│  Nav     │      ┌──────────────────────┐       │ (360px)         │
│ (240px)  │      │ Conversation 60%      │       │                 │
│          │      ├──────────────────────┤       │ [Agents]        │
│          │      │ Output Panel 40%      │       │ [Skills]        │
│          │      ├──────────────────────┤       │ [Settings]      │
│          │      │ Chat Input            │       │                 │
│          │      └──────────────────────┘       │                 │
└──────────┴────────────────────────────────────┴─────────────────┘
```



**栅格**：12 列，左 240 / 中 flex / 右 360；最小可用宽度 1280px，低于此宽度右侧编辑区折叠为图标抽屉。



### 6\.2 左侧导航（240px）

```Plain Text
┌──────────────────┐
│ + Quick Run       │ ← 常驻轻入口
├──────────────────┤
│ MISSIONS          │
│ ▼ 美股财报分析     │ ← 当前 Mission，展开 Run 列表
│   · Current run   │
│   · Tesla Q4      │
│   · Nvidia Q4     │
│ ▸ 竞品监控        │
│ ▸ 周报生成        │
│ ▸ 代码 Review     │
├──────────────────┤
│ + New Mission     │ ← 富入口，进入模板库
└──────────────────┘
```



**交互细节**：

- Mission 列表按\&\#34;最近活跃\&\#34;排序，可右键置顶

- 拖拽 Run 项可以重命名 / 复制

- 长按 Mission 显示快捷菜单（重命名、归档、导出、保存为模板）

### 6\.3 中间区域（Conversation \+ Output）

**布局**：上下分栏，可拖拽分割条。默认对话流 60% / 输出面板 40%。



#### 对话流（上）

- 单列消息 thread，最大宽度 760px 居中

- 用户消息右对齐，Agent 消息左对齐带头像

- 工具调用以可折叠卡片展示，默认折叠到 1 行摘要

- 内联预览：data\-table、小图、代码 diff、链接卡片

- 消息悬停显示行动按钮：\[Reply\] \[Quote\] \[Regenerate\] \[Pin\] \[Copy\]

#### 输出面板（下）

- 顶部 Tab：\[Code\] \[Preview\] \[Docs\] \[Charts\] \[Files\]

- 内容来自对话流的产物。点击对话流里的产物卡片自动定位到对应 Tab

- 全屏按钮：将输出面板放大为 modal，对话流隐藏

#### 输入框（底）

- 全宽，64px 高

- Placeholder：动态切换

    - 任务模式：`Run a task with your squad\.\.\.`

    - 编辑意图被识别：`Describe a change to your agents\.\.\.`

- 左侧图标：附件、Skill 选择器、@ 提及

- 右侧：发送按钮（Cmd/Ctrl \+ Enter）

### 6\.4 右侧编辑区（360px，Tab 分页）

#### Tab 1：Agents（默认）

```Plain Text
┌──────────────────────────┐
│ [Agents] [Skills] [⚙]     │
├──────────────────────────┤
│ ◉ Coordinator             │ ← 常驻，不可删
│   分派子 Agent + 解析编辑 │
│                           │
│ ◉ 数据抽取师               │
│   skills: 3   model: ...  │
│                           │
│ ◉ 数据分析师               │ ← 选中态，左侧橙色 4px 边
│   ┌──────────────────┐    │
│   │ system prompt    │    │
│   │ [editable area]  │    │
│   └──────────────────┘    │
│   skills: [+ add]         │
│   model: [dropdown]       │
│   [Save] [Discard]        │
│                           │
│ + Add Agent               │
└──────────────────────────┘
```



#### Tab 2：Skills

```Plain Text
┌──────────────────────────┐
│ [Search skills...]        │
├──────────────────────────┤
│ Built-in (10)             │
│   ☑ pdf_parse  used by 1  │
│   ☑ web_search used by 2  │
│   ☐ code_exec             │
│   ...                     │
├──────────────────────────┤
│ Custom (3)  [+ Add]       │
│   ☑ kdocs_publish         │
│   ☑ sec_filing_lookup     │
│   ☐ slack_notify          │
└──────────────────────────┘
```



#### Tab 3：Settings

- Mission 元信息（名、描述、图标）

- 班底导出（JSON）

- 保存为模板（私有 P1 / 公开 P2）

- 群聊模式开关

- 归档 Mission

## 7\. 关键交互流

### 7\.1 自然语言修改 Agent

**触发**：用户在中间输入框输入修改指令，如\&\#34;给数据分析师加 sec\_filing\_lookup skill 并默认用 Tufte 风格作图\&\#34;



**流程**：

```Plain Text
1. Coordinator 在后台用 Editor Mode prompt 解析
   输入：用户原话 + 当前 Mission 班底 JSON
   输出：班底 patch（JSON Patch 格式）+ 自然语言摘要

2. UI 弹出 diff 预览卡片（输入框上方）：
   - Header: "Proposed changes to: Data Analyst Agent"
   - Skills section: 老 chips 灰色 + 新 chip 绿色 "+ sec_filing_lookup"
   - System prompt section: 文字 diff（红色删除 / 绿色新增）
   - 右下角 [Discard] [Apply]

3. 同时右侧编辑区对应 Agent 卡片显示橙色虚线边框（pending 态）

4. 用户 Apply → patch 生效 → 卡片实时更新 + diff 卡片消失
   用户 Discard → 不变
```



**边界情况**：

- 解析失败 → Coordinator 在对话流里说\&\#34;我没看懂这个修改，能再说一次吗\&\#34;，附上他理解的关键词

- 修改影响多个 Agent → diff 预览卡片高度自适应，可滚动

- 用户连续输入两条修改 → 后一条覆盖前一条 pending 状态，前一条不消失而是合并

### 7\.2 AI 引导建 Mission

**入口**：Dashboard → \&\#34;\+ New Mission\&\#34; → 选择\&\#34;Let AI build one for me\&\#34;



**流程**：

```Plain Text
Step 1: 输入需求
  弹窗中央 placeholder："Tell me what you want to do regularly"
  下方有 3 个示例 chip：
    · "weekly competitor product updates"
    · "PR code reviews"
    · "personal finance tracking"

Step 2: AI 提案
  AI 输出"班底提案卡片"（结构化、非纯文本）：
    Heading: "Here's a squad I'd build for this:"
    3-4 个 Agent rows，每 row：
      - bold name
      - 2-line italic role
      - skill chip row
    Mission name suggestion 预览
    Action row: [Use this] [Why this combo?] [Tweak it] [Try another]

Step 3: 决策分支
  Use this → 创建 Mission，进入工作台
  Why → AI 解释推理过程（折叠在卡片下方）
  Tweak it → 进入逐 Agent 修改对话（同 7.1 的自然语言编辑）
  Try another → AI 给出第二套方案

Step 4: 创建后引导
  进入新 Mission 工作台 → 顶部出现一次性引导横幅：
  "Try running your first task. Squad is ready."
```



### 7\.3 群聊 @ 多 Agent

**目的**：在同一 Mission 内让多个 Agent 同时对一个问题给出不同视角，或显式指定某 Agent 接管。



**触发**：在输入框内输入 `@`，弹出 Agent 选择器（显示当前 Mission 的所有 Agent）



**流程**：

```Plain Text
1. 单 @ 模式：
   "@数据分析师 这份数据你怎么看？"
   → 跳过 Coordinator 分派，直接路由给数据分析师
   → 数据分析师回复

2. 多 @ 模式（群聊）：
   "@数据分析师 @报告撰写师 你们俩对这份财报的关注点不一样，分别说说"
   → Coordinator 进入"主持人模式"
   → 数据分析师先回复（带"轮到我"标识）
   → 报告撰写师后回复（带"轮到我"标识）
   → Coordinator 在最后做一句简短总结

3. 不带 @ 的消息：
   → 默认进入 Coordinator 分派流程
```



**UI 细节**：

- @ 选择器支持模糊搜索 \+ 键盘上下选择 \+ Tab 确认

- 群聊回复在对话流中按\&\#34;发言顺序\&\#34;垂直堆叠，每个 Agent 头像 \+ 名称 \+ 时间戳

- 群聊消息右上角小图标\&\#34;群聊\&\#34;标识，点击查看参与 Agent 列表

- 设置中可关闭群聊模式（默认开启）

### 7\.4 Quick Run 沉淀为 Mission

**触发**：Quick Run 中第一次完成有意义的产出后



**流程**：

```Plain Text
1. 系统检测到 Quick Run 已有 ≥3 轮对话且有产物
   → 在对话流底部插入引导卡片：
     "This looks like something you might do regularly. 
      Save as a Mission to reuse the squad."
     [Save as Mission] [Dismiss]

2. 用户点击 Save as Mission：
  弹窗：
    - Mission name 输入框（AI 预填建议名）
    - "Use AI to refine the squad?" 开关（默认开）
      开启时：AI 会基于刚才对话推荐更精准的 Agent 班底
      关闭时：直接用 Quick Run 的通用班底
  [Cancel] [Create Mission]

3. 创建后跳转到新 Mission 工作台，对话历史保留为 Run #1
```



### 7\.5 Run 切换与快照保护

**触发**：左导航点击某历史 Run



**流程**：

```Plain Text
1. 中心对话流加载该 Run 的历史消息
2. 顶部出现只读横幅：
   "Read-only — this Run is archived."
   右侧按钮：[Fork into new Run]
3. 右侧编辑区显示该 Run 的 squad_snapshot：
   - 所有编辑控件 disabled（淡灰）
   - 顶部小锁图标 + tooltip：
     "Snapshot from 2 days ago. Current squad has changed."
   - 提供链接 "View current squad" 跳回当前 Mission 班底
4. 输入框 disabled，placeholder 变为 "This run is archived. Fork to continue."
```



**Fork into new Run**：用当前 Mission 班底（不是 snapshot）拉起一个新 Run，把历史 Run 的初始 prompt 作为引子。



### 7\.6 Skill 自建（P0）

**入口**：右侧 Tab → Skills → \&\#34;\+ Add custom skill\&\#34;



#### 方式 A：MCP 接入

```Plain Text
弹窗：Connect MCP Server
  - Server URL 输入
  - Transport 选择（stdio / SSE）
  - 认证方式（None / API Key / OAuth）
  - [Test Connection]
  连接成功后显示 MCP server 暴露的所有 tool
  用户勾选要作为 Skill 启用的 tool
  [Save]
```



#### 方式 B：脚本上传（轻量）

```Plain Text
弹窗：Add Custom Skill (Script)
  - Skill name
  - 1-line description（喂给 Agent 的能力提示）
  - Schema definition（input / output JSON Schema）
  - Script type（Python / Node.js / Shell）
  - Code editor（多行）
  - Test panel（输入示例 input，运行查看 output）
  [Save]
```



**沙箱**：自建脚本在容器内运行，限制 CPU / 内存 / 网络 / 文件系统。MVP 不支持出网（白名单除外）。



## 8\. UX 设计细则

### 8\.1 视觉语言



|维度|规范|
|---|---|
|主色|Warm Orange \#E96A3C（仅用于主操作按钮、选中态、强调链接）|
|中性色|主背景 \#FAFAF9 / 面板 \#FFFFFF / 边框 \#E8E6E1 / 文字 \#1A1A1A / 次要文字 \#6B6B6B|
|字体|Inter（西文） / 苹方 / Source Han Sans（中文）— 14px 基准|
|圆角|卡片 8px / 按钮 6px / 输入框 6px|
|阴影|hover 状态 0 1px 2px rgba\(0,0,0,0\.04\)；modal 0 8px 24px rgba\(0,0,0,0\.08\)|



**禁止项**：蓝紫渐变、emoji 装饰、AI 配色（粉紫荧光）、过度毛玻璃。



### 8\.2 微文案原则

- **以用户视角写**：避免\&\#34;系统正在执行\.\.\.\&\#34;类机器口吻

- **短句优先**：句子超过 12 字考虑拆分或精简

- **动词驱动**：按钮文字用动词（\&\#34;Apply\&\#34;而非\&\#34;OK\&\#34;）

- **明确边界**：状态切换的副作用要在文案里讲清楚

|不好|好|
|---|---|
|你确定要应用这些修改吗？|Apply changes to Data Analyst?|
|系统检测到您的会话已存档|Read\-only — this Run is archived|
|没有可显示的内容|Start by creating your first Mission|



### 8\.3 关键状态设计

#### Empty States



|位置|设计|
|---|---|
|全局 Dashboard 空|大图引导 \+ 三路 onboarding 入口（模板/AI/Quick Run），不显示空文件夹图|
|Mission 内首次进入（无 Run）|中央 placeholder：\&\#34;Run your first task\. Try `Analyze Tesla Q4 earnings`\.\&\#34; 带可点击示例 chip|
|输出面板无产物|浅灰提示：\&\#34;Outputs will appear here as your agents work\.\&\#34;|
|Skill 列表自建为空|蓝色提示卡：\&\#34;Connect MCP server\&\#34; \+ \&\#34;Upload script\&\#34; 双 CTA|



#### Loading States



|场景|表现|
|---|---|
|Agent 思考|头像旁边小转圈 \+ \&\#34;thinking\.\.\.\&\#34; 灰色文字|
|工具调用|工具卡片头部进度条（不确定型）|
|长对话首次加载|上方骨架屏，按消息单元闪烁|
|AI 建班底|提案卡片骨架屏（3 个 Agent 行的占位）|



#### Error States



|场景|表现|
|---|---|
|Agent 失败|消息位置显示红色边框卡片 \+ 错误摘要 \+ \[Retry\] \[See details\]|
|Skill 调用失败|工具卡片变红，可展开看 stderr|
|Coordinator 解析失败|在对话流中以 Coordinator 自身回复呈现：\&\#34;I\&\#39;m not sure what to change\. Can you rephrase?\&\#34; 附理解到的关键词|
|网络断|顶部全宽 banner：\&\#34;Reconnecting\.\.\.\&\#34; 自动重试|



### 8\.4 键盘交互



|快捷键|动作|
|---|---|
|`Cmd/Ctrl \+ Enter`|发送消息|
|`Cmd/Ctrl \+ K`|打开全局命令面板（搜索 Mission / Run / Skill）|
|`Cmd/Ctrl \+ N`|新建 Mission|
|`Cmd/Ctrl \+ Shift \+ N`|在当前 Mission 内 New Run|
|`Cmd/Ctrl \+ B`|折叠/展开左侧导航|
|`Cmd/Ctrl \+ \.`|折叠/展开右侧编辑区|
|`@`|触发 Agent 选择器|
|`/`|触发 Skill 选择器（输入框内）|
|`Esc`|关闭 modal / 取消 pending diff|
|`↑`|编辑上一条用户消息|



### 8\.5 响应式行为



|视口|行为|
|---|---|
|≥ 1440px|三栏全展开|
|1280–1440px|三栏正常，输出面板 Tab 文案缩为图标|
|1024–1280px|右侧编辑区折叠为图标抽屉，点击展开覆盖中间区|
|\&lt; 1024px|单栏视图（移动端 P2），左导航 \+ 中区 \+ 右编辑分别为独立屏|



### 8\.6 可访问性

- 所有操作按钮可键盘触达，焦点态可见（橙色 2px 描边）

- 颜色对比度满足 WCAG AA（文字与背景 ≥ 4\.5:1）

- 不依赖单纯颜色传递信息（如 diff 不仅用红绿，也用 \+ / \- 符号）

- 所有图标按钮带 aria\-label

- 输出面板代码块支持屏幕阅读器朗读

### 8\.7 文案与命名规范



|概念|中文|英文|
|---|---|---|
|Mission|工作模块 / 模块|Mission|
|Run|执行|Run|
|Quick Run|快速执行|Quick Run|
|Agent|Agent|Agent|
|Skill|技能|Skill|
|班底|班底|Squad|
|模板|模板|Template|



## 9\. 功能模块（P0 / P1 / P2）

### P0 — MVP



|模块|子功能|
|---|---|
|Mission 管理|新建 / 重命名 / 删除 / 切换|
|Run 管理|新建 / 切换 / 历史只读 / Fork|
|Quick Run|临时工作空间 / 通用班底 / 转 Mission|
|三栏布局|左导航 \+ 中对话\+输出 \+ 右编辑|
|Agent 卡片|创建 / 编辑 / 删除 / 自然语言修改|
|Coordinator 双能力|任务分派 \+ 配置编辑（Editor Mode）|
|Skill 系统|内置 ≥ 10 个 \+ Mission 级启用|
|**Skill 自建**|**MCP 接入 \+ 脚本上传 \+ 沙箱执行**|
|多 Agent 协作|Coordinator 自动分派（串行）|
|**群聊 @ 多 Agent**|**@ 选择器 \+ 群聊主持模式**|
|Agent 平台适配|**接入 Claude Code \+ Codex（2 个）**|
|产物预览|Code / Preview / Docs / Charts|
|Mission 模板库|≥ 6 个内置模板|
|AI 引导建模块|自然语言 → 班底提案 → 创建|



### P1

- Mission Template 自定义（私有模板）

- 全局 Agent Library

- 并行调度

- 上下文 Pin

- 失败降级 / 重试

- 多 Workspace（团队场景基础）

- 输出面板 Diff 视图

- 接入 OpenCode（第三个 Agent 平台）

### P2

- 模板市场（公开分享）

- 一键部署（静态站、容器、源码包）

- 多人实时协作

- 桌面端 / 移动端

- Agent 性能数据看板

- PPT / 复杂文档预览

- Run 间结果对比 / A/B

## 10\. 内置 Mission 模板库

### 10\.1 模板列表



|模板|班底|推荐 Skill|
|---|---|---|
|**财报分析**|数据抽取师 / 数据分析师 / 报告撰写师|pdf\_parse, sec\_filing\_lookup, code\_exec, chart\_render, markdown\_write|
|**代码 Review**|静态扫描师 / 安全审计师 / 改进建议师|code\_read, lint, security\_scan, diff\_render|
|**竞品监控**|信息采集师 / 变更分析师 / 报告整合师|web\_scrape, screenshot, diff\_compare, markdown\_write|
|**周报生成**|数据收集师 / 内容整合师 / 排版师|calendar\_read, kdocs\_read, markdown\_write, kdocs\_publish|
|**公众号文章拆解**|主旨提取师 / 框架分析师 / 改写建议师|web\_fetch, markdown\_write|
|**邮件分类回复**|分类师 / 优先级判断师 / 草稿撰写师|email\_read, email\_compose, markdown\_write|



### 10\.2 模板卡片信息

每张模板卡片展示：图标、名称、1 行简介、班底头像堆叠（3\-5 个）、Skill 标签（最多 4 个，超出 \+N）、\&\#34;使用过 X 次\&\#34;（P1 社会证明）。



### 10\.3 模板的使用与扩展

- 用户基于模板创建 Mission 后，在 Mission 内的所有修改不会回写模板

- P1 阶段允许\&\#34;Save as Template\&\#34;将自己的 Mission 班底固化为私有模板

- P2 阶段允许公开发布到模板市场

## 11\. Skill 系统

### 11\.1 内置 Skill 清单（≥ 10 个，P0）



|Skill|描述|典型用途|
|---|---|---|
|`web\_search`|联网搜索|实时信息查询|
|`web\_fetch`|抓取并提取网页内容|阅读链接|
|`web\_scrape`|结构化抓取|竞品监控|
|`pdf\_parse`|PDF 文本与表格抽取|财报、报告|
|`code\_exec`|Python/Node 代码执行（沙箱）|数据处理、画图|
|`chart\_render`|渲染图表|可视化输出|
|`markdown\_write`|生成 Markdown|报告输出|
|`kdocs\_read` / `kdocs\_publish`|内网文档读写|内部工作流|
|`screenshot`|网页截图|视觉对比|
|`email\_read` / `email\_compose`|邮箱读写|邮件场景|
|`calendar\_read`|日历查询|周报场景|
|`diff\_compare`|文本/数据 diff|变更分析|



### 11\.2 自建 Skill（P0）

详见 7\.6。两种方式：MCP 接入、脚本上传。沙箱执行，限制资源与网络。



### 11\.3 Skill 启用模型

- 全局 Skill 池：所有内置 \+ 用户自建的 Skill 池

- Mission 级启用：每个 Mission 独立选择启用哪些 Skill

- Agent 级订阅：每个 Agent 在 Mission 启用的 Skill 中再选自己用哪些

## 12\. Agent 平台接入（MVP 接 2 个）

### 12\.1 接入清单



|平台|MVP|优先级|接入方式|
|---|---|---|---|
|Claude Code|✅|必接|官方 API \+ 自定义 system prompt|
|Codex|✅|必接|OpenAI Codex API|
|OpenCode|⏳ P1|可选|开源项目集成|
|用户自建 Agent|✅|通过 Coordinator \+ 内置 LLM 实现|—|



### 12\.2 适配层接口

```TypeScript
interface AgentAdapter {
  id: string;
  name: string;
  capabilities: {
    streaming: boolean;
    toolCalling: boolean;
    multiTurn: boolean;
    maxTokens: number;
  };
  
  invoke(input: {
    systemPrompt: string;
    messages: Message[];
    tools: ToolDefinition[];
    stream?: boolean;
  }): AsyncIterable<AgentEvent>;
  
  health(): Promise<HealthStatus>;
}
```

所有适配器实现统一接口，平台差异在适配层屏蔽（消息格式、工具调用协议、错误码）。



## 13\. 架构与技术选型

### 13\.1 分层架构

```Plain Text
┌─────────────────────────────────────────────────┐
│  Web Frontend                                     │
│  React 18 + Tailwind + Zustand + react-router    │
│  - 三栏布局 + Chat + Code Editor (Monaco)         │
│  - 模板库 / AI 引导向导                            │
└────────────────────────┬─────────────────────────┘
                         │ WebSocket / SSE
┌────────────────────────┴─────────────────────────┐
│  AgentHub Core (Node.js + TypeScript)             │
│  - Mission / Run 状态机                            │
│  - Coordinator（双 Mode）                          │
│      a) Dispatch Mode：分派子 Agent                │
│      b) Editor Mode：自然语言 → 班底 patch         │
│  - 模板引擎 + AI Mission Builder                   │
│  - 上下文管理 / 产物存储                           │
│  - Skill 沙箱 (Docker / Firecracker)              │
└────────────────────────┬─────────────────────────┘
                         │
┌─────────────┬──────────┴────────┬────────────────┐
│ Adapter     │ Adapter           │ Adapter        │
│ Claude Code │ Codex             │ OpenCode (P1)  │
└─────────────┴───────────────────┴────────────────┘
```



### 13\.2 关键决策



|决策点|选型|理由|
|---|---|---|
|前端框架|React \+ Tailwind \+ Zustand|生态成熟，Tailwind 适合快速 UI 迭代|
|代码编辑器|Monaco|VSCode 同源，体验最好|
|实时通信|SSE \(主\) \+ WebSocket \(P1 协作\)|SSE 简单稳定，足以覆盖 Agent 流式输出|
|持久化|PostgreSQL（结构化）\+ S3（产物）|经典组合|
|Skill 沙箱|Docker \(MVP\) → Firecracker \(P1\)|MVP 用 Docker 快，长期换轻沙箱|
|状态管理|Mission JSON Schema 单一来源|易导出、可复现、模板化|



### 13\.3 数据模型核心字段

```TypeScript
type Mission = {
  id: string;
  workspaceId: string;
  name: string;
  description?: string;
  iconUrl?: string;
  templateOrigin?: string;
  squad: Squad;             // 当前班底（权威源）
  createdAt: Date;
  updatedAt: Date;
};

type Squad = {
  agents: Agent[];
  enabledSkills: SkillId[];
  coordinator: CoordinatorConfig;
};

type Agent = {
  id: string;
  name: string;
  avatarUrl?: string;
  role: string;             // 1-line italic 描述
  systemPrompt: string;
  skills: SkillId[];        // 该 Agent 订阅的 Skill 子集
  modelAdapter: 'claude-code' | 'codex' | 'opencode';
  modelParams?: Record<string, any>;
};

type Run = {
  id: string;
  missionId: string;
  squadSnapshot: Squad;     // 启动时快照（只读）
  conversation: Message[];
  artifacts: Artifact[];
  status: 'running' | 'completed' | 'failed' | 'archived';
  startedAt: Date;
  endedAt?: Date;
};
```







