from langgraph.graph import StateGraph, END
from backend.core.graph_state import GraphState
from backend.agents.internal.code_analyzer_agent import CodeAnalyzerAgent
from backend.agents.internal.vulnerability_scanner_agent import VulnerabilityScannerAgent
from backend.agents.internal.report_generator_agent import ReportGeneratorAgent

class CodeReviewWorkflow:
    """固定的代码审查工作流：/review 命令触发，竞赛里的代码题直接用"""
    @staticmethod
    def build() -> StateGraph:
        workflow = StateGraph(GraphState)
        # 节点1：代码静态分析
        workflow.add_node("analyze_code", CodeAnalyzerAgent.analyze)
        # 节点2：漏洞扫描
        workflow.add_node("scan_vulnerabilities", VulnerabilityScannerAgent.scan)
        # 节点3：生成审查报告
        workflow.add_node("generate_report", ReportGeneratorAgent.generate)
        # 固定流程：分析→扫描→生成报告
        workflow.add_edge("analyze_code", "scan_vulnerabilities")
        workflow.add_edge("scan_vulnerabilities", "generate_report")
        workflow.add_edge("generate_report", END)
        # 入口节点
        workflow.set_entry_point("analyze_code")
        return workflow.compile()