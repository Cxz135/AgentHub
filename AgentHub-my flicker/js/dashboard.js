function getAgentKindMeta(kind) {
  return kind === 'team'
    ? { label: 'Team', badge: 'TEAM', icon: 'hub', description: '主协同单元 · 负责拆解任务、调度 Agent 并汇总结果' }
    : { label: 'Agent', badge: 'AGENT', icon: 'smart_toy', description: '执行单元 · 承接 Team 分派的具体任务' };
}

/* ===== Main render ===== */
function render() {
  ensureAllSchemas();
  const app = $('#app');
  app.innerHTML = `
    ${renderSideNav()}
    <div class="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
      ${renderTopBar()}
      <div id="main-canvas" class="flex-1 overflow-hidden flex flex-col"></div>
    </div>
    ${state.skillPanelOpen ? renderSkillPanel() : ''}`;

  const canvas = $('#main-canvas');
  if (state.view === 'dashboard')   canvas.innerHTML = renderDashboard();
  else if (state.view === 'mission') canvas.innerHTML = renderMissionWorkspace();
  else if (state.view === 'quickRun') canvas.innerHTML = renderQuickRun();
  else if (state.view === 'agents')    canvas.innerHTML = renderAgentsPage();
  else if (state.view === 'skills')    canvas.innerHTML = renderSkillsPage();
  else if (state.view === 'agent_detail') canvas.innerHTML = renderAgentDetailPage();
  else if (state.view === 'skill_detail') canvas.innerHTML = renderSkillDetailPage();
  else if (state.view === 'kbs')         canvas.innerHTML = renderKnowledgePage();
  else if (state.view === 'kb_detail')   canvas.innerHTML = renderKbDetailPage();
  else if (state.view === 'memory')    canvas.innerHTML = renderMemoryPage();
  else if (state.view === 'settings')  canvas.innerHTML = renderSettingsPage();
  if (typeof hljs !== 'undefined') hljs.highlightAll();
  // 渲染 Mermaid 图表和增强 Markdown 表格（DOM 就绪后）
  setTimeout(() => {
    if (typeof renderMermaidDiagrams === 'function') renderMermaidDiagrams();
    if (typeof enhanceMarkdownTables === 'function') enhanceMarkdownTables();
  }, 50);
}

/* ===================== Dashboard ===================== */
function renderDashboard() {
  const userName = state.user ? state.user.username : 'there';
  const heading = `早上好，${escapeHTML(userName)} 👋`;

  // 统计数据
  const missionCount = state.missions.length;
  const runCount     = state.missions.reduce((n,m)=>n+m.runs.length,0);
  const skillCount   = BUILTIN_SKILLS.length + state.customSkills.length;

  // ===== 折叠工作区指引板块 =====
  const introHeader = `
    <div class="flex items-center justify-between px-xl pt-xl pb-3">
      <h2 class="text-headline-md text-on-surface">${heading}</h2>
      <button onclick="toggleIntro()"
              class="flex items-center gap-1 px-2 py-1 rounded-lg text-label-md text-secondary hover:bg-surface-container-low transition-colors">
        <span class="material-symbols-outlined text-[18px]">${state.introCollapsed ? 'expand_more' : 'expand_less'}</span>
        <span>${state.introCollapsed ? '展开指引' : '收起'}</span>
      </button>
    </div>`;

  // 折叠态：薄条
  const introCollapsedBar = `
    <div class="mx-xl mb-md bg-surface-container-lowest border border-outline-variant rounded-xl px-md py-2.5 flex items-center gap-2 cursor-pointer hover:border-primary/40 transition-colors"
         onclick="toggleIntro()">
      <span class="material-symbols-outlined text-primary text-[16px]">tips_and_updates</span>
      <span class="text-label-md text-secondary flex-1">工作区指引（已收起） · 点击展开</span>
      <span class="material-symbols-outlined text-secondary text-[16px]">expand_more</span>
    </div>`;

  // 展开态：左卡（2/3） + 右栏（1/3 双卡）
  const introExpanded = `
    <div class="px-xl mb-md grid grid-cols-3 gap-md">
      <!-- 左卡 2/3 -->
      <div class="col-span-2 bg-surface-container-lowest border border-outline-variant rounded-xl p-xl flex flex-col gap-md">
        <p class="text-[10px] uppercase tracking-[0.2em] font-bold text-secondary">WORKSPACE</p>
        <h3 class="text-display text-on-surface tracking-tight leading-tight">把重复任务沉淀成可复用的 Agent 班底</h3>
        <p class="text-body-md text-secondary leading-relaxed">先选模板，或者让 AI 根据你的工作场景帮你搭建一个 Mission。进入模块后，所有对话、班底编辑和输出都在同一处完成。</p>
        <div class="flex items-center gap-3 pt-1">
          <button onclick="openCreateMission()"
                  class="bg-primary text-white px-4 py-2 rounded-lg flex items-center gap-2 hover:opacity-90 transition-opacity text-label-md font-medium shadow-sm">
            <span class="material-symbols-outlined text-[18px]">add</span>
            <span>创建 Mission</span>
          </button>
          <button onclick="openQuickRun()"
                  class="bg-surface border border-outline-variant text-on-surface px-4 py-2 rounded-lg flex items-center gap-2 hover:bg-surface-container-low transition-colors text-label-md font-medium">
            <span class="material-symbols-outlined text-[18px] text-primary">bolt</span>
            <span>试试 Quick Run</span>
          </button>
        </div>
        <!-- 3 个橙色统计 Tile -->
        <div class="grid grid-cols-3 gap-md pt-2">
          ${[
            { v: missionCount, label: '活跃 Mission', icon: 'hub' },
            { v: runCount,     label: '累计 Run',     icon: 'play_circle' },
            { v: skillCount,   label: '可用 Skill',   icon: 'extension' },
          ].map(t => `
            <div class="bg-primary-fixed/30 border border-primary/15 rounded-xl px-md py-md">
              <div class="w-8 h-8 rounded-lg bg-primary-fixed flex items-center justify-center mb-2">
                <span class="material-symbols-outlined text-primary text-[18px]">${t.icon}</span>
              </div>
              <p class="text-headline-lg text-on-surface leading-none">${t.v}</p>
              <p class="text-label-md text-secondary mt-1">${t.label}</p>
            </div>`).join('')}
        </div>
      </div>

      <!-- 右栏 1/3 双卡 -->
      <div class="col-span-1 flex flex-col gap-md">
        <!-- 开始方式 -->
        <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-md flex flex-col gap-3">
          <p class="text-label-md text-secondary tracking-wider">开始方式</p>
          ${[
            { icon:'view_module', name:'从模板创建', desc:'最快进入稳定工作流，适合第一次使用。', click:'openCreateMission()' },
            { icon:'auto_awesome', name:'让 AI 帮我搭建', desc:'输入一句话，自动生成班底提案和推荐技能。', click:"openCreateMission();setTimeout(()=>document.querySelector('#ai-prompt-input')?.focus(),100)" },
            { icon:'bolt', name:'先做一次 Quick Run', desc:'适合临时探索，后续可直接沉淀为 Mission。', click:'openQuickRun()' },
          ].map(s => `
            <div onclick="${s.click}"
                 class="px-3 py-2.5 rounded-lg border border-outline-variant cursor-pointer hover:border-primary/40 hover:bg-surface-container-low transition-all">
              <div class="flex items-center gap-2 mb-0.5">
                <span class="material-symbols-outlined text-primary text-[16px]">${s.icon}</span>
                <span class="font-label-md text-label-md text-on-surface font-medium">${s.name}</span>
              </div>
              <p class="text-label-sm text-secondary leading-snug pl-6">${s.desc}</p>
            </div>`).join('')}
        </div>
        <!-- 推荐路径 -->
        <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-md">
          <p class="text-label-md text-secondary tracking-wider mb-2">推荐路径</p>
          <p class="text-body-md text-secondary leading-relaxed">新用户优先从模板进入，尽快看到第一份结果；老用户则从左侧 Mission 列表回到熟悉班底继续执行。</p>
        </div>
      </div>
    </div>`;

  // ===== 我的任务区 =====
  const missionCards = state.missions.map(m => {
    const lastRun = m.runs[0];
    const statusBadge = lastRun.status === 'running'
      ? `<span class="flex items-center gap-1 text-primary text-label-sm font-bold">
           <span class="w-1.5 h-1.5 bg-primary rounded-full animate-pulse"></span>运行中</span>`
      : lastRun.status === 'idle'
      ? `<span class="flex items-center gap-1 text-secondary text-label-sm font-bold">
           <span class="w-1.5 h-1.5 bg-secondary rounded-full"></span>待启动</span>`
      : `<span class="flex items-center gap-1 text-secondary text-label-sm font-bold">
           <span class="material-symbols-outlined text-[14px]">check_circle</span>已完成</span>`;

    const avatars = m.squad.agents.slice(0,4).map(a => `
      <div class="w-7 h-7 rounded-full border-2 border-surface-container-lowest bg-secondary-container flex items-center justify-center -ml-2 first:ml-0" title="${escapeHTML(a.name)}">
        <span class="material-symbols-outlined text-on-surface-variant text-[14px]">${a.icon}</span>
      </div>`).join('');
    const extra = m.squad.agents.length > 4
      ? `<div class="w-7 h-7 rounded-full border-2 border-surface-container-lowest bg-surface-container text-[10px] flex items-center justify-center -ml-2 text-secondary font-bold">+${m.squad.agents.length-4}</div>` : '';

    return `
      <div onclick="openMission('${m.id}')"
           class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg cursor-pointer hover:border-primary/40 hover:shadow-sm mission-card-shadow transition-all flex flex-col gap-md">
        <div class="flex items-start justify-between">
          <div class="w-12 h-12 rounded-lg bg-primary-fixed flex items-center justify-center">
            <span class="material-symbols-outlined text-on-primary-fixed-variant">${m.icon}</span>
          </div>
          ${statusBadge}
        </div>
        <div>
          <h3 class="text-title-lg font-headline-md text-on-surface">${escapeHTML(m.name)}</h3>
          <p class="text-body-md text-secondary mt-1 line-clamp-2">${escapeHTML(m.description)}</p>
        </div>
        <div class="flex items-center justify-between pt-md border-t border-outline-variant/60">
          <div class="flex items-center">${avatars}${extra}</div>
          <div class="flex items-center gap-2 text-label-md text-secondary">
            <span class="material-symbols-outlined text-[14px]">play_circle</span>
            <span>${m.runs.length} 次运行</span>
          </div>
        </div>
      </div>`;
  }).join('');

  const addCard = `
    <div onclick="openCreateMission()"
         class="border-2 border-dashed border-outline-variant rounded-xl p-lg cursor-pointer hover:border-primary hover:bg-primary-fixed/20 transition-all flex flex-col items-center justify-center text-secondary hover:text-primary min-h-[200px] gap-2">
      <span class="material-symbols-outlined text-[32px]">add_circle</span>
      <p class="font-label-md text-label-md">创建新任务</p>
      <p class="text-label-sm opacity-70">使用模板 · AI 引导 · 空白</p>
    </div>`;

  return `
    <div class="flex-1 overflow-y-auto bg-background">
      ${introHeader}
      ${state.introCollapsed ? introCollapsedBar : introExpanded}
      <section class="px-xl pb-md">
        <div class="flex items-center justify-between mb-md">
          <h3 class="text-headline-md text-on-surface">我的任务</h3>
          <div class="flex items-center gap-2 text-label-md text-secondary">
            <button class="px-2 py-1 rounded hover:bg-surface-container-low flex items-center gap-1">
              <span class="material-symbols-outlined text-[16px]">filter_list</span>筛选
            </button>
            <button class="px-2 py-1 rounded hover:bg-surface-container-low flex items-center gap-1">
              <span class="material-symbols-outlined text-[16px]">sort</span>排序
            </button>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-md">
          ${missionCards}
          ${addCard}
        </div>
      </section>
    </div>`;
}

function toggleIntro() {
  state.introCollapsed = !state.introCollapsed;
  try { localStorage.setItem('dashboard_intro_collapsed', state.introCollapsed ? '1' : '0'); } catch(e){}
  render();
}

async function createMissionFromTemplate(tplId) {
  const tpl = TEMPLATES.find(t => t.id === tplId);
  if (!tpl) return;
  const missionData = {
    name: tpl.name + ' 副本',
    squad: {
      agents: tpl.agents.map((name,i) => makeAgent(
        name,
        `基于模板「${tpl.name}」生成的子 Agent。`,
        ['description','finance_mode','edit_note','public','difference','event'][i % 6],
        `你是 ${name}，负责协同完成「${tpl.name}」相关子任务。`,
        tpl.skills
      )),
      enabledSkills: tpl.skills,
      coordinator: { name:'Coordinator' }
    }
  };
  
  try {
    // 调用后端API创建mission
    const response = await api('/missions', {
      method: 'POST',
      body: JSON.stringify(missionData)
    });
    
    if (response && response.ok && response.mission) {
      state.missions.unshift(response.mission);
      showToast(`已从模板创建：${response.mission.name}`, 'success');
      openMission(response.mission.id);
    } else {
      // 如果后端API失败，前端临时创建
      const newMission = {
        id: uid('mis'), name: tpl.name + ' 副本', icon: tpl.icon,
        runs: [{ id:'run_current', title:'当前运行', status:'idle', conversation:[], artifact:null }],
        squad: missionData.squad
      };
      state.missions.unshift(newMission);
      showToast(`已从模板创建（本地临时）：${newMission.name}`, 'warning');
      openMission(newMission.id);
    }
  } catch (error) {
    console.error('创建mission失败:', error);
    const newMission = {
      id: uid('mis'), name: tpl.name + ' 副本', icon: tpl.icon,
      runs: [{ id:'run_current', title:'当前运行', status:'idle', conversation:[], artifact:null }],
      squad: missionData.squad
    };
    state.missions.unshift(newMission);
    showToast(`创建失败，已本地创建：${newMission.name}`, 'error');
    openMission(newMission.id);
  }
  render();
}