# AI 决策规范

> **📎 何时读此文件**: 添加判断逻辑时、引入新规则/阈值时、发现已有硬编码时、任务描述模糊需要澄清时
> **对应原则**: DEV-03（大模型判断优先）、AI-05（必须先问再动手）
> **相关文件**: `spec/tech-stack.md`, `../AgentHub-records/decisions/`

## 核心原则

> **能让大模型判断自然语言逻辑的，不得加入写死逻辑。如果必须存在，必须标记并记录。**

---

## 禁止行为

❌ **字符串关键字判断**：
```python
# 错误：写死逻辑
if "生成PDF" in user_input:
    generate_pdf()

# 错误：正则匹配
if re.search(r"pdf|报告|文档", user_input):
    generate_pdf()
```

❌ **硬编码规则**：
```python
# 错误：硬编码判断
if user_id == 1:
    is_admin = True

# 错误：硬编码阈值
if len(text) > 500:
    is_complex = True
```

❌ **魔法数字**：
```python
# 错误：魔法数字
if timeout > 30:  # 为什么是 30？
    abort()
```

---

## 正确做法

✅ **让模型判断**：
```python
# 正确：让 LLM 判断
response = await llm.chat([
    {"role": "system", "content": "判断用户是否需要生成 PDF。只回答 yes/no。"},
    {"role": "user", "content": user_input}
])
need_pdf = response.strip().lower() == "yes"
```

✅ **配置化**：
```yaml
# config.yaml
pdf_generation:
  trigger_keywords: ["pdf", "报告", "文档"]
  max_content_length: 5000
  timeout: 60
```

✅ **数据驱动**：
```python
# 从配置读取
config = load_config()
if user_input in config.pdf_generation.trigger_keywords:
    generate_pdf()
```

---

## 过渡期处理

如果写死逻辑因为早期验证效果而存在：

1. **标记为临时**：
   ```python
   # TODO: [TEMP] 早期验证方案，待废弃
   # 废弃日期: 2026-06-20
   # 替代方案: 使用 LLM 判断
   if "pdf" in user_input:
       generate_pdf()
   ```

2. **写入文档**：
   - 创建 `deprecated/early-validation.md`
   - 说明原因、替代方案、废弃日期

3. **定期检查**：
   - 在 `todo.md` 中创建任务
   - 到期后必须替换

---

## 澄清问题

当任务描述模糊或涉及新业务概念时，AI 必须先列出 3-5 个澄清问题：

**示例**：

用户："帮我做个报表功能"

AI 澄清问题：
1. 报表的数据源是什么？数据库、API、还是用户上传？
2. 报表格式是什么？PDF、Excel、网页表格？
3. 报表是实时生成还是定时生成？
4. 用户如何触发报表生成？按钮点击、定时任务、还是 API 调用？
5. 报表需要支持哪些筛选条件？

---

## 决策记录

重大决策必须记录到 `decisions/`：

```markdown
# 决策: 使用 LLM 判断 vs 写死逻辑

**日期**: 2026-06-10
**决策**: 优先使用 LLM 判断
**原因**: 
- 写死逻辑难以维护
- 用户需求多变，关键字匹配不准确
- LLM 可以理解语义

**例外情况**:
- 性能要求极高（>1000 QPS）
- 延迟要求极低（<50ms）
- 明确需要确定性行为

**废弃日期**: 不适用
```

---

## 检查清单

新增判断逻辑时：

- [ ] 能否让 LLM 判断？
- [ ] 是否有配置化方案？
- [ ] 是否有数据驱动方案？
- [ ] 是否标记了临时方案？
- [ ] 是否记录了废弃日期？
- [ ] 是否更新了文档？

---

> ⚠️ **重要**：写死逻辑是技术债务的主要来源。宁可让 AI 判断，也不要硬编码。
