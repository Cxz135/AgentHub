from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from loguru import logger
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, AsyncGenerator
import asyncio
import json

from backend.app.dependencies import get_db, get_orchestrator
from backend.db.database import SessionLocal
from backend.app.schemas import (
    Message as MessageSchema,
    MessageCreate,
    ChatStreamRequest,
)
from backend.app.api.auth import get_current_user
from backend.models.user import User as UserModel
from backend.services.conversation_service import ConversationService

router = APIRouter()

# 前端发送的聊天请求模型
class ChatRequest(BaseModel):
    message: str
    agent: Optional[Dict] = None
    mission: Optional[Dict] = None
    active_skills: Optional[List[str]] = []  # 用户启用的 Skill 列表

# 简单的直接聊天接口，供前端调用
@router.post("")
async def simple_chat(
    chat_req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """简单的聊天接口，直接处理前端发送的消息（需登录），自动持久化消息到数据库"""
    logger.info(f"[SIMPLE-CHAT] 用户{current_user.id} 收到消息: {chat_req.message}")

    orchestrator = get_orchestrator()
    if not hasattr(orchestrator, 'db_session') or orchestrator.db_session is None:
        orchestrator.db_session = db

    conv_service = ConversationService(db)

    # 从 mission 中提取 conversation_id
    conversation_id = None
    if chat_req.mission and chat_req.mission.get('id'):
        try:
            mission_id = chat_req.mission['id']  # 格式 "mis_123"
            conversation_id = int(mission_id.replace('mis_', ''))
        except (ValueError, AttributeError):
            conversation_id = None

    # 如果有 mission 上下文，将用户消息持久化
    if conversation_id:
        conversation = conv_service.get_conversation(conversation_id)
        if conversation and conversation.user_id == current_user.id:
            from datetime import datetime
            import re
            # 解析 mentions
            mention_pattern = r'@([\w\u4e00-\u9fa5]+)'
            found = re.findall(mention_pattern, chat_req.message)
            mentioned_agents = []
            if found and conversation.squad_config:
                squad = conversation.squad_config or {}
                agents = squad.get('agents', [])
                agent_ids = {a.get('id') or a.get('name') for a in agents}
                agent_names = {a.get('name') for a in agents}
                for name in found:
                    if name in agent_ids or name in agent_names:
                        mentioned_agents.append(name)
            conv_service.add_message_to_conversation(
                conversation_id=conversation_id,
                agent_id="user",
                content=chat_req.message,
                mentions=mentioned_agents if mentioned_agents else None
            )
            conversation.last_active_at = datetime.utcnow()
            db.commit()
            logger.info(f"[SIMPLE-CHAT] 用户消息已存入 conversation {conversation_id}")
        else:
            logger.warning(f"[SIMPLE-CHAT] 对话 {conversation_id} 不存在或不属于当前用户")
            conversation_id = None

    try:
        # 构建消息历史（包含历史消息 + 当前消息）
        all_messages = []
        if conversation_id:
            history = conv_service.get_messages(conversation_id)
            for msg in history:
                all_messages.append({"role": msg.agent_id, "content": msg.content})
        else:
            all_messages = [{"role": "user", "content": chat_req.message}]

        reply_content = None
        intermediate_messages = []
        if hasattr(orchestrator, 'get_chat_response'):
            temp_conv_id = conversation_id or 0
            response = await orchestrator.get_chat_response(
                conversation_id=temp_conv_id,
                messages=all_messages,
                request_context={
                    "current_user_id": current_user.id,
                    "active_skills": chat_req.active_skills or []
                }
            )
            if isinstance(response, dict) and "content" in response:
                reply_content = response["content"]
            # 检查是否包含中间消息（子Agent依次回复）
            if isinstance(response, dict) and "intermediate_messages" in response:
                intermediate_messages = response["intermediate_messages"]

        if reply_content is None:
            reply_content = f"你好！我收到了你的消息：'{chat_req.message}'。当前Agent: {chat_req.agent.get('name', '未知Agent') if chat_req.agent else '未指定Agent'}。"

        # 将 AI 回复持久化到数据库
        if conversation_id:
            agent_id = chat_req.agent.get('id', 'assistant') if chat_req.agent else 'assistant'
            conv_service.add_message_to_conversation(
                conversation_id=conversation_id,
                agent_id=agent_id,
                content=reply_content
            )
            logger.info(f"[SIMPLE-CHAT] AI 回复已存入 conversation {conversation_id}")

            # 如果有中间消息（子Agent依次回复），也存入数据库
            for msg in intermediate_messages:
                conv_service.add_message_to_conversation(
                    conversation_id=conversation_id,
                    agent_id=msg.get("agent_id", "agent"),
                    content=msg.get("content", "")
                )
                logger.info(f"[SIMPLE-CHAT] 中间消息已存入数据库，Agent: {msg.get('agent_id', 'agent')}")

        return {"ok": True, "reply": reply_content, "intermediate_messages": intermediate_messages}

    except Exception as e:
        logger.error(f"[SIMPLE-CHAT] 处理消息出错: {e}")
        return {"ok": False, "error": str(e), "reply": f"处理出错: {str(e)}"}


@router.get("/{conversation_id}/messages", response_model=List[MessageSchema])
async def get_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """获取某个会话的所有消息，仅限创建者"""
    conv_service = ConversationService(db)
    conversation = conv_service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="会话未找到")
    if conversation.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看其他用户的会话")
    return conversation.messages


@router.post("/{conversation_id}/messages", response_model=MessageSchema)
async def send_message(
    conversation_id: int,
    message_in: MessageCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    在指定会话中发送新消息，并触发 Orchestrator 工作流。
    仅限会话创建者操作。
    """
    from sqlalchemy import inspect
    inspector = inspect(db.get_bind())
    tables = inspector.get_table_names()
    logger.info(f"[CHAT-API-DEBUG] send_message sees tables: {tables}")
    logger.info(f"[CHAT API] 收到向对话 {conversation_id} 发送新消息的请求。")
    logger.debug(f"[CHAT API] 请求体: {message_in.model_dump_json(indent=2)}")

    # 创建Orchestrator时传入数据库会话，让它能实时写入子Agent的消息
    orchestrator = get_orchestrator()
    # 如果是第一次设置db_session，就赋值
    if not hasattr(orchestrator, 'db_session') or orchestrator.db_session is None:
        orchestrator.db_session = db
    conv_service = ConversationService(db)

    # 1. 验证对话是否存在且属于当前用户
    conversation = conv_service.get_conversation(conversation_id)
    if not conversation:
        logger.warning(f"[CHAT API] 对话 {conversation_id} 未找到。")
        raise HTTPException(status_code=404, detail="会话未找到")
    if conversation.user_id != current_user.id:
        logger.warning(f"[CHAT API] 用户{current_user.id} 无权访问对话 {conversation_id}")
        raise HTTPException(status_code=403, detail="无权访问其他用户的会话")

    # 2. 将用户消息存入数据库
    # 这是必要的，以便前端可以立即显示用户的消息
    user_message = conv_service.add_message_to_conversation(
        conversation_id=conversation_id,
        agent_id="user",
        content=message_in.content
    )
    from datetime import datetime
    conversation.last_active_at = datetime.utcnow()
    db.commit()
    logger.info(f"[CHAT API] 用户消息已存入数据库，消息 ID: {user_message.id}。")

    # 3. 调用 Orchestrator 处理任务
    # 我们需要传递完整的消息历史，而不仅仅是当前内容
    logger.info(f"[CHAT API] 准备调用 Orchestrator...")
    try:
        # 获取完整的消息历史
        messages_history = conv_service.get_messages(conversation_id)
        logger.info(f"[CHAT API] 从数据库获取到 {len(messages_history)} 条历史消息")
        
        messages_for_orchestrator = [
            {"role": msg.agent_id, "content": msg.content} for msg in messages_history
        ]
        logger.info(f"[CHAT API] 传递给Orchestrator的消息: {messages_for_orchestrator}")

        final_state = await orchestrator.get_chat_response(
            conversation_id=conversation_id,
            messages=messages_for_orchestrator,
            request_context={"current_user_id": current_user.id}
        )
        logger.info("[CHAT API] 成功收到 Orchestrator 的响应。")
        logger.debug(f"[CHAT API] Orchestrator 最终状态类型: {type(final_state)}")
        logger.debug(f"[CHAT API] Orchestrator 最终状态: {final_state}")

    except Exception as e:
        logger.opt(exception=True).error("[CHAT API] 调用 Orchestrator 时发生严重错误，完整异常信息:")
        import traceback
        logger.error(f"[CHAT API] Stack trace: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error processing message with Orchestrator: {str(e)}")

    # 4. 将 Orchestrator 的响应存入数据库
    if final_state is None:
        logger.error("[CHAT API] Orchestrator 返回了 None!")
        return user_message
        
    if isinstance(final_state, dict) and "content" in final_state and "agent_id" in final_state:
        logger.info("[CHAT API] 正在将 Agent 的回复存入数据库...")

        # 先保存中间消息（子Agent依次回复），确保前端的消息顺序正确
        if "intermediate_messages" in final_state:
            for msg in final_state["intermediate_messages"]:
                conv_service.add_message_to_conversation(
                    conversation_id=conversation_id,
                    agent_id=msg.get("agent_id", "agent"),
                    content=msg.get("content", "")
                )
                logger.info(f"[CHAT API] 中间消息已存入数据库，Agent: {msg.get('agent_id', 'agent')}")

        agent_message = conv_service.add_message_to_conversation(
            conversation_id=conversation_id,
            agent_id=final_state["agent_id"],
            content=final_state["content"]
        )
        logger.success(f"[CHAT API] Agent 消息已成功存入数据库，消息 ID: {agent_message.id}。")
        return agent_message
    else:
        logger.warning("[CHAT API] Orchestrator 返回的格式不正确，不创建 Agent 消息。")
        if isinstance(final_state, dict):
            logger.warning(f"[CHAT API] final_state的所有键: {list(final_state.keys())}")
        logger.warning(f"[CHAT API] final_state 完整内容: {final_state}")
        return user_message


# ============================================================
# SSE 流式端点
# ============================================================
# 设计要点：
# 1. 用 POST + fetch 接收 SSE（EventSource 只能 GET，POST 才能传 body + Auth）
# 2. 事件类型：user_message_saved / intermediate / token / artifact / final / error / done
# 3. fallback：如果 Orchestrator 不支持流式，自动降级为一次性返回
# 4. 持久化：user_message 立即落库；agent 产出在 final 时一次性落库


def _sse(event: str, data: dict) -> str:
    """格式化一个 SSE 事件"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _chat_stream_impl(req: ChatStreamRequest, current_user: UserModel) -> AsyncGenerator[str, None]:
    db = SessionLocal()
    """
    真正的流式生成器。

    协议：
      event: user_message_saved  -> {message_id, conversation_id, content}
      event: intermediate        -> {agent_id, content, type}
      event: token               -> {content}            ← LLM 流式
      event: artifact            -> {type, title, content, meta}
      event: final               -> {message_id, agent_id, content, ...}
      event: error               -> {message}
      event: done                -> {}                   ← 终止信号
    """
    orchestrator = get_orchestrator()
    conv_service = ConversationService(db)
    conversation_id = req.conversation_id

    # 1. 校验 + 落库用户消息
    if conversation_id:
        conversation = conv_service.get_conversation(conversation_id)
        if not conversation:
            yield _sse("error", {"message": f"对话 {conversation_id} 不存在"})
            yield _sse("done", {})
            db.close()
            return
        if conversation.user_id != current_user.id:
            yield _sse("error", {"message": "无权访问该对话"})
            yield _sse("done", {})
            db.close()
            return

    user_msg = None
    if conversation_id:
        user_msg = conv_service.add_message_to_conversation(
            conversation_id=conversation_id,
            agent_id="user",
            content=req.message,
        )
        from datetime import datetime
        conversation.last_active_at = datetime.utcnow()
        db.commit()
        yield _sse("user_message_saved", {
            "message_id": user_msg.id,
            "conversation_id": conversation_id,
            "content": req.message,
        })

    # 2. 构建消息历史
    history = []
    if conversation_id:
        for msg in conv_service.get_messages(conversation_id):
            history.append({"role": msg.agent_id, "content": msg.content})
    else:
        history = [{"role": "user", "content": req.message}]

    # 3. 解析 agent 配置
    agent_cfg = req.agent or {}
    agent_id = agent_cfg.get("id", "assistant")
    agent_name = agent_cfg.get("name", agent_id)
    llm_adapter = agent_cfg.get("llm_adapter")
    model_name = agent_cfg.get("model_name")
    system_prompt = agent_cfg.get("system_prompt")

    # 4. 调用 Orchestrator 处理
    #    优先尝试流式接口；回退到一次性接口
    final_content = ""
    intermediate_messages: List[Dict] = []
    artifacts: List[Dict] = []
    used_streaming = False

    try:
        # 4a. 尝试流式（仅对 @mention 直达 Agent 路径走 chat_stream）
        #     复杂任务走规划路径，暂不支持 token 级流式
        pending_intermediate = None  # 相邻同 agent 的 intermediate 批量
        if hasattr(orchestrator, "get_chat_stream"):
            try:
                async for chunk in orchestrator.get_chat_stream(
                    conversation_id=conversation_id or 0,
                    messages=history,
                    request_context={
                        "current_user_id": current_user.id,
                        "active_skills": req.active_skills or []
                    },
                    agent_override=agent_cfg if agent_cfg else None,
                ):
                    kind = chunk.get("type")

                    def flush_pending():
                        """把累积的 intermediate 推出去（普通函数，返回 generator）"""
                        nonlocal pending_intermediate
                        if pending_intermediate is not None:
                            im = pending_intermediate
                            intermediate_messages.append(im)
                            pending_intermediate = None
                            return _sse("intermediate", {
                                "agent_id": im["agent_id"],
                                "content": im["content"],
                                "type": im.get("type", "output"),
                            })
                        return None

                    if kind == "token":
                        used_streaming = True
                        fp = flush_pending()
                        if fp:
                            yield fp
                        yield _sse("token", {"content": chunk.get("content", "")})
                    elif kind == "intermediate":
                        # 提取 artifact（如果有）立即推送
                        for art in chunk.get("artifacts", []):
                            art_entry = {"type": art.get("type", "code"), "title": art.get("title", "代码"), "content": art.get("content", "")}
                            artifacts.append(art_entry)
                            yield _sse("artifact", art_entry)
                        # 相邻同 agent 合并批量
                        agent_id = chunk.get("agent_id", "agent")
                        content = chunk.get("content", "")
                        if pending_intermediate is not None and pending_intermediate["agent_id"] == agent_id:
                            pending_intermediate["content"] += "\n" + content
                        else:
                            fp = flush_pending()
                            if fp:
                                yield fp
                            pending_intermediate = {"agent_id": agent_id, "content": content, "type": chunk.get("type_detail", "output")}
                    elif kind == "artifact":
                        fp = flush_pending()
                        if fp:
                            yield fp
                        artifacts.append(chunk)
                        yield _sse("artifact", chunk)
                    elif kind == "thinking":
                        fp = flush_pending()
                        if fp:
                            yield fp
                        yield _sse("thinking", chunk)
                    elif kind == "final":
                        fp = flush_pending()
                        if fp:
                            yield fp
                        final_content = chunk.get("content", "")
                        intermediate_messages.extend(chunk.get("intermediate_messages", []))
                        artifacts.extend(chunk.get("artifacts", []))
                    elif kind == "error":
                        fp = flush_pending()
                        if fp:
                            yield fp
                        yield _sse("error", chunk)
            except Exception as e:
                logger.warning(f"[CHAT-STREAM] 流式路径失败，降级到一次性: {e}")
                used_streaming = False

        # 4b. 回退到一次性接口
        if not used_streaming:
            response = await orchestrator.get_chat_response(
                conversation_id=conversation_id or 0,
                messages=history,
                request_context={
                    "current_user_id": current_user.id,
                    "active_skills": req.active_skills or []
                },
                agent_override=agent_cfg if agent_cfg else None,
            )
            if isinstance(response, dict):
                final_content = response.get("content", "") or ""
                intermediate_messages = response.get("intermediate_messages", []) or []
                # 回退路径：先 yield intermediate 事件（如果有）
                for imsg in intermediate_messages:
                    yield _sse("intermediate", {
                        "agent_id": imsg.get("agent_id", "agent"),
                        "content": imsg.get("content", ""),
                        "type": imsg.get("type", "output"),
                    })
                # 一次性回复也模拟"打字机"——按 token 推
                if final_content:
                    # 按词切片，模拟流式（仅当内容较短时切词，长内容按字符）
                    if len(final_content) <= 200:
                        tokens = list(final_content)
                    else:
                        tokens = [final_content[i:i+8] for i in range(0, len(final_content), 8)]
                    for tok in tokens:
                        yield _sse("token", {"content": tok})
                        await asyncio.sleep(0.015)  # ~15ms / chunk

    except Exception as e:
        logger.exception("[CHAT-STREAM] Orchestrator 调用失败")
        yield _sse("error", {"message": f"处理消息失败: {e}"})
        yield _sse("done", {})
        db.close()
        return

    # 5. 持久化
    if conversation_id:
        # 中间消息
        for msg in intermediate_messages:
            try:
                conv_service.add_message_to_conversation(
                    conversation_id=conversation_id,
                    agent_id=msg.get("agent_id", "agent"),
                    content=msg.get("content", ""),
                )
            except Exception as e:
                logger.warning(f"[CHAT-STREAM] 落库中间消息失败: {e}")
        # 最终 Agent 回复
        final_agent_id = agent_id if agent_id else "assistant"
        try:
            agent_msg = conv_service.add_message_to_conversation(
                conversation_id=conversation_id,
                agent_id=final_agent_id,
                content=final_content,
            )
            final_message_id = agent_msg.id
        except Exception as e:
            logger.warning(f"[CHAT-STREAM] 落库最终消息失败: {e}")
            final_message_id = 0
    else:
        final_message_id = 0

    # 6. 发送 final 事件（前端据此收尾）
    yield _sse("final", {
        "message_id": final_message_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "content": final_content,
        "intermediate_messages": intermediate_messages,
        "artifacts": artifacts,
    })
    yield _sse("done", {})
    db.close()


@router.post("/stream")
async def chat_stream(
    req: ChatStreamRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """
    SSE 流式聊天端点。

    客户端用 fetch + ReadableStream 接收，每条 `event: <type>` 携带一个 JSON 数据。
    最终事件总是 `done`，浏览器据此关闭连接。
    """
    logger.info(f"[CHAT-STREAM] 用户{current_user.id} 收到流式消息: {req.message[:80]}...")
    return StreamingResponse(
        _chat_stream_impl(req, current_user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 关闭 nginx 缓冲（生产用）
            "Connection": "keep-alive",
        },
    )