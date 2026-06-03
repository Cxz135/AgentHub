import asyncio
import websockets
import json
import uuid
from pprint import pprint

# --- 配置 ---
# 要连接的 WebSocket 服务器地址
# 确保这里的端口号 (8000) 和你 FastAPI 应用运行的端口一致
WEBSOCKET_URL = "ws://127.0.0.1:8000/ws/"

# 要测试的指令
# 我们将 @tongyi 并给出一个需要写代码的任务，以触发工具调用流程
# 你可以修改这个指令来测试不同的场景
# 例如: "@echo hello world" 来测试 EchoAgent
# 或 "@tongyi 解释一下什么是人工智能" 来测试不带工具调用的最终答案
MESSAGE_TO_SEND = "@tongyi 帮我用 python 写一个斐波那契数列函数"


async def run_test_client():
    """
    运行一个简单的 WebSocket 客户端来测试 AgentHub。
    """
    # 为这次测试创建一个唯一的会话 ID
    conversation_id = str(uuid.uuid4())
    uri = f"{WEBSOCKET_URL}{conversation_id}"

    print("=" * 50)
    print(f"🚀 开始测试 AgentHub WebSocket")
    print(f"   - 服务器 URI: {uri}")
    print(f"   - 会话 ID: {conversation_id}")
    print("=" * 50)

    try:
        # 连接到 WebSocket 服务器
        async with websockets.connect(uri) as websocket:
            print(f"\n[1/3] 🟢 连接成功！")

            # 发送测试消息
            print(f"[2/3] 💬 正在发送消息...")
            print(f"      内容: '{MESSAGE_TO_SEND}'")
            await websocket.send(MESSAGE_TO_SEND)

            # 等待并接收服务器的回复
            print(f"[3/3] 📥 正在等待 Agent 的最终回复... (这可能需要一些时间)")
            response = await websocket.recv()

            print("\n" + "=" * 50)
            print("🎉 收到最终回复！")
            print("=" * 50)

            # 解析并格式化打印回复
            try:
                response_data = json.loads(response)
                pprint(response_data)
            except json.JSONDecodeError:
                print("收到的回复不是有效的 JSON 格式:")
                print(response)

    except websockets.exceptions.ConnectionClosedError as e:
        print(f"\n❌ 连接失败或被关闭: {e}")
        print("   请确保你的 FastAPI 后端服务正在运行，并且端口号正确。")
    except Exception as e:
        print(f"\n❌ 测试过程中发生未知错误: {e}")


if __name__ == "__main__":
    # 运行测试客户端
    # 如果你遇到 "pip install websockets" 的提示，请在终端中运行它
    try:
        asyncio.run(run_test_client())
    except KeyboardInterrupt:
        print("\n测试被用户中断。")