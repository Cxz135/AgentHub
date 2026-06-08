// server.js — ⚠️ 已废弃 / DEPRECATED ⚠️
// ────────────────────────────────────────────────────────────────────
// 旧版 Node.js 后端（端口 3030），仅做静态托管与历史 demo。
// 当前项目统一使用 FastAPI（端口 8000）作为唯一后端：
//   - 前端 API_BASE = 'http://localhost:8000/api'
//   - LLM 调用 / Orchestrator / 统一适配器层都在 FastAPI
//   - 数据源是 backend/agenthub.db（SQLAlchemy）
//
// 本文件保留仅为「历史参考 / 故障回滚」用途，不应在生产或 demo 中启动。
// 如需运行此 server（仅供对照），请手动 `node server.js`，并自行评估数据一致性。
//
// 旧版本说明（不再维护）：
//   - 端口 3030
//   - 把上级目录（前端 index.html 所在）静态托管到 /
//   - JWT secret 硬编码（demo 用，生产请改环境变量）
// ────────────────────────────────────────────────────────────────────
const express = require('express');
const cors = require('cors');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const path = require('path');
const db = require('./db');

const app = express();
const PORT = 3030;
const JWT_SECRET = 'agenthub-demo-secret-change-in-production';
const TOKEN_TTL = '7d';

app.use(cors({ origin: ['http://localhost:5173', 'http://localhost:3030'], credentials: true }));
app.use(express.json({ limit: '256kb' }));

/* ------------------------------------------------------------------ utils */

function signToken(user) {
  return jwt.sign({ id: user.id, email: user.email }, JWT_SECRET, { expiresIn: TOKEN_TTL });
}

function publicUser(row) {
  // 隐藏密码哈希
  if (!row) return null;
  return { id: row.id, username: row.username, email: row.email, createdAt: row.created_at };
}

function auth(req, res, next) {
  const h = req.headers.authorization || '';
  const m = h.match(/^Bearer\s+(.+)$/i);
  if (!m) return res.status(401).json({ ok: false, error: 'missing_token' });
  try {
    req.userPayload = jwt.verify(m[1], JWT_SECRET);
    next();
  } catch (e) {
    return res.status(401).json({ ok: false, error: 'invalid_token' });
  }
}

function isValidEmail(v) {
  return typeof v === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
}

/* -------------------------------------------------------------- API routes */

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, ts: Date.now() });
});

app.post('/api/register', (req, res) => {
  const { username, email, password } = req.body || {};
  if (!username || username.length < 2) return res.status(400).json({ ok: false, error: 'username_too_short' });
  if (!isValidEmail(email))             return res.status(400).json({ ok: false, error: 'invalid_email' });
  if (!password || password.length < 6) return res.status(400).json({ ok: false, error: 'password_too_short' });

  const existing = db.prepare('SELECT id FROM users WHERE email = ?').get(email);
  if (existing) return res.status(409).json({ ok: false, error: 'email_already_registered' });

  const hash = bcrypt.hashSync(password, 10);
  const info = db.prepare('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)').run(username, email, hash);
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(info.lastInsertRowid);
  const token = signToken(user);
  res.json({ ok: true, user: publicUser(user), token });
});

app.post('/api/login', (req, res) => {
  const { email, password } = req.body || {};
  if (!isValidEmail(email) || !password) return res.status(400).json({ ok: false, error: 'invalid_credentials' });

  const user = db.prepare('SELECT * FROM users WHERE email = ?').get(email);
  if (!user) return res.status(401).json({ ok: false, error: 'invalid_credentials' });
  if (!bcrypt.compareSync(password, user.password_hash)) {
    return res.status(401).json({ ok: false, error: 'invalid_credentials' });
  }
  const token = signToken(user);
  res.json({ ok: true, user: publicUser(user), token });
});

app.get('/api/me', auth, (req, res) => {
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(req.userPayload.id);
  if (!user) return res.status(404).json({ ok: false, error: 'user_not_found' });
  res.json({ ok: true, user: publicUser(user) });
});

/* --------------------------------------------------------------- skills API */

function publicSkill(row, currentUserId) {
  if (!row) return null;
  let versions = [];
  try { versions = JSON.parse(row.versions || '[]'); } catch (_) {}
  return {
    id: row.id,
    slug: row.slug,
    name: row.name,
    icon: row.icon,
    description: row.description,
    code: row.code,
    readme: row.readme || '',
    category: row.category,
    authorId: row.author_id,
    authorName: row.author_name,
    parentId: row.parent_id || null,
    versions,
    isPublished: !!row.is_published,
    installCount: row.install_count,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    isMine: currentUserId != null && row.author_id === currentUserId,
  };
}

function tryAuth(req) {
  const h = req.headers.authorization || '';
  const m = h.match(/^Bearer\s+(.+)$/i);
  if (!m) return null;
  try { return jwt.verify(m[1], JWT_SECRET); } catch { return null; }
}

const SLUG_RE = /^[a-z][a-z0-9_]{1,30}$/;
const VALID_CATEGORIES = ['search', 'data', 'output', 'custom'];

function validateSkillBody(body) {
  if (!body) return 'invalid_body';
  if (!SLUG_RE.test(body.slug || '')) return 'invalid_slug';
  if (!body.name || body.name.length > 60) return 'invalid_name';
  if (!body.description || body.description.length > 200) return 'invalid_description';
  if (!body.icon || body.icon.length > 40) return 'invalid_icon';
  if (!VALID_CATEGORIES.includes(body.category)) return 'invalid_category';
  if ((body.code || '').length > 4000) return 'code_too_long';
  if ((body.readme || '').length > 8000) return 'readme_too_long';
  return null;
}

function appendVersion(row, by, snapshot, extra) {
  let arr = [];
  try { arr = JSON.parse(row.versions || '[]'); } catch(_) {}
  arr.push({
    ts: new Date().toISOString().replace('T',' ').slice(0,19),
    by: by || null,
    snapshot,
    ...(extra || {})
  });
  // 限制最多保留 50 个版本
  if (arr.length > 50) arr = arr.slice(arr.length - 50);
  return JSON.stringify(arr);
}

function snapshotOf(row) {
  return { name: row.name, icon: row.icon, description: row.description, code: row.code, readme: row.readme, category: row.category };
}

function nextAvailableSlug(base) {
  // 首选 base_copy，冲突后 _copy_2 _copy_3 ...
  const tryName = (n) => n === 1 ? `${base}_copy` : `${base}_copy_${n}`;
  let n = 1;
  while (true) {
    const slug = tryName(n);
    const ex = db.prepare('SELECT id FROM skills WHERE slug = ?').get(slug);
    if (!ex) return slug;
    n++;
    if (n > 99) return `${base}_copy_${Date.now()}`;
  }
}

// GET /api/skills/market — 公开列表（无需登录）
app.get('/api/skills/market', (req, res) => {
  const u = tryAuth(req);
  const rows = db.prepare(`
    SELECT * FROM skills WHERE is_published = 1
    ORDER BY install_count DESC, id ASC
  `).all();
  const installedSet = new Set();
  if (u) {
    db.prepare('SELECT skill_id FROM skill_installs WHERE user_id = ?').all(u.id)
      .forEach(r => installedSet.add(r.skill_id));
  }
  res.json({
    ok: true,
    skills: rows.map(r => ({ ...publicSkill(r, u && u.id), isInstalled: installedSet.has(r.id) }))
  });
});

// GET /api/skills/mine — 我创建的 + 我安装的（必须登录）
app.get('/api/skills/mine', auth, (req, res) => {
  const uid = req.userPayload.id;
  const created = db.prepare('SELECT * FROM skills WHERE author_id = ? ORDER BY id DESC').all(uid);
  const installed = db.prepare(`
    SELECT s.* FROM skills s
    JOIN skill_installs i ON i.skill_id = s.id
    WHERE i.user_id = ?
    ORDER BY i.installed_at DESC
  `).all(uid);
  // 去重
  const map = new Map();
  [...created, ...installed].forEach(r => map.set(r.id, r));
  res.json({
    ok: true,
    skills: [...map.values()].map(r => ({ ...publicSkill(r, uid), isInstalled: true }))
  });
});

// POST /api/skills — 创建（默认私有）
app.post('/api/skills', auth, (req, res) => {
  const err = validateSkillBody(req.body);
  if (err) return res.status(400).json({ ok: false, error: err });
  const uid = req.userPayload.id;
  const author = db.prepare('SELECT username FROM users WHERE id = ?').get(uid);
  const exists = db.prepare('SELECT id FROM skills WHERE slug = ?').get(req.body.slug);
  if (exists) return res.status(409).json({ ok: false, error: 'slug_taken' });

  const publish = req.body.publish ? 1 : 0;
  const initVersions = JSON.stringify([{
    ts: new Date().toISOString().replace('T',' ').slice(0,19),
    by: uid,
    snapshot: { name: req.body.name, icon: req.body.icon, description: req.body.description,
                code: req.body.code || '', readme: req.body.readme || '', category: req.body.category },
    note: 'created'
  }]);
  const info = db.prepare(`
    INSERT INTO skills (slug, name, icon, description, code, readme, category, author_id, author_name, is_published, versions)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(req.body.slug, req.body.name, req.body.icon, req.body.description,
         req.body.code || '', req.body.readme || '', req.body.category, uid, author.username, publish, initVersions);
  const row = db.prepare('SELECT * FROM skills WHERE id = ?').get(info.lastInsertRowid);
  res.json({ ok: true, skill: publicSkill(row, uid) });
});

// PUT /api/skills/:id — 编辑（仅作者）
app.put('/api/skills/:id', auth, (req, res) => {
  const id = +req.params.id;
  const row = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  if (row.author_id !== req.userPayload.id) return res.status(403).json({ ok: false, error: 'forbidden' });

  const merged = { ...row, ...req.body, slug: row.slug };
  const err = validateSkillBody(merged);
  if (err) return res.status(400).json({ ok: false, error: err });

  const newVersions = appendVersion(row, req.userPayload.id, snapshotOf(row), { note: 'before_edit' });
  db.prepare(`
    UPDATE skills SET name=?, icon=?, description=?, code=?, readme=?, category=?, versions=?, updated_at=datetime('now')
    WHERE id=?
  `).run(req.body.name, req.body.icon, req.body.description, req.body.code || '',
         req.body.readme || '', req.body.category, newVersions, id);
  const updated = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  res.json({ ok: true, skill: publicSkill(updated, req.userPayload.id) });
});

// GET /api/skills/:id — 单条详情（所有人可读，但 isMine 依赖 token）
app.get('/api/skills/:id', (req, res) => {
  const u = tryAuth(req);
  const row = db.prepare('SELECT * FROM skills WHERE id = ?').get(+req.params.id);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  res.json({ ok: true, skill: publicSkill(row, u && u.id) });
});

// POST /api/skills/:id/fork — fork 为我的副本
app.post('/api/skills/:id/fork', auth, (req, res) => {
  const id = +req.params.id;
  const uid = req.userPayload.id;
  const src = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  if (!src) return res.status(404).json({ ok: false, error: 'not_found' });
  if (src.author_id === uid) return res.status(400).json({ ok: false, error: 'already_yours' });

  const author = db.prepare('SELECT username FROM users WHERE id = ?').get(uid);
  const newSlug = nextAvailableSlug(src.slug);

  // 可选：请求体携带修改后的字段一起创建副本
  const data = {
    name: req.body.name || newSlug,
    icon: req.body.icon || src.icon,
    description: req.body.description || src.description,
    code: req.body.code != null ? req.body.code : src.code,
    readme: req.body.readme != null ? req.body.readme : src.readme,
    category: req.body.category || src.category,
  };
  const initVersions = JSON.stringify([{
    ts: new Date().toISOString().replace('T',' ').slice(0,19),
    by: uid,
    snapshot: { ...data },
    note: `forked_from:${src.slug}`
  }]);
  const info = db.prepare(`
    INSERT INTO skills (slug, name, icon, description, code, readme, category, author_id, author_name, is_published, versions, parent_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
  `).run(newSlug, data.name, data.icon, data.description, data.code, data.readme, data.category, uid, author.username, initVersions, src.id);
  const row = db.prepare('SELECT * FROM skills WHERE id = ?').get(info.lastInsertRowid);
  res.json({ ok: true, skill: publicSkill(row, uid), forkedFrom: src.id });
});

// POST /api/skills/:id/rollback — 回滚到某个版本
app.post('/api/skills/:id/rollback', auth, (req, res) => {
  const id = +req.params.id;
  const versionIndex = +req.body.versionIndex;
  const row = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  if (row.author_id !== req.userPayload.id) return res.status(403).json({ ok: false, error: 'forbidden' });
  let arr = []; try { arr = JSON.parse(row.versions || '[]'); } catch(_) {}
  if (versionIndex < 0 || versionIndex >= arr.length) return res.status(400).json({ ok: false, error: 'bad_version' });
  const target = arr[versionIndex];
  const snap = target.snapshot;
  if (!snap) return res.status(400).json({ ok: false, error: 'no_snapshot' });

  const newVersions = appendVersion(row, req.userPayload.id, snapshotOf(row), { note: `rollback_from:${versionIndex}` });
  db.prepare(`
    UPDATE skills SET name=?, icon=?, description=?, code=?, readme=?, category=?, versions=?, updated_at=datetime('now')
    WHERE id=?
  `).run(snap.name, snap.icon, snap.description, snap.code || '', snap.readme || '', snap.category, newVersions, id);
  const updated = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  res.json({ ok: true, skill: publicSkill(updated, req.userPayload.id) });
});

// POST /api/skills/:id/publish — 发布
app.post('/api/skills/:id/publish', auth, (req, res) => {
  const id = +req.params.id;
  const row = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  if (row.author_id !== req.userPayload.id) return res.status(403).json({ ok: false, error: 'forbidden' });
  db.prepare('UPDATE skills SET is_published=1, updated_at=datetime(\'now\') WHERE id=?').run(id);
  const updated = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  res.json({ ok: true, skill: publicSkill(updated, req.userPayload.id) });
});

// POST /api/skills/:id/unpublish — 撤回
app.post('/api/skills/:id/unpublish', auth, (req, res) => {
  const id = +req.params.id;
  const row = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  if (row.author_id !== req.userPayload.id) return res.status(403).json({ ok: false, error: 'forbidden' });
  db.prepare('UPDATE skills SET is_published=0, updated_at=datetime(\'now\') WHERE id=?').run(id);
  const updated = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  res.json({ ok: true, skill: publicSkill(updated, req.userPayload.id) });
});

// POST /api/skills/:id/install — 安装到我的 skill
app.post('/api/skills/:id/install', auth, (req, res) => {
  const id = +req.params.id;
  const uid = req.userPayload.id;
  const row = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  if (!row.is_published && row.author_id !== uid) return res.status(403).json({ ok: false, error: 'not_published' });

  const inserted = db.prepare('INSERT OR IGNORE INTO skill_installs (user_id, skill_id) VALUES (?, ?)').run(uid, id);
  if (inserted.changes > 0) {
    db.prepare('UPDATE skills SET install_count = install_count + 1 WHERE id = ?').run(id);
  }
  const updated = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  res.json({ ok: true, skill: { ...publicSkill(updated, uid), isInstalled: true } });
});

// DELETE /api/skills/:id — 删除（仅作者）
app.delete('/api/skills/:id', auth, (req, res) => {
  const id = +req.params.id;
  const row = db.prepare('SELECT * FROM skills WHERE id = ?').get(id);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  if (row.author_id !== req.userPayload.id) return res.status(403).json({ ok: false, error: 'forbidden' });
  db.prepare('DELETE FROM skills WHERE id = ?').run(id);
  res.json({ ok: true });
});

/* --------------------------------------------------------------- agents API */

function publicAgent(row, currentUserId) {
  if (!row) return null;
  let skills = [];
  try { skills = JSON.parse(row.skills || '[]'); } catch (_) {}
  return {
    id: row.id,
    slug: row.slug,
    name: row.name,
    icon: row.icon,
    description: row.description,
    model: row.model,
    systemPrompt: row.system_prompt,
    skills,
    authorId: row.author_id,
    authorName: row.author_name,
    isPublic: !!row.is_public,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    isMine: currentUserId != null && row.author_id === currentUserId,
  };
}

// GET /api/agents/market — 公开Agent列表
app.get('/api/agents/market', (req, res) => {
  const u = tryAuth(req);
  const rows = db.prepare(`
    SELECT * FROM agents WHERE is_public = 1
    ORDER BY id DESC
  `).all();
  res.json({
    ok: true,
    agents: rows.map(r => publicAgent(r, u && u.id))
  });
});

// GET /api/agents/mine — 我创建的Agent
app.get('/api/agents/mine', auth, (req, res) => {
  const uid = req.userPayload.id;
  const rows = db.prepare('SELECT * FROM agents WHERE author_id = ? ORDER BY updated_at DESC').all(uid);
  res.json({
    ok: true,
    agents: rows.map(r => publicAgent(r, uid))
  });
});

// POST /api/agents — 创建Agent
app.post('/api/agents', auth, (req, res) => {
  const uid = req.userPayload.id;
  const { slug, name, icon, description, model, system_prompt, skills, is_public } = req.body || {};
  if (!slug || !SLUG_RE.test(slug)) return res.status(400).json({ ok: false, error: 'invalid_slug' });
  const exists = db.prepare('SELECT id FROM agents WHERE slug = ?').get(slug);
  if (exists) return res.status(409).json({ ok: false, error: 'slug_taken' });
  
  const author = db.prepare('SELECT username FROM users WHERE id = ?').get(uid);
  const info = db.prepare(`
    INSERT INTO agents (slug, name, icon, description, model, system_prompt, skills, author_id, author_name, is_public)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(slug, name || '新Agent', icon || 'bot', description || '', model || 'qwen-plus', system_prompt || '', JSON.stringify(skills || []), uid, author.username, is_public ? 1 : 0);
  const row = db.prepare('SELECT * FROM agents WHERE id = ?').get(info.lastInsertRowid);
  res.json({ ok: true, agent: publicAgent(row, uid) });
});

// PUT /api/agents/:id — 编辑Agent（仅作者）
app.put('/api/agents/:id', auth, (req, res) => {
  const id = +req.params.id;
  const uid = req.userPayload.id;
  const row = db.prepare('SELECT * FROM agents WHERE id = ?').get(id);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  if (row.author_id !== uid) return res.status(403).json({ ok: false, error: 'forbidden' });
  
  const { name, icon, description, model, system_prompt, skills, is_public } = req.body || {};
  db.prepare(`
    UPDATE agents SET name=?, icon=?, description=?, model=?, system_prompt=?, skills=?, is_public=?, updated_at=datetime('now')
    WHERE id=?
  `).run(name || row.name, icon || row.icon, description ?? row.description, model || row.model, system_prompt ?? row.system_prompt, skills ? JSON.stringify(skills) : row.skills, is_public != null ? (is_public ? 1 : 0) : row.is_public, id);
  const updated = db.prepare('SELECT * FROM agents WHERE id = ?').get(id);
  res.json({ ok: true, agent: publicAgent(updated, uid) });
});

// DELETE /api/agents/:id — 删除Agent（仅作者）
app.delete('/api/agents/:id', auth, (req, res) => {
  const id = +req.params.id;
  const uid = req.userPayload.id;
  const row = db.prepare('SELECT * FROM agents WHERE id = ?').get(id);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  if (row.author_id !== uid) return res.status(403).json({ ok: false, error: 'forbidden' });
  db.prepare('DELETE FROM agents WHERE id = ?').run(id);
  // 同步删除该Agent下的所有对话
  db.prepare('DELETE FROM conversations WHERE agent_id = ?').run(id);
  res.json({ ok: true });
});

/* ---------------------------------------------------------- conversations API */

function publicConversation(row) {
  if (!row) return null;
  let messages = [];
  try { messages = JSON.parse(row.messages || '[]'); } catch (_) {}
  return {
    id: row.id,
    title: row.title,
    agentId: row.agent_id,
    messages,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

// GET /api/conversations/mine — 我的所有对话列表
app.get('/api/conversations/mine', auth, (req, res) => {
  const uid = req.userPayload.id;
  const rows = db.prepare('SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC').all(uid);
  res.json({
    ok: true,
    conversations: rows.map(r => publicConversation(r))
  });
});

// GET /api/conversations/:id — 单条对话详情
app.get('/api/conversations/:id', auth, (req, res) => {
  const id = +req.params.id;
  const uid = req.userPayload.id;
  const row = db.prepare('SELECT * FROM conversations WHERE id = ? AND user_id = ?').get(id, uid);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  res.json({ ok: true, conversation: publicConversation(row) });
});

// POST /api/conversations — 创建新对话
app.post('/api/conversations', auth, (req, res) => {
  const uid = req.userPayload.id;
  const { title, agent_id, messages } = req.body || {};
  const info = db.prepare(`
    INSERT INTO conversations (title, user_id, agent_id, messages) VALUES (?, ?, ?, ?)
  `).run(title || '新对话', uid, agent_id || null, JSON.stringify(messages || []));
  const row = db.prepare('SELECT * FROM conversations WHERE id = ?').get(info.lastInsertRowid);
  res.json({ ok: true, conversation: publicConversation(row) });
});

// PUT /api/conversations/:id — 更新对话（改标题/更新消息）
app.put('/api/conversations/:id', auth, (req, res) => {
  const id = +req.params.id;
  const uid = req.userPayload.id;
  const row = db.prepare('SELECT * FROM conversations WHERE id = ? AND user_id = ?').get(id, uid);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  
  const { title, messages } = req.body || {};
  db.prepare(`
    UPDATE conversations SET title=?, messages=?, updated_at=datetime('now') WHERE id=?
  `).run(title ?? row.title, messages ? JSON.stringify(messages) : row.messages, id);
  const updated = db.prepare('SELECT * FROM conversations WHERE id = ?').get(id);
  res.json({ ok: true, conversation: publicConversation(updated) });
});

// DELETE /api/conversations/:id — 删除对话
app.delete('/api/conversations/:id', auth, (req, res) => {
  const id = +req.params.id;
  const uid = req.userPayload.id;
  const row = db.prepare('SELECT * FROM conversations WHERE id = ? AND user_id = ?').get(id, uid);
  if (!row) return res.status(404).json({ ok: false, error: 'not_found' });
  db.prepare('DELETE FROM conversations WHERE id = ?').run(id);
  res.json({ ok: true });
});

/* ---------------------------------------------------------- static frontend */

// 把 /Users/.../AgentHub-my flicker 目录直接对外提供 → 同域访问 index.html
app.use(express.static(path.join(__dirname, '..')));

// SPA fallback：未匹配 API/静态文件时，返回 index.html（注意 4.x 这里只是兜底）
app.get('/', (_req, res) => {
  res.sendFile(path.join(__dirname, '..', 'index.html'));
});

/* ---------------------------------------------------------------- bootstrap */

app.listen(PORT, () => {
  console.log(`✅ AgentHub server listening on http://localhost:${PORT}`);
  console.log(`   Frontend  → http://localhost:${PORT}/index.html`);
  console.log(`   API health → http://localhost:${PORT}/api/health`);
});