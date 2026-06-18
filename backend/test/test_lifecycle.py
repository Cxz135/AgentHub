"""
测试 LifecycleManager — 记忆生命周期状态机。
"""

import time
import pytest
from backend.memory.base import MemoryLifecycleStage
from backend.memory.lifecycle import LifecycleManager, LifecycleStats


class TestLifecycleManager:
    """基础的 CREATED → ACTIVE → DORMANT → ARCHIVED 流转"""

    def test_created_stays_created_when_no_access(self):
        lm = LifecycleManager()
        now = time.time()
        stage = lm.evaluate(
            entry_id="mem_1",
            current_stage="created",
            importance=0.8,
            created_at=now,  # 刚刚创建
        )
        assert stage == MemoryLifecycleStage.CREATED

    def test_created_to_active_after_one_day(self):
        lm = LifecycleManager()
        one_day_ago = time.time() - 86401  # 略超 1 天
        stage = lm.evaluate(
            entry_id="mem_1",
            current_stage="created",
            importance=0.8,
            created_at=one_day_ago,
        )
        assert stage == MemoryLifecycleStage.ACTIVE

    def test_created_to_active_when_accessed(self):
        lm = LifecycleManager()
        lm.track_access("mem_1")
        stage = lm.evaluate(
            entry_id="mem_1",
            current_stage="created",
            importance=0.8,
            created_at=time.time(),
        )
        assert stage == MemoryLifecycleStage.ACTIVE

    def test_active_to_dormant_after_threshold(self):
        lm = LifecycleManager(dormant_days=30)
        long_ago = time.time() - (31 * 86400)  # 31 天前创建且从未访问
        stage = lm.evaluate(
            entry_id="mem_1",
            current_stage="active",
            importance=0.5,
            created_at=long_ago,
        )
        assert stage == MemoryLifecycleStage.DORMANT

    def test_active_stays_active_with_recent_access(self):
        lm = LifecycleManager(dormant_days=30)
        lm.track_access("mem_1")  # 刚刚访问过
        long_ago_created = time.time() - (60 * 86400)  # 60 天前创建的
        stage = lm.evaluate(
            entry_id="mem_1",
            current_stage="active",
            importance=0.5,
            created_at=long_ago_created,
        )
        assert stage == MemoryLifecycleStage.ACTIVE

    def test_dormant_to_archived_low_score(self):
        lm = LifecycleManager(archive_score=0.3)
        stage = lm.evaluate(
            entry_id="mem_1",
            current_stage="dormant",
            importance=0.1,  # 超低评分
            created_at=time.time() - (60 * 86400),
        )
        assert stage == MemoryLifecycleStage.ARCHIVED

    def test_dormant_to_active_when_reaccessed(self):
        lm = LifecycleManager(dormant_days=30)
        long_ago = time.time() - (31 * 86400)
        lm.track_access("mem_1")  # 刚访问了
        stage = lm.evaluate(
            entry_id="mem_1",
            current_stage="dormant",
            importance=0.5,
            created_at=long_ago,
        )
        assert stage == MemoryLifecycleStage.ACTIVE

    def test_terminal_stages_dont_change(self):
        lm = LifecycleManager()
        # DESTROYED 不再流转
        stage = lm.evaluate(
            entry_id="mem_1",
            current_stage="destroyed",
            importance=0.5,
            created_at=time.time(),
        )
        assert stage == MemoryLifecycleStage.DESTROYED


class TestLifecycleManagerBatch:
    """批量评估"""

    def test_batch_returns_only_transitions(self):
        lm = LifecycleManager(dormant_days=30)
        now = time.time()

        entries = [
            {
                "entry_id": "1",
                "lifecycle_stage": "created",
                "importance": 0.8,
                "timestamp": time.time() - 86401,  # → ACTIVE
            },
            {
                "entry_id": "2",
                "lifecycle_stage": "active",
                "importance": 0.2,
                "timestamp": time.time() - (60 * 86400),  # → DORMANT
            },
            {
                "entry_id": "3",
                "lifecycle_stage": "destroyed",
                "importance": 0.5,
                "timestamp": now,  # 终态，不变
            },
        ]

        transitions = lm.evaluate_batch(entries)
        assert "1" in transitions
        assert transitions["1"] == MemoryLifecycleStage.ACTIVE
        assert "2" in transitions
        assert transitions["2"] == MemoryLifecycleStage.DORMANT
        assert "3" not in transitions


class TestLifecycleStats:
    """统计"""

    def test_counts_per_stage(self):
        lm = LifecycleManager()
        entries = [
            {"lifecycle_stage": "created"},
            {"lifecycle_stage": "created"},
            {"lifecycle_stage": "active"},
            {"lifecycle_stage": "active"},
            {"lifecycle_stage": "active"},
            {"lifecycle_stage": "dormant"},
            {"lifecycle_stage": "archived"},
            {"lifecycle_stage": "destroyed"},
        ]

        stats = lm.get_stats(entries)
        assert stats.total == 8
        assert stats.created == 2
        assert stats.active == 3
        assert stats.dormant == 1
        assert stats.archived == 1
        assert stats.destroyed == 1
