import os
import requests
import json
import logging

from backend.utils.logger import logger
from dotenv import load_dotenv
load_dotenv()


def web_search(query: str) -> str:
    """
    联网搜索互联网上的最新信息，输入搜索关键词，返回搜索结果的摘要。
    当你需要查询最新资讯、技术文档、实时数据，或者自身知识无法回答的问题时调用这个工具。

    Args:
        query: 搜索关键词，必须是字符串

    Returns:
        搜索结果的文本摘要
    """
    logger.info(f"[web_search] 被调用，query='{query}'")

    api_key = os.getenv("WEBSEARCH_API_KEY")
    if not api_key:
        logger.error("[web_search] ❌ WEBSEARCH_API_KEY 未配置")
        return "错误：未配置 WEBSEARCH_API_KEY"
    else:
        logger.info(f"[web_search] ✅ API_KEY 环境变量已设置，长度: {len(api_key)}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "messages": [{"role": "user", "content": query}],
        "edition": "standard",
        "search_source": "baidu_search_v2",
        "search_recency_filter": "week"
    }

    logger.info(f"[web_search] 请求 URL: https://qianfan.baidubce.com/v2/ai_search/web_search")
    logger.info(f"[web_search] 请求体: {json.dumps(payload, ensure_ascii=False)}")

    try:
        resp = requests.post(
            "https://qianfan.baidubce.com/v2/ai_search/web_search",
            headers=headers,
            json=payload,
            timeout=90
        )
        logger.info(f"[web_search] HTTP 响应状态码: {resp.status_code}")
        logger.info(f"[web_search] HTTP 响应体前300字: {resp.text[:300]}")

        if resp.status_code != 200:
            error_text = resp.text[:500]
            logger.error(f"[web_search] API 返回错误: {error_text}")
            return f"搜索API HTTP {resp.status_code}: {error_text}"

        data = resp.json()
        logger.info(f"[web_search] 响应 JSON 根字段: {list(data.keys())}")

        result = _parse_search_response(data)

        if not result:
            logger.warning("[web_search] API 返回空结果")
            return f"搜索API返回空结果"

        logger.info(f"[web_search] 搜索成功，结果长度: {len(result)}")
        logger.info(f"[web_search] 最终返回内容预览: {result[:200]}")
        return f"🔍 搜索结果（{query}）：\n{result}"

    except requests.Timeout:
        logger.error("[web_search] 请求超时（90秒）")
        return "搜索API请求超时（90秒）"
    except Exception as e:
        logger.error(f"[web_search] 请求异常: {e}", exc_info=True)
        return f"搜索失败: {e}"


def _parse_search_response(data: dict) -> str:
    """解析搜索 API 响应，提取结果文本"""
    result = ""

    results_list = data.get("results", [])
    if results_list:
        parts = []
        for item in results_list[:5]:
            title = item.get("title", "")
            url = item.get("url", "")
            snippet = item.get("snippet", "") or item.get("content", "")
            if snippet:
                parts.append(f"【{title}】{snippet}" + (f"（来源：{url}）" if url else ""))
        result = "\n".join(parts)
        logger.info(f"[web_search] 从 results 数组提取到 {len(results_list)} 条结果")

    if not result:
        references = data.get("references", [])
        if references:
            parts = []
            for item in references[:5]:
                title = item.get("title", "")
                url = item.get("url", "")
                content = item.get("content", "")
                if content:
                    parts.append(f"【{title}】{content}" + (f"（来源：{url}）" if url else ""))
            result = "\n".join(parts)
            logger.info(f"[web_search] 从 references 提取到 {len(references)} 条结果")

    if not result:
        data_results = data.get("data", {}).get("results", [])
        if data_results:
            parts = []
            for item in data_results[:5]:
                title = item.get("title", "")
                url = item.get("url", "")
                snippet = item.get("snippet", "") or item.get("content", "")
                if snippet:
                    parts.append(f"【{title}】{snippet}" + (f"（来源：{url}）" if url else ""))
            result = "\n".join(parts)
            logger.info(f"[web_search] 从 data.results 提取到 {len(data_results)} 条结果")

    if not result:
        result = data.get("result", "") or data.get("content", "")

    if not result:
        choices = data.get("choices", [])
        if choices:
            result = choices[0].get("message", {}).get("content", "")
            logger.info(f"[web_search] 从 choices[0].message.content 提取结果，长度: {len(result)}")

    if not result:
        logger.warning(f"[web_search] 未能解析响应，完整响应: {json.dumps(data, ensure_ascii=False)[:500]}")

    return result