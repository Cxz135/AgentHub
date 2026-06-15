import os
import re
import requests
import json
import logging
from collections import OrderedDict

from backend.utils.logger import logger
from dotenv import load_dotenv
load_dotenv()

# 搜索结果配置
MAX_RESULTS = 5          # 最多返回条数
MAX_SNIPPET_LEN = 300    # 每条摘要最大字符数
MIN_RELEVANCE_SCORE = 1  # 最低相关性分数（低于此值丢弃）


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
    }
    # 仅在查询明确要求最新信息时才加时效过滤
    recency_keywords = ["最新", "今天", "今日", "本周", "最近", "latest", "today", "this week"]
    if any(kw in query for kw in recency_keywords):
        payload["search_recency_filter"] = "week"

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

        raw_items = _parse_search_response_raw(data)
        if not raw_items:
            logger.warning("[web_search] API 返回空结果")
            return "搜索API返回空结果"

        logger.info(f"[web_search] 原始结果数: {len(raw_items)}")

        # 清洗 + 去重 + 相关性排序
        cleaned = _clean_and_rerank(raw_items, query)

        if not cleaned:
            logger.warning("[web_search] 清洗后无有效结果")
            return "搜索API返回空结果"

        # 格式化输出
        result = _format_results(cleaned)
        logger.info(f"[web_search] 搜索成功，清洗后 {len(cleaned)} 条，总长度: {len(result)}")
        logger.info(f"[web_search] 最终返回内容预览: {result[:200]}")
        return f"🔍 搜索结果（{query}）：\n{result}"

    except requests.Timeout:
        logger.error("[web_search] 请求超时（90秒）")
        return "搜索API请求超时（90秒）"
    except Exception as e:
        logger.error(f"[web_search] 请求异常: {e}", exc_info=True)
        return f"搜索失败: {e}"


def _parse_search_response_raw(data: dict) -> list[dict]:
    """解析搜索 API 响应，返回原始条目列表 [{title, url, content, date}]"""
    items = []

    def _extract(item_list, content_key="content"):
        for item in item_list:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            content = (item.get(content_key) or item.get("snippet") or "").strip()
            date = (item.get("date") or "").strip()
            if content:
                items.append({"title": title, "url": url, "content": content, "date": date})

    _extract(data.get("results", []), "content")
    if not items:
        _extract(data.get("references", []), "content")
    if not items:
        _extract(data.get("data", {}).get("results", []), "content")

    if not items and data.get("result"):
        items.append({"title": "", "url": "", "content": str(data["result"]), "date": ""})
    if not items and data.get("choices"):
        items.append({"title": "", "url": "", "content": data["choices"][0].get("message", {}).get("content", ""), "date": ""})

    if not items:
        logger.warning(f"[web_search] 未能解析响应: {json.dumps(data, ensure_ascii=False)[:300]}")

    return items


def _clean_and_rerank(items: list[dict], query: str) -> list[dict]:
    """清洗、去重、相关性排序。"""
    # 1. 清洗每条的 HTML 和噪声
    for item in items:
        item["content"] = _clean_text(item["content"])
        item["title"] = _clean_text(item["title"])

    # 2. 去重（相似度 > 80% 的只保留第一条）
    deduped = _deduplicate(items)

    # 3. 计算相关性分数并排序
    query_terms = _tokenize(query)
    for item in deduped:
        item["score"] = _relevance_score(item, query_terms)

    # 4. 过滤低分结果 + 排序 + 截断
    ranked = [it for it in deduped if it["score"] >= MIN_RELEVANCE_SCORE]
    ranked.sort(key=lambda x: x["score"], reverse=True)

    logger.info(
        f"[web_search] 清洗: {len(items)}→去重{len(deduped)}→"
        f"排序后Top{min(MAX_RESULTS, len(ranked))}，"
        f"分数范围: {[it['score'] for it in ranked[:MAX_RESULTS]]}"
    )
    return ranked[:MAX_RESULTS]


def _format_results(items: list[dict]) -> str:
    """格式化清洗后的结果为紧凑文本。"""
    lines = []
    for i, item in enumerate(items, 1):
        title = item["title"] or "无标题"
        content = item["content"][:MAX_SNIPPET_LEN]
        url = item["url"]
        url_hint = f"（{url}）" if url else ""
        lines.append(f"[{i}] {title}\n{content}\n{url_hint}")
    return "\n\n".join(lines)


# ========== 清洗 Helper 函数 ==========

_HTML_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_ENTITY_RE = re.compile(r"&[a-z]+;")


def _clean_text(text: str) -> str:
    """移除 HTML 标签、实体、多余空白。"""
    text = _HTML_RE.sub(" ", text)
    text = _ENTITY_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _tokenize(text: str) -> set:
    """简单分词：按非字母数字字符拆分，取长度≥2的词。"""
    tokens = re.split(r"[^a-zA-Z0-9一-鿿]+", text.lower())
    return {t for t in tokens if len(t) >= 2}


def _relevance_score(item: dict, query_terms: set) -> int:
    """计算条目与查询的相关性分数。"""
    score = 0
    title_lower = item["title"].lower()
    content_lower = item["content"].lower()

    for term in query_terms:
        if term in title_lower:
            score += 3       # 标题命中权重高
        elif term in content_lower:
            score += 1       # 正文命中权重低

    # 内容长度惩罚：极短内容降分
    if len(item["content"]) < 50:
        score = max(0, score - 2)

    # 如果有有效 URL 加分
    if item.get("url") and item["url"].startswith("http"):
        score += 1

    return score


def _deduplicate(items: list[dict]) -> list[dict]:
    """去重：标题相似度 > 80% 或 URL 相同视为重复。"""
    seen_urls = set()
    result = []
    for item in items:
        url = item.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        # 标题去重
        title = item.get("title", "")
        is_dup = False
        for kept in result:
            if _title_similarity(title, kept.get("title", "")) > 0.8:
                is_dup = True
                break
        if not is_dup:
            result.append(item)
    return result


def _title_similarity(a: str, b: str) -> float:
    """简单 Jaccard 相似度。"""
    if not a or not b:
        return 0.0
    set_a = _tokenize(a)
    set_b = _tokenize(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)