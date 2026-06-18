# 踩坑日志

## 速查索引

> 按问题类型分组，方便 AI 在遇到相似场景时快速定位。

| 类型 | 条目 | 关键词 |
|------|------|--------|
| **字符编码** | [Emoji 过滤正则误删中文](#2026-06-10-emoji-过滤正则误删中文) | Unicode, 正则, 中文乱码 |
| **字符编码** | [fpdf2 中文乱码](#2026-06-10-fpdf2-中文乱码) | fpdf2, reportlab, 字体, ttc |
| **路由配置** | [FastAPI 挂载顺序导致 404](#2026-06-10-fastapi-挂载顺序导致-404) | mount, StaticFiles, 路由优先级 |
| **Agent 行为** | [Agent 不调用 to_pdf 工具](#2026-06-10-agent-不调用-to_pdf-工具) | tool calling, 后处理, fallback |
| **前后端协议** | [artType 键名不匹配](#2026-06-10-前端-arttype-键名不匹配) | camelCase, snake_case, 字段命名 |
| **正则表达式** | [_parse_artifacts 正则终结符缺失](#2026-06-10-_parse_artifacts-正则终结符缺失) | regex, 括号, 转义字符 |

---

## 2026-06-10: Emoji 过滤正则误删中文

**问题**: PDF 中文内容全部丢失

**现象**: 
- 生成 PDF 后下载，内容中只有英文和数字
- 中文内容（如"小米"、"营收"）全部消失

**原因**: 
```python
emoji_pattern = re.compile('[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF\U0000FE00-\U0000FE0F]+')
```

正则范围 `\U000024C2-\U0001F251` 包含了中文字符 `\U00004E00-\U00009FFF`。

**解决方案**: 删除 Emoji 过滤代码，使用 reportlab 的 Arial Unicode.ttf 字体支持所有字符。

**教训**: 
- Unicode 范围检查必须仔细，特别是大范围正则
- 正则表达式测试时必须包含中文用例
- 报告生成工具应优先使用 reportlab 而非 fpdf2

**相关文件**: `backend/utils/file_converter.py`

---

## 2026-06-10: FastAPI 挂载顺序导致 404

**问题**: PDF 文件下载返回 404

**现象**: 
- 后端日志显示 PDF 生成成功
- 文件存在于 `data/attachments/0/xxx.pdf`
- 但访问 `/attachments/0/xxx.pdf` 返回 404

**原因**: `main.py` 中 `app.mount("/", ...)`（前端）在 `app.mount("/attachments", ...)`（附件）之前注册，导致所有以 `/attachments` 开头的请求被前端 StaticFiles 截获。

**解决方案**: 将 `/attachments` 挂载移到 `/` 之前。

**教训**: 
- FastAPI 的 mount 顺序决定路由优先级
- 静态文件挂载应该按从具体到一般的顺序
- 先挂载 API 和附件，再挂载前端

**相关文件**: `backend/app/main.py`

---

## 2026-06-10: Agent 不调用 to_pdf 工具

**问题**: Agent 没有调用 `file_converter.to_pdf`，直接编造了不存在的文件路径

**现象**: 
- Agent 输出显示 "PDF 已保存到 /tmp/xxx.md"
- 但文件不存在
- 日志显示 `❌ [AGENT] Agent 没有调用任何工具（直接回答）`

**原因**: 
- ReAct Prompt 中虽然要求 Agent 调用工具，但 Agent 仍然直接回答
- Agent 可能觉得直接回答更简单，或者没有正确理解工具用途
- `to_pdf` 的 docstring 不够明确，Agent 没有意识到可以直接传入内容

**解决方案**: 
- 新增 `_auto_generate_pdf` 后处理，自动检测 Agent 输出中的 PDF 请求并生成 PDF
- 强化 ReAct Prompt 规则，明确告诉 Agent 必须调用工具
- 修改 `to_pdf` 的 docstring，使用标准格式（Args/Returns）

**教训**: 
- AI 不一定会按照指示调用工具，需要后处理兜底
- 后处理比前处理更可靠（前处理依赖 AI 理解，后处理是确定性逻辑）
- 关键功能必须有降级方案（自动调用 vs Agent 主动调用）

**相关文件**: `backend/core/orchestrator.py`, `backend/utils/file_converter.py`

---

## 2026-06-10: fpdf2 中文乱码

**问题**: PDF 中文显示为乱码

**现象**: 
- 使用 fpdf2 生成 PDF 后，中文显示为乱码
- 日志显示 `Font MPDFAA+HiraginoSansGBW3 is missing the following glyphs`

**原因**: 
- fpdf2 的 `uni=True` 模式（虽然已弃用）使用字体子集，但 `.ttc` 字体文件处理有问题
- 去掉 `uni=True` 后中文直接丢失

**解决方案**: 使用 reportlab 替代 fpdf2，Arial Unicode.ttf 支持中文。

**教训**: 
- fpdf2 对中文支持不佳，特别是 `.ttc` 字体
- 报告生成应优先使用 reportlab（商业级，支持中文好）
- 字体选择很重要：Arial Unicode.ttf 是 .ttf 格式，reportlab 支持好

**相关文件**: `backend/utils/file_converter.py`

---

## 2026-06-10: 前端 artType 键名不匹配

**问题**: 产物面板显示为代码块而非文件卡片

**现象**: 
- 后端发送了 file 类型的 artifact
- 但前端显示为代码块（直接显示路径文本）
- 产物面板不显示下载按钮

**原因**: 
- 后端发送 `artType`（camelCase）
- 前端 `chat_interactions.js` 检查 `d.art_type`（snake_case）
- 由于 `d.art_type` 是 `undefined`，`artType` 被错误设为 `"artifact"`（消息类型）

**解决方案**: 
- 后端改为发送 `artType`
- 前端同时检查 `d.artType` 和 `d.art_type`

**教训**: 
- 前后端字段命名必须统一
- 检查多个可能的键名（兼容性）
- 添加调试日志确认收到的数据结构

**相关文件**: `backend/app/api/websocket.py`, `AgentHub-my flicker/js/chat_interactions.js`

---

## 2026-06-10: _parse_artifacts 正则终结符缺失

**问题**: Agent 输出中包含 `/attachments/0/xxx.pdf`，但 `_parse_artifacts` 没有提取到

**现象**: 
- Agent 输出了 markdown 链接 `[xxx](/attachments/0/xxx.pdf)`
- 但 `_parse_artifacts` 没有检测到文件路径

**原因**: 正则终结符列表只有中文全角括号 `（）`，没有 ASCII 括号 `()`。

**解决方案**: 在终结符列表中添加 `()`。

**教训**: 
- 正则表达式必须考虑所有可能的字符
- ASCII 和中文标点都要考虑
- 测试正则时要用实际数据

**相关文件**: `backend/core/orchestrator.py`

---

> 💡 **提示**：每次解决难缠问题，都应记录到本文档。AI 遇到相似场景时先检索。
