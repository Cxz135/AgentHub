"""
DeepSeek LLM 后端实现。兼容 OpenAI API 格式，使用 httpx 异步调用。
"""

import os
import json
from typing import List, Dict, AsyncGenerator, Optional, Any

import httpx

from backend.llm.backend import LLMBackend
from backend.utils.logger import logger


class DeepSeekBackend(LLMBackend):
    """DeepSeek LLM 后端（异步非阻塞）"""

    provider = "deepseek"

    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1/chat/completions",
    ):
        self.model_name = model
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or ""
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 未设置，DeepSeekBackend 将无法正常工作")
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0),
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

    async def chat(self, messages, temperature=0.7, max_tokens=None, stop=None, **kwargs):
        if not self.api_key:
            return "错误: DEEPSEEK_API_KEY 未配置"
        client = await self._get_client()
        payload = self._build_payload(messages, temperature, max_tokens, stop, stream=False)
        try:
            logger.info(f"[DeepSeekBackend] 请求 model={self.model_name}, messages={len(messages)}条")
            resp = await client.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code != 200:
                return f"调用 DeepSeek API 失败: {resp.text[:300]}"
            content = resp.json()["choices"][0]["message"]["content"]
            logger.info(f"[DeepSeekBackend] 响应成功, 长度={len(content)}字符")
            return content
        except httpx.TimeoutException:
            return "错误: DeepSeek API 请求超时"
        except Exception as e:
            return f"错误: {e}"

    async def chat_stream(self, messages, temperature=0.7, max_tokens=None, stop=None, **kwargs):
        if not self.api_key:
            yield "错误: DEEPSEEK_API_KEY 未配置"
            return
        client = await self._get_client()
        payload = self._build_payload(messages, temperature, max_tokens, stop, stream=True)
        try:
            async with client.stream("POST", self.base_url,
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
            logger.error(f"[DeepSeekBackend] 流式异常: {e}")

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def api_key_status(self) -> bool:
        return bool(self.api_key)