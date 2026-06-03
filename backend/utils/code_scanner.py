import re
from typing import List, Dict, Any
from backend.utils.logger import logger

# 常见的Python代码漏洞模式
VULNERABILITY_PATTERNS = [
    {
        "name": "硬编码密钥",
        "pattern": r'api_key|secret|password|token\s*=\s*["\'][A-Za-z0-9]{20,}["\']',
        "risk": "high",
        "suggestion": "不要在代码中硬编码密钥，使用环境变量管理敏感信息"
    },
    {
        "name": "SQL注入风险",
        "pattern": r'execute\(.*\+.*\)|cursor\.execute\(.*f["\']',
        "risk": "critical",
        "suggestion": "使用参数化查询，避免拼接SQL语句"
    },
    {
        "name": "eval函数风险",
        "pattern": r'eval\(.*\)',
        "risk": "critical",
        "suggestion": "避免使用eval执行动态代码，存在RCE风险"
    },
    {
        "name": "命令注入风险",
        "pattern": r'os\.system\(.*\)|subprocess\.call\(.*shell=True',
        "risk": "high",
        "suggestion": "避免使用shell=True，过滤所有用户输入"
    }
]

def scan_vulnerabilities(code: str) -> List[Dict[str, Any]]:
    """代码漏洞扫描工具类，静态扫描Python代码的安全问题"""
    vulnerabilities = []
    lines = code.splitlines()
    for line_num, line in enumerate(lines, 1):
        for vuln in VULNERABILITY_PATTERNS:
            if re.search(vuln["pattern"], line, re.IGNORECASE):
                vulnerabilities.append({
                    "name": vuln["name"],
                    "risk": vuln["risk"],
                    "line": line_num,
                    "code_snippet": line.strip(),
                    "suggestion": vuln["suggestion"]
                })
    logger.info(f"✅ 代码漏洞扫描完成，发现{len(vulnerabilities)}个问题")
    return vulnerabilities