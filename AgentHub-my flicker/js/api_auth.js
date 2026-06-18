/* ===================== Auth · 前后端集成 ===================== */
const API_BASE = 'http://localhost:8000/api';

async function api(path, init = {}) {
  const headers = Object.assign(
    { 'Content-Type': 'application/json' },
    init.headers || {}
  );
  const token = localStorage.getItem('agenthub_token');
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const res = await fetch(API_BASE + path, { ...init, headers });
  let data = null;
  try { data = await res.json(); } catch(e) {}
  if (!res.ok) {
    // 401 处理
    if (res.status === 401) {
      const hadToken = !!localStorage.getItem('agenthub_token');
      if (hadToken) {
        // 有 token 但失效 → 清除并提示
        localStorage.removeItem('agenthub_token');
        state.user = null;
        render();
        showToast('登录已过期，请重新登录', 'error');
        openAuthModal && openAuthModal('login');
        throw new Error('登录已过期，请重新登录');
      } else {
        // 未登录 → 直接弹注册/登录窗
        showToast('请先注册或登录后再继续', 'error');
        openAuthModal && openAuthModal('register');
        throw new Error('请先注册或登录');
      }
    }
    const msg = (data && (data.detail || data.error || data.message)) || ('HTTP ' + res.status);
    throw new Error(msg);
  }
  return data;
}

/* ===== Agent CRUD API ===== */
async function fetchCustomAgents() {
  try {
    const res = await api('/agents');
    state.customAgents = Array.isArray(res) ? res : [];
    render();
  } catch (e) {
    console.error('获取自定义Agent列表失败:', e);
    state.customAgents = [];
  }
}

async function createCustomAgentAPI(name, icon, systemPrompt, llmAdapter, tools) {
  const res = await api('/agents', {
    method: 'POST',
    body: JSON.stringify({ name, icon: icon || 'smart_toy', description: '', system_prompt: systemPrompt, llm_adapter: llmAdapter, tools: tools || [] })
  });
  await fetchCustomAgents();
  showToast(`自定义Agent "${name}" 创建成功`, 'success');
  return res;
}

async function deleteCustomAgentAPI(agentId, name) {
  if (!confirm(`确定删除自定义Agent "${name}"？此操作不可恢复。`)) return;
  try {
    await api(`/agents/${agentId}`, { method: 'DELETE' });
    showToast(`已删除 "${name}"`, 'success');
    await fetchCustomAgents();
  } catch (e) {
    showToast(`删除失败: ${e.message}`, 'error');
  }
}

async function updateCustomAgentAPI(agentId, data) {
  try {
    await api(`/agents/${agentId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
    showToast('Agent 更新成功', 'success');
    await fetchCustomAgents();
  } catch (e) {
    showToast(`更新失败: ${e.message}`, 'error');
  }
}

function openEditCustomAgentModal(agentId) {
  const agent = (state.customAgents || []).find(a => String(a.agent_id || a.id) === String(agentId));
  if (!agent) {
    showToast('未找到该 Agent 数据', 'error');
    return;
  }
  state.editingAgent = agent;
  const root = $('#modal-edit-agent');
  root.classList.remove('hidden');
  renderEditCustomAgentModal();
}

function closeEditCustomAgentModal() {
  state.editingAgent = null;
  closeModal('modal-edit-agent');
}

function renderEditCustomAgentModal() {
  const agent = state.editingAgent;
  if (!agent) return;
  const root = $('#modal-edit-agent');
  const name = agent.name || '';
  const model = (agent.llm_adapter || agent.model || 'tongyi').replace(/"/g, '&quot;');
  const sysPrompt = (agent.systemPrompt || agent.system_prompt || '').replace(/"/g, '&quot;');
  const tools = (agent.tools || agent.skills || []).join(', ');
  root.innerHTML = `
    <div class="absolute inset-0 bg-black/40" onclick="closeEditCustomAgentModal()"></div>
    <div class="absolute inset-0 flex items-center justify-center p-4">
      <div class="bg-surface-container-high rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
        <div class="flex items-center justify-between p-4 pb-0">
          <h3 class="text-title-md text-on-surface">编辑自定义Agent</h3>
          <button onclick="closeEditCustomAgentModal()" class="p-1 rounded hover:bg-surface-container">
            <span class="material-symbols-outlined">close</span>
          </button>
        </div>
        <div class="p-4 space-y-4">
          <div>
            <label class="text-label-sm text-secondary block mb-1">名称</label>
            <input id="edit-agent-name" type="text" value="${escapeAttr(name)}"
              class="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant text-on-surface text-body-md focus:outline-none focus:border-primary">
          </div>
          <div>
            <label class="text-label-sm text-secondary block mb-1">模型适配器（llm_adapter）</label>
            <input id="edit-agent-model" type="text" value="${escapeAttr(model)}"
              class="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant text-on-surface text-body-md focus:outline-none focus:border-primary">
          </div>
          <div>
            <label class="text-label-sm text-secondary block mb-1">系统提示词
              <button onclick="improveAgentPrompt('edit-agent-prompt')" title="AI 自动优化提示词" class="ml-2 px-2 py-0.5 rounded border border-primary/40 text-primary text-[11px] hover:bg-primary-fixed/30 transition-colors font-medium">✨ AI 优化</button>
            </label>
            <textarea id="edit-agent-prompt" rows="4"
              class="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant text-on-surface text-body-md focus:outline-none focus:border-primary">${sysPrompt}</textarea>
          </div>
          <div>
            <label class="text-label-sm text-secondary block mb-1">工具/技能列表（逗号分隔）</label>
            <input id="edit-agent-tools" type="text" value="${escapeAttr(tools)}"
              class="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant text-on-surface text-body-md focus:outline-none focus:border-primary">
          </div>
        </div>
        <div class="flex items-center justify-end gap-3 p-4 pt-0">
          <button onclick="closeEditCustomAgentModal()" class="px-3 py-1.5 text-secondary text-label-md hover:underline">取消</button>
          <button onclick="saveEditCustomAgent()" class="px-4 py-1.5 bg-primary text-white rounded-lg text-label-md hover:bg-primary/90 transition-colors">保存</button>
        </div>
      </div>
    </div>`;
}

function saveEditCustomAgent() {
  const agent = state.editingAgent;
  if (!agent) return;
  const agentId = agent.agent_id || agent.id;
  const data = {
    name: $('#edit-agent-name').value.trim(),
    llm_adapter: $('#edit-agent-model').value.trim(),
    system_prompt: $('#edit-agent-prompt').value.trim(),
    tools: $('#edit-agent-tools').value.split(',').map(s => s.trim()).filter(Boolean),
  };
  if (!data.name) { showToast('名称不能为空', 'error'); return; }
  closeEditCustomAgentModal();
  updateCustomAgentAPI(agentId, data);
}

async function updateCustomAgentAPI(agentId, data) {
  try {
    await api(`/agents/${agentId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
    showToast('Agent 更新成功', 'success');
    await fetchCustomAgents();
  } catch (e) {
    showToast(`更新失败: ${e.message}`, 'error');
  }
}

function openEditCustomAgentModal(agentId) {
  const agent = (state.customAgents || []).find(a => String(a.agent_id || a.id) === String(agentId));
  if (!agent) {
    showToast('未找到该 Agent 数据', 'error');
    return;
  }
  state.editingAgent = agent;
  const root = $('#modal-edit-agent');
  root.classList.remove('hidden');
  renderEditCustomAgentModal();
}

function closeEditCustomAgentModal() {
  state.editingAgent = null;
  closeModal('modal-edit-agent');
}

function renderEditCustomAgentModal() {
  const agent = state.editingAgent;
  if (!agent) return;
  const root = $('#modal-edit-agent');
  const name = agent.name || '';
  const icon = agent.icon || 'smart_toy';
  const desc = agent.description || '';
  const model = agent.model || 'qwen-plus';
  const sysPrompt = (agent.systemPrompt || agent.system_prompt || '').replace(/"/g, '&quot;');
  const skills = (agent.skills || (agent.tools || [])).join(', ');
  root.innerHTML = `
    <div class="absolute inset-0 bg-black/40" onclick="closeEditCustomAgentModal()"></div>
    <div class="absolute inset-0 flex items-center justify-center p-4">
      <div class="bg-surface-container-high rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
        <div class="flex items-center justify-between p-4 pb-0">
          <h3 class="text-title-md text-on-surface">编辑自定义Agent</h3>
          <button onclick="closeEditCustomAgentModal()" class="p-1 rounded hover:bg-surface-container">
            <span class="material-symbols-outlined">close</span>
          </button>
        </div>
        <div class="p-4 space-y-4">
          <div>
            <label class="text-label-sm text-secondary block mb-1">名称</label>
            <input id="edit-agent-name" type="text" value="${escapeAttr(name)}"
              class="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant text-on-surface text-body-md focus:outline-none focus:border-primary">
          </div>
          <div>
            <label class="text-label-sm text-secondary block mb-1">图标（Material Symbols 名称）</label>
            <input id="edit-agent-icon" type="text" value="${escapeAttr(icon)}"
              class="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant text-on-surface text-body-md focus:outline-none focus:border-primary">
          </div>
          <div>
            <label class="text-label-sm text-secondary block mb-1">描述</label>
            <input id="edit-agent-desc" type="text" value="${escapeAttr(desc)}"
              class="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant text-on-surface text-body-md focus:outline-none focus:border-primary">
          </div>
          <div>
            <label class="text-label-sm text-secondary block mb-1">模型</label>
            <input id="edit-agent-model" type="text" value="${escapeAttr(model)}"
              class="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant text-on-surface text-body-md focus:outline-none focus:border-primary">
          </div>
          <div>
            <label class="text-label-sm text-secondary block mb-1">系统提示词</label>
            <textarea id="edit-agent-prompt" rows="4"
              class="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant text-on-surface text-body-md focus:outline-none focus:border-primary">${sysPrompt}</textarea>
          </div>
          <div>
            <label class="text-label-sm text-secondary block mb-1">技能（逗号分隔）</label>
            <input id="edit-agent-skills" type="text" value="${escapeAttr(skills)}"
              class="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant text-on-surface text-body-md focus:outline-none focus:border-primary">
          </div>
        </div>
        <div class="flex items-center justify-end gap-3 p-4 pt-0">
          <button onclick="closeEditCustomAgentModal()" class="px-3 py-1.5 text-secondary text-label-md hover:underline">取消</button>
          <button onclick="saveEditCustomAgent()" class="px-4 py-1.5 bg-primary text-white rounded-lg text-label-md hover:bg-primary/90 transition-colors">保存</button>
        </div>
      </div>
    </div>`;
}

function saveEditCustomAgent() {
  const agent = state.editingAgent;
  if (!agent) return;
  const agentId = agent.agent_id || agent.id;
  const data = {
    name: $('#edit-agent-name').value.trim(),
    icon: $('#edit-agent-icon').value.trim(),
    description: $('#edit-agent-desc').value.trim(),
    model: $('#edit-agent-model').value.trim(),
    system_prompt: $('#edit-agent-prompt').value.trim(),
    skills: $('#edit-agent-skills').value.split(',').map(s => s.trim()).filter(Boolean),
  };
  if (!data.name) { showToast('名称不能为空', 'error'); return; }
  closeEditCustomAgentModal();
  updateCustomAgentAPI(agentId, data);
}

async function bootstrapAuth() {
  // 先渲染空状态，避免页面白屏
  render();

  // 从后端加载 missions
  try {
    const missionsRes = await api('/missions');
    if (missionsRes && missionsRes.ok && missionsRes.missions && missionsRes.missions.length > 0) {
      // 合并 missions，保留现有 conversation 数据
      const existing = new Map((state.missions || []).map(m => [m.id, m]));
      state.missions = missionsRes.missions.map(newM => {
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
  } catch (err) {
    console.error('[MISSIONS] 加载失败:', err);
  }

  // 加载用户信息
  const token = localStorage.getItem('agenthub_token');
  if (token) {
    try {
      const r = await api('/me');
      if (r && r.ok) {
        state.user = r.user;
        render();
      }
    } catch(e) {
      localStorage.removeItem('agenthub_token');
      render();
    }
  }
  loadSkills();
  fetchCustomAgents();
}

function openAuthModal(tab='register') {
  state.authTab = tab;
  const root = $('#modal-auth');
  root.classList.remove('hidden');
  renderAuthModal();
}

function switchAuthTab(tab) {
  state.authTab = tab;
  renderAuthModal();
}

function renderAuthModal() {
  const root = $('#modal-auth');
  if (root.classList.contains('hidden')) return;
  const isLogin = state.authTab === 'login';
  const tabBtn = (key, label) => `
    <button onclick="switchAuthTab('${key}')"
            class="flex-1 py-2 text-label-md font-medium border-b-2 transition-colors
                   ${state.authTab===key
                     ? 'border-primary text-primary'
                     : 'border-transparent text-secondary hover:text-on-surface'}">
      ${label}
    </button>`;
  root.innerHTML = `
    <div class="absolute inset-0 modal-overlay" onclick="closeModal('modal-auth')"></div>
    <div class="relative h-full w-full flex items-center justify-center p-lg" onclick="event.stopPropagation()">
      <div class="bg-surface rounded-xl shadow-xl w-full max-w-[420px] overflow-hidden">
        <div class="px-lg pt-lg pb-md flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="w-8 h-8 bg-primary rounded flex items-center justify-center text-white font-bold">A</div>
            <h3 class="text-title-lg text-on-surface">${isLogin ? '登录 AgentHub' : '注册 AgentHub'}</h3>
          </div>
          <button onclick="closeModal('modal-auth')" class="p-1 rounded hover:bg-surface-container">
            <span class="material-symbols-outlined text-secondary">close</span>
          </button>
        </div>
        <div class="px-lg flex border-b border-outline-variant">
          ${tabBtn('register', '注册')}
          ${tabBtn('login',    '登录')}
        </div>
        <form class="px-lg py-lg space-y-md" onsubmit="event.preventDefault(); ${isLogin ? 'commitLogin()' : 'commitRegister()'}">
          ${isLogin ? '' : `
            <div>
              <label class="block text-label-md text-on-surface mb-1">用户名</label>
              <input id="auth-username" type="text" required minlength="2" maxlength="32"
                     placeholder="例如：Alex Chen"
                     class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 transition-colors"/>
            </div>`}
          <div>
            <label class="block text-label-md text-on-surface mb-1">邮箱</label>
            <input id="auth-email" type="email" required
                   placeholder="you@example.com"
                   class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 transition-colors"/>
          </div>
          <div>
            <label class="block text-label-md text-on-surface mb-1">密码</label>
            <input id="auth-password" type="password" required minlength="6"
                   placeholder="至少 6 位"
                   class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-body-md focus:border-primary focus:ring-0 transition-colors"/>
          </div>
          <p id="auth-error" class="hidden text-label-md text-error"></p>
          <button type="submit"
                  class="w-full bg-primary text-white py-2.5 rounded-lg font-medium text-label-md hover:opacity-90 transition-opacity flex items-center justify-center gap-2">
            <span class="material-symbols-outlined text-[18px]">${isLogin ? 'login' : 'person_add'}</span>
            <span>${isLogin ? '登录' : '注册并登录'}</span>
          </button>
          <p class="text-label-sm text-secondary text-center pt-1">
            ${isLogin ? '还没有账号？' : '已有账号？'}
            <a onclick="switchAuthTab('${isLogin ? 'register' : 'login'}')"
               class="text-primary cursor-pointer hover:underline font-medium">
              ${isLogin ? '点此注册' : '直接登录'}
            </a>
          </p>
        </form>
      </div>
    </div>`;
  setTimeout(() => $(isLogin ? '#auth-email' : '#auth-username')?.focus(), 50);
}

function showAuthError(msg) {
  const el = $('#auth-error');
  if (!el) return;
  el.textContent = msg;
  el.classList.remove('hidden');
}

const ERROR_MESSAGES = {
  username_too_short: '用户名至少 2 位',
  invalid_email: '邮箱格式不正确',
  password_too_short: '密码至少 6 位',
  email_already_registered: '该邮箱已注册，请直接登录',
  invalid_credentials: '邮箱或密码错误',
};

async function commitRegister() {
  const username = $('#auth-username').value.trim();
  const email    = $('#auth-email').value.trim();
  const password = $('#auth-password').value;
  try {
    const r = await api('/register', {
      method: 'POST',
      body: JSON.stringify({ username, email, password })
    });
    if (r && r.ok) {
      localStorage.setItem('agenthub_token', r.token);
      state.user = r.user;
      closeModal('modal-auth');
      showToast(`欢迎，${r.user.username}！`, 'success');
      loadSkills();
      render();
    }
  } catch (e) {
    const accountExists = ['用户名已存在', '邮箱已被注册'].includes(e.message);
    if (accountExists) {
      try {
        const loginRes = await api('/login', {
          method: 'POST',
          body: JSON.stringify({ email, password })
        });
        if (loginRes && loginRes.ok) {
          localStorage.setItem('agenthub_token', loginRes.token);
          state.user = loginRes.user;
          closeModal('modal-auth');
          showToast('检测到已有账户，已自动登录 ' + loginRes.user.username, 'success');
          loadSkills();
          render();
          return;
        }
      } catch (loginError) {
        showAuthError('该账户已存在，但当前密码不正确，请直接登录并检查密码。');
        return;
      }
    }
    showAuthError(ERROR_MESSAGES[e.message] || ('注册失败：' + e.message));
  }
}

async function commitLogin() {
  const email    = $('#auth-email').value.trim();
  const password = $('#auth-password').value;
  try {
    const r = await api('/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    if (r && r.ok) {
      localStorage.setItem('agenthub_token', r.token);
      state.user = r.user;
      closeModal('modal-auth');
      showToast(`欢迎回来，${r.user.username}！`, 'success');
      loadSkills();
      render();
    }
  } catch (e) {
    showAuthError(ERROR_MESSAGES[e.message] || ('登录失败：' + e.message));
  }
}

function logout() {
  localStorage.removeItem('agenthub_token');
  state.user = null;
  state.skills = { market: state.skills.market, mine: [], loaded: state.skills.loaded };
  showToast('已退出登录', 'info');
  render();
}

/* ===================== 验收自检（控制台） ===================== */
window.__verifyChecklist = function() {
  const checks = [
    ['后端 missions 已加载', () => state.missions.length >= 0],
    ['后端 skills 已加载', () => state.skills.loaded],
    ['认证状态正常', () => state.user === null || (state.user && state.user.id)],
    ['Mission 工作台有当前 Run', () => !!getRun()],
    ['@ 多 Agent 解析', () => parseMentions('@Agent1 @Agent2 一起想想').length === 2],
    ['编辑意图解析正常', () => !!parseEditIntent('给默认助手加 web_search 技能')],
    ['详情页 NL 面板渲染（team tab=overview）', () => {
      const m = getMission('mis_fin');
      const mgr = m.squad.agents.find(x => x.kind === 'team');
      const html = renderAgentDetailNLPanel(mgr, mgr, 'overview');
      return typeof html === 'string' && html.includes('修改这个 Agent') && html.includes('解析并预览');
    }],
    ['NL 面板每个 Tab 都有提示词', () => {
      const m = getMission('mis_fin');
      const mgr = m.squad.agents.find(x => x.kind === 'team');
      const tabs = ['overview','prompt','skills','memory','planning','validation','hooks','team','readme','missions'];
      return tabs.every(t => {
        const html = renderAgentDetailNLPanel(mgr, mgr, t);
        return typeof html === 'string' && html.includes('placeholder=');
      });
    }],
    ['Add Agent Modal 函数齐全', () =>
      typeof openModalAddAgent === 'function' &&
      typeof closeModalAddAgent === 'function' &&
      typeof addAgentFromLibrary === 'function' &&
      typeof addAgentFromMarketToMission === 'function' &&
      typeof createAgentFromNL === 'function' &&
      typeof guessAgentFromNL === 'function'
    ],
    ['guessAgentFromNL 能识别翻译类描述', () => {
      const g = guessAgentFromNL('能把英文论文翻译成中文');
      return g.icon === 'translate' && g.name === 'Translator' && g.skills.includes('translate');
    }],
  ];
  console.group('AgentHub · 验收清单');
  checks.forEach(([t, fn]) => {
    let ok = false; try { ok = fn(); } catch(e){}
    console.log(`%c${ok?'✅':'❌'} ${t}`, `color:${ok?'green':'red'};font-weight:bold`);
  });
  console.groupEnd();
};
setTimeout(() => window.__verifyChecklist?.(), 800);

/* ===== Toast ===== */
function showToast(msg, type='info') {
  const el = $('#toast');
  const colorClass = type === 'success' ? 'bg-tertiary text-white'
                  : type === 'error'   ? 'bg-error text-white'
                  : 'bg-inverse-surface text-inverse-on-surface';
  el.className = `fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] ${colorClass} px-4 py-2 rounded-lg shadow-lg text-label-md transition-all`;
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.add('hidden'), 2200);
}

document.addEventListener('DOMContentLoaded', () => {
  loadCustomSkills();
  render();
  bootstrapAuth();
});

window.addEventListener('beforeunload', (e) => {
  if (state.detail && state.detail.dirty) {
    e.preventDefault();
    e.returnValue = '';
    return '';
  }
});