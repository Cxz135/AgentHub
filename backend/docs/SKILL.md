# AgentHub Skill 规范

## 概述

本文档定义了 AgentHub 中 Skill（技能）的标准格式、调用方式和注册流程。所有 Skill 必须遵循此规范，以确保 Orchestrator 能够正确识别和调用。

---

## Skill 分类

### 1. 工具类 Skill（Tool Skill）

**定义**：可执行的 Python 函数，通过 LangChain Tool 封装，支持 ReAct 循环中的 `Action/Action Input` 调用。

**注册方式**：在 `Orchestrator._register_builtin_tool_skills()` 中注册到 `self.tool_skills` 字典。

**调用格式**：
```
Thought: 需要查询深圳当前的天气情况
Action: web_search
Action Input: 深圳天气 2026年6月9日
```

**返回格式**：函数返回字符串，Orchestrator 将结果作为 `Observation` 反馈给 LLM。

**示例**：`backend/utils/web_search.py` 中的 `web_search` 函数。

---

### 2. 能力类 Skill（Native Skill）

**定义**：纯自然语言的技能描述，以 Markdown 文件存储，通过 prompt 拼装调用。

**注册方式**：在 `Orchestrator._load_native_skills()` 中从 `backend/skills/*.md` 加载到 `self.native_skills` 字典。

**调用格式**：
```
Thought: 需要生成一个聊天标题
Action: gen_chat_title
Action Input: 用户想要创建一个关于Python项目的新对话
```

**实现原理**：Orchestrator 检测到 `Action: gen_chat_title` 后，调用 `call_skill()` 方法，该方法将 `input_content` 与 `native_skills["gen_chat_title"]` 的内容拼装成 prompt，发送给 LLM 生成结果。

**示例**：`backend/skills/gen_chat_title.md`。

---

## 标准调用流程

### LLM 输出阶段

LLM 根据 prompt 判断需要调用工具，输出标准格式：

```
Thought: <思考过程，描述为什么需要调用工具>
Action: <工具名称，如 web_search、gen_chat_title>
Action Input: <工具输入参数>
```

### Orchestrator 解析阶段

1. `AgentExecutor` 解析 LLM 输出，提取 `Action` 和 `Action Input`
2. 根据 `Action` 名称查找对应工具
3. 执行工具并获取返回结果

### 结果反馈阶段

1. 工具执行结果作为 `Observation` 返回给 LLM
2. LLM 根据 Observation 继续推理或输出最终答案

---

## 工具类 Skill 开发规范

### 函数签名

```python
def skill_function(input_content: str) -> str:
    """
    工具说明

    Args:
        input_content: 工具输入参数

    Returns:
        工具执行结果的文本描述
    """
    # 实现逻辑
    return result
```

### 注册到 Orchestrator

在 `Orchestrator._register_builtin_tool_skills()` 中：

```python
def _register_builtin_tool_skills(self):
    # 单个函数
    from backend.utils.web_search import web_search
    self.tool_skills["web_search"] = web_search

    # 工具组（多个方法）
    file_converter = importlib.import_module('backend.utils.file_converter')
    for func_name in getattr(file_converter, '__all__', []):
        if func_name != "FileConversionError":
            self.tool_skills[f"file_converter.{func_name}"] = getattr(file_converter, func_name)
```

### LangChain Tool 封装

所有 `tool_skills` 中的函数会自动封装为 LangChain Tool：

```python
from langchain.tools import tool

for skill_key, skill_func in self.tool_skills.items():
    wrapped_tool = tool(skill_func)
    wrapped_tool.name = skill_key  # 必须与 skill_key 一致
    self.langchain_tools.append(wrapped_tool)
```

---

## 能力类 Skill 开发规范

### Markdown 文件格式

```markdown
---
name: skill_name
description: 技能描述，用于 Orchestrator 生成工具列表
tags: [标签1, 标签2]
---

# 技能名称

## 功能描述
详细说明技能的功能和使用场景

## 调用格式
标准 ReAct 格式：
```
Thought: ...
Action: skill_name
Action Input: <参数>
```

## 使用示例
### 示例1
输入：xxx
预期输出：xxx

## 注意事项
- 注意点1
- 注意点2
```

### 文件命名

- 文件名：`backend/skills/<skill_name>.md`
- `<skill_name>` 必须与 `name` 元数据一致
- 使用下划线或驼峰命名，避免特殊字符

---

## ReAct Prompt 配置

在 `backend/config/prompts/orchestrator_prompts.yaml` 中配置：

```yaml
react_agent:
  description: "ReAct Agent prompt - 工具调用"
  prompt: |
    你是一个专家助手，可以调用工具来完成任务。

    可用工具：
    {tools}

    工具列表：{tool_names}

    【输出格式】你必须严格按以下格式输出，只输出这三行，不要输出任何其他内容：

    Thought: 你需要做什么
    Action: 工具名称
    Action Input: 搜索关键词

    等待工具执行完成后，你会收到工具的返回结果（Observation），然后你再继续。

    【关键规则】
    1. 天气、新闻等实时信息必须调用 web_search
    2. 每次只输出 Thought、Action、Action Input 三行，然后等待
    3. Action Input 直接写搜索关键词，例如：深圳天气 或 深圳天气预报
    4. 收到 Observation 后，根据结果继续回答或再调用工具
    5. 完成后输出 Final Answer: 你的回答

    开始回答：
    问题：{input}
    {agent_scratchpad}
```

---

## Skill 调用错误处理

### 工具不存在

当 LLM 输出 `Action: unknown_tool` 时：

```python
if action not in self.tool_skills and action not in [t.name for t in self.langchain_tools]:
    return f"Observation: 错误：工具 '{action}' 不存在。可用工具：{list(self.tool_skills.keys())}"
```

### 工具执行失败

```python
try:
    result = self.tool_skills[action](action_input)
except Exception as e:
    logger.error(f"工具 {action} 执行失败: {e}")
    return f"Observation: 工具执行失败：{str(e)}"
```

### 工具返回空结果

```python
if not result:
    return f"Observation: 工具返回空结果，请检查输入参数或稍后重试"
```

---

## 禁用格式（历史兼容）

以下格式已被废弃，仅用于历史兼容，不再推荐使用：

```
【调用Skill: xxx，输入内容: xxx】
【调用Skill: xxx，方法: xxx，输入内容: xxx】
```

Orchestrator 不再解析这些格式，所有 Skill 调用必须通过 ReAct 的 `Action/Action Input` 格式。

---

## 示例：完整调用流程

### 用户输入
"深圳今天天气怎么样？"

### LLM 输出
```
Thought: 用户询问深圳天气，这是实时信息，需要调用 web_search 工具查询。
Action: web_search
Action Input: 深圳天气 2026年6月9日
```

### Orchestrator 处理

1. 解析 `Action: web_search`
2. 查找工具 `web_search` → 存在
3. 执行 `web_search("深圳天气 2026年6月9日")`
4. 获取结果：`"🔍 搜索结果（深圳天气 2026年6月9日）：深圳今日天气：晴，温度26-32°C..."`

### 反馈给 LLM
```
Observation: 🔍 搜索结果（深圳天气 2026年6月9日）：深圳今日天气：晴，温度26-32°C...
```

### LLM 最终回答
```
Final Answer: 深圳今天的天气是晴天，气温26-32°C，适合户外活动。
```