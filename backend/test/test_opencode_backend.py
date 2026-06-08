"""
OpenCodeBackend 单元测试。

80% 的测试不需要真实 API key（仅校验白名单/契约/默认值），CI 友好。
网络测试默认 skip，只有当设置了 OPENCODE_API_KEY 时才执行。
"""

import os
import asyncio
import pytest

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from backend.llm.backends.opencode import OpenCodeBackend

FREE_MODELS = OpenCodeBackend.FREE_MODELS


# === 不需要 API key 的白名单/契约测试 ===

def test_free_models_whitelist_not_empty():
    assert len(FREE_MODELS) >= 1
    assert "deepseek-v4-flash-free" in FREE_MODELS
    assert "big-pickle" in FREE_MODELS
    assert "qwen3.6-plus-free" in FREE_MODELS


def test_constructor_rejects_paid_model():
    """构造时传付费模型，必须抛 ValueError（fail-fast）"""
    with pytest.raises(ValueError, match="仅支持免费模型"):
        OpenCodeBackend(model="claude-sonnet-4-5")
    with pytest.raises(ValueError, match="仅支持免费模型"):
        OpenCodeBackend(model="gpt-5.1-codex")
    with pytest.raises(ValueError, match="仅支持免费模型"):
        OpenCodeBackend(model="gpt-5")
    with pytest.raises(ValueError, match="仅支持免费模型"):
        OpenCodeBackend(model="random-nonexistent-model")


def test_constructor_accepts_all_free_models():
    """白名单内每个模型都应能成功构造（不需要真实 key）"""
    for model in FREE_MODELS:
        b = OpenCodeBackend(model=model, api_key="dummy-key-for-test")
        assert b.model_name == model
        assert b.provider == "opencode"
        assert b.api_key_status is True


def test_default_model_is_free():
    """无参构造应使用默认免费模型 deepseek-v4-flash-free"""
    b = OpenCodeBackend(api_key="dummy-key-for-test")
    assert b.model_name == "deepseek-v4-flash-free"


def test_default_model_constant_matches():
    """DEFAULT_MODEL 必须是白名单内的一员"""
    assert OpenCodeBackend.DEFAULT_MODEL in OpenCodeBackend.FREE_MODELS


def test_api_key_status():
    b = OpenCodeBackend(model="deepseek-v4-flash-free", api_key="dummy")
    assert b.api_key_status is True
    b2 = OpenCodeBackend(model="deepseek-v4-flash-free", api_key="explicit-empty")
    # 当显式传入非空字符串时仍按传入值判断（除非构造时 os.environ 兜底）
    assert isinstance(b2.api_key_status, bool)


def test_base_url_default():
    b = OpenCodeBackend(api_key="dummy")
    assert b.base_url == "https://opencode.ai/zen/v1/chat/completions"


def test_request_time_rejects_paid_model():
    """即便绕过构造函数直接修改 model_name，请求时也应被白名单拦截"""
    b = OpenCodeBackend(api_key="dummy")
    b.model_name = "claude-opus-4-5"
    import asyncio
    with pytest.raises(ValueError, match="仅支持免费模型"):
        asyncio.run(b.chat([{"role": "user", "content": "hi"}]))


# === 需要真实 API key 的网络测试（默认 skip） ===

def _has_real_key() -> bool:
    key = os.environ.get("OPENCODE_API_KEY", "")
    return bool(key) and not key.startswith("sk-dummy")


@pytest.mark.skipif(not _has_real_key(), reason="OPENCODE_API_KEY 未设置或为占位符")
def test_chat_real():
    backend = OpenCodeBackend(model="deepseek-v4-flash-free")
    resp = asyncio.run(backend.chat([{"role": "user", "content": "用一句话说 hello"}]))
    assert isinstance(resp, str) and len(resp) > 0


@pytest.mark.skipif(not _has_real_key(), reason="OPENCODE_API_KEY 未设置或为占位符")
def test_chat_stream_real():
    backend = OpenCodeBackend(model="big-pickle")
    chunks = []
    async def collect():
        async for c in backend.chat_stream([{"role": "user", "content": "say hi"}]):
            chunks.append(c)
    asyncio.run(collect())
    assert len(chunks) > 0
    assert "".join(chunks)


# === Orchestrator 集成测试（验证注册链路） ===

def test_orchestrator_registers_opencode_backend(monkeypatch):
    """验证 Orchestrator._setup_backends 成功注册 opencode 后端"""
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    from backend.core.orchestrator import Orchestrator
    orch = Orchestrator()
    try:
        assert "opencode" in orch.llm_backends
        backend = orch.get_backend("opencode")
        assert backend.provider == "opencode"
        assert backend.model_name == "deepseek-v4-flash-free"
    finally:
        import asyncio
        # 关闭所有后端的 httpx 客户端
        for b in orch.llm_backends.values():
            try:
                asyncio.run(b.close())
            except Exception:
                pass
