function renderSettingsPage() {
  const sections = [
    { icon:'psychology',    title:'记忆管理',   desc:'查看、搜索和管理 AI 学到的所有记忆', active:true },
    { icon:'palette',       title:'外观',       desc:'主题、字号、密度调整' },
    { icon:'tune',          title:'默认模型',   desc:'统一设置 Agent 的默认 LLM 提供方' },
    { icon:'cable',         title:'连接器',     desc:'管理已接入的 MCP / API / 凭证' },
    { icon:'security',      title:'隐私与权限', desc:'Workspace 成员、角色与可见范围' },
    { icon:'notifications', title:'通知',       desc:'运行完成、Agent 变更、系统提醒' },
  ];

  const memorySection = `
    <div class="mb-md bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
      <div class="px-md py-md border-b border-outline-variant bg-surface-container">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-[20px] text-primary">psychology</span>
          <span class="font-label-lg text-on-surface">全局记忆设置</span>
        </div>
      </div>
      <div class="px-md py-md space-y-md">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-label-md text-on-surface font-medium">自动提取事实</p>
            <p class="text-label-sm text-secondary">每次对话后 LLM 自动提取偏好、决策和关键事实</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" checked onchange="showToast('记忆提取: ' + (this.checked?'已开启':'已关闭'), 'info')" class="sr-only peer"/>
            <div class="w-9 h-5 bg-outline-variant peer-checked:bg-primary rounded-full peer after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4"></div>
          </label>
        </div>
        <div class="flex items-center justify-between">
          <div>
            <p class="text-label-md text-on-surface font-medium">语义检索增强</p>
            <p class="text-label-sm text-secondary">回答前自动搜索相关历史记忆并注入上下文</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" checked onchange="showToast('语义检索: ' + (this.checked?'已开启':'已关闭'), 'info')" class="sr-only peer"/>
            <div class="w-9 h-5 bg-outline-variant peer-checked:bg-primary rounded-full peer after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4"></div>
          </label>
        </div>
        <div class="flex items-center justify-between">
          <div>
            <p class="text-label-md text-on-surface font-medium">记忆衰减</p>
            <p class="text-label-sm text-secondary">旧记忆随时间自动降低权重，长期不用的自动归档</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" checked onchange="showToast('记忆衰减: ' + (this.checked?'已开启':'已关闭'), 'info')" class="sr-only peer"/>
            <div class="w-9 h-5 bg-outline-variant peer-checked:bg-primary rounded-full peer after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4"></div>
          </label>
        </div>
        <div class="flex items-center gap-2 pt-2 border-t border-outline-variant">
          <button onclick="showToast('记忆数据导出功能即将上线','info')" class="px-3 py-1.5 rounded-lg border border-outline-variant text-label-md text-secondary hover:bg-surface-container">
            <span class="material-symbols-outlined text-[16px] align-middle mr-1">download</span>导出所有记忆
          </button>
          <button onclick="if(confirm('确定要清除所有记忆吗？此操作不可撤销。')) showToast('记忆清除功能即将上线','info')" class="px-3 py-1.5 rounded-lg border border-outline-variant text-label-md text-red-600 hover:bg-red-50">
            <span class="material-symbols-outlined text-[16px] align-middle mr-1">delete_forever</span>清除所有记忆
          </button>
        </div>
      </div>
    </div>`;

  return `
    <div class="flex-1 overflow-y-auto bg-background">
      <section class="px-xl pt-xl pb-md">
        <h2 class="text-headline-lg text-on-surface">Settings</h2>
        <p class="text-body-md text-secondary mt-1">Workspace 全局配置。</p>
      </section>
      <section class="px-xl pb-xl space-y-md max-w-3xl">
        ${memorySection}
        ${sections.filter(s => !s.active).map(s => `
          <div class="bg-surface-container-lowest border border-outline-variant rounded-xl px-md py-md flex items-center gap-md hover:border-primary/40 transition-colors cursor-pointer">
            <div class="w-10 h-10 rounded-lg bg-secondary-container flex items-center justify-center">
              <span class="material-symbols-outlined text-on-surface-variant text-[18px]">${s.icon}</span>
            </div>
            <div class="flex-1">
              <p class="font-label-md text-on-surface">${escapeHTML(s.title)}</p>
              <p class="text-label-md text-secondary">${escapeHTML(s.desc)}</p>
            </div>
            <span class="material-symbols-outlined text-secondary text-[18px]">chevron_right</span>
          </div>`).join('')}
      </section>
    </div>`;
}

/* ===================== Quick Run ===================== */
function renderQuickRun() {
  const qr = state.quickRun;
  const empty = !qr.conversation.length;
  const bubbles = qr.conversation.map((m,i) => renderBubble(m,i)).join('');
  // 不再在第 N 轮自动插入提示卡 —— 用户随时可点顶栏「保存为 Mission」按钮
  const saveCard = '';
  const canSave = qr.conversation.length > 0;

  return `
    <div class="flex-1 flex overflow-hidden bg-surface">
      <div class="flex-1 flex flex-col min-w-0">
        <div class="px-lg py-md border-b border-outline-variant bg-primary-fixed/20 flex items-start gap-2">
          <span class="material-symbols-outlined text-primary text-[18px] mt-0.5">bolt</span>
          <div class="flex-1 text-label-md">
            <p class="font-bold text-on-primary-fixed-variant">Quick Run · 临时工作空间</p>
            <p class="text-secondary mt-0.5">不属于任何 Mission。所有对话都会保留，可随时保存为 Mission。</p>
          </div>
          <div class="flex items-center gap-2 self-center">
            <span class="text-label-sm text-secondary">${qr.turns} 轮</span>
            <button onclick="manualSaveQuickRun()"
                    ${canSave ? '' : 'disabled'}
                    class="flex items-center gap-1 px-2.5 py-1 rounded-md text-label-sm bg-primary text-white hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
                    title="将当前 Quick Run 保存为 Mission，沉淀班底配置">
              <span class="material-symbols-outlined text-[14px]">bookmark_add</span>保存为 Mission
            </button>
          </div>
        </div>

        ${empty ? `
          <div class="flex-1 flex flex-col items-center justify-center text-secondary px-lg">
            <div class="w-16 h-16 rounded-full bg-primary-fixed flex items-center justify-center mb-md">
              <span class="material-symbols-outlined text-on-primary-fixed-variant text-[28px]">bolt</span>
            </div>
            <p class="text-headline-md text-on-surface mb-2">写下你想做的事</p>
            <p class="text-body-md text-center max-w-md">Quick Run 适合一次性任务、临时探索。觉得有价值时随时保存为 Mission。</p>
          </div>` : `
          <div id="chat-stream" class="flex-1 overflow-y-auto px-lg py-md space-y-md">
            ${bubbles}${saveCard}
          </div>`}

        <div class="border-t border-outline-variant px-lg py-md bg-surface">
          <div class="bg-surface-container-lowest border border-outline-variant focus-within:border-primary rounded-xl px-md py-2.5 transition-colors">
            <textarea id="chat-input" rows="2"
              onkeydown="onChatInputKeydown(event)"
              placeholder="例如：帮我对比 Notion 与 Linear 的定价策略..."
              class="w-full bg-transparent border-0 focus:ring-0 resize-none text-body-md p-0 placeholder:text-secondary"></textarea>
            <div class="flex items-center justify-between pt-2 border-t border-outline-variant/60 mt-2">
              <span class="text-label-sm text-secondary">Quick Run 无 Agent 选择，由系统直接处理</span>
              <button onclick="sendChat()" class="bg-primary text-white px-3 py-1.5 rounded-lg flex items-center gap-1.5 hover:opacity-90 text-label-md">
                发送<span class="material-symbols-outlined text-[16px]">send</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>`;
}

/* ===================== Memory Inspector ===================== */
function renderMemoryPage() {
  if (!state._memory) state._memory = { entries:[], total:0, page:1, filter:'all', search:'', loading:false };
  const m = state._memory;

  // 首次加载
  if (!m.loaded) { loadMemories(); m.loaded = true; }

  const typeFilters = [
    { id:'all',       label:'全部',   icon:'psychology' },
    { id:'fact',      label:'事实',   icon:'info' },
    { id:'preference',label:'偏好',   icon:'star' },
    { id:'decision',  label:'决策',   icon:'check_circle' },
    { id:'user_trait',label:'特征',   icon:'person' },
  ];

  const entries = m.entries || [];
  const filtered = m.filter === 'all'
    ? entries
    : entries.filter(e => e.memory_type === m.filter);

  return `
    <div class="flex-1 overflow-y-auto bg-background">
      <section class="px-xl pt-xl pb-md">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-headline-lg text-on-surface flex items-center gap-2">
              <span class="material-symbols-outlined text-[28px] text-primary">psychology</span>
              记忆面板
            </h2>
            <p class="text-body-md text-secondary mt-1">
              AI 从你的对话中学到的所有知识。共 <b>${m.total}</b> 条记忆。
            </p>
          </div>
          <button onclick="loadMemories(); showToast('记忆已刷新','success')"
            class="px-3 py-1.5 rounded-lg border border-outline-variant text-label-md text-secondary hover:bg-surface-container flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">refresh</span>刷新
          </button>
        </div>
      </section>

      <!-- 搜索 + 过滤 -->
      <section class="px-xl pb-md">
        <div class="flex items-center gap-3 flex-wrap">
          <div class="flex-1 min-w-[200px] max-w-[400px] relative">
            <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-secondary">search</span>
            <input type="text" value="${escapeHTML(m.search||'')}" placeholder="搜索记忆..."
              oninput="state._memory.search=this.value; render()"
              class="w-full pl-9 pr-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
          </div>
          <div class="flex gap-1">
            ${typeFilters.map(t => `
              <button onclick="state._memory.filter='${t.id}'; render()"
                class="px-3 py-1.5 rounded-full text-label-md transition-colors
                       ${m.filter===t.id ? 'bg-primary text-white' : 'bg-surface-container-lowest border border-outline-variant text-on-surface hover:bg-surface-container'}">
                ${t.label}
              </button>`).join('')}
          </div>
        </div>
      </section>

      <!-- 统计卡片 -->
      <section class="px-xl pb-md">
        <div class="grid grid-cols-4 gap-3">
          ${typeFilters.filter(t=>t.id!=='all').map(t => {
            const count = entries.filter(e => e.memory_type === t.id).length;
            return `
              <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-3 text-center">
                <span class="material-symbols-outlined text-[20px] text-secondary">${t.icon}</span>
                <p class="text-headline-sm text-on-surface mt-1">${count}</p>
                <p class="text-label-sm text-secondary">${t.label}</p>
              </div>`;
          }).join('')}
        </div>
      </section>

      <!-- 记忆列表 -->
      <section class="px-xl pb-xl">
        <div class="space-y-2 max-w-4xl">
          ${m.loading ? `
            <div class="text-center py-lg text-secondary">
              <span class="material-symbols-outlined animate-spin text-[32px]">progress_activity</span>
              <p class="mt-2">加载中...</p>
            </div>` : filtered.length === 0 ? `
            <div class="text-center py-xl text-secondary bg-surface-container-lowest border border-outline-variant rounded-xl">
              <span class="material-symbols-outlined text-[48px] opacity-30">psychology</span>
              <p class="text-body-md mt-2">${m.search ? '没有匹配的记忆' : '还没有任何记忆。开启对话后，AI 会自动提取关键信息。'}</p>
            </div>` : filtered.map(e => {
              const typeLabel = {fact:'事实', preference:'偏好', decision:'决策', user_trait:'特征'}[e.memory_type]||e.memory_type;
              const typeColor = {fact:'#3b82f6', preference:'#f59e0b', decision:'#10b981', user_trait:'#8b5cf6'}[e.memory_type]||'#6b7280';
              const score = (e.effective_score||e.importance).toFixed(2);
              const date = e.created_at ? new Date(e.created_at).toLocaleDateString('zh-CN') : '';
              return `
                <div class="bg-surface-container-lowest border border-outline-variant rounded-xl px-md py-md flex items-start gap-3 group hover:border-primary/30 transition-colors">
                  <span class="material-symbols-outlined text-[20px] mt-0.5" style="color:${typeColor}">${{fact:'info',preference:'star',decision:'check_circle',user_trait:'person'}[e.memory_type]||'psychology'}</span>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-1">
                      <span class="text-[10px] px-1.5 py-0.5 rounded-full font-medium text-white" style="background:${typeColor}">${typeLabel}</span>
                      <span class="text-label-sm text-secondary">${date}</span>
                      <span class="text-label-sm text-secondary">重要性 ${(e.importance*100).toFixed(0)}%</span>
                      ${e.score ? `<span class="text-label-sm text-secondary">相似度 ${(e.score*100).toFixed(0)}%</span>` : ''}
                    </div>
                    <p class="text-body-md text-on-surface">${escapeHTML(e.content)}</p>
                    ${e.confidence ? `<p class="text-label-sm text-secondary mt-1">置信度 ${(e.confidence*100).toFixed(0)}% · 检索 ${e.access_count||0} 次 · 衰减 ${(e.decay_factor||1).toFixed(2)}</p>` : ''}
                  </div>
                  <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                    ${e.id ? `
                      <button onclick="boostMemory(${e.id})" class="p-1.5 rounded hover:bg-surface-container text-secondary hover:text-primary" title="提升记忆">
                        <span class="material-symbols-outlined text-[16px]">trending_up</span>
                      </button>
                      <button onclick="deleteMemory(${e.id})" class="p-1.5 rounded hover:bg-red-50 text-secondary hover:text-red-600" title="删除">
                        <span class="material-symbols-outlined text-[16px]">delete</span>
                      </button>` : ''}
                  </div>
                </div>`;
            }).join('')
          }
        </div>

        ${m.total > 20 ? `
          <div class="flex items-center justify-center gap-3 mt-md">
            <button ${m.page<=1?'disabled':''} onclick="state._memory.page--; loadMemories();"
              class="px-3 py-1.5 rounded-lg border border-outline-variant text-label-md ${m.page<=1?'opacity-30':'hover:bg-surface-container'}">
              上一页
            </button>
            <span class="text-label-md text-secondary">第 ${m.page} 页 / 共 ${Math.ceil(m.total/20)} 页</span>
            <button ${m.page>=Math.ceil(m.total/20)?'disabled':''} onclick="state._memory.page++; loadMemories();"
              class="px-3 py-1.5 rounded-lg border border-outline-variant text-label-md ${m.page>=Math.ceil(m.total/20)?'opacity-30':'hover:bg-surface-container'}">
              下一页
            </button>
          </div>` : ''}
      </section>
    </div>`;
}

async function loadMemories() {
  const m = state._memory || {};
  m.loading = true;
  try {
    const params = new URLSearchParams({
      page: m.page||1,
      page_size: 20,
      memory_type: m.filter !== 'all' ? m.filter : '',
      sort_by: 'importance'
    });
    const res = await api(`/memory/entries?${params.toString()}`);
    m.entries = res.entries || [];
    m.total = res.total || 0;
  } catch (e) {
    console.warn('加载记忆失败:', e);
    showToast('记忆加载失败，请确认已开启 MEMORY_ENABLED', 'error');
  }
  m.loading = false;
  render();
}

async function boostMemory(id) {
  try {
    await api(`/memory/entries/${id}/boost`, { method:'POST' });
    showToast('记忆已提升', 'success');
    loadMemories();
  } catch (e) {
    showToast('操作失败', 'error');
  }
}

async function deleteMemory(id) {
  if (!confirm('确定删除这条记忆吗？')) return;
  try {
    await api(`/memory/entries/${id}`, { method:'DELETE' });
    showToast('记忆已删除', 'success');
    loadMemories();
  } catch (e) {
    showToast('删除失败', 'error');
  }
}