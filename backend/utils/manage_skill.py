# utils/manage_skill.py
"""
管理 Skill 的工具函数，供 ReAct Agent 调用
"""
import contextvars
import json
import uuid
import re
from typing import Optional
from datetime import datetime
from backend.utils.logger import logger

__all__ = ["create_skill", "update_skill", "list_skills", "delete_skill"]

_caller_ctx = contextvars.ContextVar('manage_skill_caller_ctx', default={})


def _normalize_slug(name: str) -> str:
    """将 Skill 名称转为合法的 slug"""
    # 中文转拼音或英文
    import re
    # 移除非字母数字字符，转小写，空格变下划线
    slug = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', ' ', name).strip()
    # 如果包含中文，用拼音替代
    if re.search(r'[\u4e00-\u9fa5]', slug):
        # 简单处理：取每个汉字拼音首字母，或直接用 unicode 码
        # 这里简化处理，用汉字的 unicode 码拼接
        import unicodedata
        pinyin = ''
        for c in slug:
            if '\u4e00' <= c <= '\u9fa5':
                try:
                    pinyin += unicodedata.normalize('NFKC', unicodedata.name(c, '')).lower()[:2]
                except:
                    pinyin += hex(ord(c))[2:]
            else:
                pinyin += c
        slug = re.sub(r'\s+', '_', pinyin).lower()
    else:
        slug = slug.lower().replace(' ', '_')
    # 移除非法的开头
    if slug and not slug[0].isalpha():
        slug = 'skill_' + slug
    return slug[:50]


def _extract_payload(input_content: str) -> dict:
    """从输入中提取 JSON payload"""
    if not input_content:
        raise ValueError("输入内容为空")

    content = input_content.strip()
    fenced_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
    if fenced_match:
        content = fenced_match.group(1).strip()

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        pass

    if not isinstance(payload, dict):
        raise ValueError("输入必须是 JSON 对象。")

    ctx = _caller_ctx.get({})
    if ctx:
        if "author_id" not in payload and ctx.get("current_user_id"):
            payload["author_id"] = ctx["current_user_id"]
            logger.debug(f"[_extract_payload] 已从上下文注入 author_id={ctx['current_user_id']}")
        if "author_name" not in payload and ctx.get("current_user_name"):
            payload["author_name"] = ctx["current_user_name"]

    return payload


def create_skill(input_content: str) -> str:
    """
    创建新的 Skill

    输入格式（JSON）：
    {
        "name": "技能名称",
        "description": "技能功能描述",
        "code": "技能执行代码（可选）",
        "category": "分类（可选）"
    }

    或者用自然语言：
    "创建名为 xxx 的 skill，功能是 yyy"
    """
    from backend.db.database import SessionLocal
    from backend.models.skill import Skill as SkillModel

    db = SessionLocal()
    try:
        payload = _extract_payload(input_content)

        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        code = str(payload.get("code", "")).strip()
        category = str(payload.get("category", "general")).strip()

        if not name:
            raise ValueError("创建 Skill 时必须提供 name（名称）")
        if not description:
            raise ValueError("创建 Skill 时必须提供 description（功能描述）")

        slug = _normalize_slug(name)

        # 检查 slug 是否已存在
        existing = db.query(SkillModel).filter(SkillModel.slug == slug).first()
        if existing:
            # 自动添加后缀
            slug = f"{slug}_{uuid.uuid4().hex[:4]}"

        # 如果没有提供 code，生成默认的 code
        if not code:
            code = f"# {name}\n\n你是一个{name}，擅长{description}。"

        author_id = payload.get("author_id")
        author_name = payload.get("author_name", "unknown")

        if not author_id:
            raise ValueError("创建 Skill 时必须提供 author_id（作者ID）")

        # 初始化版本历史
        init_versions = json.dumps([{
            "ts": datetime.utcnow().isoformat().replace('T', ' ')[:19],
            "by": author_id,
            "snapshot": {
                "name": name,
                "slug": slug,
                "description": description,
                "code": code,
                "category": category,
            },
            "note": "created_by_skill_creator"
        }])

        db_skill = SkillModel(
            slug=slug,
            name=name,
            icon="auto_awesome",
            description=description,
            code=code,
            readme=f"# {name}\n\n{description}",
            category=category,
            author_id=author_id,
            author_name=author_name,
            is_published=False,
            versions=init_versions
        )

        db.add(db_skill)
        db.commit()
        db.refresh(db_skill)

        result = {
            "status": "success",
            "action": "create",
            "skill_id": db_skill.id,
            "slug": db_skill.slug,
            "name": db_skill.name,
            "description": db_skill.description,
            "category": db_skill.category,
            "message": f"已创建 Skill '{db_skill.name}'，slug: {db_skill.slug}",
        }

        # 通知 orchestrator 刷新用户技能（避免循环导入，使用延迟导入）
        try:
            from backend.app.dependencies import get_orchestrator
            orch = get_orchestrator()
            if orch:
                orch.refresh_user_skills()
                logger.info(f"✅ manage_skill.create_skill 触发 orchestrator 刷新")
        except Exception as e:
            logger.warning(f"⚠️ 无法触发 orchestrator 刷新: {e}")

        logger.info(f"✅ manage_skill.create_skill 成功: {db_skill.name} (slug: {db_skill.slug})")
        return json.dumps(result, ensure_ascii=False)

    except Exception as exc:
        db.rollback()
        logger.error(f"manage_skill.create_skill 失败: {exc}")
        return json.dumps(
            {"status": "error", "action": "create", "message": str(exc)},
            ensure_ascii=False
        )
    finally:
        db.close()


def update_skill(input_content: str) -> str:
    """更新 Skill 内容"""
    from backend.db.database import SessionLocal
    from backend.models.skill import Skill as SkillModel

    db = SessionLocal()
    try:
        payload = _extract_payload(input_content)

        skill_id = payload.get("skill_id")
        slug = payload.get("slug")

        if not skill_id and not slug:
            raise ValueError("必须提供 skill_id 或 slug")

        if skill_id:
            skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
        else:
            skill = db.query(SkillModel).filter(SkillModel.slug == slug).first()

        if not skill:
            raise ValueError(f"找不到 Skill: {skill_id or slug}")

        # 更新字段
        if "name" in payload:
            skill.name = payload["name"]
        if "description" in payload:
            skill.description = payload["description"]
        if "code" in payload:
            skill.code = payload["code"]
        if "category" in payload:
            skill.category = payload["category"]

        db.commit()
        db.refresh(skill)

        result = {
            "status": "success",
            "action": "update",
            "skill_id": skill.id,
            "slug": skill.slug,
            "name": skill.name,
            "message": f"已更新 Skill '{skill.name}'",
        }

        logger.info(f"✅ manage_skill.update_skill 成功: {skill.name}")
        return json.dumps(result, ensure_ascii=False)

    except Exception as exc:
        db.rollback()
        logger.error(f"manage_skill.update_skill 失败: {exc}")
        return json.dumps(
            {"status": "error", "action": "update", "message": str(exc)},
            ensure_ascii=False
        )
    finally:
        db.close()


def list_skills(input_content: str = "") -> str:
    """列出当前用户的 Skill"""
    from backend.db.database import SessionLocal
    from backend.models.skill import Skill as SkillModel

    db = SessionLocal()
    try:
        skills = db.query(SkillModel).filter(
            (SkillModel.author_id == 0) | (SkillModel.is_published == True)
        ).order_by(SkillModel.updated_at.desc()).limit(50).all()

        result = {
            "status": "success",
            "action": "list",
            "count": len(skills),
            "skills": [
                {
                    "id": s.id,
                    "slug": s.slug,
                    "name": s.name,
                    "description": s.description,
                    "category": s.category,
                }
                for s in skills
            ]
        }

        logger.info(f"✅ manage_skill.list_skills 返回 {len(skills)} 个技能")
        return json.dumps(result, ensure_ascii=False)

    except Exception as exc:
        logger.error(f"manage_skill.list_skills 失败: {exc}")
        return json.dumps(
            {"status": "error", "action": "list", "message": str(exc)},
            ensure_ascii=False
        )
    finally:
        db.close()


def delete_skill(input_content: str) -> str:
    """删除 Skill"""
    from backend.db.database import SessionLocal
    from backend.models.skill import Skill as SkillModel

    db = SessionLocal()
    try:
        payload = _extract_payload(input_content)

        skill_id = payload.get("skill_id")
        slug = payload.get("slug")

        if not skill_id and not slug:
            raise ValueError("必须提供 skill_id 或 slug")

        if skill_id:
            skill = db.query(SkillModel).filter(SkillModel.id == skill_id).first()
        else:
            skill = db.query(SkillModel).filter(SkillModel.slug == slug).first()

        if not skill:
            raise ValueError(f"找不到 Skill: {skill_id or slug}")

        skill_name = skill.name
        db.delete(skill)
        db.commit()

        result = {
            "status": "success",
            "action": "delete",
            "message": f"已删除 Skill '{skill_name}'",
        }

        logger.info(f"✅ manage_skill.delete_skill 成功: {skill_name}")
        return json.dumps(result, ensure_ascii=False)

    except Exception as exc:
        db.rollback()
        logger.error(f"manage_skill.delete_skill 失败: {exc}")
        return json.dumps(
            {"status": "error", "action": "delete", "message": str(exc)},
            ensure_ascii=False
        )
    finally:
        db.close()