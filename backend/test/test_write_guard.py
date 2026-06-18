"""
测试 MemoryWriteGuard — 写入前过滤规则引擎。
"""

import pytest
from backend.memory.base import MemoryEntry, MemoryType, GuardResult
from backend.memory.write_guard import MemoryWriteGuard, _SENSITIVE_PATTERNS


class TestWriteGuardSensitive:
    """sensition 规则：拦截敏感信息"""

    @pytest.mark.asyncio
    async def test_blocks_api_key(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(content="我的 API key 是 sk-abc123def456ghijklmn7890", memory_type="project")
        result = await guard.evaluate(entry)
        assert not result.allowed
        assert result.rule == "sensitive"

    @pytest.mark.asyncio
    async def test_blocks_jwt_token(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(
            content="token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
            memory_type="project",
        )
        result = await guard.evaluate(entry)
        assert not result.allowed
        assert result.rule == "sensitive"

    @pytest.mark.asyncio
    async def test_blocks_connection_string(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(content="数据库地址: mongodb://admin:secret123@localhost:27017/mydb", memory_type="reference")
        result = await guard.evaluate(entry)
        assert not result.allowed
        assert result.rule == "sensitive"

    @pytest.mark.asyncio
    async def test_allows_normal_content(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(content="用户偏好使用 Python 进行后端开发", memory_type="user")
        result = await guard.evaluate(entry)
        assert result.allowed


class TestWriteGuardTemporary:
    """temporary 规则：拦截一次性临时任务"""

    @pytest.mark.asyncio
    async def test_blocks_temporary_task_with_time(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(content="用户让今天下午3点帮他写一个排序算法", memory_type="user")
        result = await guard.evaluate(entry)
        assert not result.allowed
        assert result.rule == "temporary"

    @pytest.mark.asyncio
    async def test_blocks_task_verb_as_user_type(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(content="用户让我查一下文档", memory_type="user")
        result = await guard.evaluate(entry)
        assert not result.allowed
        assert result.rule == "temporary"

    @pytest.mark.asyncio
    async def test_allows_preference_not_task(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(content="用户偏好使用函数式编程风格", memory_type="user")
        result = await guard.evaluate(entry)
        assert result.allowed


class TestWriteGuardDerivable:
    """derivable 规则：拦截可从上下文直接推导的信息"""

    @pytest.mark.asyncio
    async def test_blocks_duplicate_content_in_context(self):
        guard = MemoryWriteGuard()
        context = [{"role": "user", "content": "我使用 Python 3.12 和 FastAPI"}]
        entry = MemoryEntry(content="我使用 Python 3.12 和 FastAPI", memory_type="project")
        result = await guard.evaluate(entry, context)
        assert not result.allowed
        assert result.rule == "derivable"

    @pytest.mark.asyncio
    async def test_allows_new_content_not_in_context(self):
        guard = MemoryWriteGuard()
        context = [{"role": "user", "content": "今天天气不错"}]
        entry = MemoryEntry(content="用户是高级 Python 开发者", memory_type="user")
        result = await guard.evaluate(entry, context)
        assert result.allowed


class TestWriteGuardTransient:
    """transient 规则：拦截精确行号/时间戳的瞬时状态"""

    @pytest.mark.asyncio
    async def test_blocks_line_number_error(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(content="在第 42 行出现了 NameError", memory_type="project")
        result = await guard.evaluate(entry)
        assert not result.allowed
        assert result.rule == "transient"

    @pytest.mark.asyncio
    async def test_blocks_precise_timestamp(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(content="2024-06-15T14:30:00 时数据库连接超时", memory_type="project")
        result = await guard.evaluate(entry)
        assert not result.allowed
        assert result.rule == "transient"

    @pytest.mark.asyncio
    async def test_allows_without_line_number(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(content="部署时遇到了端口冲突问题", memory_type="project")
        result = await guard.evaluate(entry)
        assert result.allowed


class TestWriteGuardIntermediate:
    """intermediate 规则：拦截中间结果"""

    @pytest.mark.asyncio
    async def test_blocks_intermediate_marker(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(content="中间结果：正在处理数据文件", memory_type="project")
        result = await guard.evaluate(entry)
        assert not result.allowed
        assert result.rule == "intermediate"

    @pytest.mark.asyncio
    async def test_blocks_attempt_count(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(content="尝试了 3 种不同的搜索关键词", memory_type="project")
        result = await guard.evaluate(entry)
        assert not result.allowed
        assert result.rule == "intermediate"

    @pytest.mark.asyncio
    async def test_allows_in_final_response(self):
        guard = MemoryWriteGuard()
        context = [{"role": "assistant", "content": "中间结果：已下载 3 个文件，正在处理..."}]
        entry = MemoryEntry(content="中间结果：已下载 3 个文件", memory_type="project")
        result = await guard.evaluate(entry, context)
        # 因为出现在 assistant 最终回复中，应该放行
        assert result.allowed


class TestWriteGuardDuplicate:
    """duplicate 规则：拦截语义重复"""

    @pytest.mark.asyncio
    async def test_blocks_exact_hash_duplicate(self):
        guard = MemoryWriteGuard()
        entry1 = MemoryEntry(content="项目使用 FastAPI 作为 Web 框架", memory_type="project")
        entry2 = MemoryEntry(content="项目使用 FastAPI 作为 Web 框架", memory_type="project")

        r1 = await guard.evaluate(entry1)
        assert r1.allowed

        r2 = await guard.evaluate(entry2)
        assert not r2.allowed
        assert r2.rule == "duplicate"


class TestWriteGuardBatch:
    """批量评估"""

    @pytest.mark.asyncio
    async def test_evaluate_batch_filters_correctly(self):
        guard = MemoryWriteGuard()
        entries = [
            MemoryEntry(content="用户是 Python 开发者", memory_type="user"),
            MemoryEntry(content="API key: sk-verylongsecretkey12345", memory_type="project"),
            MemoryEntry(content="项目使用 PostgreSQL", memory_type="project"),
            MemoryEntry(content="帮我写一个登录页面", memory_type="user"),  # 临时任务
        ]
        filtered = await guard.evaluate_batch(entries)
        assert len(filtered) == 2  # only Python dev and PostgreSQL
        assert all(e.metadata.get("guard_rule") == "passed" for e in filtered)


class TestWriteGuardImportanceAdjustment:
    """重要性修正"""

    @pytest.mark.asyncio
    async def test_feedback_gets_high_importance(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(
            content="用户纠正：不应该在数据量小时使用 pandas",
            memory_type="feedback",
            importance=0.5,
        )
        result = await guard.evaluate(entry)
        assert result.allowed
        assert result.score >= 0.85

    @pytest.mark.asyncio
    async def test_reference_keeps_moderate_importance(self):
        guard = MemoryWriteGuard()
        entry = MemoryEntry(
            content="项目部署在 https://api.example.com",
            memory_type="reference",
            importance=0.4,
        )
        result = await guard.evaluate(entry)
        assert result.allowed
        assert result.score >= 0.5
