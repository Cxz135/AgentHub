"""
单元测试：Orchestrator._parse_artifacts

从 Agent 输出文本中提取 ``` 代码块，按语言分类为 artifact。
不需要 DB / API / Orchestrator 初始化。
"""

import pytest
from backend.core.orchestrator import Orchestrator

parse = staticmethod(Orchestrator._parse_artifacts).__func__


def test_empty_text():
    assert parse("") == []


def test_no_code_blocks():
    assert parse("纯文本，没有代码块") == []


def test_single_python_block():
    text = "这是一段 Python 代码：\n```python\nprint('hello')\n```\n结束"
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["type"] == "code"
    assert arts[0]["language"] == "python"
    assert arts[0]["title"] == "PYTHON"
    assert "print('hello')" in arts[0]["content"]


def test_html_block():
    text = "```html\n<div>Hello</div>\n```"
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["type"] == "html_preview"
    assert arts[0]["language"] == "html"


def test_mermaid_block():
    text = "```mermaid\ngraph TD\nA-->B\n```"
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["type"] == "diagram"
    assert arts[0]["language"] == "mermaid"


def test_graphviz_block():
    text = "```graphviz\ndigraph { a -> b }\n```"
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["type"] == "diagram"
    assert arts[0]["language"] == "graphviz"


def test_markdown_block():
    text = "```markdown\n# Title\nHello\n```"
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["type"] == "markdown"


def test_md_short_block():
    text = "```md\n# Title\n```"
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["type"] == "markdown"


def test_no_language_defaults_to_text():
    text = "```\nraw code\n```"
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["language"] == "text"
    assert arts[0]["type"] == "code"


def test_multiple_blocks():
    text = "```python\nx=1\n```\n中间文本\n```javascript\nconsole.log('hi')\n```"
    arts = parse(text)
    assert len(arts) == 2
    assert arts[0]["language"] == "python"
    assert arts[1]["language"] == "javascript"
    assert arts[0]["type"] == "code"
    assert arts[1]["type"] == "code"


def test_mixed_types():
    text = "```python\nx=1\n```\n```html\n<p>Hi</p>\n```"
    arts = parse(text)
    assert len(arts) == 2
    assert arts[0]["type"] == "code"
    assert arts[1]["type"] == "html_preview"


def test_inline_code_not_extracted():
    """单反引号 `code` 不应被提取为 artifact"""
    text = "用 `print(1)` 调用"
    assert parse(text) == []


def test_preserves_content_whitespace():
    text = "```python\n  def foo():\n    pass\n  \n```"
    arts = parse(text)
    assert "  def foo():" in arts[0]["content"]
    assert "    pass" in arts[0]["content"]


def test_language_with_trailing_whitespace():
    text = "```python  \nprint(1)\n```"
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["language"] == "python"


def test_text_unchanged():
    """原始 text 参数不应被修改（无副作用）"""
    text = "前文\n```python\ncode\n```\n后文"
    original = text[:]
    parse(text)
    assert text == original


def test_code_with_special_chars():
    text = "```bash\ncurl -X POST 'http://example.com' | jq .\n```"
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["type"] == "code"
    assert arts[0]["language"] == "bash"


def test_empty_code_block():
    text = "```python\n```"
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["content"] == ""


def test_code_block_at_start():
    text = "```python\nprint(1)\n```\n后面有文字"
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["language"] == "python"


def test_code_block_at_end():
    text = "前面有文字\n```python\nprint(1)\n```"
    arts = parse(text)
    assert len(arts) == 1


def test_multiline_code():
    text = "```javascript\nfunction add(a, b) {\n  return a + b;\n}\n```"
    arts = parse(text)
    assert len(arts) == 1
    assert "function add" in arts[0]["content"]
    assert "return a + b" in arts[0]["content"]


def test_json_block():
    text = '```json\n{"key": "value"}\n```'
    arts = parse(text)
    assert len(arts) == 1
    assert arts[0]["type"] == "code"
    assert arts[0]["language"] == "json"


def test_no_false_positive_triple_backtick_in_text():
    """文本中的 ````` 不是合法的代码块格式，不应匹配"""
    text = "this is not a ````` code block"
    assert parse(text) == []


def test_shebang_code_block():
    text = ("#!/usr/bin/env python3\n"
            "#-*- coding: utf-8 -*-\n"
            '"""\nSimple Thread-Safe HTTP Proxy Server\n"""\n'
            "_cache = {}\n"
            "def _is_cache_expired(timestamp: float) -> bool:\n"
            "    return time.time() - timestamp > CACHE_TTL")
    arts = parse(text)
    assert len(arts) >= 1
    code_arts = [a for a in arts if a["type"] == "code"]
    assert len(code_arts) >= 1
    assert "#!/usr/bin/env python3" in code_arts[0]["content"]


def test_decorator_code_block():
    """装饰器风格的代码应被检测为代码"""
    text = """@app.route('/')
def index():
    return "hello"

@staticmethod
def helper(): pass"""
    arts = parse(text)
    code_arts = [a for a in arts if a["type"] == "code"]
    assert len(code_arts) >= 1
    assert "@app.route" in code_arts[0]["content"] or "@app.route" in str(arts)
