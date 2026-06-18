
/* placeholders — 后续步骤填充 */
/* ===================== Mission Workspace (三栏) ===================== */
function renderMissionWorkspace() {
  const outputCollapsed = state.outputPanelCollapsed;
  const outputWidth = outputCollapsed ? 'w-[40px]' : 'flex-[2]';
  const chatFlex = outputCollapsed ? 'flex-1' : 'flex-[3]';
  const outputContent = outputCollapsed ? '' : renderOutputPanel();

  return `
    <div class="flex-1 flex overflow-hidden relative">
      <!-- Center: Chat + Output -->
      <div class="flex-1 flex min-w-0">
        <!-- Chat -->
        <div class="${chatFlex} flex flex-col border-r border-outline-variant min-w-0 bg-surface">
          ${renderChatStream()}
          ${renderChatInput()}
        </div>
        <!-- Output Panel (collapsible) -->
        <div class="${outputWidth} flex flex-col bg-surface-container-low min-w-0 border-l border-outline-variant transition-all duration-300">
          ${outputCollapsed ? `
            <div class="h-full flex flex-col items-center py-4 gap-3 cursor-pointer hover:bg-surface-container-high transition-colors"
                 onclick="state.outputPanelCollapsed=false; render()" title="展开产物面板">
              <span class="material-symbols-outlined text-secondary text-[20px] -rotate-90">expand_more</span>
              <span class="text-[10px] text-secondary writing-mode-vertical" style="writing-mode: vertical-rl;">产物面板</span>
            </div>
          ` : outputContent}
        </div>
      </div>
      <!-- Right Editor -->
      ${renderRightEditor()}
    </div>`;
}

/* ----- ChatStream ----- */
function renderChatStream() {
  const run = getRun();
  const m = getMission();
  if (!run.conversation.length) {
    return `<div class="flex-1 flex flex-col items-center justify-center text-secondary px-lg">
      <div class="w-16 h-16 rounded-full bg-primary-fixed flex items-center justify-center mb-md">
        <span class="material-symbols-outlined text-on-primary-fixed-variant text-[28px]">${m.icon}</span>
      </div>
      <p class="text-headline-md text-on-surface mb-2">${escapeHTML(m.name)}</p>
      <p class="text-body-md text-center max-w-md">${escapeHTML(m.description)}</p>
      <p class="text-label-md mt-md opacity-70">在底部输入框写下你的需求，或 @ 某个 Agent 开启协作。</p>
    </div>`;
  }

  const bubbles = run.conversation.map((msg, i) => renderBubble(msg, i)).join('');
  // Quick Run 不再自动插入保存提示卡，用户随时可点顶栏「保存为 Mission」按钮
  const quickRunSaveCard = '';

  return `
    <div id="chat-stream" class="flex-1 overflow-y-auto px-lg py-md space-y-md">
      ${bubbles}
      ${quickRunSaveCard}
    </div>`;
}

function renderMessageActions(msg, idx) {
  const hasDbId = !!msg.dbId;
  const isUser = msg.type === 'user';
  const isAgent = msg.type === 'agent';

  const actions = [];

  // 重新生成（仅 agent 消息且有 dbId）
  if (isAgent && hasDbId) {
    actions.push(`<span class="message-action-btn" onclick="event.stopPropagation(); regenerateMessage(${msg.dbId}, ${idx})" title="重新生成"><span class="material-symbols-outlined">refresh</span>重新生成</span>`);
  }

  // 引用（所有消息）
  if (hasDbId) {
    actions.push(`<span class="message-action-btn" onclick="event.stopPropagation(); quoteMessage(${msg.dbId})" title="引用"><span class="material-symbols-outlined">format_quote</span>引用</span>`);
  }

  // 展开预览（所有消息）
  if (hasDbId) {
    actions.push(`<span class="message-action-btn" onclick="event.stopPropagation(); expandMessagePreview(${msg.dbId})" title="展开预览"><span class="material-symbols-outlined">open_in_full</span>展开</span>`);
  }

  // 置顶/取消置顶（所有消息且有 dbId）
  if (hasDbId) {
    const pinIcon = msg.isPinned ? 'push_pin' : 'keep';
    const pinText = msg.isPinned ? '取消置顶' : '置顶';
    actions.push(`<span class="message-action-btn" onclick="event.stopPropagation(); toggleMessagePin(${msg.dbId}, ${idx})" title="${pinText}"><span class="material-symbols-outlined">${pinIcon}</span>${pinText}</span>`);
  }

  if (!actions.length) return '';
  const alignClass = isUser ? 'message-actions-right' : '';
  return `<div class="message-actions ${alignClass}">${actions.join('')}</div>`;
}

function renderBubble(msg, idx) {
  if (msg.type === 'user') {
    const attachments = msg.attachments || [];
    const attachmentsHtml = attachments.length > 0 ? `
      <div class="flex flex-wrap gap-2 mt-2">
        ${attachments.map(att => {
          if (att.is_image) {
            return `<div class="relative group">
              <img src="${att.url}" class="max-w-[200px] max-h-[200px] rounded-lg object-cover cursor-pointer hover:opacity-90" onclick="window.open('${att.url}', '_blank')" />
            </div>`;
          } else if (att.is_webpreview) {
            const preview = att.preview || {};
            return `<div class="w-full max-w-[320px] bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden cursor-pointer hover:bg-surface-container-low transition-colors" onclick="window.open('${att.url}', '_blank')">
              ${preview.image ? `<img src="${preview.image}" class="w-full h-[120px] object-cover" />` : ''}
              <div class="p-3">
                <div class="flex items-center gap-2 mb-1">
                  ${preview.favicon ? `<img src="${preview.favicon}" class="w-4 h-4" />` : '<span class="material-symbols-outlined text-[14px] text-secondary">travel_explore</span>'}
                  <span class="text-label-sm text-secondary truncate">${escapeHTML(preview.provider || att.url)}</span>
                </div>
                <p class="text-label-md font-bold text-on-surface truncate">${escapeHTML(preview.title || att.name)}</p>
                ${preview.description ? `<p class="text-label-sm text-secondary mt-1 line-clamp-2">${escapeHTML(preview.description)}</p>` : ''}
              </div>
            </div>`;
          } else {
            // 使用认证下载端点
            const downloadUrl = att.url.replace('/attachments/', '/api/attachments/') + '/download';
            return `<div class="flex items-center gap-2 bg-surface-container-lowest border border-outline-variant rounded-lg px-3 py-2 text-label-sm text-on-surface cursor-pointer hover:bg-surface-container-low transition-colors" onclick="downloadAttachment('${att.url}', '${escapeHTML(att.name).replace(/'/g, "\\'")}')">
              <span class="material-symbols-outlined text-[18px] text-secondary">description</span>
              <div class="flex-1 min-w-0">
                <p class="truncate text-label-md font-medium">${escapeHTML(att.name)}</p>
                <p class="text-label-sm text-secondary">${formatFileSize(att.size)}</p>
              </div>
              <span class="material-symbols-outlined text-[14px] text-secondary">download</span>
            </div>`;
          }
        }).join('')}
      </div>
    ` : '';
    return `
      <div class="flex justify-end">
        <div class="max-w-[78%] message-bubble-wrap">
          <div class="flex items-center gap-2 justify-end mb-1">
            <span class="text-label-sm text-secondary">${escapeHTML(msg.time || now())}</span>
            <span class="text-label-md font-bold text-on-surface">${escapeHTML(msg.who || 'You')}</span>
          </div>
          ${msg.text ? `<div class="bg-primary text-white rounded-2xl rounded-tr-sm px-md py-2.5 text-body-md whitespace-pre-wrap">${formatMentions(msg.text)}</div>` : ''}
          ${attachmentsHtml}
          ${renderMessageActions(msg, idx)}
        </div>
      </div>`;
  }
  if (msg.type === 'system') {
    return `<div class="flex justify-center">
      <div class="text-label-sm text-secondary bg-surface-container rounded-full px-3 py-1">${escapeHTML(msg.text)}</div>
    </div>`;
  }
  if (msg.type === 'rag') {
    const kbNames = (msg.kbIds || []).map(id => (state.kbs.list.find(k=>k.id===id) || {}).name || id).filter(Boolean);
    const collapsed = msg.collapsed !== false;
    return `
      <div class="flex justify-center">
        <div class="w-full max-w-[82%] bg-primary-fixed/20 border border-primary/30 rounded-xl overflow-hidden">
          <button onclick="toggleRagCollapse(${idx})" class="w-full px-md py-2 flex items-center gap-2 text-label-md text-on-surface hover:bg-primary-fixed/30 text-left">
            <span class="material-symbols-outlined text-[16px] text-primary">menu_book</span>
            <span class="font-bold">检索到 ${msg.hits.length} 条上下文</span>
            <span class="text-secondary">·</span>
            <span class="text-secondary truncate">${kbNames.length ? '来自 ' + escapeHTML(kbNames.join(' / ')) : ''}</span>
            <span class="ml-auto text-secondary text-[11px]">query: "${escapeHTML((msg.query||'').slice(0,28))}${(msg.query||'').length>28?'…':''}"</span>
            <span class="material-symbols-outlined text-[16px] text-secondary">${collapsed?'expand_more':'expand_less'}</span>
          </button>
          ${collapsed ? '' : `
            <ol class="px-md py-2 space-y-2 border-t border-primary/20 bg-surface-container-lowest/60 max-h-[280px] overflow-y-auto">
              ${msg.hits.map((h, i) => `
                <li class="border border-outline-variant rounded-lg p-2 bg-surface-container-lowest">
                  <div class="flex items-center gap-1 text-[11px] text-secondary mb-1">
                    <span class="text-on-surface">${escapeHTML(h.docName)}</span>
                    <span>· chunk #${h.chunkIndex}</span>
                    <span class="ml-auto text-primary">score ${h.score}</span>
                  </div>
                  <div class="text-body-md whitespace-pre-wrap text-on-surface">${highlightText((h.text||'').slice(0,400) + ((h.text||'').length>400?'…':''), h.matchedTerms)}</div>
                </li>`).join('')}
            </ol>
          `}
        </div>
      </div>`;
  }
  if (msg.type === 'artifact') {
    const artIcon = msg.artType === 'html_preview' ? 'travel_explore' : msg.artType === 'diagram' ? 'account_tree' : msg.artType === 'file' ? 'attach_file' : 'code';
    const artTitle = msg.title || 'Code';
    const lang = (msg.title && msg.title !== 'Code') ? msg.title.toLowerCase() : 'plaintext';
    const artActions = `
      <div class="flex items-center gap-1 ml-auto">
        <button onclick="navigator.clipboard.writeText(${JSON.stringify(msg.content)})" class="text-label-sm text-secondary hover:text-primary flex items-center gap-1 p-1 rounded hover:bg-surface-container" title="复制">
          <span class="material-symbols-outlined text-[14px]">content_copy</span>
        </button>
        <button onclick='openArtifactModal(${JSON.stringify({artType:msg.artType, title:msg.title, content:msg.content}).replace(/'/g, "\\'")})' class="text-label-sm text-secondary hover:text-primary flex items-center gap-1 p-1 rounded hover:bg-surface-container" title="全屏预览">
          <span class="material-symbols-outlined text-[14px]">open_in_full</span>
        </button>
      </div>`;

    if (msg.artType === 'html_preview') {
      return `<div class="flex justify-center">
        <div class="w-full max-w-[90%] bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
          <div class="flex items-center gap-2 px-md py-2 bg-surface-container border-b border-outline-variant">
            <span class="material-symbols-outlined text-[16px] text-primary">${artIcon}</span>
            <span class="text-label-md font-bold text-on-surface">${escapeHTML(artTitle)}</span>
            ${artActions}
          </div>
          <iframe srcdoc=${JSON.stringify(msg.content)} class="w-full h-[400px] border-0" sandbox="allow-scripts"></iframe>
        </div>
      </div>`;
    }
    // markdown 类型渲染为富文本预览（用 marked.js）
    // 但如果 content 是文件路径，则不渲染 markdown 内容，而是显示为文件下载卡片
    // 文件路径检测：以 / 开头，包含文件扩展名
    const _filePathPattern = /^\/[^\s]+\.[a-zA-Z0-9]+$/;
    const contentTrimmed = (msg.content || '').trim();
    const isFilePath = _filePathPattern.test(contentTrimmed);
    console.log('[ARTIFACT-DEBUG] artType:', msg.artType, 'content:', JSON.stringify(msg.content), 'isFilePath:', isFilePath);
    if (msg.artType === 'markdown' && !isFilePath) {
      const html = (typeof marked !== 'undefined') ? marked.parse(msg.content || '') : escapeHTML(msg.content);
      return `<div class="flex justify-center">
        <div class="w-full max-w-[90%] bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
          <div class="flex items-center gap-2 px-md py-2 bg-surface-container border-b border-outline-variant">
            <span class="material-symbols-outlined text-[16px] text-primary">description</span>
            <span class="text-label-md font-bold text-on-surface">${escapeHTML(artTitle)}</span>
            ${artActions}
          </div>
          <div class="markdown-body px-md py-3 overflow-y-auto max-h-[500px]">${html}</div>
        </div>
      </div>`;
    }
    // file 类型渲染为文件下载卡片
    // 同时：如果 content 是文件路径（以 /tmp 或 /var 开头），也显示为文件下载卡片
    console.log('[ARTIFACT-RENDER] artType:', msg.artType, 'content:', JSON.stringify(contentTrimmed), 'title:', msg.title);
    if (msg.artType === 'file' || (msg.artType === 'markdown' && isFilePath) || (msg.artType === 'code' && isFilePath)) {
      const fileUrl = msg.content || msg.fileMeta?.url || '';
      const fileName = msg.title || msg.fileMeta?.name || fileUrl.split('/').pop() || '下载文件';
      const fileSize = msg.fileMeta?.size ? formatFileSize(msg.fileMeta.size) : '';
      const isPdf = fileName.toLowerCase().endsWith('.pdf');
      return `<div class="flex justify-center">
        <div class="w-full max-w-[90%] bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
          <div class="flex items-center gap-3 px-4 py-3 bg-surface-container border-b border-outline-variant">
            <span class="material-symbols-outlined text-[24px] text-primary">${isPdf ? 'picture_as_pdf' : 'description'}</span>
            <div class="flex-1 min-w-0">
              <a href="#" onclick="event.preventDefault(); downloadArtifactByUrl('${escapeJS(fileUrl)}', '${escapeJS(fileName)}')"
                 class="text-primary hover:underline font-medium truncate block" title="点击下载">
                ${escapeHTML(fileName)}
              </a>
              ${fileSize ? `<span class="text-[12px] text-secondary">${fileSize}</span>` : ''}
            </div>
            <button onclick="downloadArtifactByUrl('${escapeJS(fileUrl)}', '${escapeJS(fileName)}')"
              class="px-3 py-1.5 bg-primary text-white text-sm rounded-lg hover:opacity-90 flex items-center gap-1.5 shrink-0">
              <span class="material-symbols-outlined text-[16px]">download</span>
              <span>下载</span>
            </button>
          </div>
        </div>
      </div>`;
    }
    // diagram 类型：Mermaid/Graphviz 渲染
    if (msg.artType === 'diagram') {
      const mermaidId = 'mermaid-' + Math.random().toString(36).slice(2, 8);
      return `<div class="flex justify-center">
        <div class="w-full max-w-[90%] bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
          <div class="flex items-center gap-2 px-md py-2 bg-surface-container border-b border-outline-variant">
            <span class="material-symbols-outlined text-[16px] text-primary">account_tree</span>
            <span class="text-label-md font-bold text-on-surface">${escapeHTML(artTitle)}</span>
            <div class="flex items-center gap-1 ml-auto">
              <button onclick="navigator.clipboard.writeText(${JSON.stringify(msg.content)})" class="text-label-sm text-secondary hover:text-primary flex items-center gap-1 p-1 rounded hover:bg-surface-container" title="复制源码">
                <span class="material-symbols-outlined text-[14px]">content_copy</span>
              </button>
              <button onclick='openArtifactModal(${JSON.stringify({artType:"diagram", title:msg.title, content:msg.content}).replace(/'/g, "\\'")})' class="text-label-sm text-secondary hover:text-primary flex items-center gap-1 p-1 rounded hover:bg-surface-container" title="全屏预览">
                <span class="material-symbols-outlined text-[14px]">open_in_full</span>
              </button>
            </div>
          </div>
          <div class="p-md bg-white flex justify-center overflow-x-auto">
            <div class="mermaid-diagram" id="${mermaidId}" data-content="${escapeHTML(msg.content)}" style="min-width:300px"></div>
          </div>
        </div>
      </div>`;
    }
    // diff 类型：差异对比渲染
    if (msg.artType === 'diff') {
      return `<div class="flex justify-center">
        <div class="w-full max-w-[90%] bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
          <div class="flex items-center gap-2 px-md py-2 bg-surface-container border-b border-outline-variant">
            <span class="material-symbols-outlined text-[16px] text-primary">difference</span>
            <span class="text-label-md font-bold text-on-surface">${escapeHTML(artTitle)}</span>
            ${artActions}
          </div>
          <pre class="px-md py-2.5 text-body-sm font-mono whitespace-pre-wrap overflow-x-auto max-h-[400px] overflow-y-auto diff-view"><code>${renderDiff(msg.content)}</code></pre>
        </div>
      </div>`;
    }
    return `<div class="flex justify-center">
      <div class="w-full max-w-[90%] bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
        <div class="flex items-center gap-2 px-md py-2 bg-surface-container border-b border-outline-variant">
          <span class="material-symbols-outlined text-[16px] text-primary">${artIcon}</span>
          <span class="text-label-md font-bold text-on-surface">${escapeHTML(artTitle)}</span>
          ${artActions}
        </div>
        <pre class="px-md py-2.5 text-body-sm font-mono whitespace-pre-wrap overflow-x-auto max-h-[400px] overflow-y-auto text-on-surface"><code class="language-${lang}">${escapeHTML(msg.content)}</code></pre>
      </div>
    </div>`;
  }
  if (msg.type === 'diff-card') {
    return `<div class="flex justify-center">
      <div class="bg-primary-fixed/30 border border-primary/30 rounded-xl px-md py-2.5 text-label-md text-on-primary-fixed flex items-center gap-2 cursor-pointer hover:bg-primary-fixed/60"
           onclick='openAgentDiff(${JSON.stringify(msg.payload).replace(/'/g,"\\'")})'>
        <span class="material-symbols-outlined text-[16px]">difference</span>
        <span>Coordinator 提议：${escapeHTML(msg.summary)}</span>
        <span class="font-bold ml-2">查看变更 →</span>
      </div>
    </div>`;
  }
  // agent message
  const thinkingClass = msg.thinking ? ' thinking-pulse' : '';
  // 检测是否为 markdown 内容（包含标题/列表/代码围栏/引用/分隔线/图片等）
  function isMarkdown(text) {
    return /^#{1,6}\s|^\s*[-*]\s|^\s*\d+\.\s|^\s*>\s|^\s*[-*]{3,}$|^\s*```|!\[[^\]]*\]\([^)]+\)/m.test(text);
  }
  function renderAgentText(text) {
    // 检测反问内容：Agent 反问机制在回复前追加"为了给出更准确的答案，我需要确认..."
    if (text.includes('为了给出更准确的答案，我需要确认')) {
      const parts = text.split('**我的初步回答');
      if (parts.length >= 2) {
        const clarificationPart = parts[0].trim();
        const answerPart = parts.slice(1).join('**我的初步回答').trim();
        // 追问部分：提取编号列表
        const clarificationHtml = `<div class="clarification-box">${formatMentions(clarificationPart)}</div>`;
        // 分割线
        const divider = '<hr class="clarification-divider"/>';
        // 回答部分
        const answerHtml = answerPart ? (isMarkdown(answerPart) ? `<div class="markdown-body">${marked.parse(answerPart)}</div>` : `<div class="whitespace-pre-wrap">${formatMentions(answerPart)}</div>`) : '';
        return clarificationHtml + divider + answerHtml;
      }
    }
    if (isMarkdown(text)) {
      const html = marked.parse(text);
      return `<div class="markdown-body">${html}</div>`;
    }
    return `<div class="whitespace-pre-wrap">${formatMentions(text)}</div>`;
  }
  return `
    <div class="flex justify-start${thinkingClass}">
      <div class="max-w-[82%] message-bubble-wrap">
        <div class="flex items-center gap-2 mb-1">
          <div class="w-6 h-6 rounded-full bg-secondary-container flex items-center justify-center">
            <span class="material-symbols-outlined text-on-surface-variant text-[14px]">${msg.icon || 'smart_toy'}</span>
          </div>
          <span class="text-label-md font-bold text-on-surface">${escapeHTML(msg.agent || 'Agent')}</span>
          <span class="text-label-sm text-secondary">${escapeHTML(msg.time || now())}</span>
        </div>
        <div class="bg-surface-container-lowest border border-outline-variant rounded-2xl rounded-tl-sm px-md py-2.5 text-body-md text-on-surface">${renderAgentText(msg.text || '')}</div>
        ${msg.tool ? `
          <details class="mt-1.5 bg-surface-container border border-outline-variant rounded-lg overflow-hidden text-label-md">
            <summary class="cursor-pointer flex items-center gap-2 px-3 py-2 hover:bg-surface-container-high">
              <span class="material-symbols-outlined text-secondary text-[14px]">terminal</span>
              <span class="font-mono text-secondary">${escapeHTML(msg.tool.name)}</span>
            </summary>
            <pre class="px-3 py-2 bg-inverse-surface text-inverse-on-surface text-[11px] font-mono whitespace-pre-wrap leading-relaxed">${escapeHTML(msg.tool.log)}</pre>
          </details>` : ''}
        ${renderMessageActions(msg, idx)}
      </div>
    </div>`;
}

function formatMentions(text='') {
  // 把 @AgentName / #AgentName 渲染成 chip
  const m = getMission();
  if (!m) return escapeHTML(text);
  let html = escapeHTML(text);
  m.squad.agents.forEach(a => {
    const safeName = a.name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    // # 模式：橙色编辑 chip
    html = html.replace(new RegExp('#' + safeName, 'g'),
      `<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px] font-medium bg-primary text-white"><span class="material-symbols-outlined text-[11px]">edit_square</span>${escapeHTML(a.name)}</span>`);
    // @ 模式：原蓝色 chip
    html = html.replace(new RegExp('@' + safeName, 'g'),
      `<span class="mention-chip">@${escapeHTML(a.name)}</span>`);
  });
  return html;
}

function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

/* ----- ChatInput ----- */
function renderChatInput() {
  const attachments = state.pendingAttachments || [];
  const attachmentChips = attachments.length > 0 ? `
    <div class="flex flex-wrap gap-2 mb-2 px-md">
      ${attachments.map((att, idx) => `
        <div class="flex items-center gap-1.5 bg-surface-container-low border border-outline-variant rounded-lg px-2 py-1 text-label-sm">
          ${att.is_image ? `<img src="${att.url}" class="w-5 h-5 rounded object-cover" />` : `<span class="material-symbols-outlined text-[14px] text-secondary">${att.is_webpreview ? 'travel_explore' : 'description'}</span>`}
          <span class="truncate max-w-[120px] text-on-surface">${escapeHTML(att.name || '附件')}</span>
          <button onclick="removeAttachment(${idx})" class="p-0.5 rounded hover:bg-surface-container text-secondary">
            <span class="material-symbols-outlined text-[14px]">close</span>
          </button>
        </div>
      `).join('')}
    </div>
  ` : '';

  return `
    <div class="border-t border-outline-variant px-lg py-md bg-surface">
      <div class="bg-surface-container-lowest border border-outline-variant focus-within:border-primary rounded-xl px-md py-2.5 transition-colors">
        ${attachmentChips}
        <textarea id="chat-input" rows="2"
          oninput="onChatInputChange(event)"
          onkeydown="onChatInputKeydown(event)"
          onpaste="onChatInputPaste(event)"
          placeholder="输入消息 · 用 @ 指定 Agent 进行对话 · 用 # 直接修改 Agent 配置（如 #数据分析师 加 web_search 技能）"
          class="w-full bg-transparent border-0 focus:ring-0 resize-none text-body-md p-0 placeholder:text-secondary"></textarea>
        <input type="file" id="chat-file-input" class="hidden" onchange="handleChatFileUpload(event)" />
        <div class="flex items-center justify-between pt-2 border-t border-outline-variant/60 mt-2">
          <div class="flex items-center gap-1 text-secondary">
            <button class="p-1 rounded hover:bg-surface-container-low" title="附件" onclick="$('#chat-file-input').click()">
              <span class="material-symbols-outlined text-[18px]">${attachments.length > 0 ? 'attach_file' : 'attach_file'}</span>
            </button>
            <button class="p-1 rounded hover:bg-surface-container-low" title="@ 指定 Agent 进行对话" onclick="insertTrigger('@')"><span class="material-symbols-outlined text-[18px]">alternate_email</span></button>
            <button class="p-1 rounded hover:bg-surface-container-low text-primary" title="# 直接修改 Agent 配置" onclick="insertTrigger('#')"><span class="material-symbols-outlined text-[18px]">edit_square</span></button>
            <button class="p-1 rounded hover:bg-surface-container-low" title="语音"><span class="material-symbols-outlined text-[18px]">mic</span></button>
            <button class="relative p-1.5 rounded-lg hover:bg-surface-container-low transition-colors ${(state.activeSkills&&state.activeSkills.length)>0?'bg-primary/10 text-primary':'text-secondary'}" title="技能管理" onclick="toggleSkillPanel()">
              <span class="material-symbols-outlined text-[18px]">auto_awesome</span>
              ${(state.activeSkills&&state.activeSkills.length)>0?'<span class="absolute -top-0.5 -right-0.5 w-4 h-4 bg-primary text-white text-[10px] font-bold rounded-full flex items-center justify-center">'+state.activeSkills.length+'</span>':''}
            </button>
            <span id="input-hint" class="ml-2 text-label-sm hidden"></span>
            <span class="ml-2 hidden md:inline-flex items-center gap-2 text-[10px] text-secondary">
              <span class="inline-flex items-center gap-0.5"><kbd class="px-1 py-0.5 rounded bg-surface-container border border-outline-variant text-[10px] font-mono">@</kbd>对话</span>
              <span class="inline-flex items-center gap-0.5"><kbd class="px-1 py-0.5 rounded bg-primary-fixed text-on-primary-fixed-variant border border-primary/30 text-[10px] font-mono">#</kbd>改 Agent</span>
            </span>
          </div>
          <button onclick="sendChat()" class="bg-primary text-white px-3 py-1.5 rounded-lg flex items-center gap-1.5 hover:opacity-90 text-label-md">
            <span>发送</span>
            <span class="material-symbols-outlined text-[16px]">send</span>
          </button>
        </div>
      </div>
     </div>`;
}

/* ----- Chat Attachments & URL Preview ----- */

function removeAttachment(idx) {
  state.pendingAttachments.splice(idx, 1);
  render();
}

async function handleChatFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  // 重置 input 以便可以重复选择同一文件
  event.target.value = '';

  const maxSize = 20 * 1024 * 1024; // 20MB
  if (file.size > maxSize) {
    showToast('文件大小超过 20MB 限制', 'error');
    return;
  }

  const allowedExts = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.pdf', '.txt', '.md', '.docx', '.xlsx', '.pptx', '.csv', '.json', '.zip', '.mp3', '.mp4', '.wav', '.webm', '.mov'];
  const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
  if (!allowedExts.includes(ext)) {
    showToast('不支持的文件类型: ' + ext, 'error');
    return;
  }

  // 先显示本地占位
  const localUrl = URL.createObjectURL(file);
  const isImage = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'].includes(ext);
  state.pendingAttachments.push({
    name: file.name,
    size: file.size,
    type: file.type,
    is_image: isImage,
    url: localUrl,
    is_local: true,
    file: file,
  });
  render();

  // 上传到后端
  try {
    const formData = new FormData();
    formData.append('file', file);
    const resp = await fetch(API_BASE + '/upload', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('agenthub_token') || '') },
      body: formData,
    });
    const data = await resp.json();
    if (data && data.ok && data.file) {
      // 替换为服务器 URL
      const att = state.pendingAttachments.find(a => a.name === file.name && a.is_local);
      if (att) {
        att.url = data.file.url;
        att.is_local = false;
        att.is_image = data.file.is_image;
        att.mime_type = data.file.mime_type;
        delete att.file;
      }
      showToast('文件上传成功', 'success');
      render();
    } else {
      showToast('文件上传失败: ' + (data.error || '未知错误'), 'error');
    }
  } catch (e) {
    console.error('上传失败:', e);
    showToast('文件上传失败: ' + e.message, 'error');
  }
}

function onChatInputPaste(event) {
  // 延迟检测粘贴内容中的 URL
  setTimeout(() => {
    const ta = $('#chat-input');
    if (!ta) return;
    const text = ta.value;
    detectAndPreviewUrls(text);
  }, 0);
}

function detectAndPreviewUrls(text) {
  const urlRegex = /https?:\/\/[^\s\])>"'`]+/g;
  const urls = text.match(urlRegex);
  if (!urls) return;

  // 过滤掉已经添加过的 URL
  const existingUrls = new Set((state.pendingAttachments || []).filter(a => a.is_webpreview).map(a => a.url));
  const newUrls = urls.filter(u => !existingUrls.has(u));

  newUrls.forEach(url => {
    fetchUrlPreview(url);
  });
}

async function fetchUrlPreview(url) {
  try {
    const formData = new FormData();
    formData.append('url', url);
    const resp = await fetch(API_BASE + '/preview', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('agenthub_token') || '') },
      body: formData,
    });
    const data = await resp.json();
    if (data && data.ok && data.preview) {
      state.pendingAttachments.push({
        name: data.preview.title || url,
        url: url,
        is_webpreview: true,
        preview: data.preview,
      });
      render();
    }
  } catch (e) {
    console.warn('URL 预览获取失败:', e);
  }
}

/* ----- Output Panel ----- */
function renderOutputPanel() {
  const run = getRun();

  // 实时扫描所有 agent 消息的文本，提取代码块
  // 同一消息中多个代码块，只取最大的（按行数）
  const artifacts = [];
  (run.conversation || []).forEach(msg => {
    if (msg.type === 'agent' && msg.text) {
      const extracted = extractArtifactsFromText(msg.text);
      if (extracted.length > 1) {
        // 同消息多个代码块：按行数排序，取最大的，同时过滤短片段
        extracted.sort((a, b) => (b.content || '').split('\n').length - (a.content || '').split('\n').length);
        const largest = extracted[0];
        // 只有最大的那个代码块超过 5 行，才纳入产物；否则跳过（避免示例片段）
        if (largest.content.split('\n').length >= 5) {
          artifacts.push({ ...largest, agent: msg.agent });
        }
      } else if (extracted.length === 1) {
        // 单一代码块，如果长度超过 3 行才纳入
        if (extracted[0].content.split('\n').length >= 3) {
          artifacts.push({ ...extracted[0], agent: msg.agent });
        }
      }
    }
    // 扫描消息中的附件（图片、文件、网页预览）也纳入产物
    if (msg.attachments && msg.attachments.length > 0) {
      msg.attachments.forEach(att => {
        if (att.is_image) {
          artifacts.push({
            artType: 'image',
            title: att.name || '图片',
            content: att.url,
            agent: msg.agent || msg.who,
            description: '图片文件',
            fileMeta: att
          });
        } else if (att.is_webpreview) {
          artifacts.push({
            artType: 'webcard',
            title: att.preview?.title || att.name || '网页链接',
            content: att.url,
            agent: msg.agent || msg.who,
            description: att.preview?.provider || '网页链接',
            preview: att.preview,
            fileMeta: att
          });
        } else {
          // 普通文件
          artifacts.push({
            artType: 'file',
            title: att.name || '文件',
            content: att.url,
            agent: msg.agent || msg.who,
            description: (att.mime_type || '文件').split('/').pop() || '附件',
            fileMeta: att
          });
        }
      });
    }
    // 扫描 WebSocket 推送的 artifact 消息
    if (msg.type === 'artifact') {
      artifacts.push({
        artType: msg.artType || 'file',
        title: msg.title || '文件',
        content: msg.content || '',
        agent: msg.agent || 'orchestrator',
        description: msg.artType === 'file' ? '文件下载' : (msg.artType || '产物'),
        fileMeta: msg.fileMeta
      });
    }
  });

  // 去重：相同的 content 只保留一个
  const seen = new Set();
  const uniqueArtifacts = [];
  artifacts.forEach(art => {
    const key = art.content && art.content.trim ? art.content.trim().slice(0, 200) : JSON.stringify(art);
    if (!seen.has(key)) {
      seen.add(key);
      uniqueArtifacts.push(art);
    }
  });

  // 存入全局状态，供卡片按钮引用
  state._artifacts = uniqueArtifacts;

  const hasArtifacts = uniqueArtifacts.length > 0;

  let body = '';
  if (!hasArtifacts) {
    body = `<div class="flex-1 flex flex-col items-center justify-center text-secondary p-lg text-center">
      <span class="material-symbols-outlined text-[40px] opacity-40 mb-2">draft</span>
      <p class="text-body-md">运行启动后，产物（代码 / 文档 / 网页 / 文件）将出现在这里。</p>
      <p class="text-label-sm text-secondary mt-2">Agent 回复中的代码块和上传的文件都会自动提取到这里</p>
    </div>`;
  } else {
    body = `<div class="flex-1 overflow-y-auto p-md space-y-md">
      ${uniqueArtifacts.map((art, i) => renderArtifactCard(i, art)).join('')}
    </div>`;
  }

  return `
    <div class="h-[48px] border-b border-outline-variant px-md flex items-center gap-1 shrink-0 bg-surface-container-low">
      <span class="text-label-md font-bold text-on-surface flex items-center gap-2">
        <span class="material-symbols-outlined text-[18px] text-primary">inventory_2</span>
        产物
        ${uniqueArtifacts.length > 0 ? `<span class="text-[10px] px-1.5 py-0.5 rounded-full bg-primary text-white font-bold">${uniqueArtifacts.length}</span>` : ''}
      </span>
      <div class="ml-auto flex items-center gap-1 text-secondary">
        <button onclick="state.outputPanelCollapsed=true; render()" class="p-1.5 rounded hover:bg-surface-container" title="收起产物面板">
          <span class="material-symbols-outlined text-[18px]">chevron_right</span>
        </button>
      </div>
    </div>
    ${body}`;
}

/* ----- Extract code blocks from agent text ----- */
function extractArtifactsFromText(text) {
  if (!text) return [];
  const artifacts = [];
  const codeBlockRegex = /```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g;
  let match;
  while ((match = codeBlockRegex.exec(text)) !== null) {
    const language = match[1].trim() || 'plaintext';
    const code = match[2];
    if (code.trim().length > 0) {
      const lang = language.toLowerCase();
      let artType = 'code';
      let renderMode = 'code'; // code | iframe | markdown | mermaid | table | diff
      if (lang === 'html' || lang === 'htm') {
        artType = 'html_preview';
        renderMode = 'iframe';
      } else if (lang === 'markdown' || lang === 'md') {
        artType = 'markdown';
        renderMode = 'markdown';
      } else if (lang === 'mermaid' || lang === 'graphviz') {
        artType = 'diagram';
        renderMode = 'mermaid';
      } else if (lang === 'diff') {
        artType = 'diff';
        renderMode = 'diff';
      }
      artifacts.push({
        artType: artType,
        title: language,
        content: code.trim(),
        renderMode: renderMode,
        description: inferArtifactDescription(language, code.trim())
      });
    }
  }
  return artifacts;
}

/* 从代码内容推断描述 */
function inferArtifactDescription(language, code) {
  const lang = (language || '').toLowerCase();
  
  // 尝试提取函数名（Python, JavaScript, Java, C, Go 等）
  const funcMatch = code.match(/(?:def|function|func|void|int|String)\s+(\w+)/);
  const funcName = funcMatch ? funcMatch[1] : null;
  
  // 尝试提取类名
  const classMatch = code.match(/(?:class|struct|interface)\s+(\w+)/);
  const className = classMatch ? classMatch[1] : null;
  
  // 尝试提取注释中的描述
  const commentLines = [];
  const lines = code.split('\n');
  for (let line of lines.slice(0, 10)) {
    const comment = line.match(/(?:#|\/\/|\/\*|\*)\s*(.+)/);
    if (comment && comment[1].trim().length > 3 && !comment[1].includes('import')) {
      commentLines.push(comment[1].trim());
    }
  }
  
  // 构建描述
  let parts = [];
  
  // 语言标签
  if (lang && lang !== 'plaintext') {
    parts.push(lang.charAt(0).toUpperCase() + lang.slice(1));
  }
  
  // 功能识别
  let purpose = '';
  const codeLower = code.toLowerCase();
  if (codeLower.includes('sort') && codeLower.includes('quick')) purpose = '快速排序';
  else if (codeLower.includes('sort') && codeLower.includes('merge')) purpose = '归并排序';
  else if (codeLower.includes('sort')) purpose = '排序算法';
  else if (codeLower.includes('search') || codeLower.includes('find')) purpose = '查找算法';
  else if (codeLower.includes('fibonacci')) purpose = '斐波那契数列';
  else if (codeLower.includes('classifier') || codeLower.includes('predict')) purpose = '机器学习模型';
  else if (codeLower.includes('http') || codeLower.includes('request') || codeLower.includes('server')) purpose = '网络服务';
  else if (codeLower.includes('database') || codeLower.includes('sql')) purpose = '数据库操作';
  else if (codeLower.includes('react') || codeLower.includes('component')) purpose = 'React组件';
  else if (codeLower.includes('css') || codeLower.includes('style')) purpose = '样式文件';
  else if (codeLower.includes('test') || codeLower.includes('spec')) purpose = '测试代码';
  
  if (purpose) parts.push(purpose);
  
  // 函数/类名
  if (funcName) parts.push(`${funcName}()`);
  else if (className) parts.push(`class ${className}`);
  
  // 注释补充
  if (commentLines.length > 0 && parts.length < 3) {
    const shortComment = commentLines[0].slice(0, 40);
    if (shortComment.length > 5) parts.push(shortComment);
  }
  
  return parts.length > 0 ? parts.join(' · ') : '代码片段';
}

function getArtifactKey(art) {
  // 生成产物唯一标识
  if (art.content && art.content.trim) {
    return art.content.trim().slice(0, 200);
  }
  return JSON.stringify(art);
}

function isStarredArtifact(art) {
  const m = getMission();
  if (!m) return false;
  const key = getArtifactKey(art);
  const starred = state.starredArtifacts[m.id] || [];
  return starred.includes(key);
}

function toggleStarArtifact(idx) {
  const art = state._artifacts && state._artifacts[idx];
  if (!art) return;
  const m = getMission();
  if (!m) return;
  const key = getArtifactKey(art);
  if (!state.starredArtifacts[m.id]) {
    state.starredArtifacts[m.id] = [];
  }
  const starred = state.starredArtifacts[m.id];
  const pos = starred.indexOf(key);
  if (pos === -1) {
    starred.push(key);
    showToast('已收藏产物', 'success');
  } else {
    starred.splice(pos, 1);
    showToast('已取消收藏', 'info');
  }
  // 异步保存到后端
  saveStarredArtifacts(m.id, starred);
  render();
}

async function saveStarredArtifacts(missionId, starredKeys) {
  try {
    const convId = missionId.replace('mis_', '');
    await api(`/missions/${convId}/starred-artifacts`, {
      method: 'POST',
      body: JSON.stringify({ starred_artifacts: starredKeys })
    });
  } catch (e) {
    console.warn('保存收藏失败:', e);
  }
}

function renderArtifactCard(idx, art) {
  const artTitle = art.title || 'Code';
  const lang = (art.title && art.title !== 'Code') ? art.title.toLowerCase() : 'plaintext';
  const renderMode = art.renderMode || 'code';
  const artType = art.artType || 'code';
  const description = art.description || '';
  const isStarred = isStarredArtifact(art);
  
  // 根据类型选择图标
  let artIcon = 'code';
  if (artType === 'image') artIcon = 'image';
  else if (artType === 'file') artIcon = 'description';
  else if (artType === 'webcard') artIcon = 'travel_explore';
  else if (artType === 'diagram' || renderMode === 'mermaid') artIcon = 'account_tree';
  else if (artType === 'diff') artIcon = 'difference';
  else if (renderMode === 'iframe') artIcon = 'web';
  else if (renderMode === 'markdown') artIcon = 'description';
  
  // 根据类型选择操作按钮
  let actionBtns = '';
  
  // 收藏按钮（所有类型都支持）
  const starBtn = `<button onclick="toggleStarArtifact(${idx})" class="p-1 rounded hover:bg-surface-container ${isStarred ? 'text-primary' : 'text-secondary'}" title="${isStarred ? '已收藏' : '收藏'}">
        <span class="material-symbols-outlined text-[14px]">${isStarred ? 'star' : 'star_border'}</span>
      </button>`;
  
  if (artType === 'image') {
    actionBtns = `
      ${starBtn}
      <button onclick="downloadArtifact(${idx})" class="p-1 rounded hover:bg-surface-container text-secondary" title="下载">
        <span class="material-symbols-outlined text-[14px]">download</span>
      </button>
      <button onclick="openArtifactModal(${idx})" class="p-1 rounded hover:bg-surface-container text-secondary" title="查看大图">
        <span class="material-symbols-outlined text-[14px]">open_in_full</span>
      </button>`;
  } else if (artType === 'file') {
    actionBtns = `
      ${starBtn}
      <button onclick="downloadArtifact(${idx})" class="p-1 rounded hover:bg-surface-container text-secondary" title="下载">
        <span class="material-symbols-outlined text-[14px]">download</span>
      </button>
      <button onclick="openArtifactModal(${idx})" class="p-1 rounded hover:bg-surface-container text-secondary" title="预览">
        <span class="material-symbols-outlined text-[14px]">open_in_full</span>
      </button>`;
  } else if (artType === 'webcard') {
    actionBtns = `
      ${starBtn}
      <button onclick="window.open('${art.content}', '_blank')" class="p-1 rounded hover:bg-surface-container text-secondary" title="访问网页">
        <span class="material-symbols-outlined text-[14px]">open_in_new</span>
      </button>`;
  } else {
    // 代码类型
    actionBtns = `
      ${starBtn}
      <button onclick="copyArtifactByIdx(${idx})" class="p-1 rounded hover:bg-surface-container text-secondary" title="复制">
        <span class="material-symbols-outlined text-[14px]">content_copy</span>
      </button>
      <button onclick="openArtifactModal(${idx}${renderMode === 'iframe' ? ", 'iframe'" : renderMode === 'markdown' ? ", 'markdown'" : ''})" class="p-1 rounded hover:bg-surface-container text-secondary" title="全屏预览">
        <span class="material-symbols-outlined text-[14px]">open_in_full</span>
      </button>`;
  }

  // 收藏状态：高亮边框
  const borderClass = isStarred ? 'border-primary/50 ring-1 ring-primary/20' : 'border-outline-variant';

  // 根据类型选择预览内容
  let previewContent = '';
  if (artType === 'image') {
    previewContent = `<div class="p-md flex items-center justify-center bg-surface-container-lowest">
      <img src="${art.content}" class="max-w-full max-h-[200px] object-contain rounded-lg cursor-pointer hover:opacity-90" onclick="openArtifactModal(${idx})" />
    </div>`;
  } else if (artType === 'file') {
    const meta = art.fileMeta || {};
    const fileSize = formatFileSize(meta.size);
    const ext = (meta.name || '').split('.').pop().toLowerCase();
    let fileIcon = 'description';
    if (['pdf'].includes(ext)) fileIcon = 'picture_as_pdf';
    else if (['txt','md','csv','json'].includes(ext)) fileIcon = 'text_snippet';
    else if (['docx','doc'].includes(ext)) fileIcon = 'article';
    else if (['xlsx','xls','csv'].includes(ext)) fileIcon = 'table';
    
    previewContent = `<div class="p-md">
      <div class="flex items-center gap-3 bg-surface-container border border-outline-variant rounded-xl p-md">
        <div class="w-12 h-12 rounded-xl bg-primary-fixed flex items-center justify-center shrink-0">
          <span class="material-symbols-outlined text-[24px] text-primary">${fileIcon}</span>
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-label-md font-bold text-on-surface truncate">${escapeHTML(art.title)}</p>
          <p class="text-label-sm text-secondary mt-0.5">${escapeHTML(description)}${fileSize ? ' · ' + fileSize : ''}</p>
        </div>
      </div>
    </div>`;
  } else if (artType === 'webcard') {
    const preview = art.preview || {};
    previewContent = `<div class="p-md">
      <div class="bg-surface-container border border-outline-variant rounded-xl overflow-hidden cursor-pointer hover:bg-surface-container-high transition-colors" onclick="window.open('${art.content}', '_blank')">
        ${preview.image ? `<img src="${preview.image}" class="w-full h-[100px] object-cover" />` : ''}
        <div class="p-3">
          <div class="flex items-center gap-2 mb-1">
            ${preview.favicon ? `<img src="${preview.favicon}" class="w-4 h-4" />` : '<span class="material-symbols-outlined text-[14px] text-secondary">travel_explore</span>'}
            <span class="text-label-sm text-secondary truncate">${escapeHTML(preview.provider || art.content)}</span>
          </div>
          <p class="text-label-md font-bold text-on-surface truncate">${escapeHTML(preview.title || art.title)}</p>
          ${preview.description ? `<p class="text-label-sm text-secondary mt-1 line-clamp-2">${escapeHTML(preview.description)}</p>` : ''}
        </div>
      </div>
    </div>`;
  } else if (artType === 'diagram' || renderMode === 'mermaid') {
    // Mermaid 图表预览
    const mmId = 'panel-mermaid-' + Math.random().toString(36).slice(2, 8);
    previewContent = `<div class="p-md bg-white flex justify-center overflow-x-auto">
      <div class="mermaid-diagram" id="${mmId}" data-content="${escapeHTML(art.content || '')}" style="min-width:200px; max-height:250px; overflow:hidden"></div>
    </div>`;
  } else if (artType === 'diff') {
    // Diff 预览
    previewContent = `<div class="p-md">
      <pre class="px-md py-2 text-body-sm font-mono whitespace-pre-wrap overflow-x-auto max-h-[200px] overflow-y-auto text-on-surface border border-outline-variant rounded-lg bg-surface-container-lowest diff-view"><code>${renderDiff((art.content || '').slice(0, 2000))}</code></pre>
    </div>`;
  } else {
    // 代码类型预览
    previewContent = `<div class="p-md">
      <pre class="px-md py-2 text-body-sm font-mono whitespace-pre-wrap overflow-x-auto max-h-[200px] overflow-y-auto text-on-surface border border-outline-variant rounded-lg bg-surface-container-lowest"><code class="language-${lang}">${escapeHTML(art.content || '').slice(0, 500)}${(art.content || '').length > 500 ? '...' : ''}</code></pre>
    </div>`;
  }

  return `
    <div class="bg-surface-container-lowest border ${borderClass} rounded-xl overflow-hidden group">
      <div class="flex items-center gap-2 px-md py-2 bg-surface-container border-b border-outline-variant">
        <span class="material-symbols-outlined text-[16px] text-primary">${artIcon}</span>
        <div class="flex-1 min-w-0">
          <span class="text-label-md font-bold text-on-surface truncate block">${escapeHTML(artTitle)}</span>
          ${description ? `<span class="text-label-sm text-secondary truncate block">${escapeHTML(description)}</span>` : ''}
        </div>
        <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          ${actionBtns}
        </div>
      </div>
      ${previewContent}
    </div>`;
}

function downloadArtifact(idx) {
  const art = state._artifacts && state._artifacts[idx];
  if (!art) return;
  
  if (art.artType === 'image' || art.artType === 'file') {
    const url = art.content || art.fileMeta?.url || '';
    const name = art.title || art.fileMeta?.name || 'download';
    if (url) {
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      a.target = '_blank';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      showToast('开始下载: ' + name, 'success');
    }
  } else if (art.artType === 'code') {
    // 下载代码为文件
    const blob = new Blob([art.content || ''], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (art.title || 'code') + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('代码已下载', 'success');
  }
}

function downloadArtifactByUrl(url, filename) {
  if (!url) {
    showToast('文件路径无效', 'error');
    return;
  }
  // 如果是本地临时文件路径，通过后端 API 代理下载
  if (url.startsWith('/var/') || url.startsWith('/tmp/') || url.includes('/temp/')) {
    // 调用后端文件服务
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'download';
    a.target = '_blank';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast('开始下载: ' + filename, 'success');
  } else {
    // 直接下载
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || url.split('/').pop();
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast('开始下载: ' + filename, 'success');
  }
}

async function downloadAttachment(url, filename) {
  // 使用认证下载端点
  const downloadUrl = url.replace('/attachments/', '/api/attachments/') + '/download';
  try {
    const token = localStorage.getItem('token');
    const resp = await fetch(downloadUrl, {
      headers: token ? { 'Authorization': `Bearer ${token}` } : {}
    });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const blob = await resp.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename || 'download';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
    showToast('开始下载: ' + filename, 'success');
  } catch (e) {
    console.error('下载失败:', e);
    // 降级：直接打开链接
    window.open(url, '_blank');
  }
}

function copyArtifactByIdx(idx) {
  const art = state._artifacts && state._artifacts[idx];
  if (!art) return;
  
  if (art.artType === 'image' || art.artType === 'file' || art.artType === 'webcard') {
    // 复制 URL
    navigator.clipboard.writeText(art.content || '');
    showToast('链接已复制到剪贴板', 'success');
  } else {
    // 复制代码内容
    navigator.clipboard.writeText(art.content || '');
    showToast('已复制到剪贴板', 'success');
  }
}

/* ----- Artifact Modal (fullscreen preview) ----- */
function openArtifactModal(idx, modeOverride) {
  // 支持两种调用方式：openArtifactModal(idx) 或 openArtifactModal({artType, title, content})
  let art;
  if (typeof idx === 'object' && idx !== null) {
    art = { ...idx, renderMode: 'code' };
    if (idx.artType === 'html_preview') art.renderMode = 'iframe';
  } else {
    art = state._artifacts && state._artifacts[idx];
  }
  if (!art) return;
  const artTitle = art.title || '产物';
  const artType = art.artType || 'code';
  const renderMode = modeOverride || art.renderMode || 'code';

  let content = '';
  let headerIcon = 'code';
  let headerActions = '';
  
  if (artType === 'image') {
    headerIcon = 'image';
    headerActions = `
      <button onclick="downloadArtifact(${idx})" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container text-label-md flex items-center gap-1 mr-1">
        <span class="material-symbols-outlined text-[16px]">download</span>下载
      </button>`;
    content = `<div class="flex items-center justify-center p-lg bg-surface-container-lowest">
      <img src="${art.content}" class="max-w-full max-h-[80vh] object-contain rounded-lg shadow-lg" />
    </div>`;
  } else if (artType === 'file') {
    headerIcon = 'description';
    const meta = art.fileMeta || {};
    const ext = (meta.name || art.title || '').split('.').pop().toLowerCase();
    const fileUrl = art.content || meta.url || '';
    
    headerActions = `
      <button onclick="downloadArtifact(${idx})" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container text-label-md flex items-center gap-1 mr-1">
        <span class="material-symbols-outlined text-[16px]">download</span>下载
      </button>`;
    
    if (ext === 'pdf') {
      // PDF 预览
      content = `<iframe src="${fileUrl}" class="w-full h-full border-0" type="application/pdf"></iframe>`;
    } else if (['txt','md','csv','json','py','js','html','css','xml'].includes(ext)) {
      // 文本预览：尝试 fetch 内容
      content = `<div class="p-md text-on-surface bg-surface-container-lowest overflow-y-auto">
        <pre class="text-body-sm font-mono whitespace-pre-wrap">正在加载...</pre>
      </div>`;
      // 异步加载文本
      setTimeout(async () => {
        try {
          const resp = await fetch(fileUrl);
          const text = await resp.text();
          const container = document.querySelector('#modal-ai-proposal .overflow-y-auto pre');
          if (container) container.textContent = text.slice(0, 10000); // 限制 10KB
        } catch (e) {
          const container = document.querySelector('#modal-ai-proposal .overflow-y-auto pre');
          if (container) container.textContent = '无法加载文件内容';
        }
      }, 0);
    } else {
      // 其他文件：显示下载提示
      content = `<div class="flex flex-col items-center justify-center p-lg text-secondary">
        <span class="material-symbols-outlined text-[64px] opacity-40 mb-4">description</span>
        <p class="text-body-md text-on-surface">${escapeHTML(art.title)}</p>
        <p class="text-label-sm mt-2">该文件类型暂不支持在线预览，请下载后查看</p>
        <button onclick="downloadArtifact(${idx})" class="mt-4 px-4 py-2 bg-primary text-white rounded-lg text-label-md flex items-center gap-2">
          <span class="material-symbols-outlined text-[18px]">download</span>下载文件
        </button>
      </div>`;
    }
  } else if (artType === 'webcard') {
    headerIcon = 'travel_explore';
    const preview = art.preview || {};
    headerActions = `
      <button onclick="window.open('${art.content}', '_blank')" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container text-label-md flex items-center gap-1 mr-1">
        <span class="material-symbols-outlined text-[16px]">open_in_new</span>访问网页
      </button>`;
    content = `<div class="p-md overflow-y-auto">
      <div class="bg-surface-container border border-outline-variant rounded-xl overflow-hidden">
        ${preview.image ? `<img src="${preview.image}" class="w-full h-[200px] object-cover" />` : ''}
        <div class="p-4">
          <div class="flex items-center gap-2 mb-2">
            ${preview.favicon ? `<img src="${preview.favicon}" class="w-5 h-5" />` : '<span class="material-symbols-outlined text-[16px] text-secondary">travel_explore</span>'}
            <span class="text-label-sm text-secondary">${escapeHTML(preview.provider || art.content)}</span>
          </div>
          <h2 class="text-title-lg text-on-surface mb-2">${escapeHTML(preview.title || art.title)}</h2>
          ${preview.description ? `<p class="text-body-md text-secondary">${escapeHTML(preview.description)}</p>` : ''}
          <div class="mt-4 flex gap-2">
            <a href="${art.content}" target="_blank" class="px-4 py-2 bg-primary text-white rounded-lg text-label-md flex items-center gap-2">
              <span class="material-symbols-outlined text-[16px]">open_in_new</span>访问链接
            </a>
          </div>
        </div>
      </div>
    </div>`;
  } else if (renderMode === 'iframe') {
    headerIcon = 'web';
    // 构建完整 HTML 文档
    const htmlContent = art.content || '';
    const isFullHtml = htmlContent.trim().toLowerCase().startsWith('<!doctype') || htmlContent.trim().toLowerCase().startsWith('<html');
    const srcDoc = isFullHtml ? htmlContent : `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font-family:system-ui,-apple-system,sans-serif;margin:20px;line-height:1.6;color:#333}</style></head><body>${htmlContent}</body></html>`;
    content = `<iframe srcdoc=${JSON.stringify(srcDoc)} class="w-full h-full border-0" sandbox="allow-scripts allow-same-origin"></iframe>`;
    headerActions = `
      ${renderMode === 'code' ? `<button onclick="openArtifactModal(${idx}, 'iframe')" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container text-label-md flex items-center gap-1 mr-1">
        <span class="material-symbols-outlined text-[16px]">travel_explore</span>网页预览
      </button>` : ''}
      ${renderMode === 'iframe' ? `<button onclick="openArtifactModal(${idx}, 'code')" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container text-label-md flex items-center gap-1 mr-1">
        <span class="material-symbols-outlined text-[16px]">code</span>查看源码
      </button>` : ''}`;
  } else if (renderMode === 'markdown') {
    headerIcon = 'description';
    const mdHtml = (typeof marked !== 'undefined') ? marked.parse(art.content || '') : escapeHTML(art.content || '');
    content = `<div class="markdown-body p-md overflow-y-auto">${mdHtml}</div>`;
    headerActions = `
      <button onclick="downloadArtifact(${idx})" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container text-label-md flex items-center gap-1 mr-1">
        <span class="material-symbols-outlined text-[16px]">download</span>下载 MD
      </button>`;
  } else if (artType === 'diagram' || renderMode === 'mermaid') {
    headerIcon = 'account_tree';
    const mmId = 'modal-mermaid-' + Math.random().toString(36).slice(2, 8);
    content = `<div class="p-lg bg-white flex justify-center overflow-auto">
      <div class="mermaid-diagram" id="${mmId}" data-content="${escapeHTML(art.content || '')}" style="min-width:400px"></div>
    </div>`;
    headerActions = `
      <button onclick="downloadArtifact(${idx})" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container text-label-md flex items-center gap-1 mr-1">
        <span class="material-symbols-outlined text-[16px]">download</span>下载源码
      </button>`;
  } else if (artType === 'diff') {
    headerIcon = 'difference';
    content = `<div class="overflow-y-auto bg-surface-container-lowest">
      <pre class="p-md text-body-sm font-mono whitespace-pre-wrap overflow-x-auto diff-view"><code>${renderDiff(art.content || '')}</code></pre>
    </div>`;
    headerActions = `
      <button onclick="downloadArtifact(${idx})" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container text-label-md flex items-center gap-1 mr-1">
        <span class="material-symbols-outlined text-[16px]">download</span>下载 Diff
      </button>`;
  } else {
    // 代码模式：带行号编辑器样式
    headerActions = `
      <button onclick="downloadArtifact(${idx})" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container text-label-md flex items-center gap-1 mr-1">
        <span class="material-symbols-outlined text-[16px]">download</span>下载
      </button>`;
    const lines = (art.content || '').split('\n');
    const lineNumbers = lines.map((_, i) => `<div class="text-right pr-3 text-label-sm text-secondary select-none">${i + 1}</div>`).join('');
    const codeHtml = lines.map(line => `<div class="whitespace-pre">${escapeHTML(line)}</div>`).join('');
    content = `
      <div class="flex h-full overflow-hidden bg-surface-container-lowest">
        <div class="bg-surface-container border-r border-outline-variant py-md overflow-hidden select-none" style="min-width:48px">
          ${lineNumbers}
        </div>
        <div class="flex-1 overflow-auto p-md">
          <pre class="text-body-sm font-mono text-on-surface"><code>${codeHtml}</code></pre>
        </div>
      </div>`;
  }
  $('#modal-ai-proposal').innerHTML = `
    <div class="fixed inset-0 bg-scrim/60 flex items-center justify-center z-50" onclick="if(event.target===this)closeModal('modal-ai-proposal')">
      <div class="w-[90vw] max-w-[1000px] h-[85vh] bg-surface-container rounded-2xl shadow-xl flex flex-col overflow-hidden">
        <div class="h-[56px] border-b border-outline-variant px-5 flex items-center justify-between bg-surface-container shrink-0">
          <div class="flex items-center gap-3">
            <span class="material-symbols-outlined text-primary text-[20px]">${headerIcon}</span>
            <h3 class="text-headline-md text-on-surface">${escapeHTML(artTitle)}</h3>
          </div>
          <div class="flex items-center gap-2">
            ${headerActions}
            <button onclick="copyArtifactByIdx(${idx})" class="px-3 py-1.5 rounded-lg border border-outline-variant text-on-surface hover:bg-surface-container text-label-md flex items-center gap-1">
              <span class="material-symbols-outlined text-[16px]">content_copy</span>复制
            </button>
            <button onclick="closeModal('modal-ai-proposal')" class="p-1 rounded hover:bg-surface-container">
              <span class="material-symbols-outlined text-secondary">close</span>
            </button>
          </div>
        </div>
        <div class="flex-1 overflow-hidden bg-surface">${content}</div>
      </div>
    </div>`;
  $('#modal-ai-proposal').classList.remove('hidden');
}

function renderChartMock(art) {
  return `
    <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-md">
      <p class="text-label-md text-secondary mb-2">${escapeHTML(art.title)}</p>
      <svg viewBox="0 0 320 160" class="w-full h-[160px]">
        <defs>
          <linearGradient id="g1" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="#E96A3C" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="#E96A3C" stop-opacity="0"/>
          </linearGradient>
        </defs>
        <polyline fill="none" stroke="#E96A3C" stroke-width="2"
          points="10,120 50,90 90,100 130,70 170,80 210,55 250,60 290,30"/>
        <polygon fill="url(#g1)"
          points="10,120 50,90 90,100 130,70 170,80 210,55 250,60 290,30 290,160 10,160"/>
        <polyline fill="none" stroke="#006577" stroke-width="2" stroke-dasharray="4 3"
          points="10,135 50,125 90,115 130,110 170,100 210,95 250,85 290,75"/>
      </svg>
      <div class="flex gap-md text-label-sm mt-2 text-secondary">
        <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-primary"></span>TSLA</span>
        <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-tertiary"></span>BYD</span>
      </div>
    </div>
    <div class="mt-md bg-surface-container-lowest border border-outline-variant rounded-xl p-md">
      <p class="text-label-md font-bold text-on-surface mb-1">分析摘要（草稿）</p>
      <p class="text-body-md text-secondary leading-relaxed">
        TSLA 2023 Q4 毛利率从上季度的 17.9% 回升至 <b class="text-on-surface">18.6%</b>，主要受成本下降与车型组合改善影响；
        BYD 同期毛利率约 <b class="text-on-surface">21.2%</b>，仍保持领先。后续关注 Cybertruck 量产爬坡对单车成本的扰动。
      </p>
    </div>`;
}
function renderKPIMock(art) {
  return `<div class="grid grid-cols-2 gap-md">
    ${art.items.map(k => `
      <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-md">
        <p class="text-label-md text-secondary">${escapeHTML(k.label)}</p>
        <p class="text-headline-lg text-on-surface mt-1">${escapeHTML(k.value)}</p>
      </div>`).join('')}
  </div>`;
}

/* ----- Diff 渲染 ----- */
function renderDiff(content) {
  if (!content) return '';
  const lines = content.split('\n');
  return lines.map(line => {
    if (line.startsWith('+++') || line.startsWith('---')) {
      return `<span class="diff-header">${escapeHTML(line)}</span>`;
    } else if (line.startsWith('@@')) {
      return `<span class="diff-hunk">${escapeHTML(line)}</span>`;
    } else if (line.startsWith('+')) {
      return `<span class="diff-add">${escapeHTML(line)}</span>`;
    } else if (line.startsWith('-')) {
      return `<span class="diff-del">${escapeHTML(line)}</span>`;
    } else {
      return escapeHTML(line);
    }
  }).join('\n');
}

/* ----- Mermaid 图渲染（在 render() 之后调用） ----- */
function renderMermaidDiagrams() {
  if (typeof mermaid === 'undefined') return;
  const diagrams = document.querySelectorAll('.mermaid-diagram:not([data-rendered])');
  diagrams.forEach(async (el) => {
    const content = el.getAttribute('data-content') || el.textContent || '';
    if (!content.trim()) return;
    try {
      const id = el.id || 'mermaid-' + Math.random().toString(36).slice(2, 8);
      const { svg } = await mermaid.render(id + '-svg', content);
      el.innerHTML = svg;
      el.setAttribute('data-rendered', 'true');
    } catch (e) {
      console.warn('Mermaid render failed:', e);
      el.innerHTML = `<pre class="text-red-500 text-sm p-2">图表渲染失败: ${escapeHTML(String(e))}\n\n原始代码:\n${escapeHTML(content)}</pre>`;
      el.setAttribute('data-rendered', 'true');
    }
  });
}

/* ----- Markdown 表格排序增强 ----- */
function enhanceMarkdownTables() {
  document.querySelectorAll('.markdown-body table').forEach(table => {
    if (table.hasAttribute('data-sortable')) return;
    table.setAttribute('data-sortable', 'true');
    const headers = table.querySelectorAll('th');
    headers.forEach((th, colIdx) => {
      th.style.cursor = 'pointer';
      th.title = '点击排序';
      th.addEventListener('click', () => sortTable(table, colIdx));
    });
  });
}

function sortTable(table, colIdx) {
  const tbody = table.querySelector('tbody') || table;
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const isAsc = table.getAttribute('data-sort-dir') !== 'asc';
  table.setAttribute('data-sort-dir', isAsc ? 'asc' : 'desc');
  rows.sort((a, b) => {
    const aVal = (a.cells[colIdx]?.textContent || '').trim();
    const bVal = (b.cells[colIdx]?.textContent || '').trim();
    const aNum = parseFloat(aVal), bNum = parseFloat(bVal);
    if (!isNaN(aNum) && !isNaN(bNum)) return isAsc ? aNum - bNum : bNum - aNum;
    return isAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
  });
  rows.forEach(row => tbody.appendChild(row));
}
