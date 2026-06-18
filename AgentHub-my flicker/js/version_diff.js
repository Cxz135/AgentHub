/* ============================================================
   通用 版本 diff Modal
============================================================ */
let _diffRollbackHandler = null;
function showVersionDiffModal(oldSnap, newSnap, versionIdx, rollbackFn) {
  _diffRollbackHandler = rollbackFn;
  let root = document.getElementById('modal-version-diff');
  if (!root) {
    root = document.createElement('div');
    root.id = 'modal-version-diff';
    document.body.appendChild(root);
  }
  const fields = ['name','description','code','readme','icon','category','model','role','systemPrompt','skills'];
  const rows = fields.filter(f => f in oldSnap || f in newSnap).map(f => {
    const ov = JSON.stringify(oldSnap[f] ?? '', null, 2);
    const nv = JSON.stringify(newSnap[f] ?? '', null, 2);
    const same = ov === nv;
    return `
      <div class="border-t border-outline-variant py-2">
        <p class="text-label-md font-medium ${same?'text-secondary':'text-on-surface'}">${f} ${same?'<span class="text-[10px] bg-surface-container px-1 rounded">未变</span>':'<span class="text-[10px] bg-amber-100 text-amber-700 px-1 rounded">已修改</span>'}</p>
        ${same ? '' : `
          <div class="grid grid-cols-2 gap-2 mt-1 text-[11px] font-mono">
            <div class="bg-red-50 border border-red-200 rounded p-2 max-h-40 overflow-y-auto whitespace-pre-wrap">${escapeHTML(ov)}</div>
            <div class="bg-green-50 border border-green-200 rounded p-2 max-h-40 overflow-y-auto whitespace-pre-wrap">${escapeHTML(nv)}</div>
          </div>`}
      </div>`;
  }).join('');
  root.innerHTML = `
    <div class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onclick="if(event.target===this) closeVersionDiffModal()">
      <div class="bg-surface rounded-xl shadow-2xl w-[860px] max-h-[90vh] flex flex-col overflow-hidden">
        <header class="px-lg py-md border-b border-outline-variant flex items-center justify-between">
          <h3 class="text-title-lg font-headline-md">版本对比 · v${versionIdx+1} → 当前</h3>
          <button onclick="closeVersionDiffModal()" class="text-secondary hover:text-on-surface"><span class="material-symbols-outlined">close</span></button>
        </header>
        <main class="px-lg py-md overflow-y-auto flex-1">
          <div class="grid grid-cols-2 gap-2 text-label-md font-medium pb-2 sticky top-0 bg-surface">
            <div class="text-red-700">v${versionIdx+1} (旧)</div>
            <div class="text-green-700">当前</div>
          </div>
          ${rows}
        </main>
        <footer class="px-lg py-md border-t border-outline-variant flex justify-end gap-2">
          <button onclick="closeVersionDiffModal()" class="px-4 py-1.5 rounded-lg border border-outline-variant text-on-surface-variant hover:bg-surface-container-low text-label-md">关闭</button>
          <button onclick="(_diffRollbackHandler && _diffRollbackHandler())" class="px-4 py-1.5 rounded-lg bg-primary text-white hover:opacity-90 text-label-md flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">undo</span>回滚到 v${versionIdx+1}
          </button>
        </footer>
      </div>
    </div>`;
}
function closeVersionDiffModal() {
  const root = document.getElementById('modal-version-diff');
  if (root) root.remove();
  _diffRollbackHandler = null;
}