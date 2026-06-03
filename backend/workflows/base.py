from abc import ABC, abstractmethod
from langgraph.graph import StateGraph
from typing import Dict
from backend.agents.base_agent import BaseAgent


class BaseWorkflow(ABC):
    """
    工作流插件的抽象基类。
    每个预定义的工作流都应该继承自这个类。
    """

    @property
    @abstractmethod
    def command(self) -> str:
        """
        工作流的触发指令 (例如: '/code')。
        这个指令必须是唯一的。
        """
        pass

    @abstractmethod
    def build_graph(self, agents: Dict[str, BaseAgent]) -> StateGraph:
        """
        构建并返回此工作流的 LangGraph 实例。

        Args:
            agents: 一个包含所有可用 Agent 实例的字典，
                    以便图中的节点可以根据需要调用它们。

        Returns:
            一个已编译的 StateGraph 实例。
        """
        pass