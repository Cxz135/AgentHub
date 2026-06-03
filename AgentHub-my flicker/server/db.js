// db.js — SQLite 数据库初始化（使用 better-sqlite3，同步 API，无回调地狱）
const Database = require('better-sqlite3');
const path = require('path');

const DB_PATH = path.join(__dirname, 'data.sqlite');
const db = new Database(DB_PATH);

// WAL 模式提升并发读写性能
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

// 建表（幂等）
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT    NOT NULL,
    email        TEXT    NOT NULL UNIQUE,
    password_hash TEXT   NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS skills (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    icon          TEXT    NOT NULL DEFAULT 'extension',
    description   TEXT    NOT NULL DEFAULT '',
    code          TEXT    NOT NULL DEFAULT '',
    category      TEXT    NOT NULL DEFAULT 'custom',
    author_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    author_name   TEXT    NOT NULL DEFAULT 'system',
    is_published  INTEGER NOT NULL DEFAULT 0,
    install_count INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS skill_installs (
    user_id      INTEGER NOT NULL,
    skill_id     INTEGER NOT NULL,
    installed_at TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, skill_id),
    FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE CASCADE,
    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
  );
`);

// 兼容旧库：尝试 ALTER 增字段（已存在则忽略）
function safeAlter(sql) { try { db.exec(sql); } catch (_) { /* column exists */ } }
safeAlter(`ALTER TABLE skills ADD COLUMN readme    TEXT NOT NULL DEFAULT ''`);
safeAlter(`ALTER TABLE skills ADD COLUMN versions  TEXT NOT NULL DEFAULT '[]'`);
safeAlter(`ALTER TABLE skills ADD COLUMN parent_id INTEGER`);

/* ------------------------------------------------------------ seed market */
// 启动时确保市场上至少有一批官方 demo skills
const SEED_SKILLS = [
  { slug:'news_summary', name:'news_summary', icon:'feed', category:'output',
    description:'新闻摘要：抓取多篇新闻并提炼要点',
    code:'1) 调用 web_search 收集近 24h 同主题新闻\n2) 抽取标题/摘要/来源/时间\n3) 按相似度去重并聚类\n4) 用要点列表 + 一段总结输出 Markdown',
    readme:'# news_summary\n\n用于将多篇新闻报道提炼为结构化摘要。\n\n## 输入\n- 主题关键词\n- 时间窗口（默认 24h）\n\n## 输出\n- 要点列表（去重聚类）\n- 一段总结性叙述（200~300 字）\n\n## 适用场景\n- 财经 / 行业 / 竞品监控的日报与周报' },
  { slug:'stock_kpi_extract', name:'stock_kpi_extract', icon:'monitoring', category:'data',
    description:'美股关键指标抽取：从财报/新闻中抽取关键 KPI',
    code:'输入：公司 ticker、财报 PDF\n步骤：pdf_parse → 正则匹配 EPS/Revenue/YoY → 输出结构化 JSON',
    readme:'# stock_kpi_extract\n\n从美股 10-Q / 10-K 备案文件或公开财报新闻中抽取 KPI。\n\n## 输出字段\n- EPS / Revenue / YoY / Guidance\n- 适用财报季 + 同比环比对比' },
  { slug:'image_caption', name:'image_caption', icon:'image', category:'output',
    description:'图像看图说话：上传图片，输出中文描述',
    code:'调用多模态模型 → 描述场景/物体/情绪 → 200 字内中文段落',
    readme:'# image_caption\n\n基于多模态 LLM 的看图说话。\n\n- 200 字内段落\n- 自动识别场景/物体/情绪' },
  { slug:'sql_query',   name:'sql_query',   icon:'database', category:'data',
    description:'连接到只读数据库执行 SQL 并返回结果',
    code:'1) 校验 SQL 是 SELECT\n2) 通过 readonly DSN 执行\n3) 限 1000 行返回',
    readme:'# sql_query\n\n安全的只读 SQL 查询。\n\n## 限制\n- 仅 SELECT\n- 单次最多返回 1000 行\n- 通过 readonly DSN 隔离' },
  { slug:'translate_zh_en', name:'translate_zh_en', icon:'translate', category:'output',
    description:'中英互译：保持术语与上下文风格一致',
    code:'auto-detect lang → translate via LLM with glossary hints',
    readme:'# translate_zh_en\n\n中英双向翻译，支持术语表注入。' },
  { slug:'meeting_minutes', name:'meeting_minutes', icon:'fact_check', category:'output',
    description:'会议纪要：从语音/转录文本生成结构化纪要',
    code:'speech_to_text? → 提取议题/决策/Action Item → 输出 markdown',
    readme:'# meeting_minutes\n\n会议纪要生成。\n\n## 输出结构\n- 议题列表\n- 关键决策\n- Action Items（含责任人/截止）' },
  { slug:'rss_monitor', name:'rss_monitor', icon:'rss_feed', category:'search',
    description:'RSS 监控：定时抓取 RSS 并按关键词过滤推送',
    code:'轮询 feed → 过滤 keyword → 通过 webhook 推送',
    readme:'# rss_monitor\n\n基于 RSS 的关键词监控与 webhook 推送。' },
];

const seedStmt = db.prepare(`
  INSERT OR IGNORE INTO skills (slug, name, icon, description, code, readme, category, author_name, is_published, install_count)
  VALUES (@slug, @name, @icon, @description, @code, @readme, @category, 'AgentHub 官方', 1, @install)
`);
SEED_SKILLS.forEach((s, i) => seedStmt.run({ ...s, install: 200 - i * 13 }));

// 老库回填 readme（如果之前已 seed 过，readme 字段为空字符串）
const updateReadmeStmt = db.prepare(`UPDATE skills SET readme = @readme WHERE slug = @slug AND (readme IS NULL OR readme = '')`);
SEED_SKILLS.forEach(s => updateReadmeStmt.run({ slug: s.slug, readme: s.readme }));

module.exports = db;
