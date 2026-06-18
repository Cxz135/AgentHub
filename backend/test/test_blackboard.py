"""
测试 Blackboard — 结构化任务黑板。
"""

import time
import pytest
from backend.memory.blackboard import Blackboard, BlackboardEntry


class TestBlackboardEntry:
    """BlackboardEntry 数据结构"""

    def test_create_entry(self):
        entry = BlackboardEntry(
            key="market_report",
            value="AI市场规模增长30%",
            source_agent_id="agent-research",
            source_step_id="step_1",
            confidence=0.95,
        )
        assert entry.key == "market_report"
        assert entry.confidence == 0.95
        assert entry.version == 1
        assert not entry.is_expired()
        assert entry.is_confident()

    def test_entry_expiry(self):
        # 已过期的条目
        past = time.time() - 3600
        entry = BlackboardEntry(key="old", value="data", expires_at=past)
        assert entry.is_expired()

    def test_entry_no_expiry(self):
        entry = BlackboardEntry(key="perm", value="data")
        assert not entry.is_expired()

    def test_entry_future_expiry(self):
        future = time.time() + 86400
        entry = BlackboardEntry(key="temp", value="data", expires_at=future)
        assert not entry.is_expired()

    def test_entry_confidence_threshold(self):
        entry = BlackboardEntry(key="low_conf", value="data", confidence=0.3)
        assert not entry.is_confident(threshold=0.5)
        assert entry.is_confident(threshold=0.2)

    def test_entry_staleness(self):
        old = time.time() - 7200
        entry = BlackboardEntry(key="stale", value="data", produced_at=old)
        assert entry.is_stale(max_age_seconds=3600)

    def test_to_context_text(self):
        entry = BlackboardEntry(
            key="decision",
            value="决定使用FastAPI",
            source_agent_id="planner",
            confidence=0.9,
            dependencies=["research"],
        )
        ctx = entry.to_context_text()
        assert "decision" in ctx
        assert "FastAPI" in ctx
        assert "planner" in ctx
        assert "90%" in ctx
        assert "research" in ctx

    def test_from_dict_roundtrip(self):
        entry = BlackboardEntry(
            key="test", value="hello", confidence=0.8,
            dependencies=["a", "b"], metadata={"tag": "important"},
        )
        d = entry.to_dict()
        restored = BlackboardEntry.from_dict(d)
        assert restored.key == "test"
        assert restored.confidence == 0.8
        assert restored.dependencies == ["a", "b"]
        assert restored.metadata == {"tag": "important"}


class TestBlackboardCRUD:
    """Blackboard CRUD 操作"""

    def test_put_and_get(self):
        bb = Blackboard()
        bb.put_raw("key1", "value1")
        assert bb.get_value("key1") == "value1"
        entry = bb.get("key1")
        assert entry is not None
        assert entry.version == 1

    def test_put_updates_version(self):
        bb = Blackboard()
        bb.put_raw("key1", "v1")
        bb.put_raw("key1", "v2")
        entry = bb.get("key1")
        assert entry.version == 2
        assert entry.value == "v2"

    def test_get_nonexistent(self):
        bb = Blackboard()
        assert bb.get("nonexistent") is None
        assert bb.get_value("nonexistent") is None
        assert bb.get_value("nonexistent", "default") == "default"

    def test_get_expired_returns_none(self):
        bb = Blackboard()
        bb.put_raw("temp", "data", expires_at=time.time() - 1)
        assert bb.get("temp") is None
        assert bb.get_value("temp") is None

    def test_get_all_filters_expired(self):
        bb = Blackboard()
        bb.put_raw("active", "data")
        bb.put_raw("expired", "data", expires_at=time.time() - 1)
        all_entries = bb.get_all()
        assert "active" in all_entries
        assert "expired" not in all_entries

    def test_get_active_filters_low_confidence(self):
        bb = Blackboard()
        bb.put_raw("high", "data", confidence=0.9)
        bb.put_raw("low", "data", confidence=0.3)
        active = bb.get_active()
        assert len(active) == 1
        assert active[0].key == "high"


class TestBlackboardVersioning:
    """版本控制"""

    def test_version_increments(self):
        bb = Blackboard()
        assert bb.version == 0
        bb.put_raw("a", "1")
        assert bb.version == 1
        bb.put_raw("b", "2")
        assert bb.version == 2

    def test_snapshot_is_immutable_copy(self):
        bb = Blackboard()
        bb.put_raw("key1", "value1")
        snap = bb.snapshot()

        # 修改原始黑板
        bb.put_raw("key1", "value2")

        # 快照不变
        snap_entries = snap["entries"]
        assert snap_entries["key1"]["value"] == "value1"

    def test_from_snapshot(self):
        bb = Blackboard()
        bb.put_raw("key1", "value1", confidence=0.8)
        snap = bb.snapshot()

        bb2 = Blackboard.from_snapshot(snap)
        assert bb2.get_value("key1") == "value1"
        assert bb2.get("key1").confidence == 0.8


class TestBlackboardDependencies:
    """依赖管理"""

    def test_dependency_chain(self):
        bb = Blackboard()
        bb.put_raw("a", "step a", dependencies=[])
        bb.put_raw("b", "step b", dependencies=["a"])
        bb.put_raw("c", "step c", dependencies=["b"])

        chain = bb.get_dependency_chain("c")
        assert chain == ["a", "b", "c"]

    def test_dependents(self):
        bb = Blackboard()
        bb.put_raw("a", "base", dependencies=[])
        bb.put_raw("b", "depends on a", dependencies=["a"])
        bb.put_raw("c", "also depends on a", dependencies=["a"])

        deps = bb.get_dependents("a")
        assert len(deps) == 2
        assert {d.key for d in deps} == {"b", "c"}

    def test_validate_missing_dependency(self):
        bb = Blackboard()
        bb.put_raw("b", "value", dependencies=["missing"])
        missing = bb.validate_dependencies()
        assert len(missing) == 1
        assert "b → missing" in missing

    def test_detect_cycle(self):
        bb = Blackboard()
        bb.put_raw("a", "a", dependencies=["b"])
        bb.put_raw("b", "b", dependencies=["a"])
        cycles = bb.detect_cycles()
        assert len(cycles) > 0

    def test_no_cycle_in_dag(self):
        bb = Blackboard()
        bb.put_raw("a", "a", dependencies=[])
        bb.put_raw("b", "b", dependencies=["a"])
        bb.put_raw("c", "c", dependencies=["a", "b"])
        cycles = bb.detect_cycles()
        assert len(cycles) == 0

    def test_context_for_selective_keys(self):
        bb = Blackboard()
        bb.put_raw("market", "市场报告内容", confidence=0.9)
        bb.put_raw("competitor", "竞品分析内容", confidence=0.85)
        bb.put_raw("internal", "内部备忘录", confidence=0.5)

        ctx = bb.get_context_for(keys=["market", "competitor"])
        assert "市场报告" in ctx
        assert "竞品分析" in ctx
        assert "内部备忘录" not in ctx


class TestBlackboardMaintenance:
    """维护操作"""

    def test_cleanup_expired(self):
        bb = Blackboard()
        bb.put_raw("active", "data")
        bb.put_raw("old1", "old", expires_at=time.time() - 1)
        bb.put_raw("old2", "old", expires_at=time.time() - 10)

        removed = bb.cleanup_expired()
        assert removed == 2
        assert bb.count == 1

    def test_stats(self):
        bb = Blackboard()
        bb.put_raw("a", "1", confidence=0.9)
        bb.put_raw("b", "2", confidence=0.3)
        bb.put_raw("c", "3", expires_at=time.time() - 1, confidence=0.8)

        stats = bb.stats()
        assert stats["total"] == 3
        assert stats["active"] == 1  # only 'a' (b is low conf, c is expired)
        assert stats["expired"] == 1


class TestWorkingMemoryBlackboardIntegration:
    """WorkingMemory 与 Blackboard 集成"""

    @pytest.mark.asyncio
    async def test_set_and_get_workspace_compat(self):
        from backend.memory.working_memory import WorkingMemory
        from backend.memory.base import MemoryConfig

        wm = WorkingMemory(MemoryConfig())

        # 旧接口兼容
        await wm.set_workspace("key1", "value1")
        val = await wm.get_workspace("key1")
        assert val == "value1"

    @pytest.mark.asyncio
    async def test_set_workspace_with_metadata(self):
        from backend.memory.working_memory import WorkingMemory
        from backend.memory.base import MemoryConfig

        wm = WorkingMemory(MemoryConfig())
        await wm.set_workspace(
            "market", "市场报告",
            source_agent_id="agent-research",
            source_step_id="step_2",
            confidence=0.92,
            dependencies=["step_1"],
        )

        entry = await wm.get_blackboard_entry("market")
        assert entry is not None
        assert entry.confidence == 0.92
        assert entry.source_agent_id == "agent-research"
        assert entry.dependencies == ["step_1"]

    @pytest.mark.asyncio
    async def test_blackboard_context(self):
        from backend.memory.working_memory import WorkingMemory
        from backend.memory.base import MemoryConfig

        wm = WorkingMemory(MemoryConfig())
        await wm.set_workspace("report", "报告内容...", confidence=0.9)
        await wm.set_workspace("analysis", "分析内容...", confidence=0.85)

        ctx = await wm.get_blackboard_context()
        assert "报告内容" in ctx
        assert "分析内容" in ctx

    @pytest.mark.asyncio
    async def test_get_task_state_includes_blackboard(self):
        from backend.memory.working_memory import WorkingMemory
        from backend.memory.base import MemoryConfig

        wm = WorkingMemory(MemoryConfig())
        await wm.set_task("测试任务")
        await wm.set_workspace("result", "完成")

        state = await wm.get_task_state()
        assert "blackboard" in state
        assert "workspace" in state  # 兼容旧代码
        assert state["workspace"]["result"] == "完成"

    @pytest.mark.asyncio
    async def test_clear_resets_blackboard(self):
        from backend.memory.working_memory import WorkingMemory
        from backend.memory.base import MemoryConfig

        wm = WorkingMemory(MemoryConfig())
        await wm.set_workspace("key", "value")
        assert wm.blackboard.count == 1

        await wm.clear()
        assert wm.blackboard.count == 0

    @pytest.mark.asyncio
    async def test_blackboard_stats(self):
        from backend.memory.working_memory import WorkingMemory
        from backend.memory.base import MemoryConfig

        wm = WorkingMemory(MemoryConfig())
        await wm.set_workspace("a", "1", confidence=0.9)
        await wm.set_workspace("b", "2", confidence=0.3)

        stats = await wm.get_blackboard_stats()
        assert stats["total"] == 2
        assert stats["active"] == 1  # only high confidence
