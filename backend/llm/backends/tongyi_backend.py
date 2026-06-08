# backend/llm/tongyi_backend.py
import os
import json
from typing import List, Dict, AsyncGenerator, Optional, Any
import httpx

from backend.llm.backend import LLMBackend
from backend.utils.logger import logger


class TongyiBackend(LLMBackend):
    """通义千问 LLM 后端（异步非阻塞）- 使用 OpenAI 兼容模式"""

    provider = "tongyi"

    def __init__(
        self,
        model: str = "qwen-plus",
        api_key: Optional[str] = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ):
        self.model_name = model
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY") or ""
        if not self.api_key:
            logger.warning("DASHSCOPE_API_KEY 未设置，TongyiBackend 将无法正常工作")
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._client

    def _build_openai_payload(self, messages: List[Dict[str, str]], temperature: float, max_tokens: Optional[int], stop: Optional[List[str]]) -> Dict:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stop:
            payload["stop"] = stop
        return payload

    def _extract_content(self, response_data: Dict) -> str:
        """解析 OpenAI 兼容模式返回的 content"""
        try:
            choices = response_data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return response_data.get("content", "")
        except Exception as e:
            logger.error(f"解析响应内容失败: {e}")
            return ""

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs: Any
    ) -> str:
        if not self.api_key:
            return "错误: DASHSCOPE_API_KEY 未配置"

        client = await self._get_client()
        endpoint = f"{self.base_url}/chat/completions"
        payload = self._build_openai_payload(messages, temperature, max_tokens, stop)

        try:
            resp = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code != 200:
                error_detail = resp.text[:500]
                logger.error(f"[TongyiBackend] API 返回 {resp.status_code}: {error_detail}")
                return f"调用通义千问 API 失败: {error_detail}"
            data = resp.json()
            content = self._extract_content(data)
            logger.info(f"[TongyiBackend] 响应成功, 长度={len(content)}字符")
            return content
        except httpx.TimeoutException:
            logger.error("[TongyiBackend] 请求超时")
            return "错误: 通义千问 API 请求超时"
        except Exception as e:
            logger.error(f"[TongyiBackend] 请求异常: {e}")
            return f"错误: {e}"

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        if not self.api_key:
            yield "错误: DASHSCOPE_API_KEY 未配置"
            return

        client = await self._get_client()
        endpoint = f"{self.base_url}/chat/completions"
        payload = self._build_openai_payload(messages, temperature, max_tokens, stop)
        payload["stream"] = True

        try:
            async with client.stream(
                "POST", endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json=payload,
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    # SSE 格式: data: {...}
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            # OpenAI 流式格式：choices[0].delta.content
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"[TongyiBackend] 流式异常: {e}")

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def api_key_status(self) -> bool:
        return bool(self.api_key)