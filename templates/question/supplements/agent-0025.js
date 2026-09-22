(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
      const thoughtNote = '模型决定下一步；这里展示的是教学用决策摘要。';
      const actionNote = '模型生成调用参数，运行时检查权限并执行工具。';
      const observationNote = '观测由工具返回，运行时将其回填到下一轮上下文。';
      const normalTrace = [
        { stage:'thought', round:1, title:'先确认，我还缺什么信息？', content:'需要分别核对预印本时间和会议发表信息。先搜索论文，找到可验证的来源。', note:thoughtNote },
        { stage:'action', round:1, title:'选择工具，给出结构化参数', code:'search({\n  query: "ReAct paper arXiv ICLR"\n})', note:actionNote },
        { stage:'observation', round:1, title:'搜索结果提供了新的线索', content:'找到 arXiv:2210.03629，首次提交于 2022 年 10 月。搜索摘要还提到 ICLR 2023，需要打开来源进一步确认。', note:observationNote },
        { stage:'thought', round:2, title:'有了新证据，调整下一步', content:'预印本时间已经找到。会议年份还需要确认，下一步读取论文页面，区分首次发布与正式发表。', note:thoughtNote },
        { stage:'action', round:2, title:'读取论文页面，核对信息', code:'open_page({\n  url: "https://arxiv.org/abs/2210.03629"\n})', note:actionNote },
        { stage:'observation', round:2, title:'两条信息都获得来源支持', content:'论文页面记录：首次提交为 2022-10-06；会议发表信息为 ICLR 2023。现在可以分别回答两个时间点。', note:observationNote },
        { stage:'final', round:2, title:'证据足够，给出最终答案', content:'ReAct 论文于 2022 年 10 月首次发布预印本，随后发表于 ICLR 2023。引用：arXiv:2210.03629。', note:'停止继续调用工具。完成任务、预算耗尽或无法安全推进，都可以成为停止条件。' }
      ];
      const errorTrace = [
        normalTrace[0], normalTrace[1],
        { stage:'observation', round:1, title:'超时也是一条 Observation', code:'{\n  error: "SEARCH_TIMEOUT",\n  retryable: true\n}', note:'运行时回填真实错误，不把失败包装成搜索成功。' },
        { stage:'thought', round:2, title:'检查预算，再选择有限重试', content:'搜索是只读操作，当前仍有预算。按策略退避后重试一次；再次失败就说明限制，不编造论文信息。', note:'错误反馈改变后续行动。重试次数与截止时间由运行时限制。' },
        { stage:'action', round:2, title:'在预算内重新搜索', code:'search({\n  query: "2210.03629 publication"\n})', note:'演示中仅重试一次。付款、写入等操作还需先确认状态或保证幂等。' },
        { stage:'observation', round:2, title:'重试成功，拿到论文信息', content:'本次返回包含论文来源及元数据：arXiv 首次提交 2022-10-06，发表于 ICLR 2023。', note:observationNote },
        normalTrace[6]
      ];
      let scenario = 'normal';
      let step = 0;
      const trace = () => scenario === 'normal' ? normalTrace : errorTrace;
      function renderTrace() {
        const item = trace()[step];
        $$('[data-stage]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.stage === item.stage)));
        $$('[data-scenario]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.scenario === scenario)));
        $('#loop-pane').classList.toggle('is-final', item.stage === 'final');
        $('#trace-kind').textContent = item.stage === 'final' ? 'FINAL ANSWER' : item.stage.toUpperCase();
        $('#trace-kind').style.color = item.stage === 'observation' ? 'var(--amber)' : item.stage === 'final' ? 'var(--green)' : 'var(--blue)';
        $('#round-label').textContent = item.stage === 'final' ? '任务完成' : `第 ${item.round} 轮`;
        $('#trace-title').textContent = item.title;
        $('#trace-content').textContent = item.content || '';
        $('#trace-content').hidden = !item.content;
        $('#trace-code').textContent = item.code || '';
        $('#trace-code').hidden = !item.code;
        $('#trace-note').textContent = item.note;
        $('#step-count').textContent = `${String(step + 1).padStart(2,'0')} / 07`;
        $('#prev-step').disabled = step === 0;
        $('#next-label').textContent = step === trace().length - 1 ? '再看一遍' : '下一步';
      }
      $('#next-step').addEventListener('click', () => { step = (step + 1) % trace().length; renderTrace(); });
      $('#prev-step').addEventListener('click', () => { step = Math.max(0, step - 1); renderTrace(); });
      $('#reset-loop').addEventListener('click', () => { step = 0; renderTrace(); });
      $$('[data-stage]').forEach(button => button.addEventListener('click', () => { const round = trace()[step].round; step = trace().findIndex(item => item.stage === button.dataset.stage && item.round === round); renderTrace(); }));
      $$('[data-scenario]').forEach(button => button.addEventListener('click', () => { scenario = button.dataset.scenario; step = 0; renderTrace(); }));

})();
