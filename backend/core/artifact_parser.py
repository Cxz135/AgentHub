"""
Artifact 解析器。

从 Agent 输出文本中提取结构化 artifact（代码块、markdown、文件路径），
并提供 SSE 队列推送的通用函数。

从 orchestrator 解耦，独立可测试。
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("core")


def parse_artifacts(text: str) -> list[dict]:
    """
    从 Agent 输出中提取代码块和 markdown 内容作为 artifact。

    1. 匹配 ```lang\\n...``` 标准代码围栏
    2. 检测裸 markdown（标题、列表、分隔线等）
    3. 检测无围栏的代码块（连续缩进行）

    Returns:
        list[dict]，每个 dict 包含 type/title/content/language。
    """
    artifacts = []

    # 1. 标准代码围栏
    fenced_pattern = r'```(\w*)\s*\n(.*?)```'
    for match in re.finditer(fenced_pattern, text, re.DOTALL):
        lang = match.group(1).strip() or 'text'
        code = match.group(2)
        art_type = 'html_preview' if lang in ('html',) else \
                   'diagram' if lang in ('mermaid', 'graphviz') else \
                   'markdown' if lang in ('markdown', 'md') else \
                   'code'
        artifacts.append({
            "type": art_type,
            "title": lang.upper() if lang != 'text' else '代码',
            "content": code,
            "language": lang,
        })
    # 从文本中移除已匹配的围栏，防止二次解析
    text = re.sub(fenced_pattern, '', text, flags=re.DOTALL)

    # 2. 检测裸 markdown（标题、列表、分隔线、引用等）
    lines = text.split('\n')
    in_bare_md = False
    md_lines = []
    consecutive_non_code = 0
    _code_start_added = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        is_md = (
            stripped.startswith('# ') or
            stripped.startswith('## ') or
            stripped.startswith('### ') or
            stripped.startswith('- ') or
            stripped.startswith('* ') or
            re.match(r'^\d+\. ', stripped) or
            stripped.startswith('> ') or
            stripped.startswith('---') or
            stripped.startswith('| ')
        )
        is_code_indented = (
            (line.startswith('    ') or line.startswith('\t')) and
            stripped and
            not stripped.startswith('-') and
            not stripped.startswith('*') and
            not stripped.startswith('#')
        )
        code_indicators = [
            stripped.startswith('#!'),
            stripped.startswith('@'),
            stripped.startswith('def '),
            stripped.startswith('class '),
            stripped.startswith('async def '),
            stripped.startswith('import '),
            stripped.startswith('from '),
            stripped.startswith('if __name__'),
            '"""' in stripped or "'''" in stripped,
            stripped.startswith('# -*-'),
            stripped.startswith('# coding:'),
        ]
        is_code_indicator = any(code_indicators)
        is_code_line = is_code_indented or (
            is_code_indicator and
            not stripped.startswith('# ') and
            not stripped.startswith('## ') and
            not stripped.startswith('### ') and
            not stripped.startswith('#!')
        )

        _line_added_this_iter = False
        if is_code_indicator and not in_bare_md:
            in_bare_md = True
            md_lines = [stripped] if stripped else []
            _line_added_this_iter = True

        if is_md or is_code_line:
            if not in_bare_md:
                in_bare_md = True
                md_lines = [stripped] if stripped else []
            elif not _line_added_this_iter:
                md_lines.append(stripped)
            consecutive_non_code = 0
        else:
            if in_bare_md and not _line_added_this_iter:
                md_lines.append(stripped)
            consecutive_non_code += 1
            if in_bare_md and len(md_lines) >= 3 and consecutive_non_code >= 4:
                content = '\n'.join(md_lines)
                is_markdown = any(
                    md_lines[j].startswith(('# ', '## ', '### ', '- ', '* ', '> ', '---', '| '))
                    for j in range(min(3, len(md_lines)))
                )
                artifacts.append({
                    "type": 'markdown' if is_markdown else 'code',
                    "title": 'Markdown' if is_markdown else '代码',
                    "content": content,
                    "language": 'markdown' if is_markdown else 'text',
                })
                in_bare_md = False
                md_lines = []
                consecutive_non_code = 0

    # 处理末尾
    if in_bare_md and len(md_lines) >= 3:
        content = '\n'.join(md_lines)
        is_markdown = any(
            md_lines[j].startswith(('# ', '## ', '### ', '- ', '* ', '> ', '---', '| '))
            for j in range(min(3, len(md_lines)))
        )
        artifacts.append({
            "type": 'markdown' if is_markdown else 'code',
            "title": 'Markdown' if is_markdown else '代码',
            "content": content,
            "language": 'markdown' if is_markdown else 'text',
        })

    return artifacts


def push_artifacts_to_queue(artifacts: list[dict], queue, agent_id: str) -> None:
    """
    将 artifact 列表推送到 SSE 渐进式队列。

    每个 artifact 以独立事件推送，供前端逐个渲染。
    """
    if queue is None:
        return
    for art in artifacts:
        try:
            queue.put_nowait({
                "agent_id": agent_id,
                "type": art.get("type", "code"),
                "title": art.get("title", "代码"),
                "content": art.get("content", ""),
                "artifacts": [art],
            })
        except Exception as e:
            logger.warning(f"[ArtifactParser] 推送 artifact 到队列失败: {e}")
