"""
Blackboard — 结构化任务黑板。

替代原来 WorkingMemory 中的扁平 `_workspace` dict，为每个黑板条目增加：
    - version:        版本号（支持并发冲突检测和回滚）
    - source_agent_id: 来源 Agent
    - source_step_id:  来源任务步骤
    - confidence:      置信度 (0.0~1.0)
    - expires_at:      过期时间（None=永不过期）
    - dependencies:    依赖的其他条目 key 列表
    - metadata:        额外元数据

关键设计原则（来自 Claude 规范）：
    1. 绝对只读原则：子 Agent 只能读取黑板快照，不能直接修改
    2. 快照原则：传给子 Agent 的是不可变快照，不是引用
    3. 原子性原则：每次写入都是原子的
    4. 事实性原则：黑板只存已验证的事实，不存推理和中间步骤
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core")


# ═══════════════════════════════════════════════════════════════
# BlackboardEntry
# ═══════════════════════════════════════════════════════════════

@dataclass
class BlackboardEntry:
    """
    黑板上的一条记录。

    示例:
        entry = BlackboardEntry(
            key="market_research",
            value="2024年AI市场规模增长了30%，达到500亿美元...",
            source_agent_id="agent-research-5678",
            source_step_id="step_1",
            confidence=0.95,
            dependencies=["user_query"],
        )
    """

    key: str
    value: Any
    source_agent_id: str = "orchestrator"
    source_step_id: str = ""
    produced_at: float = field(default_factory=time.time)
    confidence: float = 1.0          # 0.0 ~ 1.0
    expires_at: Optional[float] = None  # None = 永不过期
    dependencies: List[str] = field(default_factory=list)
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── 判定方法 ──

    def is_expired(self) -> bool:
        """检查是否已过期。"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def is_confident(self, threshold: float = 0.5) -> bool:
        """置信度是否达到阈值。"""
        return self.confidence >= threshold

    def is_stale(self, max_age_seconds: float = 3600) -> bool:
        """是否已过时（超过最大存活时间）。"""
        return (time.time() - self.produced_at) > max_age_seconds

    # ── 输出 ──

    def to_context_text(self, max_length: int = 500) -> str:
        """生成注入子 Agent 上下文的文本片段。"""
        value_str = str(self.value)[:max_length]
        lines = [
            f"[{self.key}] (来源: {self.source_agent_id}, 置信度: {self.confidence:.0%})",
            value_str,
        ]
        if self.dependencies:
            lines.append(f"依赖: {', '.join(self.dependencies)}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "source_agent_id": self.source_agent_id,
            "source_step_id": self.source_step_id,
            "produced_at": self.produced_at,
            "confidence": self.confidence,
            "expires_at": self.expires_at,
            "dependencies": self.dependencies,
            "version": self.version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BlackboardEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════
# Blackboard
# ═══════════════════════════════════════════════════════════════

class Blackboard:
    """
    结构化任务黑板。

    使用方式:
        bb = Blackboard()
        bb.put(BlackboardEntry(key="research", value="...", confidence=0.9))
        entry = bb.get("research")
        ctx = bb.get_context_for(["research", "competitor_analysis"])
        snap = bb.snapshot()  # 不可变快照，传给子 Agent
    """

    def __init__(self, max_history: int = 50):
        self._entries: Dict[str, BlackboardEntry] = {}
        self._version: int = 0
        self._history: List[Dict[str, Any]] = []  # 变更日志
        self._max_history = max_history

    # ── 写入 ──

    def put(self, entry: BlackboardEntry) -> str:
        """
        写入或更新一条黑板记录。

        规则：
        - 如果 key 已存在，version 递增
        - 新条目 version 从 1 开始
        - 每次写入记录变更历史

        Returns:
            entry key
        """
        existing = self._entries.get(entry.key)
        if existing:
            # 更新：版本递增，保留原始 produced_at
            entry.version = existing.version + 1
            if entry.produced_at == existing.produced_at and entry.produced_at > 0:
                entry.produced_at = time.time()  # 只有完全相同才更新时间戳
        else:
            entry.version = 1

        self._entries[entry.key] = entry
        self._version += 1

        # 记录变更
        self._history.append({
            "action": "put",
            "key": entry.key,
            "version": entry.version,
            "ts": time.time(),
        })
        self._trim_history()

        logger.debug(
            f"[BB] put '{entry.key}' v{entry.version} "
            f"(src={entry.source_agent_id}, conf={entry.confidence:.0%})"
        )
        return entry.key

    def put_raw(
        self,
        key: str,
        value: Any,
        source_agent_id: str = "orchestrator",
        source_step_id: str = "",
        confidence: float = 1.0,
        expires_at: Optional[float] = None,
        dependencies: List[str] = None,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """便捷方法：从原始值创建 BlackboardEntry 并写入。"""
        return self.put(BlackboardEntry(
            key=key,
            value=value,
            source_agent_id=source_agent_id,
            source_step_id=source_step_id,
            confidence=confidence,
            expires_at=expires_at,
            dependencies=dependencies or [],
            metadata=metadata or {},
        ))

    # ── 读取 ──

    def get(self, key: str) -> Optional[BlackboardEntry]:
        """获取单条记录。跳过已过期的记录。"""
        entry = self._entries.get(key)
        if entry and entry.is_expired():
            logger.debug(f"[BB] get '{key}' → 已过期")
            return None
        return entry

    def get_value(self, key: str, default: Any = None) -> Any:
        """获取记录的值（简化接口，兼容旧 _workspace dict 风格）。"""
        entry = self.get(key)
        return entry.value if entry else default

    def get_all(self) -> Dict[str, BlackboardEntry]:
        """获取所有未过期的记录。"""
        return {k: v for k, v in self._entries.items() if not v.is_expired()}

    def get_active(self) -> List[BlackboardEntry]:
        """返回所有活跃记录（未过期 + 置信度达标）。"""
        return [
            e for e in self._entries.values()
            if not e.is_expired() and e.is_confident()
        ]

    # ── 依赖 & 上下文 ──

    def get_dependents(self, key: str) -> List[BlackboardEntry]:
        """获取依赖指定 key 的所有记录。"""
        return [e for e in self._entries.values() if key in e.dependencies]

    def get_dependency_chain(self, key: str) -> List[str]:
        """递归获取某个 key 的完整依赖链（拓扑顺序）。"""
        visited = set()
        result = []

        def _dfs(k: str):
            if k in visited:
                return
            visited.add(k)
            entry = self._entries.get(k)
            if entry:
                for dep in entry.dependencies:
                    _dfs(dep)
                result.append(k)

        _dfs(key)
        return result

    def get_context_for(
        self,
        keys: List[str] = None,
        max_length_per_entry: int = 500,
    ) -> str:
        """
        为子 Agent 生成黑板上下文文本。

        Args:
            keys: 需要的 key 列表（None = 所有活跃记录）
            max_length_per_entry: 每条记录的最大字符数

        Returns:
            格式化的上下文文本
        """
        if keys is None:
            entries = self.get_active()
        else:
            entries = []
            for k in keys:
                e = self.get(k)
                if e and not e.is_expired():
                    entries.append(e)

        if not entries:
            return ""

        # 按置信度降序排列（更可靠的信息在前）
        entries.sort(key=lambda e: e.confidence, reverse=True)

        parts = ["=== 黑板上下文（共享任务产出） ===\n"]
        for e in entries:
            parts.append(e.to_context_text(max_length_per_entry))
            parts.append("")

        return "\n".join(parts)

    def get_context_for_step(
        self,
        step_id: str,
        dependencies: List[str] = None,
    ) -> str:
        """
        为特定步骤生成上下文（仅包含其声明的依赖）。

        Args:
            step_id: 当前步骤 ID
            dependencies: 该步骤依赖的 key 列表

        Returns:
            该步骤可见的黑板上下文
        """
        if not dependencies:
            return self.get_context_for()  # 无声明依赖 → 全部可见

        # 包含依赖链中的所有 key
        all_keys = set()
        for dep in dependencies:
            chain = self.get_dependency_chain(dep)
            all_keys.update(chain)

        return self.get_context_for(keys=list(all_keys))

    # ── 快照 & 版本控制 ──

    def snapshot(self) -> Dict[str, Any]:
        """
        生成不可变快照。

        传给子 Agent 的是快照，后续黑板的更新不影响已发送的快照。
        """
        return {
            "version": self._version,
            "entries": {
                k: copy.deepcopy(e.to_dict())
                for k, e in self._entries.items()
                if not e.is_expired()
            },
            "snapshot_at": time.time(),
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict) -> Blackboard:
        """从快照恢复黑板（只读场景）。"""
        bb = cls()
        bb._version = snapshot.get("version", 0)
        for k, v in snapshot.get("entries", {}).items():
            bb._entries[k] = BlackboardEntry.from_dict(v)
        return bb

    def rollback(self, target_version: int) -> int:
        """
        回滚到指定版本（通过重放历史实现，简单场景用）。

        Returns:
            回滚后删除的条目数
        """
        # 简化实现：找到目标版本在历史中的位置，撤销之后的操作
        removed = 0
        to_remove = []
        for h in reversed(self._history):
            if self._version <= target_version:
                break
            if h["action"] == "put":
                to_remove.append(h["key"])
            self._version -= 1

        for key in to_remove:
            if key in self._entries:
                del self._entries[key]
                removed += 1

        if removed > 0:
            logger.info(f"[BB] 回滚到 v{target_version}, 移除了 {removed} 条记录")

        return removed

    # ── 维护 ──

    def cleanup_expired(self) -> int:
        """清理过期记录。返回清理数量。"""
        before = len(self._entries)
        self._entries = {k: v for k, v in self._entries.items() if not v.is_expired()}
        removed = before - len(self._entries)
        if removed > 0:
            logger.info(f"[BB] 清理了 {removed} 条过期记录")
        return removed

    def validate_dependencies(self) -> List[str]:
        """
        检查依赖完整性。

        Returns:
            缺失的依赖 key 列表
        """
        all_keys = set(self._entries.keys())
        missing = []
        for entry in self._entries.values():
            for dep in entry.dependencies:
                if dep not in all_keys:
                    missing.append(f"{entry.key} → {dep}")
        return missing

    def detect_cycles(self) -> List[List[str]]:
        """检测依赖图中的循环依赖。返回所有检测到的环。"""
        cycles = []
        visited = set()
        stack = []

        def _dfs(key: str):
            if key in stack:
                cycle_start = stack.index(key)
                cycles.append(stack[cycle_start:] + [key])
                return
            if key in visited:
                return
            visited.add(key)
            stack.append(key)
            entry = self._entries.get(key)
            if entry:
                for dep in entry.dependencies:
                    if dep in self._entries:
                        _dfs(dep)
            stack.pop()

        for k in self._entries:
            _dfs(k)

        return cycles

    # ── 属性 ──

    @property
    def version(self) -> int:
        return self._version

    @property
    def count(self) -> int:
        return len(self._entries)

    @property
    def active_count(self) -> int:
        return len(self.get_active())

    def stats(self) -> Dict[str, Any]:
        """返回黑板统计信息。"""
        entries = list(self._entries.values())
        if not entries:
            return {"total": 0, "active": 0, "avg_confidence": 0, "expired": 0}

        expired = sum(1 for e in entries if e.is_expired())
        avg_conf = sum(e.confidence for e in entries) / len(entries)

        return {
            "total": len(entries),
            "active": self.active_count,
            "expired": expired,
            "avg_confidence": round(avg_conf, 3),
            "version": self._version,
            "history_size": len(self._history),
            "dependency_issues": len(self.validate_dependencies()),
            "cycles": len(self.detect_cycles()),
        }

    # ── 内部 ──

    def _trim_history(self):
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
