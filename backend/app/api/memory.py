"""
记忆管理 API — 用户面 CRUD + 检索 + 画像。

所有端点需要认证，scoped 到当前用户。

记忆类型（v2 四分类）：
    - user:      用户身份、偏好、沟通风格
    - feedback:  用户纠正、禁止事项
    - project:   项目目标、架构决策、历史踩坑
    - reference: 外部文档、配置、第三方依赖

兼容旧类型：fact / preference / decision / user_trait（自动映射到新四分类）
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.dependencies import get_db, get_orchestrator
from backend.app.api.auth import get_current_user
from backend.models.user import User as UserModel
from backend.utils.logger import logger

router = APIRouter()


class MemorySearchRequest(BaseModel):
    query: str
    top_k: int = 10
    memory_type: Optional[str] = None  # user | feedback | project | reference (兼容旧类型)


class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    importance: Optional[float] = None
    memory_type: Optional[str] = None  # user | feedback | project | reference


def _get_memory_svc(db: Session = None):
    """[deprecated] 获取 MemoryService，必要时注入 db session。"""
    orch = get_orchestrator()
    svc = getattr(orch, 'memory_service', None)
    if svc is None:
        raise HTTPException(status_code=503, detail="多层记忆服务未启用。设置 MEMORY_ENABLED=true 以启用。")
    # 动态注入 db session（因为 orchestrator 初始化时 db_session 可能为 None）
    if db is not None and (svc.db is None or svc.db != db):
        svc.db = db
        if svc._profiler:
            svc._profiler._db = db
        if svc._decayer:
            svc._decayer.db = db
    return svc


def _get_memory_mgr(db: Session = None):
    """
    获取 MemoryManager（v2 统一入口）。

    优先使用 orchestrator 的 memory_manager 属性，
    如果不存在则回退到构建临时实例。
    """
    orch = get_orchestrator()
    mgr = getattr(orch, 'memory_manager', None)

    if mgr is not None and db is not None:
        # 动态注入 db session
        mgr.config.db_session = db
        return mgr

    if mgr is not None:
        return mgr

    # 回退：构建临时 MemoryManager（不推荐，确保 orchestrator 初始化时创建）
    try:
        from backend.memory import MemoryManager, MemoryConfig

        config = MemoryConfig()
        if db is not None:
            config.db_session = db

        # 注入 LLM backend（如果 orchestrator 有）
        config.llm_backend = getattr(orch, '_llm_backend', None)

        # 注入 embed model（如果有）
        try:
            from backend.rag.vector_store import EmbeddingsFactory
            config.embed_model = EmbeddingsFactory().generator()
        except Exception:
            pass

        return MemoryManager(config)
    except Exception as e:
        logger.error(f"[MEM-API] 无法创建 MemoryManager: {e}")
        raise HTTPException(status_code=503, detail="记忆管理器不可用")


# ── 记忆条目 CRUD ──

@router.get("/memory/entries")
async def list_memories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    memory_type: Optional[str] = Query(None, description="user | feedback | project | reference（兼容 fact/preference/decision/user_trait）"),
    sort_by: str = Query("importance", description="importance | recent | access_count"),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """分页列出当前用户的所有记忆。"""
    try:
        mgr = _get_memory_mgr(db)
        return mgr.list_entries(
            user_id=current_user.id,
            memory_type=memory_type,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        # 回退到旧 MemoryService
        svc = _get_memory_svc(db)
        return svc.list_memories(
            user_id=current_user.id,
            page=page,
            page_size=page_size,
            memory_type=memory_type,
            sort_by=sort_by,
        )


@router.get("/memory/entries/{memory_id}")
async def get_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """获取单条记忆详情。"""
    try:
        mgr = _get_memory_mgr(db)
        result = await mgr.get_entry(memory_id)
        if not result:
            raise HTTPException(status_code=404, detail="记忆不存在")
        return result
    except HTTPException as e:
        if e.status_code == 404:
            raise
        # 回退
        svc = _get_memory_svc(db)
        result = svc.get_memory(memory_id, current_user.id)
        if not result:
            raise HTTPException(status_code=404, detail="记忆不存在")
        return result


@router.put("/memory/entries/{memory_id}")
async def update_memory(
    memory_id: int,
    body: MemoryUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """编辑记忆内容或重要性。"""
    updates = {}
    if body.content is not None:
        updates["content"] = body.content
    if body.importance is not None:
        updates["importance"] = body.importance
    if body.memory_type is not None:
        # 验证新类型是否合法
        from backend.memory.base import MemoryType
        valid_types = MemoryType.valid_values()
        if body.memory_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"无效的记忆类型 '{body.memory_type}'。合法值: {sorted(valid_types)}"
            )
        updates["memory_type"] = body.memory_type
    if not updates:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")

    try:
        mgr = _get_memory_mgr(db)
        ok = await mgr.update_entry(memory_id, updates)
        if not ok:
            raise HTTPException(status_code=404, detail="记忆不存在")
        return {"ok": True}
    except HTTPException as e:
        if e.status_code != 503:
            raise
        # 回退
        svc = _get_memory_svc(db)
        ok = svc.update_memory(memory_id, current_user.id, updates)
        if not ok:
            raise HTTPException(status_code=404, detail="记忆不存在")
        return {"ok": True}


@router.delete("/memory/entries/{memory_id}")
async def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """软删除一条记忆。"""
    try:
        mgr = _get_memory_mgr(db)
        ok = await mgr.delete_entry(memory_id)
        if not ok:
            raise HTTPException(status_code=404, detail="记忆不存在")
        return {"ok": True}
    except HTTPException as e:
        if e.status_code != 503:
            raise
        # 回退
        svc = _get_memory_svc(db)
        ok = svc.delete_memory(memory_id, current_user.id)
        if not ok:
            raise HTTPException(status_code=404, detail="记忆不存在")
        return {"ok": True}


@router.post("/memory/entries/{memory_id}/boost")
async def boost_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """手动提升记忆（重置衰减因子）。"""
    try:
        mgr = _get_memory_mgr(db)
        ok = await mgr.boost_entry(memory_id)
        if not ok:
            raise HTTPException(status_code=404, detail="记忆不存在")
        return {"ok": True}
    except HTTPException as e:
        if e.status_code != 503:
            raise
        # 回退
        svc = _get_memory_svc(db)
        ok = svc.boost_memory(memory_id, current_user.id)
        if not ok:
            raise HTTPException(status_code=404, detail="记忆不存在")
        return {"ok": True}


# ── 语义搜索 ──

@router.post("/memory/search")
async def search_memories(
    body: MemorySearchRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """语义搜索记忆。支持新四分类和旧类型过滤。"""
    if not body.query or len(body.query.strip()) < 2:
        return {"results": [], "query": body.query}

    try:
        mgr = _get_memory_mgr(db)
        results = await mgr.search_entries(
            query=body.query.strip(),
            user_id=current_user.id,
            top_k=body.top_k,
            memory_type=body.memory_type,
        )
        return {"results": results, "query": body.query}
    except HTTPException:
        # 回退
        svc = _get_memory_svc(db)
        svc._ensure_initialized()
        results = svc._retriever.search(
            query=body.query.strip(),
            user_id=current_user.id,
            top_k=body.top_k,
            memory_type=body.memory_type,
        )
        return {"results": results, "query": body.query}


# ── 用户画像 ──

@router.get("/memory/profile")
async def get_profile(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """获取当前用户的画像。"""
    try:
        mgr = _get_memory_mgr(db)
        profile = await mgr.long_term.get_user_profile(current_user.id)
        return profile
    except HTTPException:
        # 回退
        svc = _get_memory_svc(db)
        return svc.get_profile(current_user.id)


# ── 统计 ──

@router.get("/memory/stats")
async def get_memory_stats(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """获取记忆统计信息（含 WriteGuard 和生命周期统计）。"""
    try:
        mgr = _get_memory_mgr(db)
        stats = await mgr.get_stats(user_id=current_user.id)
        return stats.to_dict()
    except HTTPException:
        # 回退
        svc = _get_memory_svc(db)
        return svc.get_stats(current_user.id)


# ── 维护 ──

@router.post("/memory/maintenance")
async def run_maintenance(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """手动触发记忆维护（衰减 + 生命周期评估 + 缓存清理）。"""
    try:
        mgr = _get_memory_mgr(db)
        result = await mgr.run_maintenance(user_id=current_user.id)
        return {"ok": True, **result}
    except HTTPException:
        raise HTTPException(status_code=503, detail="记忆管理器不可用")


# ── 快照管理 ──

@router.get("/memory/checkpoints")
async def list_checkpoints(
    current_user: UserModel = Depends(get_current_user),
):
    """列出所有可用的记忆快照。"""
    try:
        mgr = _get_memory_mgr()
        return {"checkpoints": await mgr.list_checkpoints()}
    except HTTPException:
        raise HTTPException(status_code=503, detail="记忆管理器不可用")
