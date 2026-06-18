"""
MemoryManager — 统一记忆编排器

编排 5 层记忆：Instruction → ShortTerm → Working → Summary → LongTerm

使用流程:
    manager = MemoryManager(config)
    ctx = await manager.gather_context(query, user_id, agent_id)
    # ... LLM 调用 ...
    await manager.consolidate(messages, response, user_id, conversation_id)

新增能力（v2）:
    - CRUD 便捷方法: list_entries / get_entry / update_entry / delete_entry / boost_entry / search_entries
    - 版本控制: checkpoint / restore
    - 写入过滤: MemoryWriteGuard 集成
    - 生命周期: get_stats / run_maintenance
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.memory.base import (
    BaseMemory, MemoryEntry, MemoryContext, MemoryConfig,
    MemoryType, MemoryLifecycleStage, GuardResult,
)
from backend.memory.instruction_memory import InstructionMemory
from backend.memory.short_term_memory import ShortTermMemory
from backend.memory.working_memory import WorkingMemory
from backend.memory.summary_memory import SummaryMemory
from backend.memory.long_term_memory import LongTermMemory
from backend.memory.write_guard import MemoryWriteGuard
from backend.memory.lifecycle import LifecycleManager
from backend.memory.session_agent import SessionMemoryAgent

logger = logging.getLogger("core")


@dataclass
class MemoryStats:
    """各层记忆统计。"""
    instruction_count: int = 0
    short_term_count: int = 0
    working_count: int = 0
    summary_count: int = 0
    long_term_count: int = 0

    write_guard_enabled: bool = False
    write_guard_blocked: int = 0      # 累计拦截数
    write_guard_passed: int = 0       # 累计放行数

    lifecycle_stats: dict = field(default_factory=dict)

    checkpoints: int = 0              # 可用快照数

    # 压缩统计
    compression_enabled: bool = False
    compression_level: int = 0         # 当前压缩级别
    compression_count: int = 0         # 累计压缩次数
    compression_savings: int = 0       # 累计节省 token

    def to_dict(self) -> dict:
        return {
            "layers": {
                "instruction": self.instruction_count,
                "short_term": self.short_term_count,
                "working": self.working_count,
                "summary": self.summary_count,
                "long_term": self.long_term_count,
            },
            "write_guard": {
                "enabled": self.write_guard_enabled,
                "blocked": self.write_guard_blocked,
                "passed": self.write_guard_passed,
            },
            "lifecycle": self.lifecycle_stats,
            "checkpoints": self.checkpoints,
            "compression": {
                "enabled": self.compression_enabled,
                "level": self.compression_level,
                "count": self.compression_count,
                "savings": self.compression_savings,
            },
        }


class MemoryManager:
    """
    统一记忆编排器。

    属性：
        instruction   → InstructionMemory
        short_term    → ShortTermMemory
        working       → WorkingMemory
        summary       → SummaryMemory
        long_term     → LongTermMemory

    核心方法：
        gather_context()  → 对话前收集各层记忆
        consolidate()     → 对话后持久化新记忆
    """

    def __init__(self, config: MemoryConfig = None):
        self.config = config or MemoryConfig()

        # 初始化 5 层记忆
        self.instruction = InstructionMemory(self.config)
        self.short_term = ShortTermMemory(self.config)
        self.working = WorkingMemory(self.config)
        self.summary = SummaryMemory(self.config)
        self.long_term = LongTermMemory(self.config)

        # ── 新增：WriteGuard ──
        self._write_guard = MemoryWriteGuard(
            enabled=self.config.write_guard_enabled,
            strict_mode=self.config.classification_strict_mode,
        )

        # ── 新增：生命周期管理器 ──
        self._lifecycle = LifecycleManager()

        # ── 新增：Session 压缩代理 ──
        self._session_agent: Optional[SessionMemoryAgent] = None
        if self.config.session_compression_enabled and self.config.llm_backend:
            self._session_agent = SessionMemoryAgent(
                llm_backend=self.config.llm_backend,
                thresholds=self.config.session_compression_thresholds,
                max_tokens=self.config.session_compression_max_tokens,
                enabled=True,
            )
            # 注入到 ShortTermMemory
            self.short_term.set_session_agent(self._session_agent)

        # ── 新增：版本控制 ──
        self._checkpoints: Dict[str, Dict[str, Any]] = {}
        self._max_checkpoints = 10  # 最多保留 10 个版本

        # ── 统计 ──
        self._wg_blocked = 0
        self._wg_passed = 0

        # 各层开关
        self._enabled_layers: Dict[str, bool] = {
            "instruction": True,
            "short_term": True,
            "working": self.config.working_enabled,
            "summary": self.config.summary_enabled,
            "long_term": self.config.long_term_semantic_enabled
                         or self.config.long_term_extraction_enabled,
        }

        logger.info(
            f"[MEM-MGR] MemoryManager 初始化完成, "
            f"enabled={[k for k, v in self._enabled_layers.items() if v]}, "
            f"write_guard={self.config.write_guard_enabled}, "
            f"session_compression={self._session_agent is not None}"
        )

    # ── 核心方法 ──

    async def gather_context(
        self,
        query: str,
        user_id: int,
        agent_id: str = None,
    ) -> MemoryContext:
        """
        对话前：从各层记忆收集上下文。

        优先级顺序：
        1. instruction  → 系统指令
        2. short_term   → 裁剪后的消息列表
        3. working      → 当前任务状态（如果有）
        4. long_term    → 语义检索 + 用户画像
        5. summary      → 历史对话摘要
        """
        ctx = MemoryContext()

        # 1. 系统指令
        if self._enabled("instruction"):
            scopes = self.config.instruction_scopes.copy()
            if agent_id:
                scopes.append(f"agent:{agent_id}")
            ctx.instructions = await self.instruction.get_active_instructions(scopes)

        # 2. 短期记忆
        if self._enabled("short_term"):
            ctx.short_term_messages = await self.short_term.get_context_messages()

        # 3. 工作记忆
        if self._enabled("working"):
            state = await self.working.get_task_state()
            if state.get("task"):
                ctx.working_state = state

        # 4. 长期记忆（语义检索 + 用户画像）
        if self._enabled("long_term") and query:
            try:
                memories = await self.long_term.semantic_search(query, user_id)
                ctx.long_term_memories = memories
            except Exception as e:
                logger.warning(f"[MEM-MGR] long_term 检索失败: {e}")

            try:
                ctx.user_profile = await self.long_term.get_user_profile_text(user_id)
            except Exception as e:
                logger.warning(f"[MEM-MGR] user_profile 获取失败: {e}")

        # 5. 摘要记忆 + 压缩上下文
        if self._enabled("summary"):
            base_summary = await self.summary.get_context_text()
            compression_ctx = self.get_compression_context()
            # 合并：压缩上下文在前（更全局），轮次摘要在后
            parts = []
            if compression_ctx:
                parts.append(compression_ctx)
            if base_summary:
                parts.append(base_summary)
            ctx.summary_context = "\n\n".join(parts)

        logger.info(
            f"[MEM-MGR] gather_context: instructions={len(ctx.instructions)}ch, "
            f"messages={len(ctx.short_term_messages)}, "
            f"ltm={len(ctx.long_term_memories)}, "
            f"profile={len(ctx.user_profile)}ch"
        )
        return ctx

    async def consolidate(
        self,
        messages: List[dict],
        response: str,
        user_id: int,
        conversation_id: int,
        agent_id: str = None,
    ) -> None:
        """
        对话后：持久化新记忆 + 渐进压缩。

        1. short_term 添加 user+assistant 轮次
        2. 渐进压缩检查（SessionMemoryAgent）
        3. long_term 异步提取事实
        4. summary 更新轮次摘要
        5. working 如果任务完成，归档
        """
        # 1. 短期记忆
        if self._enabled("short_term"):
            await self.short_term.add_turn("assistant", response)

        # 2. 渐进压缩（后台 fire-and-forget）
        if self._session_agent and self._enabled("short_term"):
            try:
                asyncio.create_task(self._compress_async())
            except Exception as e:
                logger.warning(f"[MEM-MGR] 压缩检查启动失败: {e}")

        # 3. 长期记忆（fire-and-forget 提取事实）
        if self._enabled("long_term") and self.config.long_term_extraction_enabled:
            all_msgs = list(messages) + [{"role": "assistant", "content": response}]
            try:
                asyncio.create_task(
                    self.long_term.extract_and_store(
                        messages=all_msgs[-8:],
                        user_id=user_id,
                        conversation_id=conversation_id,
                        agent_id=agent_id or "assistant",
                    )
                )
            except Exception as e:
                logger.warning(f"[MEM-MGR] long_term extract 启动失败: {e}")

        # 4. 摘要记忆
        if self._enabled("summary"):
            all_msgs = list(messages) + [{"role": "assistant", "content": response}]
            await self.summary.add_turn_summary(all_msgs[-4:], conversation_id)

        # 5. 工作记忆归档
        if self._enabled("working"):
            complete = await self.working.is_task_complete()
            if complete:
                archived = await self.working.finish_task(archive=True)
                if archived and self._enabled("long_term"):
                    # 将任务结果作为长期记忆
                    await self.long_term.store(MemoryEntry(
                        content=f"完成任务: {archived.get('description', '')}",
                        memory_type="fact",
                        importance=0.7,
                        metadata={"task_id": archived.get("task_id", "")},
                    ))

    # ── CRUD 便捷方法 ──

    async def list_entries(
        self,
        user_id: int = None,
        memory_type: str = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        分页列出长期记忆条目。

        Args:
            user_id: 可选用户过滤
            memory_type: 可选类型过滤（支持新四分类和旧类型）
            page: 页码（从 1 开始）
            page_size: 每页数量
        """
        db = self.config.db_session
        if not db:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        from backend.models.memory import MemoryEntry as ME

        query = db.query(ME).filter(ME.is_active == True)

        if user_id is not None:
            query = query.filter(ME.user_id == user_id)

        if memory_type:
            # 兼容旧类型查询：fact → project, preference → user 等
            legacy_map = {"fact": "project", "decision": "project",
                          "preference": "user", "user_trait": "user"}
            normalized = legacy_map.get(memory_type, memory_type)
            query = query.filter(ME.memory_type == normalized)

        total = query.count()
        items = query.order_by(ME.updated_at.desc()) \
            .offset((page - 1) * page_size) \
            .limit(page_size) \
            .all()

        return {
            "items": [
                {
                    "id": e.id,
                    "content": e.content,
                    "memory_type": e.memory_type,
                    "importance": e.importance,
                    "confidence": e.confidence,
                    "access_count": e.access_count,
                    "meta_data": e.meta_data,
                    "created_at": str(e.created_at) if e.created_at else None,
                    "updated_at": str(e.updated_at) if e.updated_at else None,
                }
                for e in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """获取单条长期记忆。"""
        db = self.config.db_session
        if not db:
            return None

        from backend.models.memory import MemoryEntry as ME

        entry = db.query(ME).filter(ME.id == entry_id).first()
        if not entry:
            return None

        # 记录访问
        self._lifecycle.track_access(str(entry_id))

        return {
            "id": entry.id,
            "user_id": entry.user_id,
            "content": entry.content,
            "memory_type": entry.memory_type,
            "importance": entry.importance,
            "confidence": entry.confidence,
            "access_count": entry.access_count,
            "meta_data": entry.meta_data,
            "created_at": str(entry.created_at) if entry.created_at else None,
            "updated_at": str(entry.updated_at) if entry.updated_at else None,
        }

    async def update_entry(self, entry_id: int, updates: Dict[str, Any]) -> bool:
        """更新长期记忆条目。"""
        db = self.config.db_session
        if not db:
            return False

        from backend.models.memory import MemoryEntry as ME

        entry = db.query(ME).filter(ME.id == entry_id).first()
        if not entry:
            return False

        allowed_fields = {"content", "importance", "confidence", "meta_data", "is_active"}
        for key, value in updates.items():
            if key in allowed_fields:
                setattr(entry, key, value)

        db.commit()
        logger.info(f"[MEM-MGR] 更新记忆 entry_id={entry_id}")
        return True

    async def delete_entry(self, entry_id: int) -> bool:
        """软删除长期记忆条目。"""
        db = self.config.db_session
        if not db:
            return False

        from backend.models.memory import MemoryEntry as ME

        entry = db.query(ME).filter(ME.id == entry_id).first()
        if not entry:
            return False

        entry.is_active = False
        db.commit()
        logger.info(f"[MEM-MGR] 软删除记忆 entry_id={entry_id}")
        return True

    async def boost_entry(self, entry_id: int) -> bool:
        """提升记忆重要性到 1.0。"""
        return await self.update_entry(entry_id, {"importance": 1.0})

    async def search_entries(
        self,
        query: str,
        user_id: int = None,
        top_k: int = None,
        memory_type: str = None,
    ) -> List[Dict[str, Any]]:
        """
        语义搜索长期记忆。

        如果 LongTermMemory 已初始化（有 embed_model），使用向量检索；
        否则回退到 SQL LIKE 模糊匹配。
        """
        self.long_term._ensure_init()

        if self.long_term._retriever and self.config.long_term_semantic_enabled:
            results = await self.long_term.semantic_search(
                query=query,
                user_id=user_id or 0,
                top_k=top_k or self.config.long_term_retrieval_top_k,
                memory_type=memory_type,
            )
            # 记录访问
            for r in results:
                if r.entry_id:
                    self._lifecycle.track_access(r.entry_id)
            return [r.to_dict() for r in results]

        # 回退：SQL 模糊搜索
        db = self.config.db_session
        if not db:
            return []

        from backend.models.memory import MemoryEntry as ME

        q = db.query(ME).filter(
            ME.is_active == True,
            ME.content.contains(query),
        )
        if user_id is not None:
            q = q.filter(ME.user_id == user_id)

        results = q.order_by(ME.importance.desc()).limit(top_k or 5).all()
        return [
            {
                "id": e.id,
                "content": e.content,
                "memory_type": e.memory_type,
                "importance": e.importance,
                "confidence": e.confidence,
            }
            for e in results
        ]

    # ── 版本控制 ──

    async def checkpoint(self) -> str:
        """
        创建记忆状态快照。

        Returns:
            checkpoint_id
        """
        cid = f"cp_{int(time.time() * 1000)}"
        snapshot = {
            "checkpoint_id": cid,
            "timestamp": time.time(),
            "instruction_scopes": copy.deepcopy(self.instruction._scopes),
            "short_term_messages": copy.deepcopy(self.short_term._messages),
            "working_state": await self.working.get_task_state(),
            "summary_turns": copy.deepcopy(self.summary._turns[-20:]),
            "summary_segments": copy.deepcopy(self.summary._segments[-5:]),
        }
        self._checkpoints[cid] = snapshot

        # 限制快照数量
        if len(self._checkpoints) > self._max_checkpoints:
            oldest = sorted(self._checkpoints.keys())[0]
            del self._checkpoints[oldest]

        logger.info(f"[MEM-MGR] 创建快照: {cid}")
        return cid

    async def restore(self, checkpoint_id: str) -> bool:
        """
        回滚到指定快照。

        Args:
            checkpoint_id: checkpoint() 返回的快照 ID

        Returns:
            True 表示回滚成功
        """
        snapshot = self._checkpoints.get(checkpoint_id)
        if not snapshot:
            logger.warning(f"[MEM-MGR] 快照不存在: {checkpoint_id}")
            return False

        # 恢复各层状态
        self.instruction._scopes = copy.deepcopy(snapshot["instruction_scopes"])
        self.short_term._messages = copy.deepcopy(snapshot["short_term_messages"])

        # 恢复 working 状态
        await self.working.clear()
        if snapshot["working_state"].get("task"):
            task = snapshot["working_state"]["task"]
            await self.working.set_task(task.get("description", ""), task.get("plan"))
            for sid, step in snapshot["working_state"].get("steps", {}).items():
                await self.working.update_step(sid, step.get("status", "done"), step.get("result"))

        # 恢复 summary
        self.summary._turns = copy.deepcopy(snapshot.get("summary_turns", []))
        self.summary._segments = copy.deepcopy(snapshot.get("summary_segments", []))

        logger.info(f"[MEM-MGR] 回滚到快照: {checkpoint_id}")
        return True

    async def list_checkpoints(self) -> List[Dict[str, Any]]:
        """列出所有可用快照。"""
        return [
            {"checkpoint_id": cid, "timestamp": cp["timestamp"]}
            for cid, cp in sorted(
                self._checkpoints.items(),
                key=lambda x: x[1]["timestamp"],
                reverse=True,
            )
        ]

    # ── 生命周期 & 统计 ──

    async def get_stats(self, user_id: int = None) -> MemoryStats:
        """获取各层记忆统计。"""
        stats = MemoryStats(
            instruction_count=self.instruction.count(),
            short_term_count=self.short_term.count(),
            working_count=self.working.count(),
            summary_count=self.summary.count(),
            long_term_count=self.long_term.count(),
            write_guard_enabled=self.config.write_guard_enabled,
            write_guard_blocked=self._wg_blocked,
            write_guard_passed=self._wg_passed,
            checkpoints=len(self._checkpoints),
            compression_enabled=self._session_agent is not None,
            compression_level=self.short_term.get_compression_level(),
        )

        # 压缩统计
        if self._session_agent:
            ss = self._session_agent.get_session_summary()
            stats.compression_count = ss.total_compressions
            stats.compression_savings = ss.compression_savings

        # 生命周期统计（仅长期记忆）
        if user_id is not None and self.config.db_session:
            db = self.config.db_session
            from backend.models.memory import MemoryEntry as ME

            entries = db.query(ME).filter(ME.user_id == user_id, ME.is_active == True).all()
            lifecycle_entries = [
                {
                    "entry_id": str(e.id),
                    "lifecycle_stage": e.meta_data.get("lifecycle_stage", "active") if e.meta_data else "active",
                    "importance": e.importance,
                    "timestamp": e.created_at.timestamp() if e.created_at else time.time(),
                }
                for e in entries
            ]
            stats.lifecycle_stats = self._lifecycle.get_stats(lifecycle_entries).to_dict()

        return stats

    async def run_maintenance(self, user_id: int) -> Dict[str, int]:
        """
        手动触发记忆维护。

        执行：
        1. 长期记忆衰减（LongTermMemory.apply_decay）
        2. 生命周期状态评估
        3. WriteGuard 哈希缓存清理
        """
        result = {"decayed": 0, "lifecycle_transitions": 0}

        # 1. 衰减
        if self.config.long_term_decay_enabled:
            result["decayed"] = await self.long_term.apply_decay(user_id)

        # 2. 生命周期状态评估
        if self.config.db_session:
            db = self.config.db_session
            from backend.models.memory import MemoryEntry as ME

            entries = db.query(ME).filter(ME.user_id == user_id, ME.is_active == True).all()
            if entries:
                transition_input = [
                    {
                        "entry_id": str(e.id),
                        "lifecycle_stage": e.meta_data.get("lifecycle_stage", "active") if e.meta_data else "active",
                        "importance": e.importance,
                        "timestamp": e.created_at.timestamp() if e.created_at else time.time(),
                    }
                    for e in entries
                ]
                transitions = self._lifecycle.evaluate_batch(transition_input)
                for eid, target in transitions.items():
                    entry = db.query(ME).filter(ME.id == int(eid)).first()
                    if entry:
                        if not entry.meta_data:
                            entry.meta_data = {}
                        entry.meta_data["lifecycle_stage"] = target.value
                if transitions:
                    db.commit()
                result["lifecycle_transitions"] = len(transitions)

        # 3. 清理哈希缓存
        self._write_guard.clear_hash_cache()
        self._lifecycle.reset_access_tracker()

        logger.info(f"[MEM-MGR] 维护完成: {result}")
        return result

    # ── 黑板 ↔ 记忆桥 ──

    async def init_blackboard_from_memory(
        self, query: str, user_id: int, top_k: int = None
    ) -> int:
        """
        任务初始化：从长期记忆中检索相关信息，写入黑板。

        Args:
            query: 任务描述（用于语义检索）
            user_id: 用户 ID
            top_k: 检索数量

        Returns:
            写入黑板的长时记忆条目数
        """
        if not self._enabled("long_term"):
            return 0

        k = top_k or self.config.long_term_retrieval_top_k
        try:
            memories = await self.long_term.semantic_search(query, user_id, top_k=k)
        except Exception as e:
            logger.warning(f"[MEM-MGR] 黑板初始化-检索失败: {e}")
            return 0

        count = 0
        for mem in memories:
            await self.working.set_workspace(
                key=f"ltm_{mem.entry_id or count}",
                value=mem.content,
                source_agent_id="long_term_memory",
                source_step_id="init",
                confidence=mem.importance,
            )
            count += 1

        if count > 0:
            logger.info(f"[MEM-MGR] 从长期记忆初始化了 {count} 条黑板记录")

        return count

    async def extract_blackboard_to_memory(
        self, user_id: int, conversation_id: int = None
    ) -> int:
        """
        任务结束：将黑板中高价值条目提取到长期记忆。

        规则（参考 Claude 的记忆写入黄金法则）：
        - 只提取 confidence >= 0.7 的条目
        - 不提取 ltm_ 前缀的条目（本来就是从长期记忆来的）
        - 不提取临时/中间标记的条目

        Returns:
            写入长期记忆的条目数
        """
        if not self._enabled("long_term") or not self._enabled("working"):
            return 0

        entries = self.working.blackboard.get_active()
        count = 0

        for entry in entries:
            # 跳过从长期记忆初始化的条目
            if entry.key.startswith("ltm_"):
                continue

            # 只提取高置信度条目
            if entry.confidence < 0.7:
                continue

            # 跳过临时标记
            if entry.metadata.get("temporary"):
                continue

            content = f"[{entry.key}] {str(entry.value)[:400]}"
            await self.long_term.store(MemoryEntry(
                content=content,
                memory_type=MemoryType.PROJECT.value,
                importance=min(1.0, entry.confidence),
                metadata={
                    "source": "blackboard",
                    "blackboard_key": entry.key,
                    "source_agent_id": entry.source_agent_id,
                    "source_step_id": entry.source_step_id,
                },
            ))
            count += 1

        if count > 0:
            logger.info(f"[MEM-MGR] 从黑板提取了 {count} 条记录到长期记忆")

        return count

    # ── 书记官：结构化会话记忆写入 ──

    async def record_session_entry(
        self,
        task_id: str,
        task_goal: str,
        result: str,
        agent_id: str = "agent",
        status: str = "completed",
        key_findings: List[str] = None,
        outputs: List[Dict[str, str]] = None,
    ) -> str:
        """
        书记官：子任务完成后立即记录结构化条目到 WorkingMemory + SummaryMemory。

        这不是一个子 Agent，而是 Orchestrator 内部的后台服务方法。
        它在每个子任务成功完成后被 _execute_tasks_node 同步调用。

        写入内容：
        - WorkingMemory 黑板: 任务的结构化产出
        - SummaryMemory: 轮次级摘要

        Args:
            task_id: 子任务 ID
            task_goal: 子任务目标描述
            result: 子任务最终输出文本
            agent_id: 执行的 Agent ID
            status: 任务状态
            key_findings: 关键发现列表
            outputs: 产出物列表 [{"type": "file", "path": "..."}]

        Returns:
            黑板条目的 key
        """
        # 1. 写入 WorkingMemory 黑板
        findings = key_findings or self._extract_key_sentences(result, max_sentences=3)
        blackboard_value = {
            "task_goal": task_goal,
            "status": status,
            "key_findings": findings,
            "outputs": outputs or [],
            "result_summary": result[:500],
        }

        entry_key = await self.working.set_workspace(
            key=f"session_{task_id}",
            value=blackboard_value,
            source_agent_id=agent_id,
            source_step_id=task_id,
            confidence=0.9 if status == "completed" else 0.5,
        )

        # 2. 写入 SummaryMemory 轮次摘要
        if self._enabled("summary"):
            summary_text = f"[{task_id}] {task_goal}: {'完成' if status == 'completed' else '未完成'}"
            if findings:
                summary_text += f" | 发现: {'; '.join(findings[:2])}"
            await self.summary.add_turn_summary(
                [{"role": agent_id, "content": summary_text}],
                conversation_id=0,
            )

        logger.debug(
            f"[MEM-MGR] 书记官记录: {task_id} ({status}), "
            f"findings={len(findings)}, key={entry_key}"
        )
        return entry_key

    async def build_context_for_task(
        self,
        task_description: str,
        user_id: int,
        task_dependencies: List[str] = None,
    ) -> str:
        """
        任务上下文构建：子任务执行前，从长期记忆 + 黑板中检索相关信息。

        写入路径是 Orchestrator 统一控制；读取路径也是。
        子 Agent 只能看到 Orchestrator 注入的上下文片段，不能直接访问记忆库。

        Args:
            task_description: 当前子任务描述
            user_id: 用户 ID
            task_dependencies: 该子任务依赖的黑板 key 列表

        Returns:
            拼接好的上下文文本（直接注入子 Agent prompt）
        """
        parts = []

        # 1. 从长期记忆检索相关事实
        if self._enabled("long_term") and task_description:
            try:
                memories = await self.long_term.semantic_search(
                    query=task_description,
                    user_id=user_id,
                    top_k=3,
                )
                if memories:
                    parts.append("## 相关长期记忆")
                    for mem in memories:
                        parts.append(f"- [{mem.memory_type}] {mem.content[:200]}")
            except Exception as e:
                logger.warning(f"[MEM-MGR] build_context LTM检索失败: {e}")

        # 2. 从黑板获取依赖任务的产出
        if self._enabled("working") and task_dependencies:
            ctx = await self.working.get_blackboard_context(dependencies=task_dependencies)
            if ctx:
                parts.append(ctx)

        # 3. 用户画像
        if self._enabled("long_term"):
            try:
                profile = await self.long_term.get_user_profile_text(user_id)
                if profile:
                    parts.append(f"## 用户画像\n{profile[:300]}")
            except Exception:
                pass

        return "\n\n".join(parts) if parts else ""

    @staticmethod
    def _extract_key_sentences(text: str, max_sentences: int = 3) -> List[str]:
        """从文本中提取关键句子（简单规则，不调用 LLM）。"""
        import re
        sentences = re.split(r'[。！？\n]', text)
        key_sentences = []
        for s in sentences:
            s = s.strip()
            if len(s) > 10 and len(s) < 200:
                key_sentences.append(s)
            if len(key_sentences) >= max_sentences:
                break
        return key_sentences

    # ── 长期记忆更新（工作流收尾节点） ──

    async def update_long_term_memory(
        self,
        user_id: int,
        conversation_id: int,
        messages: List[dict] = None,
        final_summary: str = "",
    ) -> int:
        """
        长期记忆更新：工作流收尾时调用，提取整个对话的稳定事实。

        这不是一个子 Agent，而是 Orchestrator 内部的后台服务方法。
        放在 generate_summary 之后作为 LangGraph 的收尾节点。

        与 consolidate() 中每轮提取的区别：
        - consolidate 提取的是单轮事实（粒度细，频率高）
        - update_long_term_memory 提取的是整场对话沉淀后的稳定事实（粒度粗，频率低）

        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID
            messages: 完整对话消息列表
            final_summary: 最终总结文本

        Returns:
            新写入的长期记忆条目数
        """
        if not self._enabled("long_term"):
            return 0

        # 构建提取输入：优先用 messages，降级用 summary
        if messages:
            msgs = messages[-20:]  # 最近 20 条
        elif final_summary:
            msgs = [{"role": "assistant", "content": final_summary}]
        else:
            return 0

        try:
            ids = await self.long_term.extract_and_store(
                messages=msgs,
                user_id=user_id,
                conversation_id=conversation_id,
                agent_id="orchestrator",
            )
            logger.info(f"[MEM-MGR] 长期记忆更新完成: {len(ids)} 条")
            return len(ids)
        except Exception as e:
            logger.warning(f"[MEM-MGR] 长期记忆更新失败: {e}")
            return 0

    # ── Session 压缩 ──

    async def _compress_async(self) -> None:
        """后台执行渐进压缩。"""
        if not self._session_agent:
            return

        result = await self.short_term.compress_if_needed()
        if result and result.compressed:
            # 将压缩结果存入 SummaryMemory
            self.summary.store_compression(result)

            # 更新 LongTermMemory 的 retriever（如果有 compression summaries，后续检索更精准）
            logger.info(
                f"[MEM-MGR] 后台压缩完成: L{result.level}, "
                f"{result.tokens_before}→{result.tokens_after} tokens"
            )

    async def compress_now(self, force: bool = False) -> Any:
        """立即执行压缩（同步，用于测试或手动触发）。"""
        if not self._session_agent:
            return None
        result = await self.short_term.compress(force=force)
        if result and result.compressed:
            self.summary.store_compression(result)
        return result

    def get_compression_context(self) -> str:
        """获取压缩上下文文本（来自 SummaryMemory 的压缩摘要）。"""
        if not self._session_agent:
            return ""
        return self.summary.get_compression_context()

    def get_session_context(self) -> str:
        """获取 SessionMemoryAgent 的累积会话摘要文本。"""
        if not self._session_agent:
            return ""
        return self._session_agent.get_session_context_text()

    def reset_session(self) -> None:
        """重置会话状态（新会话开始时调用）。"""
        if self._session_agent:
            self._session_agent.reset()
        self._write_guard.clear_hash_cache()
        self._lifecycle.reset_access_tracker()

    # ── WriteGuard 集成 ──

    def _on_write_guard_result(self, result: GuardResult) -> None:
        """记录 WriteGuard 统计。"""
        if result.allowed:
            self._wg_passed += 1
        else:
            self._wg_blocked += 1

    # ── MemoryService 兼容别名 ──

    async def augment_context(
        self, user_id: int, query: str, conversation_id: int = None
    ) -> MemoryContext:
        """[deprecated 别名] 请使用 gather_context()。"""
        return await self.gather_context(query, user_id)

    async def on_conversation_turn(
        self, user_id: int, conversation_id: int, messages: List[dict], agent_id: str = None
    ) -> None:
        """[deprecated 别名] 请使用 consolidate()。"""
        response = ""
        for m in reversed(messages):
            if m.get("role") == "assistant":
                response = str(m.get("content", ""))
                break
        await self.consolidate(messages, response, user_id, conversation_id, agent_id)

    # ── 便捷方法 ──

    async def build_system_prompt(self, agent_id: str = None) -> str:
        """构建完整的系统 prompt。"""
        parts = []

        instructions = await self.instruction.get_active_instructions(
            self.config.instruction_scopes
        )
        if instructions:
            parts.append(instructions)

        # 注：短期记忆和长期记忆通过 gather_context 获取

        return "\n\n".join(parts)

    def enable_layer(self, name: str) -> None:
        """启用某一层记忆。"""
        if name in self._enabled_layers:
            self._enabled_layers[name] = True

    def disable_layer(self, name: str) -> None:
        """禁用某一层记忆。"""
        if name in self._enabled_layers:
            self._enabled_layers[name] = False

    def _enabled(self, name: str) -> bool:
        return self._enabled_layers.get(name, True)
