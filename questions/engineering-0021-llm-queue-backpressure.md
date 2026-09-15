---
id: engineering-0021
title: LLM 任务生产速度长期高于消费速度时，如何设计背压而不是无限排队？
category: engineering
tags: [backpressure, admission-control, bounded-queue, cancellation, fairness]
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

LLM 任务生产速度长期高于消费速度时，如何设计背压而不是无限排队？给定到达率与服务率估算积压，比较拒绝、排队和降级，并解释运行中任务超时后何时可以释放容量。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**队列只能把部分工作推迟，不能增加消费能力。** 持续过载时，要让容量不足反馈到生产端：减少准入、降低单次工作量，或增加经过验证的消费者容量。同时分别限制等待量和运行中的物理调用数，否则只是把积压从队列搬进协程、连接池或供应商内部。

[engineering-0008](engineering-0008-peak-qps-system-design.md) 讨论大促整体容量，[engineering-0009](engineering-0009-async-agent-event-priority.md) 讨论事件如何定级。本题补充持续过载的积压计算、准入和容量归还；模型切换契约见 [engineering-0017](engineering-0017-model-routing-failover.md)，不在这里重复设计路由器。

### 1. 先统一单位，再算能否排得完

记 `λ_offer` 为外部逻辑任务到达率，`λ_admit` 为实际接纳率；`C` 为可同时执行的物理调用上限，`E[S]` 为每次占用运行名额的平均秒数。对同质请求、固定容量且没有其他瓶颈的简化模型，总服务率 `μ_total ≈ C / E[S]`，单位是调用/秒。单个消费者的服务率则是 `1 / E[S]`，不要再重复乘除 `C`。

若每个逻辑任务只调用一次、初始等待队列为空、消费者已忙且输出平滑，流体近似为：

```text
持续积压增长率 = λ_admit - μ_total                  （任务/秒）
Q(t) ≈ max(0, Q(0) + (λ_admit - μ_total) × t)      （任务）
恢复后的清空时间 ≈ Q / (μ_total - λ_after)         （秒；要求 λ_after < μ_total）
```

这是固定到达率、无取消/过期的区间公式；不能跨越到达率变化直接套一次。持续 `λ_admit > μ_total` 没有稳态；`λ_admit = μ_total` 也没有吸收波动的余量。Little 定律 `L = λ_eff W` 需要稳定、同一统计边界的长期均值，不能拿它给不断增长的队列证明延迟有界。

**教学算例，日期 2026-09-16：** 一任务一调用，`λ_offer=12 任务/秒`，`C=20`，`E[S]=2 秒/调用`，故 `μ_total=10 任务/秒`。从等待量 0、运行流水线已忙开始，观察 60 秒；忽略批次、离散完成和尾延迟。下表是独立策略的流体计算，不是任何模型压测或真实容量。

| 策略 | 同一输入下的计算 | 适用条件与代价 |
| --- | --- | --- |
| 无等待名额，容量满即拒绝 | 60 秒新增 720 个任务，接纳约 600，拒绝约 120，等待量 0 | 交互请求不值得久等；保住已接纳流量，但拒绝必须让调用方可识别 |
| 有界等待，`Qmax=50` | 净增长 2/秒，25 秒填满；到 60 秒等待 50，接纳约 650、拒绝约 70 | 能吸收有限突发；持续过载仍须拒绝，不能承诺全部完成 |
| 降级后再准入 | **另假设**每次服务变为 1.5 秒，容量约 13.33/秒，负载率 0.9；此流体模型不产生持续净积压 | 任务允许缩短输出、减少步骤或换小模型，且质量/权限/格式契约通过；高风险决策不能为快而省掉必要校验 |

若无限排队，同一 60 秒后等待量为 `2×60=120`，队尾新请求的等待约 `120/10=12 秒`，还未计自身执行。对 50 名额的队列，这个近似等待为 5 秒；若端到端预算 8 秒，执行预估 2 秒、收尾 1 秒，则等待预算只剩 5 秒。**`Qmax/μ_total` 是同质、FIFO、平滑消费下的估计，既非 p99，也非硬上界。** 实际要加截止时间和服务时间分布，低优先级可能等得更久。

假设 60 秒后到达率降至 4/秒，50 个积压约需 `50/(10−4)=8.33 秒` 清空；若仍为 12/秒，则无法靠“再等一会儿”解决。降级行假设从一开始即使用新服务时间，不能把已经运行的旧调用瞬间当成更快的新调用；持续批处理、KV Cache、长短输入和供应商 RPM/TPM 都会让 `C/E[S]` 偏离实际。应按真实 Token 分布、总时限和质量目标压测，再选工作点，不能只增加并发数。

### 2. 背压要覆盖从入口到物理调用的整条路径

```text
生产端 → 当前授权/租户额度/工作量与 deadline 准入
       → 有界等待队列 → 取得运行名额并出队 → 发起物理调用
满或太迟：拒绝/协商降级    过期：不再发送     终态且资源已停：归还名额
                                            取消待确认：仍占名额
```

入口不仅限制任务数，也限制请求 bytes、预计输入/输出 Token、租户欠账和待执行工作量；否则一个超长任务就能占满内存或 TPM。队列尽量保存有大小上限的任务引用，载荷存储本身也要配额。准入时估算“排队 + 执行 + 收尾”是否赶得上 deadline，出队前再次检查。接受异步任务后应返回可查询的任务 ID，并明确 accepted 只表示接纳，不是完成。

**等待容量与运行容量是两个账本：** `Q_wait ≤ Qmax`；`R_active + R_cancel_pending ≤ C`。消费者只有拿到运行名额才可出队发送。所有调用路径，包括子 Agent、SDK 自动重试和备用模型，都要进入相应的全局/租户/供应商额度；多进程各有一个 `C` 会把总并发变成进程数乘 `C`。分布式实现需原子准入和名额所有权，不能先看计数再无保护地加一。

CPython 3.11.8 的 `asyncio.Queue` 说明了一个常见陷阱：`maxsize=0` 是无界；`get_nowait()` 移除等待项后就唤醒 putter，`task_done()` 另记未完成工作。**把取出的任务无限 `create_task()`，并不受队列 maxsize 约束。** 同理，为每个请求创建一个阻塞在 `put()` 的协程，会把无界等待藏在生产端。需要有限 worker、运行名额及入口限制共同约束；`BoundedSemaphore` 的过量 release 检查，也不等于它替你追踪远端调用。

可控制的生产端采用 credit/demand 或有截止的阻塞发送；不能无限保留等待发送的连接/协程。对无法减速的外部入口，要快速拒绝：用户速率受限可用 HTTP 429，暂时整体过载可用 503，并按协议提供可选 `Retry-After`。这是拒绝和重试提示，不保证届时有容量，也不表示任务已入队。Reactive Streams 1.0.4 的 demand 规则是一手背压范例，但该协议的取消语义不能直接套成 LLM 服务端的停机保证。

### 3. 超时、调度与重试必须服从同一容量边界

| 情况 | 应做的状态变化 | 不能偷换的含义 |
| --- | --- | --- |
| 等待中到期/取消 | 原子移除或标记不可派发，归还等待额度 | 不能仍留一个消费者会照常执行的任务 |
| 运行中 deadline 到期/用户取消 | 标记 cancel pending，通知执行器，抑制迟到输出；继续占用物理调用额度 | 断开 HTTP、取消本地 Future 或只收到“取消请求已接收”均不证明远端停止 |
| 已确认该 attempt 停止 | 用 attempt ID/所有权校验的终态事件，至多归还一次运行额度 | 重复、乱序、旧 attempt 回调不得给新调用释放名额 |
| 停止情况未知 | 保留为待对账的占用，收紧准入并隔离/告警；按后端契约查询终态或确认执行器已被终止 | 不能靠固定 sleep 或租约到期就假定远端释放，否则新旧调用会叠加 |

取消是资源问题，也可能涉及副作用：超时并不证明动作没有执行，相关幂等和对账见 [engineering-0002](engineering-0002-idempotency-distributed-transaction.md)。如果本地 worker 已退出但远端工作未确认结束，保留的是远端在途额度；应分别计量，不能在本地 `finally` 中把两种额度一起无条件释放。

调度规则由可信业务字段决定，不能让用户自报最高优先级。FIFO 简单但长任务会挡住短任务；纯高优先级先行会让低优先级饥饿。可按租户设等待/在途额度，再做加权轮转、保底份额和 aging，限制高优先级突发。**轮转保证的是获得派发机会，未必是相同 GPU 时间或相同完成延迟。** LLM 时长差异大时，应按估算 Token/算力做 deficit 调度并用实际消耗校正；不支持安全抢占时，不能为高优任务直接抹掉运行占用。

重试也会生产任务。若每个逻辑任务最多重试 2 次、每次独立失败概率教学设为 0.5，则期望尝试数 `1+0.5+0.25=1.75`，12 个逻辑任务/秒会变成约 **21 次物理尝试/秒**；这仍没计算失败相关性。三个调用层各允许总共 3 次尝试，最坏可触发 `3³=27` 次下游调用。统一总 deadline、attempt 上限和重试预算，使用带 jitter 的退避、尊重适用配额域的 `Retry-After`，每次重试重新准入。满队列拒绝不能触发无延迟重试；已在运行/取消待确认的同一请求不得因客户端超时再开一份。

监控至少拆开：外部任务到达率、接纳/拒绝/降级率、物理 attempt 率、等待长度/最老年龄、排队与执行延迟、有效完成率、各租户份额、运行/取消待确认占用和重试比。过载中“队列变短”也可能是大量超时丢弃，不能当吞吐提升；降级须同时看质量和用户可接受的结果率。

### 4. 一个可复跑的容量归还示例

以下是原创、**单线程顺序调用的教学状态机**，固定 Python 3.11.8；没有真实消息队列、网络、模型或并发测试。用两个已经过授权的租户 A/B，等待上限 4、运行上限 2、每租户等待加运行上限 3。所有调用先经过等待队列，满时即使运行名额暂空也会保守拒绝；它不是前表“无等待”的实现。时钟为从 0 起算的整数秒且不回退，deadline 到点即过期。

`ack_stopped` 是测试注入的“该物理 attempt 确已停止”，不是任意 HTTP 回包；`DONE` 仅表示停止且没有取消，不证明答案质量或交付。取消后的迟到成功仍归为 CANCELLED。此简化模型不重开同 key 的 attempt，保留终态记录用于识别重复；真实重试需独立 attempt ID、持久所有权和有界去重保留期。`jobs` 是本次有限演示的历史账本，生产不能无期限放在内存；队列有界不代表全部存储天然有界。正文其余准入估算、优先级、Token 配额和断线恢复不由这段代码实现。

<details>
<summary>展开 Python 状态机与固定事件轨迹</summary>

```python
"""Original serial teaching model. Python 3.11.8; no queue service or LLM."""
from collections import deque


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("expected nonnegative integer")


class Gate:
    def __init__(self, waiting_limit=4, running_limit=2, tenant_limit=3):
        for value in (waiting_limit, running_limit, tenant_limit):
            integer(value, 1)
        self.qmax, self.cmax, self.tmax = waiting_limit, running_limit, tenant_limit
        self.wait = {t: deque() for t in ("A", "B")}
        self.turns = deque(("A", "B"))
        self.jobs, self.running = {}, set()
        self.now = 0

    def identity(self, tenant, key):
        if tenant not in ("A", "B") or type(key) is not str or not 1 <= len(key) <= 64:
            raise ValueError("invalid trusted tenant or key")
        return tenant, key

    def advance(self, now):
        integer(now)
        if now < self.now:
            raise ValueError("clock moved backwards")
        self.now = now
        for identity, job in self.jobs.items():
            if now >= job["deadline"]:
                if job["state"] == "WAITING":
                    self.wait[identity[0]].remove(identity)
                    job["state"] = "EXPIRED"
                elif job["state"] == "RUNNING":
                    job["state"] = "CANCEL_PENDING"  # Still owns a running slot.

    def admit(self, tenant, key, deadline, now):
        identity = self.identity(tenant, key)
        integer(deadline, 1)  # Validate before comparing idempotency snapshots.
        old = self.jobs.get(identity)
        if old is not None and old["deadline"] != deadline:
            raise ValueError("same key with conflicting request")
        self.advance(now)
        if old is not None:
            return old["state"]  # No new attempt, even after cancellation.
        if deadline <= now:
            return "REJECT_EXPIRED"
        outstanding = len(self.wait[tenant]) + sum(x[0] == tenant for x in self.running)
        if outstanding >= self.tmax:
            return "REJECT_TENANT"
        if sum(map(len, self.wait.values())) >= self.qmax:
            return "REJECT_FULL"
        self.jobs[identity] = {"deadline": deadline, "state": "WAITING"}
        self.wait[tenant].append(identity)
        return "WAITING"

    def dispatch(self, now):
        self.advance(now)
        started = []
        while len(self.running) < self.cmax and any(self.wait.values()):
            tenant = self.turns[0]
            self.turns.rotate(-1)
            if not self.wait[tenant]:
                continue
            identity = self.wait[tenant].popleft()
            self.running.add(identity)  # Transfer before any hypothetical I/O.
            self.jobs[identity]["state"] = "RUNNING"
            started.append(identity)
        return started

    def cancel(self, tenant, key, now):
        identity = self.identity(tenant, key)
        job = self.jobs[identity]
        self.advance(now)
        if job["state"] == "WAITING":
            self.wait[tenant].remove(identity)
            job["state"] = "CANCELLED"
        elif job["state"] == "RUNNING":
            job["state"] = "CANCEL_PENDING"
        return job["state"]

    def ack_stopped(self, tenant, key, now):
        identity = self.identity(tenant, key)
        job = self.jobs[identity]
        if job["state"] == "WAITING":
            raise ValueError("cannot acknowledge an unstarted job")
        self.advance(now)
        if identity not in self.running:
            return False  # Repeated terminal acknowledgement cannot over-release.
        self.running.remove(identity)
        job["state"] = "CANCELLED" if job["state"] == "CANCEL_PENDING" else "DONE"
        return True


if __name__ == "__main__":
    g = Gate()
    for tenant, key in (("A", "a1"), ("A", "a2"), ("B", "b1"), ("B", "b2")):
        assert g.admit(tenant, key, 20, 0) == "WAITING"
    assert g.admit("B", "b3", 20, 0) == "REJECT_FULL"
    assert g.dispatch(0) == [("A", "a1"), ("B", "b1")]
    assert g.admit("A", "a3", 3, 0) == "WAITING"
    assert g.admit("A", "a4", 20, 0) == "REJECT_TENANT"
    assert g.cancel("A", "a1", 1) == "CANCEL_PENDING"
    assert g.dispatch(1) == [] and len(g.running) == 2
    g.advance(3)
    assert g.jobs[("A", "a3")]["state"] == "EXPIRED"
    assert g.ack_stopped("A", "a1", 3)
    assert g.dispatch(3) == [("A", "a2")]
    assert not g.ack_stopped("A", "a1", 3)
    assert g.dispatch(3) == [] and len(g.running) == 2
    print("queue-demo: PASS; waiting=1, running=2; cancelled output discarded")
```

</details>

直接运行代码会验证：第五个等待任务被拒绝；首次按 A/B 派发 a1、b1；A 的第四个在途任务被租户额度拒绝；取消 a1 后派发为空且运行量仍为 2；到 3 秒 a3 在队列中失效；只有确认 a1 停止后才能派发 a2；重复确认不能再释放名额。预期输出：`queue-demo: PASS; waiting=1, running=2; cancelled output discarded`。这是确定性状态轨迹，不是吞吐测量，也不证明生产原子性、取消完成时间或供应商并发保证。

## 延伸 / 追问

**流量均值低于容量，为什么还要拒绝？** 到达突发、长尾执行、供应商 TPM 或单租户占用都可能用完当前容量；均值小于容量不保证每个任务能在 deadline 内完成。按最老等待、运行工作量和端到端 SLO 决定准入，不能只看平均 QPS。

**worker 崩溃或租约过期后，能直接把运行计数减一吗？** 不能只凭协调端失联作此判断。要区分本地 worker 与远端 attempt：确认本地执行已终止只释放本地资源，远端仍未知则保留待对账额度，按服务契约查询/取消并隔离。接管者携带新的 ownership/fence，旧回调不能污染新 attempt；没有幂等契约时不盲目重放。

**全部请求都来自不可丢的离线任务，拒绝还有意义吗？** 有，拒绝的是当前执行准入，上游可按合同在有配额的持久存储中保留并减速重投。若输入长期大于服务率，且不允许丢弃、合并、降级或增加容量，就不可能同时保证有限存储与有限完成时间；必须改变约束，而不是换一个无限队列。

## 常见误区

- “加队列就增加吞吐”：只增加等待空间；持续正净流入必然填满。
- “超时就释放 semaphore”：本地放弃等待不等于远端已停止，cancel pending 必须算在相应运行额度内。
- “重试能提高成功率，所以每层都应重试”：过载下会放大物理调用；须跨层统一预算并重新准入。
- “FIFO 就是业务公平、调高优先级就能救急”：不同长度/租户的资源份额不同，运行中工作也不会凭优先级消失。
- “切小模型必然更快而且效果一样”：依赖任务、配额和部署，必须验证服务时间与质量；上面的 1.5 秒只是教学输入。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/ds-4.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/ds-4.html)、[slides/ds-interview.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/ds-interview.html)（Q11/Q12 学习线索）、[slides/7-6a.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/7-6a.html)。只保留题目来源；未采用课程中未经独立证实的容量/节省比例，不复制课件正文、代码或图片。
- CPython **v3.11.8**：[Lib/asyncio/queues.py](https://github.com/python/cpython/blob/v3.11.8/Lib/asyncio/queues.py#L99-L201)（full/put/get/task_done 的不同计数）、[Lib/asyncio/tasks.py](https://github.com/python/cpython/blob/v3.11.8/Lib/asyncio/tasks.py#L198-L218)（cancel 是请求）、[Lib/asyncio/locks.py](https://github.com/python/cpython/blob/v3.11.8/Lib/asyncio/locks.py#L421-L435)（BoundedSemaphore 的过量归还检查）。本文教学程序和源码口径固定于该版本。
- Reactive Streams JVM **v1.0.4**，[Specification README](https://github.com/reactive-streams/reactive-streams-jvm/blob/v1.0.4/README.md)：规则 1.1 的 demand 上限、1.8 的 eventually cancellation；只作为背压协议原理依据。
- IETF [RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)（2012，429）；[RFC 9110 §15.6.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.6.4) 与 §10.2.3（2022，503 与 Retry-After）。
- Google，*Site Reliability Engineering*，**2016 版第 21 章 [Handling Overload](https://sre.google/sre-book/handling-overload/)**，核对日期 2026-09-16：资源容量、负载拒绝、降级与重试放大。书中的具体资源经验不作为 LLM 容量公式的实测依据。
