/* ===== global state ===== */
const state = {
  view: 'dashboard',
  missionId: null,
  runId: 'run_current',
  rightTab: 'agents',
  selectedAgentId: null,
  outputPanelCollapsed: false,
  outputPanelTab: 'all',
  missionSearch: '',
  missions: [],  // 从后端加载
  showArchivedMissions: false,  // 是否显示已归档的任务
  customAgents: [],  // 从后端 API 加载的自定义 Agent
  customSkills: [],
  // Skills 系统（market + mine）
  skills: { market: [], mine: [], loaded: false },
  skillsTab: 'mine',          // 'mine' | 'market'
  agentLibraryTab: 'mine',    // 'mine' | 'market'
  agentKindFilter: 'all',     // 'all' | 'team' | 'agent'
  agentLibraryQuery: '',
  // 已启用的 Skills（用于注入到聊天上下文的 Skill）
  activeSkills: [],
  // Skill 管理面板是否显示
  skillPanelOpen: false,
  // 注：agentCreateModal 不需要额外状态，create modal 直接复用 modal-create-mission
  agentCreateModal: false,  // 自定义Agent创建弹窗
  agentToolsSkillQuery: '',
  skillEdit: null,            // { id?, slug, name, icon, description, code, category }
  attachCreatedSkillToCurrentAgent: false,
  // 详情页状态
  detail: null,               // { type:'agent'|'skill', missionId?, agentId?, skillId?, tab, draft, dirty, versionDropdownOpen }
  pendingDiff: null,
  quickRun: { turns: 0, conversation: [], promptedSave: false },
  // 用户登录态（null = 未登录）
  user: null,
  // 工作区指引板块折叠（从 localStorage 恢复）
  introCollapsed: (typeof localStorage !== 'undefined' && localStorage.getItem('dashboard_intro_collapsed') === '1'),
  // Auth modal 当前 Tab：'register' | 'login'
  authTab: 'register',
  // 聊天附件（待发送的文件列表）
  pendingAttachments: [],
  // 收藏的产物（按 missionId 存储）
  starredArtifacts: {},
  // MCP Servers（state.mcpServers）
  mcpServers: [],
  mcpLoaded: false,
  // Tools 页面：当前主分类（'skill' | 'mcp'）
  toolsKind: 'skill',
  // Agent 市场（mock，社区其他用户上传的 Team / Agent）
  agentMarket: [
    { id:'mkt_fin_team',   name:'Financial Ops Team', role:'统筹财务分析流程，拆解任务并协调多个执行 Agent。', icon:'hub',
      skills:['code_exec','chart_render','diff_compare'], authorName:'Alice@AgentHub', installCount: 1284, kind:'team', model:'GPT-4o (Omni)' },
    { id:'mkt_growth_team',name:'Growth Campaign Team', role:'负责增长活动拆解、素材协同与复盘汇总。', icon:'groups',
      skills:['web_search','markdown_write','email_compose'], authorName:'Bob@AgentHub', installCount: 932, kind:'team', model:'Claude 3.5 Sonnet' },
    { id:'mkt_visualizer', name:'Data Visualizer', role:'把结构化数据转成图表草稿。', icon:'insert_chart',
      skills:['chart_render','code_exec'], authorName:'Carol@AgentHub', installCount: 2150, kind:'agent', model:'GPT-4o mini' },
    { id:'mkt_searcher',   name:'Web Researcher', role:'抓取最新公开信息并去重。', icon:'travel_explore',
      skills:['web_search','fact_check'], authorName:'Dan@AgentHub', installCount: 4302, kind:'agent', model:'Claude 3.5 Sonnet' },
    { id:'mkt_translator', name:'Translator', role:'中英互译，保持术语一致。', icon:'translate',
      skills:['web_search'], authorName:'Eve@AgentHub', installCount: 778, kind:'agent', model:'Gemini 1.5 Pro' },
    { id:'mkt_code_review',name:'Code Reviewer', role:'按团队规范审查代码并给修改建议。', icon:'code',
      skills:['code_exec','diff_compare'], authorName:'Frank@AgentHub', installCount: 1876, kind:'agent', model:'GPT-4o (Omni)' },
  ],
};

const getMission = (id=state.missionId) => state.missions.find(m => m.id===id);
const getRun = () => {
  const m = getMission(); if (!m) return null;
  return m.runs.find(r => r.id===state.runId) || m.runs[0];
};

/* ===== SideNav ===== */
function renderSideNav() {
  console.log('[DEBUG-SIDEBAR] 开始执行renderSideNav()');
  // Missions 大类是否激活（Quick Run 已独立，不再触发 Missions 高亮）
  const missionsTabActive = ['dashboard','mission'].includes(state.view);
  const quickRunActive = state.view === 'quickRun';

  // 先定义所有内部函数和变量
  const renderTopTab = (id, icon, label, onclick) => {
    const active = (id === 'missions' && missionsTabActive)
                || (id === 'agents'    && state.view === 'agents')
                || (id === 'skills'    && state.view === 'skills')
                || (id === 'kbs'       && (state.view === 'kbs' || state.view === 'kb_detail'))
                || (id === 'memory'    && state.view === 'memory')
                || (id === 'settings'  && state.view === 'settings');
    return `
      <a onclick="${onclick}"
         class="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors
                ${active ? 'bg-secondary-container text-on-surface font-medium'
                         : 'text-on-surface-variant hover:bg-surface-container-low'}">
        <span class="material-symbols-outlined text-[20px]">${icon}</span>
        <span class="text-body-md">${label}</span>
      </a>`;
  };

  // 子项列表（仅当 Missions Tab 激活时展开）
  console.log('[DEBUG-SIDEBAR] 渲染侧边栏，每个mission:', state.missions);
  const missionItems = state.missions.map(m => {
    console.log('[DEBUG-SIDEBAR] 当前mission:', m, 'name=', m.name, 'icon=', m.icon, 'runs.length=', m.runs?.length);
    const active = state.view === 'mission' && m.id === state.missionId;
    const runsHTML = active ? `
      <div class="ml-6 mt-0.5 space-y-0.5 border-l border-outline-variant/60 pl-3 pb-1">
        ${m.runs.map(r => {
          const isCurrent = r.id === state.runId;
          const color = isCurrent ? 'text-primary font-medium'
                      : 'text-on-surface-variant hover:text-on-surface';
          return `<div class="flex items-center gap-1.5 py-1 text-label-md cursor-pointer ${color}"
                       onclick="openRun('${m.id}','${r.id}')">
                    <span>${escapeHTML(r.title)}</span>
                  </div>`;
        }).join('')}
      </div>` : '';
    return `
      <div>
        <a class="flex items-center justify-between gap-2 pl-3 pr-2 py-1.5 rounded-lg cursor-pointer transition-colors
                  ${active ? 'bg-secondary-container/60 text-on-surface font-medium'
                           : 'text-secondary hover:bg-surface-container-low'}"
           onclick="openMission('${m.id}')">
          <div class="flex items-center gap-2 min-w-0">
            ${m.is_pinned ? '<span class="material-symbols-outlined text-[12px] text-amber-500">push_pin</span>' : ''}
            <span class="material-symbols-outlined text-[16px]">${m.icon}</span>
            <span class="text-label-md truncate">${escapeHTML(m.name)}</span>
          </div>
          <div class="flex items-center gap-1">
            <span class="text-[10px] text-secondary opacity-70">${m.runs.length}</span>
            <span class="material-symbols-outlined text-[14px] text-secondary hover:text-amber-600 cursor-pointer opacity-60 hover:opacity-100"
                  onclick="event.stopPropagation(); toggleMissionPin('${m.id}')" title="置顶">push_pin</span>
            <span class="material-symbols-outlined text-[14px] text-secondary hover:text-blue-600 cursor-pointer opacity-60 hover:opacity-100"
                  onclick="event.stopPropagation(); toggleMissionArchive('${m.id}')" title="${m.is_archived ? '取消归档' : '归档'}">${m.is_archived ? 'unarchive' : 'archive'}</span>
            <span class="material-symbols-outlined text-[14px] text-red-500 hover:text-red-700 cursor-pointer opacity-60 hover:opacity-100"
                  onclick="event.stopPropagation(); deleteMission('${m.id}')" title="删除">delete</span>
          </div>
        </a>
        ${runsHTML}
      </div>`;
  }).join('');

  const missionsExpanded = missionsTabActive ? `
    <div class="ml-2 mt-1 space-y-0.5 border-l border-outline-variant/60 pl-2">
      <div class="pt-1 pb-0.5 px-2 text-[10px] uppercase tracking-wider text-secondary/70 font-bold flex items-center justify-between">
        <span>我的任务</span>
        <div class="flex items-center gap-1">
          <button onclick="toggleArchivedMissions()" title="${state.showArchivedMissions ? '隐藏归档' : '显示归档'}"
                  class="p-0.5 rounded hover:bg-surface-container-low text-[10px] ${state.showArchivedMissions ? 'text-primary' : 'text-secondary/60'}">archive</button>
        </div>
      </div>
      <div class="px-2 mb-1">
        <input type="text" id="missionSearchInput" placeholder="搜索任务..."
               value="${escapeHTML(state.missionSearch || '')}"
               class="w-full px-2 py-1 text-[11px] rounded border border-outline-variant/50 bg-surface-container-low focus:border-primary focus:outline-none"
               oninput="state.missionSearch = this.value; filterMissions(this.value)">
      </div>
      ${missionItems}
    </div>` : '';

  // 最后return整个侧边栏的HTML，确保所有变量都定义了
  return `
    <aside class="w-[260px] h-full border-r border-outline-variant bg-surface flex flex-col p-3 shrink-0">
      <!-- Logo -->
      <div class="flex items-center gap-3 px-2 pt-1 pb-4">
        <div class="w-8 h-8 bg-primary rounded flex items-center justify-center text-white font-bold">A</div>
        <div>
          <h1 class="text-title-lg font-headline-lg text-on-surface leading-tight">AgentHub</h1>
          <p class="text-label-sm text-secondary">多 Agent 协作工作台</p>
        </div>
      </div>

      <!-- 主 CTA + Quick Run（并列） -->
      <div class="space-y-2 mb-md">
        <button onclick="openCreateMission()"
          class="w-full py-2.5 px-3 bg-primary text-white rounded-lg flex items-center justify-center gap-2 hover:opacity-90 active:scale-[0.98] transition-all shadow-sm">
          <span class="material-symbols-outlined text-[18px]">add</span>
          <span class="text-body-md font-medium">New Mission</span>
        </button>
        <button onclick="openQuickRun()"
          class="w-full py-2.5 px-3 rounded-lg flex items-center justify-center gap-2 active:scale-[0.98] transition-all border
                 ${quickRunActive
                   ? 'bg-primary text-white border-primary shadow-sm hover:opacity-90'
                   : 'bg-primary-fixed/40 text-primary border-primary/30 hover:bg-primary-fixed/70'}">
          <span class="material-symbols-outlined text-[18px]">bolt</span>
          <span class="text-body-md font-medium">Quick Run</span>
        </button>
      </div>

      <!-- 顶层 4 个 Tab -->
      <nav class="flex-1 overflow-y-auto space-y-1 pr-1">
        ${renderTopTab('missions',  'assignment',     'Missions',  'openDashboard()')}
        ${missionsExpanded}
        ${renderTopTab('agents',    'smart_toy',      'Agents',    'openAgentsPage()')}
        ${renderTopTab('memory',    'psychology',     '记忆',       'openMemoryPage()')}
        ${renderTopTab('skills',    'build',      'Tools',     'openToolsPage()')}
        ${renderTopTab('kbs',       'menu_book',      '知识库',     'openKnowledgePage()')}
        ${renderTopTab('settings',  'settings',       'Settings',  'openSettingsPage()')}
      </nav>

      <!-- 底部用户卡 -->
      <div class="mt-2 pt-3 border-t border-outline-variant flex items-center gap-3 px-2 cursor-pointer hover:bg-surface-container-low rounded-lg transition-colors"
           onclick="openAuthModal()">
        <div class="w-8 h-8 rounded-full ${state.user ? 'bg-primary' : 'bg-surface-container'} flex items-center justify-center">
          <span class="material-symbols-outlined ${state.user ? 'text-white' : 'text-secondary'} text-[18px]">
            ${state.user ? 'person' : 'person_add'}
          </span>
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-label-md font-medium truncate ${state.user ? 'text-on-surface' : 'text-secondary'}">
            ${state.user ? escapeHTML(state.user.username) : 'Guest'}
          </p>
          <p class="text-[10px] text-secondary truncate">
            ${state.user ? escapeHTML(state.user.email) : '点击注册 / 登录'}
          </p>
        </div>
        ${state.user
          ? `<span class="material-symbols-outlined text-secondary text-[16px] cursor-pointer hover:text-error" title="退出登录" onclick="event.stopPropagation();logout()">logout</span>`
          : `<span class="material-symbols-outlined text-secondary text-[16px]">arrow_forward</span>`
        }
      </div>
    </aside>`;
}

// 添加删除mission的函数
async function deleteMission(missionId) {
  if (!confirm(`确定要删除任务 "${state.missions.find(m => m.id === missionId)?.name}" 吗？`)) {
    return;
  }
  
  try {
    const response = await api(`/missions/${missionId}`, {
      method: 'DELETE'
    });
    
    if (response && response.ok) {
      // 从前端状态中移除
      state.missions = state.missions.filter(m => m.id !== missionId);
      // 如果删除的是当前选中的mission，切换到第一个
      if (state.missionId === missionId && state.missions.length > 0) {
        state.missionId = state.missions[0].id;
      } else if (state.missions.length === 0) {
        state.missionId = null;
      }
      showToast('任务已删除', 'success');
      render();
    } else {
      showToast('删除失败：后端返回错误', 'error');
    }
  } catch (error) {
    console.error('删除mission失败:', error);
    // 即使后端API失败，也从前端移除
    state.missions = state.missions.filter(m => m.id !== missionId);
    if (state.missionId === missionId && state.missions.length > 0) {
      state.missionId = state.missions[0].id;
    }
    showToast('已本地删除（后端API调用失败）', 'warning');
    render();
  }
}

async function toggleMissionPin(missionId) {
  try {
    const response = await api(`/missions/${missionId}/pin`, { method: 'PUT' });
    if (response && response.ok) {
      showToast(response.message, 'success');
      // 重新加载列表以获取后端排序后的结果
      await loadMissions();
    }
  } catch (error) {
    console.error('置顶操作失败:', error);
    showToast('置顶操作失败', 'error');
  }
}

async function toggleMessagePin(messageId, idx) {
  const run = getRun();
  const msg = run.conversation[idx];
  if (!msg || !msg.dbId) {
    showToast('消息尚未保存到数据库，无法置顶', 'error');
    return;
  }
  const m = getMission();
  const conversationId = parseInt((m.id || '').replace('mis_', '')) || 0;
  if (!conversationId) {
    showToast('对话 ID 无效', 'error');
    return;
  }
  try {
    const response = await api(`/conversations/${conversationId}/messages/${msg.dbId}/pin`, { method: 'POST' });
    if (response && response.ok) {
      msg.isPinned = response.is_pinned;
      showToast(response.is_pinned ? '已置顶该消息' : '已取消置顶', 'success');
      render();
      // 刷新上下文，因为 pinned 消息会影响上下文加载
      if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        // 通过 WebSocket 广播 pin 状态变化（告知其他标签页）
        state.ws.send(JSON.stringify({ type: 'pin_update', message_id: msg.dbId, is_pinned: response.is_pinned }));
      }
    }
  } catch (error) {
    console.error('消息置顶操作失败:', error);
    showToast('消息置顶操作失败', 'error');
  }
}

async function toggleMissionArchive(missionId) {
  try {
    const response = await api(`/missions/${missionId}/archive`, { method: 'PUT' });
    if (response && response.ok) {
      showToast(response.message, 'success');
      // 重新加载列表以获取后端过滤/排序后的结果
      await loadMissions();
    }
  } catch (error) {
    console.error('归档操作失败:', error);
    showToast('归档操作失败', 'error');
  }
}

function toggleArchivedMissions() {
  state.showArchivedMissions = !state.showArchivedMissions;
  loadMissions();
}

async function loadMissions() {
  try {
    const includeArchived = state.showArchivedMissions ? 'true' : 'false';
    const response = await api(`/missions?include_archived=${includeArchived}`);
    if (response && response.ok && response.missions) {
      // 合并 missions，保留现有的 conversation 数据（避免刷新后消息消失）
      const existing = new Map((state.missions || []).map(m => [m.id, m]));
      state.missions = response.missions.map(newM => {
        const oldM = existing.get(newM.id);
        if (oldM && oldM.runs && oldM.runs.length > 0) {
          newM.runs = newM.runs.map((newRun, i) => {
            const oldRun = oldM.runs[i];
            if (oldRun && oldRun.conversation && oldRun.conversation.length > 0) {
              newRun.conversation = oldRun.conversation;
            }
            return newRun;
          });
        }
        return newM;
      });
      if (state.missions.length > 0 && !state.missionId) {
        state.missionId = state.missions[0].id;
      }
      render();
    }
  } catch (error) {
    console.error('加载missions失败:', error);
  }
}

let _missionSearchDebounce = null;
async function filterMissions(searchValue) {
  // 搜索为空时重新加载全部
  if (!searchValue || !searchValue.trim()) {
    loadMissions();
    return;
  }
  // 防抖调用后端搜索
  clearTimeout(_missionSearchDebounce);
  _missionSearchDebounce = setTimeout(async () => {
    try {
      const includeArchived = state.showArchivedMissions ? 'true' : 'false';
      const response = await api(`/missions?search=${encodeURIComponent(searchValue.trim())}&include_archived=${includeArchived}`);
      if (response && response.ok && response.missions) {
        state.missions = response.missions;
        render();
      }
    } catch (error) {
      console.error('搜索missions失败:', error);
      // 降级：前端本地过滤
      const lower = searchValue.toLowerCase();
      state.missions = state.missions.filter(m =>
        (m.name || '').toLowerCase().includes(lower) ||
        (m.description || '').toLowerCase().includes(lower)
      );
      render();
    }
  }, 300);
}

/* ===== TopBar ===== */
function renderTopBar() {
  let crumb, actions;
  if (state.view === 'dashboard') {
    crumb = `<span class="text-secondary">工作空间</span>
             <span class="material-symbols-outlined text-[14px] text-secondary">chevron_right</span>
             <span class="text-on-surface font-medium">我的工作空间</span>`;
    actions = `<button onclick="openCreateMission()"
                 class="bg-primary text-white px-4 py-1.5 rounded-lg font-label-md text-label-md flex items-center gap-2 hover:opacity-90 transition-opacity">
                 <span class="material-symbols-outlined text-[16px]">add</span>创建任务
               </button>`;
  } else if (state.view === 'mission') {
    const m = getMission();
    const r = getRun();
    crumb = `<span class="text-secondary cursor-pointer hover:text-on-surface" onclick="openDashboard()">工作空间</span>
             <span class="material-symbols-outlined text-[14px] text-secondary">chevron_right</span>
             <span class="text-on-surface font-medium">${escapeHTML(m.name)}</span>
             <span class="material-symbols-outlined text-[14px] text-secondary ml-2">chevron_right</span>
             <span class="text-secondary">${escapeHTML(r.title)}</span>`;
    actions = `<button onclick="startNewRun()" class="bg-primary text-white px-4 py-1.5 rounded-lg font-label-md text-label-md flex items-center gap-2 hover:opacity-90">
                 <span class="material-symbols-outlined text-[16px]">play_arrow</span>新运行
               </button>`;
  } else if (state.view === 'quickRun') {
    crumb = `<span class="text-secondary">工作空间</span>
             <span class="material-symbols-outlined text-[14px] text-secondary">chevron_right</span>
             <span class="text-on-surface font-medium">Quick Run</span>
             <span class="ml-2 px-2 py-0.5 rounded text-[10px] font-bold bg-primary-fixed text-on-primary-fixed">临时</span>`;
    actions = `<button onclick="manualSaveQuickRun()" class="bg-surface border border-outline-variant text-on-surface px-4 py-1.5 rounded-lg font-label-md text-label-md flex items-center gap-2 hover:bg-surface-container-low">
                 <span class="material-symbols-outlined text-[16px]">bookmark_add</span>保存为 Mission
               </button>`;
  } else {
    const titleMap = { agents:'Agents 库', skills:'Skills', memory:'记忆面板', settings:'Settings' };
    const t = titleMap[state.view] || '';
    crumb = `<span class="text-secondary">工作空间</span>
             <span class="material-symbols-outlined text-[14px] text-secondary">chevron_right</span>
             <span class="text-on-surface font-medium">${t}</span>`;
    actions = '';
  }

  return `
    <header class="h-[56px] border-b border-outline-variant bg-surface flex items-center justify-between px-lg shrink-0 z-30">
      <div class="flex items-center gap-2 text-label-md text-secondary">${crumb}</div>
      <div class="flex-1 max-w-md mx-8">
        <div class="relative flex items-center">
          <span class="material-symbols-outlined absolute left-3 text-secondary text-[20px]">search</span>
          <input class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg pl-10 pr-4 py-1.5 text-body-md focus:border-primary focus:ring-0 transition-all"
                 placeholder="搜索任务、智能体或运行记录..." type="text"/>
        </div>
      </div>
      <div class="flex items-center gap-3">
        ${actions}
        <button class="text-secondary hover:text-primary transition-colors">
          <span class="material-symbols-outlined">notifications</span>
        </button>
        <button class="text-secondary hover:text-primary transition-colors">
          <span class="material-symbols-outlined">help_outline</span>
        </button>
        <div class="h-8 w-px bg-outline-variant"></div>
        <div class="w-8 h-8 rounded-full bg-secondary-fixed flex items-center justify-center cursor-pointer">
          <span class="material-symbols-outlined text-secondary text-[18px]">person</span>
        </div>
      </div>
    </header>`;
}

/* ===== Router ===== */
function openDashboard() { if (!confirmLeaveDirty()) return; state.view='dashboard'; render(); }
async function openMission(id) {
  if (!confirmLeaveDirty()) return;
  state.view='mission'; state.missionId=id;
  const m = getMission(); state.runId = m.runs[0].id;
  state.selectedAgentId = m.squad.agents[0]?.id || null;
  // 异步加载历史聊天消息和收藏状态
  try {
    const convId = id.replace('mis_', '');
    const [msgs, starredResp] = await Promise.all([
      api(`/chat/${convId}/messages`),
      api(`/missions/${convId}/starred-artifacts`).catch(() => null)
    ]);
    if (Array.isArray(msgs) && msgs.length > 0) {
      const run = getRun();
      run.conversation = msgs.map(msg => {
        // 后端存储了结构化 JSON，尝试解析出纯文本
        let text = msg.content;
        try {
          const parsed = JSON.parse(msg.content);
          if (parsed && typeof parsed === 'object' && parsed.content !== undefined) {
            text = parsed.content;
          }
        } catch(e) {
          // 不是 JSON，保持原样
        }
        // 从 metadata 中提取附件
        const metaData = msg.meta_data || {};
        const attachments = metaData.attachments || null;
        return {
          type: msg.agent_id === 'user' ? 'user' : 'agent',
          agent: msg.agent_id === 'user' ? '我' : (m.squad.agents.find(a => a.id === msg.agent_id)?.name || msg.agent_id),
          icon: msg.agent_id === 'user' ? 'person' : (m.squad.agents.find(a => a.id === msg.agent_id)?.icon || 'smart_toy'),
          text: text,
          time: msg.created_at,
          dbId: msg.id,
          messageType: msg.message_type || 'text',
          metadata: metaData,
          attachments: attachments,
          isPinned: msg.is_pinned || false,
          mentions: msg.mentions || []
        };
      });
    }
    // 加载收藏状态
    if (starredResp && starredResp.ok && starredResp.starred_artifacts) {
      state.starredArtifacts[id] = starredResp.starred_artifacts;
    }
  } catch (e) {
    console.log('[MISSION] 加载历史消息失败或没有历史消息:', e);
  }
  render();
}
function openRun(missionId, runId) {
  if (!confirmLeaveDirty()) return;
  state.view='mission'; state.missionId=missionId; state.runId=runId;
  const m = getMission(); state.selectedAgentId = m.squad.agents[0]?.id || null;
  render();
}
function openQuickRun() { if (!confirmLeaveDirty()) return; state.view='quickRun'; render(); }
function openAgentsPage()    { if (!confirmLeaveDirty()) return; state.view='agents';    render(); }
function openWorkflowsPage() { openSkillsPage(); }   // 兼容旧入口
function openSkillsPage()    { if (!confirmLeaveDirty()) return; state.view='skills'; if (!state.skills.loaded) loadSkills(); render(); }
function openToolsPage()     { openSkillsPage(); }
function openMemoryPage()    { if (!confirmLeaveDirty()) return; state.view='memory';   render(); }
function openSettingsPage()  { if (!confirmLeaveDirty()) return; state.view='settings';  render(); }
function openKnowledgePage() {
  if (!confirmLeaveDirty()) return;
  if (!state.kbs.loaded) loadKbs();
  state.view = 'kbs';
  render();
}
function openKbDetail(kbId) {
  if (!confirmLeaveDirty()) return;
  if (!state.kbs.loaded) loadKbs();
  const kb = state.kbs.list.find(k => k.id === kbId);
  if (!kb) return showToast('知识库不存在');
  state.kbDetail = {
    id: kbId,
    tab: 'docs',
    selectedIds: new Set(),
    draft: { name: kb.name, icon: kb.icon, description: kb.description || '' },
    dirty: false,
    searchResult: null,
  };
  state.view = 'kb_detail';
  render();
}

// 离开详情页 dirty 检查；返回 true 表示可以继续；同时清掉 detail
function confirmLeaveDirty() {
  const agentSkillDirty = state.detail && state.detail.dirty;
  const kbDirty = state.kbDetail && state.kbDetail.dirty;
  if (agentSkillDirty || kbDirty) {
    if (!confirm('当前有未保存的改动，确认离开？')) return false;
  }
  state.detail = null;
  state.kbDetail = null;
  return true;
}

/* ===== Schema Migration / Defaults ===== */
const MCP_STORAGE_KEY = 'agenthub_mcp_servers_v1';
const CUSTOM_SKILLS_STORAGE_KEY = 'agenthub_custom_skills_v1';

function loadMcpServers() {
  if (state.mcpLoaded) return;
  try {
    const raw = localStorage.getItem(MCP_STORAGE_KEY);
    state.mcpServers = raw ? JSON.parse(raw) : [];
  } catch (e) { state.mcpServers = []; }
  state.mcpLoaded = true;
}
function saveMcpServers() {
  try { localStorage.setItem(MCP_STORAGE_KEY, JSON.stringify(state.mcpServers || [])); }
  catch (e) { console.warn('saveMcpServers failed', e); }
}

function loadCustomSkills() {
  try {
    const raw = localStorage.getItem(CUSTOM_SKILLS_STORAGE_KEY);
    state.customSkills = raw ? JSON.parse(raw) : [];
  } catch (e) {
    state.customSkills = [];
  }
}

function saveCustomSkills() {
  try { localStorage.setItem(CUSTOM_SKILLS_STORAGE_KEY, JSON.stringify(state.customSkills || [])); }
  catch (e) { console.warn('saveCustomSkills failed', e); }
}
function ensureAgentSchema(a) {
  if (!a) return a;
  // 旧值兼容：'main' / 'manager' → 'team'；'sub' / 'member' → 'agent'
  if (a.kind === 'main' || a.kind === 'manager') a.kind = 'team';
  else if (a.kind === 'sub' || a.kind === 'member') a.kind = 'agent';
  if (a.kind !== 'team' && a.kind !== 'agent') a.kind = 'agent';
  // 字段重命名：subAgentIds → teamMemberIds
  if (Array.isArray(a.subAgentIds) && !Array.isArray(a.teamMemberIds)) {
    a.teamMemberIds = a.subAgentIds;
    delete a.subAgentIds;
  }
  if (!Array.isArray(a.teamMemberIds)) a.teamMemberIds = [];
  if (!a.memoryConfig) a.memoryConfig = { strategy:'window', windowSize:10, summaryPrompt:'请将以上对话内容浓缩为一段不超过 200 字的要点摘要，保留关键事实、决策与下一步。', kvNamespace:'' };
  if (!a.planningConfig) a.planningConfig = { mode:'react', stepsTemplate:'1. 理解任务\n2. 拆解步骤\n3. 调用工具\n4. 汇总输出' };
  if (!a.validationConfig) a.validationConfig = { strategy:'none', rules:[], judgePrompt:'请检查以上回答是否覆盖了用户问题的全部要点，列出 missed_points: [] 与 ok: true/false' };
  if (!a.hooks) a.hooks = { preToolUse:'', postToolUse:'', onError:'', onComplete:'' };
  if (!Array.isArray(a.skills)) a.skills = [];
  // MCP Tools 用独立字段，避免和 skills 数组混淆。元素形如 "<serverId>:<toolName>"
  if (!Array.isArray(a.mcpTools)) a.mcpTools = [];
  return a;
}
function ensureMissionSchema(m) {
  if (!m || !m.squad) return m;
  if (!Array.isArray(m.squad.enabledSkills)) m.squad.enabledSkills = [];
  if (!Array.isArray(m.squad.enabledMcpTools)) m.squad.enabledMcpTools = [];
  (m.squad.agents || []).forEach(ensureAgentSchema);
  ensureMissionManager(m);
  return m;
}
// 保证 Mission 内有且仅有 1 个 Team；缺失则首个 Agent 升级，多则保留首个其余降级。
function ensureMissionManager(m) {
  if (!m || !m.squad) return;
  const agents = m.squad.agents || [];
  if (!agents.length) return;
  const teams = agents.filter(a => a.kind === 'team');
  if (teams.length === 0) {
    agents[0].kind = 'team';
  } else if (teams.length > 1) {
    teams.slice(1).forEach(a => { a.kind = 'agent'; });
  }
  // Team.teamMemberIds 首次种子化：默认包含当前 Mission 内所有其它 Agent。
  // 用 _teamSeeded 标记防止用户手动清空后被反复回填。
  const mgr = (m.squad.agents || []).find(a => a.kind === 'team');
  if (mgr && !mgr._teamSeeded) {
    if (!Array.isArray(mgr.teamMemberIds)) mgr.teamMemberIds = [];
    if (mgr.teamMemberIds.length === 0) {
      mgr.teamMemberIds = agents.filter(a => a.id !== mgr.id).map(a => a.id);
    }
    mgr._teamSeeded = true;
  }
}
function getMissionManager(m) {
  if (!m || !m.squad) return null;
  return (m.squad.agents || []).find(a => a.kind === 'team') || null;
}
function ensureAllSchemas() {
  (state.missions || []).forEach(ensureMissionSchema);
  if (!state.mcpLoaded) loadMcpServers();
}

const MODEL_OPTIONS = ['GPT-4o (Omni)','GPT-4o mini','Claude 3.5 Sonnet','Gemini 1.5 Pro','本地 Llama-3'];
