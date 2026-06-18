"""
WorkingMemory — 当前任务的工作状态

存储 Planner 生成的计划、子任务中间结果、工具调用输出。
后端：LangGraph checkpointer（AsyncSqliteSaver）+ GraphState。

v2: 引入 Blackboard（结构化任务黑板），替代扁平 _workspace dict。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from backend.memory.base import BaseMemory, MemoryEntry, MemoryConfig
from backend.memory.blackboard import Blackboard, BlackboardEntry

logger = logging.getLogger("core")


class WorkingMemory(BaseMemory):
    """
    当前任务的工作记忆。

    生命周期：set_task() → update_step() × N → finish_task()

    使用方式：
        wm = WorkingMemory(config)
        await wm.set_task("生成一个 PDF 报告", plan={"tasks": [...]})
        await wm.update_step("step_1", "done", result="...")
        state = await wm.get_task_state()
        await wm.finish_task(archive=True)
    """

    def __init__(self, config: MemoryConfig = None):
        super().__init__(config)
        self._task: Optional[Dict[str, Any]] = None
        self._steps: Dict[str, Dict[str, Any]] = {}   # step_id -> {status, result, ts}
        self._blackboard = Blackboard()                # v2: 结构化任务黑板
        self._checkpointer: Any = None

    # ── 任务管理 ──

    async def set_task(self, task_description: str, plan: dict = None) -> str:
        """设置当前任务，返回 task_id。"""
        task_id = f"task_{int(time.time() * 1000)}"
        self._task = {
            "task_id": task_id,
            "description": task_description,
            "plan": plan or {},
            "started_at": time.time(),
            "status": "running",
        }
        self._steps.clear()
        self._blackboard = Blackboard()
        logger.info(f"[WORK-MEM] 新任务: {task_id} — {task_description[:60]}")
        return task_id

    async def update_step(self, step_id: str, status: str, result: Any = None) -> None:
        """更新子任务状态。status: pending | running | done | failed"""
        self._steps[step_id] = {
            "status": status,
            "result": result,
            "updated_at": time.time(),
        }
        logger.debug(f"[WORK-MEM] step '{step_id}' → {status}")

    async def get_task_state(self) -> dict:
        """返回当前任务完整状态（含黑板快照）。"""
        return {
            "task": self._task,
            "steps": dict(self._steps),
            "blackboard": self._blackboard.snapshot(),
            "workspace": {k: e.value for k, e in self._blackboard.get_all().items()},  # 兼容旧代码
        }

    async def get_plan(self) -> Optional[dict]:
        """获取 Planner 生成的计划。"""
        if self._task:
            return self._task.get("plan")
        return None

    async def is_task_complete(self) -> bool:
        """判断所有步骤是否都已完成。"""
        if not self._steps:
            return False
        return all(s["status"] in ("done", "failed") for s in self._steps.values())

    async def finish_task(self, archive: bool = True) -> Optional[Dict[str, Any]]:
        """
        结束任务。

        Args:
            archive: True = 返回结果给调用方（用于存入 SummaryMemory/LongTermMemory）

        Returns:
            任务摘要，供其他记忆层使用。
        """
        if not self._task:
            return None
        self._task["status"] = "completed"
        self._task["finished_at"] = time.time()
        logger.info(f"[WORK-MEM] 任务完成: {self._task['task_id']}")

        if archive:
            return {
                "task_id": self._task["task_id"],
                "description": self._task["description"],
                "steps": dict(self._steps),
                "blackboard": self._blackboard.snapshot(),
                "workspace": {k: e.value for k, e in self._blackboard.get_all().items()},
            }
        return None

    # ── 跨步骤共享状态（黑板） ──

    @property
    def blackboard(self) -> Blackboard:
        """直接访问黑板实例（用于高级操作）。"""
        return self._blackboard

    async def set_workspace(self, key: str, value: Any,
                            source_agent_id: str = "orchestrator",
                            source_step_id: str = "",
                            confidence: float = 1.0,
                            dependencies: List[str] = None,
                            expires_at: float = None) -> str:
        """
        写入黑板条目（兼容旧 workspace 接口 + 新元数据）。

        旧用法（向后兼容）:
            await wm.set_workspace("result", "some text")

        新用法:
            await wm.set_workspace("market_report", "...",
                source_agent_id="agent-research",
                source_step_id="step_2",
                confidence=0.92,
                dependencies=["step_1"],
            )
        """
        return self._blackboard.put_raw(
            key=key, value=value,
            source_agent_id=source_agent_id,
            source_step_id=source_step_id,
            confidence=confidence,
            dependencies=dependencies or [],
            expires_at=expires_at,
        )

    async def get_workspace(self, key: str) -> Any:
        """获取黑板条目的值（兼容旧接口）。"""
        return self._blackboard.get_value(key)

    async def put_blackboard_entry(self, entry: BlackboardEntry) -> str:
        """写入完整的 BlackboardEntry。"""
        return self._blackboard.put(entry)

    async def get_blackboard_entry(self, key: str) -> Optional[BlackboardEntry]:
        """获取完整的 BlackboardEntry（含元数据）。"""
        return self._blackboard.get(key)

    async def get_blackboard_context(self, dependencies: List[str] = None) -> str:
        """获取黑板上下文文本（用于注入子 Agent prompt）。"""
        if dependencies:
            return self._blackboard.get_context_for(keys=dependencies)
        return self._blackboard.get_context_for()

    async def get_blackboard_stats(self) -> Dict[str, Any]:
        """获取黑板统计信息。"""
        return self._blackboard.stats()

    # ── Checkpointer 集成 ──

    def set_checkpointer(self, checkpointer: Any) -> None:
        """注入 LangGraph AsyncSqliteSaver。"""
        self._checkpointer = checkpointer

    async def save_checkpoint(self, conversation_id: str, state: dict) -> None:
        """持久化当前状态到 checkpointer。"""
        if self._checkpointer:
            config = {"configurable": {"thread_id": conversation_id}}
            await self._checkpointer.aput(config, state)

    async def load_checkpoint(self, conversation_id: str) -> Optional[dict]:
        """从 checkpointer 加载历史状态。"""
        if self._checkpointer:
            config = {"configurable": {"thread_id": conversation_id}}
            checkpoint = await self._checkpointer.aget(config)
            if checkpoint:
                return checkpoint.get("values", {})
        return None

    # ── BaseMemory 接口 ──

    async def store(self, entry: MemoryEntry) -> str:
        step_id = entry.metadata.get("step_id", f"step_{len(self._steps)}")
        await self.update_step(step_id, "done", entry.content)
        return step_id

    async def retrieve(self, query: str = "", limit: int = 5, **filters) -> List[MemoryEntry]:
        state = await self.get_task_state()
        entries = []
        if state.get("task"):
            entries.append(MemoryEntry(
                content=state["task"]["description"],
                memory_type="step",
                metadata={"role": "task"},
                entry_id=state["task"]["task_id"],
            ))
        for sid, s in state.get("steps", {}).items():
            if s.get("result"):
                entries.append(MemoryEntry(
                    content=str(s["result"])[:500],
                    memory_type="step",
                    metadata={"step_id": sid, "status": s["status"]},
                    entry_id=sid,
                ))
        return entries[-limit:]

    async def forget(self, entry_id: str = None, older_than_days: int = None) -> int:
        before = len(self._steps)
        if entry_id and entry_id in self._steps:
            del self._steps[entry_id]
        return before - len(self._steps)

    async def clear(self) -> None:
        self._task = None
        self._steps.clear()
        self._blackboard = Blackboard()

    def count(self) -> int:
        return len(self._steps) + (1 if self._task else 0)
