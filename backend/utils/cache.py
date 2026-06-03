# app/cache.py - 修复后的版本

import hashlib
import json
import time
import numpy as np
from typing import Optional, Dict
from backend.utils.logger import logger
from backend.rag.vector_store import embed_model


class SemanticCache:
    """
    语义缓存：基于向量相似度匹配
    """

    def __init__(self, host='localhost', port=6379, similarity_threshold=0.85):
        self.redis_client = None
        self.similarity_threshold = similarity_threshold
        self.ttl = 3600  # 1小时过期
        self.embed_model = embed_model
        self._connected = False

    def set_client(self, client):
        """设置Redis客户端"""
        self.redis_client = client
        self._connected = client is not None
        if self._connected:
            logger.info("✅ 语义缓存已连接Redis")
        else:
            logger.warning("⚠️ 语义缓存未连接Redis")

    def _get_embedding(self, text: str) -> list:
        """获取文本的向量"""
        try:
            return self.embed_model.embed_query(text)
        except Exception as e:
            logger.error(f"获取embedding失败: {e}")
            return None

    def _cosine_similarity(self, vec1: list, vec2: list) -> float:
        """计算余弦相似度"""
        if vec1 is None or vec2 is None:
            return 0
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

    def _get_cache_key(self, course: str, intent: str = "qa") -> str:
        """生成缓存key"""
        return f"semantic_cache:{course}:{intent}"

    def generate_key(self, query: str, *args, **kwargs) -> str:
        """生成精确缓存key（兼容旧代码）"""
        return f"exact_cache:{hashlib.md5(query.encode()).hexdigest()}"

    def get(self, query=None, course=None, intent="qa", key=None):
        """
        兼容两种调用方式：
        1. 旧方式：cache.get(key=xxx)
        2. 新方式：cache.get(query=xxx, course=xxx, intent=xxx)
        """
        # 方式1：精确匹配
        if key is not None:
            return self._exact_get(key)

        # 方式2：语义匹配
        if query is not None and course is not None:
            return self._semantic_get(query, course, intent)

        return None

    def _exact_get(self, key: str) -> Optional[Dict]:
        """精确匹配获取"""
        if not self._connected or not self.redis_client:
            logger.debug("精确缓存未启用")
            return None

        try:
            cached = self.redis_client.get(key)
            if cached:
                logger.info(f"✅ 精确缓存命中: {key[:50]}...")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"精确缓存读取失败: {e}")
        return None

    def _semantic_get(self, query: str, course: str, intent: str) -> Optional[Dict]:
        """语义匹配获取"""
        if not self._connected or not self.redis_client:
            logger.debug("语义缓存未启用")
            return None

        try:
            cache_key = self._get_cache_key(course, intent)
            logger.debug(f"查询缓存: {cache_key}")

            # 获取该课程的所有缓存向量
            cached_items = self.redis_client.hgetall(cache_key)

            if not cached_items:
                logger.info(f"📭 缓存为空: {cache_key}")
                return None

            logger.info(f"📦 找到 {len(cached_items)} 个缓存项")

            # 计算当前问题的向量
            query_embedding = self._get_embedding(query)
            if query_embedding is None:
                return None

            # 遍历所有缓存，找最相似的
            best_match = None
            best_score = 0

            for cache_id, cached_data in cached_items.items():
                try:
                    cached = json.loads(cached_data)
                    cached_embedding = cached.get("embedding")

                    if cached_embedding:
                        similarity = self._cosine_similarity(query_embedding, cached_embedding)
                        logger.debug(f"  比对: {cached['original_query'][:30]}... 相似度: {similarity:.3f}")

                        if similarity > self.similarity_threshold and similarity > best_score:
                            best_score = similarity
                            best_match = cached
                except Exception as e:
                    logger.warning(f"解析缓存项失败: {e}")
                    continue

            if best_match:
                logger.info(f"✅ 语义缓存命中！相似度: {best_score:.3f}, 原问题: {best_match['original_query'][:50]}...")
                return best_match["response"]
            else:
                logger.info(f"❌ 无缓存命中 (最高相似度: {best_score:.3f} < {self.similarity_threshold})")
                return None

        except Exception as e:
            logger.error(f"语义缓存读取失败: {e}", exc_info=True)
            return None

    def set(self, query=None, value=None, course=None, intent="qa", key=None):
        """
        兼容两种调用方式：
        1. 旧方式：cache.set(key=xxx, value=xxx)
        2. 新方式：cache.set(query=xxx, value=xxx, course=xxx, intent=xxx)
        """
        # 方式1：精确存储
        if key is not None:
            return self._exact_set(key, value)

        # 方式2：语义存储
        if query is not None and value is not None and course is not None:
            return self._semantic_set(query, value, course, intent)

        logger.warning(f"缓存存储参数错误: query={query}, course={course}, intent={intent}")
        return False

    def _exact_set(self, key: str, value: Dict) -> bool:
        """精确存储"""
        if not self._connected or not self.redis_client:
            logger.debug("精确缓存未启用，跳过存储")
            return False

        try:
            self.redis_client.setex(key, self.ttl, json.dumps(value, ensure_ascii=False))
            logger.info(f"💾 精确缓存已存储: {key[:50]}...")
            return True
        except Exception as e:
            logger.error(f"精确缓存存储失败: {e}")
            return False

    def _semantic_set(self, query: str, response: Dict, course: str, intent: str) -> bool:
        """语义存储"""

        if not self._connected or not self.redis_client:
            logger.warning("语义缓存未启用，跳过存储")
            return False
        logger.info(f"🔍 _semantic_set 被调用: query={query[:50]}, course={course}, intent={intent}")
        logger.info(f"   连接状态: _connected={self._connected}, redis_client={self.redis_client is not None}")

        try:
            cache_key = self._get_cache_key(course, intent)
            logger.info(f"💾 存储语义缓存: key={cache_key}, query={query[:50]}...")

            # 生成唯一ID
            query_hash = hashlib.md5(query.encode()).hexdigest()

            # 计算向量
            embedding = self._get_embedding(query)
            if embedding is None:
                logger.warning("无法获取embedding，跳过缓存")
                return False

            # 存储数据
            cache_data = {
                "original_query": query,
                "embedding": embedding,
                "response": response,
                "timestamp": time.time(),
                "course": course,
                "intent": intent
            }

            # 存储到hash中
            result = self.redis_client.hset(cache_key, query_hash, json.dumps(cache_data, ensure_ascii=False))
            self.redis_client.expire(cache_key, self.ttl)

            # 验证是否保存成功
            saved = self.redis_client.hexists(cache_key, query_hash)
            if saved:
                logger.info(f"✅ 语义缓存已存储: {query[:50]}... (hash: {query_hash[:8]})")
            else:
                logger.warning(f"⚠️ 语义缓存保存验证失败: {query[:50]}...")

            return True

        except Exception as e:
            logger.error(f"语义缓存存储失败: {e}", exc_info=True)
            return False

    def clear_course_cache(self, course: str):
        """清空某个课程的所有缓存"""
        if not self._connected or not self.redis_client:
            return

        try:
            cache_key = self._get_cache_key(course, "*")
            keys = self.redis_client.keys(cache_key)
            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"🗑️ 已清空课程【{course}】的语义缓存")
        except Exception as e:
            logger.warning(f"清空缓存失败: {e}")

    def get_all_caches(self, course: str, intent: str = "qa") -> Dict:
        """获取某个课程的所有缓存（用于调试）"""
        if not self._connected or not self.redis_client:
            return {}

        try:
            cache_key = self._get_cache_key(course, intent)
            cached_items = self.redis_client.hgetall(cache_key)
            result = {}
            for key, value in cached_items.items():
                result[key] = json.loads(value)
            return result
        except Exception as e:
            logger.error(f"获取缓存失败: {e}")
            return {}


# 全局实例
cache = SemanticCache()