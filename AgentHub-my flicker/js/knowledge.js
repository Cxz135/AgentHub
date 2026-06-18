/* ============================================================
   知识库（Knowledge Base / RAG）— 纯前端实现
   ============================================================
   d11: 文件解析（pdf/docx/xlsx/md/txt/csv/json）
   d12: 切分 + token + 简版 TF-IDF 检索 + 关键词高亮
   d13: state.kbs / state.kbDetail + localStorage 持久化
============================================================ */

const KB_MAX_FILE_SIZE = 5 * 1024 * 1024;   // 5MB
const KB_MAX_CHUNKS_PER_DOC = 200;
const KB_CHUNK_SIZE = 500;
const KB_LS_PREFIX = 'agenthub.kbs.v1.';

/* ---- d11: 文件解析 ---- */

async function parseFileToText(file) {
  const name = file.name || '';
  const ext = (name.split('.').pop() || '').toLowerCase();
  const size = file.size;
  // 大小硬限制
  if (size > KB_MAX_FILE_SIZE) {
    return { error: `文件 "${name}" 大小 ${(size/1024/1024).toFixed(2)}MB，超过 5MB 限制无法上传` };
  }
  try {
    if (['md','txt','json','csv','log'].includes(ext)) {
      const text = await file.text();
      return { text, fileType: ext, mime: file.type || 'text/plain' };
    }
    if (ext === 'pdf') {
      if (!window.pdfjsLib) return { error: 'PDF 解析库未就绪，请刷新页面重试' };
      const buf = await file.arrayBuffer();
      const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
      let text = '';
      const max = Math.min(pdf.numPages, 200);   // 防止超大 pdf 卡死
      for (let i = 1; i <= max; i++) {
        const page = await pdf.getPage(i);
        const content = await page.getTextContent();
        text += content.items.map(it => it.str).join(' ') + '\n\n';
      }
      if (pdf.numPages > 200) text += `\n[已截断：仅解析前 200 页，原文档共 ${pdf.numPages} 页]`;
      return { text, fileType: 'pdf', mime: 'application/pdf' };
    }
    if (ext === 'docx') {
      if (!window.mammoth) return { error: 'DOCX 解析库未就绪，请刷新页面重试' };
      const buf = await file.arrayBuffer();
      const result = await mammoth.extractRawText({ arrayBuffer: buf });
      return { text: result.value || '', fileType: 'docx', mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' };
    }
    if (ext === 'doc') {
      return { error: '.doc 格式不支持（请用 Word 另存为 .docx）' };
    }
    if (['xlsx','xls'].includes(ext)) {
      if (!window.XLSX) return { error: 'Excel 解析库未就绪，请刷新页面重试' };
      const buf = await file.arrayBuffer();
      const wb = XLSX.read(buf, { type: 'array' });
      let text = '';
      wb.SheetNames.forEach(sn => {
        text += `# ${sn}\n`;
        const ws = wb.Sheets[sn];
        text += XLSX.utils.sheet_to_csv(ws) + '\n\n';
      });
      return { text, fileType: ext, mime: 'application/vnd.ms-excel' };
    }
    return { error: `不支持的文件类型 .${ext}（仅支持 pdf/docx/xlsx/xls/md/txt/json/csv）` };
  } catch (e) {
    console.error('parseFileToText error:', e);
    return { error: '解析失败：' + (e.message || e) };
  }
}

/* ---- d12: 切分 + token + mockRagQuery + highlight ---- */

function chunkText(text, opts = {}) {
  const size = opts.size || KB_CHUNK_SIZE;
  const overlap = opts.overlap || 50;
  if (!text) return [];
  // 先按段落
  const paras = text.split(/\n{2,}/).map(p => p.trim()).filter(Boolean);
  const out = [];
  let buf = '';
  for (const p of paras) {
    if ((buf + '\n\n' + p).length <= size) {
      buf = buf ? buf + '\n\n' + p : p;
    } else {
      if (buf) out.push(buf);
      if (p.length <= size) {
        buf = p;
      } else {
        // 长段按句号切
        const sents = p.split(/(?<=[。！？.!?])\s*/).filter(Boolean);
        let sbuf = '';
        for (const s of sents) {
          if ((sbuf + s).length <= size) {
            sbuf += s;
          } else {
            if (sbuf) out.push(sbuf);
            // 单句仍然超长则硬切
            if (s.length > size) {
              for (let i = 0; i < s.length; i += size - overlap) {
                out.push(s.slice(i, i + size));
              }
              sbuf = '';
            } else {
              sbuf = s;
            }
          }
        }
        buf = sbuf;
      }
    }
    if (out.length >= KB_MAX_CHUNKS_PER_DOC) break;
  }
  if (buf && out.length < KB_MAX_CHUNKS_PER_DOC) out.push(buf);
  return out.slice(0, KB_MAX_CHUNKS_PER_DOC).map((text, index) => ({
    index, text, tokens: Math.ceil(text.length / 1.5),
  }));
}

function tokenize(s) {
  if (!s) return [];
  const out = [];
  // 英文 / 数字 单词
  const en = s.match(/[a-zA-Z]+\d*|\d+/g) || [];
  out.push(...en.map(w => w.toLowerCase()));
  // 中文字符
  const cn = s.match(/[\u4e00-\u9fa5]/g) || [];
  out.push(...cn);
  return out;
}

function mockRagQuery({ kbIds, query, topK = 5 }) {
  const terms = tokenize(query);
  if (!terms.length) return [];
  // 收集目标 docs
  const targetDocs = [];
  (state.kbs.list || []).forEach(kb => {
    if (!kbIds || !kbIds.includes(kb.id)) return;
    (kb.docs || []).forEach(doc => {
      (doc.chunks || []).forEach(ch => {
        targetDocs.push({ kbId: kb.id, kbName: kb.name, docId: doc.id, docName: doc.name, chunk: ch });
      });
    });
  });
  if (!targetDocs.length) return [];
  // 计算 df（按 chunk 维度）
  const df = {};
  const N = targetDocs.length;
  terms.forEach(t => {
    if (df[t] !== undefined) return;
    let c = 0;
    targetDocs.forEach(d => { if (d.chunk.text.toLowerCase().includes(t.toLowerCase())) c++; });
    df[t] = c;
  });
  const scored = targetDocs.map(d => {
    let score = 0;
    const lower = d.chunk.text.toLowerCase();
    const matched = new Set();
    terms.forEach(t => {
      const re = new RegExp(t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      const cnt = (lower.match(re) || []).length;
      if (cnt > 0) {
        const idf = Math.log((N + 1) / (df[t] + 1)) + 1;
        score += cnt * idf * (t.length >= 2 ? 1.5 : 1);
        matched.add(t);
      }
    });
    // 全 query 子串命中 bonus
    if (lower.includes(query.toLowerCase())) score += 3;
    return { ...d, score, matchedTerms: [...matched] };
  }).filter(x => x.score > 0);
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, topK).map(x => ({
    kbId: x.kbId, kbName: x.kbName,
    docId: x.docId, docName: x.docName,
    chunkIndex: x.chunk.index,
    text: x.chunk.text,
    score: +x.score.toFixed(2),
    matchedTerms: x.matchedTerms,
  }));
}

function highlightText(text, terms) {
  if (!terms || !terms.length) return escapeHTML(text);
  const escaped = escapeHTML(text);
  let html = escaped;
  // 按长度降序避免短词覆盖长词
  const sorted = [...new Set(terms)].sort((a, b) => b.length - a.length);
  sorted.forEach(t => {
    const re = new RegExp('(' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    html = html.replace(re, '<mark class="bg-amber-200 text-amber-900 px-0.5 rounded">$1</mark>');
  });
  return html;
}

/* ---- d13: state + localStorage ---- */

state.kbs = {
  loaded: false,
  list: [],          // [{ id, name, icon, description, docs:[], createdAt, updatedAt }]
};
state.kbDetail = null;        // { id, tab:'docs'|'missions'|'search', selectedIds:Set, draft, dirty, searchResult }
state.kbUpload = null;        // { items: [{name,size,status,error?,docId?}] }
state.slashPopup = null;      // { items:[{kbId,kbName}], activeIndex }

function kbLsKey() {
  const uid = (state.user && state.user.id) || 'guest';
  return KB_LS_PREFIX + uid;
}
function loadKbs() {
  try {
    const raw = localStorage.getItem(kbLsKey());
    state.kbs.list = raw ? JSON.parse(raw) : [];
  } catch (_) { state.kbs.list = []; }
  // 兜底字段
  state.kbs.list.forEach(kb => {
    kb.docs = kb.docs || [];
    kb.docs.forEach(d => {
      d.chunks = d.chunks || [];
      d.status = d.status || 'ready';
    });
  });
  state.kbs.loaded = true;
}
function saveKbs() {
  try {
    localStorage.setItem(kbLsKey(), JSON.stringify(state.kbs.list));
  } catch (e) {
    showToast('localStorage 写入失败（可能已超 5MB 配额）：' + e.message);
  }
}
function kbDocCount(kb)   { return (kb.docs || []).length; }
function kbChunkCount(kb) { return (kb.docs || []).reduce((s, d) => s + (d.chunks||[]).length, 0); }
function uidKb(prefix='kb')  { return prefix + '_' + Math.random().toString(36).slice(2, 9); }

// mission.kbConfig 兜底
function ensureMissionKbConfig(m) {
  if (!m.kbConfig) m.kbConfig = { triggerMode: 'auto', bindings: [] };
  return m.kbConfig;
}

// 临时占位：避免侧栏点击进入时报错（下一步会替换）
function renderKnowledgePage() {
  if (!state.kbs.loaded) loadKbs();
  const kbs = state.kbs.list;
  const search = (state.kbs.search || '').toLowerCase();
  const filtered = search ? kbs.filter(k => k.name.toLowerCase().includes(search) || (k.description||'').toLowerCase().includes(search)) : kbs;

  // 空态引导
  if (!kbs.length) {
    return `
      <div class="flex-1 overflow-y-auto bg-background">
        <section class="px-xl pt-xl pb-md">
          <h2 class="text-headline-lg text-on-surface">知识库</h2>
          <p class="text-body-md text-secondary mt-1">为每个 Mission 配置专属的 RAG 知识来源。支持 PDF / Word / Excel / Markdown / TXT / CSV / JSON。</p>
        </section>
        <section class="px-xl pb-xl">
          <div class="max-w-3xl mx-auto bg-surface-container-lowest border border-outline-variant rounded-2xl p-xl text-center shadow-sm">
            <div class="w-16 h-16 rounded-2xl bg-primary-fixed/40 flex items-center justify-center mx-auto mb-md">
              <span class="material-symbols-outlined text-primary text-[36px]">menu_book</span>
            </div>
            <h3 class="text-title-lg font-headline-lg text-on-surface">欢迎使用知识库</h3>
            <p class="text-body-md text-secondary mt-1">让你的 Mission 拥有专属的私有知识来源</p>

            <div class="grid grid-cols-3 gap-md mt-lg">
              <div class="p-md bg-surface-container-low rounded-lg">
                <div class="w-10 h-10 rounded-full bg-primary text-white flex items-center justify-center mx-auto mb-2 font-bold">1</div>
                <p class="font-label-md text-on-surface">创建知识库</p>
                <p class="text-label-sm text-secondary mt-1">按主题/项目分类，比如「产品文档」「法务条款」</p>
              </div>
              <div class="p-md bg-surface-container-low rounded-lg">
                <div class="w-10 h-10 rounded-full bg-primary text-white flex items-center justify-center mx-auto mb-2 font-bold">2</div>
                <p class="font-label-md text-on-surface">上传文档</p>
                <p class="text-label-sm text-secondary mt-1">PDF / Word / Excel / Markdown 全部支持，自动切片</p>
              </div>
              <div class="p-md bg-surface-container-low rounded-lg">
                <div class="w-10 h-10 rounded-full bg-primary text-white flex items-center justify-center mx-auto mb-2 font-bold">3</div>
                <p class="font-label-md text-on-surface">Mission 绑定</p>
                <p class="text-label-sm text-secondary mt-1">在 Mission 右栏「知识库」Tab 绑定 → 自动或 / 触发 RAG</p>
              </div>
            </div>

            <div class="flex justify-center gap-3 mt-lg">
              <button onclick="openCreateKbModal()"
                class="px-5 py-2.5 bg-primary text-white rounded-lg flex items-center gap-2 hover:opacity-90 shadow-sm">
                <span class="material-symbols-outlined text-[18px]">add</span>
                创建第一个知识库
              </button>
              <button onclick="seedExampleKb()"
                class="px-5 py-2.5 bg-surface-container border border-outline-variant text-on-surface rounded-lg flex items-center gap-2 hover:bg-surface-container-low">
                <span class="material-symbols-outlined text-[18px]">auto_awesome</span>
                使用示例知识库
              </button>
            </div>
          </div>
        </section>
      </div>`;
  }

  return `
    <div class="flex-1 overflow-y-auto bg-background">
      <section class="px-xl pt-xl pb-md flex items-end justify-between gap-3 flex-wrap">
        <div class="min-w-0">
          <h2 class="text-headline-lg text-on-surface">知识库</h2>
          <p class="text-body-md text-secondary mt-1">共 ${kbs.length} 个 · ${kbs.reduce((s,k)=>s+kbDocCount(k),0)} 文档 · ${kbs.reduce((s,k)=>s+kbChunkCount(k),0)} 切片</p>
        </div>
        <div class="flex items-center gap-2">
          <div class="relative">
            <span class="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-secondary text-[18px]">search</span>
            <input value="${escapeHTML(state.kbs.search||'')}" oninput="state.kbs.search=this.value; render(); document.getElementById('kb-search-input')?.focus()"
              id="kb-search-input" placeholder="搜索知识库…"
              class="pl-8 pr-3 py-1.5 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary w-56"/>
          </div>
          <button onclick="openCreateKbModal()"
            class="px-3 py-1.5 bg-primary text-white rounded-lg flex items-center gap-1 hover:opacity-90 text-label-md">
            <span class="material-symbols-outlined text-[16px]">add</span>新建知识库
          </button>
        </div>
      </section>

      <section class="px-xl pb-xl grid grid-cols-3 gap-md">
        ${filtered.length ? filtered.map(kb => renderKbCard(kb)).join('') : `
          <div class="col-span-3 text-center text-secondary p-xl">
            <span class="material-symbols-outlined text-[40px] opacity-40 mb-2 block">search_off</span>
            <p>没有匹配的知识库</p>
          </div>`}
      </section>
    </div>`;
}

function renderKbCard(kb) {
  const dc = kbDocCount(kb), cc = kbChunkCount(kb);
  return `
    <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-md hover:border-primary/40 transition-colors cursor-pointer group"
         onclick="openKbDetail('${kb.id}')">
      <div class="flex items-start gap-3">
        <div class="w-10 h-10 rounded-lg bg-primary-fixed/40 flex items-center justify-center shrink-0">
          <span class="material-symbols-outlined text-primary text-[20px]">${escapeHTML(kb.icon||'menu_book')}</span>
        </div>
        <div class="min-w-0 flex-1">
          <p class="font-label-md text-on-surface truncate">${escapeHTML(kb.name)}</p>
          <p class="text-label-sm text-secondary truncate">${escapeHTML(kb.description||'（无描述）')}</p>
        </div>
        <div class="relative shrink-0" onclick="event.stopPropagation()">
          <button onclick="toggleKbMenu('${kb.id}')" class="opacity-0 group-hover:opacity-100 text-secondary hover:text-on-surface p-1 rounded hover:bg-surface-container">
            <span class="material-symbols-outlined text-[18px]">more_horiz</span>
          </button>
          ${state.kbs.menuOpen === kb.id ? `
            <div class="absolute right-0 top-full mt-1 w-32 bg-surface border border-outline-variant rounded-lg shadow-lg z-10">
              <button onclick="state.kbs.menuOpen=null; openRenameKbModal('${kb.id}')" class="w-full text-left px-3 py-2 hover:bg-surface-container-low text-label-md">重命名</button>
              <button onclick="state.kbs.menuOpen=null; deleteKb('${kb.id}')" class="w-full text-left px-3 py-2 hover:bg-error/10 text-error text-label-md">删除</button>
            </div>` : ''}
        </div>
      </div>
      <div class="mt-3 flex items-center gap-3 text-label-sm text-secondary">
        <span class="flex items-center gap-1"><span class="material-symbols-outlined text-[14px]">description</span>${dc} 文档</span>
        <span class="flex items-center gap-1"><span class="material-symbols-outlined text-[14px]">view_agenda</span>${cc} 切片</span>
        <span class="ml-auto text-[11px]">${escapeHTML((kb.updatedAt||'').slice(5,16) || '-')}</span>
      </div>
    </div>`;
}

function toggleKbMenu(id) {
  state.kbs.menuOpen = state.kbs.menuOpen === id ? null : id;
  render();
}

/* ---- KB CRUD ---- */

function createKb({ name, icon='menu_book', description='' }) {
  if (!name || !name.trim()) { showToast('知识库名称不能为空'); return null; }
  const kb = {
    id: uidKb('kb'),
    name: name.trim(),
    icon,
    description: description.trim(),
    docs: [],
    createdAt: nowKbTs(),
    updatedAt: nowKbTs(),
  };
  state.kbs.list.unshift(kb);
  saveKbs();
  return kb;
}
function nowKbTs() { return new Date().toISOString().replace('T',' ').slice(0,19); }

function renameKb(id, name) {
  const kb = state.kbs.list.find(k => k.id === id);
  if (!kb || !name.trim()) return;
  kb.name = name.trim();
  kb.updatedAt = nowKbTs();
  saveKbs();
}

function deleteKb(id) {
  const kb = state.kbs.list.find(k => k.id === id);
  if (!kb) return;
  if (!confirm(`确定删除知识库「${kb.name}」？包含的 ${kbDocCount(kb)} 个文档也会被删除，且无法恢复。`)) return;
  state.kbs.list = state.kbs.list.filter(k => k.id !== id);
  // 清理所有 mission 中的绑定
  state.missions.forEach(m => {
    if (m.kbConfig) {
      m.kbConfig.bindings = (m.kbConfig.bindings || []).filter(b => b.kbId !== id);
    }
  });
  saveKbs();
  showToast('已删除', 'success');
  render();
}

/* ---- 新建/重命名 KB Modal ---- */

const KB_ICON_OPTIONS = ['menu_book','description','folder','library_books','article','school','quiz','psychology','science','gavel','engineering','business','public','shopping_bag','restaurant_menu','health_and_safety','medical_information','code'];

function openCreateKbModal() {
  state.kbs.draft = { name:'', icon:'menu_book', description:'' };
  renderKbEditModal('create');
}
function openRenameKbModal(id) {
  const kb = state.kbs.list.find(k => k.id === id);
  if (!kb) return;
  state.kbs.draft = { id, name: kb.name, icon: kb.icon || 'menu_book', description: kb.description||'' };
  renderKbEditModal('edit');
}
function closeKbEditModal() {
  const root = document.getElementById('modal-kb-edit');
  if (root) root.remove();
  state.kbs.draft = null;
}
function renderKbEditModal(mode) {
  let root = document.getElementById('modal-kb-edit');
  if (!root) {
    root = document.createElement('div');
    root.id = 'modal-kb-edit';
    document.body.appendChild(root);
  }
  const d = state.kbs.draft;
  root.innerHTML = `
    <div class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onclick="if(event.target===this) closeKbEditModal()">
      <div class="bg-surface rounded-xl shadow-2xl w-[520px] max-h-[90vh] flex flex-col overflow-hidden">
        <header class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <h3 class="text-title-lg font-headline-md">${mode==='create'?'新建知识库':'编辑知识库'}</h3>
          <button onclick="closeKbEditModal()" class="text-secondary hover:text-on-surface"><span class="material-symbols-outlined">close</span></button>
        </header>
        <main class="px-lg py-md space-y-md overflow-y-auto">
          <div>
            <label class="text-label-md text-secondary mb-1 block">名称 *</label>
            <input value="${escapeHTML(d.name)}" oninput="state.kbs.draft.name=this.value"
              class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"
              placeholder="例如：产品文档 / 法务条款 / 公司知识"/>
          </div>
          <div>
            <label class="text-label-md text-secondary mb-1 block">描述</label>
            <textarea rows="2" oninput="state.kbs.draft.description=this.value"
              class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"
              placeholder="一句话介绍这个知识库的用途">${escapeHTML(d.description)}</textarea>
          </div>
          <div>
            <label class="text-label-md text-secondary mb-1 block">图标</label>
            <div class="grid grid-cols-9 gap-2">
              ${KB_ICON_OPTIONS.map(i => `
                <button type="button" onclick="state.kbs.draft.icon='${i}'; renderKbEditModal('${mode}')"
                  class="w-9 h-9 rounded-lg border flex items-center justify-center
                         ${d.icon===i ? 'border-primary bg-primary-fixed/40' : 'border-outline-variant bg-surface-container-lowest hover:border-primary/40'}">
                  <span class="material-symbols-outlined text-[18px] ${d.icon===i?'text-primary':'text-on-surface-variant'}">${i}</span>
                </button>`).join('')}
            </div>
          </div>
        </main>
        <footer class="px-lg py-md border-t border-outline-variant flex justify-end gap-2">
          <button onclick="closeKbEditModal()" class="px-4 py-1.5 rounded-lg border border-outline-variant text-on-surface-variant hover:bg-surface-container-low text-label-md">取消</button>
          <button onclick="submitKbEdit('${mode}')" class="px-4 py-1.5 rounded-lg bg-primary text-white hover:opacity-90 text-label-md">${mode==='create'?'创建':'保存'}</button>
        </footer>
      </div>
    </div>`;
}
function submitKbEdit(mode) {
  const d = state.kbs.draft;
  if (!d || !d.name || !d.name.trim()) return showToast('请输入名称');
  if (mode === 'create') {
    const kb = createKb(d);
    closeKbEditModal();
    render();
    if (kb) openKbDetail(kb.id);
  } else {
    const kb = state.kbs.list.find(k => k.id === d.id);
    if (kb) {
      kb.name = d.name.trim();
      kb.icon = d.icon;
      kb.description = d.description.trim();
      kb.updatedAt = nowKbTs();
      saveKbs();
    }
    closeKbEditModal();
    render();
  }
}

/* ---- 示例知识库 ---- */
function seedExampleKb() {
  const sampleMd = `# AgentHub 知识库入门指南

本文档示范"知识库"模块的核心用法。

## 1. 文件类型支持
- PDF（.pdf）
- Word（.docx）
- Excel（.xlsx / .xls）
- Markdown（.md）
- 纯文本（.txt / .json / .csv）

单文件大小限制：5MB。

## 2. Mission 触发模式
- **自动**：每条消息都先做 RAG，命中片段拼到回复
- **/触发**：输入 \`/产品文档 退款政策\` 才检索指定 KB

## 3. 退款政策示例
本公司退款政策：购买后 7 天内未使用可全额退款，已使用按比例退还。
联系邮箱：refund@agenthub.example.com，工作日 24 小时内回复。

## 4. 价格示例
- Free 套餐：每月 100 次 RAG 查询，1 个知识库
- Pro 套餐：每月 10000 次 RAG 查询，50 个知识库，¥99/月
- Enterprise 套餐：定制，联系销售

## 5. 常见问题
**Q: 知识库支持中文吗？**
A: 支持。系统使用中英混合分词，中文按字、英文按 \\w+ 切分。

**Q: 文档过大怎么办？**
A: 5MB 以内可直接上传。更大请拆分。

**Q: 数据存在哪里？**
A: 当前版本存浏览器 localStorage，按用户分 namespace。`;

  const kb = createKb({
    name: 'AgentHub 入门指南',
    icon: 'auto_awesome',
    description: '示例知识库 · 包含文档解析、触发模式、退款政策、价格说明等',
  });
  if (!kb) return;
  // 加 doc
  const chunks = chunkText(sampleMd);
  kb.docs.push({
    id: uidKb('doc'),
    name: 'AgentHub-入门指南.md',
    mime: 'text/markdown',
    size: sampleMd.length,
    sourceType: 'text',
    rawText: sampleMd,
    chunks,
    status: 'ready',
    fileType: 'md',
    uploadedAt: nowKbTs(),
  });
  kb.updatedAt = nowKbTs();
  saveKbs();
  showToast('已生成示例知识库', 'success');
  render();
  setTimeout(() => openKbDetail(kb.id), 200);
}

function renderKbDetailPage() {
  if (!state.kbDetail) return '';
  const kb = state.kbs.list.find(k => k.id === state.kbDetail.id);
  if (!kb) {
    state.view = 'kbs';
    return renderKnowledgePage();
  }
  const tab = state.kbDetail.tab || 'docs';
  return `
    <div class="flex-1 overflow-y-auto bg-background">
      <!-- 顶部：返回 + 标题 + 操作 -->
      <section class="px-xl pt-lg pb-md border-b border-outline-variant bg-surface-container-lowest">
        <div class="flex items-center gap-2 text-label-md text-secondary">
          <button onclick="closeKbDetail()" class="hover:text-on-surface flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">arrow_back</span>知识库
          </button>
          <span>/</span>
          <span class="text-on-surface truncate">${escapeHTML(kb.name)}</span>
        </div>
        <div class="flex items-start gap-3 mt-3">
          <div class="w-12 h-12 rounded-xl bg-primary-fixed/40 flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined text-primary text-[24px]">${escapeHTML(kb.icon||'menu_book')}</span>
          </div>
          <div class="min-w-0 flex-1">
            <h2 class="text-headline-md text-on-surface truncate">${escapeHTML(kb.name)}</h2>
            <p class="text-body-md text-secondary mt-0.5">${escapeHTML(kb.description||'（无描述）')}</p>
            <p class="text-label-sm text-secondary mt-1">${kbDocCount(kb)} 文档 · ${kbChunkCount(kb)} 切片 · 更新于 ${escapeHTML(kb.updatedAt||'-')}</p>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button onclick="openRenameKbModal('${kb.id}')" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container-low text-label-md flex items-center gap-1">
              <span class="material-symbols-outlined text-[16px]">edit</span>编辑
            </button>
            <button onclick="deleteKb('${kb.id}')" class="px-3 py-1.5 rounded-lg border border-error/40 text-error hover:bg-error/10 text-label-md flex items-center gap-1">
              <span class="material-symbols-outlined text-[16px]">delete</span>删除
            </button>
          </div>
        </div>
        <!-- Tabs -->
        <nav class="mt-md flex items-center gap-1">
          ${renderKbDetailTab('docs',     '文档',         kbDocCount(kb), tab)}
          ${renderKbDetailTab('missions', '关联 Missions', kbBoundMissions(kb.id).length, tab)}
          ${renderKbDetailTab('search',   '检索测试',     null, tab)}
        </nav>
      </section>

      <section class="px-xl py-lg">
        ${tab === 'docs'     ? renderKbDocsTab(kb) : ''}
        ${tab === 'missions' ? renderKbMissionsTab(kb) : ''}
        ${tab === 'search'   ? renderKbSearchTab(kb) : ''}
      </section>
    </div>`;
}

function renderKbDetailTab(id, label, badge, active) {
  const isOn = id === active;
  return `<button onclick="switchKbDetailTab('${id}')"
    class="px-3 py-1.5 rounded-t-lg text-label-md flex items-center gap-1.5
           ${isOn ? 'bg-background text-primary border-x border-t border-outline-variant -mb-px' : 'text-secondary hover:text-on-surface'}">
    ${escapeHTML(label)}
    ${badge !== null ? `<span class="text-[11px] px-1.5 py-0.5 rounded-full ${isOn?'bg-primary text-white':'bg-surface-container text-secondary'}">${badge}</span>` : ''}
  </button>`;
}
function switchKbDetailTab(id) { state.kbDetail.tab = id; render(); }
function closeKbDetail() {
  if (!confirmLeaveDirty()) return;
  state.view = 'kbs';
  render();
}

/* ---- Tab 1: 文档 ---- */

function renderKbDocsTab(kb) {
  const docs = kb.docs || [];
  const selected = state.kbDetail.selectedIds;
  const allChecked = docs.length > 0 && docs.every(d => selected.has(d.id));
  return `
    <div class="flex items-center gap-2 mb-md">
      <button onclick="openKbUploadModal('${kb.id}')"
        class="px-3 py-1.5 bg-primary text-white rounded-lg flex items-center gap-1 hover:opacity-90 text-label-md">
        <span class="material-symbols-outlined text-[16px]">upload_file</span>上传文档
      </button>
      <button onclick="openKbPasteModal('${kb.id}')"
        class="px-3 py-1.5 bg-surface-container border border-outline-variant rounded-lg flex items-center gap-1 hover:bg-surface-container-low text-label-md">
        <span class="material-symbols-outlined text-[16px]">content_paste</span>粘贴文本
      </button>
      ${selected.size ? `
        <div class="ml-auto flex items-center gap-2">
          <span class="text-label-md text-secondary">已选 ${selected.size}</span>
          <button onclick="openMoveDocsModal('${kb.id}')" class="px-3 py-1.5 border border-outline-variant rounded-lg hover:bg-surface-container-low text-label-md flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">drive_file_move</span>移动到…
          </button>
          <button onclick="deleteSelectedDocs('${kb.id}')" class="px-3 py-1.5 border border-error/40 text-error rounded-lg hover:bg-error/10 text-label-md flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">delete</span>删除
          </button>
        </div>
      ` : ''}
    </div>

    ${docs.length ? `
      <div class="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
        <table class="w-full text-body-md">
          <thead class="bg-surface-container-low text-label-md text-secondary">
            <tr>
              <th class="w-10 px-3 py-2 text-left">
                <input type="checkbox" ${allChecked?'checked':''} onchange="toggleSelectAllDocs('${kb.id}', this.checked)"/>
              </th>
              <th class="px-3 py-2 text-left">文档</th>
              <th class="px-3 py-2 text-left w-20">类型</th>
              <th class="px-3 py-2 text-left w-24">大小</th>
              <th class="px-3 py-2 text-left w-20">Chunks</th>
              <th class="px-3 py-2 text-left w-32">上传时间</th>
              <th class="px-3 py-2 text-left w-44">操作</th>
            </tr>
          </thead>
          <tbody>
            ${docs.map(d => `
              <tr class="border-t border-outline-variant hover:bg-surface-container-low/50">
                <td class="px-3 py-2"><input type="checkbox" ${selected.has(d.id)?'checked':''} onchange="toggleSelectDoc('${d.id}', this.checked)"/></td>
                <td class="px-3 py-2">
                  <button onclick="openViewDocModal('${kb.id}','${d.id}')" class="text-on-surface hover:text-primary truncate text-left max-w-[300px] block">
                    <span class="material-symbols-outlined text-[14px] align-middle text-secondary mr-1">${docTypeIcon(d.fileType)}</span>${escapeHTML(d.name)}
                  </button>
                </td>
                <td class="px-3 py-2 uppercase text-label-sm text-secondary">${escapeHTML(d.fileType||'-')}</td>
                <td class="px-3 py-2 text-label-sm text-secondary">${humanSize(d.size)}</td>
                <td class="px-3 py-2 text-label-sm">${(d.chunks||[]).length}</td>
                <td class="px-3 py-2 text-label-sm text-secondary">${escapeHTML((d.uploadedAt||'').slice(5,16) || '-')}</td>
                <td class="px-3 py-2 text-label-sm">
                  <button onclick="openViewDocModal('${kb.id}','${d.id}')" class="text-primary hover:underline mr-2">查看</button>
                  <button onclick="quickMoveDoc('${kb.id}','${d.id}')" class="text-on-surface hover:underline mr-2">移动</button>
                  <button onclick="deleteDoc('${kb.id}','${d.id}')" class="text-error hover:underline">删除</button>
                </td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
    ` : `
      <div class="text-center p-xl bg-surface-container-lowest border border-outline-variant border-dashed rounded-xl">
        <span class="material-symbols-outlined text-[40px] text-secondary opacity-40 mb-2 block">cloud_upload</span>
        <p class="text-body-md text-secondary">还没有文档</p>
        <p class="text-label-sm text-secondary mt-1">点击上方「上传文档」或「粘贴文本」开始</p>
      </div>
    `}
  `;
}

function docTypeIcon(t) {
  switch ((t||'').toLowerCase()) {
    case 'pdf': return 'picture_as_pdf';
    case 'docx': case 'doc': return 'article';
    case 'xlsx': case 'xls': case 'csv': return 'table_chart';
    case 'md': return 'description';
    case 'json': return 'data_object';
    default: return 'text_snippet';
  }
}
function humanSize(n) {
  if (n == null) return '-';
  if (n < 1024) return n + ' B';
  if (n < 1024*1024) return (n/1024).toFixed(1) + ' KB';
  return (n/1024/1024).toFixed(2) + ' MB';
}
function toggleSelectDoc(id, checked) {
  if (!state.kbDetail) return;
  if (checked) state.kbDetail.selectedIds.add(id); else state.kbDetail.selectedIds.delete(id);
  render();
}
function toggleSelectAllDocs(kbId, checked) {
  const kb = state.kbs.list.find(k=>k.id===kbId);
  if (!kb) return;
  if (checked) kb.docs.forEach(d => state.kbDetail.selectedIds.add(d.id));
  else state.kbDetail.selectedIds.clear();
  render();
}
function deleteDoc(kbId, docId) {
  const kb = state.kbs.list.find(k=>k.id===kbId);
  if (!kb) return;
  const doc = kb.docs.find(d=>d.id===docId);
  if (!doc) return;
  if (!confirm(`确定删除文档「${doc.name}」？`)) return;
  kb.docs = kb.docs.filter(d=>d.id!==docId);
  kb.updatedAt = nowKbTs();
  state.kbDetail.selectedIds.delete(docId);
  saveKbs();
  render();
}
function deleteSelectedDocs(kbId) {
  const kb = state.kbs.list.find(k=>k.id===kbId);
  if (!kb) return;
  const n = state.kbDetail.selectedIds.size;
  if (!confirm(`确定删除已选 ${n} 个文档？`)) return;
  kb.docs = kb.docs.filter(d => !state.kbDetail.selectedIds.has(d.id));
  state.kbDetail.selectedIds.clear();
  kb.updatedAt = nowKbTs();
  saveKbs();
  render();
}

/* ---- 上传 Modal ---- */

function openKbUploadModal(kbId) {
  state.kbUpload = { kbId, items: [] };
  renderKbUploadModal();
}
function closeKbUploadModal() {
  const r = document.getElementById('modal-kb-upload'); if (r) r.remove();
  state.kbUpload = null;
}
function renderKbUploadModal() {
  let root = document.getElementById('modal-kb-upload');
  if (!root) { root = document.createElement('div'); root.id='modal-kb-upload'; document.body.appendChild(root); }
  const u = state.kbUpload;
  const allDone = u.items.length>0 && u.items.every(it => it.status==='ready' || it.status==='error');
  root.innerHTML = `
    <div class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onclick="if(event.target===this) closeKbUploadModal()">
      <div class="bg-surface rounded-xl shadow-2xl w-[640px] max-h-[90vh] flex flex-col overflow-hidden">
        <header class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <h3 class="text-title-lg font-headline-md">上传文档</h3>
          <button onclick="closeKbUploadModal()" class="text-secondary hover:text-on-surface"><span class="material-symbols-outlined">close</span></button>
        </header>
        <main class="px-lg py-md space-y-md overflow-y-auto">
          <label class="block border-2 border-dashed border-outline-variant rounded-xl p-lg text-center cursor-pointer hover:border-primary/60 hover:bg-primary-fixed/10 transition-colors">
            <input type="file" multiple accept=".pdf,.docx,.xlsx,.xls,.md,.txt,.json,.csv,.log" class="hidden" onchange="onKbFilesPicked(event)"/>
            <span class="material-symbols-outlined text-[36px] text-primary block mb-2">upload_file</span>
            <p class="text-body-md text-on-surface">点击或拖拽文件到此处</p>
            <p class="text-label-sm text-secondary mt-1">支持 PDF / Word(.docx) / Excel(.xlsx,.xls) / Markdown / TXT / JSON / CSV</p>
            <p class="text-label-sm text-amber-700 mt-1">⚠️ 单文件大小 ≤ 5MB</p>
          </label>
          ${u.items.length ? `
            <div class="border border-outline-variant rounded-lg overflow-hidden">
              <div class="bg-surface-container-low px-3 py-2 text-label-sm text-secondary">${u.items.length} 个文件</div>
              <ul>
                ${u.items.map((it, i) => `
                  <li class="px-3 py-2 border-t border-outline-variant flex items-center gap-2 text-label-md">
                    <span class="material-symbols-outlined text-[16px] ${it.status==='error'?'text-error':it.status==='ready'?'text-emerald-600':'text-primary'}">
                      ${it.status==='error'?'error':it.status==='ready'?'check_circle':it.status==='parsing'?'progress_activity':'pending'}
                    </span>
                    <span class="truncate flex-1">${escapeHTML(it.name)}</span>
                    <span class="text-label-sm text-secondary">${humanSize(it.size)}</span>
                    <span class="text-label-sm ${it.status==='error'?'text-error':'text-secondary'} w-40 text-right truncate" title="${escapeHTML(it.message||'')}">
                      ${escapeHTML(it.message || (it.status==='ready'?`${it.chunks} chunks`:it.status))}
                    </span>
                  </li>`).join('')}
              </ul>
            </div>
          ` : ''}
        </main>
        <footer class="px-lg py-md border-t border-outline-variant flex justify-end gap-2">
          <button onclick="closeKbUploadModal()" class="px-4 py-1.5 rounded-lg border border-outline-variant text-on-surface-variant hover:bg-surface-container-low text-label-md">${allDone?'完成':'取消'}</button>
        </footer>
      </div>
    </div>`;
}
async function onKbFilesPicked(ev) {
  const files = Array.from(ev.target.files || []);
  ev.target.value = '';
  if (!files.length) return;
  const u = state.kbUpload;
  for (const file of files) {
    const item = { name: file.name, size: file.size, status: 'uploading', message: '上传中…' };
    u.items.push(item);
    renderKbUploadModal();
    if (file.size > 10 * 1024 * 1024) {
      item.status = 'error';
      item.message = `${(file.size/1024/1024).toFixed(2)}MB > 10MB 限制`;
      showToast(`文件 "${file.name}" 超过 10MB 限制`, 'error');
      renderKbUploadModal();
      continue;
    }
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('knowledge_base', u.kbId || 'default');
      item.status = 'uploading';
      item.message = '上传并索引中…';
      renderKbUploadModal();
      const resp = await fetch(API_BASE + '/knowledge/upload', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + localStorage.getItem('agenthub_token') },
        body: formData,
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: '上传失败' }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      const result = await resp.json();
      // 将已上传的文件记录到 localStorage（保持前端一致性）
      const kb = state.kbs.list.find(k => k.id === u.kbId);
      if (kb) {
        kb.docs = kb.docs || [];
        kb.docs.push({
          id: uidKb('doc'),
          name: file.name,
          mime: file.type,
          size: file.size,
          fileType: result.filename ? result.filename.split('.').pop() : 'unknown',
          sourceType: 'file',
          chunks: result.chunks ? Array(result.chunks).fill({}) : [],
          status: 'ready',
          uploadedAt: nowKbTs(),
          backend_id: result.file_id,
        });
        kb.updatedAt = nowKbTs();
        saveKbs();
      }
      item.status = 'ready';
      item.chunks = result.chunks || 0;
      item.message = `${result.chunks || '?'} chunks 已索引`;
      showToast(`"${file.name}" 上传成功，${result.chunks} 个文本块已存入知识库`, 'success');
    } catch (e) {
      item.status = 'error';
      item.message = e.message || '上传失败';
      showToast('上传失败: ' + e.message, 'error');
    }
    renderKbUploadModal();
    if (state.view === 'kb_detail') render();
  }
  renderKbUploadModal();
}

/* ---- 粘贴文本 Modal ---- */
function openKbPasteModal(kbId) {
  state.kbPaste = { kbId, name: '', text: '' };
  renderKbPasteModal();
}
function closeKbPasteModal() {
  const r = document.getElementById('modal-kb-paste'); if (r) r.remove();
  state.kbPaste = null;
}
function renderKbPasteModal() {
  let root = document.getElementById('modal-kb-paste');
  if (!root) { root = document.createElement('div'); root.id='modal-kb-paste'; document.body.appendChild(root); }
  const p = state.kbPaste;
  root.innerHTML = `
    <div class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onclick="if(event.target===this) closeKbPasteModal()">
      <div class="bg-surface rounded-xl shadow-2xl w-[640px] max-h-[90vh] flex flex-col overflow-hidden">
        <header class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <h3 class="text-title-lg font-headline-md">粘贴文本作为文档</h3>
          <button onclick="closeKbPasteModal()" class="text-secondary hover:text-on-surface"><span class="material-symbols-outlined">close</span></button>
        </header>
        <main class="px-lg py-md space-y-md overflow-y-auto">
          <input value="${escapeHTML(p.name)}" oninput="state.kbPaste.name=this.value" placeholder="文档名称，例如 团队介绍.md"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
          <textarea rows="14" oninput="state.kbPaste.text=this.value" placeholder="把任意文本粘贴到这里…"
            class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary font-mono">${escapeHTML(p.text)}</textarea>
          <p class="text-label-sm text-secondary">字符数：${p.text.length}</p>
        </main>
        <footer class="px-lg py-md border-t border-outline-variant flex justify-end gap-2">
          <button onclick="closeKbPasteModal()" class="px-4 py-1.5 rounded-lg border border-outline-variant text-on-surface-variant hover:bg-surface-container-low text-label-md">取消</button>
          <button onclick="submitKbPaste()" class="px-4 py-1.5 rounded-lg bg-primary text-white hover:opacity-90 text-label-md">保存为文档</button>
        </footer>
      </div>
    </div>`;
}
function submitKbPaste() {
  const p = state.kbPaste;
  if (!p) return;
  if (!p.text.trim()) return showToast('内容不能为空');
  const name = (p.name || '').trim() || ('粘贴文本-' + nowKbTs().slice(5,16) + '.md');
  const kb = state.kbs.list.find(k => k.id === p.kbId);
  if (!kb) return showToast('知识库已不存在');
  if (p.text.length > KB_MAX_FILE_SIZE) {
    return showToast(`内容 ${(p.text.length/1024/1024).toFixed(2)}MB 超过 5MB 限制`, 'error');
  }
  const chunks = chunkText(p.text);
  kb.docs.push({
    id: uidKb('doc'),
    name, mime: 'text/plain', size: p.text.length,
    fileType: name.split('.').pop().toLowerCase(),
    sourceType: 'paste', rawText: p.text, chunks, status: 'ready',
    uploadedAt: nowKbTs(),
  });
  kb.updatedAt = nowKbTs();
  saveKbs();
  closeKbPasteModal();
  render();
}

/* ---- 移动 Modal ---- */
function openMoveDocsModal(kbId) {
  state.kbMove = { fromKbId: kbId, toKbId: '', docIds: [...state.kbDetail.selectedIds] };
  renderMoveDocsModal();
}
function quickMoveDoc(kbId, docId) {
  state.kbMove = { fromKbId: kbId, toKbId: '', docIds: [docId] };
  renderMoveDocsModal();
}
function closeMoveDocsModal() { const r=document.getElementById('modal-kb-move'); if(r) r.remove(); state.kbMove=null; }
function renderMoveDocsModal() {
  let root = document.getElementById('modal-kb-move');
  if (!root) { root = document.createElement('div'); root.id='modal-kb-move'; document.body.appendChild(root); }
  const m = state.kbMove;
  const others = state.kbs.list.filter(k => k.id !== m.fromKbId);
  root.innerHTML = `
    <div class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onclick="if(event.target===this) closeMoveDocsModal()">
      <div class="bg-surface rounded-xl shadow-2xl w-[460px] max-h-[80vh] flex flex-col overflow-hidden">
        <header class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <h3 class="text-title-lg font-headline-md">移动 ${m.docIds.length} 个文档到…</h3>
          <button onclick="closeMoveDocsModal()" class="text-secondary hover:text-on-surface"><span class="material-symbols-outlined">close</span></button>
        </header>
        <main class="px-lg py-md overflow-y-auto">
          ${others.length ? `
            <ul class="space-y-1">
              ${others.map(k => `
                <li>
                  <label class="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-surface-container-low cursor-pointer">
                    <input type="radio" name="kb-move-target" value="${k.id}" ${m.toKbId===k.id?'checked':''} onchange="state.kbMove.toKbId=this.value; renderMoveDocsModal()"/>
                    <span class="material-symbols-outlined text-primary text-[18px]">${escapeHTML(k.icon||'menu_book')}</span>
                    <span class="text-body-md text-on-surface">${escapeHTML(k.name)}</span>
                    <span class="text-label-sm text-secondary">${kbDocCount(k)} 文档</span>
                  </label>
                </li>`).join('')}
            </ul>
          ` : `<p class="text-body-md text-secondary text-center py-md">还没有其它知识库可选，请先新建。</p>`}
        </main>
        <footer class="px-lg py-md border-t border-outline-variant flex justify-end gap-2">
          <button onclick="closeMoveDocsModal()" class="px-4 py-1.5 rounded-lg border border-outline-variant text-on-surface-variant hover:bg-surface-container-low text-label-md">取消</button>
          <button onclick="submitMoveDocs()" ${m.toKbId?'':'disabled'} class="px-4 py-1.5 rounded-lg bg-primary text-white hover:opacity-90 text-label-md disabled:opacity-40 disabled:cursor-not-allowed">确认移动</button>
        </footer>
      </div>
    </div>`;
}
function submitMoveDocs() {
  const m = state.kbMove;
  if (!m || !m.toKbId) return;
  const from = state.kbs.list.find(k => k.id === m.fromKbId);
  const to   = state.kbs.list.find(k => k.id === m.toKbId);
  if (!from || !to) return;
  const moving = from.docs.filter(d => m.docIds.includes(d.id));
  from.docs = from.docs.filter(d => !m.docIds.includes(d.id));
  to.docs.push(...moving);
  from.updatedAt = to.updatedAt = nowKbTs();
  state.kbDetail.selectedIds.clear();
  saveKbs();
  closeMoveDocsModal();
  showToast(`已移动 ${moving.length} 个文档到「${to.name}」`, 'success');
  render();
}

/* ---- 查看文档 Modal ---- */
function openViewDocModal(kbId, docId) {
  state.kbView = { kbId, docId, mode: 'preview' };   // preview | chunks
  renderViewDocModal();
}
function closeViewDocModal() { const r=document.getElementById('modal-kb-view'); if(r) r.remove(); state.kbView=null; }
function renderViewDocModal() {
  let root = document.getElementById('modal-kb-view');
  if (!root) { root = document.createElement('div'); root.id='modal-kb-view'; document.body.appendChild(root); }
  const v = state.kbView;
  const kb = state.kbs.list.find(k=>k.id===v.kbId);
  if (!kb) return closeViewDocModal();
  const doc = (kb.docs||[]).find(d=>d.id===v.docId);
  if (!doc) return closeViewDocModal();
  const isChunks = v.mode === 'chunks';
  root.innerHTML = `
    <div class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onclick="if(event.target===this) closeViewDocModal()">
      <div class="bg-surface rounded-xl shadow-2xl w-[820px] max-h-[90vh] flex flex-col overflow-hidden">
        <header class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <div class="min-w-0">
            <h3 class="text-title-lg font-headline-md truncate">${escapeHTML(doc.name)}</h3>
            <p class="text-label-sm text-secondary mt-0.5">${escapeHTML((doc.fileType||'').toUpperCase())} · ${humanSize(doc.size)} · ${(doc.chunks||[]).length} chunks · ${escapeHTML(doc.uploadedAt||'')}</p>
          </div>
          <button onclick="closeViewDocModal()" class="text-secondary hover:text-on-surface"><span class="material-symbols-outlined">close</span></button>
        </header>
        <div class="px-lg pt-2 border-b border-outline-variant">
          <button onclick="state.kbView.mode='preview'; renderViewDocModal()"
            class="px-3 py-1.5 text-label-md ${!isChunks?'text-primary border-b-2 border-primary -mb-px':'text-secondary'}">原文预览</button>
          <button onclick="state.kbView.mode='chunks'; renderViewDocModal()"
            class="px-3 py-1.5 text-label-md ${isChunks?'text-primary border-b-2 border-primary -mb-px':'text-secondary'}">Chunks (${(doc.chunks||[]).length})</button>
        </div>
        <main class="px-lg py-md overflow-y-auto flex-1">
          ${isChunks ? `
            <ol class="space-y-2">
              ${(doc.chunks||[]).map(c => `
                <li class="border border-outline-variant rounded-lg p-2 bg-surface-container-lowest">
                  <div class="text-label-sm text-secondary mb-1">#${c.index} · ${c.tokens||0} tokens · ${c.text.length} chars</div>
                  <pre class="text-body-md whitespace-pre-wrap font-mono">${escapeHTML(c.text)}</pre>
                </li>`).join('')}
            </ol>
          ` : `
            <pre class="text-body-md whitespace-pre-wrap font-mono">${escapeHTML(doc.rawText||'(空)')}</pre>
          `}
        </main>
      </div>
    </div>`;
}

/* ---- Tab 2: 关联 Missions ---- */
function kbBoundMissions(kbId) {
  return (state.missions||[]).filter(m => (m.kbConfig?.bindings||[]).some(b => b.kbId === kbId));
}
function renderKbMissionsTab(kb) {
  const ms = kbBoundMissions(kb.id);
  if (!ms.length) {
    return `
      <div class="text-center p-xl bg-surface-container-lowest border border-outline-variant border-dashed rounded-xl">
        <span class="material-symbols-outlined text-[40px] text-secondary opacity-40 mb-2 block">link_off</span>
        <p class="text-body-md text-secondary">还没有 Mission 绑定该知识库</p>
        <p class="text-label-sm text-secondary mt-1">进入任意 Mission，在右栏「知识库」Tab 中绑定</p>
      </div>`;
  }
  return `
    <ul class="space-y-2">
      ${ms.map(m => {
        const b = m.kbConfig.bindings.find(x => x.kbId === kb.id);
        return `
          <li class="bg-surface-container-lowest border border-outline-variant rounded-lg p-3 flex items-center gap-3">
            <span class="material-symbols-outlined text-primary">flag</span>
            <div class="min-w-0 flex-1">
              <p class="text-body-md text-on-surface truncate">${escapeHTML(m.title||m.id)}</p>
              <p class="text-label-sm text-secondary">触发模式：${m.kbConfig.triggerMode==='slash'?'/ 触发':'自动'} · 启用：${b.enabled?'是':'否'} · topK=${b.topK||5}</p>
            </div>
            <button onclick="openMissionFromKb('${m.id}')" class="text-primary text-label-md hover:underline">打开 →</button>
          </li>`;
      }).join('')}
    </ul>`;
}
function openMissionFromKb(missionId) {
  if (!confirmLeaveDirty()) return;
  state.activeMissionId = missionId;
  state.view = 'mission';
  // 切到 KB tab 方便用户检查
  if (typeof state.rightTab !== 'undefined') state.rightTab = 'kbs';
  render();
}

/* ---- Tab 3: 检索测试 ---- */
function renderKbSearchTab(kb) {
  const r = state.kbDetail.searchResult;
  return `
    <div class="space-y-md">
      <div class="flex items-center gap-2">
        <input id="kb-search-test-input" value="${escapeHTML(state.kbDetail.searchQuery||'')}"
          oninput="state.kbDetail.searchQuery=this.value"
          onkeydown="if(event.key==='Enter') runKbSearchTest('${kb.id}')"
          placeholder="输入查询，例如：退款政策"
          class="flex-1 px-3 py-2 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
        <button onclick="runKbSearchTest('${kb.id}')" class="px-4 py-2 bg-primary text-white rounded-lg hover:opacity-90 text-label-md">检索</button>
      </div>
      ${r ? `
        <div class="text-label-sm text-secondary">查询「${escapeHTML(r.query)}」命中 ${r.hits.length} 条片段</div>
        <ol class="space-y-2">
          ${r.hits.map(h => `
            <li class="border border-outline-variant rounded-lg p-3 bg-surface-container-lowest">
              <div class="flex items-center gap-2 text-label-sm text-secondary mb-1">
                <span class="material-symbols-outlined text-[14px]">${docTypeIcon((kb.docs.find(d=>d.id===h.docId)||{}).fileType)}</span>
                <span class="text-on-surface">${escapeHTML(h.docName)}</span>
                <span>· chunk #${h.chunkIndex}</span>
                <span class="ml-auto text-primary">score ${h.score}</span>
              </div>
              <p class="text-body-md whitespace-pre-wrap">${highlightText(h.text, h.matchedTerms)}</p>
            </li>`).join('') || '<p class="text-secondary text-body-md p-md text-center">没有命中任何 chunk，换个查询试试</p>'}
        </ol>
      ` : `<p class="text-label-sm text-secondary">在上方输入查询，体验该 KB 的 RAG 检索效果</p>`}
    </div>`;
}
function runKbSearchTest(kbId) {
  const q = (state.kbDetail.searchQuery||'').trim();
  if (!q) return showToast('请输入查询');
  const hits = mockRagQuery({ kbIds: [kbId], query: q, topK: 8 });
  state.kbDetail.searchResult = { query: q, hits };
  render();
  setTimeout(() => document.getElementById('kb-search-test-input')?.focus(), 0);
}

/* ============================================================
   d17: Mission 右栏「知识库」Tab
============================================================ */

function renderMissionKbsTab(m, archived) {
  if (!state.kbs.loaded) loadKbs();
  const cfg = ensureMissionKbConfig(m);
  const bindings = cfg.bindings || [];
  const list = state.kbs.list || [];

  return `
    <div class="p-md space-y-md">
      <!-- 触发模式 -->
      <section class="bg-surface-container-lowest border border-outline-variant rounded-lg p-md">
        <p class="text-label-md text-on-surface font-bold mb-2 flex items-center gap-1">
          <span class="material-symbols-outlined text-[16px] text-primary">bolt</span>
          触发模式
        </p>
        <div class="grid grid-cols-2 gap-2">
          <button onclick="setMissionTriggerMode('auto')" ${archived?'disabled':''}
            class="px-3 py-2 rounded-lg border text-label-md text-left
                   ${cfg.triggerMode==='auto' ? 'border-primary bg-primary-fixed/30 text-primary' : 'border-outline-variant bg-surface-container-lowest text-on-surface hover:border-primary/40'}">
            <div class="flex items-center gap-1.5 font-bold">
              <span class="material-symbols-outlined text-[16px]">auto_awesome</span>自动
            </div>
            <p class="text-[11px] mt-1 ${cfg.triggerMode==='auto'?'text-primary':'text-secondary'}">每条消息都检索全部已启用 KB</p>
          </button>
          <button onclick="setMissionTriggerMode('slash')" ${archived?'disabled':''}
            class="px-3 py-2 rounded-lg border text-label-md text-left
                   ${cfg.triggerMode==='slash' ? 'border-primary bg-primary-fixed/30 text-primary' : 'border-outline-variant bg-surface-container-lowest text-on-surface hover:border-primary/40'}">
            <div class="flex items-center gap-1.5 font-bold">
              <span class="material-symbols-outlined text-[16px]">slash</span>/ 触发
            </div>
            <p class="text-[11px] mt-1 ${cfg.triggerMode==='slash'?'text-primary':'text-secondary'}">输入 /&lt;kb&gt; &lt;问题&gt; 才检索</p>
          </button>
        </div>
        ${cfg.triggerMode==='slash' ? `
          <div class="mt-2 p-2 rounded bg-amber-50 border border-amber-200 text-[11px] text-amber-800">
            <p class="font-bold mb-0.5">用法示例：</p>
            <p>/${escapeHTML((list.find(k=>bindings.some(b=>b.kbId===k.id&&b.enabled))||{}).name || '产品文档')} 退款政策是什么</p>
          </div>` : ''}
      </section>

      <!-- 已绑定 KB -->
      <section>
        <div class="flex items-center justify-between mb-2">
          <p class="text-label-md text-on-surface font-bold">已绑定知识库 (${bindings.length})</p>
          <button ${archived?'disabled':''} onclick="openBindKbsModal()" class="text-primary text-label-md hover:underline disabled:opacity-40 flex items-center gap-1">
            <span class="material-symbols-outlined text-[14px]">add_link</span>绑定
          </button>
        </div>
        ${bindings.length ? `
          <ul class="space-y-1.5">
            ${bindings.map(b => {
              const kb = list.find(k => k.id === b.kbId);
              if (!kb) return `
                <li class="bg-error/10 border border-error/30 rounded-lg p-2 text-label-sm text-error flex items-center gap-2">
                  <span class="material-symbols-outlined text-[14px]">error</span>
                  <span class="flex-1">知识库已不存在</span>
                  <button onclick="unbindKb('${b.kbId}')" class="hover:underline">移除</button>
                </li>`;
              return `
                <li class="bg-surface-container-lowest border border-outline-variant rounded-lg p-2">
                  <div class="flex items-center gap-2">
                    <input type="checkbox" ${b.enabled?'checked':''} ${archived?'disabled':''} onchange="toggleKbBinding('${b.kbId}', this.checked)"/>
                    <span class="material-symbols-outlined text-primary text-[16px]">${escapeHTML(kb.icon||'menu_book')}</span>
                    <button onclick="openKbDetail('${kb.id}')" class="text-body-md text-on-surface hover:text-primary truncate flex-1 text-left">${escapeHTML(kb.name)}</button>
                    <button ${archived?'disabled':''} onclick="unbindKb('${kb.id}')" class="text-secondary hover:text-error text-label-sm">移除</button>
                  </div>
                  <div class="flex items-center gap-2 mt-1.5 pl-6 text-label-sm text-secondary">
                    <span>${kbDocCount(kb)} 文档 · ${kbChunkCount(kb)} chunks</span>
                    <span class="ml-auto flex items-center gap-1">
                      topK
                      <input type="number" min="1" max="20" value="${b.topK||5}" ${archived?'disabled':''}
                        onchange="setKbBindingTopK('${kb.id}', this.value)"
                        class="w-12 px-1 py-0.5 bg-surface-container border border-outline-variant rounded text-center"/>
                    </span>
                  </div>
                </li>`;
            }).join('')}
          </ul>
        ` : `
          <div class="border border-dashed border-outline-variant rounded-lg p-md text-center text-secondary">
            <span class="material-symbols-outlined text-[28px] opacity-40 block mb-1">link_off</span>
            <p class="text-label-md">还没有绑定知识库</p>
            <button ${archived?'disabled':''} onclick="openBindKbsModal()" class="mt-2 text-primary text-label-md hover:underline">+ 立即绑定</button>
          </div>
        `}
      </section>

      <!-- 入口跳转 -->
      <section>
        <button onclick="openKnowledgePage()" class="w-full px-3 py-2 rounded-lg border border-outline-variant bg-surface-container-lowest hover:bg-surface-container text-label-md flex items-center justify-center gap-1 text-on-surface">
          <span class="material-symbols-outlined text-[16px]">menu_book</span>管理所有知识库
        </button>
      </section>
    </div>`;
}

function setMissionTriggerMode(mode) {
  const m = getMission(); if (!m) return;
  ensureMissionKbConfig(m).triggerMode = mode;
  render();
}
function toggleKbBinding(kbId, checked) {
  const m = getMission(); if (!m) return;
  const cfg = ensureMissionKbConfig(m);
  const b = cfg.bindings.find(x => x.kbId === kbId);
  if (b) { b.enabled = checked; render(); }
}
function setKbBindingTopK(kbId, v) {
  const m = getMission(); if (!m) return;
  const n = Math.max(1, Math.min(20, parseInt(v,10) || 5));
  const b = ensureMissionKbConfig(m).bindings.find(x => x.kbId === kbId);
  if (b) { b.topK = n; render(); }
}
function unbindKb(kbId) {
  const m = getMission(); if (!m) return;
  const cfg = ensureMissionKbConfig(m);
  cfg.bindings = cfg.bindings.filter(b => b.kbId !== kbId);
  render();
}

/* ---- 绑定 Modal（多选） ---- */
function openBindKbsModal() {
  if (!state.kbs.loaded) loadKbs();
  const m = getMission(); if (!m) return;
  const cfg = ensureMissionKbConfig(m);
  state.kbBind = {
    selectedIds: new Set(cfg.bindings.map(b => b.kbId)),
    search: '',
  };
  renderBindKbsModal();
}
function closeBindKbsModal() { const r=document.getElementById('modal-kb-bind'); if(r) r.remove(); state.kbBind=null; }
function renderBindKbsModal() {
  let root = document.getElementById('modal-kb-bind');
  if (!root) { root = document.createElement('div'); root.id='modal-kb-bind'; document.body.appendChild(root); }
  const s = state.kbBind;
  const q = (s.search||'').toLowerCase();
  const list = (state.kbs.list||[]).filter(k => !q || k.name.toLowerCase().includes(q));
  root.innerHTML = `
    <div class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onclick="if(event.target===this) closeBindKbsModal()">
      <div class="bg-surface rounded-xl shadow-2xl w-[520px] max-h-[80vh] flex flex-col overflow-hidden">
        <header class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <h3 class="text-title-lg font-headline-md">绑定知识库到该 Mission</h3>
          <button onclick="closeBindKbsModal()" class="text-secondary hover:text-on-surface"><span class="material-symbols-outlined">close</span></button>
        </header>
        <div class="px-lg py-2 border-b border-outline-variant">
          <input value="${escapeHTML(s.search||'')}" oninput="state.kbBind.search=this.value; renderBindKbsModal()" placeholder="搜索知识库…"
            class="w-full px-3 py-1.5 bg-surface-container-lowest border border-outline-variant rounded-lg text-body-md focus:outline-none focus:border-primary"/>
        </div>
        <main class="px-lg py-md overflow-y-auto flex-1">
          ${list.length ? `
            <ul class="space-y-1">
              ${list.map(k => `
                <li>
                  <label class="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-surface-container-low cursor-pointer">
                    <input type="checkbox" ${s.selectedIds.has(k.id)?'checked':''} onchange="toggleBindKb('${k.id}', this.checked)"/>
                    <span class="material-symbols-outlined text-primary text-[18px]">${escapeHTML(k.icon||'menu_book')}</span>
                    <span class="text-body-md text-on-surface flex-1 truncate">${escapeHTML(k.name)}</span>
                    <span class="text-label-sm text-secondary">${kbDocCount(k)} 文档</span>
                  </label>
                </li>`).join('')}
            </ul>
          ` : `
            <div class="text-center py-md">
              <p class="text-body-md text-secondary">没有可绑定的知识库</p>
              <button onclick="closeBindKbsModal(); openKnowledgePage()" class="mt-2 text-primary text-label-md hover:underline">→ 去创建一个</button>
            </div>`}
        </main>
        <footer class="px-lg py-md border-t border-outline-variant flex items-center justify-between">
          <span class="text-label-md text-secondary">已选 ${s.selectedIds.size} 个</span>
          <div class="flex gap-2">
            <button onclick="closeBindKbsModal()" class="px-4 py-1.5 rounded-lg border border-outline-variant text-on-surface-variant hover:bg-surface-container-low text-label-md">取消</button>
            <button onclick="submitBindKbs()" class="px-4 py-1.5 rounded-lg bg-primary text-white hover:opacity-90 text-label-md">确认</button>
          </div>
        </footer>
      </div>
    </div>`;
}
function toggleBindKb(kbId, checked) {
  if (checked) state.kbBind.selectedIds.add(kbId); else state.kbBind.selectedIds.delete(kbId);
  renderBindKbsModal();
}
function submitBindKbs() {
  const m = getMission(); if (!m) return;
  const cfg = ensureMissionKbConfig(m);
  const nextIds = state.kbBind.selectedIds;
  // 保留已有 bindings 的配置，新增的用默认
  const next = [];
  nextIds.forEach(id => {
    const existed = cfg.bindings.find(b => b.kbId === id);
    next.push(existed || { kbId: id, enabled: true, topK: 5 });
  });
  cfg.bindings = next;
  closeBindKbsModal();
  render();
}

/* ============================================================
   d18: sendMessage RAG / type:'rag' 折叠 / slash 触发气泡
============================================================ */

function toggleRagCollapse(idx) {
  const run = getRun(); if (!run) return;
  const msg = run.conversation[idx];
  if (msg && msg.type === 'rag') {
    msg.collapsed = msg.collapsed === false ? true : false;
    render();
  }
}

// 解析 "/kbName query"
function parseSlashCommand(text, enabledBindings) {
  const body = text.trim().slice(1);
  if (!body) {
    const names = enabledBindings.map(b => (state.kbs.list.find(k=>k.id===b.kbId) || {}).name).filter(Boolean);
    return { error: '请在 / 后输入：知识库名 + 空格 + 你的问题。例如：/' + (names[0]||'产品文档') + ' 退款政策是什么' };
  }
  const sp = body.search(/\s+/);
  const ref = sp === -1 ? body : body.slice(0, sp);
  const q   = sp === -1 ? ''   : body.slice(sp).trim();
  const kbs = state.kbs.list.filter(k => enabledBindings.some(b => b.kbId === k.id));
  const matched = kbs.find(k => k.id === ref) ||
                  kbs.find(k => k.name.toLowerCase() === ref.toLowerCase()) ||
                  kbs.find(k => k.name.toLowerCase().startsWith(ref.toLowerCase()));
  if (!matched) {
    const names = kbs.map(k => k.name).join(' / ') || '（无）';
    return { error: `未找到知识库 "${ref}"。当前已启用：${names}` };
  }
  if (!q) return { error: `请在 /${matched.name} 后输入你的问题，例如 /${matched.name} 退款政策是什么` };
  return { kbId: matched.id, query: q };
}

/* ---- / 触发气泡 ---- */
function showSlashPopover(ta, frag) {
  const m = getMission(); if (!m) return hideSlashPopover();
  const cfg = ensureMissionKbConfig(m);
  if (cfg.triggerMode !== 'slash') return hideSlashPopover();
  if (!state.kbs.loaded) loadKbs();
  const enabled = (cfg.bindings||[]).filter(b => b.enabled);
  const items = enabled.map(b => {
    const kb = state.kbs.list.find(k => k.id === b.kbId);
    return kb ? { id: kb.id, name: kb.name, icon: kb.icon||'menu_book', docs: kbDocCount(kb) } : null;
  }).filter(Boolean);
  const q = (frag||'').toLowerCase();
  const filtered = q ? items.filter(it => it.name.toLowerCase().startsWith(q) || it.name.toLowerCase().includes(q)) : items;
  state.slashPopup = { items: filtered, allItems: items, activeIndex: 0 };
  renderSlashPopover(ta);
}
function hideSlashPopover() {
  const r = document.getElementById('slash-popover'); if (r) r.remove();
  state.slashPopup = null;
}
function renderSlashPopover(ta) {
  let pop = document.getElementById('slash-popover');
  if (!pop) {
    pop = document.createElement('div');
    pop.id = 'slash-popover';
    document.body.appendChild(pop);
  }
  const s = state.slashPopup;
  const rect = ta.getBoundingClientRect();
  pop.style.cssText = `position:fixed; left:${rect.left}px; bottom:${window.innerHeight - rect.top + 6}px; width:${Math.min(360, rect.width)}px; z-index:60;`;
  if (!s || (!s.items.length && !s.allItems.length)) {
    pop.innerHTML = `
      <div class="bg-surface border border-outline-variant rounded-lg shadow-lg p-3 text-label-md text-secondary">
        当前 Mission 还没有启用的知识库。
        <button onclick="hideSlashPopover(); state.rightTab='kbs'; render();" class="text-primary hover:underline ml-1">去绑定 →</button>
      </div>`;
    return;
  }
  if (!s.items.length) {
    pop.innerHTML = `
      <div class="bg-surface border border-outline-variant rounded-lg shadow-lg p-3 text-label-md text-secondary">
        没有匹配的知识库。可用：${s.allItems.map(i => escapeHTML(i.name)).join(' / ')}
      </div>`;
    return;
  }
  pop.innerHTML = `
    <div class="bg-surface border border-outline-variant rounded-lg shadow-lg overflow-hidden text-body-md">
      <div class="px-3 py-1.5 bg-surface-container-low text-label-sm text-secondary border-b border-outline-variant flex items-center gap-1">
        <span class="material-symbols-outlined text-[14px]">menu_book</span>选择知识库（↑↓ 选择 · Enter 填充 · Esc 关闭）
      </div>
      <ul>
        ${s.items.map((it, i) => `
          <li onmouseenter="state.slashPopup.activeIndex=${i}; renderSlashPopover(document.getElementById('chat-input'))"
              onclick="selectSlashKb(${i})"
              class="flex items-center gap-2 px-3 py-1.5 cursor-pointer ${i===s.activeIndex?'bg-primary-fixed/40 text-primary':'hover:bg-surface-container-low text-on-surface'}">
            <span class="material-symbols-outlined text-primary text-[16px]">${escapeHTML(it.icon)}</span>
            <span class="flex-1 truncate">${escapeHTML(it.name)}</span>
            <span class="text-[11px] text-secondary">${it.docs} 文档</span>
          </li>`).join('')}
      </ul>
    </div>`;
}
function selectSlashKb(i) {
  const s = state.slashPopup; if (!s) return;
  const it = s.items[i]; if (!it) return;
  const ta = document.getElementById('chat-input'); if (!ta) return;
  // 找到当前 / 开头的 token，替换为 /<name> 
  const v = ta.value;
  // 期望整段以 / 开头；把 / 到第一个空白替换
  const sp = v.search(/\s/);
  const head = sp === -1 ? v : v.slice(0, sp);
  const tail = sp === -1 ? '' : v.slice(sp);
  // head 形如 "/x" 或 "/"
  const newHead = '/' + it.name;
  ta.value = newHead + ' ' + tail.replace(/^\s+/,'');
  hideSlashPopover();
  ta.focus();
  // 光标放到 newHead 之后空格之后
  const pos = newHead.length + 1;
  ta.setSelectionRange(pos, pos);
}

/* hook 进 onChatInputChange */
const _origChatChange = onChatInputChange;
onChatInputChange = function(e) {
  const ta = e.target;
  const m = getMission();
  const cfg = m ? ensureMissionKbConfig(m) : null;
  // 仅当 mission + slash 模式 + 整段以 / 开头时触发
  if (cfg && cfg.triggerMode === 'slash' && ta.value.startsWith('/')) {
    const cursor = ta.selectionStart;
    const before = ta.value.slice(0, cursor);
    const sp = before.search(/\s/);
    // 还在 head 阶段（光标在第一个空白前）
    if (sp === -1) {
      const frag = before.slice(1);    // 去掉 /
      showSlashPopover(ta, frag);
      hideMentionPopover();
      const hint = document.getElementById('input-hint');
      if (hint) hint.classList.add('hidden');
      return;
    }
  }
  hideSlashPopover();
  _origChatChange(e);
};

const _origChatKeydown = onChatInputKeydown;
onChatInputKeydown = function(e) {
  const s = state.slashPopup;
  if (s && s.items && s.items.length) {
    if (e.key === 'ArrowDown') { e.preventDefault(); s.activeIndex = (s.activeIndex+1) % s.items.length; renderSlashPopover(document.getElementById('chat-input')); return; }
    if (e.key === 'ArrowUp')   { e.preventDefault(); s.activeIndex = (s.activeIndex-1+s.items.length) % s.items.length; renderSlashPopover(document.getElementById('chat-input')); return; }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); selectSlashKb(s.activeIndex); return; }
    if (e.key === 'Escape')    { e.preventDefault(); hideSlashPopover(); return; }
  }
  _origChatKeydown(e);
};