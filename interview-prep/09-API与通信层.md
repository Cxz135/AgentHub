# 面试准备：API 与通信层

---

## Q0: 请简单介绍一下 AgentHub 的 API 与通信层

**参考答复：**

AgentHub 的 API 层基于 FastAPI 框架，提供 **三通道通信**：

**1. REST API**（HTTP）：
- `/api/chat` — 核心聊天接口（POST 同步 + SSE 流式）
- `/api/missions` — 会话 CRUD
- `/api/agents` — Agent 管理（CRUD + prompt 优化）
- `/api/skills` — Skill 市场（发布、安装、删除）
- `/api/knowledge` — RAG 知识库管理（上传、搜索、删除）
- `/api/memory` — 记忆管理（查询、删除、画像、统计）
- `/api/auth` — 用户认证（注册、登录、JWT）

**2. WebSocket**（全双工实时通信）：
- `ws/{conversation_id}` — 实时流式聊天
- 支持 token-by-token 打字机效果
- 支持 thinking 状态指示
- 支持 artifact 推送
- 支持 intermediate 进度消息

**3. SSE**（HTTP 流式降级）：
- 当 WebSocket 不可用时自动降级
- 通过 `StreamingResponse` + async generator 实现

**安全机制**：JWT 鉴权（pyjose + bcrypt）、CORS 中间件、密码哈希（passlib）

---

## Q1: 为什么同时支持 WebSocket、SSE 和 HTTP POST 三种通信方式？

**参考答复：**

三种通信方式服务于不同场景：

**WebSocket**（首选）：
- 全双工：服务端可以主动推送（如 Agent 执行进度、状态变化）
- 低延迟：一次握手，持续通信
- 适用：实时对话、复杂任务执行监控
- 不足：部分代理/CDN 不支持

**SSE（Server-Sent Events）**（降级方案）：
- 服务端 → 客户端单向流式推送
- 基于 HTTP，兼容性好（所有浏览器、所有代理/CDN 都支持）
- 适用：WebSocket 不可用时的流式输出降级
- 不足：单向通信，客户端发消息需要额外的 HTTP 请求

**HTTP POST**（基础方案）：
- 最简单的请求-响应模式
- 适用：非流式场景、API 集成测试、第三方调用
- 不足：无法实现流式打字机效果

三种方式共存的设计是**渐进增强**理念：最优体验用 WebSocket，不可用时降级到 SSE，最基础场景用 HTTP POST。

---

## Q2: WebSocket 的鉴权是怎么做的？和 HTTP API 的鉴权有什么不同？

**参考答复：**

WebSocket 鉴权在连接建立时完成：

```python
@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    # 从 query params 获取 token
    token = websocket.query_params.get("token")
    # 验证 JWT token
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    user_id = payload.get("sub")
    # 验证通过 → 接受连接
    await websocket.accept()
    # 验证失败 → 拒绝连接
    await websocket.close(code=1008)
```

**和 HTTP API 鉴权的区别**：
- HTTP：token 放在 `Authorization: Bearer xxx` header 中
- WebSocket：token 放在 URL query params 中（`ws://host/ws/conv_id?token=xxx`）
- WebSocket 握手时只能携带 URL 参数，没有 header（浏览器 WebSocket API 不支持自定义 header）

**安全考量**：
- WebSocket token 在 URL 中，可能被日志记录
- 建议 WebSocket 连接建立后立即做 token 验证，避免未认证连接消耗资源
- token 应该有合理的过期时间

---

## Q3: SSE 流式输出是如何实现的？和 WebSocket 流的实现有什么技术差异？

**参考答复：**

SSE 实现：

```python
@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    async def event_generator():
        async for event in orchestrator.get_chat_stream(...):
            if event["type"] == "token":
                yield f"data: {json.dumps(event)}\n\n"
            # ...
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        }
    )
```

**SSE vs WebSocket 流的技术差异**：
| 维度 | SSE | WebSocket |
|------|-----|-----------|
| 方向 | 单向（服务端→客户端） | 双向 |
| 协议 | HTTP | WebSocket 独立协议 |
| 自动重连 | 浏览器原生支持 | 需手动实现 |
| 消息格式 | `data: xxx\n\n` | 自定义（JSON） |
| 二进制数据 | 不支持（仅文本） | 支持 |
| 代理兼容 | 好（就是 HTTP） | 部分代理需要配置 |

项目中 SSE 的 token 发送模拟了打字机效果：`TOKEN_CHUNK_SIZE=8` 字符每块 + `TOKEN_DELAY_MS=15ms` 延迟。

---

## Q4: progressive_queue 在流式输出中是怎么工作的？

**参考答复：**

`progressive_queue` 是流式输出的核心数据通道：

**完整数据流**：

```
Orchestrator.get_chat_response()
    │
    ├─ 路由决策完成 → queue.put({"type": "thinking", "status": "done"})
    │
    ├─ Agent 开始生成 → queue.put({"type": "token_event", "token": "..."})
    │                    queue.put({"type": "token_event", "token": "..."})  # 逐 token
    │
    ├─ 子 Agent 执行中 → queue.put({"type": "intermediate", "agent_id": "...", ...})
    │
    ├─ Artifact 产出 → queue.put({"type": "artifact", ...})
    │
    └─ 最终完成 → 返回完整结果

get_chat_stream() [消费者]
    │
    ├─ while main_task 未完成:
    │   ├─ queue.get_nowait() → yield event
    │   └─ await asyncio.sleep(0)  # 让出控制权
    │
    └─ 汇总 final response + intermediate_messages + artifacts
```

**关键设计**：
- **非阻塞消费**：`get_nowait()` 而非 `get()`（不阻塞等待）
- **事件驱动**：每种事件类型有独立的处理逻辑
- **独立队列**：每个请求一个 queue，并发请求不相互干扰

---

## Q5: 聊天 API 的 agent_override 参数是做什么的？

**参考答复：**

`agent_override` 是前端实现"静默 @mention"的机制：

**场景**：用户在前端切换了 Agent（如从默认 Agent 切换到 code_reviewer），然后发送消息。正常情况下用户需要手动输入 `@code_reviewer`。

**agent_override 的实现**：
```python
if agent_override and messages:
    override_id = agent_override.get("id") or agent_override.get("agent_id")
    if override_id:
        last = messages[-1]
        # 只在用户没有显式 @mention 时注入
        if last.get("role") == "user" and "@" not in (last.get("content") or ""):
            new_content = f"@{override_id} {last.get('content', '')}".strip()
            messages = list(messages[:-1]) + [{"role": "user", "content": new_content}]
```

**效果**：前端在消息中自动加上 `@agent_id` 前缀，后端路由到指定 Agent。用户看到的是自己输入的消息，不知道背后加了 @mention。

**安全考量**：只在没有显式 @mention 时才注入，避免覆盖用户明确指定的 Agent（用户手动 @ 的优先级更高）。

---

## Q6: JWT 鉴权的完整流程是怎样的？

**参考答复：**

JWT 鉴权的完整流程：

**注册**：
1. 用户提交 username + email + password
2. 密码通过 bcrypt（passlib）哈希
3. 存储到 users 表

**登录**：
1. 用户提交 username + password
2. 验证密码哈希
3. 生成 JWT token（payload: sub=user_id, exp=过期时间）
4. 返回 token 给客户端

**鉴权**（每次请求）：
```python
async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    return user
```

**WebSocket 鉴权**：从 URL query params 提取 token → 同样的 JWT 验证逻辑。

**技术选型**：python-jose（JWT 编解码）+ passlib[bcrypt]（密码哈希）

---

## Q7: API 路由的组织结构是怎样的？如何避免路由冲突？

**参考答复：**

路由在 `app/main.py` 中集中注册：

```python
app = FastAPI()

# 各模块路由
app.include_router(conversations.router, prefix="/api/missions")
app.include_router(messages.router, prefix="/api")
app.include_router(agents.router, prefix="/api/agents")
app.include_router(chat.router, prefix="/api/chat")
app.include_router(auth.router, prefix="/api")
app.include_router(skills.router, prefix="/api/skills")
app.include_router(knowledge.router, prefix="/api/knowledge")
app.include_router(memory.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(artifacts_api.router, prefix="/api")
```

**避免冲突的策略**：
- 每个模块使用独立的 `APIRouter` 实例
- 通过 prefix 做命名空间隔离
- 有些路由共用一个 prefix（如 `/api`），但通过不同的 path 区分
- FastAPI 的路由匹配是"先注册先匹配"，需要注意注册顺序

**改进建议**：统一加 `/api/v1` 版本前缀，方便未来引入 API 版本管理。

---

## Q8: CORS 是如何配置的？为什么需要 CORS？

**参考答复：**

CORS（跨域资源共享）配置在 FastAPI 应用中：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 开发环境允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**为什么需要 CORS**：
前端和后端可能部署在不同域名/端口下（如前端在 `localhost:3000`，后端在 `localhost:8000`），浏览器的同源策略会阻止跨域请求。CORS 中间件告诉浏览器"这些跨域请求是允许的"。

**安全考量**：
- `allow_origins=["*"]` 在开发环境方便，但在生产环境应该限制为具体域名
- `allow_credentials=True` 配合具体的 origins 使用时要注意安全

---

## Q9: request_context 在 API 中传递了哪些信息？

**参考答复：**

`request_context` 是一个贯穿整个请求处理流程的字典，包含：

```python
request_context = {
    # 用户身份
    "current_user_id": 1,
    "current_user_name": "henryjin",

    # Skill 相关
    "active_skills": ["web_search", "file_converter"],

    # 消息相关
    "pinned_messages": [...],

    # 记忆相关（由 augment_context 填充）
    "augmented_memories": [...],
    "user_profile": "...",
    "memory_summary": "...",
    "use_long_term_memory": False,

    # 其他
    "conversation_mode": "single",
}
```

**设计原因**：
- 路由需要不同的上下文信息（@mention 路由需要 user_id，Skill 注入需要 active_skills）
- 用字典而非多个独立参数，避免函数签名膨胀
- 可扩展：新增上下文字段不需要修改函数签名

**缺点**：类型不安全（字典的值无类型约束），IDE 无法做自动补全。

---

## Q10: 文件上传的 API 是如何实现的？文件存储在哪里？

**参考答复：**

文件上传由 Attachments API 处理：

```python
@router.post("/api/attachments/upload")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 验证文件大小和类型
    # 保存到 data/ 目录
    file_path = f"data/uploads/{file.filename}"
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    # 记录到数据库
    # 返回文件 URL
```

**存储位置**：
- 用户上传的文档 → `data/` 目录
- 文件 MD5 记录 → `data/md5_hex_store`
- 文档映射 → `data/doc_mapping.json`

**安全考量**：
- 需要限制文件大小
- 需要限制文件类型（白名单）
- 需要防止文件名冲突（添加时间戳或 UUID）
- 上传文件不应可执行

---

## Q11: API 的错误处理是如何统一管理的？

**参考答复：**

错误处理通过 FastAPI 的异常处理机制 + 自定义 handler：

**HTTP 异常**：
```python
@router.get("/api/...")
def endpoint(...):
    item = db.query(...).first()
    if not item:
        raise HTTPException(status_code=404, detail="资源不存在")
    return item
```

**全局异常处理**（可选，当前未实现）：
```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"}
    )
```

**LLM 调用异常**：
- 在后端层捕获，以字符串形式返回错误消息（而非抛异常）
- 上层 Agent 将错误消息作为回复展示给用户

**数据库异常**：
- SQLAlchemy 的异常在 session 操作时捕获
- 返回通用错误消息，详细信息记录日志

---

## Q12: 服务启动时的 lifespan handler 做了哪些初始化工作？

**参考答复：**

`lifespan` handler 在 `app/main.py` 中，管理 FastAPI 应用的启动和关闭：

**启动时（startup）**：
1. **数据库表创建**：`Base.metadata.create_all(bind=engine)`
2. **Schema 自动迁移**：检查缺失列 → ALTER TABLE 添加
3. **孤儿数据迁移**：将无主的会话/消息迁移到首个用户
4. **Skill 种子数据**：将系统 Skill 写入数据库（如果不存在）
5. **Orchestrator 初始化**：创建全局单例，加载所有 Agent/Workflow/Skill/LLM Backend

**关闭时（shutdown）**：
- 关闭数据库连接
- 清理资源

**为什么用 lifespan 而不是 `@app.on_event`**：lifespan 是 FastAPI 推荐的 async context manager 模式，更现代，支持 async 初始化。

---

## Q13: API 的请求和响应模型是如何定义的？使用了什么做数据校验？

**参考答复：**

使用 Pydantic 模型做请求/响应的数据校验：

```python
from pydantic import BaseModel

class ChatRequest(BaseModel):
    conversation_id: str
    messages: List[Dict[str, str]]
    request_context: Optional[Dict[str, Any]] = None
    agent_override: Optional[Dict[str, Any]] = None

class AgentCreate(BaseModel):
    name: str
    description: str
    system_prompt: str
    llm_adapter: str

class AgentResponse(BaseModel):
    agent_id: str
    content: str
    intermediate_messages: Optional[List[dict]] = None
    artifacts: Optional[List[dict]] = None
```

**Pydantic 的作用**：
- 自动校验请求参数类型和格式
- 自动生成 OpenAPI/Swagger 文档
- 提供清晰的 API 契约（前后端共享类型定义）
- 支持嵌套模型和可选字段

---

## Q14: WebSocket 的消息协议是怎样的？有哪些消息类型？

**参考答复：**

WebSocket 使用 JSON 格式的消息协议：

**客户端 → 服务端**：
```json
{
  "type": "chat",
  "conversation_id": "...",
  "messages": [...],
  "request_context": {...},
  "agent_override": {...}
}
```

**服务端 → 客户端**：
| 消息类型 | 结构 | 用途 |
|---------|------|------|
| `token` | `{"type": "token", "content": "..."}` | 打字机效果 |
| `thinking` | `{"type": "thinking", "agent_id": "...", "status": "thinking\|done"}` | 思考状态 |
| `intermediate` | `{"type": "intermediate", "agent_id": "...", "content": "..."}` | 子 Agent 进度 |
| `artifact` | `{"type": "artifact", "art_type": "code", "title": "...", "content": "..."}` | 产出物 |
| `final` | `{"type": "final", "content": "...", "intermediate_messages": [...]}` | 最终回答 |
| `error` | `{"type": "error", "message": "..."}` | 错误信息 |

**心跳机制**：WebSocket 连接维护心跳（ping/pong），检测连接是否存活。

---

## Q15: 流式 API 中的 token 发送速度是如何控制的？为什么需要控制？

**参考答复：**

Token 发送速度控制：

```python
# 在 SSE 降级中模拟打字机效果
TOKEN_CHUNK_SIZE = 8    # 每块 8 个字符
TOKEN_DELAY_MS = 15     # 每块间隔 15ms

# 实际实现
for i in range(0, len(content), TOKEN_CHUNK_SIZE):
    chunk = content[i:i + TOKEN_CHUNK_SIZE]
    yield {"type": "token", "content": chunk}
    await asyncio.sleep(TOKEN_DELAY_MS / 1000)
```

**WebSocket 流**：收到 LLM 的 token 后立即推送，不额外延迟（LLM 生成速度本身就是自然的打字机效果）

**SSE 降级**：由于 SSE 拿到了完整回复（非流式），需要人工分块模拟打字机效果

**为什么需要控制速度**：
- 用户体验：打字机效果让用户感觉"AI 在思考"，比一瞬间显示全部内容更有质感
- 防止前端渲染卡顿：一次性推送大量内容可能导致前端渲染阻塞

---

## Q16: 如果有大量并发 WebSocket 连接，服务端如何管理？

**参考答复：**

当前实现中，WebSocket 连接由 FastAPI + uvicorn 管理：

- 每个连接在独立的 async task 中处理
- FastAPI 的 async 模型天然支持大量并发连接（事件循环）
- 连接通过 `websocket.accept()` 建立，通过 `websocket.close()` 或断开被清理

**当前限制**：
- 没有连接池/连接管理器（无法全局查看活跃连接数）
- 没有跨实例的 WebSocket 广播（单实例内手动管理）

**改进方向**：
- 引入连接管理器（`ConnectionManager` 类）：追踪所有活跃连接，支持广播
- Redis Pub/Sub：多实例部署时通过 Redis 跨实例广播消息
- 连接数限制：限制单用户最大连接数，防止资源耗尽

---

## Q17: API 的版本管理策略是什么？如果要引入 v2 API 怎么做？

**参考答复：**

当前项目没有 API 版本管理（所有路由直接在 `/api/...` 下）。

如果引入 v2：

1. **URL 路径版本**（推荐）：
   ```python
   app.include_router(chat_v1.router, prefix="/api/v1/chat")
   app.include_router(chat_v2.router, prefix="/api/v2/chat")
   ```

2. **向后兼容**：v1 API 保留至少一个版本周期，标记为 deprecated

3. **版本差异管理**：
   - v1 → v2 的 breaking change 只在 v2 中引入
   - v1 可以内部转发到 v2 的实现（适配器模式）

4. **API 文档**：每个版本独立的 Swagger 文档

版本管理的关键原则：**永远不要让现有客户端突然不能用**。

---

## Q18: health check 端点返回什么信息？为什么需要它？

**参考答复：**

Health check 端点：

```python
@app.get("/api/health")
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "agents": len(orchestrator.agents),
        "backends": list(orchestrator.llm_backends.keys()),
        "skills": len(orchestrator.native_skills) + len(orchestrator.tool_skills),
    }
```

**用途**：
- **负载均衡器**：确认服务实例是否存活（用于流量分发）
- **监控系统**：定期探测，发现异常时告警
- **K8s liveness probe**：容器编排平台判断 Pod 是否健康
- **调试**：快速查看当前注册的 Agent 和后端状态

**好的 health check 应该**：
- 轻量（不需要复杂计算或外部调用）
- 返回有意义的服务状态信息
- 区分 liveness（服务是否活着）和 readiness（服务是否准备好接流量）

---

## Q19: API 的安全性方面有哪些考虑？如何防止常见攻击？

**参考答复：**

当前安全措施：

1. **JWT 鉴权**：所有 API 需要有效 token
2. **密码哈希**：bcrypt 哈希，不存储明文密码
3. **CORS 控制**：限制跨域访问
4. **输入校验**：Pydantic 校验请求参数类型和格式

**需要加强的方面**：
- **Rate Limiting**：当前没有，容易被滥用
- **Request Size Limit**：防止大 payload 攻击
- **SQL 注入防护**：使用参数化查询（SQLAlchemy ORM 自动处理，原始 SQL 用 text + 参数绑定）
- **XSS 防护**：前端输出时做 HTML 转义
- **CSRF**：前后端分离 + JWT 鉴权天然免疫 CSRF（不使用 cookie）

**生产环境建议**：
- 在 API Gateway（Nginx/Cloudflare）层加 rate limiting
- 添加 WAF（Web Application Firewall）
- 监控异常流量模式

---

## Q20: 如果要给第三方开发者开放 API，你需要考虑哪些问题？

**参考答复：**

开放 API 的考量：

1. **认证机制**：API Key 或 OAuth 2.0（比 JWT 更适合第三方集成）
2. **Rate Limiting**：按 API Key 或用户维度限流（如每分钟 60 次）
3. **API 版本管理**：保证向后兼容性
4. **文档**：自动生成 OpenAPI/Swagger 文档 + 手动编写使用指南
5. **SDK**：提供 Python/JS SDK 封装 API 调用
6. **计费**：如果需要收费，需要 API 用量统计和计费系统
7. **Webhook**：支持事件回调（如"Agent 回复完成时通知我的服务"）
8. **沙箱环境**：提供测试环境，不消耗生产额度
9. **错误码规范**：统一的错误码体系，方便集成方处理
10. **API 变更通知**：邮件/Webhook 通知 API 变更

第三方 API 的设计哲学和内部 API 不同：内部可以"约定大于配置"，外部需要"文档即契约"。
