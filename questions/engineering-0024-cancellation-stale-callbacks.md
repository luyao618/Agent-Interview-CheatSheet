---
id: engineering-0024
title: 用户取消 Agent 时，各层怎样收尾，如何避免上一轮回调影响下一轮？
category: engineering
tags: [cancellation, abort-signal, stale-callbacks, durability, side-effects]
difficulty: hard
role: engineer
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

用户取消 Agent 时，各层怎样收尾，如何避免上一轮回调影响下一轮？分别推演模型流中断、工具运行中取消与强制崩溃的日志，区分 signal、当前界面、已落盘结果和工具副作用。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**取消是在请求停止后续工作，不是让过去发生的事情消失。** 需要分别回答：是否已发出取消、执行器是否已停、哪些结果已保存、哪个外部动作已提交、哪个回调仍有权更新当前轮。把它们压成一个 `cancelled` 布尔值，会同时丢掉资源状态和业务事实。

[agent-0016](agent-0016-checkpoint-resume.md) 讨论恢复，[engineering-0002](engineering-0002-idempotency-distributed-transaction.md) 讨论幂等/补偿；[engineering-0021](engineering-0021-llm-queue-backpressure.md) 解释取消待确认仍占容量，[agent-0055](agent-0055-turn-loop-input-semantics.md) 解释输入领取与退出。本题补充**取消逐层传播、跨轮回调提交门禁和已保存结果的去向**，不复写完整事务系统。

### 1. 先拆开取消的五层状态

| 层次 | 取消时做什么 | 不能从中推出什么 |
| --- | --- | --- |
| UI / 输入入口 | 显示 cancel requested、停止接受该轮的新动作；新输入明确属于哪一轮 | 用户不再等待，不代表后台停止；不要在仍有未知副作用时显示“已回滚” |
| turn / 调度循环 | 对该轮 signal 发出取消，停止发起新 step/工具，安排已有操作收尾 | 不应顺便 abort 新轮，也不能清空所有待处理输入 |
| 模型流 / 传输适配器 | 把 signal 传给支持它的 API；检查安全点，关闭本地 reader、移除监听并标记 partial/aborted | 本地断开不证明服务端停止计算、不计费或不会再有排队回调 |
| 工具 / 执行器 | 请求合作式停止，确认本地句柄/子进程状态；对副作用分别记 submitted/committed/unknown | 已发付款、邮件或文件写入不会因 Promise 被取消就撤销 |
| 日志 / 结果 / 恢复层 | 保留已确认结果与其 owner；取消状态追加记录，未知动作保留对账入口 | “没有成功回调”既不等于“没有提交”，也不等于“该删除已保存结果” |

成功结束的工具结果仍可属于一个最终被取消的 turn。例如用户取消的是“继续写总结”，不是撤销已经完成的查询。真正需要补偿时，调用具有自身幂等和失败状态的补偿动作；补偿也不是时光倒流。

### 2. 每轮一个 signal，回调在提交时核对身份

每轮创建新的 AbortController，回调捕获本轮上下文，绝不在回调发生时再去读取“当前 controller”当作自己的 controller。取消是单向信号：Node.js **22.18.0** 的 AbortController 只触发一次 abort；新一轮应得到新的、未取消的 signal。复用旧 signal 会让新工作立即取消；把全局布尔值重置为 false，则会让旧回调误以为自己重新获得资格。

可将会话关闭、该轮取消与该操作 deadline 的 signal 用 `AbortSignal.any(...)` 组合。子操作取消不应反向取消无关兄弟或新轮；会话级关闭则应阻止后续所有轮。监听器要捕获自己的 owner，并在结束时解除，使用 `{ once: true }` 也不能替代所有成功路径的清理。

回调带上并核对 `(session_id, turn_id, step/tool_call_id, attempt_id, owner_generation)`。这些身份来自可信适配器绑定，不能从模型或工具正文自报的字段取得。**检查与写入必须是同一个提交动作**：如果先检查、再 await、最后写共享状态，期间已经换轮，检查就过期了。进程内可以在一次同步临界区提交；持久存储需要带 expected generation 的 CAS/事务，新进程启动也不能把 generation 重置到会撞上旧回调的值。

错误分支和 finally 也要保留相同的 owner：不能在 catch 中统一写 `current.error` 或取消当前 controller，否则即使文本回调有门禁，旧错误仍会干扰新轮。要把两个出口分开：

- **当前视图/控制状态出口：** 只允许仍拥有当前轮且未取消、未结束的回调更新文本、按钮、spinner 或活动句柄。旧 finally 只能清理自己的资源；比较 owner 后才可清空全局 active 指针。
- **原轮结果/审计出口：** 经过鉴权、身份和幂等检查的迟到结果，可以继续记到原 turn/attempt 的账本用于对账。隔离旧回调不等于丢弃真实结果；它无权把新轮写成成功/失败，也不能释放新轮的资源名额。

### 3. 选择停止方式，而不是给所有取消一种承诺

| 方式 | 适用情况 | 代价与不适用边界 |
| --- | --- | --- |
| 合作式取消并等待收尾 | API/工具支持 signal、安全点或可取消事务 | 通常能执行 finally，但可能慢、忽略信号或卡住；不能承诺立即停止 |
| 先撤销旧轮的展示权限，后台继续有限收尾 | 用户要开始新轮，但旧操作仍需返回状态 | 响应更及时，代价是旧资源仍占用；新轮的实际执行仍须通过容量准入，不能凭 UI 已换轮无限开工 |
| 超过政策允许的收尾期限，终止专属进程 | 失控工作已放在可管理的隔离进程，且允许丢失未提交中间态 | 硬终止不运行该进程的清理逻辑；也不撤销其先前对远端的操作。不适合按进程名杀共享宿主或假定整个子进程树已回收 |

应把“已发信号”“本地进程已退出”“stdio 已关闭”“远端动作已对账”分别记下来。Node 的 `subprocess.killed` 只表示成功发送了信号，不证明进程已终止；需要观察 exit/close 或等价 wait 结果。收尾期限要按工具契约和预算制定，不能从某篇课程的固定毫秒数推成通用保证。

### 4. 三类日志：本地验证能证明什么

以下记录来自 **2026-09-16、Node.js 22.18.0** 的原创本地 fixture，流分片由脚本触发、工具是写专属临时文件的 fake；不是供应商流协议、真实付款或生产性能实测。日志节选保留实际事件字段；不同轮的结果始终带自己的 turn/operation。

**A. 模型流中断：旧片段保留，旧流不再更新新轮。** 输入为“旧流已显示片段”，用户取消后立刻建立新轮；旧适配器检测 `throwIfAborted()` 得到 AbortError，同时模拟一个已排队的迟到文本回调：

```jsonl
{"event":"partial","turn":"stream_old","text":"旧流已显示片段"}
{"event":"cancel_requested","turn":"stream_old"}
{"event":"turn_started","turn":"stream_new"}
{"event":"delivery_dropped","turn":"stream_old"}
{"event":"result_recorded","turn":"stream_old","operation":"model","value":"aborted"}
{"event":"turn_finished","turn":"stream_old","outcome":"cancelled"}
```

预期与实际一致：旧 partial 仍在临时日志中，不能冒充完整答案；新轮只显示“新流文本”，其 signal 仍未取消。旧 finish 没有把新轮 active 清掉。这里只证明本地 signal 与门禁行为，没有真实 LLM/网络请求，因此不能推出远端已停止或账单为零。

**B. 工具执行中取消：结果留在原轮，副作用不回滚。** fake tool 已等待执行屏障，取消不会解除它的 Promise。脚本先开新轮，再放行这个故意忽略 signal 的本地工具；工具向独立 receipt 文件写入并 fsync 一个已提交回执：

```jsonl
{"event":"cancel_requested","turn":"tool_old"}
{"event":"turn_started","turn":"tool_new"}
{"event":"partial","turn":"tool_new","text":"新轮不受影响"}
{"event":"result_recorded","turn":"tool_old","operation":"op1","value":"committed:fixture"}
{"event":"delivery_dropped","turn":"tool_old"}
{"event":"turn_finished","turn":"tool_old","outcome":"cancelled"}
```

独立 receipt 为 `{"operation":"op1","state":"committed","fixture":true}`。取消时 old.pending 仍为 1，提前 finish 被拒绝；收到原轮结果后才移除原轮 pending。旧结果在旧账本可查，不能覆盖新文本；相同结果重复回调不重复记账，冲突结果拒绝。`turn outcome=cancelled` 与 `operation=committed` 可以同时成立，不能据前者伪造后者回滚。

**C. 强制崩溃：没有 finally，不等于没有已保存结果。** 自建子进程先把下列日志逐条 append 并 fsync，再把 fake 工具的 committed receipt 写入另一文件。它报告带 PID/父 PID/随机 nonce/临时目录的 READY 后，父测试在“副作用有回执，但任务结果尚未确认”的窗口发送 SIGKILL：

```jsonl
{"event":"turn_started","turn":"crash_old"}
{"event":"partial_persisted","turn":"crash_old","text":"已落盘片段"}
{"event":"effect_submitted","turn":"crash_old","operation":"op1"}
```

两次 SIGKILL 验证中，父进程 wait 得到信号退出（Python POSIX returncode=-9），重读仍得到上述三行和独立 committed receipt；没有 `finally_ran`、`tool_result` 或完整 turn 完成记录。正常退出对照则多出 `finally_ran`，说明崩溃用例不能依赖清理块收尾。全部三个专属子进程已回收，临时目录已删除；发送信号前还核对了工作区 daemon PID，未操作共享进程。

恢复时只看任务日志，应把 op1 视为 **结果未知、需对账**；读取这个 fixture 的独立回执后才确认其已提交，不再重放。真实系统应查询相应权威系统，不因为本地文件有个 submitted 就断言远端 committed。这个实验只检验**本机进程被终止后**文件可读；不是断电、磁盘故障、远端事务或跨主机持久性测试。`fsync` 的具体语义仍取决于 OS/设备，不能把文件日志当成已经具备原子事务、尾记录校验与崩溃恢复协议的数据库。

### 5. 一个最小的跨轮回调门禁

下面是产生前两类日志所用的原创门禁，固定 Node.js 22.18.0。`appendRecord` 是调用方提供的同步函数，测试中对专属临时 JSONL 文件执行 append + fsync；类本身不实现数据库事务或恢复。示例每轮只登记一个模型/工具操作，多 step/重试的流回调还需额外检查 operation/attempt 身份。已知对象引用模拟进程内 owner，跨进程不能直接照搬这个比较。

```javascript
// Original synchronous, single-process teaching gate. Node.js 22.18.0.
export class TurnGate {
  constructor(appendRecord) {
    this.appendRecord = appendRecord; // Synchronous; fixtures append + fsync.
    this.active = null;
    this.runs = new Map();
  }
  start(id) {
    if (typeof id !== 'string' || !/^[a-z0-9_-]{1,40}$/.test(id) || this.runs.has(id)) {
      throw new Error('invalid or reused turn id');
    }
    if (this.active && !this.active.controller.signal.aborted) throw new Error('active turn');
    const run = {id, controller: new AbortController(), pending: new Set(),
                 operations: new Set(), results: new Map(), text: '', done: false};
    this.appendRecord({event: 'turn_started', turn: id});
    this.runs.set(id, run);
    this.active = run;
    return run;
  }
  known(run) {
    if (!run || this.runs.get(run.id) !== run) throw new Error('unknown turn owner');
  }
  enter(run, operation) {
    this.known(run);
    run.controller.signal.throwIfAborted();
    if (run.done || typeof operation !== 'string' || !operation || run.operations.has(operation)) {
      throw new Error('invalid operation');
    }
    run.operations.add(operation);
    run.pending.add(operation);
  }
  cancel(run) {
    this.known(run);
    if (run.done || run.controller.signal.aborted) return false;
    run.controller.abort(new DOMException('user cancellation', 'AbortError'));
    this.appendRecord({event: 'cancel_requested', turn: run.id});
    return true;
  }
  publish(run, text) {
    this.known(run);
    if (typeof text !== 'string') throw new Error('invalid text');
    if (this.active !== run || run.controller.signal.aborted || run.done) {
      this.appendRecord({event: 'delivery_dropped', turn: run.id});
      return false;
    }
    // No await between identity/signal checks and mutation of this turn.
    this.appendRecord({event: 'partial', turn: run.id, text});
    run.text += text;
    return true;
  }
  complete(run, operation, value) {
    this.known(run);
    if (!run.operations.has(operation) || typeof value !== 'string') throw new Error('invalid result');
    if (run.results.has(operation)) {
      if (run.results.get(operation) !== value) throw new Error('conflicting result');
      return false;
    }
    // Even a cancelled/stale turn may receive its own authoritative result.
    this.appendRecord({event: 'result_recorded', turn: run.id, operation, value});
    run.results.set(operation, value);
    run.pending.delete(operation);
    return true;
  }
  finish(run) {
    this.known(run);
    if (run.pending.size) throw new Error('local work has not settled');
    if (run.done) return false;
    this.appendRecord({event: 'turn_finished', turn: run.id,
                       outcome: run.controller.signal.aborted ? 'cancelled' : 'completed'});
    run.done = true;
    if (this.active === run) this.active = null; // Old finally cannot clear new turn.
    return true;
  }
}
```

每次回调捕获自己的 run；`publish` 在最终写入点检查身份和 signal，`complete` 始终写原 run，`finish` 只可能清空自己的 active。Map 保留了本次有限演示的历史，生产需有界保留、全局唯一的持久身份和回调鉴权。日志写入失败、进程在 append 与内存更新之间崩溃等情况也需持久层对账，不能凭这个类承诺 exactly-once。

### 6. 固定运行时源码只支持相应层次的结论

- Node.js **v22.18.0**，commit `c9ff1aecf268802fc29272c93aaa4b0691c7c6d8`：[AbortController / AbortSignal 文档](https://github.com/nodejs/node/blob/c9ff1aecf268802fc29272c93aaa4b0691c7c6d8/doc/api/globals.md#L24-L225) 说明它向支持的 Promise API 发送取消信号、abort 事件只发生一次、any 组合、reason 和监听器清理。它没有承诺取消任意函数或回滚副作用。
- Pi **v0.57.1**，commit `a9cedccdde77e9d765303463d8a6cd11c58f7a7f`：[Agent.abort](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/agent/src/agent.ts#L323-L328) 调用当前 controller；[_runLoop](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/agent/src/agent.ts#L413-L462) 新建 controller 并传 signal；[finally](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/agent/src/agent.ts#L552-L559) 清理该次运行状态。这里仅核对源码，未运行 Pi；“有 signal 传播”不能当作本文的持久日志、跨轮 fence 或强制终止方案已在上游实现的证据。

把实现观察、教学日志和生产要求分开，才不会一边讲取消隔离，一边用一个共享 `current` 指针解释所有回调。

## 延伸 / 追问

**用户取消后马上发新消息，能直接开始新轮吗？** 可以先建立新的交互身份，但实际执行仍受资源/并发准入约束；旧工具未停止的占用继续记录。新轮使用新 signal，旧结果只回原账本，不覆盖新轮或重复已提交的动作。

**旧结果回来了，全部丢掉是不是最安全？** 丢弃它对当前 UI 的写权限，与丢弃业务事实不是一回事。已鉴权、属于原 attempt 的结果可能是判断 committed/unknown 的关键证据，应按原身份幂等保存；无法验证的回调隔离待查，不能顺手记给当前轮。

**为什么全局布尔值加锁仍不够？** 锁只能保证该次读写互斥；新轮把值重置后，旧回调仍可能合法读到 false。必须比较身份/epoch，并让检查与实际写入处于同一提交边界。不同回调共享互斥锁，也不会自动获得正确的归属语义。

## 常见误区

- “取消即回滚”：取消改变后续执行意图，副作用需要独立查询/补偿。
- “共享一个全局 cancelled 就能隔离各轮”：重置布尔值无法区分旧回调和新工作。
- “finally 一定会执行”：强制进程终止可能直接跳过，恢复不能依赖它补齐日志。
- “kill 成功说明资源都释放了”：还需 wait/exit、句柄收尾及适用的远端状态确认。
- “已落盘就说明整轮成功”：完整结果、partial、submitted 与 committed 必须保持不同状态。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/codex-05.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-05.html)、[slides/dsh-7.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-7.html)。只保留学习来源，不搬运 AGPL 素材，不把课程中的取消时限或“不丢结果”描述当普遍保证。
- Node.js **v22.18.0 / `c9ff1aecf268802fc29272c93aaa4b0691c7c6d8`**：正文的 AbortSignal 文档；[child_process kill/killed](https://github.com/nodejs/node/blob/c9ff1aecf268802fc29272c93aaa4b0691c7c6d8/doc/api/child_process.md#L1668-L1791)、[exit/close](https://github.com/nodejs/node/blob/c9ff1aecf268802fc29272c93aaa4b0691c7c6d8/doc/api/child_process.md#L1435-L1565)、[fs.fsyncSync](https://github.com/nodejs/node/blob/c9ff1aecf268802fc29272c93aaa4b0691c7c6d8/doc/api/fs.md#L5652-L5662)。这些 API 文档不等于本例对真实业务系统的实验。
- Pi **v0.57.1 / `a9cedccdde77e9d765303463d8a6cd11c58f7a7f`**：[package.json](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/agent/package.json)、[MIT LICENSE](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/LICENSE)；具体取消传播代码见正文。
- 版本/来源核对和本地验证日期为 **2026-09-16**。所有日志只涉及自编 fixture、自建子进程与专属临时数据，没有修改真实调度或访问业务账户。
