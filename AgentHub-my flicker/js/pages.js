/* ===================== Agents / Workflows / Settings 页面 ===================== */
function setAgentLibraryTab(tab) {
  state.agentLibraryTab = tab;
  render();
}

function setAgentKindFilter(filter) {
  state.agentKindFilter = filter;
  render();
}

function setAgentLibraryQuery(query) {
  state.agentLibraryQuery = query;
  render();
}

function renderAgentsPage() {
  const missionAgents = [];
  state.missions.forEach(m => {
    m.squad.agents.forEach(a => missionAgents.push({ ...a, missionName: m.name, missionId: m.id, source: 'mine' }));
  });
  const backendAgents = (state.customAgents || []).map(a => ({
    ...a,
    role: a.system_prompt || '',
    icon: 'smart_toy',
    kind: 'agent',
    skills: a.tools || [],
    model: a.llm_adapter || 'tongyi',
    missionName: '自定义Agent',
    missionId: '',
    source: 'backend',
  }));
  const mine = [...missionAgents, ...backendAgents];
  const market = (state.agentMarket || []).map(a => ({ ...a, source: 'market' }));
  const tab = state.agentLibraryTab || 'mine';
  const kindFilter = state.agentKindFilter || 'all';
  const query = (state.agentLibraryQuery || '').trim().toLowerCase();
  const currentList = tab === 'mine' ? mine : market;
  const kindFiltered = kindFilter === 'all' ? currentList : currentList.filter(a => a.kind === kindFilter);
  const filtered = query
    ? kindFiltered.filter(a => {
        const haystack = [
          a.name,
          a.role,
          a.missionName,
          a.authorName,
          a.model,
          a.kind,
          ...(a.skills || []),
        ].filter(Boolean).join(' ').toLowerCase();
        return haystack.includes(query);
      })
    : kindFiltered;

  const countByName = {};
  mine.forEach(a => { countByName[a.name] = (countByName[a.name] || 0) + 1; });

  const tabBtn = (id, label, icon, count) => `
    <button onclick="setAgentLibraryTab('${id}')"
      class="px-4 py-1.5 rounded-lg text-label-md flex items-center gap-2 transition-colors
             ${tab===id ? 'bg-primary text-white' : 'bg-surface-container border border-outline-variant text-on-surface-variant hover:bg-surface-container-low'}">
      <span class="material-symbols-outlined text-[16px]">${icon}</span>${label}
      <span class="text-[11px] opacity-80">${count}</span>
    </button>`;

  const filterBtn = (id, label) => `
    <button onclick="setAgentKindFilter('${id}')"
      class="px-3 py-1.5 rounded-md text-label-md transition-colors
             ${kindFilter===id ? 'bg-surface text-primary font-bold shadow-sm' : 'text-secondary hover:text-on-surface'}">${label}</button>`;

  const cards = filtered.length ? filtered.map(a => {
    const isBackend = a.source === 'backend';
    const cnt = countByName[a.name] || 1;
    const meta = getAgentKindMeta(a.kind);
    const clickable = true;
    const action = isBackend
      ? `openAgentDetail('', '${escapeAttr(a.agent_id)}', 'backend')`
      : tab === "mine"
        ? `openAgentDetail('${a.missionId}','${a.id}','mine')`
        : `openAgentDetail('', '${a.id}', 'market')`;
    return `
      <div onclick="${clickable ? action : ''}"
           class="bg-surface-container-lowest border border-outline-variant rounded-xl p-md ${clickable ? 'cursor-pointer hover:border-primary/40' : ''} transition-colors group">
        <div class="flex items-center gap-3 mb-2">
          <div class="w-10 h-10 rounded-lg ${a.kind === 'team' ? 'bg-primary-fixed text-on-primary-fixed-variant' : 'bg-secondary-container text-on-surface-variant'} flex items-center justify-center">
            <span class="material-symbols-outlined text-[18px]">${a.icon || meta.icon}</span>
          </div>
          <div class="min-w-0 flex-1">
            <p class="font-label-md text-on-surface truncate flex items-center gap-1.5">
              ${escapeHTML(a.name)}
              ${isBackend ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-tertiary-fixed text-on-tertiary-fixed-variant">API</span>' : '<span class="text-[10px] px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant">内置</span>'}
              <span class="text-[10px] px-1.5 py-0.5 rounded ${a.kind === 'team' ? 'bg-primary text-white' : 'bg-secondary-container text-on-surface-variant'}">${meta.label}</span>
              ${tab === 'mine' && cnt>1 ? `<span class="text-[10px] bg-amber-100 text-amber-700 px-1 rounded" title="此名字出现在 ${cnt} 个 Mission 中">×${cnt}</span>` : ''}
            </p>
            <p class="text-label-sm text-secondary truncate">${isBackend ? `模型: ${escapeHTML(a.model)}` : escapeHTML(a.missionName)}</p>
          </div>
          ${isBackend ? `<div class="flex items-center gap-0.5"><button onclick="event.stopPropagation();openAgentDetail('', '${escapeAttr(a.agent_id)}', 'backend')" class="text-secondary hover:bg-surface-container/30 p-1 rounded transition-colors" title="编辑"><span class="material-symbols-outlined text-[16px]">edit</span></button><button onclick="event.stopPropagation();deleteCustomAgentAPI('${escapeAttr(a.agent_id)}','${escapeAttr(a.name)}')" class="text-error hover:bg-error-container/30 p-1 rounded transition-colors" title="删除"><span class="material-symbols-outlined text-[16px]">delete</span></button></div>` : ''}
        </div>
        <p class="text-body-md text-secondary italic line-clamp-2">${escapeHTML(a.role || meta.description)}</p>
        <div class="flex flex-wrap gap-1 mt-2">
          ${(a.skills || []).slice(0,4).map(s => `<span class="text-[10px] px-1.5 py-0.5 bg-surface-container rounded text-secondary">${escapeHTML(s)}</span>`).join('')}
          ${(a.skills || []).length>4 ? `<span class="text-[10px] text-secondary">+${(a.skills || []).length-4}</span>` : ''}
        </div>
        <div class="flex items-center justify-between text-[11px] text-secondary mt-2 pt-2 border-t border-outline-variant/60">
          <span>${isBackend ? `ID: ${escapeHTML(a.agent_id || '')}` : (tab === 'mine' ? `${(a.versions||[]).length} 个历史版本` : `${(a.installCount||0).toLocaleString()} 安装`)}</span>
          ${isBackend ? '<span class="text-[10px] text-tertiary">后端注册</span>' : `<span class="opacity-0 group-hover:opacity-100 text-primary flex items-center gap-1">
            查看详情
            <span class="material-symbols-outlined text-[14px]">arrow_forward</span>
          </span>`}
        </div>
      </div>`;
  }).join('') : `
    <div class="col-span-3 text-center text-secondary p-xl border border-dashed border-outline-variant rounded-xl">
      <span class="material-symbols-outlined text-[40px] opacity-40 mb-2 block">smart_toy</span>
      <p>${tab === 'mine' ? '当前筛选下还没有任何 Team / Agent。' : '市场当前筛选下暂无 Team / Agent。'}</p>
    </div>`;

  return `
    <div class="flex-1 overflow-y-auto bg-background">
      <section class="px-xl pt-xl pb-md">
        <h2 class="text-headline-lg text-on-surface">Agents 库</h2>
        <p class="text-body-md text-secondary mt-1">区分查看我的库与市场库，同时按 Team / Agent 两类浏览。支持关键词搜索；我的库可直接进入详情并在详情页用自然语言修改。</p>

        <div class="mt-md flex items-center justify-between gap-3 flex-wrap">
          <div class="flex items-center gap-2">
            ${tabBtn('mine','我的库','folder_special', mine.length)}
            ${tabBtn('market','市场库','storefront', market.length)}
            ${tab === 'mine' ? `<button onclick="openCreateAgentModal()" class="px-4 py-1.5 rounded-lg text-label-md flex items-center gap-2 bg-primary text-white hover:opacity-90 transition-opacity"><span class="material-symbols-outlined text-[16px]">add</span>创建自定义Agent</button>` : ''}
          </div>
          <div class="inline-flex items-center gap-1 p-1 bg-surface-container rounded-lg border border-outline-variant">
            ${filterBtn('all','全部')}
            ${filterBtn('team','Team')}
            ${filterBtn('agent','Agent')}
          </div>
        </div>
        <div class="mt-md max-w-4xl">
          <div class="relative">
            <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-secondary text-[18px]">search</span>
            <input
              value="${escapeAttr(state.agentLibraryQuery || '')}"
              oninput="setAgentLibraryQuery(this.value)"
              placeholder="搜索 Agent 名称、职责、技能、模型、Mission..."
              class="w-full pl-10 pr-24 py-2.5 bg-surface-container-lowest border border-outline-variant rounded-xl text-body-md focus:outline-none focus:border-primary"
            />
            ${query ? `
              <button onclick="setAgentLibraryQuery('')" class="absolute right-3 top-1/2 -translate-y-1/2 text-label-md text-secondary hover:text-primary">
                清空
              </button>` : ''}
          </div>
          <p class="text-[11px] text-secondary mt-2 leading-relaxed">
            可按名称、职责、技能、模型、Mission 名称等关键词搜索。需要修改时，请进入 Agent 详情页后使用右侧自然语言修改面板。
          </p>
        </div>
      </section>
      <section class="px-xl pb-xl grid grid-cols-3 gap-md">${cards}</section>
    </div>`;
}

/* ---- 创建自定义Agent 弹窗 ---- */
function openCreateAgentModal() {
  const root = $('#modal-create-mission');
  root.classList.remove('hidden');
  root.innerHTML = `
    <div class="absolute inset-0 modal-overlay" onclick="closeModal('modal-create-mission')"></div>
    <div class="relative h-full w-full flex items-center justify-center p-lg" onclick="event.stopPropagation()">
      <div class="bg-surface-container-lowest rounded-xl shadow-2xl w-[520px] max-w-full max-h-[88vh] overflow-hidden flex flex-col">
        <div class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-primary">smart_toy</span>
            <h3 class="text-headline-md text-on-surface">创建自定义 Agent</h3>
          </div>
          <button onclick="closeModal('modal-create-mission')" class="p-1 rounded hover:bg-surface-container">
            <span class="material-symbols-outlined text-secondary">close</span>
          </button>
        </div>
        <div class="flex-1 overflow-y-auto p-lg space-y-md">
          <div>
            <label class="text-label-md text-secondary mb-1 block">Agent 名称 <span class="text-error">*</span></label>
            <input id="new-agent-name" placeholder="例如：代码审查助手"
              class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
          </div>
          <div>
            <label class="text-label-md text-secondary mb-1 block">图标</label>
            <div class="grid grid-cols-12 gap-2" id="new-agent-icon-grid">
              ${SKILL_ICON_OPTIONS.map(i => `
                <button type="button" onclick="document.querySelectorAll('#new-agent-icon-grid button').forEach(b=>b.classList.remove('border-primary','bg-primary-fixed/40')); this.classList.add('border-primary','bg-primary-fixed/40'); state.newAgentIcon='${i}'"
                  class="w-9 h-9 rounded-lg border border-outline-variant bg-surface-container-lowest flex items-center justify-center hover:border-primary/40 transition-colors${i==='smart_toy'?' border-primary bg-primary-fixed/40':''}">
                  <span class="material-symbols-outlined text-[18px] text-on-surface-variant">${i}</span>
                </button>
              `).join('')}
            </div>
          </div>
          <div>
            <label class="text-label-md text-secondary mb-1 block">System Prompt <span class="text-error">*</span>
              <button onclick="improveAgentPrompt('new-agent-prompt')" title="AI 自动优化提示词" class="ml-2 px-2 py-0.5 rounded border border-primary/40 text-primary text-[11px] hover:bg-primary-fixed/30 transition-colors font-medium">✨ AI 优化</button>
            </label>
            <textarea id="new-agent-prompt" rows="4" placeholder="描述这个 Agent 的职责和行为..."
              class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"></textarea>
          </div>
          <div>
            <label class="text-label-md text-secondary mb-1 block">LLM 适配器</label>
            <select id="new-agent-llm" class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary">
              <option value="tongyi">通义千问 (tongyi)</option>
              <option value="openai">OpenAI</option>
              <option value="claude">Claude</option>
              <option value="gemini">Gemini</option>
            </select>
          </div>
          <div>
            <label class="text-label-md text-secondary mb-1 block">工具列表 (逗号分隔)</label>
            <input id="new-agent-tools" placeholder="例如：web_search, code_exec, pdf_parse"
              class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
          </div>
        </div>
        <div class="px-lg py-md border-t border-outline-variant flex items-center justify-end gap-2">
          <button onclick="closeModal('modal-create-mission')" class="px-3 py-1.5 text-secondary text-label-md hover:underline">取消</button>
          <button onclick="submitCreateAgent()" class="px-3 py-1.5 bg-primary text-white rounded-lg text-label-md hover:opacity-90">创建</button>
        </div>
      </div>
    </div>`;
}

async function submitCreateAgent() {
  let name = ($('#new-agent-name')?.value || '').trim();
  const icon = state.newAgentIcon || 'smart_toy';
  const systemPrompt = ($('#new-agent-prompt')?.value || '').trim();
  const llmAdapter = $('#new-agent-llm')?.value || 'tongyi';
  const toolsStr = ($('#new-agent-tools')?.value || '').trim();
  const tools = toolsStr ? toolsStr.split(',').map(s => s.trim()).filter(Boolean) : [];

  if (!name) { showToast('请输入 Agent 名称', 'error'); return; }
  if (!systemPrompt) { showToast('请输入 System Prompt', 'error'); return; }

  // 自动解决重名：若已存在同名Agent，追加数字后缀
  const allAgents = [...(state.customAgents || []), ...(state.missions || []).flatMap(m => m.squad?.agents || [])];
  let baseName = name;
  let counter = 2;
  while (allAgents.some(a => a.name === name)) {
    name = `${baseName} (${counter})`;
    counter++;
  }
  if (name !== baseName) showToast(`检测到重名，已自动更名为"${name}"`, 'info');

  try {
    await createCustomAgentAPI(name, icon, systemPrompt, llmAdapter, tools);
    closeModal('modal-create-mission');
  } catch (e) {
    showToast('创建失败: ' + (e.message || e), 'error');
  }
}

async function improveAgentPrompt(textareaId) {
  const ta = document.getElementById(textareaId);
  if (!ta) return;
  const original = ta.value.trim();
  if (!original || original.length < 10) {
    showToast('请先输入一段提示词，再点击 AI 优化', 'error');
    return;
  }
  const btn = ta.parentElement.querySelector('button[onclick*="improveAgentPrompt"]');
  const origLabel = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '优化中…'; btn.disabled = true; }

  try {
    const resp = await fetch(API_BASE + '/agents/improve-prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + localStorage.getItem('agenthub_token') },
      body: JSON.stringify({ prompt: original }),
    });
    const data = await resp.json();
    if (data.improved_prompt && data.improved_prompt !== original) {
      ta.value = data.improved_prompt;
      // 详情页需要手动同步 draft 状态并标记 dirty（textarea 是直接设值，不触发 oninput）
      if (textareaId === 'detail-agent-prompt' && state.detail) {
        state.detail.draft.systemPrompt = data.improved_prompt;
        markDetailDirty();
      }
      showToast('提示词已优化，长度: ' + original.length + ' → ' + data.improved_prompt.length, 'success');
    } else {
      showToast(data.note || '未能优化，已保留原提示词', 'info');
    }
  } catch (e) {
    showToast('优化失败: ' + e.message, 'error');
  } finally {
    if (btn) { btn.textContent = origLabel; btn.disabled = false; }
  }
}

async function improveSkillPrompt() {
  const ta = document.getElementById('skill-code-input');
  if (!ta) return;
  const original = ta.value.trim();
  if (!original || original.length < 10) {
    showToast('请先输入一段提示词，再点击 AI 优化', 'error');
    return;
  }
  const modal = document.getElementById('modal-skill-edit');
  const btn = modal ? modal.querySelector('button[onclick="improveSkillPrompt()"]') : null;
  const origLabel = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '优化中…'; btn.disabled = true; }

  try {
    const resp = await fetch(API_BASE + '/agents/improve-prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + localStorage.getItem('agenthub_token') },
      body: JSON.stringify({ prompt: original }),
    });
    const data = await resp.json();
    if (data.improved_prompt && data.improved_prompt !== original) {
      ta.value = data.improved_prompt;
      state.skillEdit.code = data.improved_prompt;
      showToast('提示词已优化，长度: ' + original.length + ' → ' + data.improved_prompt.length, 'success');
    } else {
      showToast(data.note || '未能优化，已保留原提示词', 'info');
    }
  } catch (e) {
    showToast('优化失败: ' + e.message, 'error');
  } finally {
    if (btn) { btn.textContent = origLabel; btn.disabled = false; }
  }
}

/* ---- Agents 库自然语言修改入口 ---- */
function submitAgentsLibEdit() {
  const ta = document.getElementById('agents-lib-edit-input');
  if (!ta) return;
  const text = (ta.value || '').trim();
  if (!text) { showToast('请先输入修改指令', 'error'); return; }
  const result = parseEditIntentGlobal(text);
  if (!result) { showToast('未能解析出明确的 Agent 修改意图。可尝试使用 #AgentName 显式指定。', 'error'); return; }
  ta.value = '';
  // 切换 detail 上下文，让 openModalAgentDiff/applyAgentDiff 能定位到正确 Mission
  const prevDetail = state.detail;
  const prevMissionId = state.missionId;
  state.missionId = result.missionId;
  // 给 Diff Modal 一个最小的 detail 锚点：仅设 missionId，不进入 agent_detail 视图
  state.detail = { type: 'agent', missionId: result.missionId, agentId: result.intent.agentId, tab: 'overview', draft: null, dirty: false };
  openModalAgentDiff(result.intent);
  // applyAgentDiff/closeModal 后会再次 render，但 state.view 不变；为了用户取消时也能恢复，我们在弹层关闭后用一次性事件复位
  const root = document.getElementById('modal-agent-diff');
  const restore = () => {
    state.missionId = prevMissionId;
    state.detail = prevDetail;
  };
  // 关闭按钮路径
  const observer = new MutationObserver(() => {
    if (root && root.classList.contains('hidden')) {
      restore();
      observer.disconnect();
    }
  });
  if (root) observer.observe(root, { attributes: true, attributeFilter: ['class'] });
}

// 跨所有 Mission 解析自然语言编辑意图。
// 返回 { intent, missionId } 或 null。
function parseEditIntentGlobal(text) {
  if (!text) return null;
  const prev = state.missionId;
  // 先按 #AgentName 显式优先：跨所有 Mission 找名字最匹配的 Agent，定位它所在 Mission
  const hashM = text.match(/#([^\s#@]+)/);
  if (hashM) {
    const frag = hashM[1].toLowerCase();
    const norm = (s) => s.toLowerCase().replace(/[\s师员]+/g,'');
    let target = null;
    for (const m of state.missions) {
      const hit = m.squad.agents.find(a =>
        a.name.toLowerCase().includes(frag) || norm(a.name).includes(norm(frag))
      );
      if (hit) { target = { mission: m, agent: hit }; break; }
    }
    if (target) {
      state.missionId = target.mission.id;
      try {
        const intent = parseEditIntent(text);
        if (intent) return { intent, missionId: target.mission.id };
      } finally {
        state.missionId = prev;
      }
    }
  }
  // 回退：在每个 Mission 上轮询 parseEditIntent，命中即返回
  for (const m of state.missions) {
    state.missionId = m.id;
    try {
      const intent = parseEditIntent(text);
      if (intent) return { intent, missionId: m.id };
    } finally {
      state.missionId = prev;
    }
  }
  return null;
}

function renderWorkflowsPage() { return renderSkillsPage(); }   // 兼容兜底

/* ===================== Skills 页面（双 Tab + 卡片矩阵） ===================== */

const SKILL_ICON_OPTIONS = ['extension','language','public','travel_explore','picture_as_pdf','terminal','insert_chart','description','menu_book','cloud_upload','screenshot','mail','difference','finance_mode','feed','monitoring','image','database','translate','fact_check','rss_feed','smart_toy','search','settings_voice','auto_awesome'];
const SKILL_CATEGORIES = [
  { id:'search', name:'信息检索', color:'bg-blue-100 text-blue-700' },
  { id:'data',   name:'数据处理', color:'bg-purple-100 text-purple-700' },
  { id:'output', name:'内容产出', color:'bg-amber-100 text-amber-700' },
  { id:'custom', name:'自定义',   color:'bg-gray-100 text-gray-700' },
];
const SKILL_CATEGORY_MAP = Object.fromEntries(SKILL_CATEGORIES.map(c => [c.id, c]));

// 合并所有技能（去重），提供给 Skills 页面使用
function normalizedCustomSkills() {
  const builtin = (BUILTIN_SKILLS || []).map(s => buildLocalSkillRecord(s, {
    ...s,
    slug: s.slug || s.id,
    isBuiltin: true,
    isInstalled: true,
    isPublished: true,
    authorName: 'system',
  }));
  const custom = (state.customSkills || []).map(s => buildLocalSkillRecord(s, {
    ...s,
    slug: s.slug || s.id,
    isBuiltin: false,
    isInstalled: true,
    isMine: true,
  }));
  // 去重：以 slug 为键
  const map = new Map();
  [...builtin, ...custom].forEach(s => map.set(s.slug, s));
  return [...map.values()];
}

function getAllSkillRecords() {
  return [...normalizedCustomSkills(), ...(state.skills.mine || []), ...(state.skills.market || [])];
}

function findSkillRecord(skillRef) {
  if (skillRef == null || skillRef === "") return null;
  return getAllSkillRecords().find(s => s.id === skillRef || s.slug === skillRef || ("builtin_" + s.slug) === skillRef) || null;
}

function makeUniqueSkillSlug(base) {
  const taken = new Set(getAllSkillRecords().map(s => s.slug || s.id));
  const seed = String(base || "skill").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/_+/g, "_") || "skill";
  let slug = seed;
  let i = 2;
  while (taken.has(slug)) slug = seed + "_" + i++;
  return slug;
}

function buildLocalSkillRecord(base, overrides={}) {
  const original = base || {};
  const slug = overrides.slug || makeUniqueSkillSlug(overrides.slugSeed || overrides.name || original.slug || original.id || "skill");
  const ts = new Date().toISOString().replace("T", " ").slice(0,19);
  return {
    id: slug,
    slug,
    name: overrides.name || original.name || slug,
    icon: overrides.icon || original.icon || "extension",
    description: overrides.description || original.description || original.desc || "",
    desc: overrides.description || original.description || original.desc || "",
    code: overrides.code ?? original.code ?? "",
    readme: overrides.readme ?? original.readme ?? "",
    category: overrides.category || original.category || "custom",
    authorName: state.user ? state.user.username : "Guest",
    isPublished: false,
    isMine: true,
    isInstalled: true,
    isBuiltin: false,
    isLocalCustom: true,
    parentId: original.id || null,
    installCount: 0,
    updatedAt: ts,
    versions: (original.versions || []).slice(),
  };
}

function upsertLocalSkillRecord(skill) {
  const idx = (state.customSkills || []).findIndex(x => (x.id || x.slug) === (skill.id || skill.slug));
  const normalized = { ...skill, id: skill.id || skill.slug, slug: skill.slug || skill.id, desc: skill.description || skill.desc || "" };
  if (idx >= 0) state.customSkills[idx] = normalized;
  else state.customSkills.push(normalized);
  saveCustomSkills();
  return normalized;
}

function updateAgentSkillReference(agent, oldSkillId, newSkillId) {
  if (!agent || !Array.isArray(agent.skills)) return;
  agent.skills = agent.skills.map(s => s === oldSkillId ? newSkillId : s);
}

function replaceSkillAcrossAllAgents(oldSkillId, newSkillId) {
  state.missions.forEach(m => m.squad.agents.forEach(a => updateAgentSkillReference(a, oldSkillId, newSkillId)));
  (state.agentMarket || []).forEach(a => updateAgentSkillReference(a, oldSkillId, newSkillId));
}

// 给 Mission 右栏使用的统一 skill 列表（同步源）
function getAllSkills() {
  const fromMine = (state.skills.mine || []).map(s => ({ id: s.slug, name: s.name, icon: s.icon, desc: s.description }));
  const fromCustom = normalizedCustomSkills().map(s => ({ id: s.slug, name: s.name, icon: s.icon, desc: s.description }));
  // 去重：以 slug/id 为键
  const map = new Map();
  [...fromMine, ...fromCustom].forEach(s => map.set(s.id, s));
  return [...map.values()];
}

async function loadSkills() {
  try {
    const market = await api('/skills/market');
    state.skills.market = market.skills || [];
    if (state.user) {
      const mine = await api('/skills/mine');
      state.skills.mine = mine.skills || [];
    } else {
      state.skills.mine = [];
    }
    state.skills.loaded = true;
    render();
  } catch (e) {
    console.warn('loadSkills failed', e);
    showToast && showToast('Skill 列表加载失败：' + (e.message || e));
  }
}

function renderSkillsPage() {
  const kind = state.toolsKind || 'skill';
  if (kind === 'mcp') return renderToolsPage_McpKind();

  const tab = state.skillsTab || 'mine';

  // 我的 Skill = 内置（系统提供） + 服务器 mine + 市场中系统内置的 skill
  const mineFromServer = state.skills.mine || [];
  const localCustoms = normalizedCustomSkills();
  const marketList = (state.skills.market || []).filter(s => s.authorName !== 'system');
  // 将市场中系统内置（authorName === system）的技能也加入"我的 Skill"，标记为只读
  const builtinInMarket = (state.skills.market || [])
    .filter(s => s.authorName === 'system')
    .map(s => ({ ...s, isBuiltin: true, isInstalled: true }));
  const myList = [...localCustoms, ...mineFromServer, ...builtinInMarket];

  const counts = `
    <div class="flex items-center gap-2">
      <button onclick="switchSkillsTab('mine')"
        class="px-4 py-1.5 rounded-lg text-label-md flex items-center gap-2 transition-colors
               ${tab==='mine' ? 'bg-primary text-white' : 'bg-surface-container border border-outline-variant text-on-surface-variant hover:bg-surface-container-low'}">
        <span class="material-symbols-outlined text-[16px]">inventory_2</span>
        我的 Skill <span class="text-[11px] opacity-80">${myList.length}</span>
      </button>
      <button onclick="switchSkillsTab('market')"
        class="px-4 py-1.5 rounded-lg text-label-md flex items-center gap-2 transition-colors
               ${tab==='market' ? 'bg-primary text-white' : 'bg-surface-container border border-outline-variant text-on-surface-variant hover:bg-surface-container-low'}">
        <span class="material-symbols-outlined text-[16px]">storefront</span>
        Skill 市场 <span class="text-[11px] opacity-80">${marketList.length}</span>
      </button>
    </div>`;

  const list = tab === 'mine' ? myList : marketList;
  const cards = list.length
    ? list.map(s => renderSkillCard(s, tab)).join('')
    : `<div class="col-span-3 text-center text-secondary p-xl border border-dashed border-outline-variant rounded-xl">
         <span class="material-symbols-outlined text-[40px] opacity-40 mb-2 block">${tab==='mine'?'inventory_2':'storefront'}</span>
         <p class="text-body-md">${tab==='mine'?'还没有自定义 Skill，点击右上角创建一个吧。':'市场暂无 Skill，去创建一个发布到市场吧。'}</p>
       </div>`;

  return `
    <div class="flex-1 overflow-y-auto bg-background">
      <section class="px-xl pt-xl pb-md flex items-start justify-between gap-4">
        <div>
          <h2 class="text-headline-lg text-on-surface">Tools</h2>
          <p class="text-body-md text-secondary mt-1">统一管理 Agent 能力。Tools 包含 Skill（代码逻辑）与 MCP Server（远程协议）。</p>
        </div>
        <button onclick="openSkillEditModal()" class="bg-primary text-white px-4 py-2 rounded-lg flex items-center gap-2 hover:opacity-90 text-label-md shrink-0">
          <span class="material-symbols-outlined text-[18px]">add</span>创建 Skill
        </button>
      </section>
      <section class="px-xl pb-md">
        ${renderToolsKindTabs(kind)}
      </section>
      <section class="px-xl pb-md">
        ${counts}
      </section>
      <section class="px-xl pb-xl grid grid-cols-3 gap-md">
        ${cards}
      </section>
    </div>`;
}

function renderToolsKindTabs(active) {
  const mcpCount = (state.mcpServers || []).length;
  return `
    <div class="inline-flex items-center gap-1 p-1 bg-surface-container rounded-lg border border-outline-variant">
      <button onclick="switchToolsKind('skill')"
        class="px-3 py-1.5 rounded-md text-label-md flex items-center gap-1.5 transition-colors
               ${active==='skill' ? 'bg-surface text-primary font-bold shadow-sm' : 'text-secondary hover:text-on-surface'}">
        <span class="material-symbols-outlined text-[16px]">extension</span>Skill
      </button>
      <button onclick="switchToolsKind('mcp')"
        class="px-3 py-1.5 rounded-md text-label-md flex items-center gap-1.5 transition-colors
               ${active==='mcp' ? 'bg-surface text-primary font-bold shadow-sm' : 'text-secondary hover:text-on-surface'}">
        <span class="material-symbols-outlined text-[16px]">cable</span>MCP Server
        <span class="text-[11px] px-1.5 py-0.5 rounded-full ${active==='mcp'?'bg-primary text-white':'bg-surface-container-low text-secondary'}">${mcpCount}</span>
      </button>
    </div>`;
}
function switchToolsKind(k) { state.toolsKind = k; render(); }

function renderSkillCard(s, tab) {
  const cat = SKILL_CATEGORY_MAP[s.category] || SKILL_CATEGORY_MAP.custom;
  const isBuiltin = s.isBuiltin;
  const isMine = s.isMine;
  const isPublished = s.isPublished;
  const isInstalled = s.isInstalled;

  // 状态徽标
  let badge;
  if (isBuiltin)        badge = `<span class="text-[10px] px-1.5 py-0.5 rounded bg-secondary-container text-on-surface-variant font-medium">内置</span>`;
  else if (isMine && isPublished) badge = `<span class="text-[10px] px-1.5 py-0.5 rounded bg-green-100 text-green-700 font-medium">已发布</span>`;
  else if (isMine)      badge = `<span class="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-medium">私有</span>`;
  else if (isInstalled) badge = `<span class="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-medium">已安装</span>`;
  else                  badge = `<span class="text-[10px] px-1.5 py-0.5 rounded bg-surface-container text-secondary font-medium">未安装</span>`;

  // 按钮组（每个按钮都加 onclick="event.stopPropagation()" 阻止冒泡到卡片）
  const stop = "event.stopPropagation();";
  let buttons;
  if (isBuiltin) {
    buttons = `<button onclick="${stop}" class="flex-1 px-2 py-1.5 rounded text-label-sm bg-surface-container text-secondary cursor-default" disabled>已内置</button>`;
  } else if (tab === 'mine' && isMine) {
    const pubBtn = isPublished
      ? `<button onclick="${stop} unpublishSkill(${s.id})" class="px-2 py-1.5 rounded text-label-sm border border-outline-variant text-on-surface-variant hover:bg-surface-container-low" title="撤回发布">撤回</button>`
      : `<button onclick="${stop} publishSkill(${s.id})" class="px-2 py-1.5 rounded text-label-sm bg-primary text-white hover:opacity-90" title="发布到市场">发布</button>`;
    buttons = `
      <button onclick="${stop} openSkillDetail(${s.id})" class="flex-1 px-2 py-1.5 rounded text-label-sm border border-outline-variant text-on-surface hover:bg-surface-container-low flex items-center justify-center gap-1">
        <span class="material-symbols-outlined text-[14px]">edit</span>编辑
      </button>
      ${pubBtn}
      <button onclick="${stop} deleteSkill(${s.id})" class="px-2 py-1.5 rounded text-label-sm border border-outline-variant text-error hover:bg-error/10" title="删除"><span class="material-symbols-outlined text-[14px]">delete</span></button>`;
  } else if (tab === 'mine') {
    buttons = `<button onclick="${stop}" class="flex-1 px-2 py-1.5 rounded text-label-sm bg-surface-container text-secondary" disabled>已安装</button>`;
  } else {
    buttons = isInstalled
      ? `<button onclick="${stop}" class="flex-1 px-2 py-1.5 rounded text-label-sm bg-secondary-container text-on-surface-variant cursor-default" disabled>已安装</button>`
      : `<button onclick="${stop} installSkill(${s.id})" class="flex-1 px-2 py-1.5 rounded text-label-sm bg-primary text-white hover:opacity-90 flex items-center justify-center gap-1">
           <span class="material-symbols-outlined text-[14px]">download</span>安装
         </button>`;
    if (isMine) {
      buttons = `<button onclick="${stop} openSkillDetail(${s.id})" class="flex-1 px-2 py-1.5 rounded text-label-sm border border-outline-variant text-on-surface hover:bg-surface-container-low">编辑</button>`;
    }
  }

  // 整卡片可点击（内置无详情页，弹提示）
  const cardClick = isBuiltin
    ? `onclick="showToast('内置 Skill 暂无详情页（不可编辑）','info')"`
    : `onclick="openSkillDetail(${s.id})"`;

  return `
    <div ${cardClick} class="bg-surface-container-lowest border border-outline-variant rounded-xl p-md hover:border-primary/40 transition-colors flex flex-col gap-2 cursor-pointer group">
      <div class="flex items-start gap-3">
        <div class="w-10 h-10 rounded-lg bg-primary-fixed/40 flex items-center justify-center shrink-0">
          <span class="material-symbols-outlined text-primary text-[20px]">${escapeHTML(s.icon||'extension')}</span>
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5">
            <p class="font-label-md text-on-surface truncate">${escapeHTML(s.name)}</p>
            ${badge}
          </div>
          <p class="text-label-sm text-secondary truncate">@${escapeHTML(s.authorName||'system')} · ${cat.name}</p>
        </div>
      </div>
      <p class="text-body-md text-secondary line-clamp-2 min-h-[40px]">${escapeHTML(s.description||'—')}</p>
      <div class="flex items-center justify-between text-[10px] text-secondary">
        <span class="${cat.color} px-1.5 py-0.5 rounded">${cat.name}</span>
        <span class="flex items-center gap-2">
          ${tab==='market' ? `<span class="flex items-center gap-1"><span class="material-symbols-outlined text-[12px]">download</span>${s.installCount||0}</span>` : ''}
          ${(s.versions && s.versions.length) ? `<span class="flex items-center gap-1"><span class="material-symbols-outlined text-[12px]">history</span>${s.versions.length}</span>` : ''}
        </span>
      </div>
      <div class="flex items-center gap-2 pt-1 border-t border-outline-variant/60" onclick="event.stopPropagation()">
        ${buttons}
      </div>
    </div>`;
}

function switchSkillsTab(t) { state.skillsTab = t; render(); }

/* ===================== Tools 页面 · MCP Server 主分类 ===================== */
function renderToolsPage_McpKind() {
  loadMcpServers();
  const servers = state.mcpServers || [];
  const card = (s) => {
    const tools = s.tools || [];
    const statusColor = s.status === 'connected' ? 'bg-emerald-500' : (s.status === 'error' ? 'bg-error' : 'bg-secondary');
    return `
      <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-md hover:border-primary/40 transition-colors group">
        <div class="flex items-start gap-3 mb-2">
          <div class="w-10 h-10 rounded-lg bg-primary-container flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined text-on-primary-container text-[18px]">cable</span>
          </div>
          <div class="min-w-0 flex-1">
            <p class="font-label-md text-on-surface truncate flex items-center gap-2">
              ${escapeHTML(s.name || '未命名 MCP Server')}
              <span class="inline-flex items-center gap-1 text-[10px] text-secondary">
                <span class="inline-block w-1.5 h-1.5 rounded-full ${statusColor}"></span>
                ${s.status || 'idle'}
              </span>
            </p>
            <p class="text-label-sm text-secondary truncate font-mono">${escapeHTML(s.transport || 'stdio')} · ${escapeHTML(s.endpoint || s.command || '—')}</p>
          </div>
          <div class="opacity-0 group-hover:opacity-100 flex items-center gap-1">
            <button onclick="testMcpServer('${s.id}')" title="探测工具列表" class="text-secondary hover:text-primary">
              <span class="material-symbols-outlined text-[16px]">refresh</span>
            </button>
            <button onclick="editMcpServer('${s.id}')" title="编辑" class="text-secondary hover:text-primary">
              <span class="material-symbols-outlined text-[16px]">edit</span>
            </button>
            <button onclick="deleteMcpServer('${s.id}')" title="删除" class="text-secondary hover:text-error">
              <span class="material-symbols-outlined text-[16px]">delete</span>
            </button>
          </div>
        </div>
        <p class="text-body-md text-secondary line-clamp-2 mb-2">${escapeHTML(s.description || '—')}</p>
        <div class="flex flex-wrap gap-1">
          ${tools.length
            ? tools.slice(0, 6).map(t => `<span class="text-[10px] px-1.5 py-0.5 bg-surface-container rounded text-secondary">${escapeHTML(t.name || t)}</span>`).join('')
            : '<span class="text-[10px] text-secondary italic">未探测到工具，点击 ↻ 测试连接</span>'}
          ${tools.length > 6 ? `<span class="text-[10px] text-secondary">+${tools.length - 6}</span>` : ''}
        </div>
      </div>`;
  };

  const grid = servers.length
    ? servers.map(card).join('')
    : `<div class="col-span-3 text-center text-secondary p-xl border border-dashed border-outline-variant rounded-xl">
         <span class="material-symbols-outlined text-[40px] opacity-40 mb-2 block">cable</span>
         <p class="text-body-md">还没有接入任何 MCP Server</p>
         <p class="text-label-sm mt-1">MCP（Model Context Protocol）让 Agent 调用远程工具。点击右上角"接入 MCP Server"开始。</p>
       </div>`;

  return `
    <div class="flex-1 overflow-y-auto bg-background">
      <section class="px-xl pt-xl pb-md flex items-start justify-between gap-4">
        <div>
          <h2 class="text-headline-lg text-on-surface">Tools</h2>
          <p class="text-body-md text-secondary mt-1">统一管理 Agent 能力。Tools 包含 Skill（代码逻辑）与 MCP Server（远程协议）。</p>
        </div>
        <button onclick="openMcpServerModal()" class="bg-primary text-white px-4 py-2 rounded-lg flex items-center gap-2 hover:opacity-90 text-label-md shrink-0">
          <span class="material-symbols-outlined text-[18px]">add</span>接入 MCP Server
        </button>
      </section>
      <section class="px-xl pb-md">${renderToolsKindTabs('mcp')}</section>
      <section class="px-xl pb-xl grid grid-cols-3 gap-md">${grid}</section>
    </div>`;
}

/* ===================== Skill 编辑/创建 Modal ===================== */

function openSkillEditModal(skillId) {
  if (!state.user) {
    showToast('请先登录后创建 Skill');
    openAuthModal && openAuthModal('register');
    return;
  }
  let editing;
  if (skillId != null) {
    editing = (state.skills.mine || []).find(s => s.id === skillId)
           || (state.skills.market || []).find(s => s.id === skillId);
    if (!editing) { showToast('Skill 不存在或无权编辑'); return; }
  }
  state.skillEdit = editing
    ? { id:editing.id, slug:editing.slug, name:editing.name, icon:editing.icon, description:editing.description, code:editing.code||'', category:editing.category, isPublished:editing.isPublished }
    : { slug:'', name:'', icon:'extension', description:'', code:'', category:'custom', isPublished:false };

  const root = document.getElementById('modal-skill-edit') || (function(){
    const el = document.createElement('div');
    el.id = 'modal-skill-edit';
    el.className = 'hidden';
    document.body.appendChild(el);
    return el;
  })();
  root.classList.remove('hidden');
  renderSkillEditModal(root);
}

function renderSkillEditModal(root) {
  const e = state.skillEdit;
  const isEdit = e.id != null;
  const iconOptions = SKILL_ICON_OPTIONS.map(i => `
    <button type="button" onclick="state.skillEdit.icon='${i}'; renderSkillEditModal(document.getElementById('modal-skill-edit'))"
      class="w-9 h-9 rounded-lg border flex items-center justify-center transition-colors
             ${e.icon===i ? 'border-primary bg-primary-fixed/40' : 'border-outline-variant bg-surface-container-lowest hover:border-primary/40'}">
      <span class="material-symbols-outlined text-[18px] ${e.icon===i?'text-primary':'text-on-surface-variant'}">${i}</span>
    </button>`).join('');

  root.innerHTML = `
    <div class="fixed inset-0 bg-black/40 z-40 flex items-center justify-center p-4" onclick="if(event.target===this) closeSkillEditModal()">
      <div class="bg-surface rounded-xl shadow-2xl w-[640px] max-h-[88vh] flex flex-col overflow-hidden">
        <header class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <h3 class="text-title-lg font-headline-md text-on-surface">${isEdit ? '编辑 Skill' : '创建 Skill'}</h3>
          <button onclick="closeSkillEditModal()" class="text-secondary hover:text-on-surface"><span class="material-symbols-outlined">close</span></button>
        </header>
        <main class="px-lg py-md overflow-y-auto space-y-md">
          <div>
            <label class="block text-label-md text-secondary mb-1">名称 (slug，英文小写下划线)</label>
            <input id="skill-slug" value="${escapeHTML(e.slug)}" ${isEdit?'disabled':''}
              oninput="state.skillEdit.slug=this.value; state.skillEdit.name=this.value"
              placeholder="例如 news_summary"
              class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary disabled:opacity-60"/>
            <p class="text-[10px] text-secondary mt-1">必须以小写字母开头，仅含 a-z 0-9 _，2-30 字符。同时作为展示名称。</p>
          </div>
          <div>
            <label class="block text-label-md text-secondary mb-1">图标</label>
            <div class="grid grid-cols-12 gap-2">${iconOptions}</div>
          </div>
          <div>
            <label class="block text-label-md text-secondary mb-1">分类</label>
            <div class="flex gap-2">
              ${SKILL_CATEGORIES.map(c => `
                <button type="button" onclick="state.skillEdit.category='${c.id}'; renderSkillEditModal(document.getElementById('modal-skill-edit'))"
                  class="px-3 py-1.5 rounded-lg text-label-md border transition-colors
                         ${e.category===c.id ? 'border-primary bg-primary-fixed/40 text-primary' : 'border-outline-variant text-on-surface-variant hover:bg-surface-container-low'}">
                  ${c.name}
                </button>`).join('')}
            </div>
          </div>
          <div>
            <label class="block text-label-md text-secondary mb-1">描述（一行）</label>
            <input value="${escapeHTML(e.description)}" oninput="state.skillEdit.description=this.value"
              placeholder="例如：抓取多篇新闻并提炼要点"
              class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
          </div>
          <div>
            <label class="block text-label-md text-secondary mb-1">实现说明 / Prompt 模板（可选，最长 4000 字）
              <button onclick="improveSkillPrompt()" title="AI 自动优化提示词" class="ml-2 px-2 py-0.5 rounded border border-primary/40 text-primary text-[11px] hover:bg-primary-fixed/30 transition-colors font-medium">✨ AI 优化</button>
            </label>
            <textarea id="skill-code-input" oninput="state.skillEdit.code=this.value" rows="6"
              placeholder="可粘贴 Prompt 模板、实现伪代码或调用步骤..."
              class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md font-mono text-[12px] focus:outline-none focus:border-primary">${escapeHTML(e.code||'')}</textarea>
          </div>
        </main>
        <footer class="px-lg py-md border-t border-outline-variant flex items-center justify-end gap-2">
          <button onclick="closeSkillEditModal()" class="px-4 py-1.5 rounded-lg border border-outline-variant text-on-surface-variant hover:bg-surface-container-low text-label-md">取消</button>
          <button onclick="commitSkillSave(false)" class="px-4 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container-low text-label-md">${isEdit?'保存':'保存为私有'}</button>
          <button onclick="commitSkillSave(true)" class="px-4 py-1.5 rounded-lg bg-primary text-white hover:opacity-90 text-label-md flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">publish</span>${isEdit && e.isPublished ? '保存（保持已发布）' : '保存并发布'}
          </button>
        </footer>
      </div>
    </div>`;
}

function closeSkillEditModal() {
  state.skillEdit = null;
  state.attachCreatedSkillToCurrentAgent = false;
  const root = document.getElementById('modal-skill-edit');
  if (root) { root.classList.add('hidden'); root.innerHTML = ''; }
}

async function commitSkillSave(publishAfter) {
  const e = state.skillEdit; if (!e) return;
  if (!/^[a-z][a-z0-9_]{1,30}$/.test(e.slug)) return showToast('slug 格式错误：以小写字母开头 + a-z0-9_，2-30 字符');
  if (!e.description || e.description.length < 2) return showToast('请填写描述');
  const isCreate = e.id == null;
  const createdSlug = e.slug;
  const attachToCurrentAgent = !!state.attachCreatedSkillToCurrentAgent && isCreate && !!state.detail && state.detail.type === 'agent';
  try {
    if (e.id != null) {
      // 更新
      await api('/skills/' + e.id, { method:'PUT', body: JSON.stringify({
        name: e.name || e.slug, icon: e.icon, description: e.description, code: e.code || '', category: e.category
      })});
      if (publishAfter && !e.isPublished) {
        await api('/skills/' + e.id + '/publish', { method:'POST' });
      }
      showToast('已保存');
    } else {
      // 新建
      await api('/skills', { method:'POST', body: JSON.stringify({
        slug: e.slug, name: e.name || e.slug, icon: e.icon, description: e.description,
        code: e.code || '', category: e.category, publish: !!publishAfter
      })});
      showToast(publishAfter ? '已创建并发布到市场' : '已创建为私有 Skill');
    }
    await loadSkills();
    if (attachToCurrentAgent && state.detail && state.detail.type === 'agent') {
      const created = getAllSkills().find(s => s.id === createdSlug);
      if (created && !state.detail.draft.skills.includes(created.id)) {
        state.detail.draft.skills.push(created.id);
        markDetailDirty();
        showToast(`已创建并添加 Skill「${created.name}」`, 'success');
      }
    }
    closeSkillEditModal();
  } catch (err) {
    state.attachCreatedSkillToCurrentAgent = false;
    showToast('保存失败：' + (err.message || err));
  }
}

async function publishSkill(id) {
  try { await api('/skills/' + id + '/publish', { method:'POST' }); showToast('已发布到市场'); await loadSkills(); }
  catch (e) { showToast('发布失败：' + (e.message || e)); }
}
async function unpublishSkill(id) {
  try { await api('/skills/' + id + '/unpublish', { method:'POST' }); showToast('已撤回'); await loadSkills(); }
  catch (e) { showToast('撤回失败：' + (e.message || e)); }
}
async function installSkill(id) {
  if (!state.user) { showToast('请先登录后再安装'); openAuthModal && openAuthModal('register'); return; }
  try { await api('/skills/' + id + '/install', { method:'POST' }); showToast('已安装到「我的 Skill」'); await loadSkills(); }
  catch (e) { showToast('安装失败：' + (e.message || e)); }
}
async function deleteSkill(id) {
  if (!confirm('确定删除这个 Skill 吗？发布到市场的版本也会一并下线。')) return;
  try { await api('/skills/' + id, { method:'DELETE' }); showToast('已删除'); await loadSkills(); }
  catch (e) { showToast('删除失败：' + (e.message || e)); }
}