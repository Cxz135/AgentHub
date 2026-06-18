"""
记忆衰减器 — Ebbinghaus 遗忘曲线实现。

衰减公式：
  effective = importance × decay_factor

  decay_factor = e^(-λ × days_since_creation) × (1 + ln(1 + access_count) × 0.1)

  λ = DECAY_LAMBDA (默认 0.05/天)
  低于 DECAY_THRESHOLD (0.1) 的记忆被归档（软删除）
"""
from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger("core")

DECAY_LAMBDA = 0.05       # 基础衰减速率（每天）
DECAY_THRESHOLD = 0.1     # 低于此分数的记忆被归档
BOOST_FACTOR = 0.1        # 访问增强因子


class MemoryDecayer:
    """管理记忆的衰减和归档。"""

    def __init__(self, db: Session):
        self.db = db

    def decay(self, user_id: int) -> int:
        """
        对用户的所有活跃记忆执行一次衰减更新。

        使用原始 SQL 以提高效率（单条 UPDATE 而非逐行操作）。

        Returns:
            被归档（软删除）的记忆数量
        """
        try:
            # 更新衰减因子
            self.db.execute(
                text(
                    """
                    UPDATE memory_entries
                    SET decay_factor = (
                        EXP(-:lambda * (julianday('now') - julianday(created_at)))
                        * (1 + LN(1 + COALESCE(access_count, 0)) * :boost)
                    )
                    WHERE user_id = :uid AND is_active = 1
                    """
                ),
                {
                    "lambda": DECAY_LAMBDA,
                    "boost": BOOST_FACTOR,
                    "uid": user_id,
                },
            )

            # 归档有效分数过低的记忆
            result = self.db.execute(
                text(
                    """
                    UPDATE memory_entries
                    SET is_active = 0
                    WHERE user_id = :uid
                      AND is_active = 1
                      AND (importance * decay_factor) < :threshold
                    """
                ),
                {
                    "uid": user_id,
                    "threshold": DECAY_THRESHOLD,
                },
            )

            archived = result.rowcount
            self.db.commit()

            if archived > 0:
                logger.info(f"[MEMORY-DECAY] 归档了 {archived} 条低分记忆 (user_id={user_id})")

            return archived
        except Exception as e:
            logger.warning(f"[MEMORY-DECAY] decay 失败: {e}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return 0

    def boost(self, memory_id: int) -> bool:
        """
        提升单条记忆：增加访问计数，重置衰减因子为 1.0。

        在记忆被检索或用户手动提升时调用。
        """
        try:
            result = self.db.execute(
                text(
                    """
                    UPDATE memory_entries
                    SET access_count = COALESCE(access_count, 0) + 1,
                        decay_factor = 1.0,
                        updated_at = :now
                    WHERE id = :mid
                    """
                ),
                {"mid": memory_id, "now": datetime.utcnow()},
            )
            self.db.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.warning(f"[MEMORY-DECAY] boost 失败: {e}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return False

    @staticmethod
    def compute_effective_score(importance: float, decay_factor: float) -> float:
        """计算有效记忆分数（供外部使用）。"""
        return importance * max(0.0, min(1.0, decay_factor))

    @staticmethod
    def compute_decay_factor(
        created_at: datetime,
        access_count: int = 0,
        reference_time: datetime = None,
    ) -> float:
        """
        计算指定时间点的衰减因子（纯函数，不访问数据库）。
        供测试和预测使用。
        """
        now = reference_time or datetime.utcnow()
        days = (now - created_at).total_seconds() / 86400.0
        raw_decay = math.exp(-DECAY_LAMBDA * days)
        access_boost = 1.0 + math.log(1 + access_count) * BOOST_FACTOR
        return raw_decay * access_boost
