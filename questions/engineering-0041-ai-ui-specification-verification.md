---
id: engineering-0041
title: 让 AI 生成界面时，如何把审美与交互目标变成可验证规格，并覆盖真实输入和边界状态？
category: engineering
tags: [ui-specification, design-tokens, composition, keyboard, accessibility]
difficulty: medium
role: both
contributor: 佚名
source: 洛小山《AI 产品从入门到精通》learn-ai（固定版本见参考）
status: published
updated: 2026-09-16
answers:
  - author: GPT-6
    type: ai
    model: GPT-6
    answered: 2026-09-16
    updated: 2026-09-16
---

## 问题

让 AI 生成界面时，如何把审美与交互目标变成可验证规格，并覆盖真实输入和边界状态？以聊天输入框为例，如何验收中文组合输入、键盘、取消、loading/空/错状态，以及设计一致性？

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**把“想要什么感觉”“必须怎样交互”“用什么证据验收”分开写，再建立对应关系。** “清晰、克制、适合长文输入”是审美和使用目标；字体、间距、状态、键盘行为及具体检查方法才是可以执行的约定。规格不能消灭审美判断，但能减少 AI 在未说明的地方随意发挥，也让评审知道哪里需要看图、哪里需要操作。

产品需求拆解见 [product-0002](product-0002-ai-prd-requirements.md)，AI 失败体验见 [product-0004](product-0004-ai-ux-failure-recovery.md)，实验装置与真实业务验收的区别见 [engineering-0040](engineering-0040-prompt-playground-reproducibility.md)。本题聚焦 AI 生成 UI 的交付规格与证据，不把一个好看的组件示例当作整条业务已经验收。

### 1. 先拆解参考，再固定规格和复用边界

先明确使用者、主要任务与环境，例如“中文写作者在桌面和窄屏上组织问题”。比较两种有理由的方向：简洁工具型便于观察输入与状态，柔和卡片型更接近消费聊天。选择需要能解释任务取舍；不要把“禁 emoji”“只能用某组件库”当普遍审美定律，也不能用课程作者的偏好代替当前项目的要求。

对获授权的参考，拆出信息层级、字阶、留白、对齐、控件形态和状态变化，而不是照抄页面或图片。把重复决策收敛成少量有语义的 design tokens；先搜索已有组件和 token，再决定复用或新增。相同语义应共享实现，合理差异则保留，例如危险操作不能为了“统一按钮”而失去辨识。

| 目标 | 本例可检查规格 | 验证方式 |
| --- | --- | --- |
| 输入优先、层级清楚 | 正文16px/1.6；宽屏标题32px、窄屏26px；主体最大980px；700px以下改为堆叠 | DOM/样式与溢出检查，加真实截图核对层级和留白 |
| 组件一致但状态可辨 | 6个颜色token、4/8/12/16/24/32px间距档；panel圆角20px、控件12px；按钮/下拉框至少44px高 | 复用样式及计算值检查；在普通、禁用、焦点和错误状态看图 |
| 必需信息可读 | 正文选定颜色对比度至少4.5:1、功能边界至少3:1、键盘焦点环3px；错误有文字，不只变红 | 对指定前景/背景计算比值，检查原生焦点，再做视觉与辅助技术验证 |
| 输入与结果可信 | 组合输入不发送、空白不发送、单请求等待、取消保留草稿、迟到结果不覆盖当前状态 | 状态断言、真实浏览器按键、合成事件及适用OS输入法分别验证 |

这些数值是本例规格，并非美感的通用公式；44px高也不等于完成全部可访问性标准。W3C WCAG 2.2 为键盘、焦点、标签、状态消息和对比度提供可核对要求，但选几条检查不能宣称整个产品符合 WCAG。

### 2. 把聊天框写成状态与交互契约

原创样例“聊稿”使用原生 textarea、button 和 select，复用同一控件圆角、高度与焦点 token；所有响应均由本地 mock 生成。页面只做一次提交与等待：输入 → loading → 成功/空回复/错误；取消先使当前请求身份失效，再通知 mock，并回到可编辑状态。这里选择等待时禁用编辑，简化单请求语义；若产品允许同时写下一条草稿，就需要把已提交文本、当前草稿及各自版本分开，不能在旧请求成功后清掉新草稿。

| 情境 / 输入 | 预期行为 | 关键检查 |
| --- | --- | --- |
| 初始空框或空白字符 | 发送禁用，说明下一步；Enter不创建请求 | trim后的空白与请求计数，不只看按钮颜色 |
| 中文组合输入中按Enter确认 | 不提交，不重建输入节点或改写正在组合的value | composition标志和isComposing；实际OS候选确认另测 |
| 普通Enter、Shift+Enter | 普通Enter发送；Shift+Enter保留原生换行，重复keydown不多发 | 浏览器按键、文本值、请求计数；不是仅调用回调函数 |
| loading | 单请求；编辑和发送禁用，取消可用，焦点移到取消；aria-busy为true | 重复点击不增加请求；用户能识别等待且能退出 |
| Escape或点击取消等待 | 草稿保留、焦点回输入框，旧请求ID失效 | 本地等待结束与真实服务停止分开；迟到结果必须被丢弃 |
| 成功 / 空回复 | 成功显示文本并清空已提交草稿；空回复明确提示并保留草稿 | 空字符串不生成空白回复气泡，不能把空回复误说成网络失败 |
| 错误 | 显示可采取动作的文案，恢复编辑和发送，保留草稿 | 错误状态、焦点、重试入口和敏感错误信息；不直接显示底层stack |

本例取消的是等待，不撤回已经显示的用户消息；显式重发形成新尝试记录。取消后即使旧 promise 仍完成，也只有匹配当前 pending ID 的结果才能更新界面。AbortSignal 是协作通知，不是服务端已停止的回执；本例专门让一个 mock 忽略取消，验证 UI 不被它覆盖。

### 3. 中文输入不能只测已经填好的汉字

W3C UI Events 的固定规范文本把 KeyboardEvent.isComposing 定义为事件是否处于 compositionstart 与对应 compositionend 之间。应用不应把确认候选词的 Enter 当成发送，也不应在渲染时替换整个输入节点，打断原生编辑过程。不同浏览器与OS的事件顺序仍需实际核对，规范文本不是实现兼容性测试结果。

本例同时检查事件的 isComposing 和组件跟踪的 composition 状态；只在普通发送快捷键时 preventDefault，保留 Shift+Enter 和组合输入的默认行为。下面是实际附件代码摘录，依赖完整样例的 canSend、DOM和状态变量，并非可直接替换所有框架输入组件的通用实现：

```javascript
function shouldSendKey(event, value, pending, composing) {
  return event.key === 'Enter' && !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey
    && !event.repeat && !event.isComposing && canSend(value, pending, composing);
}

function cancelWaiting() {
  if (!pending) return;
  const prior=pending; pending=null; sequence++;
  phase='cancelled'; events.push({kind:'cancel',id:prior.id});
  prior.controller.abort(); render(); input.focus();
}
```

浏览器验证分两组：通过自动化填入合成中文并用 CDP 驱动 Enter、Shift+Enter、Control+Enter、Tab、Shift+Tab、Escape 和点击；另外显式 dispatch CompositionEvent、InputEvent、KeyboardEvent，模拟组合开始、确认、提交文字、组合结束。后一组事件的 isTrusted=false，不能叫“真实输入法测试”；前一组按键的 isTrusted=true 也不证明真人操作或OS候选窗已被测试。真实OS输入法、其他浏览器与手机软键盘在本轮均为 not_run。

### 4. 原创样例的实际证据

2026-09-16 使用 agent-browser 0.23.4、独立 profile 的 HeadlessChrome/153.0.0.0 实跑本地页面。没有打开用户聊天或业务系统，没有读取凭据、调用模型或修改真实配置。

**16项 Node 逻辑/mock 测试通过，25项浏览器检查通过。** 浏览器覆盖空白、换行、组合状态和独立isComposing标志、重复键/点击、Tab焦点、loading锁定、Escape与按钮取消、成功/空回复/错误、长文本窄屏、文本不作为HTML执行，以及取消后旧响应丢弃。样例8个mock任务均已结束，active=0；其中两次合作式abort和一次忽略abort后的迟到完成，不是服务器资源回收的证据。

还保留同一 `probe_ime.mjs` 的三项断言：人为移除组合输入门禁的 legacy 判定得到真实 exit1 / 3 tests / 1 fail，固定实现 exit0 / 3 pass；普通Enter与Shift+Enter两个控制都保留。该反例发生在纯逻辑层，不冒充浏览器或OS输入法的实测缺陷；probe与UI逻辑文件hash留在附件中。

DOM/样式实测中，窄屏请求viewport为390×844 CSS px，无横向溢出，控件圆角均12px、高度至少44px。选定配色的对比度：muted文字/页面约5.31:1，白字/主按钮约7.54:1，功能边界/白底约5.74:1。这些是指定token的计算结果，不代表整个界面所有像素或完整WCAG验收。

本轮真实生成7张当前版本截图并逐张看图，覆盖宽屏初始、键盘焦点、loading、取消、成功、错误及窄屏错误；另保留1张初版图。初看后只加强了功能控件边界，没有把装饰线也加重。当前截图中焦点未被裁掉、操作与状态可读，窄屏改为堆叠；长消息和textarea有自己的滚动区，截图不代表全部内容都同时可见。

截图同时记录请求viewport、DPR、PNG实际尺寸与hash。full-page截图会受页面高度和滚动条影响，例如窄屏PNG为375×1245，不能把请求的390×844当作图片尺寸。DOM断言不能代替这一步图像检查，截图也不能证明键盘、焦点或异步状态正确。

完整HTML/CSS/JS、逐命令日志、原始TAP、浏览器观测及PNG在原创复跑包中。浏览器close成功后核对所属profile进程为空、专属daemon PID已退出，再删除本次profile和失效的会话元数据；没有发信号或留下常驻服务。真实OS输入法、屏幕阅读器播报、真实手机、其他浏览器及服务端取消仍为 not_run。

### 5. 选实现方式与验收层，不选审美教条

| 方案 | 适用与代价 | 不适用或不足 |
| --- | --- | --- |
| 复用现有设计系统与成熟组件 | 适合已有业务；可沿用token、可访问性和交互约定，减少重复实现 | 库的默认外观不一定适合目标；仍需验证主题覆盖、IME与业务状态，不能“用了库就通过” |
| 用原生控件做独立原型并写明规格 | 适合探索和隔离验收；依赖少、事件与状态容易观察，本例采用此方式 | 自定义复杂组件、辅助技术与跨平台成本需自己承担；原型通过不能直接当业务集成通过 |

验收应将设计规格、组件/状态测试、浏览器操作、真实输入法矩阵和图像检查分别列出。改动token或公共组件后，重看受影响状态；改动输入事件后，重跑组合输入和键盘流程；接入真实服务后，核对取消/超时/重试与实际副作用。记录代码版本、环境、未执行项和原始证据，缺证据不要补造“通过”。

### 常见误区与追问

- **“禁用某种图标或套用某组件库就是好设计。”** 风格选择依赖受众和任务；统一token、语义标签和一致交互可以检查，偏好不能冒充普适审美标准。
- **“截图好看就说明流程正确。”** 静态图看不到组合输入误发、重复提交和迟到响应覆盖；必须操作并观察状态。
- **“dispatch了composition事件就测完中文输入法。”** 合成事件只覆盖构造的序列；真实候选选择、取消、焦点切换及OS/浏览器顺序仍需验证。
- **追问：生成中的下一条草稿也要可编辑，怎么改？** 分离已提交快照与当前draft/version，取消只作用于对应请求；成功回调不能无条件清空正在编辑的新草稿，再补并发与焦点测试。
- **追问：后端不支持取消，本地还能提供取消按钮吗？** 可以明确提供“取消等待”并丢弃旧结果，但不能承诺任务已停止或费用已避免。若涉及外部副作用，还需服务端状态、幂等或补偿协议，不能靠按钮变灰推断完成。

## 参考

- 洛小山《AI 产品从入门到精通》，learn-ai 固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/taste-8.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/taste-8.html)、[slides/taste-11.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/taste-11.html)、[slides/ixd-2.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/ixd-2.html)、[slides/ixd-9.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/ixd-9.html)、[slides/vibe-3b.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-3b.html)、[slides/vibe-8.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-8.html)。作为参考拆解、状态、复用与中文输入的线索；未将作者禁用项、组件偏好或训练数据判断当普遍事实，未搬运AGPL课件正文、代码或图片。
- W3C UI Events 编辑草案，固定 `8c1b80982c16b10f28a210e4541ac799dbe39a51`：[KeyboardEvent](https://github.com/w3c/uievents/blob/8c1b80982c16b10f28a210e4541ac799dbe39a51/sections/event-keyboardevent.txt#L223-L232)、[composition与按键顺序](https://github.com/w3c/uievents/blob/8c1b80982c16b10f28a210e4541ac799dbe39a51/sections/event-compositionevent.txt#L149-L174)。固定的是规范文本，不是浏览器或OS实现版本；真实兼容性仍须实测。
- W3C，[WCAG 2.2 Recommendation，2023-10-05](https://www.w3.org/TR/2023/REC-WCAG22-20231005/)。核对1.4.3文字对比、1.4.11非文字对比、2.1.1键盘、2.4.7焦点可见、3.3.2标签与4.1.3状态消息；本文仅检查选定方面，不宣称完整合规。
