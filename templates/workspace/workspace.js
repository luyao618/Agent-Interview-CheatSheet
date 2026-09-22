(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const data = JSON.parse($('#workspace-data').textContent);
  const categories = data.categories;
  const categoryMap = new Map(categories.map(c => [c.id, c]));
  const questions = data.questions.slice().sort((a, b) => categories.findIndex(c => c.id === a.category) - categories.findIndex(c => c.id === b.category) || a.id.localeCompare(b.id));
  const questionMap = new Map(questions.map(q => [q.id, q]));
  const fileMap = new Map(questions.map(q => [q.file, q]));
  const difficultyLabels = { easy: '入门', medium: '进阶', hard: '困难' };
  const roleLabels = { engineer: '工程师', pm: '产品经理', both: '工程师 / 产品经理' };
  const workspaceKey = 'agent-interview:workspace:v1';
  const queueKey = 'agent-interview:workspace:queue:v1';
  const pageSize = 12;
  const frame = $('#question-frame');
  const drawer = $('#mobile-navigation');
  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const icon = (name, extra = '') => `<svg class="w-icon ${extra}" aria-hidden="true"><use href="#w-${name}"/></svg>`;
  const questionHash = id => `#question/${encodeURIComponent(id)}`;
  let records = new Map();
  let storageReadable = true;
  let loadedQuestionId = null;
  let currentRoute = null;
  let currentMatches = [];
  let readerQueue = [];
  let currentPage = 1;
  let composing = false;
  let searchTimeout;
  let refreshTimeout;
  let toastTimeout;
  let loadTimeout;
  let navigationState = { ids: [], returnTo: '#questions' };
  let historyState = { recent: [] };

  function readJSON(storageName, key) {
    try { return JSON.parse(window[storageName].getItem(key) || 'null'); }
    catch { return null; }
  }
  const previousHistory = readJSON('localStorage', workspaceKey);
  if (Array.isArray(previousHistory?.recent)) {
    historyState.recent = previousHistory.recent.filter(item => item && questionMap.has(item.id) && Number.isFinite(item.at)).slice(0, 20);
  }
  const previousQueue = readJSON('sessionStorage', queueKey);
  if (Array.isArray(previousQueue?.ids)) {
    navigationState.ids = [...new Set(previousQueue.ids.filter(id => questionMap.has(id)))];
    navigationState.returnTo = /^#(?:questions|home|answers)(?:\?|$)/.test(previousQueue.returnTo || '') ? previousQueue.returnTo : '#questions';
  }

  function reloadRecords() {
    records = new Map();
    storageReadable = true;
    for (const q of questions) {
      try {
        const suffix = q.language === 'zh' ? '' : `:${q.language}`;
        const stored = JSON.parse(localStorage.getItem(`agent-interview:${q.id}${suffix}:answer:v2`) || 'null');
        let text = typeof stored?.text === 'string' ? stored.text : null;
        let updatedAt = Number.isFinite(stored?.updatedAt) ? stored.updatedAt : 0;
        if (text === null) {
          const legacy = JSON.parse(localStorage.getItem(`agent-interview:${q.id}${suffix}:v1`) || 'null');
          text = typeof legacy?.note === 'string' ? legacy.note : '';
        }
        if (text.trim()) records.set(q.id, { question: q, text, updatedAt });
      } catch { storageReadable = false; }
    }
  }
  function sortedRecords() { return [...records.values()].sort((a, b) => b.updatedAt - a.updatedAt || a.question.id.localeCompare(b.question.id)); }
  function dateLabel(timestamp) {
    return timestamp > 0 ? new Date(timestamp).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }) : '已记录';
  }
  function toast(message) {
    clearTimeout(toastTimeout);
    $('#workspace-toast').textContent = message;
    $('#workspace-toast').classList.add('visible');
    toastTimeout = setTimeout(() => $('#workspace-toast').classList.remove('visible'), 2800);
  }
  function rememberVisit(id) {
    historyState.recent = [{ id, at: Date.now() }, ...historyState.recent.filter(item => item.id !== id)].slice(0, 20);
    try { localStorage.setItem(workspaceKey, JSON.stringify(historyState)); } catch { /* Reading remains available. */ }
  }
  function setQueue(ids, returnTo) {
    navigationState = { ids: [...new Set(ids.filter(id => questionMap.has(id)))], returnTo };
    try { sessionStorage.setItem(queueKey, JSON.stringify(navigationState)); } catch { /* Keep this tab's in-memory queue. */ }
  }
  function catalogHash(filters) {
    const params = new URLSearchParams();
    for (const key of ['category', 'difficulty', 'role', 'status', 'q', 'sort', 'page']) {
      const value = filters[key];
      if (value && value !== 'all' && !(key === 'sort' && value === 'id') && !(key === 'page' && Number(value) === 1)) params.set(key, value);
    }
    return '#questions' + (params.size ? `?${params}` : '');
  }
  function routeFromHash() {
    const hash = location.hash.slice(1) || 'home';
    const split = hash.indexOf('?');
    const path = split < 0 ? hash : hash.slice(0, split);
    const params = new URLSearchParams(split < 0 ? '' : hash.slice(split + 1));
    if (path.startsWith('question/')) {
      let id = '';
      try { id = decodeURIComponent(path.slice(9)); } catch { /* Show the missing-question state. */ }
      return { view: 'reader', id, q: '' };
    }
    if (path === 'answers') return { view: 'answers', q: params.get('q') || '' };
    if (path !== 'questions') return { view: 'home', q: '' };
    const allowed = (key, values, fallback) => values.includes(params.get(key)) ? params.get(key) : fallback;
    const page = Number.parseInt(params.get('page'), 10);
    return {
      view: 'questions', category: allowed('category', categories.map(c => c.id), 'all'),
      difficulty: allowed('difficulty', ['easy', 'medium', 'hard'], 'all'),
      role: allowed('role', ['engineer', 'pm'], 'all'), status: allowed('status', ['written', 'unanswered'], 'all'),
      sort: allowed('sort', ['id', 'updated'], 'id'), q: params.get('q') || '', page: Number.isFinite(page) && page > 0 ? page : 1,
    };
  }
  function navigate(hash, replace = false, keepSearchFocus = false) {
    clearTimeout(searchTimeout);
    if (replace) {
      history.replaceState(null, '', location.pathname + location.search + hash);
      renderRoute(keepSearchFocus);
    } else if (location.hash === hash) renderRoute(keepSearchFocus);
    else location.hash = hash;
  }
  function matchingQuestions(filters) {
    const terms = (filters.q || '').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return questions.filter(q => {
      if (filters.category !== 'all' && filters.category && q.category !== filters.category) return false;
      if (filters.difficulty !== 'all' && filters.difficulty && q.difficulty !== filters.difficulty) return false;
      if (filters.role !== 'all' && filters.role && q.role !== filters.role && q.role !== 'both') return false;
      if (filters.status === 'written' && !records.has(q.id)) return false;
      if (filters.status === 'unanswered' && records.has(q.id)) return false;
      const searchable = [q.id, q.title, q.category, categoryMap.get(q.category)?.label, ...q.tags].join(' ').toLocaleLowerCase();
      return terms.every(term => searchable.includes(term));
    }).sort((a, b) => filters.sort === 'updated' ? b.updated.localeCompare(a.updated) || a.id.localeCompare(b.id) : questions.indexOf(a) - questions.indexOf(b));
  }
  function renderRail() {
    const route = currentRoute || routeFromHash();
    const question = route.view === 'reader' ? questionMap.get(route.id) : null;
    const activeCategory = question?.category || (route.view === 'questions' ? route.category : 'all');
    $$('[data-nav]').forEach(link => {
      const active = link.dataset.nav === (route.view === 'reader' ? 'questions' : route.view);
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    });
    $$('[data-category-nav]').forEach(link => {
      const active = link.dataset.categoryNav === activeCategory;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'location'); else link.removeAttribute('aria-current');
    });
    $$('.local-note').forEach(node => { node.textContent = storageReadable ? '保存在此浏览器，可导出备份。' : '浏览器暂时无法读取本地记录。'; });
    $$('[data-answer-count]').forEach(node => { node.textContent = records.size; });
    $$('[data-record-progress]').forEach(node => { node.style.width = `${records.size / questions.length * 100}%`; });
    $$('[data-export]').forEach(button => { button.disabled = records.size === 0; });
    $$('[data-current-question]').forEach(node => { node.hidden = !question; });
    if (question) {
      $$('[data-current-link]').forEach(node => { node.href = questionHash(question.id); });
      $$('[data-current-id]').forEach(node => { node.textContent = question.id.toUpperCase(); });
      $$('[data-current-title]').forEach(node => { node.textContent = question.title; });
    }
  }
  function renderHome() {
    const recentRecord = sortedRecords()[0];
    const last = historyState.recent[0]?.id || recentRecord?.question.id;
    const featured = questionMap.get(last) || questionMap.get('agent-0008') || questions[0];
    const record = records.get(featured.id);
    $('#featured-question').innerHTML = `<div class="featured-topline"><span>${icon(last ? 'clock' : 'pen')}${last ? '继续上次的题目' : '建议从这道题开始'}</span><span>${difficultyLabels[featured.difficulty]}</span></div><div class="featured-id">${escapeHTML(featured.id.toUpperCase())}</div><h2>${escapeHTML(featured.title)}</h2><div class="featured-tags"><span>${escapeHTML(categoryMap.get(featured.category).short)}</span><span>${roleLabels[featured.role]}</span></div><div class="featured-bottom"><span>${record ? `已记录 ${Array.from(record.text).length} 字` : '先写下自己的理解'}</span><a class="action-button primary" href="${questionHash(featured.id)}" data-open-question="${featured.id}" data-home-question>${last ? '继续作答' : '开始作答'}${icon('arrow')}</a></div>`;
    $('#topic-grid').innerHTML = categories.map(c => `<a class="topic-card" href="#questions?category=${c.id}" style="--category-color:${c.color};--category-wash:${c.wash}"><span class="topic-card-icon">${icon(c.id)}</span><h3>${escapeHTML(c.short)}</h3><p>${escapeHTML(c.description)}</p><span class="topic-card-bottom"><span>${c.count} 道题</span>${icon('arrow')}</span></a>`).join('');
    const recommendations = ['agent-0035', 'rag-0023', 'engineering-0006'].map(id => questionMap.get(id)).filter(Boolean);
    $('#starting-list').innerHTML = recommendations.map((q, index) => `<a class="starting-row" href="${questionHash(q.id)}" data-open-question="${q.id}" data-home-question><span class="starting-number">${index + 1}</span><span><strong>${escapeHTML(q.title)}</strong><small>${escapeHTML(categoryMap.get(q.category).short)} · ${difficultyLabels[q.difficulty]}</small></span>${icon('arrow')}</a>`).join('');
    const recent = historyState.recent.length ? historyState.recent.slice(0, 3).map(item => ({ question: questionMap.get(item.id), at: item.at })) : sortedRecords().slice(0, 3).map(item => ({ question: item.question, at: item.updatedAt }));
    if (recent.length) {
      $('#recent-section').innerHTML = `<div class="section-header"><h2 id="recent-title">${historyState.recent.length ? '最近打开' : '最近作答'}</h2><a href="#answers">我的回答 ↗</a></div><div class="recent-list">${recent.map(({ question: q, at }) => `<a class="recent-row" href="${questionHash(q.id)}" data-open-question="${q.id}" data-home-question><span class="recent-symbol">${icon('clock')}</span><span><strong>${escapeHTML(q.title)}</strong><small>${dateLabel(at)} · ${records.has(q.id) ? '已有回答' : '尚未记录回答'}</small></span>${icon('arrow')}</a>`).join('')}</div>`;
    } else {
      $('#recent-section').innerHTML = '<div class="section-header"><h2 id="recent-title">每道题，都这样练</h2><span>把答案变成自己的表达</span></div><div class="getting-started"><p>不急着看答案，先给自己一点思考的空间。</p><ol><li><span>01</span>读清题目，用自己的话尝试作答</li><li><span>02</span>展开参考答案，对照遗漏的要点</li><li><span>03</span>回答追问，再补充自己的记录</li></ol></div>';
    }
  }
  function renderCatalog() {
    const route = currentRoute;
    currentMatches = matchingQuestions(route);
    const pageCount = Math.ceil(currentMatches.length / pageSize);
    currentPage = Math.min(route.page, Math.max(1, pageCount));
    const start = (currentPage - 1) * pageSize;
    const pageQuestions = currentMatches.slice(start, start + pageSize);
    $('#catalog-title').textContent = route.category === 'all' ? '全部题目' : categoryMap.get(route.category).label;
    $('#catalog-description').textContent = route.q ? `搜索「${route.q}」的结果` : '从一个方向、一类难度，或一个关键词开始。';
    for (const field of ['category', 'difficulty', 'role', 'status']) $(`#filter-${field}`).value = route[field];
    $('#sort-order').value = route.sort;
    $('#result-count').textContent = currentMatches.length ? `共 ${currentMatches.length} 道题 · 显示 ${start + 1}–${start + pageQuestions.length}` : '共 0 道题';
    $('#catalog-random').disabled = currentMatches.length === 0;
    $('#catalog-empty').hidden = currentMatches.length !== 0;
    $('#question-list').hidden = currentMatches.length === 0;
    $('#question-list').innerHTML = pageQuestions.map(q => `<a class="question-row" href="${questionHash(q.id)}" data-open-question="${q.id}" data-catalog-question><span class="question-row-id">${escapeHTML(q.id)}</span><span class="question-row-body"><span class="question-row-title">${escapeHTML(q.title)}</span><span class="question-row-meta"><span>${escapeHTML(categoryMap.get(q.category).short)}</span><span class="difficulty-badge" data-difficulty="${q.difficulty}"><span class="difficulty-dot"></span>${difficultyLabels[q.difficulty]}</span><span>${roleLabels[q.role]}</span>${records.has(q.id) ? `<span class="written-badge">${icon('check')}已有回答</span>` : ''}</span></span>${icon('arrow')}</a>`).join('');
    const visiblePages = [...new Set([1, currentPage - 1, currentPage, currentPage + 1, pageCount])].filter(n => n >= 1 && n <= pageCount).sort((a, b) => a - b);
    const parts = [];
    visiblePages.forEach((page, index) => {
      if (index && page - visiblePages[index - 1] > 1) parts.push('<span class="page-ellipsis" aria-hidden="true">…</span>');
      parts.push(`<button type="button" class="page-button ${page === currentPage ? 'active' : ''}" data-page="${page}" aria-label="第 ${page} 页" ${page === currentPage ? 'aria-current="page"' : ''}>${page}</button>`);
    });
    $('#pagination').hidden = pageCount <= 1;
    $('#pagination').innerHTML = `<button type="button" class="page-button" data-page="${currentPage - 1}" aria-label="上一页" ${currentPage === 1 ? 'disabled' : ''}>${icon('arrow', 'flip')}</button>${parts.join('')}<button type="button" class="page-button" data-page="${currentPage + 1}" aria-label="下一页" ${currentPage === pageCount ? 'disabled' : ''}>${icon('arrow')}</button>`;
  }
  function renderAnswers() {
    const terms = (currentRoute.q || '').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const items = sortedRecords().filter(item => terms.every(term => `${item.question.title} ${item.question.id} ${item.text}`.toLocaleLowerCase().includes(term)));
    $('#answers-description').textContent = records.size ? `已经留下 ${records.size} 份自己的回答。${terms.length ? ` 当前匹配 ${items.length} 份。` : ' 可以随时接着写。'}` : '你写下的理解，都在这里。';
    $('#answers-empty').hidden = items.length !== 0;
    $('#answers-empty-title').textContent = records.size ? '没有找到匹配的回答' : '从第一份回答开始';
    $('#answers-empty-description').textContent = records.size ? '试试其他关键词，或清空搜索查看全部回答。' : '打开一道题，在「我的回答」里写下思路，这里就会自动留下你的记录。';
    $('#saved-answer-list').innerHTML = items.map(item => {
      const q = item.question;
      const characters = Array.from(item.text);
      const preview = characters.slice(0, 190).join('') + (characters.length > 190 ? '…' : '');
      return `<article class="saved-answer"><div class="saved-answer-top"><span>${escapeHTML(q.id.toUpperCase())}</span><span>${dateLabel(item.updatedAt)}${item.updatedAt ? ' 更新' : ''}</span></div><h2><a href="${questionHash(q.id)}" data-open-question="${q.id}" data-saved-question>${escapeHTML(q.title)}</a></h2><p class="saved-answer-text">${escapeHTML(preview)}</p><div class="saved-answer-bottom"><span>${characters.length} 字 · ${escapeHTML(categoryMap.get(q.category).short)}</span><a href="${questionHash(q.id)}" data-open-question="${q.id}" data-saved-question>继续作答${icon('arrow')}</a></div></article>`;
    }).join('');
    $('#storage-message').textContent = storageReadable ? '回答仅保存在此浏览器。导出一份 Markdown，就可以带走自己的笔记。' : '部分浏览器记录暂时无法读取；已显示能够读取的回答，请及时导出备份。';
  }
  function navigateFrame(url) {
    const target = new URL(url, location.href).href;
    // Replace the child history entry so each workspace route is one Back step.
    try { frame.contentWindow.location.replace(target); }
    catch { frame.src = target; }
  }
  function renderReader() {
    const q = questionMap.get(currentRoute.id);
    $('#reader-error').hidden = Boolean(q);
    frame.hidden = !q;
    $('.reader-toolbar').hidden = !q;
    if (!q) { $('#reader-loading').hidden = true; if (loadedQuestionId) navigateFrame('about:blank'); loadedQuestionId = null; clearTimeout(loadTimeout); return; }
    readerQueue = navigationState.ids.includes(q.id) ? navigationState.ids.map(id => questionMap.get(id)) : questions.filter(item => item.category === q.category);
    const index = readerQueue.findIndex(item => item.id === q.id);
    $('#reader-position').textContent = `${index + 1} / ${readerQueue.length}`;
    $('#previous-question').disabled = index <= 0;
    $('#next-question').disabled = index >= readerQueue.length - 1;
    $('#back-to-list').href = navigationState.ids.includes(q.id) ? navigationState.returnTo : `#questions?category=${q.category}`;
    const returnTo = $('#back-to-list').getAttribute('href');
    $('#back-to-list span').textContent = returnTo.startsWith('#answers') ? '返回我的回答' : returnTo === '#home' ? '返回开始' : '返回题目列表';
    $('#open-standalone').href = q.file;
    frame.title = `题目：${q.title}`;
    if (loadedQuestionId !== q.id) {
      rememberVisit(q.id);
      loadedQuestionId = q.id;
      $('#reader-loading').textContent = '正在打开题目…';
      $('#reader-loading').hidden = false;
      clearTimeout(loadTimeout);
      navigateFrame(q.file);
      loadTimeout = setTimeout(() => {
        if (loadedQuestionId === q.id && !$('#reader-loading').hidden) $('#reader-loading').textContent = '若题目未显示，可点击上方「单独打开题目」。';
      }, 7000);
    }
  }
  function renderRoute(keepSearchFocus = false) {
    currentRoute = routeFromHash();
    document.body.classList.toggle('reading-question', currentRoute.view === 'reader');
    for (const name of ['home', 'questions', 'answers', 'reader']) $(`#${name}`).hidden = name !== currentRoute.view;
    const labels = { home: '开始', questions: '全部题目', answers: '我的回答', reader: '正在作答' };
    $('#view-name').textContent = labels[currentRoute.view];
    $('#global-search').placeholder = currentRoute.view === 'answers' ? '搜索我的回答与题目' : '搜索题目、关键词或编号';
    $('#global-search').setAttribute('aria-label', $('#global-search').placeholder);
    if (!keepSearchFocus) $('#global-search').value = currentRoute.q || '';
    if (currentRoute.view !== 'reader' && loadedQuestionId) {
      navigateFrame('about:blank'); loadedQuestionId = null; clearTimeout(loadTimeout);
    }
    if (currentRoute.view === 'home') renderHome();
    if (currentRoute.view === 'questions') renderCatalog();
    if (currentRoute.view === 'answers') renderAnswers();
    if (currentRoute.view === 'reader') renderReader();
    renderRail();
    document.title = `${currentRoute.view === 'reader' ? questionMap.get(currentRoute.id)?.title || '题目不存在' : labels[currentRoute.view]} · AI 面试手记`;
    if (!keepSearchFocus) {
      window.scrollTo({ top: 0, behavior: 'instant' });
      const heading = currentRoute.view === 'home' ? $('#home-title') : currentRoute.view === 'questions' ? $('#catalog-title') : currentRoute.view === 'answers' ? $('#answers-title') : null;
      heading?.focus({ preventScroll: true });
    }
  }
  function openQuestion(id, queue, returnTo) {
    if (!questionMap.has(id)) return;
    setQueue(queue, returnTo);
    navigate(questionHash(id));
  }
  function randomQuestion(pool, returnTo) {
    if (!pool.length) { toast('当前没有可选题目，请调整筛选。'); return; }
    const unanswered = pool.filter(q => !records.has(q.id) && q.id !== loadedQuestionId);
    const candidates = unanswered.length ? unanswered : pool.filter(q => q.id !== loadedQuestionId);
    const selected = (candidates.length ? candidates : pool)[Math.floor(Math.random() * (candidates.length || pool.length))];
    openQuestion(selected.id, pool.map(q => q.id), returnTo);
  }
  function exportAnswers() {
    reloadRecords();
    const items = sortedRecords();
    if (!items.length) { toast('还没有可导出的回答，先选一道题写下理解吧。'); renderRail(); return; }
    const now = new Date();
    const date = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const content = `# 我的面试回答\n\n导出日期：${date} · 共 ${items.length} 份回答\n\n` + items.map(item => `## ${item.question.title}\n\n题目：${item.question.id} · ${categoryMap.get(item.question.category).label}\n${item.updatedAt ? `\n记录更新：${new Date(item.updatedAt).toLocaleString('zh-CN')}\n` : ''}\n${item.text}\n\n---\n`).join('\n');
    const url = URL.createObjectURL(new Blob(['\ufeff', content], { type: 'text/markdown;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url; link.download = `ai-interview-answers-${date}.md`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    toast(`已导出 ${items.length} 份回答为 Markdown。`);
  }
  function refreshSavedData() {
    clearTimeout(refreshTimeout);
    refreshTimeout = setTimeout(() => {
      reloadRecords(); renderRail();
      if (currentRoute.view === 'home') renderHome();
      if (currentRoute.view === 'answers') renderAnswers();
      if (currentRoute.view === 'questions') renderCatalog();
    }, 100);
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('a[data-open-question]');
    if (link && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && event.button === 0) {
      event.preventDefault();
      const id = link.dataset.openQuestion;
      if (link.hasAttribute('data-catalog-question')) openQuestion(id, currentMatches.map(q => q.id), catalogHash({ ...currentRoute, page: currentPage }));
      else if (link.hasAttribute('data-saved-question')) openQuestion(id, sortedRecords().map(item => item.question.id), location.hash || '#answers');
      else openQuestion(id, questions.filter(q => q.category === questionMap.get(id).category).map(q => q.id), '#home');
    }
    const navigationLink = event.target.closest('a[href^="#"]:not([data-open-question])');
    if (navigationLink && /^#(?:home|questions|answers)(?:\?|$)/.test(navigationLink.getAttribute('href')) && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && event.button === 0) {
      event.preventDefault();
      navigate(navigationLink.getAttribute('href'));
    }
    const page = event.target.closest('[data-page]');
    if (page && !page.disabled) navigate(catalogHash({ ...currentRoute, page: Number(page.dataset.page) }));
    if (event.target.closest('[data-random]')) randomQuestion(questions, '#home');
    if (event.target.closest('[data-export]') && !event.target.closest('[data-export]').disabled) { exportAnswers(); if (drawer.open) drawer.close(); }
    if (drawer.open && event.target.closest('a[href^="#"]')) drawer.close();
  });
  $('#catalog-random').addEventListener('click', () => randomQuestion(currentMatches, catalogHash({ ...currentRoute, page: currentPage })));
  for (const field of ['category', 'difficulty', 'role', 'status']) $(`#filter-${field}`).addEventListener('change', event => navigate(catalogHash({ ...currentRoute, [field]: event.target.value, page: 1 }), true));
  $('#sort-order').addEventListener('change', event => navigate(catalogHash({ ...currentRoute, sort: event.target.value, page: 1 }), true));
  for (const selector of ['#reset-filters', '#empty-reset']) $(selector).addEventListener('click', () => navigate('#questions', true));
  $('#search-form').addEventListener('submit', event => {
    event.preventDefault();
    if (composing) return;
    const q = $('#global-search').value.trim();
    if (currentRoute.view === 'answers') navigate('#answers' + (q ? `?q=${encodeURIComponent(q)}` : ''));
    else navigate(catalogHash({ ...(currentRoute.view === 'questions' ? currentRoute : {}), q, page: 1 }));
  });
  function liveSearch() {
    if (composing || !['questions', 'answers'].includes(currentRoute.view)) return;
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      const q = $('#global-search').value;
      const hash = currentRoute.view === 'answers' ? '#answers' + (q ? `?q=${encodeURIComponent(q)}` : '') : catalogHash({ ...currentRoute, q, page: 1 });
      navigate(hash, true, true);
    }, 180);
  }
  $('#global-search').addEventListener('input', liveSearch);
  $('#global-search').addEventListener('compositionstart', () => { composing = true; clearTimeout(searchTimeout); });
  $('#global-search').addEventListener('compositionend', () => { composing = false; liveSearch(); });
  $('#previous-question').addEventListener('click', () => {
    const index = readerQueue.findIndex(q => q.id === currentRoute.id);
    if (index > 0) navigate(questionHash(readerQueue[index - 1].id));
  });
  $('#next-question').addEventListener('click', () => {
    const index = readerQueue.findIndex(q => q.id === currentRoute.id);
    if (index >= 0 && index + 1 < readerQueue.length) navigate(questionHash(readerQueue[index + 1].id));
  });
  $('#open-navigation').addEventListener('click', () => { drawer.showModal(); document.body.style.overflow = 'hidden'; $('#open-navigation').setAttribute('aria-expanded', 'true'); $('#close-navigation').focus(); });
  $('#close-navigation').addEventListener('click', () => drawer.close());
  drawer.addEventListener('close', () => { document.body.style.overflow = ''; $('#open-navigation').setAttribute('aria-expanded', 'false'); });
  window.addEventListener('resize', () => { if (innerWidth > 960 && drawer.open) drawer.close(); });
  window.addEventListener('hashchange', () => { clearTimeout(searchTimeout); renderRoute(); });
  window.addEventListener('storage', event => { if (event.key?.startsWith('agent-interview:') && event.key !== workspaceKey) refreshSavedData(); });
  window.addEventListener('pageshow', event => { reloadRecords(); renderRail(); if (event.persisted) refreshSavedData(); });
  window.addEventListener('message', event => {
    if (event.source !== frame.contentWindow || !event.data || typeof event.data !== 'object') return;
    if (location.protocol !== 'file:' && event.origin !== location.origin) return;
    if (event.data.type === 'interview:ready' && event.data.questionId === loadedQuestionId) { $('#reader-loading').hidden = true; clearTimeout(loadTimeout); }
    if (event.data.type === 'interview:draft-saved' && event.data.questionId === loadedQuestionId) refreshSavedData();
    if (event.data.type === 'interview:navigate' && event.data.questionId === loadedQuestionId && fileMap.has(event.data.file)) {
      const q = fileMap.get(event.data.file);
      if (!navigationState.ids.includes(q.id)) setQueue(questions.filter(item => item.category === q.category).map(item => item.id), `#questions?category=${q.category}`);
      navigate(questionHash(q.id));
    }
    if (event.data.type === 'interview:home' && event.data.questionId === loadedQuestionId) navigate('#home');
  });
  frame.addEventListener('load', () => {
    if (!loadedQuestionId) return;
    // This fallback also works if a cached question predates the workspace bridge.
    try {
      const childData = frame.contentDocument?.querySelector('#page-data');
      if (childData && JSON.parse(childData.textContent).questionId === loadedQuestionId) { $('#reader-loading').hidden = true; clearTimeout(loadTimeout); }
    } catch { /* file:// frame access can be restricted; the ready message handles it. */ }
  });
  reloadRecords();
  $('#global-search').value = routeFromHash().q || '';
  renderRoute(true);
})();
