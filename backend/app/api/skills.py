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

def public_skill(skill, user_id=None, is_installed=False):
    """将技能模型转换为公开响应格式 - 字段使用 camelCase 匹配前端期望"""
    # 解析版本历史
    try:
        versions = json.loads(skill.versions or '[]')
    except:
        versions = []
    return {
        "id": skill.id,
        "slug": skill.slug,
        "name": skill.name,
        "icon": skill.icon,
        "description": skill.description,
        "code": skill.code,
        "readme": skill.readme,
        "category": skill.category,
        "authorId": skill.author_id,
        "authorName": skill.author_name,
        "isPublished": skill.is_published,
        "installCount": skill.install_count,
        "createdAt": skill.created_at,
        "updatedAt": skill.updated_at,
        "isMine": skill.author_id == user_id if user_id else False,
        "isInstalled": is_installed,
        "versions": versions
    }

# API端点
async def try_get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)), db: Session = Depends(get_db)):
    """尝试获取当前用户，如果认证失败则返回None"""
    if not credentials:
        return None
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        if user_id is None:
            return None
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        return user
    except:
        return None

# ===== 所有静态路由必须定义在路径参数路由之前 =====
@router.get("/market")
async def get_market_skills(db: Session = Depends(get_db), current_user: Optional[UserModel] = Depends(try_get_current_user)):
    """获取市场上发布的技能列表 - 格式匹配前端期望"""
    logger.info("[SKILLS-MARKET] 收到前端请求 /api/skills/market")
    
    # 查询所有已发布的技能
    skills = db.query(SkillModel).filter(SkillModel.is_published == True).order_by(SkillModel.install_count.desc(), SkillModel.id.asc()).all()
    logger.info(f"[SKILLS-MARKET] 从数据库找到 {len(skills)} 个已发布技能")
    
    # 获取当前用户已安装的技能
    installed_set = set()
    if current_user:
        installs = db.query(SkillInstallModel).filter(SkillInstallModel.user_id == current_user.id).all()
        installed_set = {install.skill_id for install in installs}
    
    # 构造前端期望的响应格式
    skills_list = []
    for skill in skills:
        is_installed = skill.id in installed_set
        skill_dict = public_skill(skill, current_user.id if current_user else None, is_installed=is_installed)
        skills_list.append(skill_dict)
    
    logger.info(f"[SKILLS-MARKET] 返回 {len(skills_list)} 个技能给前端")
    return {"ok": True, "skills": skills_list}


@router.get("/mine")
async def get_my_skills(db: Session = Depends(get_db), current_user: Optional[UserModel] = Depends(try_get_current_user)):
    """获取当前用户的技能（我创建的 + 我安装的），未登录返回空列表"""
    logger.info("[SKILLS-MINE] 收到前端请求 /api/skills/mine")
    
    if not current_user:
        logger.info("[SKILLS-MINE] 用户未登录，返回空列表")
        return {"ok": True, "skills": []}
    
    uid = current_user.id
    
    # 我创建的
    created = db.query(SkillModel).filter(SkillModel.author_id == uid).order_by(SkillModel.id.desc()).all()
    # 我安装的
    installed_records = db.query(SkillInstallModel).filter(SkillInstallModel.user_id == uid).all()
    installed_ids = [r.skill_id for r in installed_records]
    installed = db.query(SkillModel).filter(SkillModel.id.in_(installed_ids)).all() if installed_ids else []
    
    # 去重：以 id 为键
    skill_map = {}
    for s in created:
        skill_map[s.id] = public_skill(s, uid, is_installed=True)
    for s in installed:
        if s.id not in skill_map:
            skill_map[s.id] = public_skill(s, uid, is_installed=True)
    
    skills_list = list(skill_map.values())
    logger.info(f"[SKILLS-MINE] 返回 {len(skills_list)} 个技能给前端")
    return {"ok": True, "skills": skills_list}


@router.post("")
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
    return public_skill(db_skill, current_user.id)

@router.get("/{skill_id}")
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
    return public_skill(skill, current_user.id if current_user else None, is_installed=is_installed)

@router.put("/{skill_id}")
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
    return {"ok": True, "skill": public_skill(skill, current_user.id)}

@router.post("/{skill_id}/publish")
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
    return {"ok": True, "skill": public_skill(skill, current_user.id)}

@router.post("/{skill_id}/unpublish")
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
    return {"ok": True, "skill": public_skill(skill, current_user.id)}

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

@router.post("/{skill_id}/fork")
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
    return {"ok": True, "skill": public_skill(new_skill, current_user.id)}


@router.post("/{skill_id}/rollback")
async def rollback_skill(skill_id: int, body: dict, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """回滚技能到指定版本"""
    skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="not_found")
    
    # 只能回滚自己创建的技能
    if skill.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能回滚自己创建的技能")
    
    version_idx = body.get("versionIndex")
    if version_idx is None:
        raise HTTPException(status_code=400, detail="缺少 versionIndex")
    
    # 解析版本历史
    try:
        versions = json.loads(skill.versions or '[]')
    except:
        versions = []
    
    if version_idx < 0 or version_idx >= len(versions):
        raise HTTPException(status_code=400, detail="无效的版本索引")
    
    # 获取目标版本的快照
    target = versions[version_idx]["snapshot"]
    
    # 先将当前状态保存为新版本（作为回滚前的备份）
    current_snapshot = snapshot_of(skill)
    append_version(skill, current_user.id, current_snapshot, f"rollback_from:v{version_idx + 1}")
    
    # 应用目标版本的快照
    skill.name = target.get("name", skill.name)
    skill.icon = target.get("icon", skill.icon)
    skill.description = target.get("description", skill.description)
    skill.code = target.get("code", skill.code)
    skill.readme = target.get("readme", skill.readme)
    skill.category = target.get("category", skill.category)
    
    db.commit()
    db.refresh(skill)
    
    logger.info(f"⏪ 技能回滚成功: {skill.name} -> v{version_idx + 1}")
    return {"ok": True, "skill": public_skill(skill, current_user.id)}


def seed_native_skills_to_db(db: Session):
    """
    将 skills/*.md 中的原生能力类技能写入数据库（种子数据）。
    如果数据库中已存在同名 slug 的技能，则跳过。
    这是"软约束"机制的核心：用户只需在 skills/ 目录下添加/修改 md 文件。
    """
    from pathlib import Path
    import re as _re
    
    skills_dir = Path(__file__).parent.parent.parent / "skills"
    if not skills_dir.exists():
        logger.warning("skills 目录不存在，跳过种子数据")
        return
    
    md_files = list(skills_dir.glob("*.md"))
    if not md_files:
        logger.info("skills 目录下没有 md 文件，跳过种子数据")
        return
    
    seeded_count = 0
    for md_file in md_files:
        slug = md_file.stem  # 文件名作为 slug
        
        # 检查数据库中是否已存在
        existing = db.query(SkillModel).filter(SkillModel.slug == slug).first()
        if existing:
            logger.debug(f"技能 '{slug}' 已存在于数据库，跳过")
            continue
        
        # 读取 md 文件内容
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"读取技能文件 {md_file.name} 失败: {e}")
            continue
        
        # 解析 frontmatter（--- 之间的 YAML）
        name = slug
        description = ""
        tags = []
        fm_match = _re.match(r'^---\s*\n(.*?)\n---\s*\n', content, _re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            for line in fm_text.split('\n'):
                if line.startswith('name:'):
                    name = line[5:].strip().strip('"\'')
                elif line.startswith('description:'):
                    description = line[12:].strip().strip('"\'')
                elif line.startswith('tags:'):
                    tags_str = line[5:].strip()
                    # 解析 [tag1, tag2, ...] 格式
                    tags = [t.strip().strip('"\'') for t in tags_str.strip('[]').split(',') if t.strip()]
        
        # 构建技能记录
        icon_map = {
            'web_search': 'travel_explore',
            'gen_chat_title': 'title',
            'gen_conclusion': 'summarize',
            'file_converter': 'swap_horiz',
        }
        category_map = {
            'web_search': 'search',
            'gen_chat_title': 'output',
            'gen_conclusion': 'output',
            'file_converter': 'data',
        }
        
        skill = SkillModel(
            slug=slug,
            name=name,
            icon=icon_map.get(slug, 'extension'),
            description=description,
            code=content,  # 完整的 markdown 内容作为技能代码
            category=category_map.get(slug, 'custom'),
            author_id=None,  # 系统内置，无作者
            author_name='system',
            is_published=True,  # 内置技能默认发布
            install_count=0,
            versions='[]',
        )
        db.add(skill)
        seeded_count += 1
        logger.info(f"🌱 已写入种子技能: {slug} -> {name}")
    
    if seeded_count > 0:
        db.commit()
        logger.info(f"🎉 种子数据写入完成，共 {seeded_count} 个技能")
    else:
        logger.info("📦 所有原生技能已存在于数据库，无需写入")


@router.post("/refresh")
async def refresh_user_skills(current_user: UserModel = Depends(get_current_user)):
    """
    手动刷新用户 Skill（从数据库重新加载到 Orchestrator）。
    用户创建/更新 Skill 后可以调用此接口立即生效，无需等待定时刷新。

    注意：需要管理员权限或 Skill 作者才能刷新。
    """
    try:
        from backend.app.dependencies import get_orchestrator
        orchestrator = get_orchestrator()
        orchestrator.refresh_user_skills()
        logger.info(f"✅ 用户 {current_user.username} 触发了 Skill 刷新")
        return {"ok": True, "message": "Skill 刷新成功"}
    except Exception as e:
        logger.error(f"❌ Skill 刷新失败: {e}")
        return {"ok": False, "message": f"刷新失败: {str(e)}"}


@router.get("/available")
async def get_available_skills(current_user: UserModel = Depends(get_current_user)):
    """
    获取所有可用的 Skill 列表（内置 + 用户创建的已发布 Skill）。

    返回格式包含 Skill 的元信息（name, description, icon），
    前端用于渲染 Skill 管理面板。
    """
    from backend.app.dependencies import get_orchestrator

    try:
        orchestrator = get_orchestrator()

        # 1. 内置 Skill（从 MD 文件加载）
        builtin_skills = []
        from pathlib import Path
        skills_dir = Path(__file__).parent.parent.parent / "skills"
        if skills_dir.exists():
            for md_file in skills_dir.glob("*.md"):
                skill_name = md_file.stem
                content = orchestrator.native_skills.get(skill_name, "")
                # 尝试解析 frontmatter
                name = skill_name
                description = ""
                fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL) if content else None
                if fm_match:
                    for line in fm_match.group(1).split('\n'):
                        if line.startswith('name:'):
                            name = line[5:].strip().strip('"\'')
                        elif line.startswith('description:'):
                            description = line[12:].strip().strip('"\'')
                builtin_skills.append({
                    "slug": skill_name,
                    "name": name,
                    "icon": "extension",
                    "description": description or f"内置技能: {skill_name}",
                    "category": "builtin",
                    "is_builtin": True
                })

        # 2. 用户创建的 Skill（从数据库加载）
        from sqlalchemy import text
        from backend.db.database import SessionLocal
        db = SessionLocal()
        result = db.execute(text(
            "SELECT slug, name, icon, description, category FROM skills WHERE author_id IS NOT NULL AND is_published = 1"
        ))
        user_skills = result.fetchall()
        db.close()

        user_skills_list = []
        for row in user_skills:
            slug, name, icon, description, category = row
            # 跳过已存在于内置 Skill 的
            if slug in [s['slug'] for s in builtin_skills]:
                continue
            user_skills_list.append({
                "slug": slug,
                "name": name or slug,
                "icon": icon or "extension",
                "description": description or f"用户技能: {slug}",
                "category": category or "custom",
                "is_builtin": False
            })

        # 合并所有 Skill
        all_skills = builtin_skills + user_skills_list

        logger.info(f"[SKILLS-AVAILABLE] 返回 {len(all_skills)} 个可用 Skill")
        return {"ok": True, "skills": all_skills}

    except Exception as e:
        logger.error(f"❌ 获取可用 Skill 失败: {e}")
        return {"ok": False, "message": f"获取失败: {str(e)}", "skills": []}