# 面试准备：Agent 系统

---

## Q0: 请简单介绍一下 AgentHub 的 Agent 系统

**参考答复：**

AgentHub 的 Agent 系统是一个 **可注册、可配置、可扩展** 的多 Agent 框架。

**核心架构**：
- `BaseAgent`（抽象基类）：定义 `process_message() → AgentResponse` 的统一接口
- `CustomAgent`（通用实现）：由 `system_prompt + LLMBackend` 驱动的可配置 Agent
- `Adapter` 层（DeepSeekAdapter、TongyiAdapter）：封装不同 LLM 平台的调用细节
- `Internal Agents`（内置专业 Agent）：PlannerAgent、RAGAgent、CodeAnalyzerAgent、SummarizerAgent 等

**Agent 注册来源**：
1. `custom_agents.yaml` — 5 个系统预置 Agent（code_reviewer、product_manager、agent_builder、opencode_coder、opencode_bigpickle）
2. 数据库 `custom_agents` 表 — 用户通过 API 创建的自定义 Agent
3. Internal Agent — 系统中硬编码的专业 Agent

**关键特性**：
- **A-Tier 配置**：每个 Agent 可独立配置 3 个维度（记忆策略、规划模式、校验策略）
- **LLM 后端绑定**：每个 Agent 绑定一个 LLM 后端，支持不同 Agent 用不同模型
- **工具集成**：Agent 可以使用所有注册的 LangChain Tool（web_search、rag_retrieval、file_converter 等）
- **动态创建**：用户可以通过 `agent_builder` Agent 自然语言创建新 Agent

---

## Q1: BaseAgent 和 CustomAgent 的设计关系是怎样的？为什么这样分层？

**参考答复：**

这是一个经典的 **模板方法模式**：

**BaseAgent**（抽象层）：
- 定义统一接口：`process_message(messages, context) → AgentResponse`
- `AgentResponse` 包含 `final_answer: FinalAnswer`（统一返回格式）
- 所有 Agent 的公共行为可以放在这里

**CustomAgent**（实现层）：
- 继承 BaseAgent，实现 `process_message()`
- 核心逻辑：拼接 system_prompt + 历史消息 → 调用 LLMBackend.chat() → 返回回复
- 支持 `from_config()` 工厂方法，从配置字典创建

**分层的好处**：
1. 用户创建的 Agent（来自数据库）和系统预置 Agent（来自 YAML）都走 CustomAgent，代码复用
2. 如果需要一种全新的 Agent 类型（如基于规则的非 LLM Agent），可以继承 BaseAgent 独立实现
3. Orchestrator 只依赖 BaseAgent 接口，不关心具体实现——符合依赖倒置原则

---

## Q2: Agent 的 A-Tier 配置（记忆、规划、校验）是如何实现的？这三个维度具体怎么配？

**参考答复：**

A-Tier 是每个 Agent 的三个独立配置维度，存储在 `custom_agents` 表的 JSON 字段中：

**1. memory_config（记忆策略）**：
```json
{
  "strategy": "sliding_window",  // none | sliding_window | summary
  "window_size": 10,
  "summary_threshold": 4000
}
```
控制该 Agent 如何处理历史消息。

**2. planning_config（规划模式）**：
```json
{
  "mode": "react",  // direct | react | plan_execute
  "max_iterations": 3
}
```
- `direct`：直接 LLM 调用，无工具
- `react`：ReAct 循环，可以使用 LangChain Tool
- `plan_execute`：先规划再执行（复杂任务）

**3. validation_config（校验策略）**：
```json
{
  "strategy": "llm_judge",  // none | rules | llm_judge
  "rules": [{"type": "regex", "pattern": ".*", "message": "..."}],
  "max_retries": 2
}
```
控制 LLM 输出后的质量校验。

这三个维度可以自由组合，适应不同 Agent 的需求。例如代码审查 Agent 需要 `react + rules`（需要工具 + 输出格式严格），而闲聊 Agent 只需要 `direct + none`。

---

## Q3: custom_agents.yaml 中的 Agent 是怎么被加载和注册的？

**参考答复：**

加载流程在 `_setup_agents()` 中：

1. 读取 `custom_agents.yaml` 文件，解析 YAML 数组
2. 遍历每个 Agent 定义：
   - 提取 `agent_id`、`name`、`description`、`system_prompt`
   - 从 `llm_config` 中获取 `adapter_id` 和 `model_name`
   - 用 `adapter_id` 查找对应的 LLM 后端（如"tongyi" → TongyiBackend）
   - 用 `model_name` 覆盖后端的默认模型（如"qwen-long"）
   - 创建 `CustomAgent(agent_id, system_prompt, llm_backend, name)`
3. 将 CustomAgent 实例注册到 `self.agents[agent_id]`

关键细节：
- Agent 的 YAML 定义和 LLM Backend 是分离的——Agent 引用 adapter_id，adapter_id 对应已注册的后端
- `model_name` 可以覆盖后端默认模型，实现同一后端不同模型
- 如果 YAML 解析失败，单个 Agent 加载失败不影响其他 Agent

---

## Q4: agent_builder 是怎么实现"用自然语言创建 Agent"的？

**参考答复：**

agent_builder 是系统的元 Agent，负责 Agent 生命周期管理。它的实现：

**System Prompt**：详细的 Agent 创建指南，包括：
- 需要收集哪些信息（名称、描述、系统提示词、LLM 后端、工具等）
- 如果信息不足要主动追问
- 配置的约束规则（命名规范、system_prompt 要求）

**工具支持**：agent_builder 通过 `manage_agent` 工具与数据库交互：
- `manage_agent.create_agent(name, description, system_prompt, ...)` → 写入 custom_agents 表
- `manage_agent.update_agent(agent_id, ...)` → 更新已有 Agent
- `manage_agent.delete_agent(agent_id)` → 删除 Agent
- `manage_agent.list_agents()` → 查看所有 Agent

**工作流程**：
1. 用户说"帮我创建一个擅长前端开发的 Agent"
2. agent_builder 分析需求 → 如果信息不全（如没有指定 LLM 后端），追问用户
3. 信息收集完整后 → 调用 `manage_agent.create_agent()` 写入数据库
4. Orchestrator 的后台定时刷新机制（60 秒）自动加载新 Agent

---

## Q5: Internal Agent（PlannerAgent、RAGAgent 等）和 CustomAgent 有什么不同？为什么是两种实现？

**参考答复：**

这两类 Agent 的本质区别：

**CustomAgent**（数据驱动）：
- 行为完全由 `system_prompt + LLMBackend` 定义
- 配置存储在 YAML 或数据库中
- 可以在运行时动态创建、修改
- 适合：角色型 Agent（代码审查专家、产品经理等）

**Internal Agent**（逻辑驱动）：
- 有固定的内部逻辑和专门的 prompt 模板
- 行为硬编码在 Python 类中，不能通过配置修改
- 在系统关键流程中使用
- 适合：系统功能型 Agent（Planner、Summarizer、Evaluator）

**分开实现的原因**：
- Internal Agent 需要严格的输出格式（如 Planner 必须输出 JSON 计划），通过专用 prompt + 解析逻辑保证
- CustomAgent 面向终端用户，需要灵活性——用户可以任意修改 system_prompt
- 混合使用会破坏 Internal Agent 的可靠性——如果用户把 Planner 的 system_prompt 改乱了，整个动态规划流程就崩了

---

## Q6: Agent 的 ReAct 执行模式是怎么实现的？

**参考答复：**

ReAct（Reasoning + Acting）模式让 Agent 可以调用工具。实现方式：

**1. Tool 封装**：所有工具类 Skill 通过 `@tool` 装饰器封装为 LangChain Tool：
```python
wrapped_tool = tool(skill_func)
wrapped_tool.name = skill_key
```

**2. ReAct Prompt**：使用专门的 ReAct prompt 模板（定义在 `orchestrator_prompts.yaml`），指导 LLM 按格式输出：
```
Thought: 我需要搜索相关知识...
Action: web_search
Action Input: Python async best practices
Observation: [搜索结果]
Thought: 根据搜索结果...
Final Answer: ...
```

**3. 循环控制**：通过 `REACT_MAX_ITERATIONS = 3` 限制最大循环次数，防止无限 ReAct 循环消耗过多 token

**4. 执行流程**：LLM 输出 → 解析 Action → 执行 Tool → 将 Observation 反馈给 LLM → 循环直到输出 Final Answer 或达到最大迭代

---

## Q7: Agent 的 fallback 链是什么？如何配置？

**参考答复：**

Agent 的 fallback 链定义了当前 Agent 调用失败时，可以降级到哪些替代后端：

```python
AGENT_FALLBACK_CHAIN = {
    "opencode_coder": ["tongyi", "deepseek"],
    "deepseek": ["tongyi"],
}
```

**工作流程**：
1. Agent 调用主 LLM 后端失败
2. 查找该 Agent 的 fallback 链
3. 按顺序尝试 fallback 后端（检查 `_healthy` 状态）
4. 第一个健康的 fallback 后端接管调用
5. 如果全部 fallback 都失败 → 返回错误消息

**为什么 OpenCode 有更长的 fallback 链**：OpenCode 是免费服务，稳定性不如付费 API，所以需要更完善的降级保障。

**当前限制**：fallback 只切换 LLM 后端，不修改 system_prompt。如果 system_prompt 对特定模型有优化（如 DeepSeek 的 prompt 和 Tongyi 的 prompt 可能不完全兼容），降级后的回答质量可能下降。

---

## Q8: 用户通过 API 创建的自定义 Agent 是如何生效的？需要重启服务吗？

**参考答复：**

不需要重启服务，通过**定时刷新机制**实现热加载：

1. 用户通过 `/api/agents` 创建 Agent → 写入 `custom_agents` 表
2. Orchestrator 的后台线程每 60 秒执行 `refresh_user_skills()`（实际上也刷新 Agent）
3. 刷新流程：
   - 清理旧的用户创建的 Agent
   - 从数据库重新加载所有用户创建的 Agent
   - 更新 `self.agents` 字典
   - `agent_builder` 创建成功后立即触发一次刷新

**最大延迟**：60 秒。如果用户需要在创建后立即使用，`agent_builder` 会在创建成功后主动触发一次即时刷新，减少等待时间。

这种设计避免了每次创建都重启服务，但也意味着高并发场景下需要考虑 Agent 注册表的并发安全（当前实现中用简单的字典更新）。

---

## Q9: Agent 间如何协作完成一个复杂任务？以一个具体例子说明。

**参考答复：**

以"帮我分析这段代码的性能问题并给出优化方案"为例：

1. **用户消息** → Orchestrator
2. **复杂度分类** → LLM 判断为 complex（需要多步骤分析）
3. **PlannerAgent 拆解** → 生成子任务计划：
   ```json
   [
     {"task": "代码静态分析", "agent": "code_reviewer"},
     {"task": "漏洞扫描", "agent": "vulnerability_scanner"},
     {"task": "生成综合报告", "agent": "report_generator", "depends_on": [0, 1]}
   ]
   ```
4. **并行执行**：code_reviewer 和 vulnerability_scanner 并行运行
5. **依赖等待**：report_generator 等待前两个完成后执行
6. **结果评估**：Evaluator 检查报告质量
7. **Summarizer 汇总** → 最终回答返回给用户

整个过程中，Orchestrator 通过 progressive_queue 推送中间进度，用户实时看到"正在进行代码分析...""正在进行漏洞扫描..."等状态更新。

---

## Q10: Agent 的 system_prompt 是如何设计的？有没有什么设计原则？

**参考答复：**

System prompt 的设计遵循几个原则（以 code_reviewer 为例）：

```yaml
system_prompt: >
  你是一个世界级的软件工程师，专长是代码审查。
  你的任务是：
  1. 仔细阅读用户提供的代码。
  2. 识别出其中潜在的 bug、性能问题、不符合最佳实践的地方或安全漏洞。
  3. 提出清晰、具体、可执行的改进建议。
  4. 你的回答应该总是专业、严谨且具有建设性。
  5. 如果代码质量很高，也不要吝啬你的赞美。
```

设计原则：
1. **角色设定清晰**："世界级的软件工程师"——明确能力水平
2. **任务边界明确**：列出 1-5 的具体任务，不模糊
3. **输出质量约束**："专业、严谨、具有建设性"、"清晰、具体、可执行"
4. **正面引导**："不要吝啬你的赞美"——避免只找问题不认可好代码
5. **简洁**：system_prompt 尽量简短，减少 token 消耗，为对话历史留出空间

---

## Q11: DeepSeekAdapter 和 TongyiAdapter 的职责是什么？为什么需要 Adapter 层？

**参考答复：**

Adapter 层是 LLM 后端的封装，提供了统一的 Agent 调用接口：

```
BaseAgent → Adapter（统一接口） → LLMBackend（具体实现） → API
```

**为什么需要 Adapter 层**：
1. **隔离变化**：不同 LLM 平台的 API 格式不同（虽然都声称 OpenAI-compatible，但细节有差异），Adapter 屏蔽这些差异
2. **Agent 解耦**：Agent 不直接依赖具体 LLM 平台，只依赖 Adapter 接口
3. **配置灵活性**：同一个 Agent 可以绑定不同的 Adapter（切换 LLM 不需要改 Agent 代码）

**当前实现中**，Adapter 层和 LLMBackend 层有一定重叠（两者都做了 API 调用的封装）。这是在多次重构中形成的中间状态，后续可以进一步统一。

---

## Q12: 如何保证自定义 Agent 的 system_prompt 质量？有提供 prompt 优化功能吗？

**参考答复：**

项目中提供了 **AI 优化提示词** 功能：

通过 `/api/agents/improve-prompt` 接口，用户可以提交原始 system_prompt，LLM 自动分析并优化：
- 补充缺失的任务定义
- 优化表述的清晰度
- 添加输出格式约束
- 检查潜在的歧义

**agent_builder 的约束**：在创建 Agent 时，agent_builder 会主动检查 system_prompt 的完整性，如果信息不足会追问。例如如果用户只说"创建一个前端 Agent"，agent_builder 会追问"这个 Agent 擅长使用哪些前端框架？React/Vue/Angular？需要什么级别的代码输出？"

---

## Q13: orchestrator 中的 `_call_agent_with_tools` 方法做了什么？工具调用的完整链路是什么？

**参考答复：**

`_call_agent_with_tools` 是 Agent + 工具的集成执行器：

1. 构造 prompt（system_prompt + 工具列表 + 用户消息）
2. 调用 LLM 后端获取回复
3. 解析回复中的 Action/Action Input 标记
4. 如果存在 Action → 在 tool_skills 中查找对应工具并执行
5. 将工具执行结果（Observation）反馈给 LLM
6. 重复 3-5 直到输出 Final Answer 或达到最大迭代
7. 在流式模式下，工具调用过程和结果通过 progressive_queue 推送给前端

**完整链路**：Orchestrator → Agent.process_message() → ReAct 循环 → LLMBackend.chat() → httpx → API 提供商

工具调用的中间状态（Thought、Action、Observation）在流式模式下是否展示给用户取决于配置——tool_output 事件默认被消费但不渲染。

---

## Q14: 如果有 10 个用户同时创建 Agent，定时刷新会有并发问题吗？

**参考答复：**

当前定时刷新是单线程的（后台 daemon 线程），每 60 秒执行一次，不存在刷新本身的并发问题。

但在 Agent 创建和刷新之间有一个**时间窗口问题**：
- 用户在 t=0 创建 Agent → 写入数据库
- 刷新在 t=60 执行 → 加载新 Agent
- 用户在 t=30 尝试 @mention 新 Agent → Agent 尚未注册 → 找不到 Agent

**agent_builder 的优化**：创建成功后立即触发一次同步刷新（`refresh_user_skills()`），将时间窗口缩短到几乎为零。

**并发写入问题**：目前 `self.agents` 字典的读写没有加锁。虽然在 Python GIL 下基本安全，但如果引入异步刷新机制，需要考虑线程安全问题。

---

## Q15: Agent 的 validation 策略（rules/llm_judge）是如何实现的？什么场景下用哪种？

**参考答复：**

Validation 策略在 LLM 输出后进行质量校验：

**rules 策略**：
- 检查项：正则匹配、JSON Schema 校验、字符串包含等
- 实现：`_validate_rule_regex()` + `_validate_rule_json_schema()`
- 适用场景：输出格式有明确约束（如必须包含代码块、必须是有效 JSON）
- 优点：快速、确定性、无额外 LLM 调用

**llm_judge 策略**：
- 再调一次 LLM，让其评估输出是否合格
- 实现：`_validate_llm_judge()`，传入 judge_prompt 和原始回答
- 适用场景：输出质量需要语义判断（如回答是否完整、逻辑是否清晰）
- 缺点：额外 LLM 调用，成本和时间翻倍

**选择建议**：能用 rules 就不用 llm_judge（节省成本）。只有语义质量无法用规则描述时才用 llm_judge。

**重试机制**：校验失败 + `retries_left > 0` → 将失败原因反馈给 LLM → 重新生成 → 再次校验。

---

## Q16: 如果 Agent 的回复被截断了（因为 max_tokens 限制），系统会怎么处理？

**参考答复：**

截断检测和恢复：

1. **响应完整性检查**：`check_response_completeness()` 函数检查 LLM 回复是否完整：
   - 检查是否以自然结束符结尾
   - 检查未闭合的代码块
   - 检查 JSON 是否完整
2. **截断处理**：如果检测到截断 → 自动触发 continuation 请求，让 LLM 继续生成
3. **完整回复拼接**：将原始回复和 continuation 回复拼接为完整回答

这个机制对用户透明——前端看到的是拼接后的完整回复，不会感知到截断和恢复的过程。

---

## Q17: 项目中的 Agent 和 LangChain 的 Agent 概念有什么区别？

**参考答复：**

核心区别：AgentHub 的 Agent 是**更高层级的抽象**。

**LangChain Agent** 是一个 ReAct 循环 + Tool 的单一实体：接收输入，通过思考-行动-观察循环，输出结果。

**AgentHub Agent** 是一个**可配置的角色**：
- 有 identity（agent_id、name、description、icon）
- 有专属的 system_prompt（定义"人格"和能力边界）
- 绑定特定的 LLM 后端
- 可选启用 ReAct（通过 planning_config.mode = "react"）
- 有独立的记忆/校验配置
- 可被 Orchestrator 调度和编排

AgentHub 的 Agent 内部可能使用 LangChain 的 ReAct Agent（如果启用了 react 模式），但 AgentHub 的 Agent 本身是一个更上层的概念——它是一个可被调度、可被 mention、可被管理的独立实体。

---

## Q18: 如何设计一个 Agent 的"能力边界"？怎么让 Agent 在被问到超出能力范围的问题时妥善处理？

**参考答复：**

能力边界的定义通过 system_prompt 实现：

1. **明确声明能力范围**："你是一个代码审查专家，擅长阅读和分析代码"
2. **显式边界**："如果用户的问题与代码无关，礼貌地说明你的专业领域并建议使用其他 Agent"
3. **引导用户**："如果你需要产品需求分析，可以 @product_manager"

在 system_prompt 中定义边界有几个技巧：
- 使用**正向**描述能力（"你擅长..."）而非负向（"你不会..."）——效果更好
- 给出**具体场景**作为示例（"如果用户问天气..."）
- 建议**替代方案**（"建议使用 @xxx"），不要只说"我不会"

这项设计责任在 Agent 创建者，agent_builder 在创建 Agent 时会帮助检查 system_prompt 是否包含足够的能力边界描述。

---

## Q19: Agent 的执行过程是如何被追踪和记录的？

**参考答复：**

Agent 执行过程的追踪通过多个层面：

1. **数据库记录**：每个子 Agent 的回复作为独立 Message 写入 messages 表（agent_id 区分）
2. **流式推送**：intermediate 消息通过 progressive_queue/WebSocket 实时推送到前端
3. **日志系统**：关键节点（Agent 开始执行、工具调用、执行完成）有结构化日志
4. **LangGraph Checkpoint**：如果走动态规划流程，完整的 GraphState 被 checkpoint 持久化

前端展示：在复杂任务的执行过程中，用户能看到"流水线"式的进度展示——每个子 Agent 的输入、输出按时间顺序排列。这提供了执行过程的可追溯性。

---

## Q20: 如果要支持 Agent 的市场/共享机制（让用户分享他们创建的 Agent），你会怎么设计？

**参考答复：**

Agent 市场的设计方案：

1. **数据模型扩展**：在 `custom_agents` 表中增加 `is_published`、`install_count`、`rating`、`tags` 字段
2. **市场 API**：`/api/agents/marketplace` — 浏览、搜索、排序（按安装量/评分）
3. **安装机制**：用户点击"安装"→ 复制 Agent 配置到用户的 namespace → 可在本地修改
4. **版本管理**：Agent 更新后，已安装的用户收到更新通知（可选同步）
5. **审核机制**：system_prompt 需要经过内容审核（防止恶意 prompt injection）
6. **评分和评论**：用户可以对 Agent 评分和评论

安全考虑：
- 共享 Agent 的 system_prompt 可能有 prompt injection 风险
- 需要在安装前做沙箱化检查
- 共享 Agent 绑定的 LLM 后端可能在其他用户环境中不可用

这个设计参考了 Skill 市场（项目中已实现的 Skill 安装机制），可以复用大部分模式。
