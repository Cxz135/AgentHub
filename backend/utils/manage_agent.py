import contextvars
import json
import re
import uuid
from datetime import datetime

from backend.db.database import SessionLocal
from backend.models.conversation import Conversation
from backend.models.custom_agent import CustomAgent as CustomAgentModel
from backend.utils.logger import logger
from backend.utils.agent_config import (
    normalize_memory_config,
    normalize_planning_config,
    normalize_validation_config,
)

__all__ = ["create_agent", "update_agent", "list_agents"]

# 上下文变量：用于向工具函数注入调用者上下文（current_user_id、conversation_id）
_caller_ctx = contextvars.ContextVar('manage_caller_ctx', default={})

VALID_ADAPTERS = {"tongyi", "deepseek", "opencode"}


def _extract_payload(input_content: str) -> dict:
    """Accept raw JSON or a fenced json block produced by the LLM."""
    if not input_content or not input_content.strip():
        raise ValueError("输入内容为空，无法解析 Agent 管理请求。")

    content = input_content.strip()
    fenced_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
    if fenced_match:
        content = fenced_match.group(1).strip()

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"无法解析 JSON 输入: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("输入必须是 JSON 对象。")

    # 🎯 从调用者上下文注入缺失的 current_user_id 和 conversation_id
    # （即使 LLM 未在 JSON 中包含，框架也会自动补上）
    ctx = _caller_ctx.get({})
    if ctx:
        if "current_user_id" not in payload and ctx.get("current_user_id"):
            payload["current_user_id"] = ctx["current_user_id"]
            logger.debug(f"[_extract_payload] 已从上下文注入 current_user_id={ctx['current_user_id']}")
        if "conversation_id" not in payload and ctx.get("conversation_id"):
            payload["conversation_id"] = ctx["conversation_id"]
            logger.debug(f"[_extract_payload] 已从上下文注入 conversation_id={ctx['conversation_id']}")

    return payload


def _resolve_user_id(db, payload: dict) -> int:
    current_user_id = payload.get("current_user_id")
    if current_user_id:
        return int(current_user_id)

    conversation_id = payload.get("conversation_id")
    if conversation_id:
        conversation = db.query(Conversation).filter(Conversation.id == int(conversation_id)).first()
        if conversation and conversation.user_id:
            return int(conversation.user_id)

    raise ValueError("缺少 current_user_id，且无法从 conversation_id 推断用户。")


def _normalize_tools(payload: dict) -> list[str]:
    tools = payload.get("tools", [])
    if tools is None:
        return []
    if not isinstance(tools, list):
        raise ValueError("tools 必须是字符串数组。")
    return [str(tool).strip() for tool in tools if str(tool).strip()]


def _normalize_adapter(payload: dict, existing_adapter: str | None = None) -> str:
    adapter = str(payload.get("llm_adapter") or existing_adapter or "tongyi").strip().lower()
    if adapter not in VALID_ADAPTERS:
        raise ValueError(f"不支持的 llm_adapter: {adapter}，可选值: {sorted(VALID_ADAPTERS)}")
    return adapter


def _build_create_name(db, user_id: int, requested_name: str) -> str:
    existing = db.query(CustomAgentModel).filter(
        CustomAgentModel.name == requested_name,
        CustomAgentModel.user_id == user_id,
        CustomAgentModel.is_active == True,
    ).first()
    if not existing:
        return requested_name
    suffix = datetime.now().strftime("%m%d%H%M")
    return f"{requested_name}_{suffix}"


def _register_runtime_agent(db_agent: CustomAgentModel) -> None:
    # 延迟导入，避免在模块加载时引入循环依赖。
    from backend.app.dependencies import get_orchestrator

    orchestrator = get_orchestrator()
    orchestrator.register_custom_agent(db_agent)


def create_agent(input_content: str) -> str:
    """Create a custom agent from a JSON payload."""
    db = SessionLocal()
    try:
        payload = _extract_payload(input_content)
        user_id = _resolve_user_id(db, payload)
        name = str(payload.get("name", "")).strip()
        system_prompt = str(payload.get("system_prompt", "")).strip()
        if not name:
            raise ValueError("创建 Agent 时必须提供 name。")
        if not system_prompt:
            raise ValueError("创建 Agent 时必须提供 system_prompt。")

        final_name = _build_create_name(db, user_id, name)
        agent_id = f"custom_{final_name.replace(' ', '_').lower()}_{uuid.uuid4().hex[:6]}"
        # A 档：归一化 3 类嵌套配置，非法输入会抩 ValueError 被外层捕获转 JSON 错误
        memory_cfg = normalize_memory_config(payload.get("memory_config"))
        planning_cfg = normalize_planning_config(payload.get("planning_config"))
        validation_cfg = normalize_validation_config(payload.get("validation_config"))
        db_agent = CustomAgentModel(
            name=final_name,
            agent_id=agent_id,
            user_id=user_id,
            icon=str(payload.get("icon") or "smart_toy").strip() or "smart_toy",
            description=str(payload.get("description") or "").strip(),
            system_prompt=system_prompt,
            llm_adapter=_normalize_adapter(payload),
            tools=_normalize_tools(payload),
            memory_config=memory_cfg,
            planning_config=planning_cfg,
            validation_config=validation_cfg,
        )
        db.add(db_agent)
        db.commit()
        db.refresh(db_agent)
        _register_runtime_agent(db_agent)
        result = {
            "status": "success",
            "action": "create",
            "agent_id": db_agent.agent_id,
            "name": db_agent.name,
            "llm_adapter": db_agent.llm_adapter,
            "tools": db_agent.tools or [],
            "message": f"已创建 Agent '{db_agent.name}'。",
        }
        logger.info(f"✅ manage_agent.create_agent 成功: {db_agent.agent_id}")
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        db.rollback()
        logger.error(f"manage_agent.create_agent 失败: {exc}")
        return json.dumps(
            {"status": "error", "action": "create", "message": str(exc)},
            ensure_ascii=False
        )
    finally:
        db.close()


def update_agent(input_content: str) -> str:
    """Update an existing custom agent from a JSON payload."""
    db = SessionLocal()
    try:
        payload = _extract_payload(input_content)
        user_id = _resolve_user_id(db, payload)
        target_agent_id = str(payload.get("agent_id") or "").strip()
        target_name = str(payload.get("target_name") or payload.get("name") or "").strip()

        query = db.query(CustomAgentModel).filter(
            CustomAgentModel.user_id == user_id,
            CustomAgentModel.is_active == True,
        )
        if target_agent_id:
            db_agent = query.filter(CustomAgentModel.agent_id == target_agent_id).first()
        elif target_name:
            db_agent = query.filter(CustomAgentModel.name == target_name).first()
        else:
            raise ValueError("更新 Agent 时必须提供 agent_id 或 target_name。")

        if not db_agent:
            raise ValueError("未找到要更新的 Agent。")

        if "name" in payload and str(payload["name"]).strip():
            new_name = str(payload["name"]).strip()
            conflict = query.filter(
                CustomAgentModel.name == new_name,
                CustomAgentModel.agent_id != db_agent.agent_id,
            ).first()
            if conflict:
                raise ValueError(f"同名 Agent 已存在: {new_name}")
            db_agent.name = new_name
        if "icon" in payload:
            db_agent.icon = str(payload.get("icon") or "smart_toy").strip() or "smart_toy"
        if "description" in payload:
            db_agent.description = str(payload.get("description") or "").strip()
        if "system_prompt" in payload and str(payload["system_prompt"]).strip():
            db_agent.system_prompt = str(payload["system_prompt"]).strip()
        if "llm_adapter" in payload:
            db_agent.llm_adapter = _normalize_adapter(payload, db_agent.llm_adapter)
        if "tools" in payload:
            db_agent.tools = _normalize_tools(payload)
        # A 档：3 类嵌套配置只有在 payload 中显式出现时才更新，避免误清空现有配置
        if "memory_config" in payload:
            db_agent.memory_config = normalize_memory_config(payload.get("memory_config"))
        if "planning_config" in payload:
            db_agent.planning_config = normalize_planning_config(payload.get("planning_config"))
        if "validation_config" in payload:
            db_agent.validation_config = normalize_validation_config(payload.get("validation_config"))

        db.commit()
        db.refresh(db_agent)
        _register_runtime_agent(db_agent)
        result = {
            "status": "success",
            "action": "update",
            "agent_id": db_agent.agent_id,
            "name": db_agent.name,
            "llm_adapter": db_agent.llm_adapter,
            "tools": db_agent.tools or [],
            "message": f"已更新 Agent '{db_agent.name}'。",
        }
        logger.info(f"✅ manage_agent.update_agent 成功: {db_agent.agent_id}")
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        db.rollback()
        logger.error(f"manage_agent.update_agent 失败: {exc}")
        return json.dumps(
            {"status": "error", "action": "update", "message": str(exc)},
            ensure_ascii=False
        )
    finally:
        db.close()


def list_agents(input_content: str) -> str:
    """List active custom agents for the current user."""
    db = SessionLocal()
    try:
        payload = _extract_payload(input_content)
        user_id = _resolve_user_id(db, payload)
        agents = db.query(CustomAgentModel).filter(
            CustomAgentModel.user_id == user_id,
            CustomAgentModel.is_active == True,
        ).all()
        result = [
            {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "description": agent.description or "",
                "llm_adapter": agent.llm_adapter,
                "tools": agent.tools or [],
            }
            for agent in agents
        ]
        return json.dumps(
            {"status": "success", "action": "list", "agents": result},
            ensure_ascii=False
        )
    except Exception as exc:
        logger.error(f"manage_agent.list_agents 失败: {exc}")
        return json.dumps(
            {"status": "error", "action": "list", "message": str(exc)},
            ensure_ascii=False
        )
    finally:
        db.close()