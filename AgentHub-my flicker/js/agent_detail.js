/* ============================================================
   Markdown 极简渲染器（# / ## / ### / **bold** / *em* / `code` / -list）
============================================================ */
function renderMarkdown(md='') {
  if (!md) return '<p class="text-secondary italic">（无内容）</p>';
  let html = escapeHTML(md);
  // 代码块 ```
  html = html.replace(/```([\s\S]*?)```/g, (_, c) => `<pre class="bg-surface-container p-2 rounded my-2 text-[12px] font-mono overflow-x-auto">${c.replace(/^\n/, '')}</pre>`);
  html = html
    .replace(/^### (.+)$/gm, '<h3 class="text-title-md font-headline-md mt-4 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm,  '<h2 class="text-title-lg font-headline-md mt-4 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm,   '<h1 class="text-headline-md font-headline-md mt-4 mb-2">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,    '<em>$1</em>')
    .replace(/`([^`]+)`/g,    '<code class="bg-surface-container px-1 rounded text-[12px]">$1</code>')
    .replace(/^- (.+)$/gm,    '<li class="ml-5 list-disc">$1</li>')
    .replace(/(<li[\s\S]*?<\/li>\n?)+/g, m => `<ul class="my-2">${m}</ul>`)
    .split(/\n{2,}/).map(p => /^<(h\d|ul|pre)/.test(p.trim()) ? p : `<p class="my-2 leading-relaxed">${p.replace(/\n/g,'<br/>')}</p>`).join('');
  return html;
}

/* ============================================================
   Agent 详情页
============================================================ */

function openAgentDetail(missionId, agentId, source="mine") {
  let a = null;
  const resolvedMissionId = missionId || "";
  if (source === "market") {
    a = (state.agentMarket || []).find(x => x.id === agentId);
  } else if (source === "backend") {
    const raw = (state.customAgents || []).find(x => String(x.agent_id || x.id) === String(agentId));
    if (raw) a = backendAgentToDetailShape(raw);
  } else {
    const m = state.missions.find(x => x.id === missionId);
    a = m && m.squad.agents.find(x => x.id === agentId);
  }
  if (!a) return showToast("Agent 不存在");
  ensureAgentSchema(a);
  state.detail = {
    type: "agent",
    missionId: resolvedMissionId, agentId, source,
    tab: "overview",
    draft: cloneAgentForDraft(a),
    dirty: false,
    versionDropdownOpen: false,
    nlPanelOpen: true,
  };
  state.view = "agent_detail";
  render();
}

/* ========== Backend Agent 与详情页 draft 字段映射 ========== */
/* ---- A 档：前端策略 ID 与后端枚举的双向映射表 ---- */
const MEMORY_FE_TO_BE  = { none:'none', window:'sliding_window', summary:'summary' };
const MEMORY_BE_TO_FE  = { none:'none', sliding_window:'window', summary:'summary' };
const PLANNING_FE_TO_BE = { none:'direct', react:'react', plan:'plan_execute' };
const PLANNING_BE_TO_FE = { direct:'none', react:'react', plan_execute:'plan' };
const VALIDATION_FE_TO_BE = { none:'none', rule:'rules', llm:'llm_judge' };
const VALIDATION_BE_TO_FE = { none:'none', rules:'rule', llm_judge:'llm' };

function _beMemoryToFe(be) {
  if (!be || typeof be !== 'object') return {};
  const feStrategy = MEMORY_BE_TO_FE[be.strategy] || be.strategy || 'window';
  const fe = { strategy: feStrategy };
  if (be.window_size != null) fe.windowSize = be.window_size;
  if (be.summary_prompt) fe.summaryPrompt = be.summary_prompt;
  if (be.summary_threshold != null) fe.summaryThreshold = be.summary_threshold;
  // 多层记忆框架字段
  fe.semanticRetrieval = be.semantic_retrieval_enabled !== false;  // 默认 true
  fe.retrievalTopK = be.semantic_retrieval_top_k || 5;
  fe.extractFacts = be.extract_facts !== false;  // 默认 true
  fe.decayEnabled = be.decay_enabled !== false;   // 默认 true
  return fe;
}
function _fePlanningToBe(fe) {
  if (!fe || typeof fe !== 'object' || !fe.mode) return null;
  const mode = PLANNING_FE_TO_BE[fe.mode];
  // B 档（tree）—— 不下发后端
  if (!mode) return null;
  const out = { mode };
  if (fe.stepsTemplate) out.steps_template = fe.stepsTemplate;
  return out;
}
function _bePlanningToFe(be) {
  if (!be || typeof be !== 'object') return {};
  const fe = { mode: PLANNING_BE_TO_FE[be.mode] || 'react' };
  if (be.steps_template) fe.stepsTemplate = be.steps_template;
  return fe;
}
function _feMemoryToBe(fe) {
  if (!fe || typeof fe !== 'object' || !fe.strategy) return null;
  const strategy = MEMORY_FE_TO_BE[fe.strategy];
  // B 档（kv）—— 不下发
  if (!strategy) return null;
  const out = { strategy };
  if (strategy === 'sliding_window') {
    out.window_size = parseInt(fe.windowSize) || 10;
  } else if (strategy === 'summary') {
    if (fe.summaryPrompt) out.summary_prompt = fe.summaryPrompt;
    if (fe.summaryThreshold != null) out.summary_threshold = parseInt(fe.summaryThreshold) || 4000;
  }
  // 多层记忆框架字段（可选，默认 true）
  out.semantic_retrieval_enabled = fe.semanticRetrieval !== false;
  out.semantic_retrieval_top_k = parseInt(fe.retrievalTopK) || 5;
  out.extract_facts = fe.extractFacts !== false;
  out.decay_enabled = fe.decayEnabled !== false;
  return out;
}
function _beValidationToFe(be) {
  if (!be || typeof be !== 'object') return {};
  const fe = { strategy: VALIDATION_BE_TO_FE[be.strategy] || 'none' };
  if (Array.isArray(be.rules)) {
    // 后端是 [{type:'regex', pattern, message}] —— 转为前端字符串数组（暂只显示 pattern）
    fe.rules = be.rules.map(r => (r && typeof r === 'object') ? (r.pattern || '') : String(r||''));
  }
  if (be.judge_prompt) fe.judgePrompt = be.judge_prompt;
  if (be.max_retries != null) fe.maxRetries = be.max_retries;
  return fe;
}
function _feValidationToBe(fe) {
  if (!fe || typeof fe !== 'object' || !fe.strategy) return null;
  const strategy = VALIDATION_FE_TO_BE[fe.strategy];
  // B 档（human）—— 不下发
  if (!strategy) return null;
  const out = { strategy };
  if (strategy === 'rules') {
    out.rules = (Array.isArray(fe.rules) ? fe.rules : [])
      .map(s => String(s||'').trim())
      .filter(Boolean)
      .map(pat => ({ type:'regex', pattern: pat }));
  } else if (strategy === 'llm_judge') {
    if (fe.judgePrompt) out.judge_prompt = fe.judgePrompt;
  }
  if (fe.maxRetries != null) out.max_retries = parseInt(fe.maxRetries) || 0;
  return out;
}

function backendAgentToDetailShape(raw) {
  return {
    id: raw.agent_id,
    agent_id: raw.agent_id,
    name: raw.name || '',
    role: raw.description || '',
    icon: raw.icon || 'smart_toy',
    model: raw.llm_adapter || raw.model || 'tongyi',
    kind: 'agent',
    systemPrompt: raw.system_prompt || raw.systemPrompt || '',
    skills: Array.isArray(raw.tools) ? [...raw.tools] : (Array.isArray(raw.skills) ? [...raw.skills] : []),
    mcpTools: [],
    teamMemberIds: [],
    versions: [],
    readme: '',
    // A 档：3 类配置 backends→draft（snake_case + backends 枚举 → camelCase + 前端 id）
    memoryConfig: _beMemoryToFe(raw.memory_config),
    planningConfig: _bePlanningToFe(raw.planning_config),
    validationConfig: _beValidationToFe(raw.validation_config),
    updatedAt: raw.updated_at || raw.created_at || Date.now(),
    _source: 'backend',
    _backendOriginal: raw
  };
}

function detailDraftToBackendPayload(draft) {
  return {
    name: (draft.name || '').trim(),
    icon: draft.icon || 'smart_toy',
    description: draft.role || '',
    system_prompt: draft.systemPrompt || '',
    llm_adapter: draft.model || 'tongyi',
    tools: Array.isArray(draft.skills) ? draft.skills : [],
    // A 档：draft→backends（前端 id → 后端枚举），B 档子类（kv/tree/human）会被转成 null 不下发
    memory_config: _feMemoryToBe(draft.memoryConfig),
    planning_config: _fePlanningToBe(draft.planningConfig),
    validation_config: _feValidationToBe(draft.validationConfig)
  };
}

function cloneAgentForDraft(a) {
  ensureAgentSchema(a);
  return {
    name: a.name, role: a.role, icon: a.icon, model: a.model,
    kind: a.kind || 'agent',
    systemPrompt: a.systemPrompt || '',
    skills: [...(a.skills||[])],
    mcpTools: [...(a.mcpTools||[])],
    teamMemberIds: [...(a.teamMemberIds||[])],
    memoryConfig:    JSON.parse(JSON.stringify(a.memoryConfig    || {})),
    planningConfig:  JSON.parse(JSON.stringify(a.planningConfig  || {}))
  };
}

function getCurrentAgent() {
  if (!state.detail || state.detail.type !== "agent") return null;
  if (state.detail.source === "market") {
    return (state.agentMarket || []).find(x => x.id === state.detail.agentId) || null;
  }
  if (state.detail.source === "backend") {
    const raw = (state.customAgents || []).find(x =>
      String(x.agent_id || x.id) === String(state.detail.agentId)
    );
    return raw ? backendAgentToDetailShape(raw) : null;
  }
  const m = state.missions.find(x => x.id === state.detail.missionId);
  return m && m.squad.agents.find(x => x.id === state.detail.agentId);
}

// 此 Agent (按 id) 出现在哪些 Mission（如果共享了 id；多数情况只在自己创建的那一个）
// 进一步：按"同名"也算"相关"（演示数据中 Agent 是 Mission 内独立创建的，没有跨 Mission 同 ID 的）
function getAgentRelatedMissions(agent) {
  if (!agent) return [];
  const relatedById   = state.missions.filter(m => m.squad.agents.some(a => a.id === agent.id));
  const relatedByName = state.missions.filter(m => m.squad.agents.some(a => a.name === agent.name && a.id !== agent.id));
  // 去重，id 优先
  const map = new Map();
  relatedById.forEach(m => map.set(m.id, { mission: m, viaName: false }));
  relatedByName.forEach(m => { if (!map.has(m.id)) map.set(m.id, { mission: m, viaName: true }); });
  return [...map.values()];
}

function setDetailTab(tab) {
  if (!state.detail) return;
  state.detail.tab = tab;
  state.detail.versionDropdownOpen = false;
  render();
}

function toggleAgentDetailNLPanel() {
  if (!state.detail || state.detail.type !== 'agent') return;
  state.detail.nlPanelOpen = state.detail.nlPanelOpen === false;
  render();
}

function toggleSkillPanel() {
  state.skillPanelOpen = !state.skillPanelOpen;
  if (state.skillPanelOpen && !state.skills.loaded) {
    loadSkills();
  }
  render();
}

function toggleActiveSkill(slug) {
  if (!state.activeSkills) state.activeSkills = [];
  const idx = state.activeSkills.indexOf(slug);
  if (idx >= 0) {
    state.activeSkills.splice(idx, 1);
  } else {
    state.activeSkills.push(slug);
  }
  render();
}

function markDetailDirty() {
  if (!state.detail) return;
  if (!state.detail.dirty) {
    state.detail.dirty = true;
    // 仅更新顶栏（避免每次按键 rerender 丢失焦点）
    const saveBtn = document.getElementById('detail-save-btn');
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.classList.remove('bg-surface-container','text-secondary','cursor-not-allowed');
      saveBtn.classList.add('bg-primary','text-white','hover:opacity-90');
      saveBtn.innerHTML = '<span class="material-symbols-outlined text-[16px]">save</span>保存';
    }
    const dot = document.getElementById('detail-dirty-dot');
    if (dot) dot.classList.remove('hidden');
  }
}
function closeDetail() {
  if (state.detail && state.detail.dirty) {
    if (!confirm("当前有未保存的改动，确认离开？")) return false;
  }
  const detailType = state.detail && state.detail.type;
  state.detail = null;
  state.view = detailType === "agent" ? "agents" : "skills";
  if (state.view === "skills" && !state.skills.loaded) loadSkills();
  render();
  return true;
}

// 拦截 SideNav 切换：dirty 时弹确认（统一拦截 openMission/openDashboard/...）
function guardLeaveDetail(nextFn) {
  if (state.detail && state.detail.dirty) {
    if (!confirm('当前有未保存的改动，确认离开？')) return;
    state.detail = null;
  } else if (state.detail) {
    state.detail = null;
  }
  nextFn();
}

function renderAgentDetailPage() {
  const a = getCurrentAgent();
  if (!a) {
    return `<div class="flex-1 flex items-center justify-center text-secondary">Agent 不存在 <button class="ml-2 text-primary underline" onclick="closeDetail()">返回</button></div>`;
  }
  const d = state.detail;
  const draft = d.draft;
  const tab = d.tab;
  const dirty = d.dirty;
  const related = getAgentRelatedMissions(a);
  const allSkills = getAllSkills();

  const tabs = [
    { id:'overview',   icon:'dashboard',        label:'概览' },
    { id:'prompt',     icon:'edit_note',        label:'System Prompt' },
    { id:'skills',     icon:'build',            label:'Tools' },
    { id:'memory',     icon:'memory',           label:'记忆' },
    { id:'planning',   icon:'account_tree',     label:'规划' },
    { id:'validation', icon:'fact_check',       label:'校验' },
    { id:'hooks',      icon:'webhook',          label:'Hooks' },
    ...(draft.kind === 'team' ? [{ id:'team', icon:'hub', label:'Agents' }] : []),
    { id:'readme',     icon:'description',      label:'文档' },
    { id:'missions',   icon:'task',             label:`关联 Mission (${related.length})` },
  ];

  let body = '';
  if (tab === 'overview') {
    body = `
      <div class="space-y-md max-w-2xl">
        <div>
          <label class="text-label-md text-secondary mb-1 block">角色类型</label>
          <div class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border
                      ${draft.kind==='team'
                        ? 'border-primary/40 bg-primary-fixed/40 text-primary'
                        : 'border-tertiary/40 bg-tertiary-container text-on-tertiary-container'}">
            <span class="material-symbols-outlined text-[16px]">
              ${draft.kind==='team' ? 'hub' : 'smart_toy'}
            </span>
            <span class="text-label-md font-bold">
              ${draft.kind==='team' ? 'Team' : 'Agent'}
            </span>
            <span class="material-symbols-outlined text-[14px] opacity-60 ml-1" title="Kind 在创建时确定，不可修改">lock</span>
          </div>
          <p class="text-[11px] text-secondary mt-2 leading-relaxed">
            类型在创建时确定，之后不可直接修改。
            ${draft.kind==='team'
              ? 'Team 是 Mission 的唯一主协同单元：负责拆解任务、并行调度 Agents 并汇总结果。'
              : 'Agent 由 Team 按需调起完成具体子任务；当 Mission 里只有 1 个角色时，它会自动承担 Team 职责。'}
          </p>
        </div>
        <div>
          <label class="text-label-md text-secondary mb-1 block">名称</label>
          <input value="${escapeHTML(draft.name)}" oninput="state.detail.draft.name=this.value; markDetailDirty()"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
        </div>
        <div>
          <label class="text-label-md text-secondary mb-1 block">角色描述</label>
          <textarea rows="2" oninput="state.detail.draft.role=this.value; markDetailDirty()"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary">${escapeHTML(draft.role)}</textarea>
        </div>
        <div>
          <label class="text-label-md text-secondary mb-1 block">图标 (material-symbols)</label>
          <input value="${escapeHTML(draft.icon)}" oninput="state.detail.draft.icon=this.value; markDetailDirty()"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
        </div>
        <div>
          <label class="text-label-md text-secondary mb-1 block">模型</label>
          <select onchange="state.detail.draft.model=this.value; markDetailDirty()"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary">
            ${MODEL_OPTIONS.map(m =>
              `<option value="${m}" ${draft.model===m?'selected':''}>${m}</option>`).join('')}
          </select>
        </div>
      </div>`;
  } else if (tab === 'prompt') {
    body = `
      <div class="max-w-3xl">
        <div class="flex items-center justify-between mb-1">
          <label class="text-label-md text-secondary">System Prompt
            <button onclick="improveAgentPrompt('detail-agent-prompt')" title="AI 自动优化提示词" class="ml-2 px-2 py-0.5 rounded border border-primary/40 text-primary text-[11px] hover:bg-primary-fixed/30 transition-colors font-medium">✨ AI 优化</button>
          </label>
          <button onclick="resetAgentPromptToOriginal()" class="text-[12px] text-secondary hover:text-primary">恢复服务器版本</button>
        </div>
        <textarea id="detail-agent-prompt" rows="14" oninput="state.detail.draft.systemPrompt=this.value; markDetailDirty()"
          class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md font-mono text-[12px] focus:outline-none focus:border-primary"
          placeholder="你是一名...">${escapeHTML(draft.systemPrompt)}</textarea>
        <p class="text-[11px] text-secondary mt-1">该 Prompt 决定 Agent 的行为基调与边界。保存后会写入此 Mission 中该 Agent 的副本。</p>
      </div>`;
  } else if (tab === 'skills') {
    body = renderAgentDetailToolsTab(draft, allSkills);
  } else if (tab === 'memory') {
    body = renderAgentDetailMemoryTab(draft);
  } else if (tab === 'planning') {
    body = renderAgentDetailPlanningTab(draft);
  } else if (tab === 'validation') {
    body = renderAgentDetailValidationTab(draft);
  } else if (tab === 'hooks') {
    body = renderAgentDetailHooksTab(draft);
  } else if (tab === 'team') {
    body = renderAgentDetailTeamTab(a, draft);
  } else if (tab === 'readme') {
    body = `
      <div class="grid grid-cols-2 gap-md max-w-5xl">
        <div>
          <label class="text-label-md text-secondary mb-1 block">Markdown 编辑</label>
          <textarea rows="20" oninput="state.detail.draft.readme=this.value; markDetailDirty(); document.getElementById('readme-preview').innerHTML=renderMarkdown(this.value)"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md font-mono text-[12px] focus:outline-none focus:border-primary"
            placeholder="# Agent 简介\n\n描述这个 Agent 的能力、用法...">${escapeHTML(draft.readme)}</textarea>
        </div>
        <div>
          <label class="text-label-md text-secondary mb-1 block">实时预览</label>
          <div id="readme-preview" class="px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg min-h-[460px] text-body-md prose-sm">${renderMarkdown(draft.readme)}</div>
        </div>
      </div>`;
  } else if (tab === 'missions') {
    body = related.length ? `
      <div class="grid grid-cols-2 gap-md max-w-4xl">
        ${related.map(({mission,viaName}) => `
          <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-md hover:border-primary/40 transition-colors cursor-pointer"
               onclick="guardLeaveDetail(()=>openMission('${mission.id}'))">
            <div class="flex items-center gap-3 mb-2">
              <div class="w-10 h-10 rounded-lg bg-secondary-container flex items-center justify-center">
                <span class="material-symbols-outlined text-on-surface-variant">${escapeHTML(mission.icon||'task')}</span>
              </div>
              <div class="min-w-0">
                <p class="font-label-md text-on-surface truncate">${escapeHTML(mission.name)}</p>
                <p class="text-label-sm text-secondary">${mission.squad.agents.length} agents · ${(mission.runs||[]).length} runs ${viaName?'· <span class="text-amber-700">同名 Agent</span>':''}</p>
              </div>
            </div>
            <p class="text-body-md text-secondary line-clamp-2">${escapeHTML(mission.description||'—')}</p>
          </div>`).join('')}
      </div>
    ` : `
      <div class="text-center text-secondary p-xl border border-dashed border-outline-variant rounded-xl max-w-2xl">
        <span class="material-symbols-outlined text-[40px] opacity-40 mb-2 block">task</span>
        <p>这个 Agent 目前只在当前 Mission 中。</p>
      </div>`;
  }

  // A 档：backends Agent 详情页中 memory/planning/validation 3 个 Tab 已解锁可编辑
  // 三个字段在保存时通过 detailDraftToBackendPayload 一并 PUT 给后端，
  // 后端 normalize_*_config 校验后持久化。
  // hooks/team 两个 Tab 当前后端无字段支持，继续锁定。
  if (state.detail.source === 'backend' && ['hooks','team'].includes(tab)) {
    const labelMap = { hooks:'Hooks', team:'Agents' };
    body = `
      <div class="max-w-4xl">
        <div class="mb-md p-3 rounded-lg border flex items-start gap-2"
             style="background: rgba(220, 38, 38, 0.08); border-color: rgba(220, 38, 38, 0.3); color: rgb(153, 27, 27);">
          <span class="material-symbols-outlined text-[18px] mt-0.5">lock</span>
          <div class="text-label-md leading-relaxed">
            <b>${labelMap[tab]}</b> 配置目前暂不支持更改，敬请期待后续迭代。
            <br/><span class="text-[11px] opacity-80">下方为 UI 预览，已禁用编辑。</span>
          </div>
        </div>
        <fieldset disabled class="opacity-60 pointer-events-none select-none border-0 p-0 m-0">
          ${body}
        </fieldset>
      </div>`;
  }

  const versions = a.versions || [];
  const nlPanelOpen = d.nlPanelOpen !== false;

  return `
    <div class="flex-1 overflow-y-auto bg-background">
      <header class="px-xl pt-lg pb-md border-b border-outline-variant flex items-center justify-between gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <button onclick="closeDetail()" class="text-secondary hover:text-primary flex items-center gap-1 text-label-md">
            <span class="material-symbols-outlined text-[18px]">arrow_back</span>Agents 库
          </button>
          <span class="text-secondary">/</span>
          <div class="w-9 h-9 rounded-lg bg-secondary-container flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined text-on-surface-variant">${escapeHTML(draft.icon||'smart_toy')}</span>
          </div>
          <div class="min-w-0">
            <p class="font-headline-md text-title-lg text-on-surface truncate flex items-center gap-2">${escapeHTML(draft.name)}<span id="detail-dirty-dot" class="${dirty?'':'hidden'} w-2 h-2 rounded-full bg-amber-500" title="有未保存改动"></span></p>
            <p class="text-label-md text-secondary truncate">在 ${related.length} 个 Mission 中 · ${versions.length} 个历史版本</p>
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <div class="relative">
            <button onclick="state.detail.versionDropdownOpen=!state.detail.versionDropdownOpen; render()"
              class="px-3 py-1.5 rounded-lg text-label-md border border-outline-variant text-on-surface-variant hover:bg-surface-container-low flex items-center gap-1">
              <span class="material-symbols-outlined text-[16px]">history</span>
              历史版本 (${versions.length})
              <span class="material-symbols-outlined text-[14px]">expand_more</span>
            </button>
            ${d.versionDropdownOpen ? `
              <div class="absolute right-0 top-full mt-1 w-80 max-h-80 overflow-y-auto bg-surface border border-outline-variant rounded-lg shadow-lg z-10">
                ${versions.length ? versions.map((v,i) => `
                  <div class="px-3 py-2 hover:bg-surface-container-low cursor-pointer border-b border-outline-variant/50 last:border-0"
                       onclick="showAgentVersionDiff(${i})">
                    <p class="text-label-md text-on-surface">v${i+1} · ${escapeHTML(v.ts||'-')}</p>
                    <p class="text-[11px] text-secondary truncate">${escapeHTML(v.note||'手动保存')}</p>
                  </div>`).join('') : `<div class="p-3 text-secondary text-label-md text-center">还没有历史版本</div>`}
              </div>` : ''}
          </div>
          <button id="detail-save-btn" onclick="commitAgentSave()" ${dirty?'':'disabled'}
            class="px-4 py-1.5 rounded-lg text-label-md flex items-center gap-1
                   ${dirty?'bg-primary text-white hover:opacity-90':'bg-surface-container text-secondary cursor-not-allowed'}">
            <span class="material-symbols-outlined text-[16px]">save</span>保存
          </button>
        </div>
      </header>

      <div class="flex">
        <aside class="w-60 shrink-0 border-r border-outline-variant py-md min-h-[60vh]">
          ${tabs.map(t => `
            <button onclick="setDetailTab('${t.id}')"
              class="w-full px-4 py-2.5 flex items-center gap-2 text-label-md transition-colors text-left
                     ${tab===t.id ? 'bg-primary-fixed/40 text-primary border-l-2 border-primary' : 'text-on-surface-variant hover:bg-surface-container-low border-l-2 border-transparent'}">
              <span class="material-symbols-outlined text-[18px]">${t.icon}</span>${t.label}
            </button>`).join('')}
        </aside>
        <section class="flex-1 min-w-0 flex">
          <div class="flex-1 min-w-0 px-xl py-lg">${body}</div>
          <aside class="${nlPanelOpen ? 'w-[360px]' : 'w-[64px]'} shrink-0 border-l border-outline-variant/60 bg-surface transition-all duration-200 ease-out">
            <div class="h-full ${nlPanelOpen ? 'px-md py-lg' : 'px-2 py-lg'}">
              <button onclick="toggleAgentDetailNLPanel()"
                class="w-full mb-3 ${nlPanelOpen ? 'px-3 py-2 justify-between' : 'px-2 py-2 justify-center'} rounded-lg border border-outline-variant bg-surface-container-lowest text-label-md text-on-surface-variant hover:border-primary/40 hover:text-primary flex items-center gap-2">
                <span class="material-symbols-outlined text-[18px]">${nlPanelOpen ? 'right_panel_close' : 'left_panel_open'}</span>
                ${nlPanelOpen ? `<span>${tab === 'missions' ? '显示中' : '自然语言修改'}</span>` : ''}
              </button>
              ${nlPanelOpen ? renderAgentDetailNLPanel(a, draft, tab) : `
                <button onclick="toggleAgentDetailNLPanel()"
                  class="w-full mt-2 px-2 py-3 rounded-xl border border-dashed border-outline-variant text-secondary hover:text-primary hover:border-primary/40 flex flex-col items-center gap-2">
                  <span class="material-symbols-outlined text-[20px]">auto_awesome</span>
                  <span class="[writing-mode:vertical-rl] text-[11px] tracking-[0.2em]">修改</span>
                </button>
              `}
            </div>
          </aside>
        </section>
      </div>
    </div>`;
}

/* ===== Agent 详情页自然语言修改面板 ===== */
function renderAgentDetailNLPanel(a, draft, tab) {
  // 不同 Tab 给不同提示词与 chip
  const presets = {
    overview: {
      hint: '例如：把名字改为 "财报分析专家"；模型换成 GPT-4o',
      chips: ['换个更专业的名字', '改成 Claude 3.5 Sonnet', '把角色描述写得更精确'],
    },
    prompt: {
      hint: '例如：让它更关注新能源板块；不要使用过于学术的措辞',
      chips: ['让它更关注 AI 板块', '不要使用过于专业的术语', '加一段：始终给出引用来源'],
    },
    skills: {
      hint: '例如：加 web_search 技能；移除 chart_render',
      chips: ['加 web_search 技能', '移除 chart_render', '加 markdown_write'],
    },
    memory: {
      hint: '例如：开启语义检索；扩大窗口到 15 轮；关闭自动提取',
      chips: ['让它记得更多', '开启语义记忆', '只保留要点摘要', '关闭自动提取事实'],
    },
    planning: {
      hint: '例如：先制定计划再执行；遇到分支条件先停下问用户',
      chips: ['先制定计划再执行', '复杂任务必须确认', '简化规划流程'],
    },
    validation: {
      hint: '例如：每步执行后做一次自检；不通过自动重试',
      chips: ['执行后自检', '失败自动重试 3 次', '关闭自动校验'],
    },
    hooks: {
      hint: '例如：执行前打日志；遇错误发通知',
      chips: ['执行前打日志', '错误时发通知', '完成后归档'],
    },
    team: {
      hint: '例如：加一个会写报告的 Agent；让它更倾向调度 Data Extractor',
      chips: ['让它优先调度 Data Extractor', '让它更平均地分配任务'],
    },
    readme: {
      hint: '例如：根据 Prompt 自动生成一段 README；补充使用示例',
      chips: ['自动生成 README', '补充使用示例', '添加一节 FAQ'],
    },
    missions: {
      hint: '本 Tab 仅展示关联，不可在此修改 Agent。',
      chips: [],
    },
  };
  const p = presets[tab] || { hint: '用一句话描述你想怎么改这个 Agent。', chips: [] };

  return `
    <div class="p-md border border-outline-variant rounded-xl bg-surface-container-lowest">
      <p class="font-label-md text-on-surface mb-1 flex items-center gap-1.5">
        <span class="material-symbols-outlined text-[16px] text-primary">auto_awesome</span>
        用自然语言修改 Agent
      </p>
      <p class="text-[11px] text-secondary mb-2 leading-relaxed">
        当前正在编辑 <b class="text-on-surface">${escapeHTML(draft.name)}</b>。输入一句话生成修改 Diff，确认后才会应用。${tab==='missions'?'<br/><span class="text-amber-700">本 Tab 不支持修改</span>':''}
      </p>
      <textarea id="agent-detail-nl-input" rows="4"
        ${tab==='missions'?'disabled':''}
        placeholder="${escapeAttr(p.hint)}"
        class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg p-2 text-body-md focus:border-primary focus:ring-0 resize-none ${tab==='missions'?'opacity-50 cursor-not-allowed':''}"></textarea>
      ${p.chips.length ? `
        <div class="flex flex-wrap gap-1 mt-2">
          ${p.chips.map(c => `<button onclick="setAgentDetailNLPreset('${escapeAttr(c)}')" class="text-[11px] px-2 py-0.5 rounded-full border border-outline-variant text-secondary hover:border-primary/40 hover:text-primary">${escapeHTML(c)}</button>`).join('')}
        </div>` : ''}
      <button onclick="submitAgentDetailNLEdit()" ${tab==='missions'?'disabled':''}
        class="w-full mt-2 ${tab==='missions'?'bg-surface-container text-secondary cursor-not-allowed':'bg-primary text-white hover:opacity-90'} px-3 py-1.5 rounded-lg text-label-md flex items-center justify-center gap-1">
        <span class="material-symbols-outlined text-[16px]">send</span>解析并预览
      </button>
      <p class="text-[10px] text-secondary mt-2 leading-relaxed">
        改动会在弹窗中展示 Diff，确认后才应用，可在历史版本回滚。
      </p>
    </div>`;
}

function setAgentDetailNLPreset(text) {
  const ta = document.getElementById('agent-detail-nl-input');
  if (!ta) return;
  ta.value = text;
  ta.focus();
}

/* ===== Skill 管理面板 ===== */
function renderSkillPanel() {
  const mine = state.skills.mine || [];
  const market = state.skills.market || [];
  const builtin = market.filter(s => s.authorName === 'system');
  const available = [...mine, ...market.filter(s => s.authorName !== 'system')];
  const activeMap = {};
  (state.activeSkills || []).forEach(s => activeMap[s] = true);

  return `
  <div id="skill-panel" class="fixed inset-0 z-50 flex items-center justify-center">
    <div class="fixed inset-0 bg-black/40" onclick="toggleSkillPanel()"></div>
    <div class="relative w-[480px] max-h-[80vh] bg-surface-container-lowest rounded-2xl border border-outline-variant shadow-2xl flex flex-col overflow-hidden">
      <div class="flex items-center justify-between px-lg py-lg border-b border-outline-variant">
        <div>
          <h2 class="text-title-lg font-medium">技能管理</h2>
          <p class="text-label-sm text-secondary mt-1">启用技能后，AI 会在回答时遵循技能指示</p>
        </div>
        <button onclick="toggleSkillPanel()" class="p-2 rounded-full hover:bg-surface-container-low transition-colors">
          <span class="material-symbols-outlined text-[20px]">close</span>
        </button>
      </div>
      <div class="flex-1 overflow-y-auto p-lg">
        ${available.length === 0 ? `
          <div class="text-center py-xl">
            <span class="material-symbols-outlined text-[48px] text-secondary">extension</span>
            <p class="text-body-md text-secondary mt-md">暂无可用技能</p>
          </div>
        ` : `
          <div class="grid gap-md">
            ${available.map(skill => `
              <div class="flex items-center gap-md p-md rounded-xl bg-surface-container-high border border-outline-variant hover:border-primary/30 transition-colors ${activeMap[skill.slug] ? 'ring-2 ring-primary/50' : ''}">
                <div class="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <span class="material-symbols-outlined text-[20px] text-primary">auto_awesome</span>
                </div>
                <div class="flex-1 min-w-0">
                  <div class="text-label-lg font-medium">${escapeHTML(skill.name)}</div>
                  <div class="text-label-sm text-secondary line-clamp-2">${escapeHTML(skill.description || skill.slug)}</div>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" class="sr-only peer" ${activeMap[skill.slug] ? 'checked' : ''} onchange="toggleActiveSkill('${skill.slug}')">
                  <div class="w-11 h-6 bg-surface-switch-unselected rounded-full peer peer-checked:bg-primary transition-colors after:content-[''] after:absolute after:top-[3px] after:left-[3px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-5"></div>
                </label>
              </div>
            `).join('')}
          </div>
        `}
      </div>
      <div class="px-lg py-md border-t border-outline-variant flex items-center justify-between">
        <span class="text-label-sm text-secondary">已启用 ${state.activeSkills?.length || 0} 个技能</span>
        <button onclick="toggleSkillPanel()" class="px-4 py-2 bg-primary text-white rounded-lg hover:opacity-90 text-label-md">
          完成
        </button>
      </div>
    </div>
  </div>`;
}

/* ---- A 档：3 类配置的自然语言解析（轻量正则）----
 * 命中后直接改写 draft.*Config + markDetailDirty + render，返回 true。
 * 未命中返回 false，调用方再走原 parseEditIntent 走 Diff 弹窗流程。
 */
function tryApplyConfigNLEdit(raw, draft) {
  if (!raw || !draft) return false;
  const txt = String(raw);
  let hit = null;

  // ---------- 记忆 ----------
  // 关闭记忆 / 不保留记忆 / 清空记忆
  if (/(关闭|不保留|清空|去掉)\s*(对话)?\s*(记忆|memory|历史)/i.test(txt)) {
    draft.memoryConfig = { strategy: 'none' };
    hit = '已切换记忆策略为「不保留」';
  }
  // 滑动窗口 N 轮
  else if (/(滑动窗口|sliding[ _-]?window|最近\s*\d+\s*轮)/i.test(txt)) {
    const m = txt.match(/(\d+)\s*(轮|条|条对话)/);
    const n = m ? Math.max(1, Math.min(100, parseInt(m[1]))) : 10;
    draft.memoryConfig = { strategy: 'window', windowSize: n };
    hit = `已切换记忆策略为「滑动窗口」，窗口 ${n} 轮`;
  }
  // 摘要 / summary
  else if (/(摘要|压缩|summary)/i.test(txt) && /(记忆|memory|对话|历史)/i.test(txt)) {
    draft.memoryConfig = Object.assign({}, draft.memoryConfig, { strategy: 'summary' });
    hit = '已切换记忆策略为「摘要压缩」';
  }
  // 语义记忆 / 开启语义检索
  else if (/(开启|打开|启用)\s*(语义|semantic)\s*(记忆|检索|搜索)/i.test(txt)) {
    draft.memoryConfig = Object.assign({}, draft.memoryConfig, { semanticRetrieval: true });
    hit = '已开启语义记忆检索';
  }
  // 关闭语义记忆
  else if (/(关闭|停用|禁用)\s*(语义|semantic)\s*(记忆|检索|搜索)/i.test(txt)) {
    draft.memoryConfig = Object.assign({}, draft.memoryConfig, { semanticRetrieval: false });
    hit = '已关闭语义记忆检索';
  }
  // 自动提取事实
  else if (/(开启|打开|启用)\s*(自动\s*)?(提取|抽取)\s*(事实|记忆|知识)/i.test(txt)) {
    draft.memoryConfig = Object.assign({}, draft.memoryConfig, { extractFacts: true });
    hit = '已开启自动事实提取';
  }
  // 关闭自动提取
  else if (/(关闭|停用|禁用)\s*(自动\s*)?(提取|抽取)\s*(事实|记忆|知识)/i.test(txt)) {
    draft.memoryConfig = Object.assign({}, draft.memoryConfig, { extractFacts: false });
    hit = '已关闭自动事实提取';
  }

  // ---------- 规划 ----------
  if (!hit) {
    if (/(直接回答|不规划|direct)/i.test(txt) && /(规划|planning|模式)/i.test(txt)) {
      draft.planningConfig = { mode: 'none' };
      hit = '已切换规划模式为「直接回答」';
    } else if (/(react|思考[\-\s]?行动|reasoning\s*and\s*acting)/i.test(txt)) {
      draft.planningConfig = { mode: 'react' };
      hit = '已切换规划模式为「ReAct」';
    } else if (/(plan[\-\s]?execute|先规划再执行|分步执行|计划再执行)/i.test(txt)) {
      draft.planningConfig = Object.assign({}, draft.planningConfig, { mode: 'plan' });
      hit = '已切换规划模式为「Plan-Execute」';
    }
  }

  // ---------- 校验 ----------
  if (!hit) {
    if (/(关闭|不要|去掉)\s*(校验|validation|审查)/i.test(txt)) {
      draft.validationConfig = { strategy: 'none' };
      hit = '已切换校验策略为「不校验」';
    } else if (/(规则\s*校验|正则\s*校验|rule|regex)/i.test(txt)) {
      draft.validationConfig = Object.assign({}, draft.validationConfig, { strategy: 'rule', rules: draft.validationConfig?.rules || [] });
      hit = '已切换校验策略为「规则校验」';
    } else if (/(llm\s*judge|llm\s*评审|让\s*llm\s*判定|大模型\s*评审)/i.test(txt)) {
      draft.validationConfig = Object.assign({}, draft.validationConfig, { strategy: 'llm' });
      hit = '已切换校验策略为「LLM Judge」';
    }
  }

  if (!hit) return false;
  markDetailDirty();
  render();
  showToast(hit + '，请在右侧 Tab 中确认细节并点击保存。', 'success');
  return true;
}


async function renderAgentDetailNLEdit() {
  if (!state.detail || state.detail.type !== 'agent') return;
  const ta = document.getElementById('agent-detail-nl-input');
  if (!ta) return;
  const raw = (ta.value || '').trim();
  if (!raw) { showToast('请先输入修改指令', 'error'); return; }
  const draft = state.detail.draft;
  const a = getCurrentAgent();
  if (!a || !draft) return;

  // A 档：先尝试用 NL 调整 3 类配置（memory / planning / validation），命中即直接改 draft + render
  if (tryApplyConfigNLEdit(raw, draft)) {
    ta.value = '';
    return;
  }

  // 强制锁定到当前 Agent：把 # 前缀替换为当前 Agent 名
  let text = raw.replace(/^\s*#[^\s#@]+\s*/, '');
  text = `#${draft.name} ` + text;
  // missionId 已经匹配 state.missionId / state.detail.missionId；parseEditIntent 默认用 getMission()
  // 临时同步 state.missionId 以确保 parseEditIntent 与 openModalAgentDiff 都定位到当前 Mission
  const prevMid = state.missionId;
  state.missionId = state.detail.missionId;
  let intent = null;
  try { intent = parseEditIntent(text); } finally {}
  if (!intent) {
    state.missionId = prevMid;
    showToast('未能解析出明确的修改意图。可换一种说法，或直接编辑左侧表单。', 'error');
    return;
  }
  // 双重保险：强制 intent.agentId = 当前 Agent
  if (intent.agentId !== a.id) intent.agentId = a.id;
  ta.value = '';
  openModalAgentDiff(intent);
  // 关闭后恢复 missionId
  const root = document.getElementById('modal-agent-diff');
  if (root) {
    const observer = new MutationObserver(() => {
      if (root.classList.contains('hidden')) {
        state.missionId = prevMid;
        observer.disconnect();
      }
    });
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
  } else {
    state.missionId = prevMid;
  }
}

function renderAgentDetailToolsTab(draft, allSkills) {
  const sub = state.agentToolsSub || 'skill';
  const subTabs = `
    <div class="inline-flex items-center gap-1 p-0.5 bg-surface-container rounded-md border border-outline-variant text-label-sm">
      <button onclick="state.agentToolsSub='skill';render()"
        class="px-2.5 py-1 rounded ${sub==='skill' ? 'bg-surface text-primary font-bold' : 'text-secondary'}">
        Skill <span class="text-[10px] opacity-70">${draft.skills.length}</span>
      </button>
      <button onclick="state.agentToolsSub='mcp';render()"
        class="px-2.5 py-1 rounded ${sub==='mcp' ? 'bg-surface text-primary font-bold' : 'text-secondary'}">
        MCP <span class="text-[10px] opacity-70">${draft.mcpTools.length}</span>
      </button>
    </div>`;

  if (sub === 'mcp') {
    const mcpTools = getAllMcpTools();
    const groupByServer = {};
    mcpTools.forEach(t => {
      if (!groupByServer[t.serverId]) groupByServer[t.serverId] = { name: t.serverName, list: [] };
      groupByServer[t.serverId].list.push(t);
    });
    const enabledSet = new Set(draft.mcpTools);
    const empty = mcpTools.length === 0;
    return `
      <div class="max-w-3xl">
        <div class="flex items-center justify-between mb-3">
          <p class="text-label-md text-secondary">勾选此 Agent 可调用的 MCP 工具（${draft.mcpTools.length} / ${mcpTools.length}）：</p>
          ${subTabs}
        </div>
        ${empty ? `
          <div class="text-center text-secondary p-lg border border-dashed border-outline-variant rounded-lg">
            <span class="material-symbols-outlined text-[36px] opacity-40 mb-2 block">cable</span>
            <p>还没有可用 MCP Tools</p>
            <button onclick="openToolsPage()" class="mt-2 text-primary font-bold hover:underline text-label-md">去接入 MCP Server →</button>
          </div>
        ` : Object.entries(groupByServer).map(([sid, g]) => `
          <div class="mb-3">
            <p class="text-label-sm text-secondary mb-1.5 flex items-center gap-1.5 px-1">
              <span class="material-symbols-outlined text-[14px]">cable</span>${escapeHTML(g.name)}
            </p>
            <div class="grid grid-cols-2 gap-2">
              ${g.list.map(t => {
                const on = enabledSet.has(t.key);
                return `
                  <label class="flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer transition-colors
                                ${on ? 'border-primary bg-primary-fixed/30' : 'border-outline-variant bg-surface-container-lowest hover:border-primary/40'}">
                    <input type="checkbox" ${on?'checked':''} onchange="toggleAgentDraftMcpTool('${escapeAttr(t.key)}')" class="accent-primary"/>
                    <span class="material-symbols-outlined text-[16px] ${on?'text-primary':'text-secondary'}">webhook</span>
                    <span class="text-body-md flex-1 truncate font-mono text-[12px]">${escapeHTML(t.name)}</span>
                  </label>`;
              }).join('')}
            </div>
          </div>
        `).join('')}
      </div>`;
  }

  const query = (state.agentToolsSkillQuery || '').trim().toLowerCase();
  const filteredSkills = query
    ? allSkills.filter(s => [s.id, s.name, s.desc, s.icon].filter(Boolean).join(' ').toLowerCase().includes(query))
    : allSkills;

  return `
    <div class="max-w-3xl">
      <div class="flex items-center justify-between mb-3">
        <p class="text-label-md text-secondary">勾选此 Agent 启用的 Skill（${draft.skills.length} / ${allSkills.length}）：</p>
        ${subTabs}
      </div>
      <div class="mb-3 flex items-center gap-2">
        <div class="relative flex-1">
          <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-secondary text-[18px]">search</span>
          <input value="${escapeAttr(state.agentToolsSkillQuery || '')}" oninput="setAgentToolsSkillQuery(this.value)"
            placeholder="搜索 Skill 名称、描述、slug..."
            class="w-full pl-10 pr-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
        </div>
        <button onclick="openAgentSkillCreateModal()"
          class="px-3 py-2 rounded-lg bg-primary text-white hover:opacity-90 text-label-md flex items-center gap-1 shrink-0">
          <span class="material-symbols-outlined text-[16px]">add</span>添加 Skill
        </button>
      </div>
      <div class="mb-3 flex items-center justify-between text-[11px] text-secondary">
        <span>当前显示 ${filteredSkills.length} 个 Skill</span>
        ${query ? `<button onclick="setAgentToolsSkillQuery('')" class="hover:text-primary">清空搜索</button>` : `<span>新建后会自动挂载到当前 Agent</span>`}
      </div>
      ${filteredSkills.length ? `
      <div class="grid grid-cols-2 gap-2">
        ${filteredSkills.map(s => {
          const on = draft.skills.includes(s.id);
          return `
            <label class="flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer transition-colors
                          ${on ? 'border-primary bg-primary-fixed/30' : 'border-outline-variant bg-surface-container-lowest hover:border-primary/40'}">
              <input type="checkbox" ${on?'checked':''} onchange="toggleAgentDraftSkill('${s.id}')" class="accent-primary"/>
              <span class="material-symbols-outlined text-[16px] ${on?'text-primary':'text-secondary'}">${s.icon||'extension'}</span>
              <span class="text-body-md flex-1 truncate">${escapeHTML(s.name)}</span>
            </label>`;
        }).join('')}
      </div>` : `
      <div class="text-center text-secondary p-lg border border-dashed border-outline-variant rounded-lg">
        <span class="material-symbols-outlined text-[36px] opacity-40 mb-2 block">search_off</span>
        <p>没有找到匹配的 Skill</p>
        <p class="text-[11px] mt-1">换个关键词试试，或直接创建一个新的 Skill。</p>
      </div>`}
    </div>`;
}

function setAgentToolsSkillQuery(query) {
  state.agentToolsSkillQuery = query;
  render();
}

function openAgentSkillCreateModal() {
  state.attachCreatedSkillToCurrentAgent = !!state.user;
  openSkillEditModal();
}

function toggleAgentDraftMcpTool(key) {
  if (!state.detail || state.detail.type !== 'agent') return;
  const arr = state.detail.draft.mcpTools;
  const i = arr.indexOf(key);
  if (i >= 0) arr.splice(i,1); else arr.push(key);
  markDetailDirty();
  render();
}

function renderAgentDetailMemoryTab(draft) {
  const c = draft.memoryConfig || {};
  const strategies = [
    { id:'none',    label:'不保留',  icon:'block',          desc:'每次调用都从空上下文开始' },
    { id:'window',  label:'滑动窗口', icon:'view_carousel',  desc:'保留最近 N 轮对话' },
    { id:'summary', label:'摘要压缩', icon:'compress',       desc:'超出窗口时 LLM 压缩为摘要' },
  ];
  const semanticOn = c.semanticRetrieval !== false;  // 默认开启
  const extractOn = c.extractFacts !== false;
  const decayOn = c.decayEnabled !== false;
  return `
    <div class="max-w-3xl space-y-md">
      <div>
        <label class="text-label-md text-secondary mb-2 block">工作记忆策略</label>
        <div class="grid grid-cols-3 gap-2">
          ${strategies.map(s => {
            const on = (c.strategy||'window') === s.id;
            const onclick = `state.detail.draft.memoryConfig.strategy='${s.id}'; markDetailDirty(); render()`;
            return `
              <button onclick="${onclick}"
                class="text-left p-3 rounded-lg border transition-colors
                       ${on ? 'border-primary bg-primary-fixed/30' : 'border-outline-variant bg-surface-container-lowest hover:border-primary/40'}">
                <div class="flex items-center gap-2 mb-1">
                  <span class="material-symbols-outlined text-[18px] ${on?'text-primary':'text-secondary'}">${s.icon}</span>
                  <span class="font-label-md ${on?'text-primary':'text-on-surface'}">${s.label}</span>
                </div>
                <p class="text-label-sm text-secondary">${s.desc}</p>
              </button>`;
          }).join('')}
        </div>
      </div>

      ${(c.strategy === 'window' || c.strategy === 'summary') ? `
        <div>
          <label class="text-label-md text-secondary mb-1 block">窗口轮数 (windowSize)</label>
          <input type="number" min="1" max="100" value="${c.windowSize||10}"
            oninput="state.detail.draft.memoryConfig.windowSize=parseInt(this.value)||10; markDetailDirty()"
            class="w-32 px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
          <p class="text-[11px] text-secondary mt-1">保留最近多少条 user/assistant 消息进入 LLM 上下文。</p>
        </div>` : ''}

      ${c.strategy === 'summary' ? `
        <div>
          <label class="text-label-md text-secondary mb-1 block">摘要 Prompt</label>
          <textarea rows="4" oninput="state.detail.draft.memoryConfig.summaryPrompt=this.value; markDetailDirty()"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md font-mono text-[12px] focus:outline-none focus:border-primary"
            placeholder="请将以上对话压缩成不超过 200 字...">${escapeHTML(c.summaryPrompt||'')}</textarea>
        </div>` : ''}

      <!-- 🧠 多层语义记忆（新功能） -->
      <div class="border-t border-outline-variant pt-md mt-md">
        <h3 class="text-label-lg text-on-surface mb-3 flex items-center gap-2">
          <span class="material-symbols-outlined text-[20px] text-primary">psychology</span>
          语义记忆（跨会话知识）
        </h3>

        <div class="space-y-3">
          <label class="flex items-center gap-3 p-3 rounded-lg border border-outline-variant bg-surface-container-lowest cursor-pointer hover:border-primary/40 transition-colors">
            <input type="checkbox" ${semanticOn?'checked':''}
              onchange="state.detail.draft.memoryConfig.semanticRetrieval=this.checked; markDetailDirty()"
              class="w-4 h-4 accent-primary"/>
            <div>
              <span class="text-label-md text-on-surface font-medium">语义检索增强</span>
              <p class="text-label-sm text-secondary">回答前自动搜索相关历史记忆并注入上下文</p>
            </div>
          </label>

          ${semanticOn ? `
            <div class="ml-9">
              <label class="text-label-sm text-secondary mb-1 block">每次检索条数 (retrievalTopK)</label>
              <input type="range" min="1" max="20" value="${c.retrievalTopK||5}"
                oninput="state.detail.draft.memoryConfig.retrievalTopK=parseInt(this.value); this.nextElementSibling.textContent=this.value; markDetailDirty()"
                class="w-full accent-primary"/>
              <span class="text-label-sm text-primary font-bold">${c.retrievalTopK||5}</span>
            </div>` : ''}

          <label class="flex items-center gap-3 p-3 rounded-lg border border-outline-variant bg-surface-container-lowest cursor-pointer hover:border-primary/40 transition-colors">
            <input type="checkbox" ${extractOn?'checked':''}
              onchange="state.detail.draft.memoryConfig.extractFacts=this.checked; markDetailDirty()"
              class="w-4 h-4 accent-primary"/>
            <div>
              <span class="text-label-md text-on-surface font-medium">自动提取事实</span>
              <p class="text-label-sm text-secondary">每次对话后 LLM 自动提取偏好、决策和关键事实</p>
            </div>
          </label>

          <label class="flex items-center gap-3 p-3 rounded-lg border border-outline-variant bg-surface-container-lowest cursor-pointer hover:border-primary/40 transition-colors">
            <input type="checkbox" ${decayOn?'checked':''}
              onchange="state.detail.draft.memoryConfig.decayEnabled=this.checked; markDetailDirty()"
              class="w-4 h-4 accent-primary"/>
            <div>
              <span class="text-label-md text-on-surface font-medium">记忆衰减</span>
              <p class="text-label-sm text-secondary">旧记忆随时间自动降低权重，长期不用的自动归档</p>
            </div>
          </label>
        </div>
      </div>
    </div>`;
}

function renderAgentDetailPlanningTab(draft) {
  const c = draft.planningConfig || {};
  const modes = [
    { id:'none',  label:'直接回答',  icon:'bolt',           desc:'不规划，单步生成结果' },
    { id:'react', label:'ReAct',     icon:'autorenew',      desc:'循环：思考 → 行动 → 观察' },
    { id:'plan',  label:'Plan-Execute', icon:'list_alt',    desc:'先生成完整计划再分步执行' },
    { id:'tree',  label:'Tree of Thought', icon:'account_tree', desc:'多路径分支搜索最优解', disabled:true },
  ];
  return `
    <div class="max-w-3xl space-y-md">
      <div>
        <label class="text-label-md text-secondary mb-2 block">规划模式</label>
        <div class="grid grid-cols-2 gap-2">
          ${modes.map(s => {
            const on = (c.mode||'react') === s.id;
            const lockedCls = s.disabled ? 'opacity-50 cursor-not-allowed' : '';
            const lockedTip = s.disabled ? '<span class="ml-1 text-[10px] text-secondary">(敬请期待)</span>' : '';
            const onclick = s.disabled
              ? `showToast('${s.label} 模式暂不支持，敬请期待后续迭代','info')`
              : `state.detail.draft.planningConfig.mode='${s.id}'; markDetailDirty(); render()`;
            return `
              <button onclick="${onclick}"
                class="text-left p-3 rounded-lg border transition-colors ${lockedCls}
                       ${on ? 'border-primary bg-primary-fixed/30' : 'border-outline-variant bg-surface-container-lowest hover:border-primary/40'}">
                <div class="flex items-center gap-2 mb-1">
                  <span class="material-symbols-outlined text-[18px] ${on?'text-primary':'text-secondary'}">${s.icon}</span>
                  <span class="font-label-md ${on?'text-primary':'text-on-surface'}">${s.label}${lockedTip}</span>
                </div>
                <p class="text-label-sm text-secondary">${s.desc}</p>
              </button>`;
          }).join('')}
        </div>
      </div>
      ${c.mode === 'plan' ? `
        <div>
          <label class="text-label-md text-secondary mb-1 block">计划模板</label>
          <textarea rows="6" oninput="state.detail.draft.planningConfig.stepsTemplate=this.value; markDetailDirty()"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md font-mono text-[12px] focus:outline-none focus:border-primary">${escapeHTML(c.stepsTemplate||'')}</textarea>
          <p class="text-[11px] text-secondary mt-1">Agent 生成计划时会以这个模板为骨架。</p>
        </div>` : ''}
    </div>`;
}

function renderAgentDetailValidationTab(draft) {
  const c = draft.validationConfig || {};
  const strategies = [
    { id:'none',     label:'不校验',  icon:'block',         desc:'输出即为最终结果' },
    { id:'rule',     label:'规则校验', icon:'rule',         desc:'根据下方规则列表逐项检查' },
    { id:'llm',      label:'LLM Judge', icon:'gavel',      desc:'调用 LLM 评估并判定是否需要重做' },
    { id:'human',    label:'人审',     icon:'group',         desc:'结果待人工确认后再返回', disabled:true },
  ];
  const rules = Array.isArray(c.rules) ? c.rules : [];
  return `
    <div class="max-w-3xl space-y-md">
      <div>
        <label class="text-label-md text-secondary mb-2 block">校验策略</label>
        <div class="grid grid-cols-2 gap-2">
          ${strategies.map(s => {
            const on = (c.strategy||'none') === s.id;
            const lockedCls = s.disabled ? 'opacity-50 cursor-not-allowed' : '';
            const lockedTip = s.disabled ? '<span class="ml-1 text-[10px] text-secondary">(敬请期待)</span>' : '';
            const onclick = s.disabled
              ? `showToast('${s.label} 策略暂不支持，敬请期待后续迭代','info')`
              : `state.detail.draft.validationConfig.strategy='${s.id}'; markDetailDirty(); render()`;
            return `
              <button onclick="${onclick}"
                class="text-left p-3 rounded-lg border transition-colors ${lockedCls}
                       ${on ? 'border-primary bg-primary-fixed/30' : 'border-outline-variant bg-surface-container-lowest hover:border-primary/40'}">
                <div class="flex items-center gap-2 mb-1">
                  <span class="material-symbols-outlined text-[18px] ${on?'text-primary':'text-secondary'}">${s.icon}</span>
                  <span class="font-label-md ${on?'text-primary':'text-on-surface'}">${s.label}${lockedTip}</span>
                </div>
                <p class="text-label-sm text-secondary">${s.desc}</p>
              </button>`;
          }).join('')}
        </div>
      </div>
      ${c.strategy === 'rule' ? `
        <div>
          <div class="flex items-center justify-between mb-2">
            <label class="text-label-md text-secondary">校验规则</label>
            <button onclick="addValidationRule()" class="text-primary text-label-md font-bold hover:underline flex items-center gap-1">
              <span class="material-symbols-outlined text-[14px]">add</span>新增规则
            </button>
          </div>
          ${rules.length ? `
            <div class="space-y-2">
              ${rules.map((r, i) => `
                <div class="flex items-center gap-2">
                  <input value="${escapeAttr(r)}" oninput="updateValidationRule(${i}, this.value)"
                    placeholder="例如：response.length < 500"
                    class="flex-1 px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md font-mono text-[12px] focus:outline-none focus:border-primary"/>
                  <button onclick="removeValidationRule(${i})" class="p-1 text-secondary hover:text-error">
                    <span class="material-symbols-outlined text-[18px]">delete</span>
                  </button>
                </div>`).join('')}
            </div>` : `
            <p class="text-secondary text-label-md italic px-3 py-2 border border-dashed border-outline-variant rounded-lg">还没有规则，点击右上角"新增规则"。</p>`}
        </div>` : ''}
      ${c.strategy === 'llm' ? `
        <div>
          <label class="text-label-md text-secondary mb-1 block">Judge Prompt</label>
          <textarea rows="6" oninput="state.detail.draft.validationConfig.judgePrompt=this.value; markDetailDirty()"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md font-mono text-[12px] focus:outline-none focus:border-primary">${escapeHTML(c.judgePrompt||'')}</textarea>
          <p class="text-[11px] text-secondary mt-1">Judge 返回 ok=false 时，主流程会让 Agent 重试。</p>
        </div>` : ''}
    </div>`;
}

function addValidationRule() {
  const arr = state.detail.draft.validationConfig.rules = state.detail.draft.validationConfig.rules || [];
  arr.push('');
  markDetailDirty(); render();
}
function updateValidationRule(i, v) {
  const arr = state.detail.draft.validationConfig.rules;
  if (!arr) return;
  arr[i] = v;
  markDetailDirty();
}
function removeValidationRule(i) {
  state.detail.draft.validationConfig.rules.splice(i, 1);
  markDetailDirty(); render();
}

function renderAgentDetailHooksTab(draft) {
  const h = draft.hooks || {};
  const fields = [
    { key:'preToolUse',  label:'PreToolUse',   desc:'每次调用工具前触发；可改写参数或拒绝调用。' },
    { key:'postToolUse', label:'PostToolUse',  desc:'工具返回后触发；可后处理或记录指标。' },
    { key:'onError',     label:'OnError',      desc:'工具/模型抛错时触发；可重试、降级或终止。' },
    { key:'onComplete',  label:'OnComplete',   desc:'任务整体完成后触发；可清理资源或推送通知。' },
  ];
  return `
    <div class="max-w-3xl space-y-md">
      <p class="text-label-sm text-secondary">Hook 是在 Agent 关键执行节点注入的 JS 片段。下面是占位编辑器，最终运行需后端 sandbox 支持。</p>
      ${fields.map(f => `
        <div>
          <label class="text-label-md text-secondary mb-1 block flex items-center gap-1.5">
            <span class="material-symbols-outlined text-[16px]">webhook</span>${f.label}
          </label>
          <p class="text-[11px] text-secondary mb-1">${f.desc}</p>
          <textarea rows="4" oninput="state.detail.draft.hooks.${f.key}=this.value; markDetailDirty()"
            placeholder="// ${f.label} 钩子\\n// 入参：ctx, args; 返回值会覆盖默认行为"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md font-mono text-[12px] focus:outline-none focus:border-primary">${escapeHTML(h[f.key]||'')}</textarea>
        </div>
      `).join('')}
    </div>`;
}

function renderAgentDetailTeamTab(a, draft) {
  // 仅 Team 进得来；但保留兜底
  if (draft.kind !== 'team') {
    return `
      <div class="max-w-2xl">
        <div class="p-md bg-surface-container-low border border-outline-variant rounded-lg">
          <p class="font-label-md text-on-surface mb-1 flex items-center gap-1.5">
            <span class="material-symbols-outlined text-[18px] text-secondary">info</span>
            仅 Team 可以编排 Agents
          </p>
          <p class="text-label-sm text-secondary">当前角色类型是 Agent。类型在创建时确定不可修改；如需新建 Team，请去 Mission 班底新增一个角色并让它作为主协同单元。</p>
        </div>
      </div>`;
  }

  const m = state.missions.find(x => x.id === state.detail.missionId);
  const allOthers = (m && m.squad.agents || []).filter(x => x.id !== a.id);

  // teamMemberIds 现为权威集合：保留与当前 Mission 内成员的交集，避免脏 id
  if (!Array.isArray(draft.teamMemberIds)) draft.teamMemberIds = [];
  draft.teamMemberIds = draft.teamMemberIds.filter(id => allOthers.some(x => x.id === id));
  const memberIds = draft.teamMemberIds.slice();
  const members = memberIds.map(id => allOthers.find(x => x.id === id)).filter(Boolean);

  const rowMember = (s) => `
    <div class="flex items-center gap-3 p-2.5 rounded-lg border border-outline-variant bg-surface-container-lowest">
      <div class="w-8 h-8 rounded bg-tertiary-container flex items-center justify-center shrink-0">
        <span class="material-symbols-outlined text-on-tertiary-container text-[16px]">${escapeHTML(s.icon || 'smart_toy')}</span>
      </div>
      <div class="flex-1 min-w-0">
        <p class="font-label-md text-on-surface truncate">${escapeHTML(s.name)}</p>
        <p class="text-label-sm text-secondary truncate">${escapeHTML(s.role || '')}</p>
      </div>
      <button onclick="removeTeamMember('${s.id}')"
        class="p-1 rounded text-secondary hover:text-error hover:bg-error-container" title="从此 Team 调度链移除">
        <span class="material-symbols-outlined text-[16px]">close</span>
      </button>
    </div>`;

  const emptyBlock = (text) => `
    <div class="text-center text-secondary p-md border border-dashed border-outline-variant rounded-lg">
      <p class="text-label-sm">${escapeHTML(text)}</p>
    </div>`;

  return `
    <div class="max-w-3xl space-y-md">
      <div class="p-md bg-primary-container/30 border border-primary/30 rounded-lg">
        <p class="font-label-md text-on-surface mb-1 flex items-center gap-1.5">
          <span class="material-symbols-outlined text-[18px] text-primary">hub</span>
          Team 下的 Agents
        </p>
        <p class="text-label-sm text-secondary leading-relaxed">
          下方列表中的 Agent 都可被该 Team 调度。被「移除」的 Agent 仍存在于 Mission，但 Team 默认不调用它们；点击右上角“添加 Agent”可以从你的库 / 市场或自然语言描述创建新成员。
        </p>
      </div>

      <div>
        <div class="flex items-center justify-between mb-2">
          <p class="text-label-md text-on-surface font-bold">Agents（${members.length}）</p>
          <button onclick="openModalAddAgent('${state.detail.missionId}')"
            class="text-label-md text-primary font-bold flex items-center gap-1 hover:underline">
            <span class="material-symbols-outlined text-[16px]">add</span>添加 Agent
          </button>
        </div>
        ${members.length ? `<div class="space-y-2">${members.map(rowMember).join('')}</div>` : emptyBlock('此 Team 当前没有可调度的 Agent；点击右上角“添加 Agent”开始补充执行单元。')}
      </div>
    </div>`;
}

/* ---- Team Members 操作 ---- */
function setTeamSearch(v) {
  if (!state.detail) return;
  state.detail.teamSearch = v;
  // 仅重渲染当前页面，不脏化
  render();
  // 重新聚焦输入框 + 把光标放到末尾
  const el = document.querySelector('input[oninput^="setTeamSearch"]');
  if (el) { el.focus(); try { el.setSelectionRange(v.length, v.length); } catch(e){} }
}

function removeTeamMember(memberId) {
  const draft = state.detail && state.detail.draft;
  if (!draft) return;
  if (!Array.isArray(draft.teamMemberIds)) draft.teamMemberIds = [];
  const i = draft.teamMemberIds.indexOf(memberId);
  if (i >= 0) draft.teamMemberIds.splice(i, 1);
  markDetailDirty(); render();
}

// 直接添加 Mission 内已存在的某个 Agent id 到调度链；触发 Team Prompt 同步 Diff Modal。
function addTeamMember(memberId, opts={}) {
  const draft = state.detail && state.detail.draft;
  if (!draft) return;
  const m = state.missions.find(x => x.id === state.detail.missionId);
  if (!m) return;
  if (!Array.isArray(draft.teamMemberIds)) draft.teamMemberIds = [];
  if (draft.teamMemberIds.includes(memberId)) return;
  const newMember = m.squad.agents.find(x => x.id === memberId);
  if (!newMember) return;
  draft.teamMemberIds.push(memberId);
  markDetailDirty(); render();
  if (opts.silent) return;
  // 自动同步：弹出 Team System Prompt 补丁
  const intent = buildManagerSyncPromptDiff(draft, newMember, m);
  if (intent) {
    setTimeout(() => openModalAgentDiff(intent), 100);
  }
}

// 兼容旧调用：依赖现有 teamMemberIds 是否包含 memberId 决定 add / remove
function toggleTeamMember(memberId) {
  const draft = state.detail && state.detail.draft;
  if (!draft) return;
  if (!Array.isArray(draft.teamMemberIds)) draft.teamMemberIds = [];
  if (draft.teamMemberIds.includes(memberId)) removeTeamMember(memberId);
  else addTeamMember(memberId);
}

// 从「我的库」（其它 Mission）添加 Agent：浅拷贝一份进当前 Mission 的 squad，再加入 Team 调度链。
function addTeamMemberFromLibrary(fromMissionId, srcAgentId) {
  const draft = state.detail && state.detail.draft;
  if (!draft) return;
  const dstMission = state.missions.find(x => x.id === state.detail.missionId);
  const srcMission = state.missions.find(x => x.id === fromMissionId);
  if (!dstMission || !srcMission) return;
  const src = srcMission.squad.agents.find(a => a.id === srcAgentId);
  if (!src) return;
  const newAgent = cloneAgentForMission(src, dstMission);
  dstMission.squad.agents.push(newAgent);
  ensureAgentSchema(newAgent);
  // 加入调度链 + 弹出 Prompt 同步 Diff
  if (!Array.isArray(draft.teamMemberIds)) draft.teamMemberIds = [];
  draft.teamMemberIds.push(newAgent.id);
  markDetailDirty(); render();
  const intent = buildManagerSyncPromptDiff(draft, newAgent, dstMission);
  if (intent) setTimeout(() => openModalAgentDiff(intent), 100);
  showToast(`已从你的 Agent 库添加 "${newAgent.name}"`);
}

// 从市场添加 Agent：把 mock 市场 Agent 物化成 Mission squad 内的真实 Agent
function addTeamMemberFromMarket(marketAgentId) {
  const draft = state.detail && state.detail.draft;
  if (!draft) return;
  const dstMission = state.missions.find(x => x.id === state.detail.missionId);
  if (!dstMission) return;
  const src = (state.agentMarket || []).find(x => x.id === marketAgentId);
  if (!src) return;
  const newAgent = cloneAgentForMission(src, dstMission);
  dstMission.squad.agents.push(newAgent);
  ensureAgentSchema(newAgent);
  if (!Array.isArray(draft.teamMemberIds)) draft.teamMemberIds = [];
  draft.teamMemberIds.push(newAgent.id);
  markDetailDirty(); render();
  const intent = buildManagerSyncPromptDiff(draft, newAgent, dstMission);
  if (intent) setTimeout(() => openModalAgentDiff(intent), 100);
  showToast(`已从社区市场安装 "${newAgent.name}"`);
}

/* ---- Library / Market 推荐 & 工具 ---- */
function cloneAgentForMission(src, dstMission) {
  // 解决潜在重名冲突：在当前 Mission 中已有同名 Agent 时加后缀
  const existsName = (n) => dstMission.squad.agents.some(a => a.name === n);
  let name = src.name;
  if (existsName(name)) {
    let suffix = 2;
    while (existsName(`${src.name} (${suffix})`)) suffix++;
    name = `${src.name} (${suffix})`;
  }
  return {
    id: 'a_' + Math.random().toString(36).slice(2, 10),
    name,
    role: src.role || '',
    icon: src.icon || getAgentKindMeta(src.kind || 'agent').icon,
    model: src.model || 'GPT-4o mini',
    kind: 'agent',  // 插入 Mission 时会由 _insertAgentToMission 决定最终类型
    systemPrompt: src.systemPrompt || (src.kind === 'team'
      ? `你是 ${src.name} 的 Team 负责人。${src.role || ''}`
      : `你是一名 ${src.name}。${src.role || ''}`),
    skills: [...(src.skills || [])],
    mcpTools: [...(src.mcpTools || [])],
    teamMemberIds: [],
    memoryConfig: src.memoryConfig ? JSON.parse(JSON.stringify(src.memoryConfig)) : {
      strategy:'window', windowSize:10,
      summaryPrompt:'请将以上对话内容浓缩为一段不超过 200 字的要点摘要，保留关键事实、决策与下一步。',
      kvNamespace:'',
    },
    planningConfig:   src.planningConfig   ? JSON.parse(JSON.stringify(src.planningConfig))   : {},
    validationConfig: src.validationConfig ? JSON.parse(JSON.stringify(src.validationConfig)) : {},
    hooks:            src.hooks            ? JSON.parse(JSON.stringify(src.hooks))            : {},
    readme: src.readme || '',
    versions: [],
    ownerId: null,
    updatedAt: Date.now(),
  };
}

// 用户的"Agent 库"：跨 Mission 收集所有 Agent（去重 + 排除当前 Mission 已有 + 排除 excludeIds）
function getMyLibraryAgents(currentMissionId, excludeIds, query, manager) {
  const out = [];
  const seenName = new Set();
  state.missions.forEach(mm => {
    if (mm.id === currentMissionId) return;
    mm.squad.agents.forEach(a => {
      if (excludeIds.has(a.id)) return;
      if (seenName.has(a.name)) return;
      // 跨 Mission 同名 Agent 也不重复推荐（按名字去重）
      // 当前 Mission 内同名也排除
      const dstMission = state.missions.find(x => x.id === currentMissionId);
      if (dstMission && dstMission.squad.agents.some(x => x.name === a.name)) return;
      seenName.add(a.name);
      out.push({
        id: a.id, name: a.name, role: a.role, icon: a.icon, skills: a.skills || [], kind: a.kind,
        fromMissionId: mm.id, fromMissionName: mm.name,
        _score: scoreAgentMatch(manager, a, query),
      });
    });
  });
  // 加上后端自建 Agent（customAgents）
  (state.customAgents || []).forEach(a => {
    const agentKey = a.agent_id || `backend_${a.id}`;
    if (excludeIds.has(agentKey)) return;
    if (seenName.has(a.name)) return;
    seenName.add(a.name);
    out.push({
      id: agentKey,
      name: a.name,
      role: a.description || a.system_prompt || '',
      icon: a.icon || 'smart_toy',
      skills: a.tools || [],
      kind: 'agent',
      model: a.llm_adapter || 'GPT-4o mini',
      fromCustomAgent: true,
      _score: scoreAgentMatch(manager, { name: a.name, role: a.description || '', skills: a.tools || [] }, query),
    });
  });
  // 搜索过滤
  const filtered = query ? out.filter(x => agentMatchesQuery(x, query)) : out;
  return filtered.sort((x, y) => y._score - x._score);
}

// 从后端自定义 Agent 库添加（被添加 Agent 弹窗调用）
function addAgentFromCustomAgent(customAgentId, dstMissionId) {
  const dst = state.missions.find(x => x.id === dstMissionId);
  const src = (state.customAgents || []).find(a => String(a.agent_id || a.id) === String(customAgentId));
  if (!dst || !src) return;
  const newAgent = cloneAgentForMission({
    name: src.name,
    role: src.description || src.system_prompt || '',
    icon: src.icon || 'smart_toy',
    skills: src.tools || [],
    model: src.llm_adapter || 'GPT-4o mini',
    kind: 'agent'
  }, dst);
  const { intent } = _insertAgentToMission(newAgent, dst);
  closeModalAddAgent();
  showToast(`已添加 "${newAgent.name}" 到 Team`, 'success');
  if (intent) setTimeout(() => { state.missionId = dst.id; openModalAgentDiff(intent); }, 100);
  else render();
}

function getRecommendedAgents(manager, excludeIds, query) {
  const market = state.agentMarket || [];
  const filtered = market
    .filter(x => !excludeIds.has(x.id))
    .map(x => ({ ...x, _score: scoreAgentMatch(manager, x, query) }))
    .filter(x => !query || agentMatchesQuery(x, query));
  return filtered.sort((x, y) => y._score - x._score);
}

function agentMatchesQuery(x, q) {
  q = q.toLowerCase();
  if ((x.name || '').toLowerCase().includes(q)) return true;
  if ((x.role || '').toLowerCase().includes(q)) return true;
  if (Array.isArray(x.skills) && x.skills.some(s => (s || '').toLowerCase().includes(q))) return true;
  return false;
}

// 极简评分：manager.role + skills 与候选的 role/skills 关键词重合度
function scoreAgentMatch(manager, candidate, query) {
  let s = candidate.installCount ? Math.min(candidate.installCount / 1000, 5) : 0;
  if (!manager) return s;
  const mgrTokens = ((manager.role || '') + ' ' + (manager.skills || []).join(' ')).toLowerCase().split(/[\s,，。.\-_/]+/).filter(Boolean);
  const candTokens = ((candidate.role || '') + ' ' + (candidate.skills || []).join(' ')).toLowerCase();
  mgrTokens.forEach(t => { if (t.length > 1 && candTokens.includes(t)) s += 1; });
  if (query) {
    const ql = query.toLowerCase();
    if ((candidate.name || '').toLowerCase().includes(ql)) s += 5;
  }
  return s;
}

// 生成 Manager System Prompt 同步补丁
function buildManagerSyncPromptDiff(managerDraft, newMember, mission) {
  if (!managerDraft || !newMember) return null;
  const oldPrompt = managerDraft.systemPrompt || '';
  // 先剥离旧的"## 团队成员补充"段（避免反复追加）
  const STRIPPED = oldPrompt.replace(/\n*## 团队成员补充[\s\S]*$/m, '').replace(/\s+$/, '');

  const others = (mission && mission.squad.agents || []).filter(a => a.id !== managerDraft.id && (managerDraft.teamMemberIds || []).includes(a.id));
  const lines = others.map(o => {
    const skills = (o.skills || []).slice(0, 3).join(' / ') || '通用能力';
    return `- **${o.name}**（${o.role || '团队成员'}）：可在涉及 ${skills} 时调用。`;
  });
  const block = `## 团队成员补充\n团队中已包含以下成员，遇到对应能力相关任务时可委托：\n${lines.join('\n')}`;
  const newPrompt = (STRIPPED ? STRIPPED + '\n\n' : '') + block;

  // 构造 promptDiff：keep STRIPPED + add block 行
  const oldLines = oldPrompt.split('\n');
  const newLines = newPrompt.split('\n');
  // 简化：把整段旧的标记 keep，新增的标记 add
  const keepCount = STRIPPED.split('\n').length;
  const promptDiff = [
    ...newLines.slice(0, keepCount).map((t, idx) => ({ type:'keep', text: oldLines[idx] !== undefined ? oldLines[idx] : t })),
    ...newLines.slice(keepCount).map(t => ({ type:'add', text: t })),
  ];
  // 若旧 prompt 比新 prompt 多（之前有"团队成员补充"段被剥离），把多出来的旧行打成 remove
  if (oldLines.length > keepCount) {
    oldLines.slice(keepCount).forEach(t => promptDiff.push({ type:'remove', text: t }));
  }

  return {
    agentId: managerDraft._agentRefId || (state.detail && state.detail.agentId),
    summary: `同步 Manager 提示词：新增成员 ${newMember.name}`,
    addedSkills: [],
    removedSkills: [],
    promptDiff,
    // 给 openModalAgentDiff 一个完整的目标 prompt，便于直接覆盖
    _newPrompt: newPrompt,
    _isManagerSync: true,
  };
}

function toggleAgentDraftSkill(skillId) {
  if (!state.detail || state.detail.type !== 'agent') return;
  const arr = state.detail.draft.skills;
  const i = arr.indexOf(skillId);
  if (i >= 0) arr.splice(i,1); else arr.push(skillId);
  markDetailDirty();
  render();
}

function resetAgentPromptToOriginal() {
  const a = getCurrentAgent();
  if (!a) return;
  state.detail.draft.systemPrompt = a.systemPrompt || '';
  state.detail.dirty = true;
  render();
}

async function commitAgentSave() {
  const a = getCurrentAgent();
  if (!a || !state.detail || !state.detail.dirty) return;
  ensureAgentSchema(a);
  const draft = state.detail.draft;

  // ===== Backend 自定义 Agent：通过 API 持久化 =====
  if (state.detail.source === 'backend') {
    if (!(draft.name || '').trim()) {
      showToast('名称不能为空', 'error');
      return;
    }
    try {
      const agentId = state.detail.agentId;
      await api(`/agents/${agentId}`, {
        method: 'PUT',
        body: JSON.stringify(detailDraftToBackendPayload(draft))
      });
      state.detail.dirty = false;
      showToast('已保存', 'success');
      await fetchCustomAgents();
      render();
    } catch (e) {
      showToast(`保存失败: ${e.message || e}`, 'error');
    }
    return;
  }

  // ===== Mine / Market：原有内存版本机制不变 =====
  // 全字段快照写入版本（保存前的旧值）
  a.versions = a.versions || [];
  a.versions.push({
    ts: new Date().toISOString().replace('T',' ').slice(0,19),
    by: state.user ? state.user.username : 'guest',
    snapshot: {
      name:a.name, role:a.role, icon:a.icon, model:a.model, kind:a.kind||'agent',
      systemPrompt:a.systemPrompt,
      skills:[...(a.skills||[])],
      mcpTools:[...(a.mcpTools||[])],
      teamMemberIds:[...(a.teamMemberIds||[])],
      memoryConfig: JSON.parse(JSON.stringify(a.memoryConfig||{})),
      planningConfig: JSON.parse(JSON.stringify(a.planningConfig||{})),
      validationConfig: JSON.parse(JSON.stringify(a.validationConfig||{})),
      hooks: JSON.parse(JSON.stringify(a.hooks||{})),
      readme:a.readme||'',
    },
    note: 'before_edit',
  });
  if (a.versions.length > 50) a.versions = a.versions.slice(-50);
  // 应用 draft（kind 不从 draft 写回：Kind 创建后不可修改）
  a.name = draft.name; a.role = draft.role; a.icon = draft.icon; a.model = draft.model;
  // a.kind 保持不变
  a.systemPrompt = draft.systemPrompt;
  a.skills = [...draft.skills];
  a.mcpTools = [...draft.mcpTools];
  a.teamMemberIds = [...(draft.teamMemberIds||[])];
  a.memoryConfig = JSON.parse(JSON.stringify(draft.memoryConfig));
  a.planningConfig = JSON.parse(JSON.stringify(draft.planningConfig));
  a.validationConfig = JSON.parse(JSON.stringify(draft.validationConfig));
  a.hooks = JSON.parse(JSON.stringify(draft.hooks));
  a.readme = draft.readme;
  a.updatedAt = Date.now();
  // ensureMissionManager 仅作为防御性兑现（创建控制了唯一性，这里不会变更 kind）
  const m2 = state.missions.find(x => x.id === state.detail.missionId);
  if (m2 && typeof ensureMissionManager === 'function') ensureMissionManager(m2);
  state.detail.dirty = false;
  showToast('已保存（共 ' + a.versions.length + ' 个版本）', 'success');
  render();
}

function showAgentVersionDiff(idx) {
  const a = getCurrentAgent();
  if (!a || !a.versions[idx]) return;
  const snap = a.versions[idx].snapshot;
  const cur = { name:a.name, role:a.role, icon:a.icon, model:a.model, systemPrompt:a.systemPrompt, skills:[...a.skills], readme:a.readme||'' };
  showVersionDiffModal(snap, cur, idx, () => rollbackAgentVersion(idx));
}

function rollbackAgentVersion(idx) {
  const a = getCurrentAgent();
  if (!a || !a.versions[idx]) return;
  ensureAgentSchema(a);
  const snap = a.versions[idx].snapshot;
  // 把当前状态先存档
  a.versions.push({
    ts: new Date().toISOString().replace('T',' ').slice(0,19),
    by: state.user ? state.user.username : 'guest',
    snapshot: {
      name:a.name, role:a.role, icon:a.icon, model:a.model, kind:a.kind||'agent',
      systemPrompt:a.systemPrompt,
      skills:[...(a.skills||[])],
      mcpTools:[...(a.mcpTools||[])],
      teamMemberIds:[...(a.teamMemberIds||[])],
      memoryConfig: JSON.parse(JSON.stringify(a.memoryConfig||{})),
      planningConfig: JSON.parse(JSON.stringify(a.planningConfig||{})),
      validationConfig: JSON.parse(JSON.stringify(a.validationConfig||{})),
      hooks: JSON.parse(JSON.stringify(a.hooks||{})),
      readme:a.readme||'',
    },
    note: `rollback_from:v${idx+1}`,
  });
  Object.assign(a, {
    name: snap.name, role: snap.role, icon: snap.icon, model: snap.model,
    kind: snap.kind || 'agent',
    systemPrompt: snap.systemPrompt,
    skills: [...(snap.skills||[])],
    mcpTools: [...(snap.mcpTools||[])],
    teamMemberIds: [...((snap.teamMemberIds||snap.subAgentIds)||[])],
    memoryConfig: snap.memoryConfig ? JSON.parse(JSON.stringify(snap.memoryConfig)) : a.memoryConfig,
    planningConfig: snap.planningConfig ? JSON.parse(JSON.stringify(snap.planningConfig)) : a.planningConfig,
    validationConfig: snap.validationConfig ? JSON.parse(JSON.stringify(snap.validationConfig)) : a.validationConfig,
    hooks: snap.hooks ? JSON.parse(JSON.stringify(snap.hooks)) : a.hooks,
    readme: snap.readme || '',
    updatedAt: Date.now(),
  });
  // 同步 draft
  state.detail.draft = cloneAgentForDraft(a);
  state.detail.dirty = false;
  closeVersionDiffModal();
  showToast(`已回滚到 v${idx+1}`, 'success');
  render();
}