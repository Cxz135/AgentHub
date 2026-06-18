function renderRightEditor() {
  const m = getMission();
  const archived = false; // legacy: Run 不再归档，所有右栏始终可写
  const tabs = [
    { id:'agents', label:'Team',   icon:'groups' },
    { id:'skills', label:'Tools',  icon:'build' },
    { id:'kbs',    label:'知识库', icon:'menu_book' },
    { id:'settings', label:'设置', icon:'tune' },
  ];
  let body = '';
  if (state.rightTab === 'agents')   body = renderAgentsTab(m, archived);
  if (state.rightTab === 'skills')   body = renderMissionToolsTab(m, archived);
  if (state.rightTab === 'kbs')      body = renderMissionKbsTab(m, archived);
  if (state.rightTab === 'settings') body = renderSettingsTab(m, archived);

  return `
    <aside class="w-[360px] border-l border-outline-variant bg-surface-container-low flex flex-col shrink-0 ${archived ? 'pointer-events-none opacity-95' : ''}">
      <div class="h-[48px] border-b border-outline-variant px-3 flex items-center gap-1 shrink-0 bg-surface-container-low">
        ${tabs.map(t => `
          <button onclick="state.rightTab='${t.id}';render()"
            class="flex-1 py-1.5 rounded-lg text-label-md flex items-center justify-center gap-1.5
                   ${state.rightTab===t.id ? 'bg-surface-container-lowest text-primary font-bold border border-outline-variant' : 'text-secondary hover:bg-surface-container'}">
            <span class="material-symbols-outlined text-[16px]">${t.icon}</span>${t.label}
          </button>`).join('')}
      </div>
      <div class="flex-1 overflow-y-auto">${body}</div>
    </aside>`;
}

function renderAgentsTab(m, archived) {
  ensureMissionSchema(m);
  const agents = m.squad.agents || [];
  const team = getMissionManager(m);
  const individualAgents = agents.filter(a => a.kind === 'agent');
  const agentById = new Map(individualAgents.map(a => [a.id, a]));

  const selectedId = state.selectedAgentId || (team && team.id) || (agents[0] && agents[0].id);

  const renderRow = (a, i, total, opts = {}) => {
    const meta = getAgentKindMeta(a.kind);
    const isLast = i === total - 1;
    const isSelected = a.id === selectedId;
    const isTeam = a.kind === 'team';
    const childAgents = isTeam ? (a.teamMemberIds || []).map(id => agentById.get(id)).filter(Boolean) : [];
    const cardBase = isTeam
      ? `bg-primary-container/40 border-2 border-primary/60 shadow-sm`
      : (isSelected ? 'bg-surface-container-lowest border border-primary/30 shadow-sm' : 'hover:bg-surface-container border border-transparent');
    return `
      <div class="${opts.noConnector ? '' : `agent-connector ${isLast ? 'agent-connector-last' : ''}`}">
        <div onclick="selectAgent('${a.id}')"
             class="relative flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-all group ${cardBase}">
          <div class="w-10 h-10 rounded-lg ${isTeam ? 'bg-primary text-on-primary' : 'bg-secondary-container text-on-surface-variant'} flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined text-[20px]">${a.icon}</span>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between gap-1">
              <p class="font-label-md text-on-surface truncate flex items-center gap-1.5">
                ${escapeHTML(a.name)}
                <span class="text-[9px] px-1.5 py-0.5 rounded ${isTeam ? 'bg-primary text-on-primary' : 'bg-secondary-container text-on-surface-variant'} font-bold tracking-wide">${meta.badge}</span>
              </p>
              <button onclick="event.stopPropagation(); openAgentDetail('${m.id}','${a.id}')"
                title="打开详情页"
                class="opacity-0 group-hover:opacity-100 text-secondary hover:text-primary transition-opacity shrink-0">
                <span class="material-symbols-outlined text-[16px]">open_in_new</span>
              </button>
            </div>
            <p class="text-[11px] ${isTeam ? 'text-primary font-medium' : 'text-secondary'} mt-0.5">${meta.description}</p>
            <p class="text-label-sm text-secondary italic line-clamp-2 mt-0.5">${escapeHTML(a.role)}</p>
            <div class="flex items-center gap-2 mt-1.5 text-[10px] text-secondary">
              ${isTeam ? `<span>${childAgents.length} 个 Agent</span>` : `<span>${escapeHTML(a.model || '未设置模型')}</span>`}
            </div>
            <div class="flex gap-1 mt-1.5 flex-wrap">
              ${(a.skills||[]).slice(0,4).map(s => `<span class="text-[10px] px-1.5 py-0.5 bg-surface-container rounded text-secondary">${escapeHTML(s)}</span>`).join('')}
              ${(a.skills||[]).length>4 ? `<span class="text-[10px] text-secondary">+${(a.skills||[]).length-4}</span>` : ''}
            </div>
          </div>
        </div>
      </div>`;
  };

  const teamBlock = team ? `
    <div class="mb-md">
      <p class="text-label-sm text-secondary mb-2 flex items-center gap-1 px-1">
        <span class="material-symbols-outlined text-[14px] text-primary">hub</span>Team
        <span class="text-[10px] text-secondary opacity-70">（Mission 唯一主协同单元）</span>
      </p>
      ${renderRow(team, 0, 1, { noConnector: true })}
    </div>` : '';

  const agentsList = individualAgents.map((a, i) => renderRow(a, i, individualAgents.length)).join('');
  const agentsBlock = individualAgents.length ? `
    <div>
      <p class="text-label-sm text-secondary mb-2 flex items-center gap-1 px-1">
        <span class="material-symbols-outlined text-[14px]">smart_toy</span>Agents
        <span class="text-[10px] text-secondary opacity-70">（由 Team 按需调起执行）</span>
      </p>
      <div class="space-y-3">${agentsList}</div>
    </div>` : '';

  const selected = agents.find(a => a.id === selectedId);
  const detail = selected ? `
    <div class="px-md py-md border-t border-outline-variant bg-surface">
      <div class="flex items-center gap-2 mb-3">
        <span class="material-symbols-outlined text-secondary text-[18px]">${selected.icon}</span>
        <p class="font-label-md text-on-surface">${escapeHTML(selected.name)} · ${getAgentKindMeta(selected.kind).label}</p>
      </div>
      <div class="space-y-3">
        <div>
          <label class="text-label-sm text-secondary mb-1 block">模型</label>
          <select ${archived?'disabled':''} onchange="setQuickAgentModel('${m.id}','${selected.id}', this.value)"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary">
            ${MODEL_OPTIONS.map(model => `<option value="${model}" ${selected.model===model?'selected':''}>${model}</option>`).join('')}
          </select>
        </div>
        <button ${archived?'disabled':''} onclick="openAgentDetail('${m.id}','${selected.id}')"
          class="w-full px-3 py-2 rounded-lg border border-outline-variant bg-surface-container-lowest text-on-surface hover:border-primary/40 hover:bg-surface-container text-label-md flex items-center justify-center gap-1 disabled:opacity-50">
          <span class="material-symbols-outlined text-[16px]">open_in_new</span>前往详情
        </button>
      </div>
    </div>` : '';

  return `
    <div class="p-md">
      <div class="flex items-center justify-between mb-md">
        <p class="font-label-md text-on-surface">Team</p>
        <button ${archived?'disabled':''} onclick="openModalAddAgent('${m.id}')"
          class="text-label-md text-primary font-bold flex items-center gap-1 hover:underline disabled:opacity-50">
          <span class="material-symbols-outlined text-[14px]">add</span>添加 Agent
        </button>
      </div>

      ${teamBlock}
      ${agentsBlock}

      ${!agents.length ? `
        <div class="text-center text-secondary p-lg border border-dashed border-outline-variant rounded-lg">
          <span class="material-symbols-outlined text-[36px] opacity-40 mb-2 block">groups</span>
          <p>还没有 Agent。点击右上角“添加 Agent”开始组建团队。</p>
        </div>` : ''}

      <p class="mt-md text-[11px] text-secondary leading-relaxed px-1 flex items-start gap-1">
        <span class="material-symbols-outlined text-[13px] mt-[1px]">info</span>
        <span>Mission 中最多只有 1 个 Team；当新增第 2 个角色时，首个角色会自动升级为 Team，后续新增角色默认为 Agent。类型在创建时确定，不可直接切换。</span>
      </p>
    </div>
    ${detail}`;
}

function setQuickAgentModel(missionId, agentId, model) {
  const m = state.missions.find(x => x.id === missionId);
  const a = m && m.squad.agents.find(x => x.id === agentId);
  if (!a) return;
  ensureAgentSchema(a);
  a.model = model;
  a.updatedAt = Date.now();
  if (state.detail && state.detail.type === 'agent' && state.detail.agentId === agentId && state.detail.draft) {
    state.detail.draft.model = model;
  }
  showToast(`已切换 ${a.name} 的模型`, 'success');
  render();
}

function renderMissionToolsTab(m, archived) {
  ensureMissionSchema(m);
  const sub = state.missionToolsSub || 'skill';
  const subTabs = `
    <div class="inline-flex items-center gap-1 p-0.5 bg-surface-container rounded-md border border-outline-variant text-label-sm">
      <button onclick="state.missionToolsSub='skill';render()"
        class="px-2.5 py-1 rounded ${sub==='skill' ? 'bg-surface text-primary font-bold' : 'text-secondary'}">
        Skill
      </button>
      <button onclick="state.missionToolsSub='mcp';render()"
        class="px-2.5 py-1 rounded flex items-center gap-1 ${sub==='mcp' ? 'bg-surface text-primary font-bold' : 'text-secondary'}">
        MCP <span class="text-[10px] opacity-70">${(state.mcpServers||[]).length}</span>
      </button>
    </div>`;

  if (sub === 'mcp') return renderMissionMcpToolsList(m, archived, subTabs);
  return renderMissionSkillsList(m, archived, subTabs);
}

function renderMissionSkillsList(m, archived, subTabs) {
  const all = getAllSkills();
  return `
    <div class="p-md">
      <div class="flex items-center justify-between mb-md gap-2">
        <p class="font-label-md text-on-surface">Mission 启用的技能 (${m.squad.enabledSkills.length}/${all.length})</p>
        ${subTabs}
      </div>
      <div class="space-y-2">
        ${all.map(s => {
          const on = m.squad.enabledSkills.includes(s.id);
          const isCustom = state.customSkills.find(x => x.id === s.id);
          return `
            <div class="flex items-center gap-3 p-2.5 bg-surface-container-lowest border border-outline-variant rounded-lg group">
              <div class="w-8 h-8 rounded bg-secondary-container flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined text-on-surface-variant text-[16px]">${s.icon}</span>
              </div>
              <div class="flex-1 min-w-0">
                <p class="font-label-md text-on-surface truncate flex items-center gap-1">
                  ${escapeHTML(s.name)}
                  ${isCustom ? '<span class="text-[9px] px-1 bg-primary-fixed text-on-primary-fixed-variant rounded">MCP</span>' : ''}
                </p>
                <p class="text-label-sm text-secondary truncate">${escapeHTML(s.desc)}</p>
              </div>
              <button onclick="openSkillDetailBySlug('${s.id}')" title="打开详情页"
                class="opacity-0 group-hover:opacity-100 text-secondary hover:text-primary transition-opacity">
                <span class="material-symbols-outlined text-[16px]">open_in_new</span>
              </button>
              <label class="relative inline-flex items-center cursor-pointer">
                <input ${archived?'disabled':''} type="checkbox" class="skill-switch sr-only" ${on?'checked':''} onchange="toggleSkill('${s.id}')"/>
                <span class="switch-bg w-9 h-5 bg-surface-container-highest rounded-full transition-colors relative">
                  <span class="switch-dot absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform"></span>
                </span>
              </label>
            </div>`;
        }).join('')}
      </div>
      <div class="mt-md pt-md border-t border-outline-variant flex items-center justify-between text-label-sm">
        <span class="text-secondary">想要更多？</span>
        <button onclick="openToolsPage()" class="text-primary font-bold hover:underline">前往 Tools 库 →</button>
      </div>
    </div>`;
}

function renderMissionMcpToolsList(m, archived, subTabs) {
  loadMcpServers();
  const tools = getAllMcpTools();
  const enabledSet = new Set(m.squad.enabledMcpTools || []);
  const empty = tools.length === 0;
  const groupByServer = {};
  tools.forEach(t => {
    if (!groupByServer[t.serverId]) groupByServer[t.serverId] = { name: t.serverName, list: [] };
    groupByServer[t.serverId].list.push(t);
  });

  const grouped = Object.entries(groupByServer).map(([sid, g]) => `
    <div class="mb-3">
      <p class="text-label-sm text-secondary mb-1.5 flex items-center gap-1.5 px-1">
        <span class="material-symbols-outlined text-[14px]">cable</span>${escapeHTML(g.name)}
      </p>
      <div class="space-y-2">
        ${g.list.map(t => {
          const on = enabledSet.has(t.key);
          return `
            <div class="flex items-center gap-3 p-2.5 bg-surface-container-lowest border border-outline-variant rounded-lg">
              <div class="w-8 h-8 rounded bg-primary-container flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined text-on-primary-container text-[14px]">webhook</span>
              </div>
              <div class="flex-1 min-w-0">
                <p class="font-label-md text-on-surface truncate font-mono">${escapeHTML(t.name)}</p>
                <p class="text-label-sm text-secondary truncate">${escapeHTML(t.desc || '—')}</p>
              </div>
              <label class="relative inline-flex items-center cursor-pointer">
                <input ${archived?'disabled':''} type="checkbox" class="skill-switch sr-only" ${on?'checked':''} onchange="toggleMissionMcpTool('${escapeAttr(t.key)}')"/>
                <span class="switch-bg w-9 h-5 bg-surface-container-highest rounded-full transition-colors relative">
                  <span class="switch-dot absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform"></span>
                </span>
              </label>
            </div>`;
        }).join('')}
      </div>
    </div>`).join('');

  return `
    <div class="p-md">
      <div class="flex items-center justify-between mb-md gap-2">
        <p class="font-label-md text-on-surface">MCP Tools (${enabledSet.size}/${tools.length})</p>
        ${subTabs}
      </div>
      ${empty ? `
        <div class="text-center text-secondary p-lg border border-dashed border-outline-variant rounded-lg">
          <span class="material-symbols-outlined text-[36px] opacity-40 mb-2 block">cable</span>
          <p class="text-body-md">还没有可用 MCP Tools</p>
          <button onclick="openToolsPage()" class="mt-2 text-primary font-bold hover:underline text-label-md">去 Tools 库接入 MCP Server →</button>
        </div>
      ` : grouped}
      ${!empty ? `
        <div class="mt-md pt-md border-t border-outline-variant flex items-center justify-between text-label-sm">
          <span class="text-secondary">想要更多？</span>
          <button onclick="openToolsPage()" class="text-primary font-bold hover:underline">管理 MCP Server →</button>
        </div>
      ` : ''}
    </div>`;
}

function toggleMissionMcpTool(key) {
  const m = getMission(); if (!m) return;
  ensureMissionSchema(m);
  const i = m.squad.enabledMcpTools.indexOf(key);
  if (i >= 0) m.squad.enabledMcpTools.splice(i, 1);
  else m.squad.enabledMcpTools.push(key);
  render();
}

function renderSkillsTab(m, archived) {
  const all = getAllSkills();
  return `
    <div class="p-md">
      <div class="flex items-center justify-between mb-md">
        <p class="font-label-md text-on-surface">Mission 启用的技能 (${m.squad.enabledSkills.length}/${all.length})</p>
        <button ${archived?'disabled':''} onclick="openMCPModal()" class="text-label-md text-primary font-bold flex items-center gap-1 hover:underline disabled:opacity-50">
          <span class="material-symbols-outlined text-[14px]">cable</span>接入 MCP
        </button>
      </div>
      <div class="space-y-2">
        ${all.map(s => {
          const on = m.squad.enabledSkills.includes(s.id);
          const isCustom = state.customSkills.find(x => x.id === s.id);
          return `
            <div class="flex items-center gap-3 p-2.5 bg-surface-container-lowest border border-outline-variant rounded-lg group">
              <div class="w-8 h-8 rounded bg-secondary-container flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined text-on-surface-variant text-[16px]">${s.icon}</span>
              </div>
              <div class="flex-1 min-w-0">
                <p class="font-label-md text-on-surface truncate flex items-center gap-1">
                  ${escapeHTML(s.name)}
                  ${isCustom ? '<span class="text-[9px] px-1 bg-primary-fixed text-on-primary-fixed-variant rounded">MCP</span>' : ''}
                </p>
                <p class="text-label-sm text-secondary truncate">${escapeHTML(s.desc)}</p>
              </div>
              <button onclick="openSkillDetailBySlug('${s.id}')" title="打开详情页"
                class="opacity-0 group-hover:opacity-100 text-secondary hover:text-primary transition-opacity">
                <span class="material-symbols-outlined text-[16px]">open_in_new</span>
              </button>
              <label class="relative inline-flex items-center cursor-pointer">
                <input ${archived?'disabled':''} type="checkbox" class="skill-switch sr-only" ${on?'checked':''} onchange="toggleSkill('${s.id}')"/>
                <span class="switch-bg w-9 h-5 bg-surface-container-highest rounded-full transition-colors relative">
                  <span class="switch-dot absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform"></span>
                </span>
              </label>
            </div>`;
        }).join('')}
      </div>
    </div>`;
}

function renderSettingsTab(m, archived) {
  return `
    <div class="p-md space-y-md">
      <div>
        <p class="text-label-md text-secondary mb-1">Mission 名称</p>
        <input ${archived?'disabled':''} class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0" value="${escapeHTML(m.name)}"/>
      </div>
      <div>
        <p class="text-label-md text-secondary mb-1">描述</p>
        <textarea ${archived?'disabled':''} rows="3" class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 resize-none">${escapeHTML(m.description)}</textarea>
      </div>
      <div class="bg-surface-container-lowest border border-outline-variant rounded-lg p-3">
        <p class="font-label-md text-on-surface mb-1 flex items-center gap-2">
          <span class="material-symbols-outlined text-secondary text-[16px]">switch_account</span>Coordinator 模式
        </p>
        <p class="text-label-sm text-secondary mb-2">分派任务 + 解析自然语言编辑指令</p>
        <div class="flex gap-2">
          <button class="flex-1 py-1.5 rounded border border-primary bg-primary text-white text-label-md">分派</button>
          <button class="flex-1 py-1.5 rounded border border-outline-variant text-secondary text-label-md hover:border-primary">编辑</button>
        </div>
      </div>
      ${archived ? '' : `
        <button class="w-full py-2 bg-error-container text-on-error-container border border-error/30 rounded-lg text-label-md hover:bg-error hover:text-white transition-colors">
          归档此 Mission
        </button>`}
    </div>`;
}

/* ----- Quick Run save card (deprecated · 保留以兼容历史调用，已不在 renderQuickRun 中使用) ----- */
function renderSaveAsMissionCard() {
  return `
    <div class="bg-primary-fixed/40 border border-primary/30 rounded-xl p-md mx-auto max-w-lg text-center">
      <p class="font-label-md text-on-primary-fixed-variant mb-1">这段对话很有用？</p>
      <p class="text-label-md text-secondary mb-3">保存为 Mission，下次直接复用班底配置。</p>
      <div class="flex gap-2 justify-center">
        <button onclick="state.quickRun.promptedSave=true; render()" class="px-3 py-1.5 text-secondary text-label-md hover:underline">稍后</button>
        <button onclick="openSaveAsMissionModal()" class="px-3 py-1.5 bg-primary text-white rounded-lg text-label-md hover:opacity-90 flex items-center gap-1">
          <span class="material-symbols-outlined text-[14px]">bookmark_add</span>保存为 Mission
        </button>
      </div>
    </div>`;
}

/* ----- Agent / Skill actions ----- */
function selectAgent(id) { state.selectedAgentId = id; render(); }
function toggleSkill(id) {
  const m = getMission();
  const i = m.squad.enabledSkills.indexOf(id);
  if (i>=0) m.squad.enabledSkills.splice(i,1);
  else m.squad.enabledSkills.push(id);
}
function addAgent() {
  const m = getMission();
  ensureMissionSchema && ensureMissionSchema(m);
  const cur = m.squad.agents || [];
  const hasTeam = cur.some(a => a.kind === 'team');

  if (cur.length === 0) {
    const a = makeAgent(
      'New Team',
      '描述这个 Team 的职责（主协同单元，直接面向用户拆解任务）。',
      'hub',
      '你是 Mission 的 Team 负责人，负责理解用户目标、拆解任务、调度合适的 Agent，并整合最终输出。',
      [],
      'team'
    );
    m.squad.agents.push(a);
    showToast('已新增 Team，请在右侧完成配置', 'success');
    render();
    return;
  }

  if (cur.length === 1 && !hasTeam) {
    cur[0].kind = 'team';
    cur[0].icon = cur[0].icon || 'hub';
    cur[0].systemPrompt = cur[0].systemPrompt || '你是 Mission 的 Team 负责人，负责理解用户目标、拆解任务、调度合适的 Agent，并整合最终输出。';
  }

  const a = makeAgent(
    'New Agent',
    '在这里描述这个 Agent 的职责（由 Team 调起执行的具体子任务）。',
    'smart_toy',
    '你是一名 Agent，专注完成 Team 委派的具体任务。',
    [],
    'agent'
  );
  m.squad.agents.push(a);
  const team = cur.find(x => x.kind === 'team') || m.squad.agents.find(x => x.kind === 'team');
  if (team) {
    team.teamMemberIds = team.teamMemberIds || [];
    if (!team.teamMemberIds.includes(a.id)) team.teamMemberIds.push(a.id);
  }
  showToast('已新增 Agent，请在右侧完成配置', 'success');
  render();
}