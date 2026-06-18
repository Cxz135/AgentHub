# 前后端接口协议

> **📎 何时读此文件**: 修改 API 时、新增接口时、前后端联调异常时、新功能开发前
> **对应原则**: PRJ-02（先打通 API，再写页面）、AI-02（禁止只改一端）

## 接口清单

项目启动前，所有接口必须满足以下条件：
- ✅ 接口文档已定义
- ✅ 后端已实现
- ✅ 已用 curl 验证通过
- ✅ 前端已对接

---

## 接口列表

### 1. 认证相关

| 接口 | 方法 | 路径 | 状态 |
|------|------|------|------|
| 注册 | POST | `/api/register` | [ ] |
| 登录 | POST | `/api/login` | [ ] |
| 获取当前用户 | GET | `/api/me` | [ ] |

### 2. 资源管理

| 接口 | 方法 | 路径 | 状态 |
|------|------|------|------|
| 列表 | GET | `/api/resources` | [ ] |
| 创建 | POST | `/api/resources` | [ ] |
| 详情 | GET | `/api/resources/{id}` | [ ] |
| 更新 | PUT | `/api/resources/{id}` | [ ] |
| 删除 | DELETE | `/api/resources/{id}` | [ ] |

### 3. 文件上传

| 接口 | 方法 | 路径 | 状态 |
|------|------|------|------|
| 上传文件 | POST | `/api/upload` | [ ] |
| 下载文件 | GET | `/api/attachments/{uid}/{filename}` | [ ] |

### 4. WebSocket

| 接口 | 路径 | 状态 |
|------|------|------|
| 实时通信 | `/ws/{id}` | [ ] |

#### WebSocket 消息格式

> **重要**：WebSocket 是双向通信，消息格式必须前后端严格一致。这是 `rules/api-consistency.md` 在 WS 场景下的应用。

##### 客户端 → 服务端 (C→S)

| 消息类型 | `type` 字段 | 必填字段 | 可选字段 | 说明 |
|----------|------------|----------|----------|------|
| 用户消息 | `user_message` | `content` | `attachments`, `context` | 用户发送的对话消息 |
| 心跳 | `ping` | — | — | 保持连接活跃 |
| 取消生成 | `cancel` | — | `task_id` | 中断当前 AI 生成 |

**消息示例**：
```json
// 用户消息
{
  "type": "user_message",
  "content": "帮我生成一份小米的营收报告",
  "attachments": [],
  "context": {"mode": "research"}
}

// 心跳
{"type": "ping"}

// 取消
{"type": "cancel", "task_id": "abc-123"}
```

##### 服务端 → 客户端 (S→C)

| 消息类型 | `type` 字段 | 必填字段 | 说明 |
|----------|------------|----------|------|
| 流式 Token | `token` | `content`, `idx` | 逐字/逐 token 推送 |
| 工具调用开始 | `tool_start` | `tool_name`, `args` | Agent 开始调用工具 |
| 工具调用结果 | `tool_result` | `tool_name`, `result` | 工具调用完成 |
| 产物通知 | `artifact` | `artType`, `url`, `filename` | 生成文件（PDF/图片/代码） |
| 对话完成 | `done` | `usage`, `duration_ms` | 当前对话结束 |
| 错误 | `error` | `code`, `message` | 处理出错 |
| 心跳响应 | `pong` | — | 心跳回复 |

**消息示例**：
```json
// 流式 Token
{"type": "token", "content": "小", "idx": 0, "model": "claude"}

// 工具调用开始
{"type": "tool_start", "tool_name": "to_pdf", "args": {"content": "# 报告\n..."}}

// 工具调用结果
{"type": "tool_result", "tool_name": "to_pdf", "result": "/attachments/0/report.pdf"}

// 产物通知（注意：字段名使用 camelCase，与 REST API 保持一致）
{"type": "artifact", "artType": "file", "url": "/attachments/0/report.pdf", "filename": "report.pdf"}

// 对话完成
{"type": "done", "usage": {"input_tokens": 500, "output_tokens": 300}, "duration_ms": 3200}

// 错误
{"type": "error", "code": "RATE_LIMIT", "message": "请求过于频繁，请稍后重试"}

// 心跳响应
{"type": "pong"}
```

##### 字段命名约定

| 层 | 命名风格 | 示例 |
|----|---------|------|
| WebSocket `type` 字段 | snake_case | `user_message`, `tool_start`, `tool_result` |
| 数据字段 | camelCase | `artType`, `taskId`, `durationMs` |
| REST API 字段 | camelCase | 与数据字段保持一致 |

> ⚠️ **常见坑**：WS 消息的 `type` 使用 snake_case，但消息内部的业务字段使用 camelCase。前后端必须统一。参见 `AgentHub-records/gotcha.md` 中的 artType 键名不匹配问题。

---

## 接口验证命令

### 示例：验证注册接口

```bash
# 注册
curl -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}'

# 预期返回
# {"id": 1, "username": "test", "token": "..."}
```

### 示例：验证文件上传

```bash
# 上传
curl -X POST http://localhost:8000/api/upload \
  -H "Authorization: Bearer TOKEN" \
  -F "file=@test.pdf"

# 预期返回
# {"filename": "xxx.pdf", "url": "/attachments/0/xxx.pdf"}
```

### 示例：验证 WebSocket

```bash
# 使用 wscat 测试
wscat -c "ws://localhost:8000/ws/123"

# 发送消息
> {"type": "message", "content": "hello"}

# 预期返回
< {"type": "token", "content": "..."}
```

---

## 接口变更规范

任何接口变更必须遵循以下流程：

1. **更新文档**：先修改本文档，标记变更状态
2. **后端实现**：更新后端接口
3. **验证通过**：用 curl 验证新接口
4. **前端对接**：更新前端 API 调用
5. **联调测试**：前后端联合测试

**禁止**：只改前端或只改后端，导致接口不一致。

---

## 字段一致性

前后端字段必须完全一致：

- 字段名：使用 camelCase 或 snake_case，前后端统一
- 数据类型：必须匹配，不得前端传 string 后端收 int
- 空值处理：明确 null / undefined / "" 的语义
- 错误码：统一错误码，不得各自定义

---

## 变更日志

| 日期 | 变更接口 | 变更内容 | 影响 |
|------|----------|----------|------|
| [日期] | [接口] | [内容] | [影响范围] |

---

> ⚠️ **重要**：接口未经验证不得进入下一阶段开发。
