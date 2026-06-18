/* ===================== Step 6 ‑ Interactions ===================== */

/* ---- 输入框：实时识别 @ ---- */
function onChatInputChange(e) {
  const ta = e.target;
  const cursor = ta.selectionStart;
  const before = ta.value.slice(0, cursor);
  const lastAt = before.lastIndexOf('@');
  const lastHash = before.lastIndexOf('#');
  // 取最近的触发符
  const trigger = lastAt > lastHash ? '@' : (lastHash > lastAt ? '#' : null);
  const triggerIdx = trigger === '@' ? lastAt : lastHash;
  // 仅在触发符后紧跟空格/换行之前显示
  if (trigger && triggerIdx >= 0 && !/\s/.test(before.slice(triggerIdx+1))) {
    showAgentPopover(ta, trigger);
  } else {
    hideMentionPopover();
  }
  // 编辑意图实时提示（# 或自然语言）
  const hint = $('#input-hint');
  if (hint) {
    if (ta.value.includes('#')) {
      hint.innerHTML = `<span class="material-symbols-outlined text-[12px]">edit_square</span> # 模式：直接修改 Agent 配置（发送后弹出变更预览）`;
      hint.classList.remove('hidden');
      hint.classList.add('text-primary','flex','items-center','gap-1');
    } else if (parseEditIntent(ta.value)) {
      hint.textContent = '检测到编辑指令 — 发送后会弹出变更预览';
      hint.classList.remove('hidden');
      hint.classList.add('text-primary');
    } else {
      hint.classList.add('hidden');
    }
  }
}

function onChatInputKeydown(e) {
  if (e.key === 'Escape') hideMentionPopover();
  const isImeComposing = e.isComposing || e.keyCode === 229;
  if (isImeComposing) return;
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
}

/* ---- 自然语言编辑意图解析 ---- */
function parseEditIntent(text) {
  if (!text) return null;
  const m = getMission(); if (!m) return null;
  const skillNames = getAllSkills().map(s => s.name);

  const matchAgent = (frag) => {
    if (!frag) return null;
    const norm = (s) => s.toLowerCase().replace(/[\s师员]+/g,'');
    return m.squad.agents.find(a =>
      a.name.toLowerCase().includes(frag.toLowerCase()) ||
      norm(a.name).includes(norm(frag)) ||
      (a.role || '').toLowerCase().includes(frag.toLowerCase())
    );
  };

  /* ===== 显式 # 语法 — 最高优先级 ===== */
  // 形如：#AgentName 加 web_search 技能 / #AgentName 移除 chart_render / #AgentName 更关注新能源
  const hashMatch = text.match(/#([^\s#@]+)\s+(.+)/);
  if (hashMatch) {
    const ag = matchAgent(hashMatch[1]);
    if (!ag) return null;
    const body = hashMatch[2].trim();

    // # 后再检查 add/remove/prompt
    const addSk = skillNames.find(s => new RegExp('(加上?|增加|新增|添加|装上|配上|开启|启用)\\s*' + s, 'i').test(body));
    if (addSk && !ag.skills.includes(addSk)) {
      return {
        agentId: ag.id,
        summary: `为 ${ag.name} 添加 ${addSk} 技能`,
        addedSkills: [addSk], removedSkills: [], promptDiff: []
      };
    }
    const rmSk = skillNames.find(s => new RegExp('(去掉|移除|关闭|禁用|删除|停用)\\s*' + s, 'i').test(body));
    if (rmSk && ag.skills.includes(rmSk)) {
      return {
        agentId: ag.id,
        summary: `从 ${ag.name} 移除 ${rmSk} 技能`,
        addedSkills: [], removedSkills: [rmSk], promptDiff: []
      };
    }
    // 默认：把整段视作 prompt 调整
    const oldLines = ag.systemPrompt.split('\n');
    return {
      agentId: ag.id,
      summary: `调整 ${ag.name} 的配置：${body.slice(0,28)}${body.length>28?'...':''}`,
      addedSkills: [], removedSkills: [],
      promptDiff: [
        ...oldLines.map(l => ({type:'keep', text:l})),
        { type:'add', text: `补充指令（# 直接修改）：${body}` }
      ]
    };
  }

  // 自然语言匹配
  const addPat = /(给|让|为)\s*([^,，。：:]+?)\s*(加上?|增加|新增|添加|装上|配上|开启)\s*([a-z_]+)\s*(技能|工具)?/i;
  const removePat = /(去掉|移除|关闭|禁用|删除)\s*([^,，。：:]+?)\s*的?\s*([a-z_]+)\s*(技能|工具)?/i;
  const promptPat = /(让|把)\s*([^,，。：:]+?)\s*(更|更加|偏向|关注|聚焦|强调|不要|减少)/;

  let r;
  if ((r = text.match(addPat))) {
    const ag = matchAgent(r[2]); if (!ag) return null;
    const sk = skillNames.find(s => s.toLowerCase() === r[4].toLowerCase());
    if (!sk) return null;
    if (ag.skills.includes(sk)) return null;
    return {
      agentId: ag.id,
      summary: `为 ${ag.name} 添加 ${sk} 技能`,
      addedSkills: [sk], removedSkills: [], promptDiff: []
    };
  }
  if ((r = text.match(removePat))) {
    const ag = matchAgent(r[2]); if (!ag) return null;
    const sk = r[3];
    if (!ag.skills.includes(sk)) return null;
    return {
      agentId: ag.id,
      summary: `从 ${ag.name} 移除 ${sk} 技能`,
      addedSkills: [], removedSkills: [sk], promptDiff: []
    };
  }
  if ((r = text.match(promptPat))) {
    const ag = matchAgent(r[2]); if (!ag) return null;
    const oldLines = ag.systemPrompt.split('\n');
    const addition = `补充指令（来自用户自然语言修改）：${text}`;
    return {
      agentId: ag.id,
      summary: `调整 ${ag.name} 的 System Prompt 倾向性`,
      addedSkills: [], removedSkills: [],
      promptDiff: [
        ...oldLines.map(l => ({type:'keep', text:l})),
        {type:'add', text: addition}
      ]
    };
  }
  return null;
}

/* ---- 群聊 @ 多 Agent 解析 ---- */
function parseMentions(text) {
  const m = getMission(); if (!m) return [];
  const out = [];
  m.squad.agents.forEach(a => {
    if (text.includes('@' + a.name)) out.push(a);
  });
  // 也检查自建 Agent（数据库中的自定义 Agent）
  (state.customAgents || []).forEach(a => {
    if (text.includes('@' + a.name) && !out.some(x => x.name === a.name)) {
      out.push({ ...a, role: a.description || a.system_prompt || '', skills: a.tools || [] });
    }
  });
  return out;
}

function simulateGroupChat(text, mentioned) {
  const run = getRun();
  const m = getMission();
  const names = mentioned.map(x => x.name).join(', ');
  let waitReply = `已收到，正在向 @${names} 发起请求...`;
  run.conversation.push({ type:'agent', agent:'orchestrator', icon:'hub', time: now(), text: waitReply, thinking: true });
  render();

  const conversationId = parseInt((m.id||'').replace('mis_','')) || 0;
  let finalContent = '';
  let finalIntermed = [];
  let hadIntermed = false;

  // WebSocket 消息处理器
  const wsHandlers = {
    user_message_saved(d) {
      // 找到最后一条用户消息，绑定数据库ID
      const lastUser = run.conversation.findLast(m => m.type === 'user');
      if (lastUser) lastUser.dbId = d.message_id;
    },
    thinking(d) {
      const agentId = d.agent_id || 'orchestrator';
      let bubble = run.conversation.find(m => m.type === 'agent' && m.agent === agentId && m.thinking);
      if (d.status === 'thinking') {
        if (!bubble) {
          bubble = { type:'agent', agent:agentId, icon:agentId==='orchestrator'?'hub':'smart_toy', time:now(), text:'思考中...', thinking: true };
          run.conversation.push(bubble);
        }
      } else if (d.status === 'done' && bubble) {
        const idx = run.conversation.indexOf(bubble);
        if (idx !== -1) run.conversation.splice(idx, 1);
      }
      render(); scrollChatToBottom();
    },
    intermediate(d) {
      hadIntermed = true;
      const agentId = d.agent_id || 'agent';
      const thinkBubble = run.conversation.find(m => m.type === 'agent' && m.agent === agentId && m.thinking);
      if (thinkBubble) {
        const idx = run.conversation.indexOf(thinkBubble);
        if (idx !== -1) run.conversation.splice(idx, 1);
      }
      const existBubble = run.conversation.find(m => m.type === 'agent' && m.agent === agentId && !m.thinking && m.text === d.content);
      if (!existBubble) {
        run.conversation.push({ type:'agent', agent:d.agent_id, icon:d.agent_id==='orchestrator'?'hub':'smart_toy', time:now(), text:d.content, dbId: d.message_id });
      }
      render(); scrollChatToBottom();
    },
    token(d) {
      finalContent += d.content;
      let tokenBubble = run.conversation.find(m => m.type === 'agent' && m.agent === 'orchestrator' && m.isTokenStream);
      if (!tokenBubble) {
        tokenBubble = { type:'agent', agent:'orchestrator', icon:'hub', time:now(), text:'', isTokenStream: true };
        run.conversation.push(tokenBubble);
      }
      tokenBubble.text = finalContent;
      render(); scrollChatToBottom();
    },
    artifact(d) {
      run.conversation.push({
        type:'artifact', agent:names || '',
        icon:'code', time:now(),
        artType:d.artType || d.art_type || d.type || 'code', title:d.title || '产物', content:d.content
      });
      render(); scrollChatToBottom();
    },
    final(d) {
      finalContent = d.content || finalContent;
      finalIntermed = d.intermediate_messages || [];
      
      // 清理 thinking 气泡和 token 流式气泡
      const thinkIdx = run.conversation.findIndex(m => m.type === 'agent' && m.thinking);
      if (thinkIdx !== -1) run.conversation.splice(thinkIdx, 1);
      const tokenIdx = run.conversation.findIndex(m => m.type === 'agent' && m.isTokenStream);
      if (tokenIdx !== -1) run.conversation.splice(tokenIdx, 1);
      
      // 最终回复（避免重复）
      const lastAgent = run.conversation.findLast(m => m.type === 'agent');
      if (!lastAgent || lastAgent.text !== finalContent) {
        run.conversation.push({ type:'agent', agent:'orchestrator', icon:'hub', time:now(), text: finalContent || '已完成', dbId: d.message_id });
      } else if (lastAgent) {
        lastAgent.dbId = d.message_id;
      }

      render(); scrollChatToBottom();
      // 刷新侧边栏排序（最近活跃）
      loadMissions();
    },
    error(d) {
      const thinkIdx = run.conversation.findIndex(m => m.type === 'agent' && m.thinking);
      if (thinkIdx !== -1) run.conversation.splice(thinkIdx, 1);
      run.conversation.push({ type:'agent', agent:'orchestrator', icon:'hub', time: now(), text: '抱歉，调用后端处理 @ 请求时出错了：' + (d.message || '未知错误') });
      render(); scrollChatToBottom();
    }
  };

  // 连接 WebSocket 并发送消息
  (async () => {
    try {
      await connectWebSocket(conversationId, wsHandlers);
      wsSend(text, state.activeSkills || []);
    } catch (error) {
      const thinkIdx = run.conversation.findIndex(m => m.type === 'agent' && m.thinking);
      if (thinkIdx !== -1) run.conversation.splice(thinkIdx, 1);
      run.conversation.push({ type:'agent', agent:'orchestrator', icon:'hub', time: now(), text: '抱歉，WebSocket 连接失败：' + error.message });
      render();
    }
  })();
}

function agentReplyMock(a, userText, idx) {
  const tail = ['先从我的角度切入','按职责给出我的判断','按我的能力给出补充意见','输出我这部分的草稿'][idx % 4];
  return `好的，关于"${userText.replace(/@\S+\s*/g,'').slice(0,40)}"，${tail}：基于我擅长的 ${a.skills.slice(0,2).join(' / ') || '通用'} 能力，我会输出对应内容。`;
}

/* ---- sendChat 升级版 ---- */
function sendChat() {
  const ta = $('#chat-input'); if (!ta) return;
  const text = ta.value.trim();
  const attachments = state.pendingAttachments || [];
  if (!text && attachments.length === 0) return;
  ta.value = '';
  hideMentionPopover();

  // Quick Run 分支
  if (state.view === 'quickRun') {
    const qr = state.quickRun;
    qr.conversation.push({ type:'user', who:'You', time: now(), text });
    qr.turns += 1;
    render();
    setTimeout(() => {
      qr.conversation.push({
        type:'agent', agent:'Quick Assistant', icon:'bolt', time: now(),
        text: `已处理你的请求："${text.slice(0,60)}"。这是一段示意回复，真实环境会基于通用 Agent 完成。`
      });
      render();
    }, 700);
    return;
  }

  // Mission 分支
  const run = getRun();
  const m0 = getMission();
  const cfg = m0 ? ensureMissionKbConfig(m0) : { triggerMode:'auto', bindings:[] };
  const enabledBindings = (cfg.bindings||[]).filter(b => b.enabled);

  // === SLASH 模式：以 / 开头 → 单 KB 检索（不走 intent/mentions）===
  if (cfg.triggerMode === 'slash' && text.startsWith('/')) {
    run.conversation.push({ type:'user', who:'You', time: now(), text });
    if (!enabledBindings.length) {
      run.conversation.push({ type:'system', text:'当前 Mission 未启用任何知识库，请到右栏「知识库」Tab 绑定/启用后再使用 / 触发' });
      render();
      return;
    }
    const parsed = parseSlashCommand(text, enabledBindings);
    if (parsed.error) {
      run.conversation.push({ type:'system', text: parsed.error });
      render();
      return;
    }
    const binding = enabledBindings.find(b => b.kbId === parsed.kbId);
    const hits = mockRagQuery({ kbIds:[parsed.kbId], query: parsed.query, topK: (binding && binding.topK) || 5 });
    if (hits.length) {
      run.conversation.push({ type:'rag', time: now(), hits, query: parsed.query, kbIds:[parsed.kbId], collapsed: true });
    }
    render();
    setTimeout(() => {
      const a = m0.squad.agents[0];
      if (!a) return;
      let reply;
      if (!hits.length) {
        const kbName = state.kbs.list.find(k => k.id === parsed.kbId)?.name || parsed.kbId;
        reply = `已收到。在知识库「${kbName}」中未找到与「${parsed.query}」相关的片段。`;
      } else {
        const docs = [...new Set(hits.map(h => h.docName))];
        reply = `基于检索到的 ${hits.length} 条片段，回答如下：\n\n${hits[0].text.slice(0, 180)}${hits[0].text.length>180?'…':''}\n\n（已参考：${docs.join('，')}）`;
      }
      run.conversation.push({ type:'agent', agent:a.name, icon:a.icon, time: now(), text: reply });
      render();
    }, 700);
    return;
  }

  // === AUTO 模式 / 无 RAG：先 push 用户消息 ===
  run.conversation.push({ type:'user', who:'You', time: now(), text, attachments: attachments.length > 0 ? attachments : undefined });

  // AUTO RAG 注入：检索并推 rag 消息
  let autoHits = null;
  if (cfg.triggerMode === 'auto' && enabledBindings.length) {
    const kbIds = enabledBindings.map(b => b.kbId);
    const topK  = Math.max(...enabledBindings.map(b => b.topK||5));
    autoHits = mockRagQuery({ kbIds, query: text, topK });
    if (autoHits.length) {
      run.conversation.push({ type:'rag', time: now(), hits: autoHits, query: text, kbIds, collapsed: true });
    }
  }

  // 1) 编辑意图优先
  const intent = parseEditIntent(text);
  if (intent) {
    run.conversation.push({
      type:'diff-card',
      summary: intent.summary,
      payload: intent
    });
    render();
    setTimeout(() => openModalAgentDiff(intent), 200);
    return;
  }

  // 2) @ 多 Agent 群聊
  const mentioned = parseMentions(text);
  if (mentioned.length >= 1) {
    render();
    simulateGroupChat(text, mentioned);
    return;
  }

  // 3) 默认：调用后端API处理请求
  render();
  scrollChatToBottom();
  const m = getMission();
  const a = m.squad.agents[0];
  // 有指定 Agent 才传 agent_override，否则后端自动路由（避免注入假 @orchestrator）
  const targetAgent = a || null;
  // 先显示收到消息的提示
  let waitReply = a ? '已收到。正在调用后端AI处理您的请求...' : '已收到。将交由 Orchestrator 处理...';
  run.conversation.push({ type:'agent', agent:a?.name||'Orchestrator', icon:a?.icon||'hub', time: now(), text: waitReply, thinking: true });
  render();
  scrollChatToBottom();
  
  // 调用后端 WebSocket 流式聊天接口
  const mId = parseInt((m.id||'').replace('mis_','')) || 0;
  let finalContent = '';
  let finalIntermed = [];
  let hadIntermed = false;

  // WebSocket 消息处理器
  const wsHandlers = {
    user_message_saved(d) {
      const lastUser = run.conversation.findLast(m => m.type === 'user');
      if (lastUser) lastUser.dbId = d.message_id;
    },
    thinking(d) {
      const agentId = d.agent_id || 'agent';
      let bubble = run.conversation.find(m => m.type === 'agent' && m.agent === agentId && m.thinking);
      if (d.status === 'thinking') {
        if (!bubble) {
          bubble = { type:'agent', agent:agentId, icon:agentId==='orchestrator'?'hub':'smart_toy', time:now(), text:'思考中...', thinking: true };
          run.conversation.push(bubble);
        }
      } else if (d.status === 'done' && bubble) {
        const idx = run.conversation.indexOf(bubble);
        if (idx !== -1) run.conversation.splice(idx, 1);
      }
      render(); scrollChatToBottom();
    },
    intermediate(d) {
      hadIntermed = true;
      const agentId = d.agent_id || 'agent';
      const thinkBubble = run.conversation.find(m => m.type === 'agent' && m.agent === agentId && m.thinking);
      if (thinkBubble) {
        const idx = run.conversation.indexOf(thinkBubble);
        if (idx !== -1) run.conversation.splice(idx, 1);
      }
      const existBubble = run.conversation.find(m => m.type === 'agent' && m.agent === agentId && !m.thinking && m.text === d.content);
      if (!existBubble) {
        run.conversation.push({
          type:'agent', agent:d.agent_id==='orchestrator'?'Orchestrator':d.agent_id,
          icon:d.agent_id==='orchestrator'?'hub':'smart_toy',
          time:now(), text:d.content, dbId: d.message_id
        });
      }
      render(); scrollChatToBottom();
    },
    token(d) {
      finalContent += d.content;
      let tokenBubble = run.conversation.find(m => m.type === 'agent' && m.agent === (targetAgent?.name || 'orchestrator') && m.isTokenStream);
      if (!tokenBubble) {
        const thinkIdx = run.conversation.findIndex(m => m.type === 'agent' && m.thinking);
        if (thinkIdx !== -1) run.conversation.splice(thinkIdx, 1);
        tokenBubble = { type:'agent', agent:targetAgent?.name||'orchestrator', icon:targetAgent?.icon||'hub', time:now(), text:'', isTokenStream: true };
        run.conversation.push(tokenBubble);
      }
      tokenBubble.text = finalContent;
      render(); scrollChatToBottom();
    },
    artifact(d) {
      run.conversation.push({
        type:'artifact', agent:targetAgent?.name||'orchestrator',
        icon:'code', time:now(),
        artType:d.artType || d.art_type || d.type || 'code', title:d.title || '产物', content:d.content
      });
      render(); scrollChatToBottom();
    },
    final(d) {
      finalContent = d.content || finalContent;
      finalIntermed = d.intermediate_messages || [];
      
      // 清理 thinking 气泡和 token 流式气泡
      const thinkIdx = run.conversation.findIndex(m => m.type === 'agent' && m.thinking);
      if (thinkIdx !== -1) run.conversation.splice(thinkIdx, 1);
      const tokenIdx = run.conversation.findIndex(m => m.type === 'agent' && m.isTokenStream);
      if (tokenIdx !== -1) run.conversation.splice(tokenIdx, 1);

      // 如果没有 intermediate 且没有 token，添加最终回复
      const lastAgent = run.conversation.findLast(m => m.type === 'agent');
      if (!lastAgent || lastAgent.text !== finalContent) {
        run.conversation.push({ type:'agent', agent:targetAgent?.name||'orchestrator', icon:targetAgent?.icon||'hub', time:now(), text: finalContent || '已完成', dbId: d.message_id });
      } else if (lastAgent) {
        lastAgent.dbId = d.message_id;
      }

      render(); scrollChatToBottom();
      // 刷新侧边栏排序（最近活跃）
      loadMissions();
    },
    error(d) {
      const thinkIdx = run.conversation.findIndex(m => m.type === 'agent' && m.thinking);
      if (thinkIdx !== -1) run.conversation.splice(thinkIdx, 1);
      run.conversation.push({ type:'agent', agent:targetAgent?.name||'orchestrator', icon:targetAgent?.icon||'hub', time:now(), text:'抱歉，调用后端API时出错了：'+(d.message||'未知错误') });
      render(); scrollChatToBottom();
    }
  };

  // 连接 WebSocket 并发送消息
  (async () => {
    try {
      await connectWebSocket(mId, wsHandlers);
      wsSend(text, state.activeSkills || [], targetAgent, attachments);
      // 清空已发送的附件
      state.pendingAttachments = [];
      render();
    } catch (error) {
      const thinkIdx = run.conversation.findIndex(m => m.type === 'agent' && m.thinking);
      if (thinkIdx !== -1) run.conversation.splice(thinkIdx, 1);
      run.conversation.push({ type:'agent', agent:targetAgent?.name||'Orchestrator', icon:targetAgent?.icon||'hub', time:now(), text:'抱歉，WebSocket 连接失败：'+error.message });
      render(); scrollChatToBottom();
    }
  })();
}

/* ---- New Run（并发，不归档旧 Run） ---- */
function startNewRun() {
  const m = getMission();
  // 把当前 running 的 Run 标记为 idle（仍可写、仍可继续对话）
  const cur = m.runs.find(r => r.id === state.runId);
  if (cur && cur.status === 'running') cur.status = 'idle';

  const newRun = {
    id: uid('run'),
    title: '新运行 · ' + now(),
    status: 'running',
    startedAt: now(),
    squadSnapshot: JSON.parse(JSON.stringify(m.squad)),
    conversation: [{ type:'system', text:'已启动新运行，使用当前 Agent Team。旧 Run 仍可继续对话。' }],
    artifact: null
  };
  m.runs.unshift(newRun);
  state.runId = newRun.id;
  render();
  showToast('已启动新运行（旧 Run 仍可继续）', 'success');
}

function manualSaveQuickRun() {
  if (!state.quickRun.conversation.length) {
    showToast('Quick Run 还没有任何对话', 'error');
    return;
  }
  openModalSaveAsMission();
}

/* ===================== 消息操作 ===================== */
async function regenerateMessage(messageId, idx) {
  const m = getMission();
  if (!m) return;
  const convId = parseInt((m.id || '').replace('mis_', '')) || 0;
  if (!convId) { showToast('无效的对话 ID', 'error'); return; }

  showToast('正在重新生成...', 'info');
  try {
    const response = await api(`/conversations/${convId}/messages/${messageId}/regenerate`, {
      method: 'POST'
    });
    if (response && response.ok) {
      const run = getRun();
      const msg = run.conversation[idx];
      if (msg) {
        msg.text = response.content;
        msg.dbId = response.new_message_id;
        msg.isPinned = false;
      }
      showToast('重新生成成功', 'success');
      render();
    } else {
      showToast('重新生成失败', 'error');
    }
  } catch (e) {
    console.error('重新生成失败:', e);
    showToast('重新生成失败: ' + e.message, 'error');
  }
}

async function quoteMessage(messageId) {
  try {
    const response = await api(`/messages/${messageId}/quote`, {
      method: 'POST',
      body: JSON.stringify({ target_conversation_id: 0 })
    });
    if (response && response.ok) {
      const quoteText = response.display || '';
      const ta = $('#chat-input');
      if (ta) {
        const prefix = ta.value ? ta.value + '\n' : '';
        ta.value = prefix + '> ' + quoteText + '\n';
        ta.focus();
      }
      showToast('已引用到输入框', 'success');
    } else {
      showToast('引用失败', 'error');
    }
  } catch (e) {
    console.error('引用失败:', e);
    showToast('引用失败: ' + e.message, 'error');
  }
}

async function expandMessagePreview(messageId) {
  try {
    const response = await api(`/messages/${messageId}/content`);
    if (response && response.ok) {
      const content = response.content || '';
      const type = response.type || 'text';
      const agentId = response.agent_id || '';
      const isPinned = response.is_pinned || false;
      const createdAt = response.created_at || '';

      // 弹窗展示完整内容
      const root = $('#modal-ai-proposal');
      root.classList.remove('hidden');
      root.innerHTML = `
        <div class="absolute inset-0 modal-overlay" onclick="closeModal('modal-ai-proposal')"></div>
        <div class="relative h-full w-full flex items-center justify-center p-lg" onclick="event.stopPropagation()">
          <div class="bg-surface-container-lowest rounded-xl shadow-2xl w-[640px] max-w-full max-h-[80vh] overflow-hidden flex flex-col">
            <div class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="material-symbols-outlined text-primary text-[20px]">description</span>
                <h3 class="text-headline-md text-on-surface">消息详情</h3>
                ${isPinned ? '<span class="ml-2 text-[11px] px-2 py-0.5 bg-primary-fixed text-on-primary-fixed-variant rounded-full font-medium">已置顶</span>' : ''}
              </div>
              <button onclick="closeModal('modal-ai-proposal')" class="p-1 rounded hover:bg-surface-container">
                <span class="material-symbols-outlined text-secondary">close</span>
              </button>
            </div>
            <div class="p-lg overflow-y-auto flex-1">
              <div class="flex items-center gap-2 mb-3 text-label-sm text-secondary">
                <span class="font-medium text-on-surface">Agent: ${escapeHTML(agentId)}</span>
                <span>·</span>
                <span>${escapeHTML(createdAt)}</span>
                <span>·</span>
                <span class="px-1.5 py-0.5 rounded bg-surface-container text-[10px] uppercase">${escapeHTML(type)}</span>
              </div>
              <div class="bg-surface-container-lowest border border-outline-variant rounded-lg p-md">
                <pre class="text-body-md whitespace-pre-wrap font-mono text-on-surface">${escapeHTML(content)}</pre>
              </div>
            </div>
            <div class="px-lg py-md border-t border-outline-variant flex items-center justify-end gap-2">
              <button onclick="navigator.clipboard.writeText(${JSON.stringify(content)})" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container text-label-md flex items-center gap-1">
                <span class="material-symbols-outlined text-[16px]">content_copy</span>复制内容
              </button>
              <button onclick="closeModal('modal-ai-proposal')" class="px-3 py-1.5 bg-primary text-white rounded-lg text-label-md hover:opacity-90">关闭</button>
            </div>
          </div>
        </div>`;
    } else {
      showToast('获取消息内容失败', 'error');
    }
  } catch (e) {
    console.error('展开预览失败:', e);
    showToast('展开预览失败: ' + e.message, 'error');
  }
}