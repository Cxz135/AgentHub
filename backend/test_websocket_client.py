"""
WebSocket 测试客户端

用法:
    python test_websocket_client.py

测试 WebSocket 连接和消息收发
"""
import asyncio
import json
import websockets
import sys

# 配置
WEBSOCKET_URL = "ws://127.0.0.1:8000/ws/{conversation_id}?token={token}"

# 从 auth.py 复制的 token 创建逻辑（用于测试）
def create_test_token(user_id: int, secret_key: str = "your-secret-key-keep-it-safe") -> str:
    """创建测试用 JWT token"""
    from datetime import datetime, timedelta
    import base64
    import hmac
    
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    
    import json as json_module
    header_b64 = base64.urlsafe_b64encode(json_module.dumps(header).encode()).decode().rstrip('=')
    payload_b64 = base64.urlsafe_b64encode(json_module.dumps(payload).encode()).decode().rstrip('=')
    
    signature = hmac.new(
        secret_key.encode(),
        f"{header_b64}.{payload_b64}".encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"


async def test_websocket():
    """测试 WebSocket 连接"""
    import hashlib
    import getpass
    
    # 从数据库获取真实 token，或者使用测试 token
    # 这里假设你有一个有效的 JWT token
    test_token = None
    
    # 尝试从 .env 或环境变量获取 token
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    # 如果没有预设 token，尝试使用测试 token
    if not test_token:
        print("⚠️ 未找到预设 token，尝试使用测试 token...")
        # 注意：这需要后端 JWT_SECRET 为默认值
        test_token = create_test_token(1)  # user_id = 1
    
    # 对话 ID（可以改成你实际的 conversation_id）
    conversation_id = 1
    
    uri = f"ws://127.0.0.1:8000/ws/{conversation_id}?token={test_token}"
    
    print(f"🔌 连接到: {uri[:80]}...")
    
    try:
        async with websockets.connect(uri) as ws:
            print("✅ 连接成功！")
            
            # 发送测试消息
            test_message = "你好，请介绍一下你自己"
            print(f"\n📤 发送消息: {test_message}")
            
            await ws.send(json.dumps({
                "message": test_message,
                "active_skills": []
            }))
            
            # 接收响应
            print("\n📥 接收响应中...")
            message_count = 0
            final_content = ""
            
            async for msg_text in ws:
                msg = json.loads(msg_text)
                msg_type = msg.get("type", "unknown")
                
                if msg_type == "token":
                    content = msg.get("content", "")
                    print(content, end="", flush=True)
                    final_content += content
                elif msg_type == "thinking":
                    status = msg.get("status")
                    agent = msg.get("agent_id", "agent")
                    if status == "thinking":
                        print(f"\n🤔 [{agent}] 思考中...", end="", flush=True)
                    else:
                        print(f" ✅")
                elif msg_type == "intermediate":
                    print(f"\n📝 [{msg.get('agent_id', 'agent')}] {msg.get('content', '')[:100]}...")
                elif msg_type == "artifact":
                    print(f"\n🎨 [产物] {msg.get('title', '未命名')}")
                elif msg_type == "final":
                    print(f"\n\n🎉 完成！最终内容长度: {len(final_content)}")
                    break
                elif msg_type == "error":
                    print(f"\n❌ 错误: {msg.get('message', '未知错误')}")
                    break
                elif msg_type == "pong":
                    print("🏓 心跳响应")
                elif msg_type == "user_message_saved":
                    print(f"💾 消息已保存: {msg}")
                else:
                    print(f"\n收到未知消息类型: {msg_type}")
                
                message_count += 1
                if message_count > 1000:  # 防止无限循环
                    print("\n⚠️ 消息数量过多，停止接收")
                    break
            
            print(f"\n总共收到 {message_count} 条消息")
            
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"\n❌ 连接断开: {e}")
        return False
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        return False
    
    return True


async def test_with_auth_failure():
    """测试认证失败的情况"""
    print("\n\n=== 测试认证失败 ===")
    uri = "ws://127.0.0.1:8000/ws/1?token=invalid_token"
    
    try:
        async with websockets.connect(uri) as ws:
            print("❌ 不应该成功连接！")
            return False
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"✅ 预期中的断开: {e.code} - {e.reason}")
        return True
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return True


if __name__ == "__main__":
    print("=" * 60)
    print("AgentHub WebSocket 测试客户端")
    print("=" * 60)
    
    # 运行主要测试
    success = asyncio.run(test_websocket())
    
    if success:
        print("\n✅ WebSocket 测试通过！")
    else:
        print("\n❌ WebSocket 测试失败")
        sys.exit(1)