"""
InstructionMemory — 系统指令记忆

存储和检索系统级指令，按 scope 隔离：
- "global"          → 全局系统 prompt
- "agent:{id}"      → 特定 Agent 的 system prompt
- "project"         → 项目级规则
- "skill:{name}"    → 特定 Skill 的指令

后端：内存 dict + 可选 SQL 持久化。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from backend.memory.base import BaseMemory, MemoryEntry, MemoryConfig

logger = logging.getLogger("core")


class InstructionMemory(BaseMemory):
    """
    指令记忆，管理多层级的系统 prompt 片段。

    使用方式：
        im = InstructionMemory(config)
        await im.set_instruction("global", "你是一个友好的AI助手")
        await im.set_instruction("agent:tongyi", "使用中文回复")
        prompt = await im.get_active_instructions(["global", "agent:tongyi"])
    """

    def __init__(self, config: MemoryConfig = None):
        super().__init__(config)
        self._scopes: Dict[str, Dict] = {}  # scope -> {content, priority, entry_id}

    # ── 指令管理 ──

    async def set_instruction(self, scope: str, content: str, priority: int = 0) -> str:
        """
        设置某个 scope 的指令。

        Args:
            scope: 作用域标识
            content: 指令文本
            priority: 优先级（越大越靠前，默认 0）

        Returns:
            指令 ID（= scope）
        """
        entry_id = f"instr_{scope}"
        self._scopes[scope] = {
            "content": content,
            "priority": priority,
            "entry_id": entry_id,
        }
        logger.debug(f"[INSTR-MEM] set '{scope}', priority={priority}, len={len(content)}")
        return entry_id

    async def get_instruction(self, scope: str) -> Optional[str]:
        """获取单个 scope 的指令。"""
        entry = self._scopes.get(scope)
        return entry["content"] if entry else None

    async def get_active_instructions(self, scopes: List[str] = None) -> str:
        """
        合并多个 scope 的指令为一个 prompt 片段。

        Args:
            scopes: 要包含的 scope 列表。None = 使用 config 中的默认 scopes。

        Returns:
            合并后的指令文本，按 priority 降序排列。
        """
        if scopes is None:
            scopes = self.config.instruction_scopes

        entries = []
        for scope in scopes:
            entry = self._scopes.get(scope)
            if entry and entry["content"]:
                entries.append(entry)

        # 按 priority 降序
        entries.sort(key=lambda e: e["priority"], reverse=True)

        return "\n\n".join(e["content"] for e in entries)

    async def remove_instruction(self, scope: str) -> bool:
        """删除某个 scope 的指令。"""
        if scope in self._scopes:
            del self._scopes[scope]
            return True
        return False

    async def list_scopes(self) -> List[str]:
        """列出所有已注册的 scope。"""
        return sorted(self._scopes.keys())

    # ── BaseMemory 接口 ──

    async def store(self, entry: MemoryEntry) -> str:
        scope = entry.metadata.get("scope", "global")
        return await self.set_instruction(scope, entry.content, int(entry.importance * 10))

    async def retrieve(self, query: str = "", limit: int = 5, **filters) -> List[MemoryEntry]:
        scopes = filters.get("scopes", None)
        text = await self.get_active_instructions(scopes)
        if not text:
            return []
        return [MemoryEntry(content=text, memory_type="instruction", entry_id="all")]

    async def forget(self, entry_id: str = None, older_than_days: int = None) -> int:
        if entry_id:
            scope = entry_id.replace("instr_", "")
            return 1 if await self.remove_instruction(scope) else 0
        count = len(self._scopes)
        self._scopes.clear()
        return count

    async def clear(self) -> None:
        self._scopes.clear()

    def count(self) -> int:
        return len(self._scopes)
