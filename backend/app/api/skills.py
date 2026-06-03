# app/api/skills.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Optional
import json
from datetime import datetime, timedelta
from jose import JWTError, jwt
from backend.app.dependencies import get_db
from backend.app.schemas import SkillCreate, SkillResponse
from backend.app.api.auth import get_current_user, SECRET_KEY, ALGORITHM
from backend.models.user import User as UserModel
from backend.models.skill import Skill as SkillModel, SkillInstall as SkillInstallModel
from backend.utils.logger import logger
import re

router = APIRouter()

# 工具函数
def generate_slug(name: str) -> str:
    """根据名称生成URL友好的slug"""
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    return slug

def next_available_slug(base_slug: str, db: Session) -> str:
    """生成唯一的slug，如果已存在则添加数字后缀"""
    slug = base_slug
    counter = 1
    while db.query(SkillModel).filter(SkillModel.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug

def snapshot_of(skill):
    """创建技能当前状态的快照"""
    return {
        "name": skill.name,
        "icon": skill.icon,
        "description": skill.description,
        "code": skill.code,
        "readme": skill.readme,
        "category": skill.category
    }

def append_version(skill, user_id, snapshot, note):
    """添加新版本到历史记录"""
    try:
        versions = json.loads(skill.versions or '[]')
    except:
        versions = []
    
    versions.append({
        "ts": datetime.utcnow().isoformat().replace('T', ' ')[:19],
        "by": user_id,
        "snapshot": snapshot,
        "note": note
    })
    return json.dumps(versions)

def public_skill(skill, user_id=None):
    """将技能模型转换为公开响应格式"""
    return {
        "id": skill.id,
        "slug": skill.slug,
        "name": skill.name,
        "icon": skill.icon,
        "description": skill.description,
        "code": skill.code,
        "readme": skill.readme,
        "category": skill.category,
        "author_id": skill.author_id,
        "author_name": skill.author_name,
        "is_published": skill.is_published,
        "install_count": skill.install_count,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
        "isMine": skill.author_id == user_id if user_id else False
    }

# API端点
async def try_get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = None, db: Session = Depends(get_db)):
    """尝试获取当前用户，如果认证失败则返回None"""
    if not credentials:
        return None
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            return None
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        return user
    except:
        return None

@router.get("/market", response_model=List[SkillResponse])
async def get_market_skills(db: Session = Depends(get_db), current_user: Optional[UserModel] = Depends(try_get_current_user)):
    """获取市场上发布的技能列表"""
    # 查询所有已发布的技能
    skills = db.query(SkillModel).filter(SkillModel.is_published == True).order_by(SkillModel.install_count.desc(), SkillModel.id.asc()).all()
    
    # 获取当前用户已安装的技能
    installed_set = set()
    if current_user:
        installs = db.query(SkillInstallModel).filter(SkillInstallModel.user_id == current_user.id).all()
        installed_set = {install.skill_id for install in installs}
    
    # 构造响应
    result = []
    for skill in skills:
        skill_dict = public_skill(skill, current_user.id if current_user else None)
        skill_dict["isInstalled"] = skill.id in installed_set
        result.append(SkillResponse.model_validate(skill_dict))
    
    return result

@router.get("/mine", response_model=List[SkillResponse])
async def get_my_skills(current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取我创建的技能"""
    skills = db.query(SkillModel).filter(SkillModel.author_id == current_user.id).order_by(SkillModel.updated_at.desc()).all()
    return [SkillResponse.model_validate(public_skill(skill, current_user.id)) for skill in skills]

@router.get("/installed", response_model=List[SkillResponse])
async def get_installed_skills(current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取我安装的技能"""
    # 查询用户安装的所有技能ID
    install_ids = db.query(SkillInstallModel.skill_id).filter(SkillInstallModel.user_id == current_user.id).all()
    skill_ids = [id[0] for id in install_ids]
    
    # 获取这些技能的详细信息
    skills = db.query(SkillModel).filter(SkillModel.id.in_(skill_ids)).order_by(SkillModel.updated_at.desc()).all()
    
    # 添加isInstalled标记
    result = []
    for skill in skills:
        skill_dict = public_skill(skill, current_user.id)
        skill_dict["isInstalled"] = True
        result.append(SkillResponse.model_validate(skill_dict))
    
    return result

@router.post("", response_model=SkillResponse)
async def create_skill(skill_in: SkillCreate, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """创建新技能（默认私有）"""
    # 检查slug是否已存在
    existing = db.query(SkillModel).filter(SkillModel.slug == skill_in.slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="slug_taken")
    
    # 初始化版本历史
    init_versions = json.dumps([{
        "ts": datetime.utcnow().isoformat().replace('T', ' ')[:19],
        "by": current_user.id,
        "snapshot": snapshot_of(skill_in),
        "note": "created"
    }])
    
    # 创建技能记录
    db_skill = SkillModel(
        slug=skill_in.slug,
        name=skill_in.name,
        icon=skill_in.icon,
        description=skill_in.description,
        code=skill_in.code,
        readme=skill_in.readme,
        category=skill_in.category,
        author_id=current_user.id,
        author_name=current_user.username,
        is_published=skill_in.publish,
        versions=init_versions
    )
    
    db.add(db_skill)
    db.commit()
    db.refresh(db_skill)
    
    logger.info(f"✅ 新技能创建成功: {db_skill.name}")
    return SkillResponse.model_validate(public_skill(db_skill, current_user.id))

@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill_detail(skill_id: int, db: Session = Depends(get_db), current_user: Optional[UserModel] = Depends(try_get_current_user)):
    """获取单条技能详情"""
    skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="not_found")
    
    # 检查是否已安装
    is_installed = False
    if current_user:
        install = db.query(SkillInstallModel).filter(
            SkillInstallModel.user_id == current_user.id,
            SkillInstallModel.skill_id == skill_id
        ).first()
        is_installed = install is not None
    
    skill_dict = public_skill(skill, current_user.id if current_user else None)
    skill_dict["isInstalled"] = is_installed
    return SkillResponse.model_validate(skill_dict)

@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(skill_id: int, skill_in: SkillCreate, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """编辑技能（仅作者）"""
    skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="not_found")
    if skill.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    
    # 添加版本历史
    new_versions = append_version(skill, current_user.id, snapshot_of(skill), {"note": "before_edit"})
    
    # 更新技能信息
    skill.name = skill_in.name
    skill.icon = skill_in.icon
    skill.description = skill_in.description
    skill.code = skill_in.code
    skill.readme = skill_in.readme
    skill.category = skill_in.category
    skill.versions = new_versions
    skill.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(skill)
    
    logger.info(f"🔄 技能更新成功: {skill.name}")
    return SkillResponse.model_validate(public_skill(skill, current_user.id))

@router.post("/{skill_id}/publish", response_model=SkillResponse)
async def publish_skill(skill_id: int, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """发布技能"""
    skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="not_found")
    if skill.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    
    skill.is_published = True
    skill.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(skill)
    
    logger.info(f"📢 技能已发布: {skill.name}")
    return SkillResponse.model_validate(public_skill(skill, current_user.id))

@router.post("/{skill_id}/unpublish", response_model=SkillResponse)
async def unpublish_skill(skill_id: int, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """撤回发布"""
    skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="not_found")
    if skill.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    
    skill.is_published = False
    skill.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(skill)
    
    logger.info(f"📢 技能已撤回: {skill.name}")
    return SkillResponse.model_validate(public_skill(skill, current_user.id))

@router.post("/{skill_id}/install")
async def install_skill(skill_id: int, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """安装技能"""
    skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="not_found")
    if not skill.is_published and skill.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="not_published")
    
    # 检查是否已安装
    existing_install = db.query(SkillInstallModel).filter(
        SkillInstallModel.user_id == current_user.id,
        SkillInstallModel.skill_id == skill_id
    ).first()
    
    if not existing_install:
        # 添加安装记录
        install = SkillInstallModel(user_id=current_user.id, skill_id=skill_id)
        db.add(install)
        # 增加安装计数
        skill.install_count += 1
        db.commit()
    
    db.refresh(skill)
    skill_dict = public_skill(skill, current_user.id)
    skill_dict["isInstalled"] = True
    
    logger.info(f"📥 技能安装成功: {skill.name}")
    return {"ok": True, "skill": skill_dict}

@router.delete("/{skill_id}")
async def delete_skill(skill_id: int, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """删除技能（仅作者）"""
    skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="not_found")
    if skill.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    
    # 删除相关的安装记录
    db.query(SkillInstallModel).filter(SkillInstallModel.skill_id == skill_id).delete()
    # 删除技能本身
    db.delete(skill)
    db.commit()
    
    logger.info(f"🗑️ 技能已删除: {skill.name}")
    return {"ok": True}

@router.post("/{skill_id}/fork", response_model=SkillResponse)
async def fork_skill(skill_id: int, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """Fork技能为我的副本"""
    src_skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
    if not src_skill:
        raise HTTPException(status_code=404, detail="not_found")
    if src_skill.author_id == current_user.id:
        raise HTTPException(status_code=400, detail="already_yours")
    
    # 生成新的唯一slug
    new_slug = next_available_slug(src_skill.slug, db)
    
    # 初始化版本历史
    init_versions = json.dumps([{
        "ts": datetime.utcnow().isoformat().replace('T', ' ')[:19],
        "by": current_user.id,
        "snapshot": snapshot_of(src_skill),
        "note": f"forked_from:{src_skill.slug}"
    }])
    
    # 创建fork的副本
    new_skill = SkillModel(
        slug=new_slug,
        name=src_skill.name,
        icon=src_skill.icon,
        description=src_skill.description,
        code=src_skill.code,
        readme=src_skill.readme,
        category=src_skill.category,
        author_id=current_user.id,
        author_name=current_user.username,
        is_published=False,  # fork的技能默认不发布
        parent_id=src_skill.id,
        versions=init_versions
    )
    
    db.add(new_skill)
    db.commit()
    db.refresh(new_skill)
    
    logger.info(f"🔀 技能Fork成功: {src_skill.name} -> {new_skill.name}")
    return SkillResponse.model_validate(public_skill(new_skill, current_user.id))