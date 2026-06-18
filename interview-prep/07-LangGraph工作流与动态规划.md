# 面试准备：LangGraph 工作流与动态规划

---

## Q0: 请简单介绍一下 AgentHub 中的 LangGraph 工作流和动态规划

**参考答复：**

AgentHub 使用 LangGraph 作为 Agent 编排的核心引擎，实现了两种工作流模式：

**1. 固定工作流（Built-in Workflows）**：
- RAG 工作流：retrieve_knowledge → summarize_content
- Code Review 工作流：analyze_code → scan_vulnerabilities → generate_report
- 通过关键词匹配自动触发

**2. 动态规划工作流（Dynamic Planning）**：
- 通过 LLM 进行任务复杂度自动分类
- 对于 complex 任务，PlannerAgent 将任务拆解为子任务 JSON 计划
- 通过 LangGraph StateGraph 动态执行：execute_tasks → evaluate_results → generate_summary
- 支持条件边：评估结果不合格 → 重规划 → 重新执行
- 支持子任务并行执行

核心数据结构是 `GraphState`（TypedDict），在所有节点间共享。状态通过 `AsyncSqliteSaver` checkpointer 持久化到 SQLite，实现跨请求的状态保持。

---

## Q1: 为什么选择 LangGraph 的 StateGraph 而不是 Chain？

**参考答复：**

StateGraph 和 Chain 的核心区别是控制流：

**Chain（线性流程）**：
- 固定的 A → B → C 流程
- 无条件分支
- 适合：简单的管道式处理

**StateGraph（状态机流程）**：
- 节点 + 边（包括条件边）定义流程
- 支持运行时动态路由（条件边根据 state 决定下一步）
- 支持循环（evaluate → 不通过 → execute）
- 支持 checkpointer（状态持久化）
- 适合：复杂的不确定性流程

**AgentHub 为什么需要 StateGraph**：
- 复杂任务的执行是不确定的——不知道需要执行几轮，每轮可能有不同的子任务
- 需要根据评估结果动态决定：结束 / 重试 / 重新规划
- 需要跨请求保持对话状态（checkpointer）
- 固定工作流虽然简单，但 StateGraph 为未来扩展（如增加人工审核节点）提供了可能

用 Chain 做不到条件路由和循环，如果用纯 Python if-else 实现，代码会变得难以维护。

---

## Q2: GraphState 是如何设计的？包含哪些字段？

**参考答复：**

GraphState 是一个 TypedDict，包含以下核心字段：

```python
class GraphState(TypedDict):
    messages: List[BaseMessage]        # 对话消息历史
    current_task: str                  # 当前正在执行的任务描述
    task_plan: List[dict]              # Planner 生成的子任务计划列表
    completed_tasks: List[dict]        # 已完成的子任务及结果
    intermediate_results: List[str]    # 中间结果汇总
    final_summary: Optional[str]       # 最终摘要（设置此字段触发结束）
    memory_summary: Optional[str]      # 压缩后的历史摘要
    error_count: int                   # 错误计数
```

**设计考量**：
- TypedDict 而非 Pydantic Model——LangGraph 对 TypedDict 的支持更原生
- `final_summary` 作为"结束信号"——节点检查此字段决定是否流转到 END
- `task_plan` 和 `completed_tasks` 分离——可在评估节点中对比计划 vs 完成
- `error_count` 用于防止无限循环

---

## Q3: 动态规划的三个节点（execute_tasks、evaluate_results、generate_summary）各自做什么？

**参考答复：**

三个节点的详细职责：

**execute_tasks（任务执行节点）**：
1. 从 GraphState 中获取 task_plan（子任务列表）
2. 拓扑排序：按依赖关系确定执行顺序
3. 并行执行：无依赖的子任务通过 `asyncio.gather()` 并行执行
4. 每个子任务：分配给指定的 Agent，等待返回结果
5. 将完成的子任务结果写入 `completed_tasks`
6. 如果有子任务失败，记录错误到 `error_count`

**evaluate_results（结果评估节点）**：
1. 读取 `completed_tasks`，检查所有子任务是否完成
2. 调用 LLM（Evaluator）评估每个子任务结果的质量
3. 如果全部通过 → 设置 `final_summary` 信号
4. 如果有不通过的 → 生成补充子任务，更新 `task_plan`
5. 也可以判断"已完成的子任务结果已经足够"→ 直接设为通过

**generate_summary（摘要生成节点）**：
1. 收集所有子任务的输出
2. 调用 SummarizerAgent 整合为最终回答
3. 将 `final_summary` 写入 state
4. 流转到 END

条件边 `after_evaluation` 根据 `final_summary` 是否存在决定下一步。

---

## Q4: 条件边（conditional edges）是如何工作的？在项目中用于什么场景？

**参考答复：**

条件边的核心概念：不固定下一步走向，而是在运行时根据 state 动态决定。

```python
def after_evaluation(state: GraphState) -> str:
    if state.get("final_summary"):
        return "summarize"        # 转到 generate_summary
    return "execute_again"        # 转到 execute_tasks（重试）

workflow.add_conditional_edges(
    "evaluate_results",           # 从这个节点出发
    after_evaluation,             # 决策函数
    {
        "summarize": "generate_summary",
        "execute_again": "execute_tasks"
    }
)
```

**在项目中的应用**：
- evaluate 后根据质量决定：结束 or 重试
- 决策函数是纯 Python 函数，可以访问完整 state，可以做任意复杂的判断

**条件边 vs 固定边**：
- 固定边：A → B（永远这样走）
- 条件边：A → 根据 state → B 或 C 或 D

条件边是 StateGraph 相比 Chain 的核心优势。

---

## Q5: checkpointer（AsyncSqliteSaver）在项目中是如何使用的？它解决了什么问题？

**参考答复：**

checkpointer 是 LangGraph 的状态持久化机制：

```python
_conn = await aiosqlite.connect("agenthub_memory.sqlite")
checkpointer = AsyncSqliteSaver(_conn)

config = {"configurable": {"thread_id": conversation_id}}
# 获取历史状态
current_checkpoint = await checkpointer.aget(config)
# 执行图
graph.invoke(initial_state, config)
# 状态自动保存到 SQLite
```

**解决的问题**：
1. **跨请求状态保持**：用户发送消息 → 图执行 → 状态保存。下次用户发消息 → 从 checkpoint 恢复状态 → 继续执行
2. **对话连续**：同一个 `thread_id`（conversation_id）的多次请求共享状态
3. **断点续传**：如果服务重启，checkpoint 中的状态不丢失

**为什么用独立的 SQLite**：`agenthub_memory.sqlite` 专门用于 checkpoint，与主数据库 `agenthub.db` 隔离，避免 checkpoint 的频繁写入影响主业务。

---

## Q6: 代码审查工作流（CodeReviewWorkflow）的三节点设计是怎样的？

**参考答复：**

Code Review 工作流是一个三节点的固定流程：

**节点1：analyze_code**
- 输入：用户提供的代码 + 审查要求
- 执行：CodeAnalyzerAgent 分析代码结构和质量
- 输出：代码分析报告（结构、复杂度、最佳实践等）

**节点2：scan_vulnerabilities**
- 输入：代码 + 分析报告
- 执行：VulnerabilityScannerAgent 做安全扫描（如 SQL 注入、XSS、硬编码密钥等）
- 输出：漏洞清单及严重级别

**节点3：generate_report**
- 输入：分析报告 + 漏洞清单
- 执行：ReportGeneratorAgent 生成综合报告
- 输出：结构化的审查报告（Markdown 格式）

**流转**：analyze → scan → report → END（线性流程，无条件边）

这是一种**流水线模式**：每个节点只关心自己的任务，输出作为下一个节点的输入。

---

## Q7: 固定工作流和动态规划工作流各适合什么场景？为什么不统一用动态规划？

**参考答复：**

**固定工作流适合**：
- 流程确定、步骤明确的任务（如代码审查总是 3 步）
- 对延迟敏感的任务（固定流程跳过了 LLM 规划环节）
- 高频率调用的任务（如图文检索）

**动态规划适合**：
- 任务不确定、需要灵活拆解的场景
- 复杂程度不一的任务（有时只需要 2 步，有时需要 5 步）
- 需要自适应重试的任务

**不统一用动态规划的原因**：
1. **延迟**：动态规划需要 LLM 先做任务拆解（额外的一次 LLM 调用），对于固定流程是浪费
2. **可靠性**：固定流程的确定性更高（不依赖 LLM 的规划能力）
3. **成本**：动态规划每次都要生成 JSON 计划 + 评估，token 消耗更大

实际策略是**混合使用**：先用关键词匹配判断是否触发固定工作流，匹配不到再走动态规划的复杂度判断。

---

## Q8: 动态规划中子任务的依赖关系是如何处理的？

**参考答复：**

子任务依赖关系在 PlannerAgent 生成的计划中定义：

```json
[
  {"id": 0, "task": "分析代码结构", "agent": "code_reviewer", "depends_on": []},
  {"id": 1, "task": "扫描安全漏洞", "agent": "vulnerability_scanner", "depends_on": []},
  {"id": 2, "task": "生成报告", "agent": "report_generator", "depends_on": [0, 1]}
]
```

**执行逻辑**（在 `_execute_tasks_node` 中）：
1. 解析所有子任务的 `depends_on` 字段
2. 拓扑排序：确定执行批次
   - 批次1：task 0 和 task 1（无依赖）→ 并行执行
   - 批次2：task 2（依赖 0 和 1 完成）→ 等待批次1完成后执行
3. 每批次内的子任务通过 `asyncio.gather()` 并行执行
4. 结果存入 `completed_tasks`

这种设计实现了**最大并行度**：无依赖关系的任务并行执行，有依赖的串行等待。

---

## Q9: RAG 工作流为什么设计为两节点（retrieve + summarize）而不是更多？

**参考答复：**

两节点设计是**职责单一**原则的体现：

**retrieve_knowledge**：只负责"找到相关信息"
- 向量检索
- 结果压缩/排序
- 不关心如何生成回答

**summarize_content**：只负责"基于信息生成回答"
- 拼接 prompt
- LLM 生成
- 不关心中间如何检索

**为什么不用更多节点**（如加一个 query 改写节点）：
- 当前场景下，两节点足够
- 每增加一个节点就增加一次处理延迟
- 多节点增加了状态管理的复杂度

**未来扩展**：如果检索质量不满足需求，可以在 retrieve 之前插入 query_rewrite 节点（用 LLM 改写用户 query 以优化检索），架构上只需新增节点 + 修改边。

---

## Q10: 动态规划的评估节点如何判断子任务是否完成？评估标准是什么？

**参考答复：**

评估通过 **ReplanEvaluator**（`replan_evaluator.py`）的两层决策实现，而非单纯依赖 LLM：

**第一层：代码规则引擎（硬条件判定）**——纯代码逻辑，无需 LLM：
1. 重规划次数 ≥ `MAX_REPLAN_LIMIT`（2）→ 强制降级
2. 子任务已在 `task_states` 中标记为 "retried" 且质量仍不通过 → 硬失败，触发 replan
3. 所有子任务都失败 → 触发 replan
4. 所有子任务都通过 → 直接 complete（跳过 LLM 评估，节省调用）

**第二层：LLM 语义评估**——仅在硬条件未触发时调用：
- 分析每个子任务的质量报告（passed + score + issues）
- 返回 `EvaluationVerdict`：`retry` | `replan` | `degrade` | `complete`
- 每次评估带有 confidence（置信度 0-1）
- 只对不满足要求的子任务生成补充计划（增量重试）

**通过标准**：
- 所有计划中的子任务都已完成
- 每个子任务的质量检查（QC）通过，或虽有小瑕疵但总体可接受
- 子任务之间的衔接正确

**不通过的场景**：
- 某个子任务 Agent 返回了不相关的内容
- 子任务质量不通过且重试无效（硬失败）
- 缺少关键信息

**PlanAnalyzer 辅助**（`plan_analyzer.py`）：从三个维度（步骤数、依赖深度、工具多样性）分析计划复杂度，综合判定为 simple/moderate/complex，辅助评估决策。

---

## Q11: 图形化工作流和代码化工作流各有什么优劣？在这个项目中为什么选择代码化？

**参考答复：**

**图形化工作流（如 LangSmith Studio、Flowise）**：
- 优点：可视化，非技术人员也能搭建；拖拽式操作
- 缺点：复杂逻辑（如条件边中的动态决策）难以表达；版本控制不方便

**代码化工作流（LangGraph StateGraph）**：
- 优点：任意复杂的逻辑都能表达；Git 版本控制；IDE 支持（自动补全、类型检查）；易于测试
- 缺点：非技术人员无法直接修改

**AgentHub 选择代码化的原因**：
1. 工作流中涉及复杂的 LLM 调用和 prompt 工程，代码化更灵活
2. 条件边的决策逻辑需要访问数据库和 Agent 注册表，图形化工具做不到
3. 项目本身就是代码驱动的，图形化会增加维护负担
4. 用户自定义工作流通过 Agent 创建（自然语言）而非拖拽，不需要可视化编辑器

---

## Q12: 如果 PlannerAgent 生成的计划质量不好（如子任务划分不合理），系统是如何应对的？

**参考答复：**

应对策略分几个层面：

**1. 生成阶段优化**（prompt 约束）：
- Planner 的 prompt 中包含详细的子任务划分指南和示例
- 明确每个 Agent 的能力边界，避免分配不合理任务

**2. PlanAnalyzer 分析**（纯函数，`plan_analyzer.py`）：
- 从 Planner 输出的 TaskSpec 列表中自动分析三个维度：
  - 步骤数（1-3=simple, 4-7=moderate, 8+=complex）
  - 依赖深度（DAG 拓扑排序计算深度）
  - 工具/领域多样性（统计涉及的 Agent 种类）
- 综合判定取三个维度的最高级别，用于辅助评估决策

**3. 评估阶段纠正**（ReplanEvaluator 两层决策）：
- 硬条件判定：检测到子任务划分过粗导致的覆盖问题 → 触发 replan
- LLM 语义评估：分析质量报告后决定 retry/replan/degrade/complete

**4. 重规划机制**：
- 评估不通过 → 生成新的补充计划（而非完全重新规划）
- 补充计划通常更精细，弥补原计划的不足

**5. 降级兜底**：
- 如果 `MAX_REPLAN_LIMIT = 2` 次重规划后仍然不行，强制降级为直接 LLM 调用

**核心设计理念**：不追求一次完美，而是通过"规划 → 执行 → 评估 → 重规划"的循环逐步逼近，同时通过硬上限保证不会无限循环。

---

## Q13: 动态规划中如何避免无限循环？（如：evaluate 永远不通过 → 不断重试）

**参考答复：**

防止无限循环的多层保护（代码规则而非依赖 LLM 自觉）：

1. **重规划次数硬上限**：`MAX_REPLAN_LIMIT = 2`——超过后 ReplanEvaluator 的硬条件判定直接返回 `degrade`，强制降级为直接 LLM 调用
2. **单个子任务重试上限**：`MAX_TASK_RETRIES = 3`——子任务重试超过此次数且仍失败，标记为 "retried" 状态，硬条件判定检测到此状态触发 replan 或 degrade
3. **硬条件判定前置**：在 LLM 语义评估之前，先检查代码规则（次数上限、硬失败数、全失败），避免了"LLM 评估不通过 → 重试 → LLM 再评估不通过"的恶性循环
4. **降级链**：retry（单任务重试）→ replan（重新规划）→ degrade（放弃规划，直调 LLM）
5. **全部通过优化**：如果所有子任务都通过质量检查，直接 complete，完全跳过 LLM 评估调用——既不浪费 token，也避免了 LLM 过度挑剔导致的不必要重试

这套机制的核心设计理念是"代码规则兜底 + LLM 辅助判断"：硬条件保证不会失控，LLM 提供灵活判断。

这些保护机制确保即使在最坏情况下，系统也能返回一个"不完美但有用"的结果，而非无限循环。

---

## Q14: LangGraph 的 MemorySaver 和 AsyncSqliteSaver 在项目中分别用于什么场景？

**参考答复：**

项目中主要使用 **AsyncSqliteSaver**：

**AsyncSqliteSaver**（持久化）：
- 基于 aiosqlite（异步 SQLite）
- 状态持久化到磁盘（`agenthub_memory.sqlite`）
- 服务重启后状态不丢失
- 用于：生产环境的对话状态保持

**MemorySaver**（内存）：
- 基于 Python dict
- 只在进程生命周期内有效
- 服务重启后状态丢失
- 用于：临时场景或测试

**项目中的使用**：
```python
# 主流程使用 AsyncSqliteSaver
_conn = await aiosqlite.connect("agenthub_memory.sqlite")
self._checkpointer = AsyncSqliteSaver(_conn)

# 降级场景使用 MemorySaver（如多个 mention 的路由中）
temp_checkpointer = MemorySaver()
```

选择 AsyncSqliteSaver 是因为：对话状态需要在请求间持久保持（用户可能关闭浏览器再打开，对话历史应该还在）。

---

## Q15: 工作流中的错误处理是怎么做的？如果某个子节点失败了，整个流程会怎样？

**参考答复：**

工作流中的错误处理策略：

**节点级错误**：
- 每个节点的执行包裹在 try/except 中
- 失败 → 记录错误日志 + 在 state 中标记
- 不直接崩溃，让流程继续

**子任务级错误**：
- 某个子 Agent 调用失败 → 触发 fallback 链重试
- fallback 全部失败 → 该子任务标记为失败，记录错误原因
- 不影响其他子任务的并行执行

**流程级错误**：
- evaluate 节点检测到有失败的子任务 → 决定是否需要重试
- 如果是关键子任务失败 → 触发重规划
- 如果非关键子任务失败 → 可能跳过，继续用已有结果生成摘要

**降级策略**：
- 整个工作流失败 → 降级为直接 LLM 调用（绕过规划流程）
- 返回给用户的错误消息是友好的人类可读文本，而非异常堆栈

---

## Q16: 工作流的 prompt 是如何管理的？（workflow_prompts.yaml 的内容和作用）

**参考答复：**

工作流相关的 prompt 统一在 `workflow_prompts.yaml` 中管理：

**包含的 prompt 模板**：
- **plan_evaluation**：评估节点用的 prompt（检查子任务完成度和质量）
- **memory_compression**：总结历史对话时的压缩 prompt
- **task_execution**：单个子任务执行时的 prompt（包含上下文注入）
- **fallback**：工作流失败时的降级 prompt

**使用方式**：
```python
prompt = self.prompt_loader.get('workflow', 'plan_evaluation',
    task_plan=json.dumps(task_plan),
    completed_results=json.dumps(completed_tasks),
)
```

集中管理的好处：调整 prompt 不需要找到对应代码位置，所有工作流 prompt 在一个文件中一目了然。

---

## Q17: 如果要在项目中新增一个"文档翻译"工作流，需要做什么？

**参考答复：**

新增工作流的完整步骤：

1. **创建工作流类**（`backend/workflows/translation_workflow.py`）：
   ```python
   class TranslationWorkflow(BaseWorkflow):
       @staticmethod
       def build():
           workflow = StateGraph(GraphState)
           workflow.add_node("detect_language", detect_fn)
           workflow.add_node("translate", translate_fn)
           workflow.add_node("proofread", proofread_fn)
           workflow.set_entry_point("detect_language")
           workflow.add_edge("detect_language", "translate")
           workflow.add_edge("translate", "proofread")
           workflow.add_edge("proofread", END)
           return workflow
   ```

2. **注册工作流**（在 Orchestrator 的 `_register_builtin_workflows` 中）：
   ```python
   self.workflows["translation"] = {
       "graph": TranslationWorkflow.build(),
       "keywords": ["翻译", "translate", "译成"],
       "description": "文档翻译工作流"
   }
   ```

3. **创建 Agent**（如果需要专用的翻译 Agent，在 `custom_agents.yaml` 中添加）

4. **添加 prompt**（在 `workflow_prompts.yaml` 中添加翻译相关的 prompt）

5. **测试**：确保用户输入"帮我把这段翻译成英文"时触发翻译工作流

---

## Q18: 动态规划的执行过程中，用户能看到什么？前端如何展示进度？

**参考答复：**

用户在复杂任务执行过程中看到的：

1. **思考阶段**：Orchestrator 显示"正在分析任务复杂度..."
2. **规划阶段**：PlannerAgent 生成计划后，前端展示"任务已拆解为 X 个子任务"
3. **执行阶段**：通过 progressive_queue 推送 intermediate 消息：
   - "Agent A 正在分析代码结构..."
   - "Agent B 正在扫描安全漏洞..."
   - 并行执行时，两个进度同时展示
4. **评估阶段**：显示"正在检查执行结果..."
5. **汇总阶段**：Summarizer 输出最终的综合回答

**前端渲染方式**：
- 通过 WebSocket 接收 streaming 事件
- intermediate 消息以流水线卡片展示（类似 CI/CD pipeline）
- 子 Agent 的输出默认折叠，用户可以展开查看
- Artifact（代码文件）以独立卡片渲染

---

## Q19: GraphState 中的 messages 字段和数据库中的 messages 表是什么关系？

**参考答复：**

两者服务于不同目的：

**GraphState.messages**（内存中的）：
- 每个工作流执行实例的运行时状态
- 只在当前请求生命周期内有效
- 通过 checkpointer 持久化，下次请求恢复
- 格式：LangChain 的 BaseMessage（HumanMessage、AIMessage 等）
- 用途：LangGraph 节点间传递对话上下文

**messages 表（数据库中的）**：
- 永久存储的所有对话消息
- 跨请求、跨会话持久化
- 格式：自定义的 Message ORM 模型
- 用途：前端渲染历史对话、数据分析、记忆提取

**数据流**：用户消息 → 转换为 GraphState.messages → 工作流执行 → 子 Agent 回复 → 写入 messages 表（持久化）+ 更新 GraphState.messages（运行时）

两者是**双写**关系，LangGraph 的 checkpoint 是性能优化（避免每次从数据库加载全部历史），messages 表是数据权威来源。

---

## Q20: 如果让你将动态规划从单机扩展到分布式（多个工作节点），你会怎么设计架构？

**参考答复：**

分布式动态规划的架构设计：

1. **消息队列解耦**：将 Orchestrator 拆分为 Planner（规划服务）和 Executor（执行服务），通过消息队列（如 RabbitMQ/Redis）通信
2. **任务分发**：Planner 生成计划后，将子任务发布到队列，多个 Worker 消费并执行
3. **状态共享**：GraphState 从本地内存迁移到 Redis（分布式缓存），所有 Worker 共享状态视图
4. **Checkpointer 升级**：AsyncSqliteSaver 替换为基于 PostgreSQL 的 checkpointer（支持多实例访问）
5. **WebSocket 广播**：使用 Redis Pub/Sub 做跨实例的 WebSocket 消息广播
6. **Agent 注册中心**：Agent 注册表从内存字典迁移到 Redis/etcd（多实例共享）

核心挑战：
- 分布式下的事务一致性（如子任务的依赖等待）
- 节点间的时间同步和消息顺序
- 网络分区时的容错处理

对于当前规模（单机），这些不是必需的。但如果需要支持大量并发用户或需要 GPU 节点独立运行本地模型，分布式架构就很有价值。
