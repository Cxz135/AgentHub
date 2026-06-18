/* ============================================================
   Skill 详情页
============================================================ */

async function openSkillDetail(skillId) {
  // 先尝试从 state 中找
  let s = (state.skills.mine || []).find(x => x.id === skillId)
       || (state.skills.market || []).find(x => x.id === skillId);
  if (!s) {
    try { const r = await api('/skills/' + skillId); s = r.skill; }
    catch (e) { showToast('Skill 加载失败：' + (e.message||e)); return; }
  }
  state.detail = {
    type: 'skill',
    skillId: s.id,
    snapshot: s,                   // 服务器最新数据
    tab: 'overview',
    draft: cloneSkillForDraft(s),
    dirty: false,
    versionDropdownOpen: false,
  };
  state.view = 'skill_detail';
  render();
}

function openSkillDetailBySlug(slug) {
  const s = (state.skills.mine || []).concat(state.skills.market || []).find(x => x.slug === slug);
  if (s) return openSkillDetail(s.id);
  // 内置 skill 暂无详情页（无 server id），退化为提示
  showToast('该 Skill 是内置只读项，暂无详情页');
}

function cloneSkillForDraft(s) {
  return {
    name: s.name, slug: s.slug, icon: s.icon || 'extension',
    description: s.description || '',
    code: s.code || '', readme: s.readme || '',
    category: s.category || 'custom',
  };
}

function renderSkillDetailPage() {
  const d = state.detail;
  if (!d || d.type !== 'skill') {
    return `<div class="flex-1 flex items-center justify-center text-secondary">Skill 不存在 <button class="ml-2 text-primary underline" onclick="closeDetail()">返回</button></div>`;
  }
  const s = d.snapshot;
  const draft = d.draft;
  const tab = d.tab;
  const dirty = d.dirty;
  const isMine = !!s.isMine;
  const isReadonly = !isMine;

  // 使用情况：哪些 mission/agent 启用了这个 skill（按 slug）
  const usages = [];
  state.missions.forEach(m => {
    m.squad.agents.forEach(a => {
      if ((a.skills||[]).includes(s.slug)) usages.push({ mission: m, agent: a });
    });
  });

  const versions = s.versions || [];

  const tabs = [
    { id:'overview', icon:'dashboard',     label:'概览' },
    { id:'prompt',   icon:'edit_note',     label:'Prompt 模板' },
    { id:'readme',   icon:'description',   label:'文档' },
    { id:'usage',    icon:'task',          label:`使用情况 (${usages.length})` },
    { id:'versions', icon:'history',       label:`版本 (${versions.length})` },
  ];

  let body = '';
  if (tab === 'overview') {
    body = `
      <div class="space-y-md max-w-2xl">
        ${isReadonly ? `
          <div class="bg-amber-50 border border-amber-300 text-amber-800 px-3 py-2 rounded-lg text-label-md flex items-start gap-2">
            <span class="material-symbols-outlined text-[18px] mt-0.5">info</span>
            <div>这是 <strong>${escapeHTML(s.authorName||'system')}</strong> 创建的 Skill，你只能查看。修改并保存会自动为你创建一个副本到「我的 Skill」。</div>
          </div>` : ''}
        <div>
          <label class="text-label-md text-secondary mb-1 block">slug（唯一标识）</label>
          <input value="${escapeHTML(draft.slug)}" disabled
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md text-secondary opacity-70"/>
          ${s.parentId ? `<p class="text-[11px] text-secondary mt-1">Forked from skill #${s.parentId}</p>` : ''}
        </div>
        <div>
          <label class="text-label-md text-secondary mb-1 block">名称</label>
          <input value="${escapeHTML(draft.name)}" oninput="state.detail.draft.name=this.value; markDetailDirty()"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
        </div>
        <div>
          <label class="text-label-md text-secondary mb-1 block">描述</label>
          <input value="${escapeHTML(draft.description)}" oninput="state.detail.draft.description=this.value; markDetailDirty()"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
        </div>
        <div>
          <label class="text-label-md text-secondary mb-1 block">分类</label>
          <div class="flex gap-2">
            ${SKILL_CATEGORIES.map(c => `
              <button onclick="state.detail.draft.category='${c.id}'; markDetailDirty(); render()"
                class="px-3 py-1.5 rounded-lg text-label-md border transition-colors
                       ${draft.category===c.id ? 'border-primary bg-primary-fixed/40 text-primary' : 'border-outline-variant text-on-surface-variant hover:bg-surface-container-low'}">
                ${c.name}
              </button>`).join('')}
          </div>
        </div>
        <div>
          <label class="text-label-md text-secondary mb-1 block">图标</label>
          <div class="grid grid-cols-12 gap-2">
            ${SKILL_ICON_OPTIONS.map(i => `
              <button onclick="state.detail.draft.icon='${i}'; markDetailDirty(); render()"
                class="w-9 h-9 rounded-lg border flex items-center justify-center
                       ${draft.icon===i ? 'border-primary bg-primary-fixed/40' : 'border-outline-variant bg-surface-container-lowest hover:border-primary/40'}">
                <span class="material-symbols-outlined text-[18px] ${draft.icon===i?'text-primary':'text-on-surface-variant'}">${i}</span>
              </button>`).join('')}
          </div>
        </div>
        <div class="flex flex-wrap gap-3 pt-2 text-label-md text-secondary border-t border-outline-variant">
          <span>作者：<strong class="text-on-surface">${escapeHTML(s.authorName||'-')}</strong></span>
          <span>状态：${s.isPublished?'<span class="text-green-700 font-medium">已发布</span>':'<span class="text-amber-700">私有</span>'}</span>
          <span>安装数：${s.installCount||0}</span>
          <span>更新于：${escapeHTML(s.updatedAt||'-')}</span>
        </div>
      </div>`;
  } else if (tab === 'prompt') {
    body = `
      <div class="max-w-3xl">
        <label class="text-label-md text-secondary mb-1 block">Prompt 模板 / 实现伪代码</label>
        <textarea rows="16" oninput="state.detail.draft.code=this.value; markDetailDirty()"
          class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg font-mono text-[12px] focus:outline-none focus:border-primary"
          placeholder="// 模板">${escapeHTML(draft.code)}</textarea>
        <p class="text-[11px] text-secondary mt-1">${isReadonly?'修改并保存将自动 fork 为你的副本。':'保存时会自动写入版本快照，可在「版本」Tab 中回滚。'}</p>
      </div>`;
  } else if (tab === 'readme') {
    body = `
      <div class="grid grid-cols-2 gap-md max-w-5xl">
        <div>
          <label class="text-label-md text-secondary mb-1 block">Markdown 编辑</label>
          <textarea rows="20" oninput="state.detail.draft.readme=this.value; markDetailDirty(); document.getElementById('readme-preview').innerHTML=renderMarkdown(this.value)"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg font-mono text-[12px] focus:outline-none focus:border-primary"
            placeholder="# Skill 简介">${escapeHTML(draft.readme)}</textarea>
        </div>
        <div>
          <label class="text-label-md text-secondary mb-1 block">实时预览</label>
          <div id="readme-preview" class="px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg min-h-[460px] text-body-md">${renderMarkdown(draft.readme)}</div>
        </div>
      </div>`;
  } else if (tab === 'usage') {
    body = usages.length ? `
      <div class="grid grid-cols-2 gap-md max-w-4xl">
        ${usages.map(u => `
          <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-md hover:border-primary/40 transition-colors cursor-pointer"
               onclick="guardLeaveDetail(()=>{state.missionId='${u.mission.id}'; openMission('${u.mission.id}');})">
            <div class="flex items-center gap-3 mb-2">
              <div class="w-10 h-10 rounded-lg bg-secondary-container flex items-center justify-center">
                <span class="material-symbols-outlined text-on-surface-variant">${escapeHTML(u.mission.icon||'task')}</span>
              </div>
              <div class="min-w-0">
                <p class="font-label-md text-on-surface truncate">${escapeHTML(u.mission.name)}</p>
                <p class="text-label-sm text-secondary truncate">由 Agent <strong>${escapeHTML(u.agent.name)}</strong> 启用</p>
              </div>
            </div>
          </div>`).join('')}
      </div>
    ` : `
      <div class="text-center text-secondary p-xl border border-dashed border-outline-variant rounded-xl max-w-2xl">
        <span class="material-symbols-outlined text-[40px] opacity-40 mb-2 block">task</span>
        <p>暂无 Mission 中的 Agent 启用此 Skill。</p>
      </div>`;
  } else if (tab === 'versions') {
    body = versions.length ? `
      <div class="space-y-2 max-w-3xl">
        ${versions.map((v,i) => `
          <div class="bg-surface-container-lowest border border-outline-variant rounded-lg p-3 flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="text-label-md text-on-surface">v${i+1} · ${escapeHTML(v.ts||'-')}</p>
              <p class="text-[11px] text-secondary">${escapeHTML(v.note||'手动保存')}</p>
              <p class="text-[11px] text-secondary line-clamp-2 mt-1">${escapeHTML((v.snapshot && v.snapshot.code || '').slice(0,80))}…</p>
            </div>
            <div class="flex gap-1 shrink-0">
              <button onclick="showSkillVersionDiff(${i})" class="px-2 py-1 text-[12px] rounded border border-outline-variant text-on-surface-variant hover:bg-surface-container-low">查看 diff</button>
              ${isMine ? `<button onclick="rollbackSkillVersion(${i})" class="px-2 py-1 text-[12px] rounded bg-primary text-white hover:opacity-90">回滚</button>` : ''}
            </div>
          </div>`).join('')}
      </div>
    ` : `
      <div class="text-center text-secondary p-xl border border-dashed border-outline-variant rounded-xl max-w-2xl">
        <span class="material-symbols-outlined text-[40px] opacity-40 mb-2 block">history</span>
        <p>还没有历史版本，编辑保存后会出现快照。</p>
      </div>`;
  }

  return `
    <div class="flex-1 overflow-y-auto bg-background">
      <header class="px-xl pt-lg pb-md border-b border-outline-variant flex items-center justify-between gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <button onclick="closeDetail()" class="text-secondary hover:text-primary flex items-center gap-1 text-label-md">
            <span class="material-symbols-outlined text-[18px]">arrow_back</span>Skills
          </button>
          <span class="text-secondary">/</span>
          <div class="w-9 h-9 rounded-lg bg-primary-fixed/40 flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined text-primary">${escapeHTML(draft.icon||'extension')}</span>
          </div>
          <div class="min-w-0">
            <p class="font-headline-md text-title-lg text-on-surface truncate flex items-center gap-2">${escapeHTML(draft.name||draft.slug)}<span id="detail-dirty-dot" class="${dirty?'':'hidden'} w-2 h-2 rounded-full bg-amber-500" title="有未保存改动"></span></p>
            <p class="text-label-md text-secondary truncate">@${escapeHTML(s.authorName||'-')} · ${(SKILL_CATEGORY_MAP[draft.category]||{name:''}).name} · ${versions.length} 版本${isReadonly?' · <span class="text-amber-700">只读</span>':''}</p>
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          ${isMine && !s.isPublished ? `<button onclick="publishSkill(${s.id})" class="px-3 py-1.5 rounded-lg text-label-md border border-outline-variant text-on-surface-variant hover:bg-surface-container-low flex items-center gap-1"><span class="material-symbols-outlined text-[16px]">publish</span>发布</button>` : ''}
          ${isMine && s.isPublished ? `<button onclick="unpublishSkill(${s.id})" class="px-3 py-1.5 rounded-lg text-label-md border border-outline-variant text-on-surface-variant hover:bg-surface-container-low">撤回</button>` : ''}
          <button id="detail-save-btn" onclick="commitSkillDetailSave()" ${dirty?'':'disabled'}
            class="px-4 py-1.5 rounded-lg text-label-md flex items-center gap-1
                   ${dirty?'bg-primary text-white hover:opacity-90':'bg-surface-container text-secondary cursor-not-allowed'}">
            <span class="material-symbols-outlined text-[16px]">save</span>${isReadonly?'另存为副本':'保存'}
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
        <section class="flex-1 px-xl py-lg min-w-0">${body}</section>
      </div>
    </div>`;
}

async function commitSkillDetailSave() {
  if (!state.user) { showToast('请先登录'); openAuthModal && openAuthModal('register'); return; }
  const d = state.detail;
  if (!d || d.type !== 'skill' || !d.dirty) return;
  const draft = d.draft;
  const s = d.snapshot;

  if (!s.isMine) {
    // Fork 流程
    if (!confirm(`这不是你创建的 Skill。\n保存将为你创建一个副本到「我的 Skill」。是否继续？`)) return;
    try {
      const r = await api('/skills/' + s.id + '/fork', {
        method: 'POST',
        body: JSON.stringify({
          name: draft.name, icon: draft.icon, description: draft.description,
          code: draft.code, readme: draft.readme, category: draft.category,
        }),
      });
      showToast(`已创建副本：${r.skill.slug}`, 'success');
      await loadSkills();
      // 跳到新副本详情
      d.dirty = false;
      openSkillDetail(r.skill.id);
    } catch (e) {
      showToast('Fork 失败：' + (e.message||e));
    }
    return;
  }

  // 我自己的 → PUT 直接更新（后端会写 versions）
  try {
    const r = await api('/skills/' + s.id, {
      method: 'PUT',
      body: JSON.stringify({
        name: draft.name, icon: draft.icon, description: draft.description,
        code: draft.code, readme: draft.readme, category: draft.category,
      }),
    });
    d.snapshot = r.skill;
    d.draft = cloneSkillForDraft(r.skill);
    d.dirty = false;
    await loadSkills();
    showToast('已保存（版本 ' + (r.skill.versions||[]).length + '）', 'success');
    render();
  } catch (e) {
    showToast('保存失败：' + (e.message||e));
  }
}

function showSkillVersionDiff(idx) {
  const d = state.detail; if (!d) return;
  const versions = d.snapshot.versions || [];
  if (!versions[idx]) return;
  const snap = versions[idx].snapshot;
  const cur = { name:d.snapshot.name, icon:d.snapshot.icon, description:d.snapshot.description, code:d.snapshot.code, readme:d.snapshot.readme, category:d.snapshot.category };
  showVersionDiffModal(snap, cur, idx, () => rollbackSkillVersion(idx));
}

async function rollbackSkillVersion(idx) {
  const d = state.detail; if (!d || !d.snapshot.isMine) return showToast('只能回滚自己创建的 Skill');
  if (!confirm(`确定回滚到 v${idx+1} ？当前内容会写入新的历史版本。`)) return;
  try {
    const r = await api('/skills/' + d.snapshot.id + '/rollback', {
      method:'POST',
      body: JSON.stringify({ versionIndex: idx }),
    });
    d.snapshot = r.skill;
    d.draft = cloneSkillForDraft(r.skill);
    d.dirty = false;
    closeVersionDiffModal();
    await loadSkills();
    showToast(`已回滚到 v${idx+1}`, 'success');
    render();
  } catch (e) {
    showToast('回滚失败：' + (e.message||e));
  }
}