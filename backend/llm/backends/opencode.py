"""
OpenCode Zen LLM 后端实现（仅限免费模型）。

OpenCode Zen 是 OpenCode 团队提供的统一模型路由服务，通过
https://opencode.ai/zen/v1 即可访问 7 个免费档模型（DeepSeek / Big Pickle /
Qwen / MiMo / minimax / Nemotron 等）。本后端采用 OpenAI 兼容协议
（/v1/chat/completions），复用 DeepSeekBackend 的实现模板。

注意：出于安全考虑，构造时与请求时双重校验 model_name 是否在免费白名单
FREE_MODELS 内，避免误传付费模型造成计费。
"""

import os
import json
from typing import List, Dict, AsyncGenerator, Optional, Any

import httpx

from backend.llm.backend import LLMBackend
from backend.utils.logger import logger


class OpenCodeBackend(LLMBackend):
    """OpenCode Zen LLM 后端（异步非阻塞，仅支持免费模型）"""

    provider = "opencode"

    FREE_MODELS: frozenset = frozenset({
        "deepseek-v4-flash-free",
        "big-pickle",
        "mimo-v2.5-free",
        "qwen3.6-plus-free",
        "minimax-m3-free",
        "nemotron-3-ultra-free",
        "nemotron-3-super-free",
    })
    DEFAULT_MODEL = "deepseek-v4-flash-free"
    DEFAULT_BASE_URL = "https://opencode.ai/zen/v1/chat/completions"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
    ):
        if model not in self.FREE_MODELS:
            raise ValueError(
                f"OpenCodeBackend 仅支持免费模型，'{model}' 不在白名单内。"
                f"可选免费模型: {sorted(self.FREE_MODELS)}"
            )
        self.model_name = model
        self.api_key = api_key or os.environ.get("OPENCODE_API_KEY") or ""
        if not self.api_key:
            logger.warning("OPENCODE_API_KEY 未设置，OpenCodeBackend 将无法正常工作")
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    def _ensure_free_model(self) -> None:
        if self.model_name not in self.FREE_MODELS:
            raise ValueError(
                f"[OpenCodeBackend] 当前 adapter 仅支持免费模型，"
                f"'{self.model_name}' 不在白名单内。"
                f"可用免费模型: {sorted(self.FREE_MODELS)}"
            )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._client

    def _build_payload(self, messages, temperature, max_tokens, stop, stream=False):
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stop:
            payload["stop"] = stop
        return payload

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        self._ensure_free_model()
        if not self.api_key:
            return "错误: OPENCODE_API_KEY 未配置"
        client = await self._get_client()
        payload = self._build_payload(messages, temperature, max_tokens, stop, stream=False)
        try:
            logger.info(f"[OpenCodeBackend] 请求 model={self.model_name}, messages={len(messages)}条")
            resp = await client.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code != 200:
                error_detail = resp.text[:300]
                logger.error(f"[OpenCodeBackend] API 返回 {resp.status_code}: {error_detail}")
                return f"调用 OpenCode Zen API 失败: {error_detail}"
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content", "")
            logger.info(f"[OpenCodeBackend] 响应成功, 长度={len(content)}字符")
            return content
        except httpx.TimeoutException:
            logger.error("[OpenCodeBackend] 请求超时")
            return "错误: OpenCode Zen API 请求超时"
        except Exception as e:
            logger.error(f"[OpenCodeBackend] 请求异常: {e}")
            return f"错误: {e}"

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        self._ensure_free_model()
        if not self.api_key:
            yield "错误: OPENCODE_API_KEY 未配置"
            return
        client = await self._get_client()
        payload = self._build_payload(messages, temperature, max_tokens, stop, stream=True)
        try:
            async with client.stream(
                "POST",
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except Exception as e:
            logger.error(f"[OpenCodeBackend] 流式异常: {e}")

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def api_key_status(self) -> bool:
        return bool(self.api_key)
