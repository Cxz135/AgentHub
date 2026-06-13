# 面试准备：LLM 后端层

---

## Q0: 请简单介绍一下 AgentHub 的 LLM 后端层

**参考答复：**

AgentHub 的 LLM 后端层是一个 **统一抽象、多提供商** 的 LLM 接入层，解决了"一个项目需要对接多个 AI 模型提供商"的工程问题。

**核心抽象**：
- `LLMBackend`（抽象基类）：定义 `chat()` 和 `chat_stream()` 两个统一接口
- `BaseLLM`（底层）：提供 `invoke()` 方法，处理更底层的调用

**三个后端实现**：
1. `TongyiBackend` — 对接阿里云 DashScope（Qwen 系列），默认后端
2. `DeepSeekBackend` — 对接 DeepSeek API（DeepSeek-Chat/Coder）
3. `OpenCodeBackend` — 对接 OpenCode Zen（7 款免费模型路由）

**统一接口设计**：
- `chat(messages) → str`：非流式调用，返回完整回复
- `chat_stream(messages) → AsyncGenerator[str]`：流式调用，逐 token 返回

所有后端使用 `httpx.AsyncClient` 做异步 HTTP 调用，遵循 OpenAI-compatible 的消息格式。

---

## Q1: 为什么需要一个统一的 LLMBackend 抽象层？直接调 API 不行吗？

**参考答复：**

统一抽象层的价值在多个维度：

**1. 解耦 Agent 和 LLM 提供商**：Agent 不需要知道后端是 DeepSeek 还是 Tongyi，只需要调用 `backend.chat(messages)`。切换 LLM 提供商不需要改 Agent 代码。

**2. 统一容错处理**：所有后端的重试、超时、错误处理在统一层实现，不需要每个 Agent 各自处理。

**3. 健康检查统一**：启动时的健康检查对所有后端一视同仁，不健康的后端自动移除。

**4. 流式/非流式统一**：chat() 和 chat_stream() 两个接口覆盖所有场景，上层不需要区分。

**5. 多后端共存**：同一个系统中可以同时使用多个 LLM 提供商，不同 Agent 用不同后端，这是 AgentHub 多 Agent 协作的基础。

**直接调 API 的问题**：代码中会散布各种 API 调用的细节（不同的 base_url、不同的 auth header、不同的错误处理），Agent 和 LLM 提供商耦合在一起，切换或新增提供商成本很高。

---

## Q2: 三个后端（Tongyi、DeepSeek、OpenCode）的 API 有什么差异？抽象层如何处理这些差异？

**参考答复：**

虽然三个后端都声称 OpenAI-compatible，但实际有差异：

**API 差异**：
- Base URL 不同：`https://dashscope.aliyuncs.com/...` vs `https://api.deepseek.com/...` vs OpenCode 的 URL
- 模型名称不同：`qwen-plus` vs `deepseek-chat` vs `big-pickle`
- API Key 不同：各自独立的环境变量
- 速率限制不同：各平台限制策略不同
- OpenCode 是免费路由（内部再做分发），有额外的路由逻辑

**抽象层的处理方式**：
- 每个 Backend 类持有自己的 `base_url`、`api_key`、`model_name`
- Backend 构造函数从环境变量读取配置，内部封装差异
- `chat()` 和 `chat_stream()` 接口签名完全一致，差异封装在内部
- 通过 `get_backend(name)` 工厂方法按名称获取后端，名称屏蔽了具体实现

这个设计体现了**策略模式**：每个 Backend 是一个策略，Orchestrator 通过统一的接口调用不同的策略。

---

## Q3: 健康检查（health check）是怎么实现的？为什么要在启动时做？

**参考答复：**

健康检查在 `_health_check_backends()` 中实现：

```python
for name, backend in list(self.llm_backends.items()):
    url = backend.base_url + '/chat/completions'
    payload = {"model": backend.model_name,
               "messages": [{"role": "user", "content": "ping"}],
               "max_tokens": 5}
    with httpx.Client(timeout=8) as client:
        resp = client.post(url, headers={...}, json=payload)
        ok = resp.status_code == 200
    if ok:
        backend._healthy = True
    else:
        del self.llm_backends[name]  # 移除不健康后端
```

**设计考量**：
1. **同步执行**：使用 `httpx.Client` 而非 `AsyncClient`，确保在初始化阶段完成（后续依赖检查结果）
2. **最小化消耗**：`max_tokens=5`，ping 级别的最小调用
3. **超时控制**：8 秒超时，避免启动卡死
4. **自动移除**：不健康的后端直接从注册表中删除，后续路由中不可见

**为什么在启动时做**：避免运行时才发现 LLM 不可用。如果用户等了 30 秒的复杂规划流程，最后因为后端挂了返回错误，体验很差。启动时 fail-fast 更好。

---

## Q4: httpx.AsyncClient 在项目中的使用方式是什么？连接池是如何管理的？

**参考答复：**

项目中使用 httpx 做异步 HTTP 调用：

**Backend 层使用方式**：
- 每个 Backend 实例内部创建 `httpx.AsyncClient`（或在需要时创建）
- 设置超时：`httpx.Timeout(connect=10, read=60, write=10, pool=10)`
- 设置 headers：Authorization（Bearer token）、Content-Type

**连接池管理**：
- 当前实现中，每个 Backend 可能在每次调用时创建新的 AsyncClient（取决于具体实现）
- 理想情况下应该使用单例 AsyncClient 并复用连接池

**异步调用示例**：
```python
async with httpx.AsyncClient(timeout=...) as client:
    response = await client.post(url, json=payload, headers=headers)
    # 处理流式响应
    async for line in response.aiter_lines():
        ...
```

使用 `aiter_lines()` 处理 SSE 流式响应，配合 async generator 逐 token yield。

---

## Q5: chat() 和 chat_stream() 的实现有什么区别？流式输出是如何实现的？

**参考答复：**

**chat()（非流式）**：
```python
async def chat(self, messages) -> str:
    response = await client.post(url, json={
        "messages": messages,
        "model": self.model_name,
        "stream": False,
    })
    data = response.json()
    return data["choices"][0]["message"]["content"]
```

**chat_stream()（流式）**：
```python
async def chat_stream(self, messages) -> AsyncGenerator[str, None]:
    async with client.stream("POST", url, json={
        "messages": messages,
        "model": self.model_name,
        "stream": True,
    }) as response:
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data["choices"][0].get("delta", {}).get("content"):
                    yield data["choices"][0]["delta"]["content"]
```

**核心区别**：
- chat() 等完整响应，一次性返回
- chat_stream() 通过 async generator 逐 token yield
- 流式使用 `stream=True` + `response.aiter_lines()` 处理 SSE
- 流式需要自己解析 SSE 格式（`data: ` 前缀 + JSON）

---

## Q6: OpenCodeBackend 的免费模型路由是怎么工作的？和付费后端有什么区别？

**参考答复：**

OpenCode Zen 是一个免费的 LLM 路由服务，内部接入多款免费模型：

**DEFAULT_MODEL**：`deepseek-v4-flash-free`

**7 款免费模型白名单**：包括 Big Pickle、MiMo v2.5、Qwen3.6 Plus、MiniMax M3、Nemotron 等

**工作原理**：
- OpenCode Zen 作为反向代理，接收 OpenAI-compatible 请求
- 根据请求中的 model 参数路由到对应的免费后端
- 对客户端透明——客户端只看到 OpenCode 的 URL

**与付费后端的区别**：
1. **稳定性**：免费服务不保证 SLA，可能随时限流或不可用
2. **速率限制**：比付费 API 更严格的 rate limit
3. **模型选择**：只能用白名单中的免费模型
4. **Fallback 链更长**：OpenCode Agent 的 fallback 链包含两个付费后端（tongyi + deepseek）

OpenCode 在项目中的定位是**零成本选项**，适合 demo 和轻量使用。

---

## Q7: 如果后端返回非 200 状态码，如何处理？

**参考答复：**

错误处理在 Backend 层实现：

1. **HTTP 错误**：检查 `response.status_code`，非 200 → 记录错误日志 + 返回错误消息
2. **网络错误**：httpx 的 `ConnectError`、`TimeoutException` 等 → try/except 捕获
3. **JSON 解析错误**：API 返回非 JSON 响应 → try/except `json.JSONDecodeError`
4. **API 业务错误**：API 返回 200 但内容中有错误信息 → 检查 choices 是否为空

**统一错误返回**：
```python
try:
    response = await client.post(...)
    response.raise_for_status()  # 非 200 抛异常
    data = response.json()
    return data["choices"][0]["message"]["content"]
except httpx.HTTPStatusError as e:
    logger.error(f"API 返回错误: {e.response.status_code}")
    return f"API 调用失败: HTTP {e.response.status_code}"
except Exception as e:
    logger.error(f"LLM 调用异常: {e}")
    return f"处理请求时出错: {e}"
```

错误消息以字符串形式返回给上层（而非抛异常），上层 Agent 可以将错误消息作为回复返回给用户或触发 fallback。

---

## Q8: 项目中如何管理不同模型的 token 限制和上下文窗口？

**参考答复：**

Token 管理的几个层面：

1. **配置级**：`DEFAULT_MAX_TOKENS = 8192`，在 `config.py` 中定义，作为默认值
2. **模型级**：每个 Backend 知道自己的模型上下文窗口大小（如 Qwen-Long 支持更长上下文）
3. **策略级**：记忆策略（sliding_window/summary）在消息发送前裁剪，确保不超过上下文窗口
4. **运行时**：`DEFAULT_SUMMARY_THRESHOLD = 4000`，当消息 token 超过此值时触发摘要压缩

当前没有实现精确的 token 计数（如 tiktoken），裁剪策略基于消息数量（sliding_window 保留 N 轮）或字符数估算。精确的 token 计数是后续优化方向。

---

## Q9: 如果用户想接入一个新的 LLM 提供商（如 OpenAI），需要做什么？

**参考答复：**

接入新提供商的步骤：

1. **创建 Backend 类**：在 `backend/llm/backends/` 下新建文件，继承 `LLMBackend`，实现 `chat()` 和 `chat_stream()` 方法
2. **配置环境变量**：在 `.env` 中添加新提供商的 API Key 和 Base URL
3. **注册后端**：在 Orchestrator 的 `_setup_backends()` 中添加注册代码：
   ```python
   openai = OpenAIBackend(model="gpt-4o")
   self.llm_backends["openai"] = openai
   ```
4. **可选：创建 Adapter**：如果需要特殊的调用逻辑
5. **可选：注册 Agent**：在 `custom_agents.yaml` 中添加使用新后端的 Agent

整个过程只需要新增代码，不需要修改现有 Backend 代码——这就是抽象层的好处。

---

## Q10: LLM 调用的重试机制是怎样的？重试策略如何设计？

**参考答复：**

重试在多个层面实现：

**Backend 层重试**：
- 网络超时、临时服务不可用（503）→ 自动重试
- 使用指数退避（exponential backoff）
- 最多重试 2-3 次

**Agent 层重试**：
- validation 失败 → 将失败原因反馈给 LLM → 重新生成
- 通过 `max_retries` 配置（默认 2 次）

**Fallback 重试**：
- 主后端失败 → 尝试 fallback 链中的其他后端

**重试设计原则**：
- 只重试可恢复的错误（网络超时、503），不重试不可恢复的错误（401 认证失败、400 参数错误）
- 重试有上限，避免无限重试
- 每次重试记录日志，便于问题排查

---

## Q11: temperature 参数在项目中是如何使用的？不同场景用不同的 temperature 吗？

**参考答复：**

Temperature 配置：

- **默认值**：`DEFAULT_TEMPERATURE = 0.7`（在 `config.py` 中）
- **使用场景**：
  - 创意性 Agent（如 product_manager、opencode_bigpickle）→ 较高 temperature（0.7-0.9），鼓励多样性
  - 精确性 Agent（如 code_reviewer、PlannerAgent）→ 较低 temperature（0.1-0.3），保证输出一致性
  - 事实性回答 → temperature=0，最确定性

当前项目中，temperature 在 Backend 层是可配置参数，但不同 Agent 还没有独立设置 temperature 的能力。这是一个可以增强的方向——将 temperature 加入 Agent 的 A-Tier 配置中。

---

## Q12: OpenCode Zen 的 7 个免费模型分别适合什么场景？

**参考答复：**

OpenCode Zen 路由的免费模型及其适用场景：

1. **deepseek-v4-flash-free**（默认）：通用编程和对话，速度快，适合日常编码
2. **big-pickle**：实验性模型，回答简短有趣，适合 demo 和趣味场景
3. **MiMo v2.5**：适合代码生成和补全
4. **Qwen3.6 Plus**：中文优化，适合中文对话和内容生成
5. **MiniMax M3**：多模态能力（如果平台支持）
6. **Nemotron**：英文优化，适合技术文档和代码

选择原则：中文场景优先用 Qwen3.6 Plus，编码场景优先用 DeepSeek/MiMo，Demo 场景用 Big Pickle。

---

## Q13: 后端层的 API Key 是如何管理和轮换的？

**参考答复：**

API Key 管理：

**存储**：通过环境变量（`.env` 文件）注入，每个后端读取自己的环境变量：
- `DASHSCOPE_API_KEY` → Tongyi
- `DEEPSEEK_API_KEY` → DeepSeek
- `OPENCODE_API_KEY` → OpenCode

**安全措施**：
- `.env` 加入 `.gitignore`，不提交版本控制
- 日志输出时使用 `mask_api_key()` 脱敏
- Pydantic Settings 提供类型安全的读取

**当前限制**：不支持多 Key 轮换和自动切换。如果 API Key 额度耗尽，需要手动更换 `.env` 中的 Key 并重启服务。

---

## Q14: 流式输出的 token 拼接有哪些注意事项？如何处理不完整的 Unicode 字符？

**参考答复：**

流式 token 拼接的挑战：

1. **不完整字符**：SSE 流中的 token 可能在一个多字节字符（如中文 UTF-8 编码）的中间被截断 → 导致乱码
2. **增量拼接**：每个 delta token 需要拼接到前面的内容中

**处理方式**：
- 使用字符串拼接（Python 3 原生 Unicode 支持）
- 如果遇到解码错误，暂时缓存不完整的字节，等待下一个 chunk 拼接完成
- 在最终输出前做一次完整的 Unicode 规范化

在项目中，流式 token 通过 `content += delta_content` 在 Consumer 端拼接。由于 Python 3 的字符串是 Unicode 原生支持的，大部分情况下不会出现编码问题。但如果 API 返回的是字节级流，需要注意 UTF-8 多字节字符的边界处理。

---

## Q15: 后端层有没有做请求级别的超时控制？怎么设置？

**参考答复：**

超时控制通过 httpx 的 Timeout 配置：

```python
httpx.Timeout(
    connect=10.0,   # 建立 TCP 连接的超时
    read=60.0,      # 读取响应的超时（流式场景下重要）
    write=10.0,     # 发送请求的超时
    pool=10.0,      # 从连接池获取连接的超时
)
```

**为什么 read 超时设得较长**：流式输出场景下，token 是一个一个返回的，如果 read 超时太短，长时间的生成会被中断。60 秒足够容许许多模型的长响应。

**健康检查专用超时**：启动时的 ping 使用 8 秒超时（`LLM_HEALTH_CHECK_TIMEOUT`），比正常超时短很多——ping 只需要几毫秒。

---

## Q16: 后端层如何区分不同类型的 API 错误并给出有意义的错误消息？

**参考答复：**

错误分类和处理：

| 错误类型 | HTTP 状态码 | 处理方式 |
|---------|------------|---------|
| 认证失败 | 401 | 不重试，提示检查 API Key |
| 权限不足 | 403 | 不重试，提示检查账号权限 |
| 资源不存在 | 404 | 不重试，提示检查模型名称 |
| 请求超限 | 429 | 指数退避重试 |
| 服务端错误 | 500/502/503 | 指数退避重试 |
| 网络超时 | N/A | 重试，超时后 fallback |

**错误消息格式**：包含错误类型 + HTTP 状态码 + 后端名称，便于排查：
```
API 调用失败 (tongyi): HTTP 429 - 请求过于频繁，请稍后重试
```

---

## Q17: 项目的 LLM 调用有没有做 prompt 级别的缓存？（如相同 prompt 不重复调用）

**参考答复：**

当前项目没有实现 prompt 级别的缓存。每一个请求都会调用 LLM API。

**可以实现缓存的场景**：
- 系统 prompt 相同的请求
- 完全相同的用户问题（FAQ 场景）
- 复杂度分类的 prompt（结构固定，只有 user_message 变化）

**缓存的实现方案**：
- 使用 `@lru_cache` 装饰器缓存系统 prompt 的响应
- 使用内容哈希做精确匹配缓存（如同一个用户问题短时间内重复问）
- Redis 做分布式缓存

**当前不做缓存的原因**：对话场景下大部分请求都是不同的（用户每次问的问题不同），缓存命中率可能不高。但复杂度分类是一个很好的缓存切入点——同一个用户消息的复杂度分类结果可以缓存。

---

## Q18: 如果要在后端层加一个请求日志（记录每次 LLM 调用的延迟和 token 消耗），怎么设计？

**参考答复：**

请求日志的设计方案：

1. **中间件/装饰器**：在 `LLMBackend` 基类的 `chat()` 方法上加一个 logging wrapper
2. **记录内容**：
   - timestamp（请求时间）
   - backend_name（哪个后端）
   - model_name（哪个模型）
   - latency_ms（调用延迟）
   - input_tokens（输入 token 数，从 API 响应中获取）
   - output_tokens（输出 token 数）
   - status（成功/失败/fallback）
   - error_message（如果失败）
3. **存储**：写入专门的 `llm_call_logs` 表或日志文件
4. **用途**：
   - 成本分析（每个模型的花费）
   - 性能监控（哪个后端延迟最高）
   - 故障排查（哪类错误最多）
   - 用量统计（每天的调用量趋势）

当前项目中没有这个功能，但日志系统（structured logging）已经有了基础设施，扩展相对容易。

---

## Q19: 后端层的测试是怎么做的？如何 mock LLM 调用？

**参考答复：**

LLM 调用的测试策略：

1. **Mock Backend**：在测试中创建一个 mock 的 `LLMBackend`，`chat()` 方法返回预定义的响应
   ```python
   class MockBackend(LLMBackend):
       async def chat(self, messages):
           return "这是一个测试回复"
   ```

2. **Mock httpx**：使用 `pytest-httpx` 或 `unittest.mock` mock 底层 HTTP 调用，控制返回的状态码和内容

3. **集成测试**：在需要真实 LLM 调用的测试中，使用环境变量控制是否实际调用（如设置 `TEST_MODE=true` 跳过 LLM 调用）

4. **Snapshot 测试**：对 prompt 模板做 snapshot 测试，确保 prompt 修改是可预期的

测试的核心难点是 LLM 的非确定性——同样的 prompt 可能返回不同的结果。因此单元测试主要 mock LLM，集成测试关注 prompt 结构和路由逻辑。

---

## Q20: 如果要支持本地模型（如通过 Ollama 接入 Llama），后端层需要做什么改变？

**参考答复：**

接入 Ollama 本地模型的设计：

1. **创建 OllamaBackend**：继承 `LLMBackend`，对接 Ollama 的 API（OpenAI-compatible）
   ```python
   class OllamaBackend(LLMBackend):
       def __init__(self, model="llama3.2", base_url="http://localhost:11434/v1"):
           self.base_url = base_url
           self.model_name = model
   ```

2. **环境变量配置**：`OLLAMA_BASE_URL=http://localhost:11434/v1`、`OLLAMA_MODEL=llama3.2`

3. **健康检查调整**：本地模型的健康检查需要检查 Ollama 服务是否在运行（而非外网连接）

4. **功能差异处理**：
   - 本地模型可能不支持某些功能（如 function calling）
   - 本地模型可能不支持流式输出
   - 需要在 Backend 中做能力声明

5. **资源管理**：本地模型需要考虑内存/显存占用，可能需要增加模型加载/卸载的管理逻辑

架构上，由于 `LLMBackend` 抽象层的存在，新增 OllamaBackend 不需要修改任何现有代码——只需要新建一个类并在 `_setup_backends()` 中注册。
