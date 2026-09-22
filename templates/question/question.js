(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const { questionId, language } = JSON.parse($('#page-data').textContent);
  const embedded = window.parent !== window;
  if (embedded) document.body.classList.add('embedded-question');
  function notifyWorkspace(type, extra = {}) {
    if (!embedded) return;
    const targetOrigin = location.protocol === 'file:' ? '*' : location.origin;
    window.parent.postMessage({ type, questionId, ...extra }, targetOrigin);
  }
  const suffix = language === 'zh' ? '' : `:${language}`;
  const draftKey = `agent-interview:${questionId}${suffix}:answer:v2`;
  const legacyKey = `agent-interview:${questionId}${suffix}:v1`;
  const input = $('#my-answer');
  let draft = { text: '', updatedAt: null };
  let storageAvailable = true;
  // Preserve an earlier prototype's draft without reviving its review controls.
  try {
    const stored = JSON.parse(localStorage.getItem(draftKey) || 'null');
    if (stored && typeof stored.text === 'string') {
      draft = { text: stored.text, updatedAt: stored.updatedAt ?? null };
    } else {
      const legacy = JSON.parse(localStorage.getItem(legacyKey) || 'null');
      if (legacy && typeof legacy.note === 'string') draft.text = legacy.note;
    }
  } catch { storageAvailable = false; }
  input.value = draft.text;
  function renderDraft() {
    $('#word-count').textContent = `${Array.from(draft.text).length} 字`;
    $('#draft-state').textContent = !storageAvailable ? '仅本次页面保留' : draft.text ? '已自动保存' : '尚未记录';
    $('#draft-hint').textContent = storageAvailable ? '仅保存在当前浏览器，刷新后保留。' : '浏览器暂不支持保存，请自行复制回答以免丢失。';
  }
  input.addEventListener('input', () => {
    draft = { text: input.value, updatedAt: Date.now() };
    try { localStorage.setItem(draftKey, JSON.stringify(draft)); storageAvailable = true; }
    catch { storageAvailable = false; }
    renderDraft();
    notifyWorkspace('interview:draft-saved');
  });
  renderDraft();
  $('#reference-answer').addEventListener('toggle', event => {
    $('#answer-toggle-label').textContent = event.target.open ? '收起答案' : '展开答案';
  });
  $$('.followup-answer').forEach(details => details.addEventListener('toggle', () => {
    details.querySelector('[data-followup-label]').textContent = details.open ? '收起追答' : '展开追答';
  }));
  const mediaDialog = $('#media-dialog');
  let mediaTrigger = null;
  $$('[data-image-preview]').forEach(button => button.addEventListener('click', () => {
    const source = button.querySelector('img');
    const image = new Image();
    image.src = source.src;
    image.alt = source.alt;
    $('#media-content').replaceChildren(image);
    mediaTrigger = button;
    mediaDialog.showModal();
    document.body.style.overflow = 'hidden';
    $('#close-media').focus();
  }));
  $('#close-media').addEventListener('click', () => mediaDialog.close());
  mediaDialog.addEventListener('close', () => {
    document.body.style.overflow = '';
    mediaTrigger?.focus();
  });
  let printStates = null;
  window.addEventListener('beforeprint', () => {
    if (!printStates) printStates = $$('details').map(details => [details, details.open]);
    $('#print-draft').textContent = input.value.trim() ? input.value : '（尚未作答）';
    $$('details').forEach(details => { details.open = true; });
  });
  window.addEventListener('afterprint', () => {
    printStates?.forEach(([details, open]) => { details.open = open; });
    printStates = null;
  });
  $('#print-page').addEventListener('click', () => window.print());
  if (embedded) document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || link.download || link.target === '_blank' || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin) return;
    const file = decodeURIComponent(url.pathname.split('/').pop());
    if (/^(?:agent|llm|rag|engineering|product)-\d{4}-.+\.html$/.test(file)) {
      event.preventDefault();
      notifyWorkspace('interview:navigate', { file });
    } else if (file === 'index.html') {
      event.preventDefault();
      notifyWorkspace('interview:home');
    }
  });
  notifyWorkspace('interview:ready');
})();
