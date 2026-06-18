/* ===================== 验收自检（控制台） ===================== */
// ---- SSE 流式读取器 ----
async function readSSEStream(response, handlers) {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let currentEvent = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const line of lines) {
      const s = line.trim();
      if (s.startsWith('event: ')) currentEvent = s.slice(7).trim();
      else if (s.startsWith('data: ') && handlers[currentEvent]) {
        try { await handlers[currentEvent](JSON.parse(s.slice(6))); } catch (e) { console.warn('SSE', e); }
      }
    }
  }
}