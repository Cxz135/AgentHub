/* ===================== WebSocket 流式管理 ===================== */
// WebSocket 状态
const wsState = {
  socket: null,           // WebSocket 实例
  conversationId: null,   // 当前连接的 conversation ID
  status: 'disconnected', // disconnected | connecting | connected | error
  reconnectAttempts: 0,   // 重连尝试次数
  maxReconnectAttempts: 5,
  reconnectDelay: 1000,   // 重连延迟（毫秒）
  heartbeatInterval: null,
  currentHandlers: null,  // 当前消息处理器
};

// WebSocket URL
const WS_BASE = 'ws://localhost:8000/ws';

function getWsUrl(conversationId) {
  const token = localStorage.getItem('agenthub_token');
  return `${WS_BASE}/${conversationId}?token=${token || ''}`;
}

// 连接 WebSocket
function connectWebSocket(conversationId, handlers) {
  return new Promise((resolve, reject) => {
    // 如果已连接且是同一个 conversation，直接返回
    if (wsState.socket && wsState.status === 'connected' && wsState.conversationId === conversationId) {
      wsState.currentHandlers = handlers;
      resolve();
      return;
    }

    // 断开旧连接
    if (wsState.socket) {
      wsState.socket.close();
      wsState.socket = null;
    }

    wsState.conversationId = conversationId;
    wsState.status = 'connecting';
    wsState.currentHandlers = handlers;

    console.log(`[WS] 正在连接 conversation ${conversationId}...`);
    const ws = new WebSocket(getWsUrl(conversationId));

    ws.onopen = () => {
      console.log('[WS] 连接已建立');
      wsState.status = 'connected';
      wsState.reconnectAttempts = 0;
      
      // 启动心跳
      startHeartbeat();
      
      resolve();
    };

    ws.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        const msgType = msg.type || '';
        
        // 调用对应的处理器
        if (wsState.currentHandlers && wsState.currentHandlers[msgType]) {
          await wsState.currentHandlers[msgType](msg);
        } else if (msgType === 'pong') {
          // 心跳响应，不做处理
        } else if (msgType === 'ping') {
          // 服务端 ping，客户端自动 pong（WebSocket 会处理）
        } else {
          console.log('[WS] 收到未知消息类型:', msgType, msg);
        }
      } catch (e) {
        console.warn('[WS] 消息解析失败:', e);
      }
    };

    ws.onerror = (error) => {
      console.error('[WS] 连接错误:', error);
      wsState.status = 'error';
    };

    ws.onclose = (event) => {
      console.log(`[WS] 连接关闭: code=${event.code}, reason=${event.reason}`);
      wsState.status = 'disconnected';
      stopHeartbeat();

      // 如果非正常关闭，尝试重连
      if (event.code !== 1000 && event.code !== 1001 && wsState.reconnectAttempts < wsState.maxReconnectAttempts) {
        wsState.reconnectAttempts++;
        console.log(`[WS] ${wsState.reconnectAttempts}/${wsState.maxReconnectAttempts} 次重连中...`);
        setTimeout(() => {
          if (wsState.currentHandlers) {
            connectWebSocket(conversationId, wsState.currentHandlers).catch(console.error);
          }
        }, wsState.reconnectDelay * wsState.reconnectAttempts);
      }
    };

    wsState.socket = ws;
  });
}

// 断开 WebSocket
function disconnectWebSocket() {
  if (wsState.socket) {
    wsState.socket.close(1000, '用户主动断开');
    wsState.socket = null;
  }
  wsState.status = 'disconnected';
  wsState.conversationId = null;
  stopHeartbeat();
}

// 发送消息
function wsSend(message, activeSkills = [], agentOverride = null, attachments = []) {
  if (!wsState.socket || wsState.status !== 'connected') {
    console.error('[WS] 未连接，无法发送消息');
    return false;
  }
  
  const payload = {
    message: message,
    active_skills: activeSkills || [],
    agent_override: agentOverride
  };
  
  // 如果有附件，添加到 payload
  if (attachments && attachments.length > 0) {
    payload.attachments = attachments.map(att => ({
      name: att.name,
      url: att.url,
      type: att.type || att.mime_type,
      is_image: att.is_image,
      is_webpreview: att.is_webpreview,
      preview: att.preview,
      size: att.size,
    }));
  }
  
  wsState.socket.send(JSON.stringify(payload));
  console.log('[WS] 消息已发送:', message.slice(0, 50), attachments.length > 0 ? `+ ${attachments.length} 个附件` : '');
  return true;
}

// 启动心跳
function startHeartbeat() {
  stopHeartbeat();
  wsState.heartbeatInterval = setInterval(() => {
    if (wsState.socket && wsState.status === 'connected') {
      // WebSocket 自动保活，不需要额外发 ping
      // 但我们可以用它来检测连接状态
      // 如果需要自定义心跳，可以在这里发送
    }
  }, 30000); // 30 秒检查一次
}

// 停止心跳
function stopHeartbeat() {
  if (wsState.heartbeatInterval) {
    clearInterval(wsState.heartbeatInterval);
    wsState.heartbeatInterval = null;
  }
}