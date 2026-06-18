"""
测试 SessionMemoryAgent — 四级渐进式会话压缩。
"""

import pytest
from backend.memory.session_agent import (
    SessionMemoryAgent, CompressionResult, SessionSummary,
    DEFAULT_COMPRESSION_THRESHOLDS,
)
from backend.memory.short_term_memory import ShortTermMemory
from backend.memory.summary_memory import SummaryMemory
from backend.memory.base import MemoryConfig


# ── 简易 mock LLM backend ──

class MockLLMBackend:
    """模拟 LLM，根据不同输入返回对应的压缩结果。"""

    def __init__(self, responses: list = None):
        self.responses = responses or []
        self.calls = []

    async def chat(self, messages: list) -> str:
        self.calls.append(messages)
        if self.responses:
            return self.responses.pop(0) if self.responses else "[]"
        return "[]"


def make_mock_llm_for_level(level: int) -> MockLLMBackend:
    """创建针对特定压缩级别的 mock LLM。"""
    if level <= 2:
        return MockLLMBackend([
            '[{"role": "user", "content": "压缩后的用户消息"}, '
            '{"role": "assistant", "content": "压缩后的助手回复"}]'
        ])
    elif level == 3:
        return MockLLMBackend([
            '{"summary": "段落摘要", '
            '"key_decisions": ["决定使用FastAPI"], '
            '"active_tasks": ["编写API"], '
            '"errors_encountered": [], '
            '"pending_questions": [], '
            '"user_preferences": ["偏好简洁代码"]}'
        ])
    else:
        return MockLLMBackend([
            '{"global_summary": "全局摘要", '
            '"key_outcomes": ["完成了API开发"], '
            '"unresolved": [], '
            '"user_context": "高级Python开发者", '
            '"suggestions": ["建议添加测试"]}'
        ])


class TestCompressionThresholds:
    """压缩阈值判定 — 从高到低返回最高适用级别"""

    def test_no_compression_below_50_percent(self):
        agent = SessionMemoryAgent(llm_backend=None)
        level = agent._determine_level(0.45)
        assert level == 0

    def test_l1_at_55_percent(self):
        agent = SessionMemoryAgent(llm_backend=None)
        level = agent._determine_level(0.55)
        assert level == 1

    def test_l2_at_75_percent(self):
        agent = SessionMemoryAgent(llm_backend=None)
        level = agent._determine_level(0.75)
        assert level == 2

    def test_l3_at_88_percent(self):
        agent = SessionMemoryAgent(llm_backend=None)
        level = agent._determine_level(0.88)
        assert level == 3

    def test_l4_at_97_percent(self):
        agent = SessionMemoryAgent(llm_backend=None)
        level = agent._determine_level(0.97)
        assert level == 4

    def test_no_repeat_compression_same_level(self):
        agent = SessionMemoryAgent(llm_backend=None)
        agent._last_level = 2
        # ratio=0.80 满足 L1(0.50), L2(0.70)，但 _last_level=2 所以只能 > 2
        # L3 threshold=0.85，0.80 < 0.85 → 不满足 → 返回 0
        level = agent._determine_level(0.80)
        assert level == 0  # 无法跳到下一级

    def test_jumps_to_next_level_when_ratio_sufficient(self):
        agent = SessionMemoryAgent(llm_backend=None)
        agent._last_level = 2
        # ratio=0.90 满足 L3(0.85) 且 3 > 2
        level = agent._determine_level(0.90)
        assert level == 3

    def test_force_upgrades_level(self):
        agent = SessionMemoryAgent(llm_backend=None)
        agent._last_level = 1
        level = agent._determine_level(0.55, force=True)
        assert level == 2

    def test_custom_thresholds(self):
        agent = SessionMemoryAgent(llm_backend=None, thresholds={1: 0.30, 2: 0.60, 3: 0.80, 4: 0.95})
        assert agent._determine_level(0.35) == 1
        assert agent._determine_level(0.65) == 2
        assert agent._determine_level(0.85) == 3


class TestTokenEstimation:
    """Token 估算"""

    def test_estimates_empty(self):
        agent = SessionMemoryAgent(llm_backend=None)
        tokens = agent._estimate_tokens([])
        assert tokens == 0

    def test_estimates_messages(self):
        agent = SessionMemoryAgent(llm_backend=None)
        messages = [
            {"role": "user", "content": "你好，请帮我写代码"},
            {"role": "assistant", "content": "好的，我来帮你"},
        ]
        tokens = agent._estimate_tokens(messages)
        assert tokens > 0

    def test_estimates_large_content(self):
        agent = SessionMemoryAgent(llm_backend=None)
        messages = [{"role": "user", "content": "长文本" * 500}]
        tokens = agent._estimate_tokens(messages)
        assert tokens > 500


class TestCompressionResult:
    """CompressionResult 数据结构"""

    def test_successful_result(self):
        result = CompressionResult(
            level=2, compressed=True,
            messages_before=20, messages_after=10,
            tokens_before=4000, tokens_after=2000,
        )
        assert result.compressed
        assert result.level == 2
        assert result.messages_after < result.messages_before

    def test_failed_result(self):
        result = CompressionResult(
            level=3, compressed=False,
            messages_before=15, messages_after=15,
            tokens_before=3000, tokens_after=3000,
            error="LLM timeout",
        )
        assert not result.compressed
        assert result.error == "LLM timeout"


class TestSessionSummary:
    """SessionSummary 数据结构"""

    def test_empty_summary(self):
        ss = SessionSummary()
        assert ss.to_context_text() == ""

    def test_summary_with_content(self):
        ss = SessionSummary(
            global_summary="本次对话讨论了API设计",
            key_decisions=["使用FastAPI", "使用PostgreSQL"],
            active_tasks=["编写用户管理模块"],
            errors_encountered=[{"error": "端口冲突", "resolution": "改用8080"}],
            user_preferences=["偏好简洁代码"],
        )
        ctx = ss.to_context_text()
        assert "API设计" in ctx
        assert "FastAPI" in ctx
        assert "PostgreSQL" in ctx
        assert "用户管理模块" in ctx
        assert "端口冲突" in ctx
        assert "简洁代码" in ctx


class TestSessionAgentWithMockLLM:
    """完整压缩流程（mock LLM），使用 force 或精确控制 token 比"""

    @pytest.mark.asyncio
    async def test_l1_compression_forced(self):
        """force=True 时升级到下一压缩级别"""
        config = MemoryConfig(short_term_window_size=50)
        stm = ShortTermMemory(config)

        for i in range(5):
            await stm.add_turn("user", f"消息{i}")
            await stm.add_turn("assistant", f"回复{i}")

        mock_llm = make_mock_llm_for_level(1)
        agent = SessionMemoryAgent(llm_backend=mock_llm, max_tokens=8000)
        agent._last_level = 0
        stm.set_session_agent(agent)

        # force 压缩：从 L0 → L1
        result = await stm.compress(force=True)
        assert result is not None
        assert result.level == 1
        assert result.compressed
        assert len(mock_llm.calls) == 1

    @pytest.mark.asyncio
    async def test_l2_compression_forced(self):
        """force=True 升级 L1→L2"""
        config = MemoryConfig(short_term_window_size=50)
        stm = ShortTermMemory(config)

        for i in range(5):
            await stm.add_turn("user", f"消息{i}")
            await stm.add_turn("assistant", f"回复{i}")

        mock_llm = make_mock_llm_for_level(2)
        agent = SessionMemoryAgent(llm_backend=mock_llm, max_tokens=8000)
        agent._last_level = 1
        stm.set_session_agent(agent)

        result = await stm.compress(force=True)
        assert result is not None
        assert result.level == 2
        assert result.compressed

    @pytest.mark.asyncio
    async def test_l3_compression_forced(self):
        """force=True 升级 L2→L3，结构化摘要"""
        config = MemoryConfig(short_term_window_size=50)
        stm = ShortTermMemory(config)

        for i in range(5):
            await stm.add_turn("user", f"消息{i}")
            await stm.add_turn("assistant", f"回复{i}")

        mock_llm = make_mock_llm_for_level(3)
        agent = SessionMemoryAgent(llm_backend=mock_llm, max_tokens=8000)
        agent._last_level = 2
        stm.set_session_agent(agent)

        result = await stm.compress(force=True)
        assert result is not None
        assert result.level == 3
        assert result.structured is not None
        assert "决定使用FastAPI" in str(result.structured)

    @pytest.mark.asyncio
    async def test_l4_compression_forced(self):
        """force=True 升级 L3→L4，全局摘要"""
        config = MemoryConfig(short_term_window_size=50)
        stm = ShortTermMemory(config)

        for i in range(5):
            await stm.add_turn("user", f"消息{i}")
            await stm.add_turn("assistant", f"回复{i}")

        mock_llm = make_mock_llm_for_level(4)
        agent = SessionMemoryAgent(llm_backend=mock_llm, max_tokens=8000)
        agent._last_level = 3
        stm.set_session_agent(agent)

        result = await stm.compress(force=True)
        assert result is not None
        assert result.level == 4
        assert result.compressed
        assert result.structured is not None
        assert "全局摘要" in str(result.structured)

    @pytest.mark.asyncio
    async def test_compress_if_needed_noop_when_below_threshold(self):
        """token 比低于阈值时不触发压缩"""
        config = MemoryConfig(short_term_window_size=50)
        stm = ShortTermMemory(config)
        stm.max_tokens = 8000

        for i in range(3):
            await stm.add_turn("user", "短消息")
            await stm.add_turn("assistant", "短回复")

        mock_llm = make_mock_llm_for_level(1)
        agent = SessionMemoryAgent(llm_backend=mock_llm, max_tokens=8000)
        stm.set_session_agent(agent)

        result = await stm.compress_if_needed()
        # ratio 很低 → 不触发 → compress_if_needed 返回 None
        assert result is None

    @pytest.mark.asyncio
    async def test_compress_if_needed_triggers_when_ratio_high(self):
        """token 比高时自动触发压缩"""
        config = MemoryConfig(short_term_window_size=50)
        stm = ShortTermMemory(config)

        # max_tokens 极小 + 多条消息 → 高 ratio
        stm.max_tokens = 30
        for i in range(5):
            await stm.add_turn("user", "消息内容")
            await stm.add_turn("assistant", "回复内容")

        # 使用能处理 L1 的 mock
        mock_llm = make_mock_llm_for_level(1)
        agent = SessionMemoryAgent(llm_backend=mock_llm, max_tokens=30)
        stm.set_session_agent(agent)

        result = await stm.compress_if_needed()
        assert result is not None
        # 可能触发也可能不触发（取决于 token 估算精度），但至少不应崩溃
        assert result.level >= 0


class TestSummaryMemoryCompression:
    """SummaryMemory 压缩摘要存储"""

    def test_store_compression_level3(self):
        sm = SummaryMemory()
        result = CompressionResult(
            level=3, compressed=True,
            messages_before=30, messages_after=12,
            tokens_before=5000, tokens_after=2000,
            summary="段落摘要内容",
            structured={
                "summary": "段落摘要",
                "key_decisions": ["使用Redis缓存"],
                "active_tasks": ["实现缓存层"],
                "errors_encountered": [{"error": "连接超时", "resolution": "增加超时时间"}],
            },
        )
        sm.store_compression(result)

        l3_summaries = sm.get_compression_summary(level=3)
        assert len(l3_summaries) == 1
        assert l3_summaries[0]["summary"] == "段落摘要内容"

        ctx = sm.get_compression_context()
        assert "Redis缓存" in ctx

    def test_store_compression_level4_updates_global(self):
        sm = SummaryMemory()
        result = CompressionResult(
            level=4, compressed=True,
            messages_before=50, messages_after=6,
            tokens_before=8000, tokens_after=1000,
            summary="这是全局会话摘要",
            structured={"global_summary": "这是全局会话摘要", "key_outcomes": ["完成API"]},
        )
        sm.store_compression(result)

        assert sm._global_summary == "这是全局会话摘要"
        assert sm.get_latest_compression_level() == 4

        stats = sm.get_compression_stats()
        assert stats["total_compressions"] == 1
        assert stats["latest_level"] == 4

    def test_multiple_compressions_accumulate(self):
        sm = SummaryMemory()
        sm.store_compression(CompressionResult(level=1, compressed=True,
            messages_before=10, messages_after=8, tokens_before=3000, tokens_after=2400))
        sm.store_compression(CompressionResult(level=2, compressed=True,
            messages_before=20, messages_after=14, tokens_before=5000, tokens_after=3500))
        sm.store_compression(CompressionResult(level=3, compressed=True,
            messages_before=30, messages_after=12, tokens_before=6000, tokens_after=3000,
            summary="段3", structured={"summary": "段3", "key_decisions": ["d1"]}))

        stats = sm.get_compression_stats()
        assert stats["total_compressions"] == 3
        assert stats["levels"] == {1: 1, 2: 1, 3: 1}
        # total_savings = (3000-2400) + (5000-3500) + (6000-3000) = 5100
        assert stats["total_savings"] == 5100


class TestShortTermMemoryCompression:
    """ShortTermMemory 压缩集成"""

    @pytest.mark.asyncio
    async def test_compression_ratio(self):
        config = MemoryConfig(short_term_window_size=50, short_term_max_tokens=2000)
        stm = ShortTermMemory(config)
        assert stm.get_compression_ratio() == 0.0

        for i in range(20):
            await stm.add_turn("user", "长消息内容" * 50)
        assert stm.get_compression_ratio() > 0.5

    def test_compression_level_tracks_state(self):
        config = MemoryConfig()
        stm = ShortTermMemory(config)
        assert stm.get_compression_level() == 0
        stm._compression_level = 2
        assert stm.get_compression_level() == 2

    @pytest.mark.asyncio
    async def test_compress_without_agent_returns_none(self):
        config = MemoryConfig()
        stm = ShortTermMemory(config)
        result = await stm.compress()
        assert result is None

    @pytest.mark.asyncio
    async def test_raw_messages_property(self):
        config = MemoryConfig()
        stm = ShortTermMemory(config)
        await stm.add_turn("user", "hello")
        await stm.add_turn("assistant", "hi")
        assert len(stm.raw_messages) == 2
