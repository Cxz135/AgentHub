# 知识管理规范

> **📎 何时读此文件**: 会话开始时（了解记录体系）、会话结束时（确保记录完整）、新增记录时（了解格式规范）
> **对应原则**: KNW-01~KNW-04（知识管理全部原则）

## 核心原则

> **AI 会遗忘，文档不会。所有关键决策、待办事项、废弃方案必须持久化。**

---

## 文档体系

```
AI协作开发-- shallow/
├── readme.md              # 总纲
├── todo.md                # 当前待办
├── gotcha.md              # 踩坑日志
├── deprecated/            # 废弃方案
│   ├── old-auth.md
│   ├── old-pdf-method.md
│   └── ...
├── decisions/             # 决策记录
│   ├── 2026-06-10-pdf-generation.md
│   └── ...
└── lessons/               # 经验教训
    ├── emoji-filter-bug.md
    └── ...
```

---

## 待办事项 (todo.md)

### 格式

```markdown
# 待办事项

## 高优先级

- [ ] 修复 PDF 中文乱码问题
  - 状态: 进行中
  - 负责人: AI
  - 截止日期: 2026-06-11
  - 阻塞: 无
  - 备注: 已定位到 Emoji 过滤正则问题

## 中优先级

- [ ] 优化产物面板渲染
  - 状态: 待开始
  - 负责人: AI
  - 截止日期: 2026-06-12
  - 阻塞: 待 PDF 修复完成后

## 低优先级

- [ ] 添加用户反馈功能
  - 状态: 待讨论
  - 负责人: 待定
  - 截止日期: 未确定
  - 阻塞: 需求不明确

## 已完成

- [x] 修复 to_pdf 文件名过长
  - 完成日期: 2026-06-10
  - 备注: 已修改正则匹配
```

### 规则

- 与 AI 讨论出多个待办但只能展开一个时，其余写入 `todo.md`
- 每次会话开始时，AI 必须先读取 `todo.md`
- 任务完成后更新状态
- 过期任务重新评估

---

## 踩坑日志 (gotcha.md)

### 格式

```markdown
# 踩坑日志

## 2026-06-10: Emoji 过滤正则误删中文

**问题**: PDF 中文内容全部丢失

**原因**: Emoji 过滤正则 `[\U000024C2-\U0001F251]` 包含了中文字符 `\U00004E00-\U00009FFF`

**解决方案**: 删除 Emoji 过滤，使用 reportlab 的 Arial Unicode 字体支持

**教训**: 
- Unicode 范围检查必须仔细
- 正则表达式测试时要包含中文用例
- 报告生成工具应优先使用 reportlab

**相关文件**: `backend/utils/file_converter.py`

---

## 2026-06-10: FastAPI 挂载顺序导致 404

**问题**: PDF 文件下载返回 404

**原因**: `app.mount("/", ...)` 在前，`app.mount("/attachments", ...)` 在后，前端截获了附件请求

**解决方案**: 将 `/attachments` 挂载移到 `/` 之前

**教训**: 
- FastAPI 的 mount 顺序决定路由优先级
- 静态文件挂载应该按从具体到一般的顺序

**相关文件**: `backend/app/main.py`
```

### 规则

- 每次解决难缠问题，要求 AI 总结成一条记录
- 包含：问题、原因、解决方案、教训、相关文件
- AI 遇到相似场景时，先检索 `gotcha.md`

---

## 废弃方案 (deprecated/)

### 格式

```markdown
# 废弃方案: 使用 fpdf2 生成 PDF

**废弃日期**: 2026-06-10

**废弃原因**: 
- fpdf2 对中文支持不佳（需要 uni=True 但已弃用）
- 使用 .ttc 字体时子集问题导致乱码
- 报告已替换为 reportlab

**替代方案**: reportlab + Arial Unicode.ttf

**历史代码**: 
```python
# 旧代码（已废弃）
from fpdf import FPDF
pdf = FPDF()
pdf.add_font('Hiragino', fname='/System/Library/Fonts/Hiragino Sans GB.ttc', uni=True)
```

**注意事项**: 
- 如果未来 fpdf2 修复了 Unicode 支持，可以重新评估
- 当前项目优先使用 reportlab

**相关文件**: 
- `backend/utils/file_converter.py`（已删除 fpdf2 优先逻辑）
```

### 规则

- 已废弃的方法或思路必须写入 `deprecated/`
- 包含：废弃原因、替代方案、历史代码、注意事项
- AI 新会话开始时读取 `deprecated/`
- 避免 AI 遗忘后倒退到旧方案

---

## 决策记录 (decisions/)

### 格式

```markdown
# 决策: 使用 reportlab 作为 PDF 生成首选

**日期**: 2026-06-10
**状态**: 已采纳
**决策人**: AI + 用户

## 背景

项目需要生成中文 PDF 文件。尝试了 fpdf2、weasyprint、reportlab 三种方案。

## 考虑的方案

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| fpdf2 | 轻量、纯 Python | 中文支持差、ttc 字体问题 | ❌ 废弃 |
| weasyprint | 支持 HTML/CSS | 依赖系统库、macOS 中文字体问题 | ⚠️ 降级 |
| reportlab | 中文支持好、稳定 | 稍重 | ✅ 首选 |

## 决策

使用 reportlab 作为 PDF 生成首选方案，Arial Unicode.ttf 作为字体。

## 影响

- `backend/utils/file_converter.py` 已修改
- 需要安装 `reportlab` 依赖

## 后续

- 监控 reportlab 的性能和稳定性
- 如果未来需要更复杂的排版，可以重新评估 weasyprint
```

---

## 使用流程

1. **会话开始**：
   - AI 读取 `todo.md` 了解当前任务
   - AI 读取 `deprecated/` 了解废弃方案
   - AI 读取 `gotcha.md` 了解踩坑记录

2. **开发过程中**：
   - 遇到新坑 → 记录到 `gotcha.md`
   - 产生新待办 → 记录到 `todo.md`
   - 废弃旧方案 → 记录到 `deprecated/`
   - 做重大决策 → 记录到 `decisions/`

3. **会话结束**：
   - AI 更新 `todo.md` 状态
   - AI 总结本次会话的踩坑记录
   - AI 记录未完成的事项

---

> 💡 **提示**：知识管理是 AI 协作的基石。没有文档，AI 每次会话都会遗忘。
