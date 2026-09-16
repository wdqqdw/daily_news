(() => {
  'use strict';
  // One storage entry per article avoids overwriting unrelated marks across tabs.
  const prefix = 'daily_news.read.v1.';
  const buttons = Array.from(document.querySelectorAll('[data-read-id]'));
  const entries = Array.from(document.querySelectorAll('[data-library-entry]'));
  const memory = new Map();
  const status = document.getElementById('reading-status');
  let storageAvailable = true;
  const announce = message => { if (status) status.textContent = message; };
  const normalize = text => text.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, ' ').trim();
  const isRead = id => {
    if (memory.has(id)) return memory.get(id);
    try { return localStorage.getItem(prefix + id) === '1'; }
    catch (_) { storageAvailable = false; return false; }
  };
  entries.forEach(entry => {
    entry.searchText = normalize(entry.dataset.search);
  });

  function render() {
    buttons.forEach(button => {
      const read = isRead(button.dataset.readId);
      button.disabled = false;
      button.setAttribute('aria-pressed', String(read));
      button.setAttribute('aria-label', (read ? '取消已了解：' : '标记已了解：') + button.dataset.readTitle);
      button.querySelector('.read-label').textContent = read ? '已了解' : '标记已了解';
      button.closest('[data-item-id]')?.classList.toggle('is-read', read);
    });
    for (const state of ['read', 'unread']) {
      const list = document.getElementById(state + '-list');
      if (!list) continue;
      const query = normalize(document.getElementById(state + '-search').value);
      const terms = query.split(' ').filter(Boolean);
      const group = entries.filter(entry => isRead(entry.dataset.itemId) === (state === 'read'));
      let shown = 0;
      group.forEach(entry => {
        if (entry.parentElement !== list) list.appendChild(entry);
        entry.hidden = !terms.every(term => entry.searchText.includes(term));
        if (!entry.hidden) shown++;
      });
      // Keep publication order stable after moving an item between columns.
      group.forEach(entry => list.appendChild(entry));
      document.getElementById(state + '-count').textContent = query ? shown + ' / ' + group.length : group.length;
      const empty = document.getElementById(state + '-empty');
      empty.hidden = shown !== 0;
      empty.textContent = group.length ? '没有匹配的内容，试试其他关键词。' : state === 'read' ? '还没有已了解的内容。读完后，点一下“标记已了解”。' : '全部都已了解，等待下一期新内容。';
    }
  }

  buttons.forEach(button => button.addEventListener('click', () => {
    const id = button.dataset.readId;
    const value = !isRead(id);
    memory.set(id, value);
    try {
      if (value) localStorage.setItem(prefix + id, '1');
      else localStorage.removeItem(prefix + id);
    } catch (_) { storageAvailable = false; }
    render();
    // The selected card may have moved into a column with an active filter.
    if (button.closest('[hidden]')) document.getElementById((value ? 'read' : 'unread') + '-search')?.focus();
    else button.focus({preventScroll: true});
    announce((value ? '已标记为已了解：' : '已移回未了解：') + button.dataset.readTitle + (storageAvailable ? '' : '。浏览器无法保存记录，本次标记仅在当前页面有效。'));
  }));
  document.querySelectorAll('[data-reading-search]').forEach(input => input.addEventListener('input', render));
  window.addEventListener('storage', event => {
    if (event.key === null || event.key.startsWith(prefix)) {
      memory.clear();
      render();
    }
  });
  window.addEventListener('pageshow', () => { memory.clear(); render(); });
  render();
  if (!storageAvailable) announce('浏览器无法保存阅读记录，标记仅在当前页面有效。');
})();
