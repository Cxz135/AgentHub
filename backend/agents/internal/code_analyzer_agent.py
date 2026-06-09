from typing import Dict, Any
from backend.utils.logger import logger
from backend.llm.llm_provider import get_llm
from backend.config.prompts import get_prompt_loader

class CodeAnalyzerAgent:
    @staticmethod
    async def analyze(state: Dict[str, Any]) -> Dict[str, Any]:
        """分析代码的结构、复杂度、可维护性等指标"""
        logger.info("--- [CodeAnalyzerAgent] 开始代码静态分析 ---")
        llm = get_llm()
        task_content = state.get("task_content", "")
        logger.info(f"[CodeAnalyzerAgent] 开始处理待分析代码，代码长度：{len(task_content)}字符")
        prompt_loader = get_prompt_loader()
        prompt = prompt_loader.get('agent', 'code_analyzer_prompt', task_content=task_content)
        logger.info("[CodeAnalyzerAgent] 已构建分析提示词，调用LLM进行分析")
        response = await llm.invoke(prompt)
        logger.info("✅ [CodeAnalyzerAgent] 代码分析完成，结果已生成")
        if isinstance(response, str):
            content = response.strip()
        else:
            content = response.content.strip()
        return {**state, "code_analysis": content}