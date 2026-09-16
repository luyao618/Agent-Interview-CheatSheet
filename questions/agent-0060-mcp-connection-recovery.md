---
id: agent-0060
title: MCP 客户端怎样做懒连接、重连和能力刷新，避免旧连接事件破坏新状态？
category: agent
tags: [mcp, connection-lifecycle, recovery, generation, capability-snapshot, reliability]
difficulty: medium
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

MCP 客户端怎样做懒连接、重连和能力刷新，避免旧连接事件破坏新状态？若旧客户端 A 的断线通知晚于新客户端 B 建立连接才到达，注册表应该如何变化？

## 答案 · GPT-6

把每个 server 的连接交给一个有明确生命周期的 owner：首次需要时合并连接请求；连接替换时增加 generation；所有异步回调、目录结果和失败都携带它们所属的 client identity 与 generation。**先确认事件属于当前连接，再在同一个临界区里修改状态。** 新连接完成初始化后还要重新发现工具，只有完整且未过期的目录才能成为可用快照。

[agent-0007](agent-0007-mcp-call-lifecycle.md) 解释调用链，[agent-0049](agent-0049-mcp-streaming-bidirectional-stateful-sessions.md) 讨论通信扩展；本题聚焦客户端恢复。模型已经取走菜单后的调用准入见 [agent-0058](agent-0058-tool-catalog-sampling-snapshot.md)，这里不重写其权限与 schema 校验器。涉及协议的结论以 MCP **2025-06-18** 固定版为准，不能把旧题的扩展示意当作协议保证。

### 1. 懒连接、连接就绪与目录可用分开

注册配置只表示 host 知道某个 server 的连接入口，并不证明服务在线，也不等于已经知道其最新 tools。首次按需发现或使用时触发连接；同一 server 的多个调用方共享一个启动任务。单个调用方放弃等待，不应取消其他调用方仍需要的连接。状态应按 server 隔离，避免一个服务不可达拖住其他服务。

以下是**原创 host 策略**，不是 MCP 标准状态枚举。本例选择已知失效时撤下可用目录；可另存旧描述供 UI 展示，但必须标为过期且不可执行。

| host 状态 | 进入条件 | 可用注册表与下一步 |
| --- | --- | --- |
| `idle` | 仅载入合成配置 | 没有连接；首次需求创建唯一 owner worker |
| `connecting` | 已分配新的 client/generation | 无可用目录；完成 `initialize`、版本/能力核对和 `notifications/initialized` |
| `refreshing` | 初始化完成，或已知目录失效 | 无可用目录；拉完整工具清单并校验，不能沿用前一连接的能力标记 |
| `ready` | 完整目录与当前 identity/generation/revision 匹配 | 原子发布不可变能力及工具快照；空列表也可合法 ready |
| `disconnected` / `backoff` | 当前逻辑连接失效，或暂时性 RPC 故障 | 撤下本 server 的目录，关闭旧 client，在预算内重试 |
| `failed` / `stopped` | 致命错误、预算耗尽，或显式停止 | 释放等待方，收集已有任务；不会因新调用自动无限重启 |

`tools` capability 表示 server 支持工具协议；`listChanged` 表示目录变更通知能力。二者都不是实际工具清单。如果未声明 tools，就不发送 `tools/list`；支持 tools 但返回空列表，与发现失败也不同。没有 `listChanged` 时，host 需要明确的按需刷新、TTL 或轮询策略，不能永久假设缓存正确。本例只实现显式 `refresh`，不悄悄增加轮询线程。

### 2. 三个序号问题与有界恢复

**连接归属。** server 名称或 URL 在重连后通常不变，不能拿它识别回调来源。用 `(client object identity, generation)` 绑定一次连接尝试；generation 在这个 owner 内单调递增。检查和删注册项必须受同一个锁/actor 串行顺序保护，不能检查完解锁、过一会儿再按 server 名清空。进程重启后的持久消息还需要 owner epoch，不能复用从 1 开始的裸 generation。

**目录修订。** `tools/list_changed` 是“需要重新取清单”的失效信号，不是可直接合并的工具增删补丁。回调只增加 dirty revision、撤下可用目录并唤醒一个 worker。一次刷新记录起始 revision；返回时如果期间又有通知，就丢弃候选结果并再取一次。这样既合并突发通知，也不会因为清掉一个布尔 `dirty` 而吞掉刷新过程中新来的变更。UI 状态推送可以节流，但必须先处理有效世代的失效，再合并展示；不能让迟到的 `A: disconnected` 覆盖 `B: ready`。

**重试预算。** 只对已分类的暂时性连接/传输故障退避，采用有上限的指数退避并在实际部署中加 jitter、总时间预算。认证需交互、配置禁用/移除、不支持的协议版本、坏清单等应进入停止或待处理状态；不要不断重启来“修复”权限问题。停止先关闭准入、唤醒等待者，再取消并收集连接、刷新和退避任务。压在锁里的网络等待会阻碍停止和失效通知，所以 I/O 一律在锁外。

本例有意使用很小的**教学预算**：每个 owner 生命周期最多创建 3 个 client，失败后的名义退避为 1 秒、2 秒；成功连接不会重置这个累计预算。退避函数只推进一个 event-loop turn，记录的是虚拟秒数，不是实测等待时间。一次不稳定刷新批次最多取 3 次清单，稳定发布后下一批重新计数。默认 mock RPC 等待阈值是 0.1 秒；真实产品若采用“稳定运行一段时间后重置”策略，必须另有总预算和禁用/停止检查，不能无条件清零。

MCP 文档建议请求超时与取消处理；Python cancellation 仍是合作式的。本例在超时后取消并 `gather` 已有 mock RPC，迟到返回也不能把已判定的 timeout 改成成功。所有 mock 等待都响应取消；**这不证明任意 SDK、阻塞代码或 OS 资源能在 0.1 秒内回收**。真实 transport 还需有界关闭、资源所有权及必要的外部监督。断线前已发出的工具调用可能结果未知，恢复连接不授权自动重放有副作用的调用。

### 3. stdio 与 Streamable HTTP 的恢复动作不同

| 观察到的故障 | 恢复层与动作 | 不能推导的结论 |
| --- | --- | --- |
| stdio 子进程退出、管道失效 | 管理子进程的 supervisor 回收其拥有的进程/管道；若政策允许，启动替代进程并重新初始化、发现能力与清单 | 留着旧工具描述不能复活旧进程；启动进程不等于目录 ready |
| Streamable HTTP 的某条 SSE 流断开 | 先由 transport 判断是否只需恢复该流；协议允许服务端提供 resumability，客户端可按规范使用 `Last-Event-ID` | 流关闭未必是整个 MCP session 失效，也不等于请求取消；恢复可选且不保证远端 exactly-once |
| 携带 `Mcp-Session-Id` 的请求收到 session 无效的 HTTP 404 | 固定版规范要求不带旧 session ID 发起新的初始化；host 重新核对能力并刷新目录 | 不能仅重开 SSE 后继续信任旧会话/旧清单，也不能把普通端点发现错误一概当此情形 |

在 2025-06-18 中，Streamable HTTP 替代旧版 HTTP+SSE；兼容探测、session 重建和某条流恢复是不同路径。session ID、SSE event ID 与 host generation 各有作用，不能互相替代。本例的 `disconnect` **专指适配器已经判定的逻辑连接失效**，不会把每次 HTTP 响应体结束都映射成它；fixture 不实现 HTTP、stdio 或 SDK 的恢复协议。

### 4. 合理方案与代价

| 方案 | 适用条件与收益 | 代价与不适用场景 |
| --- | --- | --- |
| 按需连接，失效就撤下可用目录（本例） | 服务多、调用稀疏或变化大时，减少无用启动；失效边界清晰 | 首次发现有冷启动延迟，通知风暴可能短时无工具可用；严格低延迟的常用工具不宜只靠冷启动 |
| 预热常用连接，保留旧描述但标为 unavailable，后台恢复 | 需要稳定的 UI/搜索入口或有冷启动 SLA 时，描述缓存与执行可用性分开 | 常驻连接有资源成本，必须区分旧描述与可调用绑定；未经当前版本及权限复核，不能把旧缓存拿来继续执行 |

两种方案都需要 identity guard 和完整快照发布。保留旧描述是可用性/展示取舍，不是“断线也安全可执行”的承诺；懒连接也不是只在启动时少调用一个 API，它会把等待、共享任务及首次失败契约移到需求入口。

### 5. 示例：A 的旧断线通知晚于 B 初始化

输入都是合成对象：A、B 的 server label 都是 `same-server`。A 提供 `lookup / doc_id-v1`，B 提供 `lookup / slug-v2`；这些只是 mock schema 标签。先由健康检查路径处理 A 失效，触发 B 建立；A 的另一条迟到 `onclose` 随后才到。

| 顺序 | 事件 | owner 与可用注册表 |
| --- | --- | --- |
| 1 | 构造 owner；首次 `ready()` | 构造时零连接；首次调用创建 A/g1，完整发现后注册 v1 |
| 2 | 当前 A/g1 的健康故障被接受 | 撤下 v1，A 回收；在预算内创建 B/g2 |
| 3 | B 完成初始化，但人为卡住它的 `tools/list` | `current=B, generation=2, phase=refreshing`；可用注册表为 `None` |
| 4 | A/g1 的迟到断线通知到达 | identity/generation 不匹配，返回 `False`；B 保持当前连接，目录仍等待刷新 |
| 5 | 放行 B 的清单结果 | 原子发布 g2 的 v2 清单；旧快照对象仍是 v1，不能伪装成新快照 |
| 6 | 再来一条 A 通知 | 仍忽略，不撤下 B，也不额外重连 |

若写成 `registry.pop(server_name)`，第 4 或第 6 步就会删掉 B 的状态。只比较 generation、只比较对象名，或在锁外比较后稍晚再删除，也都不能满足这个边界。**错误同样有归属**：已失效尝试返回的异常不能把后续恢复判成致命失败；当前尝试的致命异常则要释放等待者并明确失败。

<details>
<summary>可运行的原创 Python 3.11.8 fixture（纯内存 mock）</summary>

保存为 `recovery_fixture.py`，运行 `python3 recovery_fixture.py`。它只模拟一个 server owner，`initialize()` 代表完整握手、`list_tools()` 直接返回完整 tuple，`close()` 只标记无外部资源的 mock 已关闭。真实分页须在适配器内拉完所有页、限制页数/时间并校验，再尝试一次发布；本代码不验证分页 cursor、JSON Schema、真实协议消息或远端目录一致性。每个异步示例都显式 await `stop()` 并断言已收集任务。

```python
# file: recovery_fixture.py
"""Original synthetic MCP owner; no SDK, sockets, processes or credentials."""
import asyncio
from dataclasses import dataclass, field
import json
import math


class Transient(Exception):
    pass


class Halt(Exception):
    pass


@dataclass(frozen=True)
class Caps:
    tools: bool = True
    list_changed: bool = True


@dataclass(frozen=True)
class Tool:
    name: str
    schema: str  # Synthetic schema label, not JSON Schema validation.


@dataclass(frozen=True)
class Snapshot:
    generation: int
    revision: int
    capabilities: Caps
    tools: tuple


@dataclass
class Step:
    value: object
    gate: object = None
    started: asyncio.Event = field(default_factory=asyncio.Event)
    late_on_cancel: bool = False

    async def run(self):
        self.started.set()
        try:
            if self.gate is not None:
                await self.gate.wait()
        except asyncio.CancelledError:
            if not self.late_on_cancel:
                raise
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class MockClient:
    def __init__(self, listing, initialize=None):
        self.label = 'same-server'  # A and B intentionally share this label.
        self.init = initialize or Step(Caps())
        self.listing = list(listing)
        self.list_calls = 0
        self.closed = False

    async def initialize(self):
        # Models the whole initialize + initialized exchange, not one wire RPC.
        return await self.init.run()

    async def list_tools(self):
        self.list_calls += 1
        if not self.listing:
            raise Halt('mock_listing_exhausted')
        return await self.listing.pop(0).run()

    def close(self):
        # Mock owns no OS resources or background tasks; synchronous and total.
        self.closed = True


class Owner:
    def __init__(self, clients, attempts=3, refreshes=3, rpc_seconds=0.1,
                 backoff=None):
        if (type(attempts) is not int or attempts < 1 or
                type(refreshes) is not int or refreshes < 1 or
                not math.isfinite(rpc_seconds) or rpc_seconds <= 0):
            raise ValueError("invalid_budget")
        self.pool = iter(clients)
        self.max_attempts, self.max_refreshes = attempts, refreshes
        self.rpc_seconds = rpc_seconds
        self.backoff = backoff or self.virtual_backoff
        self.cv = asyncio.Condition()
        self.wake = asyncio.Event()
        self.worker = self.current = self.snapshot = self.capabilities = None
        self.generation = self.revision = self.attempts = 0
        self.alive = self.stopped = False
        self.phase, self.error = 'idle', None
        self.created, self.delays = [], []
        self.rpc_tasks = set()
        self.spawned = self.collected = 0

    @staticmethod
    async def virtual_backoff(seconds):
        # Records seconds but advances only an event-loop turn in this fixture.
        await asyncio.sleep(0)

    def matches(self, client, generation):
        # Call only while holding cv, with no await between check and mutation.
        return (not self.stopped and self.alive and
                self.current is client and self.generation == generation)

    async def ready(self):
        async with self.cv:
            if self.stopped:
                raise Halt('stopped')
            if self.worker is None:
                self.worker = asyncio.create_task(self.run())
            await self.cv.wait_for(lambda: self.snapshot is not None or
                                   self.error is not None or self.stopped)
            if self.stopped:
                raise Halt('stopped')
            if self.error is not None:
                raise Halt(self.error)
            return self.snapshot

    async def event(self, client, generation, kind):
        if kind not in ('disconnect', 'changed', 'refresh'):
            raise ValueError(kind)
        async with self.cv:
            if not self.matches(client, generation):
                return False
            if (kind == 'changed' and self.capabilities is not None and
                    not self.capabilities.list_changed):
                return False
            if kind == 'disconnect':
                self.alive = False
            else:
                self.revision += 1
            self.snapshot = None
            self.phase = 'disconnected' if kind == 'disconnect' else 'refreshing'
            self.wake.set()
            self.cv.notify_all()
            return True

    async def rpc(self, awaitable):
        task = asyncio.create_task(awaitable)
        self.rpc_tasks.add(task)
        self.spawned += 1
        try:
            done, _ = await asyncio.wait({task}, timeout=self.rpc_seconds)
            if not done:
                raise Transient('rpc_timeout')
            return task.result()
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.rpc_tasks.remove(task)
            self.collected += 1

    async def run(self):
        try:
            while True:
                async with self.cv:
                    if self.stopped:
                        return
                    if self.attempts == self.max_attempts:
                        raise Halt('connection_budget_exhausted')
                    self.attempts += 1
                    client = next(self.pool, None)
                    if client is None:
                        raise Halt('mock_clients_exhausted')
                    self.created.append(client)
                    self.current = client
                    self.generation += 1
                    generation = self.generation
                    self.revision = 0
                    self.alive = True
                    self.snapshot = self.capabilities = None
                    self.phase = 'connecting'
                    self.wake.clear()
                    self.cv.notify_all()
                try:
                    caps = await self.rpc(client.initialize())
                    async with self.cv:
                        if not self.matches(client, generation):
                            raise Transient('invalidated_initialization')
                        if (type(caps) is not Caps or type(caps.tools) is not bool or
                                type(caps.list_changed) is not bool or
                                (caps.list_changed and not caps.tools)):
                            raise Halt('invalid_capabilities')
                        self.capabilities = caps
                        self.phase = 'refreshing'
                        self.cv.notify_all()
                    refreshes = 0
                    while True:
                        async with self.cv:
                            if not self.matches(client, generation):
                                break
                            revision = self.revision
                            self.wake.clear()
                        refreshes += 1
                        if refreshes > self.max_refreshes:
                            raise Halt('refresh_budget_exhausted')
                        tools = await self.rpc(client.list_tools()) if caps.tools else ()
                        async with self.cv:
                            if not self.matches(client, generation):
                                break
                            if revision != self.revision:
                                continue  # Never clear a newer invalidation.
                            if (type(tools) is not tuple or
                                    any(type(t) is not Tool or type(t.name) is not str or
                                        not t.name or type(t.schema) is not str for t in tools) or
                                    len({t.name for t in tools}) != len(tools)):
                                raise Halt('invalid_tools')
                            self.snapshot = Snapshot(generation, revision, caps, tools)
                            self.phase = 'ready'
                            self.cv.notify_all()
                        refreshes = 0
                        await self.wake.wait()
                except Exception as exc:
                    async with self.cv:
                        still_current = self.matches(client, generation)
                    if still_current and not isinstance(exc, Transient):
                        raise  # Fatal errors belong only to the live attempt.
                    # Invalidated attempt errors and classified transients retry.
                finally:
                    async with self.cv:
                        if self.current is client and self.generation == generation:
                            self.alive = False
                            self.snapshot = self.capabilities = None
                            self.phase = 'backoff'
                            self.cv.notify_all()
                    client.close()
                if self.attempts < self.max_attempts:
                    delay = min(2 ** (self.attempts - 1), 4)
                    self.delays.append(delay)
                    await self.backoff(delay)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            async with self.cv:
                self.error = str(exc)
        finally:
            async with self.cv:
                self.alive = False
                self.current = self.snapshot = self.capabilities = None
                self.phase = 'stopped' if self.stopped else 'failed'
                self.cv.notify_all()

    async def stop(self):
        async with self.cv:
            if not self.stopped:
                self.stopped = True
                self.alive = False
                self.snapshot = self.capabilities = None
                self.phase = 'stopped'
                if self.worker is not None:
                    self.worker.cancel()
                self.cv.notify_all()
            worker = self.worker
        if worker is not None:
            # A caller must await stop; it is never a detached shutdown request.
            await asyncio.shield(asyncio.gather(worker, return_exceptions=True))

    def collected_all(self):
        return (not self.rpc_tasks and self.spawned == self.collected and
                (self.worker is None or self.worker.done()) and
                all(c.closed for c in self.created))


async def demo():
    gate = asyncio.Event()
    pending = Step((Tool('lookup', 'slug-v2'),), gate)
    a = MockClient([Step((Tool('lookup', 'doc_id-v1'),))])
    b = MockClient([pending])
    owner = Owner([a, b])
    try:
        old = await owner.ready()
        await owner.event(a, 1, 'disconnect')  # Health path detects A first.
        await pending.started.wait()  # B initialized, list result still blocked.
        accepted = await owner.event(a, 1, 'disconnect')  # Delayed onclose.
        before = dict(phase=owner.phase, generation=owner.generation,
                      registry=owner.snapshot, old_event_accepted=accepted,
                      current_is_b=owner.current is b)
        gate.set()
        new = await owner.ready()
        return dict(old_schema=old.tools[0].schema, before_refresh=before,
                    new_generation=new.generation, new_schema=new.tools[0].schema,
                    connection_attempts=owner.attempts, virtual_delays=owner.delays)
    finally:
        await owner.stop()
        assert owner.collected_all()


if __name__ == '__main__':
    print(json.dumps(asyncio.run(demo()), indent=2))
```

</details>

2026-09-16 在 Python 3.11.8 本地运行得到：`before_refresh={phase: refreshing, generation: 2, registry: null, old_event_accepted: false, current_is_b: true}`，随后 `new_generation=2, new_schema=slug-v2, connection_attempts=2, virtual_delays=[1]`。这里的 `null` 是 JSON 对不可用注册表的投影，与“已成功发现零个工具”的空 tuple 不同。

配套原创测试执行 `python3 test_recovery.py`，**28 个测试通过**：包括 A 迟到事件、双重身份校验、共享启动与取消等待者、100 条通知合并为一次额外刷新、刷新期间变更导致候选作废、初始化期间通知、重连与刷新预算耗尽、致命故障、三种阶段停止、超时后迟到返回、旧 RPC 错误归属、能力变化、坏/空清单及输入不可变性。测试的 31 个 owner、73/73 个 RPC task、40 个已创建 client 和 12 个等待任务在 event-loop teardown 前完成收集；两次 demo 也各自执行独立的清理断言，不计入这些测试计数。完整测试与复跑脚本随单题 review 证据提供。

`ready()` 返回的 snapshot 离开锁后就可能过期。调用方要在真正执行入口复核当前 binding，不能拿“曾经 ready”当执行许可。真实适配器还需处理分页期间的服务端变更、丢通知、权限过滤及在途结果；没有服务端版本/一致性保证时，本地 revision 只描述**已观察到的变化**，不能证明远端 schema 从未变过。

## 延伸 / 追问

**追问 1：重连成功后能否直接把旧工具名重新注册？**

不能当作最新能力。新连接必须完成能力核对、完整发现与目录发布；名称一样也可能 schema 或权限已变。可以保留旧描述供 UI 显示，但必须标记 unavailable，不应拿它绕过新连接准入。

**追问 2：刷清单时又收到十条 list_changed，要并发发十次 RPC 吗？**

通常不需要。每个连接用一个 worker 和 dirty revision 合并需求：结果只有在当前连接及起始 revision 仍有效时才发布；否则再取一次。连续变化要有批次预算，超限进入明确失败/冷却状态。单纯“清 dirty 后返回”会丢失交错通知。

**追问 3：调用已发出但 SSE 断了，重连后重新发一次是否安全？**

不由重连结果决定。按 transport 支持恢复原流/响应，并按业务幂等键或状态查询确认原调用结果；无法确认时保留结果未知。新的 request ID 或 session ID 不能证明旧副作用未发生。

**追问 4：用户禁用 server，延迟回调还能再次启动连接吗？**

停止状态必须先在线性化点关闭准入，并使旧 identity/generation 的事件失效；再停止退避、取消并收集已拥有的任务。未来重新启用应建立新的 owner/epoch，重新校验配置及授权，而不是让旧回调清除 stopped 标记。

## 常见误区

- **“连接成功就是工具列表已刷新。”** 初始化能力与具体目录分开；`refreshing` 期间可用注册表为空，不能复用旧 ready 标记。
- **“stdio 自动重启策略可以原样用于 HTTP。”** 进程退出、单条 SSE 流结束、session 失效分别由不同层处理；重启次数、退避和停止条件是 host 策略。
- **“按 server 名移除就行；布尔 connected 足够。”** 同名新 client 可能已经就位。身份和世代的比较、失效及发布必须在同一临界区。
- **“合并通知就是保留最后一条 UI 状态。”** 先按连接归属处理失效，刷新用 revision 防止丢变更；展示层节流不能变成事实真源。
- **“timeout、重连、测试通过证明没有副作用或泄漏。”** 合作式 mock 能证明本地收集逻辑，不证明真实 transport 回收硬时限、持久性、授权原子性或远端 exactly-once。

## 参考

- 学习线索：洛小山《AI 产品从入门到精通》learn-ai，固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/9-31.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/9-31.html)、[slides/12-20.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/12-20.html)、[slides/dsh-21.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-21.html)。[LICENSE](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/LICENSE) 为 AGPL-3.0；只作线索，未移入课件正文、代码或图片。课程中的产品专属时延、退避数列及私有/还原源码结论未作为本文已核实的产品保证。
- 一手协议：Model Context Protocol **2025-06-18**，仓库固定 `cd0623765886c8cc282e3e5e1a03ab7469055fab`：[Lifecycle](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/docs/specification/2025-06-18/basic/lifecycle.mdx) 的 Initialization、Capability Negotiation、Timeouts；[Transports](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/docs/specification/2025-06-18/basic/transports.mdx) 的 stdio、Resumability and Redelivery、Session Management；[Tools](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/docs/specification/2025-06-18/server/tools.mdx) 的 Listing Tools、List Changed Notification。[该版本 LICENSE](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/LICENSE) 说明 Apache-2.0 迁移、新规范贡献与尚未同意迁移的旧 MIT 贡献的区分；非规范文档另有 CC-BY-4.0，不能概括成全仓单一 MIT。
- 一手运行语义：CPython **v3.11.8**，[Doc/library/asyncio-task.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/asyncio-task.rst) 的 Waiting Primitives、Task Cancellation、Shielding From Cancellation；[`LICENSE`](https://github.com/python/cpython/blob/v3.11.8/LICENSE) 记录 PSF 许可及历史。本文 `asyncio.wait` 超时后显式取消并收集；测试仅适用于原创合作式 mock，不冒充 MCP SDK 集成或生产可靠性测量。
