from typing import Dict, Any
from backend.utils.logger import logger
from backend.llm.llm_provider import get_llm

class CodeAnalyzerAgent:
    @staticmethod
    async def analyze(state: Dict[str, Any]) -> Dict[str, Any]:
        """分析代码的结构、复杂度、可维护性等指标"""
        logger.info("--- [CodeAnalyzerAgent] 开始代码静态分析 ---")
        llm = get_llm()
        task_content = state.get("task_content", "")
        logger.info(f"[CodeAnalyzerAgent] 开始处理待分析代码，代码长度：{len(task_content)}字符")
        prompt = f"请分析以下代码的结构、复杂度、可维护性，列出主要问题：\n{task_content}"
        logger.info("[CodeAnalyzerAgent] 已构建分析提示词，调用LLM进行分析")
        response = await llm.invoke(prompt)
        logger.info("✅ [CodeAnalyzerAgent] 代码分析完成，结果已生成")
        return {**state, "code_analysis": response.content.strip()}