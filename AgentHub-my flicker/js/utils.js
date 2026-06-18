/* ===== helpers ===== */
const $  = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));
const uid = (p='id') => p + '_' + Math.random().toString(36).slice(2,8);
const now = () => new Date().toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit' });
const escapeHTML = (s='') => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const escapeAttr = escapeHTML;
const escapeJS = (s='') => s.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

/** 滚动聊天区到底部（解决每次render后滚动到顶部的问题） */
function scrollChatToBottom() {
  requestAnimationFrame(() => {
    const el = document.getElementById('chat-stream');
    if (el) el.scrollTop = el.scrollHeight;
  });
}

/** 对最后一个 agent 消息气泡执行打字机动画 */
let _typingLock = false;
let _typingSkip = false;
async function typewriteLastBubble(fullText, speed = 10) {
  if (_typingLock) { _typingLock = false; await sleep(50); }
  _typingLock = true;
  _typingSkip = false;
  const stream = document.getElementById('chat-stream');
  if (!stream) { _typingLock = false; return; }
  const bubbles = Array.from(stream.querySelectorAll('.flex.justify-start'));
  const bubbleDiv = bubbles[bubbles.length - 1];
  if (!bubbleDiv) { _typingLock = false; return; }
  const textEl = bubbleDiv.querySelector('.bg-surface-container-lowest');
  if (!textEl) { _typingLock = false; return; }

  // 点击气泡可跳过打字动画
  const skipHandler = () => { _typingSkip = true; };
  bubbleDiv.addEventListener('click', skipHandler, { once: true });

  const run = getRun();
  const msg = run.conversation[run.conversation.length - 1];
  if (!msg) { _typingLock = false; return; }

  textEl.innerHTML = '';
  let displayed = '';
  
  // 长文本(>500字)使用更快速度
  const effectiveSpeed = fullText.length > 500 ? Math.max(2, speed / 2) : speed;
  
  for (let i = 0; i < fullText.length; i++) {
    if (!_typingLock || _typingSkip) break;  // 允许取消动画或跳过
    displayed += fullText[i];
    msg.text = displayed;
    textEl.innerHTML = formatMentions(displayed) + '<span class="typing-cursor">▌</span>';
    scrollChatToBottom();
    await sleep(effectiveSpeed);
  }
  msg.text = fullText;
  textEl.innerHTML = formatMentions(fullText);
  scrollChatToBottom();
  _typingLock = false;
  _typingSkip = false;
  bubbleDiv.removeEventListener('click', skipHandler);
}

/* ===== builtin skills ===== */
const BUILTIN_SKILLS = [];

/* ===== templates ===== */
const TEMPLATES = [];

/* ===== seed missions ===== */
function makeAgent(name, role, icon, prompt, skills, kind='agent') {
  return {
    id: uid('agent'), name, role, icon, systemPrompt: prompt,
    skills: skills || [],
    mcpTools: [],
    model:'GPT-4o (Omni)',
    kind,                                    // 'team' | 'agent'
    teamMemberIds: [],                       // 仅 team 用：被该 team 调度的 agent id 顺序列表
    memoryConfig: {
      strategy: 'window',                    // 'window'|'summary'|'kv'|'none'
      windowSize: 10,
      summaryPrompt: '请将以上对话内容浓缩为一段不超过 200 字的要点摘要，保留关键事实、决策与下一步。',
      kvNamespace: '',
    },
    planningConfig: {
      mode: 'react',                         // 'react'|'plan_execute'|'reflection'|'manual'
      stepsTemplate: '1. 理解任务\n2. 拆解步骤\n3. 调用工具\n4. 汇总输出',
    },
    validationConfig: {
      strategy: 'none',                      // 'none'|'self_review'|'judge_llm'|'rules'
      rules: [],
      judgePrompt: '请检查以上回答是否覆盖了用户问题的全部要点，列出 missed_points: [] 与 ok: true/false',
    },
    hooks: {
      preToolUse: '', postToolUse: '', onError: '', onComplete: '',
    },
    readme: '', versions: [], ownerId: null, updatedAt: Date.now()
  };
}

const MISSIONS = [];
