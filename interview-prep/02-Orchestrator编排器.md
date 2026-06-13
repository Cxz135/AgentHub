# 面试准备：Orchestrator 编排器

---

## Q0: 请简单介绍一下 AgentHub 的 Orchestrator 模块

**参考答复：**

Orchestrator 是 AgentHub 的中央调度引擎，约 3256 行代码，是整个系统的大脑。它的核心职责是：接收用户消息后，自动判断任务类型和复杂度，然后路由到最合适的处理路径。

初始化时按严格顺序加载：LLM 后端 → 健康检查 → 记忆服务 → Skill 加载 → Agent 注册 → 工作流注册 → 动态规划图构建。这个顺序是经过多次重构迭代确定的最优顺序。

核心路由采用 **5 级优先级决策链**：
1. 检测 @mention → 单 Agent 或多 Agent 群聊
2. Agent 管理请求 → 路由到 agent_builder
3. 关键词匹配固定工作流 → RAG 或 Code Review
4. LLM 复杂度分类 → complex 走动态规划，moderate 走专家 Agent，simple 直接回复
5. 系统查询 → Orchestrator 自回复

路由前后分别执行记忆增强（语义检索 + 用户画像注入）和记忆提取（LLM 提取事实 → 持久化 → 衰减），形成一个完整的对话处理管线。

---

## Q1: Orchestrator 的初始化顺序为什么那么重要？具体顺序是什么？

**参考答复：**

初始化顺序的设计原则是"先核心基础设施，后业务功能"。具体顺序和原因：

1. **`_setup_backends()`** — 最先注册 LLM 后端（Tongyi、DeepSeek、OpenCode），因为后续所有组件都依赖 LLM 调用
2. **`_health_check_backends()`** — 同步验证后端连通性，防止用不了的后端污染 Agent 注册
3. **`create_memory_service()`** — 初始化记忆服务，但用 try/except 包裹（非致命），未配置也不影响主流程
4. **`_load_native_skills()`** — 加载 Markdown Skill 文件
5. **`_load_user_skills_from_db()`** — 加载用户创建的 Skill
6. **`_register_builtin_tool_skills()`** — 注册 Python 工具函数并封装为 LangChain Tool（此时 Skill 已就绪，Agent 注册时需要这些 tools）
7. **`_setup_agents()`** — 注册所有 Agent（此时 tools 已就绪，可以创建 ReAct 执行器）
8. **`_register_builtin_workflows()`** — 注册固定工作流
9. **`_load_custom_agents_from_db()`** — 加载用户自定义 Agent（必须在规划图之前，确保 Planner 可见）
10. **`_build_planning_graph()`** — 构建动态规划图（此时所有 Agent 已就绪）
11. **`_start_user_skills_refresh_timer()`** — 启动后台 60 秒定时刷新

如果顺序错误（比如先注册 Agent 再注册 tools），Agent 的 ReAct 循环就会缺少可用工具。

---

## Q2: 路由决策的完整优先级是什么？为什么这样设计？

**参考答复：**

路由优先级从高到低：

1. **@mention 检测**：用正则 `@(\w+)` 提取，支持多个 mention → 群聊并行
2. **Agent 管理请求**：LLM 分类为 `agent_management` → 路由到 agent_builder
3. **固定工作流匹配**：关键词打分，得分 > 6 → 触发 RAG/Code Review 工作流
4. **LLM 复杂度路由**：complex → 动态规划、moderate → 专家 Agent、simple → 直接回复
5. **系统查询**：如"有哪些 Agent"→ Orchestrator 自查
6. **默认聊天**：兜底路由到主 Agent

优先级设计的核心逻辑是："显式意图优先于隐式推断"。@mention 是用户最明确的意图（"我就要这个 Agent"），所以最高优先级。Agent 管理请求虽然也是 LLM 推断的，但因为需要调用修改系统的工具，所以排在固定工作流之前。固定工作流之所以排在复杂度路由之前，是因为关键词匹配更可靠——如果用户明显在问"什么是"（触发 RAG），那就直接走 RAG 流程，不要再让 LLM 判断一次复杂度。

---

## Q3: `_classify_complexity` 的 LLM 分类和关键词降级是如何协同的？

**参考答复：**

这是一个 **LLM 优先 + 规则兜底** 的双层分类策略：

**主路径（LLM 分类）**：调用 Tongyi 后端，传入精心设计的 prompt，要求返回 `simple`/`moderate`/`complex`/`agent_management` 四分类之一。LLM 能理解语义（如"帮我设计一下系统架构"虽然不含"复杂"二字，但 LLM 能判断需要多步骤），比关键词匹配更准确。

**降级路径（关键词规则）**：当 LLM 调用失败时（网络超时、API 异常等），自动降级到 `_fallback_complexity_rule()`：
- 短消息（< 15 字符）→ simple
- 含"开发一个"、"架构"、"重构"等词 → complex
- 含"写一个"、"debug"、"优化"等词且长度 > 30 → moderate
- 含"创建 agent"等词 → agent_management
- 其他 → simple

这种双层设计保证了：正常情况下的智能分类 + 异常情况下的不中断服务。

---

## Q4: @mention 多 Agent 群聊是如何实现的？怎么收集和汇总多个 Agent 的回复？

**参考答复：**

@mention 的支持通过正则 `MENTION_REGEX = r'@(\w+)'` 实现。

**单 Agent mention**：提取 `@agent_id`，去掉消息中的 @mention 前缀，将纯净消息发送给指定 Agent，返回其回复。

**多 Agent 群聊**：当检测到 2 个或以上有效 Agent ID 时：
1. 将用户消息（保留原始 @mention 以便每个 Agent 知道上下文）并行发送给所有被 mention 的 Agent
2. 使用 `asyncio.gather()` 并行等待所有 Agent 回复
3. 收集所有回复，格式化为群聊展示格式（标明每条回复来自哪个 Agent）
4. 统一返回给前端

这里需要注意的一点是：多 Agent 之间不直接对话，而是各自由用户消息独立驱动。这是一种"星型"通信拓扑，而非网状拓扑。

---

## Q5: `get_chat_stream` 的流式输出是如何设计的？progressive_queue 的作用是什么？

**参考答复：**

`get_chat_stream` 的设计核心是 **生产者-消费者 + 并发** 模式：

1. **后台任务**：`get_chat_response()` 作为 `asyncio.Task` 在后台运行，处理完整的路由和 LLM 调用
2. **progressive_queue**：一个 `asyncio.Queue`，后台任务在处理过程中将事件推入其中
3. **前台消费**：主协程轮询队列，实时 yield 事件给前端

事件类型和对应的前端效果：
- `token_event` → 打字机效果逐字显示
- `thinking` → 显示"Agent 正在思考..."动画
- `intermediate` → 显示子 Agent 执行过程的中间消息
- `artifact` → 推送代码/HTML 等产出物，前端渲染为独立卡片
- `tool_output` → 静默消费（不展示给用户）
- 最终 `final` → 完整回答 + 所有中间消息和 artifact 的聚合

关键实现细节：每个请求使用独立的 `per_request_queue`，避免并发请求间的队列污染。main_task 使用 `asyncio.shield()` 保护，防止被取消。

---

## Q6: Agent 的 Fallback 机制具体是怎么实现的？

**参考答复：**

Fallback 机制的核心是一个 **降级链映射表**：

```python
AGENT_FALLBACK_CHAIN = {
    "opencode_coder": ["tongyi", "deepseek"],
    "deepseek": ["tongyi"],
    "tongyi": ["deepseek"],
}
```

当某个 Agent 调用 LLM 失败时：
1. 检查该 Agent 的 `agent_id` 是否有对应的 fallback 链
2. 遍历 fallback 链，找到第一个健康可用的后端
3. 用 fallback 后端重新调用 LLM
4. 如果全部不可用，返回明确的错误消息

这个设计的关键是：fallback 是**按 Agent 粒度**而非全局配置的，因为不同 Agent 对模型的依赖不同（代码审查 Agent 用 DeepSeek 效果最好，fallback 到 Tongyi 可以接受，但反过来不一定）。

---

## Q7: 工具类 Skill 和能力类 Skill 的区别是什么？为什么有两种？

**参考答复：**

这是两种互补的 Skill 机制，对应两种不同的能力扩展方式：

**工具类 Skill（Tool Skill）**：
- 本质是 **可执行的 Python 函数**，如 `web_search`、`rag_retrieval`、`file_converter.to_pdf`
- 通过 `@tool` 装饰器封装为 LangChain Tool
- 在 ReAct 循环中被 Agent 调用：Agent 思考后选择工具，执行工具，观察结果
- 适用场景：需要外部 API 调用、文件操作、数据库操作等确定性的行为能力

**能力类 Skill（Native Skill）**：
- 本质是 **Markdown 格式的 prompt 注入**，描述一种能力或工作模式
- 存储在 `skills/` 目录或数据库 `skills` 表中
- 被注入到 Agent 的 system prompt 中，影响 LLM 的回答风格和内容
- 适用场景：文档生成规范、代码风格约束、特定领域的回答模板等

两种 Skill 互补的原因：有些能力（如联网搜索）必须通过代码实现，而有些能力（如"用学术论文的风格回答"）只需要 prompt 工程。分开管理让用户可以根据需要选择合适的方式扩展 Agent 能力，而且避免了 prompt 膨胀和工具过多的问题。

---

## Q8: Orchestrator 如何在对话过程中实时保存子 Agent 的消息？

**参考答复：**

Orchestrator 持有一个 `db_session` 引用，在处理子 Agent 消息时：

1. 子 Agent 执行完成后，将回复包装为 `Message` 对象（包含 agent_id、content、conversation_id）
2. 通过 db_session 直接写入 `messages` 表
3. 同时推入 progressive_queue，让前端实时展示

这样做的目的是：用户可以在复杂任务的执行过程中，看到每个子 Agent 的工作进度和中间结果，而不用等到全部完成后才看到最终结果。这对于耗时较长的复杂任务来说，大大提升了用户体验。

---

## Q9: Orchestrator 如何处理错误的用户输入和边界情况？

**参考答复：**

Orchestrator 处理边界情况的策略：

1. **空消息**：直接返回"没有收到任何消息"，不进入处理管线
2. **无法识别的 @mention**：过滤掉不在 Agent 注册表中的 ID，如果全部无效则走到默认路由
3. **Agent 调用失败**：通过 fallback 链重试，全部失败后返回错误信息而非崩溃
4. **LLM 返回空内容**：使用 `check_response_completeness()` 检测，必要时触发重试或返回提示
5. **工作流执行失败**：捕获异常，降级为直接 LLM 调用（绕过规划流程）
6. **记忆服务失败**：非致命错误，仅记录 warning 日志，不影响主回答

所有这些边界处理都遵循一个原则：**优雅降级，永不让用户看到 500 错误**。

---

## Q10: `_handle_plan_command` 中的动态规划是如何实现的？

**参考答复：**

动态规划通过 LangGraph 的 StateGraph 实现，包含三个核心节点：

1. **execute_tasks（任务执行）**：
   - PlannerAgent 分析任务，生成 JSON 格式的子任务列表（每个子任务包含 task_id、description、assigned_agent、dependencies）
   - 按依赖关系拓扑排序
   - 并行执行无依赖关系的子任务（使用 `asyncio.gather`）
   - 将各子 Agent 的回复存入 GraphState

2. **evaluate_results（结果评估）**：
   - Evaluator LLM 检查所有子任务是否完成、质量是否达标
   - 如果通过 → 设置 state["final_summary"] 信号，流转到 generate_summary
   - 如果未通过 → 生成新的补充子任务，流转回 execute_tasks（重规划）

3. **generate_summary（生成摘要）**：
   - SummarizerAgent 整合所有子任务结果
   - 生成最终的综合回答
   - 流转到 END

关键设计是条件边 `after_evaluation`：它读取 GraphState 决定下一步是 END 还是重试，这实现了自适应的任务执行——不需要预先知道要执行多少轮。

---

## Q11: 动态规划的重规划（replan）机制是怎样的？

**参考答复：**

重规划是动态规划的核心智能体现。当 evaluator 发现子任务输出不满足要求时：

1. Evaluator 分析哪些子任务的结果不够好（可能信息不完整、质量不够、需要更多上下文）
2. 生成新的补充子任务列表（而非重新执行全部任务）
3. 通过条件边回到 `execute_tasks` 节点
4. 只执行新增的子任务，保留之前已完成的子任务结果

这个设计的优势是 **增量重试** 而非全部重来：已经完成且质量达标的子任务结果会被保留，只有不满足要求的部分才重新执行。这在 token 消耗和响应时间上都更高效。

为了防止无限重规划，有最大迭代次数限制（`DEFAULT_MAX_ITERATIONS = 10`）。

---

## Q12: Orchestrator 中的 memory_summary 是什么？和 MemoryService 有什么区别？

**参考答复：**

这是两个不同层次的记忆机制：

**MemorySummary（LangGraph checkpointer 层面）**：
- 存储在 `AsyncSqliteSaver` 的 checkpoint 中
- 由 LangGraph 内置的摘要机制生成（当消息超过一定长度时自动压缩）
- 作用是让 LangGraph 状态图在多次调用间保持对话连贯性
- 每个 conversation_id 一个 checkpoint

**MemoryService（业务层面）**：
- 5 层记忆框架（指令、短期、工作、摘要、长期语义）
- 包含 LLM 驱动的结构化事实提取、ChromaDB 语义检索、用户画像、衰减机制
- 作用是跨会话积累用户知识、理解用户偏好、提供个性化体验
- 每个 user_id 一份长期记忆

简单类比：MemorySummary 是"这次对话讲了什么"，MemoryService 是"这个用户是什么样的人"。

---

## Q13: 复杂度分类 prompt 的设计思路是什么？

**参考答复：**

复杂度分类 prompt（在 `orchestrator_prompts.yaml` 中）的设计思路：

1. **明确输出格式**：要求 LLM 严格返回四个词之一（simple/moderate/complex/agent_management），避免歧义
2. **提供分类标准**：用具体的例子说明每类的判断标准，而非抽象描述
   - simple：简单问候、事实查询、单步骤操作
   - moderate：需要一定专业知识但不需要多角色协作
   - complex：需要多步骤、多角色协作的任务
   - agent_management：涉及创建/修改/删除 Agent 的请求
3. **给出边界案例**：帮助 LLM 处理模糊情况（如"帮我写一个排序算法"→ moderate，"帮我开发一个电商系统"→ complex）
4. **考虑历史摘要**：传入 `history_summary` 参数，让 LLM 结合上下文判断（如果之前用中文聊技术，现在突然切换话题，也算 complex）

---

## Q14: Orchestrator 如何处理多轮对话中的话题切换？

**参考答复：**

话题切换的检测和处理：

1. **LangGraph checkpointer 加载历史**：每次请求加载 conversation_id 对应的 checkpoint，获取之前的消息和摘要
2. **上下文注入复杂度判断**：将历史摘要传入复杂度分类 prompt，让 LLM 判断当前消息是否是话题切换
3. **话题切换→重新规划**：如果检测到显著的话题变化，清空当前工作记忆中的任务状态，启动新的规划周期
4. **记忆策略缓冲**：对于 sliding_window 策略，保留最近 N 轮对话；对于 summary 策略，保留压缩后的历史摘要，让 Agent 即使在新话题中也能引用之前的上下文

这个机制的核心是：不依赖简单的"检测到新话题就清空历史"策略，而是让 LLM 自己判断当前消息在上下文中的复杂度，从而做出更智能的路由决策。

---

## Q15: Skill 注入（active_skills）是怎么工作的？

**参考答复：**

Skill 注入是用户主动启用的能力增强机制：

1. **用户选择**：前端 Skill 管理面板中，用户可以勾选启用的 Skill（如"web_search"、"file_converter"）
2. **请求携带**：前端将启用的 Skill 列表通过 `request_context.active_skills` 传给后端
3. **注入 prompt**：Orchestrator 的 `get_active_skills_injection()` 方法从 `native_skills` 字典中查找对应 Skill 的 Markdown 内容，拼接为统一的注入文本
4. **拼入 system prompt**：注入文本放在 system prompt 的重要位置，前面有"【重要】"标记强调
5. **后处理校验**：`_ensure_skill_prefix_in_output()` 方法检查 LLM 输出是否遵循了 Skill 指令，如果被放到 Thought 部分而非 Final Answer，会尝试修正

这个设计让 Skill 的管理和注入完全解耦：用户随时可以启用/禁用 Skill，不需要修改 Agent 配置。

---

## Q16: Orchestrator 的 `_register_builtin_tool_skills` 是如何动态注册工具的？

**参考答复：**

工具注册使用了 Python 的反射机制：

1. **静态导入知名工具**：`rag_retrieval`、`web_search`、`scan_vulnerabilities` 直接 import
2. **动态导入工具组**：`file_converter`、`manage_agent`、`manage_skill` 使用 `importlib.import_module()` 动态加载模块，读取模块的 `__all__` 列表获取所有导出函数，逐个注册为 `"{module}.{function}"` 格式的工具名
3. **封装为 LangChain Tool**：遍历所有注册的工具函数，用 `@tool` 装饰器包装，设置 `name` 属性，添加到 `langchain_tools` 列表

这种设计的灵活性很高：添加新工具只需在 `utils/` 目录下创建模块并在 `__all__` 中导出函数，Orchestrator 自动发现和注册，不需要修改注册代码。

---

## Q17: get_backend() 的降级逻辑是怎么设计的？

**参考答复：**

`get_backend(name)` 是 LLM 后端访问的统一入口，降级逻辑分两层：

1. **精确匹配**：按名称查找，找到直接返回
2. **默认降级**：找不到时自动降级到 `tongyi` 后端（如果可用的话），并记录 warning 日志
3. **彻底失败**：如果 tongyi 也不可用（所有后端都挂了），抛出 RuntimeError

这个设计的好处是：业务代码不需要关心后端是否可用，只要调用 `get_backend(name)`，系统自动处理降级。同时保留了足够的日志信息用于问题排查。

---

## Q18: Orchestrator 的性能瓶颈在哪里？有做过什么优化？

**参考答复：**

主要瓶颈和优化措施：

**瓶颈1：复杂任务的串行等待。** 虽然子任务内部是并行的，但 evaluate → replan → execute 的循环是串行的。每个循环都需要一次 LLM 调用做评估。优化思路：可以引入投机执行（speculative execution），在评估的同时预执行一些可能需要的子任务。

**瓶颈2：启动时的同步健康检查。** 每个后端需要 8 秒超时，如果后端多或网络慢，启动会变慢。目前是同步的，已标记为可优化为异步。

**瓶颈3：ChromaDB 单客户端。** ChromaDB 的 PersistentClient 锁粒度较大，高并发下可能成为瓶颈。后续可考虑迁移到 ChromaDB 的服务化部署。

**已做的优化**：
- 健康检查只 ping 不实际生成（`max_tokens=5`），减少 API 消耗
- 记忆提取使用 `fire-and-forget`（`asyncio.create_task`），不阻塞主回答
- 流式输出使用独立队列，避免不同请求的队列竞争

---

## Q19: 如果 LLM 返回格式不符合预期（如 Planner 返回非 JSON），如何处理？

**参考答复：**

这是一类常见的 LLM 输出可靠性问题，项目的处理策略是：

1. **Prompt 约束**：在 Planner 的 system prompt 中严格规定输出格式（"严格输出 JSON 数组"），并在 prompt 中给出完整示例
2. **解析容错**：解析时使用 try/except 包裹 `json.loads()`，并尝试从 LLM 输出中提取 JSON 片段（处理 LLM 在 JSON 前后加解释文字的情况）
3. **验证重试**：如果 JSON 解析失败或结构不符合预期，触发重试（最多 `max_retries` 次），重试时在 prompt 中加入"上次输出格式错误，请严格按 JSON 格式输出"
4. **降级兜底**：如果多次重试仍然失败，降级为直接调用默认 Agent，不做任务拆解

这套策略的核心是：尽可能通过 prompt 工程避免问题，发生问题时通过重试修复，实在不行就降级保底。

---

## Q20: 如果让你给 Orchestrator 增加一个新功能（如支持定时任务），你会如何设计？

**参考答复：**

支持定时任务的设计方案：

1. **任务定义**：新增 `ScheduledTask` 数据模型（task_id、user_id、conversation_id、cron_expression、prompt、next_run_at、is_active）
2. **调度器**：在 Orchestrator 中集成一个轻量级调度器（如 APScheduler），在后台线程中运行，按 cron 表达式触发任务
3. **执行流程**：到期时自动构造消息（模拟用户发送），复用现有 `get_chat_response()` 管线，生成回复后通过 WebSocket 推送给用户或保存为通知
4. **管理接口**：新增 API 路由 `/api/scheduled-tasks`，支持 CRUD 操作
5. **持久化**：使用 SQLite 存储任务定义，服务重启后自动加载未过期的任务

关键设计决策：复用现有路由管线而非另起一套——定时任务本质上是"在指定时间触发的自动对话"，处理逻辑和普通对话完全一致，只需要增加触发机制和通知机制。
