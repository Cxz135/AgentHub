from abc import ABC, abstractmethod
from typing import List, Dict, Any

# 假设 Message 类的定义，实际项目中应从 models.message 导入
# from backend.models.message import Message

class BaseLLM(ABC):
    """
    所有大语言模型客户端的基础抽象类。
    它定义了所有 LLM 实现必须遵守的统一接口。
    """

    @abstractmethod
    async def invoke(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        """
        调用 LLM 的核心方法。

        :param messages: 一个列表，其中每个字典代表一条消息，
                       通常包含 'role' 和 'content' 键。
                       例如: [{'role': 'user', 'content': '你好'}]
        :param kwargs: 其他特定于模型的参数，例如 temperature, max_tokens 等。
        :return: LLM 生成的文本响应。
        """
        pass