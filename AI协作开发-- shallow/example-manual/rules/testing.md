# 测试规范

> **📎 何时读此文件**: 写/改测试时、代码修改超过 10 行时、提交 PR 前、测试失败时
> **对应原则**: DBG-04（禁止绕过测试）、AI-04（禁止为通过测试而降级）
> **相关文件**: `rules/definition-of-done.md`, `skill/code-generation.md`, `skill/code-review.md`

## 核心原则

> **任何非琐碎修改（超过 10 行代码或改动核心逻辑），必须先编写或更新对应的单元测试，并确保测试通过。**

---

## 测试覆盖率

| 类型 | 覆盖范围 | 必须 | 工具 |
|------|----------|------|------|
| 单元测试 | 函数/方法 | ✅ | pytest |
| 集成测试 | API 接口 | ✅ | pytest + httpx |
| 端到端测试 | 用户链路 | 可选 | Playwright |
| 性能测试 | 耗时/吞吐量 | 可选 | pytest-benchmark |

---

## 测试编写规范

### 单元测试

```python
# 正确示例
def test_to_pdf_with_content():
    """测试 to_pdf 直接传入内容"""
    content = "# 标题\n正文内容"
    result = to_pdf(content, user_id=0)
    
    assert result is not None
    assert result.startswith("/attachments/")
    assert result.endswith(".pdf")
    
    # 验证文件存在
    file_path = result.replace("/attachments/0/", "data/attachments/0/")
    assert os.path.exists(file_path)
    assert os.path.getsize(file_path) > 0

# 错误示例
def test_pdf():
    result = to_pdf("test")  # 没有断言
    print(result)  # 使用 print
```

### 集成测试

```python
# 正确示例
def test_upload_and_download():
    """测试上传后能够下载"""
    # 上传
    response = client.post("/api/upload", files={"file": ("test.pdf", b"content")})
    assert response.status_code == 200
    url = response.json()["url"]
    
    # 下载
    response = client.get(url)
    assert response.status_code == 200
    assert response.content == b"content"
```

---

## AI 生成测试的特殊要求

> AI 生成的测试存在系统性风险：「测试恰好通过但没有真正验证逻辑」。以下规则专门针对此问题。

### 反例验证规则

**每个 AI 生成的测试函数，必须经过反例验证**：

1. **故意错误验证**：在实现代码中临时引入一个错误（如反转条件、修改返回值），确认至少一个相关测试会失败
2. **空值验证**：确认测试在输入为 `None`/`[]`/`""` 时不会误判通过
3. **类型错误验证**：确认测试在输入类型错误时有合理表现（失败或跳过，而非静默通过）

```python
# ❌ 错误：AI 生成的"空壳"测试
def test_generate_pdf():
    """这个测试无论实现怎么改都会通过"""
    result = generate_pdf("# 标题")
    assert result is not None  # 永远为真！

# ✅ 正确：有意义的断言
def test_generate_pdf():
    """验证 PDF 生成的完整输出"""
    result = generate_pdf("# 标题\n正文内容", user_id=0)

    # 检查返回值格式
    assert result.startswith("/attachments/")
    assert result.endswith(".pdf")

    # 检查文件确实生成
    import os
    file_path = result.replace("/attachments/0/", "data/attachments/0/")
    assert os.path.exists(file_path), f"文件不存在: {file_path}"
    assert os.path.getsize(file_path) > 0, "文件为空"
```

### AI 测试禁止模式

| 禁止模式 | 示例 | 为什么危险 |
|----------|------|-----------|
| **万能通过断言** | `assert result is not None` | 只要不抛异常就通过 |
| **真值模糊断言** | `assert result` | None/0/"" 都能通过 |
| **类型仅断言** | `assert isinstance(result, str)` | 空字符串也通过 |
| **预测性断言** | `assert result == expected`（expected 是 AI 猜的） | AI 猜的 expected 可能本身就不对 |
| **无副作用验证** | 调了函数但不检查文件/DB/状态变化 | 函数可能什么都没做 |

### 测试自验证流程

AI 完成测试编写后，必须执行以下自验证：

```
🧪 测试自验证：

测试文件: test_file_converter.py
测试函数数: 5

反例验证:
- test_to_pdf_with_content: ✅ 故意修改返回值后测试失败（验证有效）
- test_to_pdf_empty_content: ✅ 输入空字符串时测试正确失败
- test_to_pdf_special_chars: ✅ 特殊字符测试有效
- test_to_pdf_file_exists: ✅ 文件不存在时测试失败
- test_to_pdf_large_content: ⚠️ 未验证文件内容正确性（需补充）

结论: 4/5 验证有效，1 个需补充
```

---

## 禁止行为

❌ **禁止修改测试断言**：
```python
# 错误：为了通过测试而修改断言
assert result == "expected"  # 改为 assert result is not None
```

❌ **禁止删除测试文件**：
```python
# 错误：删除失败的测试
# os.remove("test_failed.py")
```

❌ **禁止降低测试标准**：
```python
# 错误：降低覆盖率要求
# 从 80% 降到 50%
```

❌ **禁止绕过检查**：
```python
# 错误：跳过验证
if True:  # 原为 if validate(data):
    process(data)
```

---

## 失败处理流程

当测试失败时：

1. **记录失败**：
   - 测试名称
   - 预期结果
   - 实际结果
   - 差异分析

2. **分析原因**：
   - 是测试问题还是实现问题
   - 是环境问题还是逻辑问题
   - 是回归问题还是新 bug

3. **修复方案**：
   - 如果测试过时：更新测试
   - 如果实现 bug：修复实现
   - 如果环境差异：记录环境要求

4. **验证修复**：
   - 运行相关测试
   - 运行全部测试
   - 检查覆盖率

---

## 测试检查清单

提交代码前检查：

- [ ] 新增功能有对应的单元测试
- [ ] 修改的函数有对应的回归测试
- [ ] 所有测试通过
- [ ] 测试覆盖率不低于 80%（核心模块）
- [ ] 没有临时调试代码
- [ ] 测试不依赖外部服务（使用 mock）

---

## 测试数据

- 使用 `faker` 生成测试数据
- 测试数据独立于生产数据
- 敏感数据必须脱敏
- 测试后清理数据

---

## 持续集成

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests
        run: pytest --cov=backend --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

> ⚠️ **重要**：没有测试的代码是不允许合并的。AI 不得在测试未通过时声称"完成"。
