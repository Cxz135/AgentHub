# app/api/websocket.py
"""
WebSocket 聊天端点

支持双向实时通信，复用 orchestrator 的流式生成器。
认证通过 query 参数传递 token: ws://host/ws/123?token=xxx
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from sqlalchemy.orm import Session
from jose import JWTError, jwt
import asyncio
import json
import time
from typing import Optional, Dict, Any

from backend.app.dependencies import get_db, get_orchestrator
from backend.models.user import User as UserModel
from backend.services.conversation_service import ConversationService
from backend.utils.logger import logger

import os
from dotenv import load_dotenv
load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-keep-it-safe")
ALGORITHM = "HS256"

router = APIRouter()


class ConnectionManager:
    """
    WebSocket 连接管理器
    
    功能：
    - 管理所有活跃的 WebSocket 连接
    - 支持心跳保活
    - 处理断线重连
    """
    
    def __init__(self):
        # conversation_id -> WebSocket
        self.active_connections: Dict[int, WebSocket] = {}
        # conversation_id -> last_ping_timestamp
        self.last_ping: Dict[int, float] = {}
        # 心跳间隔（秒）
        self.heartbeat_interval = 30
        # 连接超时（秒）
        self.connection_timeout = 120
    
    async def connect(self, websocket: WebSocket, conversation_id: int):
        """接受并注册 WebSocket 连接"""
        await websocket.accept()
        
        # 如果该 conversation 已有一个连接，先关闭旧的
        if conversation_id in self.active_connections:
            old_ws = self.active_connections[conversation_id]
            try:
                await old_ws.close(code=1001, reason="新连接取代旧连接")
            except Exception:
                pass
        
        self.active_connections[conversation_id] = websocket
        self.last_ping[conversation_id] = time.time()
        logger.info(f"[WS] 连接已建立，conversation_id={conversation_id}，当前活跃连接数: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket, conversation_id: int):
        """断开并移除 WebSocket 连接"""
        if conversation_id in self.active_connections:
            del self.active_connections[conversation_id]
        if conversation_id in self.last_ping:
            del self.last_ping[conversation_id]
        logger.info(f"[WS] 连接已断开，conversation_id={conversation_id}，当前活跃连接数: {len(self.active_connections)}")
    
    async def send(self, conversation_id: int, data: dict) -> bool:
        """向指定 conversation 的连接发送数据"""
        if conversation_id in self.active_connections:
            try:
                ws = self.active_connections[conversation_id]
                await ws.send_json(data)
                return True
            except Exception as e:
                logger.warning(f"[WS] 发送消息失败: {e}")
                await self.disconnect(self.active_connections[conversation_id], conversation_id)
                return False
        return False
    
    async def broadcast(self, data: dict):
        """广播消息到所有连接"""
        for conv_id, ws in list(self.active_connections.items()):
            try:
                await ws.send_json(data)
            except Exception:
                await self.disconnect(ws, conv_id)
    
    def update_ping(self, conversation_id: int):
        """更新心跳时间戳"""
        self.last_ping[conversation_id] = time.time()
    
    async def check_connections(self):
        """检查所有连接的超时情况，断开超时的连接"""
        now = time.time()
        timeout_connections = []
        for conv_id, last_ping_time in list(self.last_ping.items()):
            if now - last_ping_time > self.connection_timeout:
                timeout_connections.append(conv_id)
        
        for conv_id in timeout_connections:
            if conv_id in self.active_connections:
                logger.warning(f"[WS] 连接超时，断开 conversation_id={conv_id}")
                try:
                    await self.active_connections[conv_id].close(code=1001, reason="连接超时")
                except Exception:
                    pass
                await self.disconnect(self.active_connections[conv_id], conv_id)


# 全局连接管理器
manager = ConnectionManager()


def decode_token_from_query(token: str) -> Optional[int]:
    """
    从 query token 解码出 user_id
    
    Args:
        token: JWT token string
        
    Returns:
        user_id if valid, None otherwise
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        return user_id
    except (JWTError, ValueError, TypeError) as e:
        logger.warning(f"[WS] token解码失败: {e}")
        return None


async def authenticate_websocket(websocket: WebSocket, db: Session) -> Optional[UserModel]:
    """
    认证 WebSocket 连接
    
    Args:
        websocket: WebSocket 实例
        db: 数据库 session
        
    Returns:
        UserModel if authenticated, None otherwise
    """
    # 从 query 参数获取 token
    token = websocket.query_params.get("token")
    if not token:
        logger.warning("[WS] 认证失败: 未提供 token")
        await websocket.close(code=4001, reason="需要 token 参数")
        return None
    
    user_id = decode_token_from_query(token)
    if not user_id:
        logger.warning("[WS] 认证失败: token 无效")
        await websocket.close(code=4001, reason="token 无效或已过期")
        return None
    
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        logger.warning(f"[WS] 认证失败: 用户 {user_id} 不存在")
        await websocket.close(code=4001, reason="用户不存在")
        return None
    
    logger.info(f"[WS] 认证成功: user={user.username} id={user.id}")
    return user


def ws_format_message(msg_type: str, data: dict) -> str:
    """
    格式化 WebSocket 消息为 JSON 字符串
    
    Args:
        msg_type: 消息类型 (token, intermediate, artifact, thinking, final, error, ping, pong)
        data: 消息数据
        
    Returns:
        JSON string
    """
    return json.dumps({"type": msg_type, **data}, ensure_ascii=False)


@router.websocket("/ws/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: int,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    WebSocket 聊天端点

    消息格式（客户端发送）：
        {"message": "用户消息", "active_skills": ["skill1"], "agent_override": {...}, "use_long_term_memory": true}

    消息格式（服务端推送）：
        - {"type": "token", "content": "..."}  # token 流
        - {"type": "thinking", "agent_id": "...", "status": "thinking|done"}  # thinking 状态
        - {"type": "intermediate", "agent_id": "...", "content": "...", "type": "..."}  # 中间消息
        - {"type": "artifact", "type": "...", "title": "...", "content": "..."}  # 产物
        - {"type": "final", "content": "...", "intermediate_messages": [...]}  # 最终回复
        - {"type": "error", "message": "..."}  # 错误
        - {"type": "pong"}  # 心跳响应
        - {"type": "context_loaded", "pinned_count": N, "recent_count": M}  # 上下文加载完成

    Args:
        conversation_id: 对话 ID
        token: JWT token（query 参数）
    """
    # 认证
    user = await authenticate_websocket(websocket, db)
    if not user:
        return
    
    # 建立连接
    await manager.connect(websocket, conversation_id)
    
    # 获取 orchestrator
    orchestrator = get_orchestrator()
    if not hasattr(orchestrator, 'db_session') or orchestrator.db_session is None:
        orchestrator.db_session = db
    
    conv_service = ConversationService(db)
    
    # 确保 conversation 存在
    conversation = conv_service.get_conversation(conversation_id)
    if not conversation or conversation.user_id != user.id:
        await websocket.close(code=4003, reason="对话不存在或无权限")
        return
    
    # 启动心跳任务
    heartbeat_task = asyncio.create_task(_heartbeat(websocket, conversation_id))
    
    try:
        # 主消息循环
        while True:
            # 接收客户端消息（等待超时改为30秒，因为客户端应该很快发送消息）
            try:
                raw_data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30  # 30秒超时足够客户端发送消息
                )
            except asyncio.TimeoutError:
                logger.warning(f"[WS] 接收消息超时，conversation_id={conversation_id}")
                break
            
            # 更新心跳
            manager.update_ping(conversation_id)
            
            # 解析消息
            try:
                client_msg = json.loads(raw_data)
            except json.JSONDecodeError:
                logger.warning(f"[WS] 收到无效 JSON: {raw_data[:100]}")
                await websocket.send_text(ws_format_message("error", {"message": "无效的 JSON 格式"}))
                continue
            
            # 处理 ping
            if client_msg.get("type") == "ping":
                await websocket.send_text(ws_format_message("pong", {}))
                continue
            
            # 处理聊天消息
            message = client_msg.get("message", "")
            active_skills = client_msg.get("active_skills", [])
            agent_override = client_msg.get("agent_override")
            use_long_term_memory = client_msg.get("use_long_term_memory", False)
            attachments = client_msg.get("attachments", [])  # 前端发送的附件

            if not message and not attachments:
                await websocket.send_text(ws_format_message("error", {"message": "消息内容为空"}))
                continue

            # 构建附件 metadata
            msg_meta_data = {}
            if attachments:
                msg_meta_data["attachments"] = attachments
                # 如果有图片，附加到消息内容中供 Agent 参考
                image_urls = [att.get("url") for att in attachments if att.get("is_image")]
                if image_urls:
                    msg_meta_data["image_urls"] = image_urls

            # 解析 mentions（@agent）
            mentioned_agents = []
            if message:
                # 匹配 @agent_name 或 @agent_id
                import re
                mention_pattern = r'@([\w\u4e00-\u9fa5]+)'
                found = re.findall(mention_pattern, message)
                if found:
                    # 从 squad 中解析可用 agent 列表
                    squad = conversation.squad_config or {}
                    agents = squad.get('agents', [])
                    agent_ids = {a.get('id') or a.get('name') for a in agents}
                    agent_names = {a.get('name') for a in agents}
                    for name in found:
                        if name in agent_ids or name in agent_names:
                            mentioned_agents.append(name)

            # 保存用户消息（content 保持纯文本，attachments 放在 metadata）
            user_msg = conv_service.add_message_to_conversation(
                conversation_id=conversation_id,
                agent_id="user",
                content=message,
                metadata=msg_meta_data if msg_meta_data else None,
                mentions=mentioned_agents if mentioned_agents else None
            )
            from datetime import datetime
            conversation.last_active_at = datetime.utcnow()
            db.commit()
            await websocket.send_text(ws_format_message("user_message_saved", {
                "message_id": user_msg.id,
                "conversation_id": conversation_id
            }))

            # 构建消息上下文（支持置顶消息和长期记忆）
            if use_long_term_memory:
                context_data = conv_service.rebuild_context_with_long_term_memory(
                    conversation_id=conversation_id,
                    user_id=user.id,
                    limit=50
                )
            else:
                context_data = conv_service.get_conversation_context(
                    conversation_id=conversation_id,
                    limit=50,
                    include_pinned=True
                )

            logger.info(f"[WS] context_data 加载完成, 共 {len(context_data)} 条消息, conversation_id={conversation_id}")
            pinned_count = sum(1 for m in context_data if m.get("is_pinned"))
            await websocket.send_text(ws_format_message("context_loaded", {
                "pinned_count": pinned_count,
                "total_count": len(context_data),
                "use_long_term_memory": use_long_term_memory
            }))

            history = [{"role": m["role"], "content": m["content"]} for m in context_data]

            request_context = {
                "current_user_id": user.id,
                "active_skills": active_skills or [],
                "use_long_term_memory": use_long_term_memory,
                "pinned_messages": [m for m in context_data if m.get("is_pinned")]
            }

            try:
                done = False
                async for chunk in orchestrator.get_chat_stream(
                    conversation_id=conversation_id,
                    messages=history,
                    request_context=request_context,
                    agent_override=agent_override
                ):
                    kind = chunk.get("type")
                    
                    if kind == "token":
                        await websocket.send_text(ws_format_message("token", {
                            "content": chunk.get("content", "")
                        }))
                    elif kind == "thinking":
                        await websocket.send_text(ws_format_message("thinking", {
                            "agent_id": chunk.get("agent_id", "agent"),
                            "status": chunk.get("status", "thinking")
                        }))
                    elif kind == "intermediate":
                        # 推送 artifact（如果有）
                        for art in chunk.get("artifacts", []):
                            await websocket.send_text(ws_format_message("artifact", {
                                "artType": art.get("type", "code"),
                                "title": art.get("title", ""),
                                "content": art.get("content", "")
                            }))
                    elif kind == "artifact":
                        logger.info(f"[WS] Sending artifact: artType={chunk.get('art_type')}, title={chunk.get('title')}")
                        await websocket.send_text(ws_format_message("artifact", {
                            "artType": chunk.get("art_type", "code"),
                            "title": chunk.get("title", ""),
                            "content": chunk.get("content", "")
                        }))
                        
                        # 保存 intermediate 消息到数据库
                        inter_msg = None
                        try:
                            inter_msg = conv_service.add_message_to_conversation(
                                conversation_id=conversation_id,
                                agent_id=chunk.get("agent_id", "agent"),
                                content=chunk.get("content", ""),
                            )
                        except Exception as e:
                            logger.warning(f"[WS] 保存 intermediate 消息失败: {e}")
                        
                        await websocket.send_text(ws_format_message("intermediate", {
                            "message_id": inter_msg.id if inter_msg else None,
                            "agent_id": chunk.get("agent_id", "agent"),
                            "content": chunk.get("content", ""),
                            "type": chunk.get("type", "output")
                        }))
                    elif kind == "final":
                        final_content = chunk.get("content", "")
                        
                        # 保存 AI 回复
                        final_agent_msg = conv_service.add_message_to_conversation(
                            conversation_id=conversation_id,
                            agent_id="assistant",
                            content=final_content
                        )
                        
                        await websocket.send_text(ws_format_message("final", {
                            "message_id": final_agent_msg.id,
                            "content": final_content,
                            "intermediate_messages": chunk.get("intermediate_messages", [])
                        }))
                        
                        # 收到 final 后，优雅关闭连接
                        done = True
                        logger.info(f"[WS] 消息处理完成，关闭连接，conversation_id={conversation_id}")
                    elif kind == "error":
                        await websocket.send_text(ws_format_message("error", {
                            "message": chunk.get("message", "未知错误")
                        }))
                    
                    # 更新心跳
                    manager.update_ping(conversation_id)
                
                # 如果收到 final，正常关闭连接
                if done:
                    try:
                        await websocket.close(code=1000, reason="处理完成")
                        logger.info(f"[WS] 已发送正常关闭，conversation_id={conversation_id}")
                    except Exception:
                        pass
                    break
                    
            except Exception as e:
                logger.error(f"[WS] orchestrator 流式处理出错: {e}")
                await websocket.send_text(ws_format_message("error", {
                    "message": f"处理出错: {str(e)}"
                }))
                
    except WebSocketDisconnect:
        logger.info(f"[WS] 客户端断开连接，conversation_id={conversation_id}")
    except Exception as e:
        logger.error(f"[WS] WebSocket 错误: {e}")
    finally:
        # 取消心跳任务
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        # 断开连接
        await manager.disconnect(websocket, conversation_id)


async def _heartbeat(websocket: WebSocket, conversation_id: int):
    """
    心跳任务：定期发送 ping 维持连接
    
    Args:
        websocket: WebSocket 实例
        conversation_id: 对话 ID
    """
    try:
        while True:
            await asyncio.sleep(manager.heartbeat_interval)
            try:
                await websocket.send_text(ws_format_message("ping", {}))
                logger.debug(f"[WS] 发送心跳，conversation_id={conversation_id}")
            except Exception:
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"[WS] 心跳任务异常: {e}")


@router.get("/ws/connections")
async def get_connection_count():
    """获取当前活跃连接数（调试用）"""
    return {
        "active_connections": len(manager.active_connections),
        "connections": list(manager.active_connections.keys())
    }