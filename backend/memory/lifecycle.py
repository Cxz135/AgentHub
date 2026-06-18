"""
LifecycleManager — 记忆生命周期管理器。

管理各层记忆从 CREATED → ACTIVE → DORMANT → ARCHIVED → DESTROYED 的状态流转。

触发条件：
    - CREATED → ACTIVE:   经过 WriteGuard 验证 / 被检索使用
    - ACTIVE → DORMANT:   超过 30 天未被访问
    - DORMANT → ARCHIVED: 评分低于阈值（默认 0.3）
    - * → DESTROYED:      手动删除
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.memory.base import MemoryLifecycleStage

logger = logging.getLogger("core")

# 默认阈值
DEFAULT_DORMANT_DAYS = 30        # 30 天未访问 → DORMANT
DEFAULT_ARCHIVE_SCORE = 0.3      # 评分低于此 → ARCHIVED
DEFAULT_CLEANUP_DAYS = 90        # 归档 90 天后清理


@dataclass
class LifecycleStats:
    """生命周期统计。"""
    total: int = 0
    created: int = 0
    active: int = 0
    dormant: int = 0
    archived: int = 0
    destroyed: int = 0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "created": self.created,
            "active": self.active,
            "dormant": self.dormant,
            "archived": self.archived,
            "destroyed": self.destroyed,
        }


class LifecycleManager:
    """
    记忆生命周期管理器。

    使用方式：
        lm = LifecycleManager()
        lm.track_access(entry_id)  # 每次检索命中时调用
        transitions = lm.evaluate_transitions(entries)  # 批量评估状态流转
    """

    def __init__(
        self,
        dormant_days: int = DEFAULT_DORMANT_DAYS,
        archive_score: float = DEFAULT_ARCHIVE_SCORE,
        cleanup_days: int = DEFAULT_CLEANUP_DAYS,
    ):
        self.dormant_days = dormant_days
        self.archive_score = archive_score
        self.cleanup_days = cleanup_days

        # entry_id → last_access_timestamp
        self._access_tracker: Dict[str, float] = {}

    # ── 访问追踪 ──

    def track_access(self, entry_id: str) -> None:
        """记录一次记忆访问。"""
        self._access_tracker[entry_id] = time.time()

    def track_access_batch(self, entry_ids: List[str]) -> None:
        """批量记录访问。"""
        now = time.time()
        for eid in entry_ids:
            self._access_tracker[eid] = now

    def last_accessed(self, entry_id: str) -> Optional[float]:
        """获取上次访问时间。"""
        return self._access_tracker.get(entry_id)

    # ── 状态评估 ──

    def evaluate(
        self,
        entry_id: str,
        current_stage: str,
        importance: float,
        created_at: float,
        updated_at: Optional[float] = None,
    ) -> MemoryLifecycleStage:
        """
        评估单条记忆应该处于哪个阶段。

        Args:
            entry_id: 记忆 ID
            current_stage: 当前阶段
            importance: 当前重要性评分
            created_at: 创建时间戳
            updated_at: 最后更新时间戳

        Returns:
            应该转换到的目标阶段
        """
        stage = MemoryLifecycleStage(current_stage)

        # 终态不变
        if stage.is_terminal():
            return stage

        now = time.time()
        last_access = self._access_tracker.get(entry_id, updated_at or created_at)
        days_since_access = (now - last_access) / 86400.0

        # CREATED → ACTIVE：如果被访问过或存在超过 1 天
        if stage == MemoryLifecycleStage.CREATED:
            if entry_id in self._access_tracker or (now - created_at) > 86400:
                return MemoryLifecycleStage.ACTIVE
            return stage

        # ACTIVE → DORMANT：超过 dormant_days 天未访问
        if stage == MemoryLifecycleStage.ACTIVE and days_since_access > self.dormant_days:
            return MemoryLifecycleStage.DORMANT

        # DORMANT → ACTIVE：被重新访问
        if stage == MemoryLifecycleStage.DORMANT and entry_id in self._access_tracker:
            if days_since_access < self.dormant_days:
                return MemoryLifecycleStage.ACTIVE

        # DORMANT → ARCHIVED：评分低于阈值
        if stage == MemoryLifecycleStage.DORMANT and importance < self.archive_score:
            return MemoryLifecycleStage.ARCHIVED

        return stage

    def evaluate_batch(
        self,
        entries: List[Dict[str, Any]],
    ) -> Dict[str, MemoryLifecycleStage]:
        """
        批量评估，返回 {entry_id: 目标阶段}。

        每个 entry dict 需包含: entry_id, lifecycle_stage, importance, timestamp
        """
        transitions = {}
        for e in entries:
            eid = e.get("entry_id") or e.get("id", "")
            if not eid:
                continue
            target = self.evaluate(
                entry_id=str(eid),
                current_stage=e.get("lifecycle_stage", "active"),
                importance=float(e.get("importance", 0.5)),
                created_at=float(e.get("timestamp", time.time())),
            )
            current = MemoryLifecycleStage(e.get("lifecycle_stage", "active"))
            if target != current:
                transitions[str(eid)] = target
        return transitions

    # ── 统计 ──

    def get_stats(self, entries: List[Dict[str, Any]]) -> LifecycleStats:
        """统计各阶段数量。"""
        stats = LifecycleStats(total=len(entries))
        for e in entries:
            stage = e.get("lifecycle_stage", "active")
            if hasattr(stats, stage):
                setattr(stats, stage, getattr(stats, stage) + 1)
        return stats

    # ── 清理 ──

    def should_cleanup(self, entry_id: str, archived_at: float) -> bool:
        """判断归档记忆是否应该被永久清理。"""
        return (time.time() - archived_at) > (self.cleanup_days * 86400)

    def reset_access_tracker(self) -> None:
        """清空访问追踪（跨会话时调用）。"""
        self._access_tracker.clear()
