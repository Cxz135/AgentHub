import os


import pytest
from unittest.mock import patch, mock_open

from backend.agents.custom_agent import CustomAgent
from backend.agents.deepseek_adapter import DeepSeekAdapter
from backend.agents.tongyi_adapter import TongyiAdapter
from backend.core.orchestrator import Orchestrator
from backend.utils.logger import logger
from langgraph.checkpoint.memory import MemorySaver

# 一个模拟的 YAML 文件内容，与我们真实的文件保持一致
# 这使得测试不依赖于磁盘上的真实文件，更加独立和快速
MOCK_YAML_CONTENT = """
- agent_id: "code_reviewer"
  name: "代码审查专家"
  description: "一个专门审查代码质量的 Agent。"
  system_prompt: "你是一个世界级的软件工程师，专长是代码审查。"
  llm_config:
    adapter_id: "deepseek"
    model_name: "deepseek-coder"

- agent_id: "product_manager"
  name: "产品经理"
  description: "一个擅长分析用户需求的 Agent。"
  system_prompt: "你是一位经验丰富的产品经理。"
  llm_config:
    adapter_id: "tongyi"
    model_name: "qwen-long"
"""


@pytest.fixture
def mock_env_vars(monkeypatch):
    """
    一个 Pytest fixture，用于临时设置环境变量。
    我们的适配器在初始化时会检查 API keys。
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_deepseek_key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test_tongyi_key")


# 我们 patch `open` 的范围被精确限制在 orchestrator 模块，以避免对其他库造成副作用。
@patch('backends.core.orchestrator.AsyncSqliteSaver.from_conn_string', return_value=MemorySaver())
@patch('backends.core.orchestrator.open', new_callable=mock_open, read_data=MOCK_YAML_CONTENT)
def test_custom_agent_loading(mock_open_file, mock_sqlite_saver, mock_env_vars):
    """
    一个完整的集成测试，用于验证 Orchestrator 的自定义 Agent 加载逻辑。
    它使用了 mock_open 来模拟 `custom_agents.yaml` 文件的读取，
    并 patch 了 AsyncSqliteSaver 以使用内存 checkpointer，
    使得测试完全在内存中进行，无需真实的磁盘文件或数据库。
    """
    # 初始化 Orchestrator。在初始化过程中，它会尝试读取 YAML 并加载 Agents。
    orchestrator = Orchestrator()

    # 1. 验证自定义 Agent 是否被成功加载
    assert "code_reviewer" in orchestrator.agents
    assert "product_manager" in orchestrator.agents
    
    # 2. 验证内部默认 Agent 也仍然存在
    assert "planner" in orchestrator.agents
    assert "summarizer" in orchestrator.agents
    
    # 3. 验证加载的 Agent 类型是否正确
    code_reviewer_agent = orchestrator.agents["code_reviewer"]
    product_manager_agent = orchestrator.agents["product_manager"]
    
    assert isinstance(code_reviewer_agent, CustomAgent)
    assert isinstance(product_manager_agent, CustomAgent)

    # 4. 验证 System Prompt 是否被正确配置
    assert code_reviewer_agent.system_prompt == "你是一个世界级的软件工程师，专长是代码审查。"
    assert product_manager_agent.system_prompt == "你是一位经验丰富的产品经理。"

    # 5. 验证底层的 LLM Adapter 是否被正确创建和注入
    assert isinstance(code_reviewer_agent.llm_adapter, DeepSeekAdapter)
    assert code_reviewer_agent.llm_adapter.model_name == "deepseek-coder"
    
    assert isinstance(product_manager_agent.llm_adapter, TongyiAdapter)
    assert product_manager_agent.llm_adapter.model_name == "qwen-long"

    # 6. 验证 mock_open 被正确调用
    mock_open_file.assert_called_once()
    
    logger.info("自定义 Agent 加载测试成功通过！")