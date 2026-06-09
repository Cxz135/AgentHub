from typing import Dict, Any
from backend.utils.logger import logger
from backend.llm.llm_provider import get_llm
from backend.config.prompts import get_prompt_loader

class ReportGeneratorAgent:
    @staticmethod
    async def generate(state: Dict[str, Any]) -> Dict[str, Any]:
        """整合分析结果和漏洞扫描结果，生成结构化的代码审查报告"""
        logger.info("--- [ReportGeneratorAgent] 开始生成审查报告 ---")
        llm = get_llm()
        context = f"""
代码分析结果：{state.get('code_analysis', {})}
漏洞扫描结果：{state.get('vulnerabilities', [])}
原始代码：{state['task_content']}
"""
        prompt_loader = get_prompt_loader()
        prompt = prompt_loader.get('agent', 'report_generator_prompt')
        response = llm.invoke(context + prompt)
        logger.info("✅ CodeReview工作流执行完成，生成最终审查报告")
        if isinstance(response, str):
            content = response.strip()
        else:
            if isinstance(response, str):
                content = response.strip()
            elif hasattr(response, 'content'):
                content = response.content.strip()
            elif hasattr(response, 'final_answer') and hasattr(response.final_answer, 'content'):
                content = response.final_answer.content.strip()
            else:
                content = str(response).strip()
        return {**state, "final_answer": content}