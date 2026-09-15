---
id: engineering-0026
title: 模型流尚未结束就执行工具时，如何在断流或取消后保持 tool call/result 记录完整？
category: engineering
tags: [agent, streaming, tool-calling, event-log, cancellation, concurrency]
difficulty: hard
role: engineer
contributor: 佚名
source: 洛小山《AI 产品从入门到精通》learn-ai，固定版本学习线索
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

模型流尚未结束就执行工具时，如何在断流或取消后保持 tool call/result 记录完整？两个工具并行，第二个先结束，随后模型断流，最终 transcript 应保留什么？

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 回答 2026-09-16

核心是把**模型流、工具执行、记录提交**看作三个不同的生命期。模型停止输出，只能说明不能再收新调用；已经启动的工具仍需要有人收尾。每个工具必须先有可追踪的调用记录，然后才能执行；离开收流循环后，统一收集已启动任务的结果。没有证据的结果保持 unknown，不为了凑齐 call/result 而编造成功、失败或回滚。

本题补的是流与工具重叠时的收尾边界。并行依赖和幂等设计见 [agent-0032](agent-0032-parallel-tool-calling.md)，事件真源与请求重建见 [engineering-0025](engineering-0025-event-log-model-projection.md)，分层取消见 [engineering-0024](engineering-0024-cancellation-stale-callbacks.md)。这里不把“能拼成一份 transcript”当成“能直接发给任意模型”。

### 1. 从分片到执行，跨过哪些门槛

| 层次 | 已知事实 | 可以做什么 |
| --- | --- | --- |
| partial chunk | 收到一段文本或参数字符；可能还在字符串中间 | 按 attempt/item ID 重组、暂态展示、留诊断记录；不能补括号后执行 |
| 完整且已授权的 call item | 适配器确认该调用不可再改写，完整参数通过 Schema、工具名、当前权限和限额检查 | 将不可变的 `run/attempt/call_id/ordinal/name/args` 提交，再分发工具 |
| 工具观测 | 收到返回值，或仅观测到本地异常/取消 | 立即记录真实返回或执行状态；异常不自动证明远端动作没有发生 |
| 模型终态 | 正常完成、断流、取消或错误 | 正常终态才提交完整 assistant 消息；失败分片可保留为 chunk，带失败状态，不能伪装正常答案 |
| drain 收尾 | 已启动任务已收集，或剩余项有明确的待核实记录及持有者 | 按调用顺序生成读模型，决定能否开始下一轮；未知项不能偷偷消失 |

**完整调用不等于完整 assistant 消息。** 只有具体协议/适配器确实提供不可变的逐调用结束边界，才能在整个响应结束前启动。`JSON.parse` 成功、收到任意 `*_end` 或 UI 看似完整，都不能代替协议保证。供应商要求等完整响应、存在工具拒绝/改写的后续可能、需要人工批准，或调用有不可逆副作用时，应延后执行。本例只允许两个自制只读 `lookup`，不模拟真实授权系统。

最小不变量是：启动执行前，该调用记录已经提交；每份真实结果必须引用同 attempt 中已接受的 call；重建后每个已接受 call 都能找到真实观测或明确的 unresolved 状态。重复的确认事件不能重复分发，同 ID 不同参数必须拒绝；这种去重只覆盖当前 Run，不能冒充跨进程或业务侧 exactly-once。

### 2. drain 管所有权，排序管呈现

收流循环的正常、异常和用户取消出口应汇到同一个收尾路径：关闭准入 → 固定已启动集合 → drain → 提交收尾状态 → 决定结束或下一 attempt。工具必须先并发启动，再等待集合；如果每收到一个调用就 `await execute()`，即使容器名叫队列也已经串行了。

**终态日志写入也可能失败，不能把它放在任务回收的保护范围之外。** 准入关闭通知必须在写入失败时仍然发出；已启动任务由 `finally` 取消并收集，保留首次存储异常后再抛给调用者。坏日志拒绝后续写入，不能补造结果或宣称 DrainClosed；可靠前缀里缺少观测的 call 仍是 unresolved。等待通知的一方也要同时观察生产该通知的任务：任务已经失败就取回异常，不能只等一个永远不来的 Event。工具启动、返回和 closing 的通知都遵循这一规则。

记录的真实完成顺序可以是 `c2 → c1`，模型输入投影仍可稳定按 `ordinal` 排成 `c1 → c2`。不要重写日志来伪造完成时间，也不要为了有序呈现而把已完成的 c2 只留在内存等 c1：应立即保存观测，再在读模型中排序。按调用顺序是本例的确定性选择，具体 provider 对结果位置、消息分组和 call ID 的要求还要由适配器校验。

CPython 3.11.8 的 `asyncio.gather` 按传入顺序返回结果；默认模式会先传播首个异常，但其他任务可能继续运行，所以仅 catch 该异常就退出不能算 drain。`TaskGroup` 遇到未处理异常会取消兄弟任务，适合整组失败策略；若要保留独立查询结果，须先区分业务失败与调度/存储失败。`gather(return_exceptions=True)` 也不能把日志写失败吞成一个正常工具结果。

本例用 `wait(..., FIRST_EXCEPTION)` 在存储等未处理异常发生时提前进入回收，再以 `gather(return_exceptions=True)` 取回所有任务结果。普通工具异常已转换为 unknown 观测，不会被误当成存储失败去中断其他独立工具；存储出错则停止本次收尾提交，并传播首个 OSError。

drain 需要预算和持有者。到期发取消是请求，不是资源释放证明。生产中不合作的任务应由受监督 worker 持有，保留执行 ID 与核实渠道；不能把未结束 future 丢出作用域，也不能无限等挂死线程。取消的应是收流和可取消工作，收尾不能依赖同一个已经被杀掉的 owner。`shield` 仅阻止某种取消传播，不提供持久持有者或崩溃恢复。

| 方案 | 适合 | 代价与不适用场景 |
| --- | --- | --- |
| 等模型正常终态，记完整消息和调用，再执行 | 协议无法证明逐调用稳定；写操作或需审批的调用 | 生命周期简单，但模型生成与工具延迟无法重叠；不满足强烈的低延迟只读预取需求 |
| 完整 call item 先记再提前执行，流后 drain | 独立只读工具、适配器有稳定 item 边界、可承担重复费用 | 多出参数冻结、日志、取消与恢复复杂度；不能用在可能改写的 call 或无幂等保障的付款上 |

一手源码也展示了不同选择：Pi **v0.57.1 / `a9cedccdde77e9d765303463d8a6cd11c58f7a7f`** 的 `packages/agent/src/agent-loop.ts:141–158` 先等待 `streamAssistantResponse`，错误/aborted 则结束，不在该流内执行工具；`:242–283` 把 partial 更新与最终 message_end 区分；`:305–359` 逐项 await 工具并生成结果。本次只读这些源码，没有运行 Pi；下方并发提前执行模型不是这个版本 Pi 的实现，也不据此判断其他版本。

### 3. 两工具并行、第二个先结束、然后断流

假设原创协议 `fixture-v1` 的 `call_ready` 是不可再改写的完整 item 边界，正常 `completed` 是整条 assistant 的终态。两工具无依赖、无业务副作用：`c1 = lookup({"key":"a"})` 返回 `{"value":11}`，`c2 = lookup({"key":"b"})` 返回 `{"value":22}`。参数各分成 `{"key":"` 和剩余字符。Python 3.11.8 用 `asyncio.Event` 控制先后，不靠固定 sleep 或真实网络延迟。

| 原始日志序号 | 实际发生的事 | 对 transcript 的影响 |
| --- | --- | --- |
| 0–6 | attempt 开始；重组参数；c1、c2 的 CallAccepted 分别提交于 3、6 | 两个调用有据可查；此时仍没有完整 assistant |
| 7–8 | 两个 ToolStarted；两者均已进入自制工具后才放行 c2 | 验证确实重叠执行 |
| 9 | c2 返回 22，立即写 Observation | c2 的结果不等待 c1 才保存 |
| 10–11 | 文本 chunk“我已经查到”；模型断流，关闭准入 | chunk 留在诊断记录；无 AssistantComplete |
| 12–13 | drain 期间 c1 返回 11，写 Observation；DrainClosed | 结果投影按 c1、c2 排序；本次没有 unknown |

下面是本地 fixture **实际运行**的最终原生 transcript。它保留完整调用和真实结果，并明确 `assistant: null`，不伪造一条含半句的完整 assistant：

```json
{
  "stream": "disconnected",
  "drain_closed": true,
  "assistant": null,
  "calls": [
    {"id": "c1", "ordinal": 0, "name": "lookup", "args": {"key": "a"}},
    {"id": "c2", "ordinal": 1, "name": "lookup", "args": {"key": "b"}}
  ],
  "results": [
    {"id": "c1", "result": {"value": 11}},
    {"id": "c2", "result": {"value": 22}}
  ],
  "unresolved": []
}
```

这份记录已经能解释工具发生了什么，但本例 `model_export` 会拒绝它：没有完整 assistant 终态。实际 provider 如果只接受完整 assistant + 配对结果，不能靠把 partial 改成 completed 来满足格式。应停止自动续发，按协议设计显式恢复：例如在新 attempt 中将已证实结果作为标明来源的运行时上下文，重新经过授权与请求校验；保留原失败 attempt，避免盲目重做已执行工具。通用 provider 迁移不是本例实现范围。

取消对照中，c2 已返回而 c1 等待，预算到期取消本地 c1 coroutine：`results` 仅保留 c2；`unresolved` 写 `{"id":"c1","status":"unknown","reason":"local_cancel"}`。若只有 CallAccepted 而未观测到执行，则为 `no_observation`。它们是运行时对知识缺口的记录，**不是返回给模型的伪造 tool result**。真实工具明确返回的错误体则是可记录的真实结果；网络异常只说明没拿到可靠结果。

<details>
<summary>可运行原创 fixture（保存为 closure_demo.py；只在新建临时目录使用）</summary>

```python
import asyncio
import json
import math
import os
from pathlib import Path


def copy_json(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


class Journal:
    # One event-loop writer; caller supplies a NEW file in its own temp directory.
    def __init__(self, path):
        self.path = Path(path)
        self.file = self.path.open('x', encoding='utf-8')
        self.rows = []
        self.poisoned = False
        self.failure = None

    def emit(self, kind, **data):
        if self.poisoned:
            raise self.failure
        row = copy_json(dict(seq=len(self.rows), kind=kind, **data))
        try:
            self.file.write(json.dumps(row, ensure_ascii=False) + '\n')
            self.file.flush()
            os.fsync(self.file.fileno())
        except OSError as error:
            self.poisoned = True
            self.failure = error
            raise  # Never start another tool or claim closure after this failure.
        self.rows.append(row)

    def close(self):
        try:
            self.file.close()
        except OSError as error:
            if self.failure is None:
                self.poisoned, self.failure = True, error
            raise self.failure


class Run:
    def __init__(self, journal, run_id, tool):
        self.log, self.run_id, self.tool = journal, run_id, tool
        self.parts, self.calls, self.tasks = {}, {}, {}
        self.text = ''
        self.sealed = False
        self.admission_closed = asyncio.Event()
        self.log.emit('AttemptStarted', run=run_id)

    def gate(self, run_id):
        if run_id != self.run_id or self.sealed:
            raise ValueError('stale run or closed admission')

    def chunk(self, run_id, text):
        self.gate(run_id)
        if type(text) is not str or len(self.text) + len(text) > 4096:
            raise ValueError('text limit/type')
        self.log.emit('TextChunk', text=text)
        self.text += text

    def args_delta(self, run_id, call_id, ordinal, chunk):
        self.gate(run_id)
        if (type(call_id) is not str or not call_id or len(call_id) > 64
                or type(ordinal) is not int or not 0 <= ordinal < 2
                or type(chunk) is not str or call_id in self.calls):
            raise ValueError('bad delta')
        old = self.parts.get(call_id, (ordinal, ''))
        if (old[0] != ordinal or len(old[1]) + len(chunk) > 1024
                or any(k != call_id and p[0] == ordinal for k, p in self.parts.items())):
            raise ValueError('slot collision or size limit')
        self.log.emit('ArgsChunk', id=call_id, ordinal=ordinal, text=chunk)
        self.parts[call_id] = (ordinal, old[1] + chunk)

    def call_ready(self, run_id, call_id):
        # Trusted fixture marker: this item's arguments are irrevocably complete.
        self.gate(run_id)
        if call_id in self.calls:
            return  # Duplicate ready marker does NOT execute twice within this Run.
        ordinal, raw = self.parts[call_id]
        def unique(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError('duplicate argument key')
                out[key] = value
            return out
        args = json.loads(raw, object_pairs_hook=unique)
        if type(args) is not dict or set(args) != {'key'} or args['key'] not in ('a', 'b'):
            raise ValueError('fixture lookup schema')
        call = dict(id=call_id, ordinal=ordinal, name='lookup', args=args)
        self.log.emit('CallAccepted', **call)  # Must succeed BEFORE create_task.
        self.calls[call_id] = call
        self.tasks[call_id] = asyncio.create_task(self.execute(call))

    async def execute(self, call):
        self.log.emit('ToolStarted', id=call['id'])
        try:
            result = copy_json(await self.tool(copy_json(call)))
        except asyncio.CancelledError:
            self.log.emit('Observation', id=call['id'], status='unknown', reason='local_cancel')
            raise
        except Exception as exc:
            self.log.emit('Observation', id=call['id'], status='unknown', reason=type(exc).__name__)
        else:
            self.log.emit('Observation', id=call['id'], status='returned', result=result)

    async def finish(self, reason, budget=1.0):
        # A supervisor passes user cancellation as data; it owns this cleanup.
        if (self.sealed or reason not in ('completed', 'disconnected', 'cancelled')
                or type(budget) not in (int, float) or not math.isfinite(budget) or budget < 0):
            raise ValueError('invalid finish')
        if reason == 'completed' and set(self.parts) != set(self.calls):
            raise ValueError('unfinished call item')
        self.sealed = True
        tasks = list(self.tasks.values())
        failure, outcomes = None, []
        try:
            try:
                if reason == 'completed':
                    self.log.emit('AssistantComplete', text=self.text,
                                  calls=sorted(self.calls.values(), key=lambda c: c['ordinal']))
                else:
                    self.log.emit('StreamInterrupted', reason=reason)
            finally:
                self.admission_closed.set()  # Notification must not depend on storage.
            if tasks:
                await asyncio.wait(tasks, timeout=budget, return_when=asyncio.FIRST_EXCEPTION)
        except BaseException as error:
            failure = error
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            # Safe here ONLY because the original fake tools cooperate with cancellation.
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        if self.log.failure is not None:
            raise self.log.failure  # Cleanup errors must not replace the first storage error.
        if failure is not None:
            raise failure
        for outcome in outcomes:
            if isinstance(outcome, BaseException) and not isinstance(outcome, asyncio.CancelledError):
                raise outcome
        self.log.emit('DrainClosed')
        return transcript(self.log.rows)


def transcript(rows):
    calls, observations = {}, {}
    assistant, stop, closed = None, None, False
    for seq, row in enumerate(rows):
        if row['seq'] != seq:
            raise ValueError('journal gap')
        kind = row['kind']
        if kind == 'CallAccepted':
            if row['id'] in calls:
                raise ValueError('duplicate call')
            calls[row['id']] = {k: copy_json(row[k]) for k in ('id', 'ordinal', 'name', 'args')}
        elif kind == 'Observation':
            if row['id'] not in calls or row['id'] in observations:
                raise ValueError('orphan or duplicate observation')
            observations[row['id']] = row
        elif kind == 'AssistantComplete':
            assistant = {k: copy_json(row[k]) for k in ('text', 'calls')}
            stop = 'completed'
        elif kind == 'StreamInterrupted':
            stop = row['reason']
        elif kind == 'DrainClosed':
            closed = True
    ordered = sorted(calls.values(), key=lambda c: c['ordinal'])
    results, unresolved = [], []
    for call in ordered:
        observed = observations.get(call['id'], {})
        if observed.get('status') == 'returned':
            results.append(dict(id=call['id'], result=copy_json(observed['result'])))
        else:
            unresolved.append(dict(id=call['id'], status='unknown',
                                   reason=observed.get('reason', 'no_observation')))
    return dict(stream=stop or 'open', drain_closed=closed, assistant=assistant,
                calls=ordered, results=results, unresolved=unresolved)


def model_export(view):
    # Teaching gate, not an SDK serializer. Interrupted history is never auto-repaired.
    if not view['drain_closed'] or view['assistant'] is None or view['unresolved']:
        raise ValueError('NOT_EXPORTABLE')
    return copy_json(dict(assistant=view['assistant'], tool_results=view['results']))


async def await_notice(event, worker):
    notice = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait((notice, worker), return_when=asyncio.FIRST_COMPLETED)
        if worker in done:
            worker.result()  # Observe failure even if no notification was ever sent.
        if not event.is_set():
            raise RuntimeError('worker ended without notification')
    finally:
        if not notice.done():
            notice.cancel()
        await asyncio.gather(notice, return_exceptions=True)


async def demo(path):
    journal = Journal(path)
    gates = {key: asyncio.Event() for key in ('a', 'b')}
    started = {key: asyncio.Event() for key in gates}
    finished = {key: asyncio.Event() for key in gates}
    async def lookup(call):
        key = call['args']['key']
        started[key].set()
        await gates[key].wait()
        finished[key].set()
        return dict(value={'a': 11, 'b': 22}[key])
    run, closing = None, None
    try:
        run = Run(journal, 'r1', lookup)
        for call_id, ordinal, key in (('c1', 0, 'a'), ('c2', 1, 'b')):
            run.args_delta('r1', call_id, ordinal, '{"key":"')
            run.args_delta('r1', call_id, ordinal, key + '"}')
            run.call_ready('r1', call_id)
        await await_notice(started['a'], run.tasks['c1'])
        await await_notice(started['b'], run.tasks['c2'])
        gates['b'].set()
        await await_notice(finished['b'], run.tasks['c2'])
        run.chunk('r1', '我已经查到')
        closing = asyncio.create_task(run.finish('disconnected'))
        await await_notice(run.admission_closed, closing)
        gates['a'].set()
        view = await closing
        return dict(events=copy_json(journal.rows), transcript=view)
    finally:
        owned = list(run.tasks.values()) if run is not None else []
        if run is not None:
            run.sealed = True
            run.admission_closed.set()
        if closing is not None:
            owned.append(closing)
        for task in owned:
            if not task.done():
                task.cancel()
        await asyncio.gather(*owned, return_exceptions=True)  # Also retrieve already-failed closing.
        journal.close()
```

</details>

在同目录执行以下命令即可输出完整事件与最终 transcript，退出时关闭文件并删除本次临时目录：

```sh
python - <<'PY'
import asyncio, json, tempfile
from pathlib import Path
from closure_demo import demo
with tempfile.TemporaryDirectory(prefix='closure-demo-') as folder:
    result = asyncio.run(demo(Path(folder) / 'events.jsonl'))
    print(json.dumps(result, ensure_ascii=False, indent=2))
PY
```

验证口径（2026-09-16）：Python 3.11.8，macOS arm64，原创 JSONL 文件、两个协作取消的本地工具，未调用模型或业务 API。正式验证从本文抽取 Python：原有 11 tests 覆盖两工具时序、参数截断/重复键、重复确认、迟到输入、正常终态、用户取消、执行前/结果写入失败、工具异常和关闭文件后的重建。另有 8 tests / 17 故障场景覆盖两种终态的 write/flush/fsync 失败、用户取消时终态写失败、demo 的 closing 无通知就失败，以及启动、观测、分片、DrainClosed、等待原语以及收尾 close 的二次失败路径。故障注入使用专属临时文件；回归在测试兜底之前断言任务完成、异常已取回、首次异常对象保留，未触发被动 watchdog 或兜底取消。坏日志不追加 DrainClosed 或新结果，断流主例不补造 assistant 消息。

代码有意限定为单事件循环、最多两个调用、受信任的 fixture 事件和本地文件系统；JSONL 回放不是通用畸形/恶意日志校验器。`flush/fsync` 的使用不证明断电、文件截断或跨进程事务安全，也不把日志与远端工具做成原子事务。`budget` 是 `asyncio.wait` 的等待秒数，之后的协作取消与 gather **不提供生产硬时限**；外部强杀/重复取消 owner、非合作工具、后续核实、真实审批与 provider 序列化均未实现。`DrainClosed` 表示本地任务已收集，仍可能带 unknown，不代表所有业务动作都有确定结果。

## 常见误区

- **“等模型流成功再记调用就行。”** 若工具已提前执行，断流后会找不到触发它的记录；应在分发前提交调用，或采用完全延后执行的方案。
- **“补齐 JSON、拼回半句，就能当完整 assistant。”** 参数可解析不代表被最终确认，完整 call item 也不代表整条 assistant 正常结束；失败 chunk 与正常 message 要分开。
- **“按调用顺序展示，就应按顺序执行或延后保存快工具结果。”** 执行并发、观测即时保存、投影稳定排序是三个决定。
- **“取消就是回滚，给所有未完成工具补一个 cancelled 结果即可。”** 本地取消不证明远端状态。只能记录有来源的返回或 unresolved 状态；已有结果和调用不能抹掉。

## 延伸 / 追问

**如果 c2 很快而 c1 永远不返回，如何兼顾首屏和审计？** UI 可按完成顺序展示 c2 的暂态进度，先保存 c2 的真实结果；最终投影仍按稳定 call ID/ordinal 对齐。drain 到期后剩余 c1 必须有 owner 和核实记录；未知项阻止需要完整工具轮次的自动续发，不要为了首屏改写真源。

**调用已落盘，工具也可能执行了，但结果落盘前进程崩溃怎么办？** 重建只能得出该 call 待核实。用业务幂等键、远端执行 ID 查询，或人工确认；没有查询/幂等能力的写工具不应自动重放。一次成功运行无法证明远端 exactly-once。

**如果重试再次收到同一个 call ID，怎样处理？** 在同 attempt 中比较不可变载荷，同 ID 同载荷才可去重，不同载荷应报冲突。跨 attempt 的模型 ID 不应自行解释成业务幂等键；是否复用结果要另外校验参数、权限、时效和业务操作身份。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定版本 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/codex-03.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-03.html)、[slides/dsh-22.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-22.html)。仅作为学习线索，课程所述其他运行时的提前执行、重试和持久性不作为本文已验证事实；不复制其 AGPL 正文、代码或图片。
- Mario Zechner，Pi v0.57.1，MIT，固定 commit `a9cedccdde77e9d765303463d8a6cd11c58f7a7f`：[agent-loop.ts:141–158](https://github.com/badlogic/pi-mono/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/agent/src/agent-loop.ts#L141)、[partial 与终态:242–283](https://github.com/badlogic/pi-mono/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/agent/src/agent-loop.ts#L242)、[工具执行:305–359](https://github.com/badlogic/pi-mono/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/agent/src/agent-loop.ts#L305)、[LICENSE](https://github.com/badlogic/pi-mono/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/LICENSE)。用于说明另一种时序，不是本例提前执行的证据。
- Python Software Foundation，CPython **v3.11.8**：[asyncio-task.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/asyncio-task.rst)，Task Cancellation、TaskGroup、gather、shield、wait、Task.cancel 各节；[许可证](https://github.com/python/cpython/blob/v3.11.8/LICENSE)。支持并发收集、异常传播和取消边界的说明，不能推导工具业务状态。
