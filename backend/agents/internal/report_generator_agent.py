from typing import Dict, Any
from backend.utils.logger import logger
from backend.llm.llm_provider import get_llm

class ReportGeneratorAgent:
    @staticmethod
    async def generate(state: Dict[str, Any]) -> Dict[str, Any]:
        """整合分析结果和漏洞扫描结果，生成结构化的代码审查报告"""
        logger.info("--- [ReportGeneratorAgent] 开始生成审查报告 ---")
        llm = get_llm()
        # 把所有中间结果拼起来，让LLM生成结构化报告
        context = f"""
代码分析结果：{state.get('code_analysis', {})}
漏洞扫描结果：{state.get('vulnerabilities', [])}
原始代码：{state['task_content']}
"""
        prompt = f"""你是专业的代码审查专家，根据以上信息生成一份markdown格式的代码审查报告，包含：
1. 代码基本信息（语言、行数、函数数）
2. 发现的安全漏洞列表，每个漏洞说明风险等级和修复建议
3. 代码优化建议
请用清晰的标题，格式规范。"""
        response = llm.invoke(context + prompt)
        logger.info("✅ CodeReview工作流执行完成，生成最终审查报告")
        return {**state, "final_answer": response.content.strip()}