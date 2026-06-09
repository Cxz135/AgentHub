import os
import yaml
from typing import Dict, Any, Optional

class PromptLoader:
    """提示词加载器，从YAML文件加载所有提示词配置"""

    _instance: Optional['PromptLoader'] = None
    _prompts: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_prompts()
        return cls._instance

    def _load_prompts(self):
        """加载所有提示词文件"""
        prompts_dir = os.path.dirname(__file__)

        prompt_files = [
            'orchestrator_prompts.yaml',
            'workflow_prompts.yaml',
            'agent_prompts.yaml',
        ]

        for filename in prompt_files:
            filepath = os.path.join(prompts_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if data:
                        self._prompts.update(data)

    def get(self, category: str, key: str, **kwargs) -> str:
        """
        获取提示词，支持模板变量替换

        Args:
            category: 类别，如 'orchestrator', 'workflow', 'agent'
            key: 键名，如 'simple_chat', 'react_agent'
            **kwargs: 模板变量

        Returns:
            格式化后的提示词
        """
        if category not in self._prompts:
            return f"Error: Unknown category '{category}'"

        data = self._prompts[category]
        if key not in data:
            return f"Error: Unknown key '{key}' in category '{category}'"

        template = data[key]
        if isinstance(template, dict):
            template = template.get('prompt', template.get('system', ''))

        if not template:
            return ""

        if kwargs:
            try:
                return template.format(**kwargs)
            except KeyError as e:
                return template

        return template

    def get_raw(self, category: str, key: str) -> Dict[str, Any]:
        """获取原始提示词配置（不格式化）"""
        if category not in self._prompts:
            return {}
        return self._prompts[category].get(key, {})

    def get_all(self, category: str) -> Dict[str, Any]:
        """获取某个类别的所有提示词"""
        return self._prompts.get(category, {})


def get_prompt_loader() -> PromptLoader:
    """获取PromptLoader单例"""
    return PromptLoader()