
/* ----- Chat input handlers (placeholders, full impl in Step 6) ----- */
function onChatInputChange(e){ /* Step 6 */ }
function onChatInputKeydown(e){
  const isImeComposing = e.isComposing || e.keyCode === 229;
  if (isImeComposing) return;
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
}
function sendChat(){
  const ta = $('#chat-input'); if (!ta) return;
  const text = ta.value.trim(); if (!text) return;
  const run = getRun();
  run.conversation.push({ type:'user', who:'You', time: now(), text });
  ta.value = '';
  render();
  // 模拟一个 Agent 回复
  setTimeout(() => {
    const m = getMission();
    const a = m.squad.agents[0];
    run.conversation.push({ type:'agent', agent: a.name, icon: a.icon, time: now(),
      text: '已收到。我会基于当前班底配置开始处理这个请求。' });
    render();
  }, 700);
}
function insertMentionTrigger(){ insertTrigger('@'); }
function insertTrigger(ch){
  const ta = $('#chat-input'); if (!ta) return;
  const v = ta.value || '';
  ta.value = v + (v && !v.endsWith(' ') ? ' ' : '') + ch;
  ta.focus();
  // 主动触发一次 popover
  showAgentPopover(ta, ch);
}
function openMCPModal(){ openModalMCPConnect(); }
function openAgentDiff(p){ openModalAgentDiff(p); }
function openSaveAsMissionModal(){ openModalSaveAsMission(); }

/* ===================== Modal: Create Mission ===================== */
function openCreateMission() { openModalCreateMission(); }

async function openModalCreateMission() {
  const root = $('#modal-create-mission');
  root.classList.remove('hidden');
  root.innerHTML = `
    <div class="absolute inset-0 modal-overlay" onclick="closeModal('modal-create-mission')"></div>
    <div class="relative h-full w-full flex items-center justify-center p-lg" onclick="event.stopPropagation()">
      <div class="bg-surface-container-lowest rounded-xl shadow-2xl w-[520px] max-w-full overflow-hidden flex flex-col">
        <div class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <h3 class="text-headline-md text-on-surface">创建新任务</h3>
          <button onclick="closeModal('modal-create-mission')" class="p-1 rounded hover:bg-surface-container">
            <span class="material-symbols-outlined text-secondary">close</span>
          </button>
        </div>
        <div class="p-lg space-y-md">
          <div>
            <label class="text-label-md text-on-surface font-medium block mb-1">任务名称 <span class="text-error">*</span></label>
            <input id="create-mission-name" type="text" placeholder="例如：财报分析、竞品监控..."
              class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0" />
          </div>
          <div>
            <label class="text-label-md text-on-surface font-medium block mb-1">任务描述（可选）</label>
            <textarea id="create-mission-desc" rows="3" placeholder="描述你的任务目标，Orchestrator 将根据任务自动分配合适的 Agent..."
              class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 resize-none"></textarea>
          </div>
          <p class="text-label-sm text-secondary">Agent 和 Skill 无需手动配置，Orchestrator 会在运行时根据任务动态调度。</p>
        </div>
        <div class="px-lg py-md border-t border-outline-variant flex items-center justify-end gap-2">
          <button onclick="closeModal('modal-create-mission')" class="px-3 py-1.5 text-secondary text-label-md hover:underline">取消</button>
          <button onclick="handleCreateMission()" class="px-4 py-1.5 bg-primary text-white rounded-lg text-label-md hover:opacity-90 flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">add</span>创建
          </button>
        </div>
      </div>
    </div>`;
  // 自动聚焦
  setTimeout(() => $('#create-mission-name')?.focus(), 100);
}

async function handleCreateMission() {
  const name = $('#create-mission-name')?.value.trim();
  if (!name) { showToast('请输入任务名称', 'error'); return; }
  const desc = $('#create-mission-desc')?.value.trim() || '';
  
  closeModal('modal-create-mission');
  
  try {
    const response = await api('/missions', {
      method: 'POST',
      body: JSON.stringify({ name, description: desc })
    });
    
    if (response && response.ok && response.mission) {
      state.missions.unshift(response.mission);
      showToast('任务创建成功', 'success');
      openMission(response.mission.id);
    } else {
      throw new Error('后端返回异常');
    }
  } catch (error) {
    console.error('创建任务失败:', error);
    showToast('创建失败：' + (error.message || error), 'error');
  }
}

/* ===== 兼容旧引用 — 改为调用简约创建 ===== */
function createMissionFromTemplate() { openCreateMission(); }
function createBlankMission() { openCreateMission(); }
function aiProposeFromInput() { openCreateMission(); }
function openModalAIProposal() { openCreateMission(); }
function acceptAIProposal() { openCreateMission(); }

/* ===================== Modal: Agent Diff ===================== */
function openModalAgentDiff(payload) {
  const root = $('#modal-agent-diff');
  root.classList.remove('hidden');
  const { agentId, addedSkills=[], removedSkills=[], promptDiff=[], summary } = payload;
  // 优先用 detail.draft 锁定的 mission；否则退回 getMission()
  const m = (state.detail && state.detail.type === 'agent' && state.detail.missionId)
    ? state.missions.find(x => x.id === state.detail.missionId)
    : getMission();
  const agent = m && m.squad.agents.find(a => a.id === agentId);

  const skillChips = (skills, kind) => skills.map(s => `
    <span class="text-label-sm px-2 py-1 rounded-full border flex items-center gap-1
      ${kind==='add'?'bg-tertiary-fixed text-on-tertiary-fixed-variant border-tertiary/40'
                   :'bg-error-container text-on-error-container border-error/30 line-through'}">
      <span class="material-symbols-outlined text-[14px]">${kind==='add'?'add':'remove'}</span>${escapeHTML(s)}
    </span>`).join('');

  const promptHTML = promptDiff.map(line => {
    if (line.type==='add')    return `<div class="px-2 py-0.5 diff-bg-added diff-text-added">+ ${escapeHTML(line.text)}</div>`;
    if (line.type==='remove') return `<div class="px-2 py-0.5 diff-bg-removed diff-text-removed">- ${escapeHTML(line.text)}</div>`;
    return `<div class="px-2 py-0.5 text-secondary">  ${escapeHTML(line.text)}</div>`;
  }).join('');

  root.innerHTML = `
    <div class="absolute inset-0 modal-overlay" onclick="closeModal('modal-agent-diff')"></div>
    <div class="relative h-full w-full flex items-center justify-center p-lg" onclick="event.stopPropagation()">
      <div class="bg-surface-container-lowest rounded-xl shadow-2xl w-[720px] max-w-full max-h-[88vh] overflow-hidden flex flex-col">
        <div class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-primary">difference</span>
            <h3 class="text-headline-md text-on-surface">配置变更预览</h3>
          </div>
          <button onclick="closeModal('modal-agent-diff')" class="p-1 rounded hover:bg-surface-container">
            <span class="material-symbols-outlined text-secondary">close</span>
          </button>
        </div>

        <div class="px-lg py-md bg-primary-fixed/20 border-b border-outline-variant text-label-md text-on-primary-fixed-variant flex items-start gap-2">
          <span class="material-symbols-outlined text-primary text-[16px] mt-0.5">smart_toy</span>
          <span>Coordinator 提议：<b>${escapeHTML(summary)}</b></span>
        </div>

        <div class="flex-1 overflow-y-auto p-lg space-y-md">
          <div class="flex items-center gap-3 p-3 bg-surface-container-low border border-outline-variant rounded-xl">
            <div class="w-10 h-10 rounded-lg bg-secondary-container flex items-center justify-center">
              <span class="material-symbols-outlined text-on-surface-variant text-[18px]">${agent?.icon || 'smart_toy'}</span>
            </div>
            <div>
              <p class="font-label-md text-on-surface">${escapeHTML(agent?.name || 'Agent')}</p>
              <p class="text-label-sm text-secondary italic">${escapeHTML(agent?.role || '')}</p>
            </div>
          </div>

          ${(addedSkills.length || removedSkills.length) ? `
          <section>
            <p class="font-label-md text-on-surface mb-2">技能变更</p>
            <div class="flex flex-wrap gap-1.5">
              ${skillChips(removedSkills,'remove')}
              ${skillChips(addedSkills,'add')}
            </div>
          </section>` : ''}

          ${promptDiff.length ? `
          <section>
            <p class="font-label-md text-on-surface mb-2">System Prompt</p>
            <div class="bg-surface-container border border-outline-variant rounded-lg overflow-hidden font-mono text-[12px] leading-relaxed">
              ${promptHTML}
            </div>
          </section>` : ''}
        </div>

        <div class="px-lg py-md border-t border-outline-variant flex items-center justify-between">
          <div class="text-label-sm text-secondary flex items-center gap-2">
            <span class="material-symbols-outlined text-[14px]">history</span>该变更会写入版本历史，可随时回滚。
          </div>
          <div class="flex gap-2">
            <button onclick="closeModal('modal-agent-diff')" class="px-3 py-1.5 text-secondary text-label-md hover:underline">取消</button>
            <button onclick="applyAgentDiff('${agentId}', ${JSON.stringify({addedSkills,removedSkills,promptDiff}).replace(/'/g,"\\'")})" class="px-3 py-1.5 bg-primary text-white rounded-lg text-label-md hover:opacity-90 flex items-center gap-1">
              <span class="material-symbols-outlined text-[14px]">check</span>应用变更
            </button>
          </div>
        </div>
      </div>
    </div>`;
}

function applyAgentDiff(agentId, change) {
  const m = (state.detail && state.detail.type === 'agent' && state.detail.missionId)
    ? state.missions.find(x => x.id === state.detail.missionId)
    : getMission();
  const a = m && m.squad.agents.find(x => x.id === agentId);
  if (!a) return;
  // 应用 skill diff
  (change.removedSkills||[]).forEach(s => { const i = a.skills.indexOf(s); if (i>=0) a.skills.splice(i,1); });
  (change.addedSkills||[]).forEach(s => { if (!a.skills.includes(s)) a.skills.push(s); });
  // 应用 prompt diff
  if (change.promptDiff?.length) {
    a.systemPrompt = change.promptDiff
      .filter(l => l.type !== 'remove')
      .map(l => l.text)
      .join('\n');
  }
  // 同步加入到 Mission 启用的 skill 集合
  (change.addedSkills||[]).forEach(s => { if (!m.squad.enabledSkills.includes(s)) m.squad.enabledSkills.push(s); });

  // 若当前正处于 Agent 详情页且就是这个 Agent，则把变更也同步到 draft（避免立刻被 draft 覆盖）
  if (state.detail && state.detail.type === 'agent' && state.detail.agentId === a.id) {
    const draft = state.detail.draft;
    if (draft) {
      draft.skills = [...a.skills];
      draft.systemPrompt = a.systemPrompt;
    }
  }

  const run = getRun();
  if (run) {
    run.conversation.push({
      type:'agent', agent:'Coordinator', icon:'switch_account', time: now(),
      text:`已更新 ${a.name} 的配置。变更立即在下一轮对话生效。`
    });
  }
  state.selectedAgentId = a.id;
  state._highlightAgentId = a.id;
  closeModal('modal-agent-diff');
  render();
  // 高亮闪烁
  setTimeout(() => {
    $$('.agent-connector > div').forEach(el => {
      if (el.textContent.includes(a.name)) el.classList.add('agent-pending');
    });
  }, 30);
  showToast('Agent 配置已更新', 'success');
}

/* ===================== Modal: Add Agent (三段式) ===================== */
// state.addAgentModal: { missionId, tab: 'lib'|'market'|'nl', search, nlText, onAdded }
function openModalAddAgent(missionId, opts={}) {
  state.addAgentModal = {
    missionId,
    tab: 'lib',
    search: '',
    nlText: '',
    onAdded: opts.onAdded || null,
  };
  renderModalAddAgent();
}
function closeModalAddAgent() {
  const root = $('#modal-add-agent');
  if (root) { root.classList.add('hidden'); root.innerHTML = ''; }
  state.addAgentModal = null;
}
function setAddAgentTab(t) {
  if (!state.addAgentModal) return;
  state.addAgentModal.tab = t;
  renderModalAddAgent();
}
function setAddAgentSearch(v) {
  if (!state.addAgentModal) return;
  state.addAgentModal.search = v;
  renderModalAddAgent();
  const el = document.getElementById('add-agent-search');
  if (el) { el.focus(); try { el.setSelectionRange(v.length, v.length); } catch(e){} }
}
function setAddAgentNLText(v) {
  if (!state.addAgentModal) return;
  state.addAgentModal.nlText = v;
  // 不重渲染，textarea 内容由浏览器维护即可
}

function renderModalAddAgent() {
  const root = $('#modal-add-agent');
  if (!root || !state.addAgentModal) return;
  const { missionId, tab, search, nlText } = state.addAgentModal;
  const dstMission = state.missions.find(x => x.id === missionId);
  if (!dstMission) { closeModalAddAgent(); return; }

  // 当前 Mission 已有 Agent 的名字 + id 排除集
  const excludeIds = new Set(dstMission.squad.agents.map(a => a.id));
  const excludeNames = new Set(dstMission.squad.agents.map(a => a.name));

  // 用 Team 上下文给评分用（如果存在）
  const manager = getMissionManager(dstMission);

  const myLib = getMyLibraryAgents(missionId, excludeIds, search, manager).slice(0, 8);
  const market = getRecommendedAgents(manager, excludeIds, search).slice(0, 8);

  const tabBtn = (id, label, icon, count) => `
    <button onclick="setAddAgentTab('${id}')"
      class="flex items-center gap-1.5 px-3 py-2 text-label-md border-b-2 transition-colors
             ${tab===id ? 'border-primary text-primary font-bold' : 'border-transparent text-secondary hover:text-on-surface'}">
      <span class="material-symbols-outlined text-[16px]">${icon}</span>${label}${count!=null?`<span class="text-[10px] opacity-70">(${count})</span>`:''}
    </button>`;

  const rowAdd = (s, action, badge='') => `
    <div class="flex items-center gap-3 p-2.5 rounded-lg border border-outline-variant bg-surface-container-lowest hover:border-primary/40">
      <div class="w-8 h-8 rounded bg-tertiary-container flex items-center justify-center shrink-0">
        <span class="material-symbols-outlined text-on-tertiary-container text-[16px]">${escapeHTML(s.icon || getAgentKindMeta(s.kind || 'agent').icon)}</span>
      </div>
      <div class="flex-1 min-w-0">
        <p class="font-label-md text-on-surface truncate flex items-center gap-1.5">
          ${escapeHTML(s.name)}
          <span class="text-[10px] px-1 rounded ${s.kind === 'team' ? 'bg-primary/15 text-primary' : 'bg-secondary-container text-on-surface-variant'}">${getAgentKindMeta(s.kind || 'agent').label}</span>
          ${badge}
        </p>
        <p class="text-label-sm text-secondary truncate">${escapeHTML(s.role || '')}</p>
        ${s.fromMissionName ? `<p class="text-[11px] text-secondary mt-0.5">来自 Mission：${escapeHTML(s.fromMissionName)}</p>` : ''}
        ${s.authorName ? `<p class="text-[11px] text-secondary mt-0.5">@${escapeHTML(s.authorName)} · ${(s.installCount||0).toLocaleString()} 安装</p>` : ''}
      </div>
      <button onclick="${action}"
        class="px-2.5 py-1 rounded text-label-md text-primary hover:bg-primary-container/30 flex items-center gap-1 shrink-0" title="加入到当前 Mission">
        <span class="material-symbols-outlined text-[16px]">add</span>添加
      </button>
    </div>`;

  const emptyBlock = (text) => `
    <div class="text-center text-secondary p-md border border-dashed border-outline-variant rounded-lg">
      <p class="text-label-sm">${escapeHTML(text)}</p>
    </div>`;

  let body = '';
  if (tab === 'lib') {
    body = `
      <div class="mb-2 relative">
        <span class="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-secondary text-[16px]">search</span>
        <input id="add-agent-search" type="text" value="${escapeAttr(search)}" oninput="setAddAgentSearch(this.value)"
          placeholder="按名称 / 职责 / 技能搜索…"
          class="w-full pl-8 pr-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:border-primary focus:ring-0"/>
      </div>
      ${myLib.length
        ? `<div class="space-y-2">${myLib.map(s => rowAdd(s, s.fromCustomAgent
            ? `addAgentFromCustomAgent('${s.id}','${missionId}')`
            : `addAgentFromLibrary('${s.fromMissionId}','${s.id}','${missionId}')`
          )).join('')}</div>`
        : emptyBlock(search ? '没有匹配的 Agent。' : '你的其它 Mission 里还没有可推荐的 Agent。')}`;
  } else if (tab === 'market') {
    body = `
      <div class="mb-2 relative">
        <span class="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-secondary text-[16px]">search</span>
        <input id="add-agent-search" type="text" value="${escapeAttr(search)}" oninput="setAddAgentSearch(this.value)"
          placeholder="按名称 / 职责搜索市场…"
          class="w-full pl-8 pr-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:border-primary focus:ring-0"/>
      </div>
      ${market.length
        ? `<div class="space-y-2">${market.map(s => rowAdd(s, `addAgentFromMarketToMission('${s.id}','${missionId}')`,
            `<span class="text-[10px] px-1 rounded bg-amber-100 text-amber-700">市场</span>`)).join('')}</div>`
        : emptyBlock(search ? '市场没有匹配的 Agent。' : '市场暂无推荐。')}`;
  } else {
    // nl
    body = `
      <div class="space-y-2">
        <p class="text-label-sm text-secondary">用一句话描述你想要的 Agent，AI 会根据描述生成一个占位 Agent，可以稍后再去详情页精修。</p>
        <textarea id="add-agent-nl-text" rows="4"
          oninput="setAddAgentNLText(this.value)"
          placeholder="例如：一个会做财务模型分析的 Agent；或：一个能写中英双语营销文案的 Writer"
          class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg p-2 text-body-md focus:border-primary focus:ring-0 resize-none">${escapeHTML(nlText||'')}</textarea>
        <div class="flex flex-wrap gap-1">
          ${[
            '一个会做财务模型分析的 Agent',
            '一个会用 SQL 查数据库的 Agent',
            '一个能把英文论文翻译成中文的 Agent',
          ].map(c => `<button onclick="setAddAgentNLText('${escapeAttr(c)}'); document.getElementById('add-agent-nl-text').value='${escapeAttr(c)}';" class="text-[11px] px-2 py-0.5 rounded-full border border-outline-variant text-secondary hover:border-primary/40 hover:text-primary">${escapeHTML(c)}</button>`).join('')}
        </div>
        <button onclick="createAgentFromNL('${missionId}')"
          class="w-full mt-1 bg-primary text-white px-3 py-2 rounded-lg text-label-md flex items-center justify-center gap-1 hover:opacity-90">
          <span class="material-symbols-outlined text-[16px]">auto_awesome</span>用 AI 创建并加入团队
        </button>
      </div>`;
  }

  root.classList.remove('hidden');
  root.innerHTML = `
    <div class="absolute inset-0 modal-overlay" onclick="closeModalAddAgent()"></div>
    <div class="relative h-full w-full flex items-center justify-center p-lg" onclick="event.stopPropagation()">
      <div class="bg-surface-container-lowest rounded-xl shadow-2xl w-[680px] max-w-full max-h-[88vh] overflow-hidden flex flex-col">
        <div class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-primary">person_add</span>
            <h3 class="text-headline-md text-on-surface">添加角色到「${escapeHTML(dstMission.name)}」</h3>
          </div>
          <button onclick="closeModalAddAgent()" class="p-1 rounded hover:bg-surface-container">
            <span class="material-symbols-outlined text-secondary">close</span>
          </button>
        </div>
        <div class="px-lg pt-2 border-b border-outline-variant flex items-center gap-1">
          ${tabBtn('lib','我的 Agent 库','folder_special', myLib.length)}
          ${tabBtn('market','社区市场','storefront', market.length)}
          ${tabBtn('nl','自然语言描述创建','auto_awesome')}
        </div>
        <div class="flex-1 overflow-y-auto p-lg">${body}</div>
        <div class="px-lg py-md border-t border-outline-variant flex items-center justify-between text-label-sm">
          <p class="text-secondary flex items-center gap-1.5">
            <span class="material-symbols-outlined text-[14px]">info</span>
            ${dstMission.squad.agents.length === 0
              ? '当前 Mission 还没有角色：第一个加入的角色会自动成为 Team。'
              : (manager
                  ? `加入后会自动成为 Agent，并补丁同步 Team「${escapeHTML(manager.name)}」的提示词。`
                  : '加入后将自动设为 Agent。')}
          </p>
          <button onclick="closeModalAddAgent()" class="px-3 py-1.5 text-secondary hover:underline">取消</button>
        </div>
      </div>
    </div>`;
}

// 共享：把新角色真正插入 Mission，应用 Team 默认的“加进调度链”语义。
function _insertAgentToMission(newAgent, dstMission, opts={}) {
  ensureAgentSchema(newAgent);
  // 第一个角色 → Team；其它 → Agent
  if (dstMission.squad.agents.length === 0) {
    newAgent.kind = 'team';
  } else {
    newAgent.kind = 'agent';
  }
  dstMission.squad.agents.push(newAgent);
  ensureMissionManager(dstMission);

  // 如果当前 Mission 已有 Team 且不是新角色，把它加到 Team 的 teamMemberIds，并同步 Prompt。
  const mgr = getMissionManager(dstMission);
  let intent = null;
  if (mgr && mgr.id !== newAgent.id) {
    if (!Array.isArray(mgr.teamMemberIds)) mgr.teamMemberIds = [];
    if (!mgr.teamMemberIds.includes(newAgent.id)) mgr.teamMemberIds.push(newAgent.id);
    // 如果当前正处于 Team 详情页 draft，同步 draft.teamMemberIds，避免被旧 draft 覆盖
    if (state.detail && state.detail.type === 'agent' && state.detail.agentId === mgr.id && state.detail.draft) {
      const d = state.detail.draft;
      if (!Array.isArray(d.teamMemberIds)) d.teamMemberIds = [];
      if (!d.teamMemberIds.includes(newAgent.id)) d.teamMemberIds.push(newAgent.id);
    }
    intent = buildManagerSyncPromptDiff(mgr, newAgent, dstMission);
  }
  return { intent, mgr };
}

// 从我的库添加（被 Modal 调用）
function addAgentFromLibrary(srcMissionId, srcAgentId, dstMissionId) {
  const dst = state.missions.find(x => x.id === dstMissionId);
  const src = state.missions.find(x => x.id === srcMissionId);
  if (!dst || !src) return;
  const srcAgent = src.squad.agents.find(a => a.id === srcAgentId);
  if (!srcAgent) return;
  const newAgent = cloneAgentForMission(srcAgent, dst);
  const { intent } = _insertAgentToMission(newAgent, dst);
  closeModalAddAgent();
  showToast(`已添加 "${newAgent.name}" 到 Team`, 'success');
  if (intent) setTimeout(() => { state.missionId = dst.id; openModalAgentDiff(intent); }, 100);
  else render();
}

// 从市场添加（被 Modal 调用）
function addAgentFromMarketToMission(marketAgentId, dstMissionId) {
  const dst = state.missions.find(x => x.id === dstMissionId);
  const src = (state.agentMarket || []).find(x => x.id === marketAgentId);
  if (!dst || !src) return;
  const newAgent = cloneAgentForMission(src, dst);
  const { intent } = _insertAgentToMission(newAgent, dst);
  closeModalAddAgent();
  showToast(`已从社区市场安装 "${newAgent.name}"`, 'success');
  if (intent) setTimeout(() => { state.missionId = dst.id; openModalAgentDiff(intent); }, 100);
  else render();
}

// 用自然语言描述创建（mock 占位）
function createAgentFromNL(dstMissionId) {
  const dst = state.missions.find(x => x.id === dstMissionId);
  if (!dst || !state.addAgentModal) return;
  const text = (state.addAgentModal.nlText || '').trim();
  if (!text) { showToast('请先描述一下想要的 Agent', 'error'); return; }
  // 极简 NL → schema 推断（mock，不调 LLM）
  const guess = guessAgentFromNL(text);
  const newAgent = makeAgent(guess.name, guess.role, guess.icon, guess.systemPrompt, guess.skills, 'agent');
  const { intent } = _insertAgentToMission(newAgent, dst);
  closeModalAddAgent();
  showToast(`已根据描述创建 "${newAgent.name}"，可在详情页精修`, 'success');
  if (intent) setTimeout(() => { state.missionId = dst.id; openModalAgentDiff(intent); }, 100);
  else render();
}

// 极简 NL → Agent schema（不调 LLM 的占位实现）
function guessAgentFromNL(text) {
  const lower = text.toLowerCase();
  // icon 推断
  let icon = 'smart_toy';
  if (/翻译|translate/.test(lower)) icon = 'translate';
  else if (/营销|文案|writer|写/.test(lower)) icon = 'edit_note';
  else if (/财务|financ|金融|分析/.test(lower)) icon = 'finance_mode';
  else if (/sql|database|数据库|查数据/.test(lower)) icon = 'database';
  else if (/code|代码|编程/.test(lower)) icon = 'code';
  else if (/research|搜索|调研/.test(lower)) icon = 'search';
  else if (/审|review|检查/.test(lower)) icon = 'rule';
  // 名字推断：尽量从描述里抓一个名词，或用通用名
  let name = 'Custom Agent';
  if (/翻译/.test(text)) name = 'Translator';
  else if (/财务|金融|财报/.test(text)) name = 'Financial Helper';
  else if (/营销|文案/.test(text)) name = 'Marketing Writer';
  else if (/sql|数据库|查数据/.test(lower)) name = 'Data Querier';
  else if (/调研|搜索|research/.test(lower)) name = 'Researcher';
  else if (/审|review/.test(lower)) name = 'Reviewer';
  else if (/写报告|report/.test(lower)) name = 'Report Writer';
  // skills 简单推断
  const skills = [];
  if (/sql|数据库/.test(lower)) skills.push('sql_query');
  if (/搜索|web|research/.test(lower)) skills.push('web_search');
  if (/写|markdown|report/.test(lower)) skills.push('markdown_write');
  if (/翻译/.test(text)) skills.push('translate');
  return {
    name, role: text.slice(0, 60), icon,
    systemPrompt: `你是一名 ${name}。你的职责：${text}\n请基于 Team 派发的子任务给出高质量、可验证的输出。`,
    skills,
  };
}

/* ===================== Modal: MCP Connect ===================== */
function openModalMCPConnect() {
  const root = $('#modal-mcp-connect');
  root.classList.remove('hidden');
  root.innerHTML = `
    <div class="absolute inset-0 modal-overlay" onclick="closeModal('modal-mcp-connect')"></div>
    <div class="relative h-full w-full flex items-center justify-center p-lg" onclick="event.stopPropagation()">
      <div class="bg-surface-container-lowest rounded-xl shadow-2xl w-[600px] max-w-full max-h-[88vh] overflow-hidden flex flex-col">
        <div class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-primary">cable</span>
            <h3 class="text-headline-md text-on-surface">接入 MCP 服务</h3>
          </div>
          <button onclick="closeModal('modal-mcp-connect')" class="p-1 rounded hover:bg-surface-container">
            <span class="material-symbols-outlined text-secondary">close</span>
          </button>
        </div>
        <div class="flex-1 overflow-y-auto p-lg space-y-md">
          <div>
            <p class="font-label-md text-on-surface mb-1">服务地址</p>
            <input id="mcp-url" value="https://mcp.example.com/sse" class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 font-mono text-label-md"/>
          </div>
          <div>
            <p class="font-label-md text-on-surface mb-1">认证（可选）</p>
            <input placeholder="Bearer ..." class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 font-mono text-label-md"/>
          </div>
          <button onclick="testMCPConnection()" id="mcp-test-btn" class="w-full py-2 bg-surface-container-high text-on-surface rounded-lg text-label-md hover:bg-surface-container flex items-center justify-center gap-2">
            <span class="material-symbols-outlined text-[16px]">wifi_find</span>测试连接
          </button>
          <div id="mcp-tools" class="hidden">
            <p class="font-label-md text-on-surface mb-2 flex items-center gap-2">
              <span class="material-symbols-outlined text-tertiary text-[18px]">check_circle</span>连接成功，发现 4 个工具
            </p>
            <div class="space-y-2">
              ${[
                { id:'jira_query',  name:'jira_query',  desc:'查询 Jira issue' },
                { id:'jira_create', name:'jira_create', desc:'创建 Jira issue' },
                { id:'slack_send',  name:'slack_send',  desc:'发送 Slack 消息' },
                { id:'slack_list',  name:'slack_list',  desc:'列出 Channel' },
              ].map(t => `
                <label class="flex items-center gap-2 p-2.5 bg-surface-container-low border border-outline-variant rounded-lg cursor-pointer hover:border-primary/40">
                  <input type="checkbox" checked class="mcp-tool-check rounded text-primary focus:ring-0" data-id="${t.id}" data-name="${t.name}" data-desc="${t.desc}"/>
                  <div class="flex-1">
                    <p class="font-label-md text-on-surface">${escapeHTML(t.name)}</p>
                    <p class="text-label-sm text-secondary">${escapeHTML(t.desc)}</p>
                  </div>
                </label>`).join('')}
            </div>
          </div>
        </div>
        <div class="px-lg py-md border-t border-outline-variant flex items-center justify-end gap-2">
          <button onclick="closeModal('modal-mcp-connect')" class="px-3 py-1.5 text-secondary text-label-md hover:underline">取消</button>
          <button onclick="saveMCPSkills()" id="mcp-save-btn" class="px-3 py-1.5 bg-primary text-white rounded-lg text-label-md hover:opacity-90 hidden">
            保存为 Mission 技能
          </button>
        </div>
      </div>
    </div>`;
}

function testMCPConnection() {
  const btn = $('#mcp-test-btn');
  btn.innerHTML = `<span class="material-symbols-outlined text-[16px] animate-spin">progress_activity</span>连接中...`;
  btn.disabled = true;
  setTimeout(() => {
    btn.innerHTML = `<span class="material-symbols-outlined text-[16px]">check</span>连接成功`;
    btn.className = 'w-full py-2 bg-tertiary-fixed text-on-tertiary-fixed-variant rounded-lg text-label-md flex items-center justify-center gap-2';
    $('#mcp-tools').classList.remove('hidden');
    $('#mcp-save-btn').classList.remove('hidden');
  }, 1300);
}

function saveMCPSkills() {
  const checks = $$('.mcp-tool-check').filter(c => c.checked);
  const m = getMission();
  checks.forEach(c => {
    const id = c.dataset.id;
    if (!state.customSkills.find(s => s.id === id)) {
      state.customSkills.push({ id, name: c.dataset.name, icon:'extension', desc: c.dataset.desc });
    }
    if (!m.squad.enabledSkills.includes(id)) m.squad.enabledSkills.push(id);
  });
  closeModal('modal-mcp-connect');
  showToast(`已添加 ${checks.length} 个 MCP 技能`, 'success');
  render();
}

/* ===================== Tools 级 MCP Server CRUD ===================== */
function openMcpServerModal(editingId) {
  loadMcpServers();
  const editing = editingId ? (state.mcpServers || []).find(s => s.id === editingId) : null;
  state.mcpEdit = {
    id: editing ? editing.id : null,
    name: editing ? editing.name : '',
    description: editing ? editing.description : '',
    transport: editing ? editing.transport : 'sse',
    endpoint: editing ? (editing.endpoint || '') : '',
    command: editing ? (editing.command || '') : '',
    auth: editing ? (editing.auth || '') : '',
    tools: editing ? (editing.tools || []).slice() : [],
    selectedToolIds: new Set((editing && editing.tools) ? editing.tools.map(t => t.name) : []),
    testStatus: editing && editing.status ? editing.status : 'idle',
    testError: '',
  };
  renderMcpServerModal();
}

function renderMcpServerModal() {
  const root = $('#modal-mcp-connect');
  const m = state.mcpEdit;
  const transportInput = m.transport === 'stdio'
    ? `<input id="mcp-edit-command" value="${escapeAttr(m.command || '')}" placeholder="node ./my-mcp-server.js"
        class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 font-mono text-label-md"/>
       <p class="text-label-sm text-secondary mt-1">本地进程启动命令（演示用，真实运行需后端代理）</p>`
    : `<input id="mcp-edit-endpoint" value="${escapeAttr(m.endpoint || '')}" placeholder="${m.transport === 'http' ? 'https://api.example.com/mcp' : 'https://mcp.example.com/sse'}"
        class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 font-mono text-label-md"/>`;

  const statusBlock = (() => {
    if (m.testStatus === 'connected') {
      return `<div class="flex items-center gap-2 text-tertiary text-label-md">
        <span class="material-symbols-outlined text-[18px]">check_circle</span>
        连接成功，发现 ${m.tools.length} 个工具
      </div>`;
    }
    if (m.testStatus === 'testing') {
      return `<div class="flex items-center gap-2 text-secondary text-label-md">
        <span class="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>正在握手...
      </div>`;
    }
    if (m.testStatus === 'error') {
      return `<div class="flex items-center gap-2 text-error text-label-md">
        <span class="material-symbols-outlined text-[18px]">error</span>${escapeHTML(m.testError || '连接失败')}
      </div>`;
    }
    return `<p class="text-label-sm text-secondary">填写完成后点击 "测试连接" 探测可用工具。</p>`;
  })();

  const toolsBlock = m.tools.length ? `
    <div>
      <p class="font-label-md text-on-surface mb-2">选择要启用的工具 (${m.selectedToolIds.size}/${m.tools.length})</p>
      <div class="space-y-2 max-h-[200px] overflow-y-auto pr-1">
        ${m.tools.map(t => `
          <label class="flex items-start gap-2 p-2.5 bg-surface-container-low border border-outline-variant rounded-lg cursor-pointer hover:border-primary/40">
            <input type="checkbox" ${m.selectedToolIds.has(t.name) ? 'checked' : ''}
              onchange="toggleMcpEditTool('${escapeAttr(t.name)}')" class="mt-1 rounded text-primary focus:ring-0"/>
            <div class="flex-1 min-w-0">
              <p class="font-label-md text-on-surface font-mono">${escapeHTML(t.name)}</p>
              <p class="text-label-sm text-secondary">${escapeHTML(t.desc || '')}</p>
            </div>
          </label>`).join('')}
      </div>
    </div>` : '';

  root.classList.remove('hidden');
  root.innerHTML = `
    <div class="absolute inset-0 modal-overlay" onclick="closeMcpServerModal()"></div>
    <div class="relative h-full w-full flex items-center justify-center p-lg" onclick="event.stopPropagation()">
      <div class="bg-surface-container-lowest rounded-xl shadow-2xl w-[640px] max-w-full max-h-[88vh] overflow-hidden flex flex-col">
        <div class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-primary">cable</span>
            <h3 class="text-headline-md text-on-surface">${m.id ? '编辑 MCP Server' : '接入 MCP Server'}</h3>
          </div>
          <button onclick="closeMcpServerModal()" class="p-1 rounded hover:bg-surface-container">
            <span class="material-symbols-outlined text-secondary">close</span>
          </button>
        </div>
        <div class="flex-1 overflow-y-auto p-lg space-y-md">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <p class="font-label-md text-on-surface mb-1">名称 <span class="text-error">*</span></p>
              <input id="mcp-edit-name" value="${escapeAttr(m.name)}" placeholder="my-jira-mcp"
                class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0"/>
            </div>
            <div>
              <p class="font-label-md text-on-surface mb-1">传输协议</p>
              <select id="mcp-edit-transport" onchange="onMcpTransportChange(this.value)"
                class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0">
                <option value="sse"   ${m.transport==='sse'?'selected':''}>SSE</option>
                <option value="http"  ${m.transport==='http'?'selected':''}>HTTP</option>
                <option value="stdio" ${m.transport==='stdio'?'selected':''}>STDIO</option>
              </select>
            </div>
          </div>
          <div>
            <p class="font-label-md text-on-surface mb-1">${m.transport === 'stdio' ? '启动命令' : 'Endpoint'} <span class="text-error">*</span></p>
            ${transportInput}
          </div>
          <div>
            <p class="font-label-md text-on-surface mb-1">描述</p>
            <textarea id="mcp-edit-desc" rows="2" placeholder="一句话说明这个 Server 的用途"
              class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 resize-none">${escapeHTML(m.description || '')}</textarea>
          </div>
          <div>
            <p class="font-label-md text-on-surface mb-1">认证 Token（可选）</p>
            <input id="mcp-edit-auth" value="${escapeAttr(m.auth || '')}" placeholder="Bearer xxx 或留空"
              class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 font-mono text-label-md"/>
          </div>
          <button onclick="testMcpServerInModal()" class="w-full py-2 bg-surface-container-high text-on-surface rounded-lg text-label-md hover:bg-surface-container flex items-center justify-center gap-2">
            <span class="material-symbols-outlined text-[16px]">wifi_find</span>测试连接 / 探测工具
          </button>
          ${statusBlock}
          ${toolsBlock}
        </div>
        <div class="px-lg py-md border-t border-outline-variant flex items-center justify-end gap-2">
          <button onclick="closeMcpServerModal()" class="px-3 py-1.5 text-secondary text-label-md hover:underline">取消</button>
          <button onclick="submitMcpServer()" class="px-4 py-1.5 bg-primary text-white rounded-lg text-label-md hover:opacity-90">
            ${m.id ? '保存修改' : '保存'}
          </button>
        </div>
      </div>
    </div>`;
}

function closeMcpServerModal() { state.mcpEdit = null; closeModal('modal-mcp-connect'); }

function onMcpTransportChange(v) {
  state.mcpEdit.transport = v;
  // 切换协议时保留旧 endpoint / command
  syncMcpEditFromForm();
  renderMcpServerModal();
}

function syncMcpEditFromForm() {
  const m = state.mcpEdit; if (!m) return;
  const nameEl = $('#mcp-edit-name');
  if (nameEl) m.name = nameEl.value.trim();
  const descEl = $('#mcp-edit-desc');
  if (descEl) m.description = descEl.value.trim();
  const authEl = $('#mcp-edit-auth');
  if (authEl) m.auth = authEl.value.trim();
  const epEl = $('#mcp-edit-endpoint');
  if (epEl) m.endpoint = epEl.value.trim();
  const cmdEl = $('#mcp-edit-command');
  if (cmdEl) m.command = cmdEl.value.trim();
}

function toggleMcpEditTool(toolName) {
  const m = state.mcpEdit; if (!m) return;
  if (m.selectedToolIds.has(toolName)) m.selectedToolIds.delete(toolName);
  else m.selectedToolIds.add(toolName);
  syncMcpEditFromForm();
  renderMcpServerModal();
}

function testMcpServerInModal() {
  const m = state.mcpEdit; if (!m) return;
  syncMcpEditFromForm();
  if (!m.name) { showToast('请先填写名称', 'error'); return; }
  if (m.transport === 'stdio' ? !m.command : !m.endpoint) {
    showToast(m.transport === 'stdio' ? '请填写启动命令' : '请填写 Endpoint', 'error');
    return;
  }
  m.testStatus = 'testing'; m.testError = '';
  renderMcpServerModal();
  setTimeout(() => {
    // mock：根据名字哈希返回不同的工具集
    const seed = (m.name || '').toLowerCase();
    const presets = [
      [
        { name:'jira_search',  desc:'按 JQL 查询 Jira 工单' },
        { name:'jira_create',  desc:'创建 Jira 工单' },
        { name:'jira_comment', desc:'给工单添加评论' },
      ],
      [
        { name:'github_pr_list',    desc:'列出 Pull Request' },
        { name:'github_pr_review',  desc:'对 PR 添加 Review 评论' },
        { name:'github_issue_open', desc:'创建 Issue' },
      ],
      [
        { name:'slack_send',    desc:'发送 Slack 消息' },
        { name:'slack_history', desc:'读取 Channel 历史' },
      ],
      [
        { name:'fs_read',  desc:'读取文件内容' },
        { name:'fs_write', desc:'写入文件' },
        { name:'fs_list',  desc:'列目录' },
      ],
    ];
    const idx = seed.includes('git') ? 1 : seed.includes('slack') ? 2 : seed.includes('fs') || seed.includes('file') ? 3 : 0;
    m.tools = presets[idx];
    m.selectedToolIds = new Set(m.tools.map(t => t.name));
    m.testStatus = 'connected';
    renderMcpServerModal();
  }, 800);
}

function submitMcpServer() {
  const m = state.mcpEdit; if (!m) return;
  syncMcpEditFromForm();
  if (!m.name) { showToast('请填写名称', 'error'); return; }
  if (m.transport === 'stdio' ? !m.command : !m.endpoint) {
    showToast(m.transport === 'stdio' ? '请填写启动命令' : '请填写 Endpoint', 'error');
    return;
  }
  loadMcpServers();
  const selectedTools = (m.tools || []).filter(t => m.selectedToolIds.has(t.name));
  const payload = {
    name: m.name,
    description: m.description || '',
    transport: m.transport,
    endpoint: m.endpoint || '',
    command: m.command || '',
    auth: m.auth || '',
    tools: selectedTools,
    status: m.testStatus === 'connected' ? 'connected' : 'idle',
    updatedAt: Date.now(),
  };
  if (m.id) {
    const i = state.mcpServers.findIndex(s => s.id === m.id);
    if (i >= 0) state.mcpServers[i] = { ...state.mcpServers[i], ...payload };
  } else {
    payload.id = uid('mcp');
    payload.createdAt = Date.now();
    state.mcpServers.push(payload);
  }
  saveMcpServers();
  closeMcpServerModal();
  showToast(m.id ? 'MCP Server 已更新' : 'MCP Server 已添加', 'success');
  render();
}

function editMcpServer(id) { openMcpServerModal(id); }

function deleteMcpServer(id) {
  loadMcpServers();
  const s = state.mcpServers.find(x => x.id === id);
  if (!s) return;
  if (!confirm(`确定删除 MCP Server "${s.name}"？所有引用此 Server 工具的 Mission 与 Agent 将自动解除引用。`)) return;
  state.mcpServers = state.mcpServers.filter(x => x.id !== id);
  saveMcpServers();
  // 级联清理 mission / agent 引用
  (state.missions || []).forEach(m => {
    ensureMissionSchema(m);
    m.squad.enabledMcpTools = (m.squad.enabledMcpTools || []).filter(k => !k.startsWith(id + ':'));
    (m.squad.agents || []).forEach(a => {
      a.mcpTools = (a.mcpTools || []).filter(k => !k.startsWith(id + ':'));
    });
  });
  showToast('已删除', 'success');
  render();
}

function testMcpServer(id) {
  loadMcpServers();
  const s = state.mcpServers.find(x => x.id === id);
  if (!s) return;
  s.status = 'testing';
  render();
  setTimeout(() => {
    s.status = 'connected';
    saveMcpServers();
    showToast(`"${s.name}" 连接正常 (${(s.tools||[]).length} 工具)`, 'success');
    render();
  }, 700);
}

// 工具：返回所有可在 Agent / Mission 中启用的 MCP Tools，扁平
function getAllMcpTools() {
  loadMcpServers();
  const out = [];
  (state.mcpServers || []).forEach(s => {
    (s.tools || []).forEach(t => {
      out.push({
        key: s.id + ':' + t.name,
        serverId: s.id,
        serverName: s.name,
        name: t.name,
        desc: t.desc || '',
      });
    });
  });
  return out;
}

// HTML attr escape (避免引号问题)
// escapeAttr 已在第155行定义：const escapeAttr = escapeHTML; 此处不再重复定义

/* ===================== Modal: Save As Mission ===================== */
function openModalSaveAsMission() {
  const root = $('#modal-save-as-mission');
  root.classList.remove('hidden');
  root.innerHTML = `
    <div class="absolute inset-0 modal-overlay" onclick="closeModal('modal-save-as-mission')"></div>
    <div class="relative h-full w-full flex items-center justify-center p-lg" onclick="event.stopPropagation()">
      <div class="bg-surface-container-lowest rounded-xl shadow-2xl w-[520px] max-w-full overflow-hidden flex flex-col">
        <div class="px-lg py-md border-b border-outline-variant flex items-center gap-2">
          <span class="material-symbols-outlined text-primary">bookmark_add</span>
          <h3 class="text-headline-md text-on-surface">保存为 Mission</h3>
        </div>
        <div class="p-lg space-y-md">
          <div>
            <p class="font-label-md text-on-surface mb-1">名称</p>
            <input id="save-name" value="临时对话沉淀" class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0"/>
          </div>
          <div>
            <p class="font-label-md text-on-surface mb-1">描述（可选）</p>
            <textarea id="save-desc" rows="2" placeholder="一句话总结这个 Mission 解决了什么问题" class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 resize-none"></textarea>
          </div>
          <label class="flex items-center gap-2 p-2.5 bg-primary-fixed/30 border border-primary/30 rounded-lg cursor-pointer">
            <input type="checkbox" id="ai-optimize" checked class="rounded text-primary focus:ring-0"/>
            <div>
              <p class="font-label-md text-on-primary-fixed-variant flex items-center gap-1">
                <span class="material-symbols-outlined text-[14px]">auto_awesome</span>让 Coordinator 自动优化班底
              </p>
              <p class="text-label-sm text-secondary">基于这段对话推断最优 Agent 与 Skill 组合。</p>
            </div>
          </label>
        </div>
        <div class="px-lg py-md border-t border-outline-variant flex items-center justify-end gap-2">
          <button onclick="closeModal('modal-save-as-mission')" class="px-3 py-1.5 text-secondary text-label-md hover:underline">取消</button>
          <button onclick="commitSaveAsMission()" class="px-3 py-1.5 bg-primary text-white rounded-lg text-label-md hover:opacity-90 flex items-center gap-1">
            <span class="material-symbols-outlined text-[14px]">check</span>保存
          </button>
        </div>
      </div>
    </div>`;
}

function commitSaveAsMission() {
  const name = $('#save-name').value.trim() || '未命名任务';
  const desc = $('#save-desc').value.trim() || '从 Quick Run 沉淀的临时对话。';
  const aiOpt = $('#ai-optimize').checked;
  const agents = aiOpt
    ? [makeAgent('通用助手','基于对话推断生成','smart_toy','你是一个通用助手，继承自 Quick Run 上下文。',['web_search','markdown_write'])]
    : [];
  const m = {
    id: uid('mis'), name, icon:'bookmark', description: desc,
    squad:{ agents, enabledSkills: aiOpt ? ['web_search','markdown_write'] : [], coordinator:{ name:'Coordinator' } },
    runs:[{
      id:'run_current', title:'当前运行', status:'running',
      conversation: state.quickRun.conversation.slice(),
      artifact: null
    }]
  };
  state.missions.unshift(m);
  state.quickRun = { turns:0, conversation:[], promptedSave:false };
  closeModal('modal-save-as-mission');
  openMission(m.id);
  showToast(`「${name}」已保存为 Mission`, 'success');
}

/* ===================== Mention popover ===================== */
function showMentionPopover(textarea) { showAgentPopover(textarea, '@'); }
function showAgentPopover(textarea, mode='@') {
  const m = getMission(); if (!m) return;
  const pop = $('#mention-popover');
  const rect = textarea.getBoundingClientRect();
  pop.style.left = (rect.left + 24) + 'px';
  pop.style.bottom = (window.innerHeight - rect.top + 8) + 'px';
  pop.style.top = 'auto';
  pop.classList.remove('hidden');

  const isEdit = mode === '#';
  const headerIcon = isEdit ? 'edit_square' : 'alternate_email';
  const headerText = isEdit ? '选择要修改配置的 Agent' : '选择要 @ 的 Agent';
  const headerColor = isEdit ? 'text-primary' : 'text-secondary';
  const borderClass = isEdit ? 'border-primary/40' : 'border-outline-variant';
  const tipText = isEdit
    ? '选中后用自然语言描述要做的修改，发送后弹出变更预览'
    : '选中后该 Agent 会接收并处理这条消息';

  pop.innerHTML = `
    <div class="bg-surface-container-lowest border ${borderClass} rounded-lg shadow-xl w-[280px] overflow-hidden">
      <div class="px-3 py-1.5 text-label-sm ${headerColor} border-b ${borderClass} flex items-center gap-1 ${isEdit ? 'bg-primary-fixed/30' : ''}">
        <span class="material-symbols-outlined text-[12px]">${headerIcon}</span>
        <span class="font-bold">${headerText}</span>
      </div>
      <div class="max-h-[240px] overflow-y-auto">
        ${m.squad.agents.map(a => `
          <div onclick="selectAgentForTrigger('${a.name.replace(/'/g,"\\'")}', '${mode}')"
               class="flex items-center gap-2 px-3 py-2 cursor-pointer ${isEdit ? 'hover:bg-primary-fixed/40' : 'hover:bg-surface-container'}">
            <div class="w-7 h-7 rounded-full ${isEdit ? 'bg-primary-fixed' : 'bg-secondary-container'} flex items-center justify-center">
              <span class="material-symbols-outlined ${isEdit ? 'text-on-primary-fixed-variant' : 'text-on-surface-variant'} text-[14px]">${a.icon}</span>
            </div>
            <div class="min-w-0 flex-1">
              <p class="font-label-md text-on-surface truncate">${escapeHTML(a.name)}</p>
              <p class="text-label-sm text-secondary truncate">${escapeHTML(a.role)}</p>
            </div>
            ${isEdit ? '<span class="material-symbols-outlined text-primary text-[14px] opacity-60">build</span>' : ''}
          </div>`).join('')}
        ${(state.customAgents||[]).length ? `
          <div class="border-t border-outline-variant/60 px-3 py-1 text-[10px] text-secondary bg-surface-container-low">自建 Agent（数据库）</div>
          ${(state.customAgents||[]).map(a => `
            <div onclick="selectAgentForTrigger('${(a.name||'').replace(/'/g,"\\'")}', '${mode}')"
                 class="flex items-center gap-2 px-3 py-2 cursor-pointer ${isEdit ? 'hover:bg-primary-fixed/40' : 'hover:bg-surface-container'}">
              <div class="w-7 h-7 rounded-full ${isEdit ? 'bg-primary-fixed' : 'bg-secondary-container'} flex items-center justify-center">
                <span class="material-symbols-outlined ${isEdit ? 'text-on-primary-fixed-variant' : 'text-on-surface-variant'} text-[14px]">${a.icon || 'smart_toy'}</span>
              </div>
              <div class="min-w-0 flex-1">
                <p class="font-label-md text-on-surface truncate">${escapeHTML(a.name||'')}</p>
                <p class="text-label-sm text-secondary truncate">${escapeHTML(a.description || a.system_prompt || '')}</p>
              </div>
              <span class="text-[10px] text-secondary bg-surface-container px-1 rounded">自建</span>
            </div>`).join('')}` : ''}
      </div>
      <div class="px-3 py-1.5 border-t ${borderClass} text-[10px] text-secondary bg-surface-container-low">
        ${tipText}
      </div>
    </div>`;
}
function hideMentionPopover() { $('#mention-popover').classList.add('hidden'); }
function selectMention(name) { selectAgentForTrigger(name, '@'); }
function selectAgentForTrigger(name, mode) {
  const ta = $('#chat-input'); if (!ta) return;
  const v = ta.value;
  const triggerIdx = mode === '@' ? v.lastIndexOf('@') : v.lastIndexOf('#');
  ta.value = (triggerIdx >= 0 ? v.slice(0, triggerIdx) : v) + mode + name + ' ';
  hideMentionPopover();
  ta.focus();
  // 触发一次 input 事件，刷新 hint
  ta.dispatchEvent(new Event('input', { bubbles:true }));
}

/* ===================== Modal close ===================== */
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) { el.classList.add('hidden'); el.innerHTML = ''; }
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    ['modal-create-mission','modal-ai-proposal','modal-agent-diff','modal-mcp-connect','modal-edit-agent','modal-save-as-mission','modal-auth'].forEach(closeModal);
    hideMentionPopover();
  }
});