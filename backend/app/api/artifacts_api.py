# app/api/artifacts_api.py
"""
产物（Artifact）管理 API

功能：
- 查询对话的所有产物
- 查询用户的所有产物（跨对话）
- 删除产物
- 置顶/收藏产物
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from backend.app.dependencies import get_db
from backend.app.api.auth import get_current_user
from backend.models.user import User as UserModel
from backend.models.artifact import Artifact
from backend.utils.logger import logger

router = APIRouter()


class ArtifactOut(BaseModel):
    id: str
    message_id: Optional[str] = None
    conversation_id: Optional[int] = None
    type: str
    content: Optional[str] = None
    meta_data: Optional[dict] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ArtifactListOut(BaseModel):
    artifacts: List[ArtifactOut]
    total: int


@router.get("/conversations/{conversation_id}/artifacts", response_model=ArtifactListOut)
async def list_conversation_artifacts(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    artifact_type: Optional[str] = Query(None, description="按类型过滤: code, file, html_preview, markdown, diagram"),
):
    """
    获取指定对话的所有产物。

    按创建时间倒序排列，支持分页和类型过滤。
    """
    query = db.query(Artifact).filter(Artifact.conversation_id == conversation_id)

    if artifact_type:
        query = query.filter(Artifact.type == artifact_type)

    total = query.count()
    artifacts = (
        query
        .order_by(Artifact.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []
    for a in artifacts:
        result.append({
            "id": a.id,
            "message_id": a.message_id,
            "conversation_id": conversation_id,
            "type": a.type,
            "content": a.content[:500] if a.content and len(a.content) > 500 else a.content,
            "meta_data": a.meta_data,
            "created_at": a.created_at,
        })

    return ArtifactListOut(artifacts=result, total=total)


@router.get("/artifacts", response_model=ArtifactListOut)
async def list_user_artifacts(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    artifact_type: Optional[str] = Query(None),
):
    """
    获取当前用户的所有产物（跨所有对话）。

    按创建时间倒序排列。
    """
    from backend.models.conversation import Conversation

    # 获取用户的所有对话 ID
    user_conv_ids = (
        db.query(Conversation.id)
        .filter(Conversation.user_id == current_user.id)
        .all()
    )
    conv_id_list = [c[0] for c in user_conv_ids]

    if not conv_id_list:
        return ArtifactListOut(artifacts=[], total=0)

    query = db.query(Artifact).filter(Artifact.conversation_id.in_(conv_id_list))

    if artifact_type:
        query = query.filter(Artifact.type == artifact_type)

    total = query.count()
    artifacts = (
        query
        .order_by(Artifact.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []
    for a in artifacts:
        result.append({
            "id": a.id,
            "message_id": a.message_id,
            "conversation_id": a.conversation_id,
            "type": a.type,
            "content": a.content[:500] if a.content and len(a.content) > 500 else a.content,
            "meta_data": a.meta_data,
            "created_at": a.created_at,
        })

    return ArtifactListOut(artifacts=result, total=total)


@router.delete("/artifacts/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    删除指定产物（仅允许产物所属对话的创建者）。
    """
    from backend.models.conversation import Conversation

    artifact = db.query(Artifact).filter(Artifact.id == artifact_id).first()
    if not artifact:
        raise HTTPException(status_code=404, detail="产物不存在")

    # 验证所有权：通过 conversation_id → user
    conversation = db.query(Conversation).filter(Conversation.id == artifact.conversation_id).first()
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除此产物")

    db.delete(artifact)
    db.commit()

    logger.info(f"[ARTIFACT-API] 产物已删除: id={artifact_id}, type={artifact.type}")
    return {"ok": True, "deleted_id": artifact_id}


@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    获取单个产物的完整详情。
    """
    from backend.models.conversation import Conversation

    artifact = db.query(Artifact).filter(Artifact.id == artifact_id).first()
    if not artifact:
        raise HTTPException(status_code=404, detail="产物不存在")

    conversation = db.query(Conversation).filter(Conversation.id == artifact.conversation_id).first()
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问此产物")

    return {
        "id": artifact.id,
        "message_id": artifact.message_id,
        "conversation_id": message.conversation_id,
        "type": artifact.type,
        "content": artifact.content,
        "meta_data": artifact.meta_data,
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }
