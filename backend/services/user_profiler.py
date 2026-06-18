"""
用户画像构建器 — 从语义记忆中聚合持久化用户模型。

每次提取新记忆后增量更新。
get_summary() 返回的人类可读文本可直接注入 system prompt。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core")

PROFILE_PROMPT = """你是一个用户画像分析师。请根据以下关于用户的最新记忆条目，更新或创建用户画像。

当前已知画像：
{current_profile}

最新记忆：
{new_memories}

请输出 JSON：
{{
  "summary": "一句话概括用户（中文，不超过100字）",
  "traits": [{{"trait": "特征描述", "confidence": 0.9}}],
  "preferences": {{"key": "value"}}
}}

规则：
- summary 应简洁地描述用户的角色、技能、偏好和在做的项目
- traits 列出用户的显著特征（最多 5 条）
- preferences 只记录明确的偏好（如语言、代码风格）
- 如果新记忆没有值得更新画像的信息，返回当前画像不变
"""


class UserProfiler:
    """从语义记忆中构建和维护用户画像。"""

    def __init__(self, llm_backend: Any, db: Any = None):
        self.llm_backend = llm_backend
        self._db = db
        # 内存缓存，避免频繁查库
        self._cache: Dict[int, Dict[str, Any]] = {}

    def get_summary(self, user_id: int) -> str:
        """获取用户画像的人类可读摘要（供注入 system prompt）。"""
        profile = self.get_full_profile(user_id)
        return profile.get("summary", "")

    def get_full_profile(self, user_id: int) -> Dict[str, Any]:
        """获取完整用户画像（JSON）。"""
        # 先查缓存
        if user_id in self._cache:
            return self._cache[user_id]

        # 查数据库
        if self._db:
            try:
                from backend.models.memory import UserProfile as UP
                profile = self._db.query(UP).filter(UP.user_id == user_id).first()
                if profile:
                    result = {
                        "summary": profile.summary_text or "",
                        "traits": profile.traits_json or [],
                        "preferences": profile.preferences_json or {},
                    }
                    self._cache[user_id] = result
                    return result
            except Exception as e:
                logger.warning(f"[PROFILE] 加载画像失败: {e}")

        return {"summary": "", "traits": [], "preferences": {}}

    def load_profile(self, user_id: int) -> Dict[str, Any]:
        """从数据库加载用户画像。"""
        try:
            from backend.models.memory import UserProfile as UP

            profile = self._db.query(UP).filter(UP.user_id == user_id).first()
            if profile:
                return {
                    "summary": profile.summary_text or "",
                    "traits": profile.traits_json or [],
                    "preferences": profile.preferences_json or {},
                }
        except Exception as e:
            logger.warning(f"[PROFILE] load_profile 失败: {e}")
        return {"summary": "", "traits": [], "preferences": {}}

    def save_profile(self, user_id: int, profile: Dict[str, Any]):
        """保存用户画像到数据库。"""
        try:
            from backend.models.memory import UserProfile as UP

            record = self._db.query(UP).filter(UP.user_id == user_id).first()
            if record:
                record.summary_text = profile.get("summary", "")
                record.traits_json = profile.get("traits", [])
                record.preferences_json = profile.get("preferences", {})
            else:
                record = UP(
                    user_id=user_id,
                    summary_text=profile.get("summary", ""),
                    traits_json=profile.get("traits", []),
                    preferences_json=profile.get("preferences", {}),
                )
                self._db.add(record)
            self._db.commit()
            self._cache[user_id] = profile
        except Exception as e:
            logger.warning(f"[PROFILE] save_profile 失败: {e}")
            try:
                self._db.rollback()
            except Exception:
                pass

    async def update(
        self,
        user_id: int,
        new_memories: List[Any],
    ) -> Dict[str, Any]:
        """
        增量更新用户画像。

        只有 preference 和 user_trait 类型的记忆才会触发画像更新。
        """
        relevant = [
            m for m in new_memories
            if hasattr(m, 'memory_type') and m.memory_type in ('preference', 'user_trait')
        ]
        if not relevant:
            return self.get_full_profile(user_id)

        current = self.load_profile(user_id)

        # 构建新记忆文本
        new_text = "\n".join(
            f"- [{m.memory_type}] {m.content}" for m in relevant
        )

        try:
            prompt = PROFILE_PROMPT.format(
                current_profile=json.dumps(current, ensure_ascii=False, indent=2),
                new_memories=new_text,
            )
            response = await self.llm_backend.chat([
                {"role": "user", "content": prompt}
            ])
            text = response.strip() if isinstance(response, str) else str(response).strip()

            # 解析 JSON
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                updated = json.loads(match.group(0))
                if isinstance(updated, dict):
                    profile = {
                        "summary": updated.get("summary", current.get("summary", "")),
                        "traits": updated.get("traits", current.get("traits", [])),
                        "preferences": updated.get("preferences", current.get("preferences", {})),
                    }
                    self.save_profile(user_id, profile)
                    logger.info(f"[PROFILE] 更新用户画像: {profile['summary'][:80]}...")
                    return profile
        except Exception as e:
            logger.warning(f"[PROFILE] update 失败: {e}")

        return current
