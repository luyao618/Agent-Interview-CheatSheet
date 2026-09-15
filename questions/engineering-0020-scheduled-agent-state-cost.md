---
id: engineering-0020
title: 定时 Agent 应复用会话还是重建上下文，怎样兼顾增量状态、漏跑合并和预算？
category: engineering
tags: [scheduled-agents, state, catch-up, concurrency, budget]
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

定时 Agent 应复用会话还是重建上下文，怎样兼顾增量状态、漏跑合并和预算？以每小时新闻整理离线五小时后恢复为例，说明该跑几次、带哪些状态，以及如何处理重复执行、运行重叠和成本上界。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**通常按逻辑批次重建有限上下文，但把业务游标、未完成区间、去重和预算独立持久化。** 调度器只负责让系统有机会工作，不能把“触发过”“已经整理到这里”“已经发送给用户”当成同一件事。

同一次未完成执行的恢复机制见 [agent-0016](agent-0016-checkpoint-resume.md)，一般 Token 降本方法见 [agent-0038](agent-0038-reduce-agent-token-cost.md)，提交/副作用幂等见 [engineering-0002](engineering-0002-idempotency-distributed-transaction.md)。本题补充定时运行的时间与窗口语义，不复写完整 checkpoint 或计费方案。

### 1. 会话是工作上下文，业务状态才是恢复依据

| 方案 | 适用情况 | 需要保留什么，代价是什么 |
| --- | --- | --- |
| 每个逻辑批次重建上下文 | 新闻摘要、增量检查、定时报表，批次目标相对独立 | 注入稳定任务说明、必要偏好、窗口/游标和当前增量；上下文易约束，但不能丢失持久业务状态 |
| 恢复同一未完成 run 的会话/checkpoint | 多步骤调查、未完成工具流程，前面推导仍是后面动作的必要输入 | 保留有限执行上下文与工具结果，按版本恢复；不等于以后每次定时触发都追加到这段会话 |
| 长期复用一个会话 | 确实需要持续协作脉络，且能做有效压缩与校验 | 有上下文连续性，但旧新闻、工具输出和错误可能反复进入输入；必须有容量、版本与失效策略，不宜无限追加 |

**不能一概说“定时任务不需要记忆”，也不能无限追加旧会话。** 对话摘要可以帮助模型理解任务，但不能承担可靠的“已处理到哪里、已经花了多少、是否已发送”账本。推荐把以下状态独立保存：

- `tenant/task/config_version`：任务身份、规则、时区、调度策略、授权和配额版本。模型读到的新闻不能自行修改这些约束。
- `processed_until`：连续、已完成且结果已提交的业务覆盖边界；不是最后启动时间或调度器最新触发时间。
- `source_cursors`、`seen_news(id, version)`：各来源增量分页位置、稳定新闻 ID/修订版本。时间戳可能并列，应使用来源支持的游标或复合键，不能只靠“最后一条时间”。
- `pending_run`：固定窗口起止、恢复截止点、阶段、结果引用、租约/fence；一次恢复运行中不要反复把截止点改成新的 now。
- 物理调用次数、预算预留与待对账 usage；以及结果/outbox/发送回执。上下文清空、进程重启或 worker 接管不能把这些计数清零。

新闻的发布时间不一定等于系统可见时间。晚到、回填与更正可通过来源更新游标，或带回看区间的拉取加 ID/版本去重处理。不要只用 `published_at > 上次运行时间` 就宣称不会漏新闻；来源游标/拉取进度与摘要覆盖游标也应按实际流水线分别提交。

### 2. 离线五小时：先算到期点，再决定业务合并

**教学假设：**任务在 Asia/Shanghai 每小时整点整理，09:00 的任务已经成功处理并提交 `[08:00,09:00)`，所以 `processed_until=09:00`。随后离线，到 **2026-09-16 14:00:00+08:00** 恢复；没有配置丢弃迟到窗口。14:00 本身是已经到期的边界。

到期点是 10、11、12、13、14 点，**共五个，不是六个**；尚未完成的名义业务区间是 `[09:00,14:00)`。边界统一左闭右开：14:00 才出现的新记录属于下一窗口，不在当前批次的快照中。恢复时先固定 cutoff=14:00，下一正常边界为 15:00；14:05 恢复仍只有这五个完整小时窗口，13:59:59 恢复则只有四个。

| 恢复政策 | 本例逻辑运行数 | 覆盖区间与取舍 |
| --- | --- | --- |
| 每个错过周期分别补跑 | 5 | `[09,10)`、`[10,11)`、`[11,12)`、`[12,13)`、`[13,14)`；适合必须保留每小时独立结果，调用和通知可能较多 |
| 合并连续积压 | 1 | 一次处理 `[09,14)`；适合用户主要需要最新汇总，前提是来源完整性、上下文和预算允许 |
| 每批最多两小时 | 3 | `[09,11)`、`[11,13)`、`[13,14)`；适合五小时数据太多，逐批提交后再推进游标 |
| 只保留最近一小时 | 1 | 只处理 `[13,14)`；明确放弃 `[09,13)`，必须记录跳过区间并符合产品约定，不能称为完整补跑 |

**本例默认选择合并一次，覆盖五小时增量**，而不是补发五条同样的“当前新闻”。每个批次都从持久游标取范围，不以实际启动时间重新定义窗口。若数据量无法在限额内处理完整，则提前分批，或保存未完成状态等待明确的配额/计划调整；不能只取 Top-k 就把整个五小时标记为处理完。

调度器的 coalescing 只合并触发，不自动合并业务数据。APScheduler 3.11.0 的 `coalesce`、`misfire_grace_time` 与 `max_instances` 是不同控制项；源码会在达到实例上限时跳过提交，并不保证替应用保存待处理新闻。若任务只是取“现在之前一小时”，合并成一次照样会漏掉更早内容。Kubernetes CronJob 也明确可能创建重复 Job 或错过 Job，业务仍需幂等。

### 3. 重复、重叠和窗口提交如何收敛

把逻辑 run 绑定到 `(tenant/task/config_version, start_utc, end_utc)`，与每次物理执行 attempt 分开。重复触发若对应已完成区间，读取既有结果；未完成时恢复已持久化的窗口，不因为 now 变了、换 worker 或改合并方式就另开一个重叠区间。

每个新闻任务先串行处理连续区间，运行中来新触发时记录积压并在之后重新协调；不能把 `max_instances=1` 当成跨机器锁或永久不漏跑队列。可以选择并行处理互不重叠区间，但连续游标只能推进到已完成前缀，不能用最大完成时间越过中间失败窗口；本例不实现这种并行模式。

生产可以用协调存储中的租约与递增 fencing token 控制 owner。租约过期不代表旧 worker 已停：新 worker 接管后，旧 token 的游标/结果提交必须被拒绝；已经发出的模型调用仍可能计费。物理请求在发出前通过共享账本扣减额度，接管继续使用同一逻辑 run 的计数，不能重新获得完整重试预算。租约判断使用协调系统的时间源，进程内耗时/截止时间宜用单调时钟，不依赖各 worker 墙钟恰好一致。

只有确认该窗口的来源已完整处理、结果校验通过后，才在**一个本地持久事务**提交结果、outbox 与新游标。完成生成但写库失败不前移游标；outbox 后续发送失败只重试发送，不重新整理整段新闻。对外发送仍需稳定幂等键/回执核查，不能由本地事务推导远端 exactly-once；接收端没有相应能力时应明确可能重复或丢失的取舍。本题不发送任何真实新闻。

### 4. 时区和预算都是配置，不由长会话隐式决定

保存 IANA 时区名、调度规则和配置版本，内部窗口与幂等键用明确 UTC instant。Asia/Shanghai 的本例可按连续 3600 秒小时网格计算；“每天当地 09:00”或其他日历 cron 不能直接套这个固定间隔算法。夏令时切换会让某个当地时刻不存在或出现两次，应明确跳过、补跑、选择 fold 的策略，并按锁定的调度器/tzdata 验证。

下面的模拟刻意采用**以已确认 cursor 为锚点的 UTC 固定一小时间隔**，不是通用 cron parser。它拒绝 naive datetime 和 now 早于游标的输入；跨 DST 的本地显示可能跳过或重复一个小时，UTC key 仍然不同。更换时区/规则版本时要处理既有 pending 区间和预算，不能通过新配置键悄悄遗忘旧进度。

成本上界要限制物理调用，而不只是限制“一个 run”。以下均为**教学价格与限额，非供应商现价/实测账单**：

- 每逻辑 run 最多 **2 次物理模型请求**，包含失败、重试、接管前已发出的请求；每次计费输入上限 6000 Token，计费输出总量上限 1000 Token。
- 假定无缓存等其他计价路径，输入/输出价格分别为 2/8 美元每百万 Token；最多 2 次抓取，每次假定 0.001 美元。预算使用整数微美元，`1 USD=1,000,000 微美元`。
- 则每 run 的受控项目上界为 `2×(6000×2/10⁶ + 1000×8/10⁶) + 2×0.001 = 0.042 USD`。逐次五跑为 0.210 USD，合并一次为 0.042 USD，两小时分三批为 0.126 USD。本例分批结果可直接分段展示，没有额外模型总汇调用；若增加总汇或其他隐藏阶段，必须另计请求与预算。

若恢复预算为 0.150 USD，完整五跑不能一次全部准入；按该上界最多准入三跑，未处理窗口仍留在游标之后。能完整处理的合并方案可只预留 0.042 USD。合并不保证实际成本或质量更好：更大的输入可能需要更多分页/模型调用，因此须满足前述完整性条件。

输入计数包含系统提示、工具定义、当前增量和必要历史，下一次请求前重新测量；输出限制须对应实际计费口径，不能只限可见文字而忽略额外计费推理。SDK 隐式重试、子 Agent、工具和转发调用都要计入或禁用；无法约束的项目不能被藏在“上界”之外。此算式不含税、存储、网络等未建模费用，实际总预算需为它们另设已知上限。

预算预留应覆盖并发与所有 run；usage 缺失保留最坏预留，不按零释放。模拟采用保守的整 run 预留，完成后也不返还未用部分；生产只有在真实用量可核对后才可释放差额。日预算/恢复预算和调用计数必须持久化，不能每次唤醒或会话重建就清零。

### 5. 可复跑的恢复与预算模型

以下代码在 **Python 3.11.8** 本地运行，只有内存计划和账本，没有启动调度器、创建定时任务、读取真实新闻或调用模型。`complete_window=True` 与 `result_ref` 是可信业务处理层已确认完整性的模拟输入，不证明真实来源分页、新闻去重或摘要质量。租约、fence、预算和提交必须在真实存储中用事务/CAS 实现；本模型不提供线程/进程并发或崩溃恢复保证，也省略了续租接口。一次计划最多取 24 个已到期小时，超过部分仍留在游标之后；这是延期，不是丢弃或直接推进到 now。

<details>
<summary>固定间隔计划、接管与保守预算预留示例</summary>

```python
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

HOUR = timedelta(hours=1)
RUN_CAP_MICRO_USD = 2 * (6000 * 2 + 1000 * 8) + 2 * 1000  # 教学费率，42000微美元。


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return value.astimezone(timezone.utc)


def plan(cursor, now, mode, chunk_hours=2, max_slots=24):
    if type(mode) is not str or mode not in {"each", "merge", "chunks"}:
        raise ValueError("policy")
    if any(type(x) is not int or x < 1 for x in (chunk_hours, max_slots)):
        raise ValueError("positive integer limits required")
    start, cutoff = utc(cursor), utc(now)
    if cutoff < start:
        raise ValueError("clock/cursor regression")
    count = min((cutoff - start) // HOUR, max_slots)
    if count == 0:
        return []
    width = {"each": 1, "merge": count, "chunks": chunk_hours}[mode]
    return [(start + i * HOUR, start + min(i + width, count) * HOUR)
            for i in range(0, count, width)]


class Ledger:
    # 单个 tenant/task/config 的串行内存模型；不创建 scheduler 或发送新闻。
    def __init__(self, task, cursor, budget_micro_usd):
        if type(task) is not str or not task.strip():
            raise ValueError("task identity")
        if type(budget_micro_usd) is not int or budget_micro_usd < 0:
            raise ValueError("budget")
        self.task, self.cursor = task, utc(cursor)
        self.remaining = budget_micro_usd
        self.runs, self.outbox = {}, {}
        self.pending, self.active, self.epoch = None, None, 0

    def claim(self, start, end, owner, now, lease_seconds=600):
        start, end, now = utc(start), utc(end), utc(now)
        if type(owner) is not str or not owner.strip():
            raise ValueError("owner")
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
            raise ValueError("lease")
        if end <= start or end > now or (end - start) % HOUR:
            raise ValueError("closed integral-hour window required")
        key = json.dumps([self.task, start.isoformat(), end.isoformat()], separators=(",", ":"))
        if key in self.runs and self.runs[key]["status"] == "done":
            return None  # 已完成：读取既有结果，不再预留预算或重复生成。
        if start != self.cursor or (self.pending is not None and self.pending != key):
            raise ValueError("resume the existing contiguous window first")
        if self.active is not None and now < self.active["expires"]:
            if self.active["owner"] != owner:
                raise ValueError("busy")
            return (key, self.active["fence"])
        try:
            expires = now + timedelta(seconds=lease_seconds)
        except OverflowError as error:
            raise ValueError("lease outside datetime range") from error
        if key not in self.runs:
            if self.remaining < RUN_CAP_MICRO_USD:
                raise ValueError("insufficient reserved budget")
            self.remaining -= RUN_CAP_MICRO_USD
            self.runs[key] = {"start": start, "end": end, "status": "pending",
                              "model": 0, "fetch": 0, "result": None}
        self.epoch += 1
        self.pending = key
        self.active = {"owner": owner, "fence": self.epoch, "expires": expires}
        return (key, self.epoch)

    def checked(self, token, owner, now):
        now = utc(now)
        if (type(token) is not tuple or len(token) != 2 or type(token[0]) is not str
                or type(token[1]) is not int or token[1] < 1 or type(owner) is not str):
            raise ValueError("token/owner types")
        if (self.active is None or token != (self.pending, self.active["fence"])
                or owner != self.active["owner"] or now >= self.active["expires"]):
            raise ValueError("expired or superseded owner")
        return self.runs[token[0]]

    def use(self, token, owner, now, kind, input_tokens=None, output_limit=None):
        if type(kind) is not str or kind not in {"model", "fetch"}:
            raise ValueError("request kind")
        if kind == "model":
            if (type(input_tokens) is not int or not 0 <= input_tokens <= 6000
                    or type(output_limit) is not int or not 1 <= output_limit <= 1000):
                raise ValueError("per-request token limit")
        elif input_tokens is not None or output_limit is not None:
            raise ValueError("fetch has no model token fields")
        row = self.checked(token, owner, now)
        if row[kind] >= 2:
            raise ValueError("physical request quota exhausted")
        row[kind] += 1  # 实际发请求之前记账；失败、重试、接管都不重置。

    def finish(self, token, owner, now, complete_window, result_ref):
        if complete_window is not True or type(result_ref) is not str or not result_ref.strip():
            raise ValueError("complete source processing and valid result required")
        row = self.checked(token, owner, now)
        if row["start"] != self.cursor:
            raise ValueError("cursor conflict")
        row["result"], row["status"] = result_ref, "done"
        self.outbox[token[0]] = result_ref
        self.cursor = row["end"]
        self.pending, self.active = None, None
        # 生产需将结果、outbox、游标做成同一持久事务；此处没有外部发送。


def example():
    cursor = datetime.fromisoformat("2026-09-16T09:00:00+08:00")
    restored = datetime.fromisoformat("2026-09-16T14:00:00+08:00")
    plans = {mode: plan(cursor, restored, mode) for mode in ("each", "merge", "chunks")}
    ledger = Ledger("demo/news/config-v1", cursor, 150000)
    start, end = plans["merge"][0]
    token = ledger.claim(start, end, "worker-A", restored)
    ledger.use(token, "worker-A", restored, "fetch")
    ledger.use(token, "worker-A", restored, "model", 6000, 1000)
    ledger.finish(token, "worker-A", restored + timedelta(minutes=1), True, "simulated-summary-ref")
    assert ledger.claim(start, end, "worker-B", restored + timedelta(minutes=2)) is None
    return {"due_slots": len(plans["each"]), "logical_runs": {k: len(v) for k, v in plans.items()},
            "illustrative_cap_usd": {k: str(Decimal(len(v) * RUN_CAP_MICRO_USD) / 1000000)
                                     for k, v in plans.items()},
            "committed_cursor_utc": ledger.cursor.isoformat(),
            "reserved_micro_usd": 150000 - ledger.remaining, "outbox_records": len(ledger.outbox)}


if __name__ == "__main__":
    print(json.dumps(example(), ensure_ascii=False, indent=2))
```

</details>

实际模拟输出：到期点 5 个；each/merge/chunks 分别为 5/1/3 个逻辑 run，教学上界为 0.21/0.042/0.126 USD。合并提交后游标为 `2026-09-16T06:00:00+00:00`（上海 14:00），只保留一条 outbox 记录、预留 42000 微美元；相同区间再次 claim 返回已完成，不再预留或生成。

验证还覆盖了截止点前一秒、重复触发、预算不足、未处理完整、未来/不连续窗口、租约到期后新 owner 接管、旧 owner 拒绝提交、接管后物理调用上限不重置，以及 DST 两个方向的 UTC 窗口。时区用 `tzdata 2025.2 / IANA 2025b` 固定测试数据；实际部署应按采用的 tzdata 版本复核。这里检查的是教学规则与算例，不是真实账单或新闻交付结果。

## 延伸 / 追问

**追问 1：调度器只补触发一次，为什么仍可能漏新闻？**

如果这次仍只读最近一小时，就漏掉了更早积压。合并触发后要从持久业务游标读取到固定 cutoff，或明确登记被产品策略放弃的区间；同时处理源数据晚到、更正和分页完整性。

**追问 2：旧 worker 卡住，租约过期后能直接放心重跑吗？**

不能假设旧 worker 已停止。新 owner 必须取得更高 fence，提交端拒绝旧 token；所有已发请求和剩余重试额度仍属于同一逻辑 run。对外动作还需要执行端幂等/回执，租约本身不能撤回已发生的动作。

**追问 3：每次重建会话，如何保持用户偏好与长任务记忆？**

把明确的偏好、业务状态和必要知识作为有来源/版本的独立记录注入；同一次未完成流程从 checkpoint 恢复。长期会话摘要可辅助理解，但不能替代游标、授权、预算或发送账本。

## 常见误区

- **“定时任务不需要记忆。”** 它可能不需要旧聊天全文，但通常需要可靠的增量、去重、预算和交付状态。
- **“无限追加旧会话最省事。”** 旧上下文会增加重复输入并带入过期信息；必须限制和重建，不能用对话长度承载业务进度。
- **“漏跑五次就一定补五次。”** 到期点数量、逻辑批次数和数据覆盖范围是三个决定；须预先约定重放、合并或明确丢弃策略。
- **“并发上限为一就不会重复或漏跑。”** 调度器作用域、租约过期和远端副作用都还有边界，业务游标与幂等提交不能省。
- **“每次只花一点钱，不用跨 run 记账。”** 重试、积压和并发会叠加成本；未知 usage 与接管不能重置预算。

## 参考

- 课程线索：洛小山《AI 产品从入门到精通》learn-ai，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/9-26.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/9-26.html)、[slides/dsh-19.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-19.html)。只作选题线索；未沿用“定时任务一概不需要记忆”或固定成本倍率，正文、时间例与代码独立编写，未搬运 AGPL 素材。
- APScheduler 3.11.0，commit `6c72a51416893eb0eebbe63d0f2a0151952cab59`：[User guide](https://github.com/agronholm/apscheduler/blob/6c72a51416893eb0eebbe63d0f2a0151952cab59/docs/userguide.rst) 的并发实例、misfire 与 coalescing；[BaseScheduler 源码](https://github.com/agronholm/apscheduler/blob/6c72a51416893eb0eebbe63d0f2a0151952cab59/src/apscheduler/schedulers/base.py) 的 run_times 合并和实例上限处理；[CronTrigger 文档](https://github.com/agronholm/apscheduler/blob/6c72a51416893eb0eebbe63d0f2a0151952cab59/docs/modules/triggers/cron.rst) 的 wall-clock/DST 边界。本题没有启动 APScheduler，不能把自己的恢复政策说成该库默认保证。
- Kubernetes 官方 CronJob `batch/v1` 文档固定快照 `b0d509bc3e2da337260abb3cff31517f02cb9077`：[CronJob](https://github.com/kubernetes/website/blob/b0d509bc3e2da337260abb3cff31517f02cb9077/content/en/docs/concepts/workloads/controllers/cron-jobs.md)，concurrencyPolicy、startingDeadlineSeconds、timeZone 与近似调度/幂等要求；同一 CronJob 的并发策略不是所有任务的全局锁。
- CPython 3.11.8，commit `db85d51d3ea4adfc6147d6af400e167659689eed`：[zoneinfo 文档](https://github.com/python/cpython/blob/db85d51d3ea4adfc6147d6af400e167659689eed/Doc/library/zoneinfo.rst)，时区数据来源、fold 与 UTC 转换；Python 维护的 [tzdata 2025.2](https://pypi.org/project/tzdata/2025.2/) 用于固定本例 DST 测试数据。

来源核实与本地模拟日期：**2026-09-16**。未创建真实定时任务、发送新闻或访问真实账单；预算价格和执行策略均为明确标注的教学假设。
