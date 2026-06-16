"""
统一 LLM 后端抽象接口。
所有 LLM 平台（Tongyi / DeepSeek / OpenCode 等）都实现此接口。
职责单一：只负责与 LLM API 的通信，不包含任何 Agent 角色逻辑。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, AsyncGenerator, Optional, Any


class LLMBackend(ABC):
    """所有 LLM 后端的统一抽象"""

    provider: str          # "tongyi" / "deepseek" / "opencode"
    model_name: str        # "qwen-plus" / "deepseek-coder" / ...

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs: Any
    ) -> str:
        """
        统一的非流式调用接口。

        Args:
            messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        """
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        """统一的流式调用接口，前端可实现打字机效果。"""
        ...

    def chat_sync(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> str:
        """同步包装器，供 LangChain Tool 等同步上下文调用。"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已有事件循环中运行（如 Jupyter）
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.chat(messages, temperature, max_tokens, **kwargs)
                    )
                    return future.result(timeout=300)
            return loop.run_until_complete(
                self.chat(messages, temperature, max_tokens, **kwargs)
            )
        except RuntimeError:
            return asyncio.run(
                self.chat(messages, temperature, max_tokens, **kwargs)
            )

    def count_tokens(self, text: str) -> int:
        """估算 token 数"""
        return len(text)

    @property
    def api_key_status(self) -> bool:
        """检查 API Key 是否已配置"""
        return True