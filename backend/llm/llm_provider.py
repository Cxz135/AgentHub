import json
import logging
from typing import List, Dict, Any
import os
import asyncio
import dashscope
from dotenv import load_dotenv

from backend.llm.base_llm import BaseLLM

logger = logging.getLogger(__name__)


class TongyiLLM(BaseLLM):
    """
    一个使用通义千问 API 的真实 LLM 客户端。
    """
    def __init__(self, model: str = "qwen-plus"):
        load_dotenv()
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")
        dashscope.api_key = self.api_key
        self.model = model
        logger.info(f"TongyiLLM 初始化完成，使用模型: {self.model}")

    async def invoke(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        """
        异步调用通义千问模型并返回文本响应。
        通过将同步的 SDK 调用包装在 to_thread 中，以非阻塞的方式执行。
        """
        logger.info(f"TongyiLLM 正在准备调用 API，模型: {self.model}")

        def sync_call():
            logger.debug("进入后台线程执行同步的 dashscope.Generation.call...")
            response = dashscope.Generation.call(
                model=self.model,
                messages=messages,
                result_format='message',
                **kwargs
            )
            if response.status_code == 200:
                content = response.output.choices[0].message.content
                logger.info("后台线程成功收到 API 响应。")
                return content or ""
            else:
                logger.error(f"调用通义千问 API 失败: {response.code} - {response.message}")
                return f"调用 LLM 失败: {response.message}"

        try:
            # 在一个单独的线程中运行同步的 blocking 函数，以避免阻塞 asyncio 事件循环
            content = await asyncio.to_thread(sync_call)
            logger.debug(f"异步 invoke 方法成功获取到后台线程的结果。")
            return content
        except Exception as e:
            #logger.opt(exception=True).error("执行 to_thread(sync_call) 时发生未知异常。")
            return f"调用 LLM 时发生异常: {e}"


def get_llm() -> BaseLLM:
    """
    LLM 工厂函数。
    现在它返回一个真实的通义千问 LLM 实例。
    """
    # 将 PlannerAgent 的大脑从“玩具”换成“真家伙”
    logger.info("LLM 工厂: 创建并返回真实的 TongyiLLM 实例。")
    return TongyiLLM(model="qwen-plus")