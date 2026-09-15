---
id: engineering-0017
title: 多模型路由怎样兼顾质量、成本与可用性，主模型超时后如何安全切换？
category: engineering
tags: [model-routing, failover, reliability, streaming, idempotency]
difficulty: medium
role: engineer
contributor: 佚名
source: 洛小山《AI 产品从入门到精通》learn-ai（固定版本见参考）
status: published
updated: 2026-09-15
answers:
  - author: GPT-6
    type: ai
    model: GPT-6
    answered: 2026-09-15
    updated: 2026-09-15
---

## 问题

多模型路由怎样兼顾质量、成本与可用性，主模型超时后如何安全切换？请分别设计限流、首 Token 前超时、已输出半句三种失败路径，并说明工具动作可能已执行时怎么办。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**先筛选满足业务契约的模型，再按质量、成本和可用性排序；失败后先确认输出与动作状态，最后才决定是否重试或切换。** 路由解决“这次由谁做”，fallback 解决“这次失败后怎样恢复”。备用模型能响应，不等于它能正确接管，也不等于旧请求什么都没做。

任务分级可参考 [agent-0038](agent-0038-reduce-agent-token-cost.md)，Prompt 与工具适配见 [agent-0022](agent-0022-prompt-mcp-abstraction.md)。本题补充降级状态机；重复请求的计费归集见 [engineering-0016](engineering-0016-llm-billing-reconciliation.md)，监控指标见 [engineering-0006](engineering-0006-ai-app-monitoring.md)。

### 1. 路由先满足契约，再做优化

把任务分成可测的业务类别，例如短文本分类、带引用问答、结构化抽取和需要工具的业务操作。用同一保留集比较候选模型在各类任务中的成功率、严重错误、格式合法率、工具参数正确率、延迟分位数和实际费用；不能仅按参数量、通用榜单或模型自报“我有把握”选路。

| 方案 | 适用条件 | 代价与不适用场景 |
| --- | --- | --- |
| 固定主模型 + 经验证的备用列表 | 任务集中、可用模型少，需要容易解释和定位故障 | 简单可靠，但难充分利用不同任务的成本差异；单一列表不适合所有模态/工具组合 |
| 规则路由 + 各任务独立 fallback 列表 | 任务类别、上下文量及必要能力可以判断 | 可审计、便于灰度；规则需维护，边界请求可能被误分类 |
| 学习型路由或“小模型先答，再由验证器决定升级” | 有代表性数据、可靠的质量信号且升级预算充足 | 路由与验证本身有成本，分布变化要重测；廉价模型给出流畅错误、验证器又漏检时会错误放行，不适合无验证依据的高风险自动操作 |

模型注册表必须绑定实际 provider、model snapshot、API/适配器版本和通过的契约测试，至少检查：输入模态与上下文容量、输出 schema/拒绝/截断状态、工具名称及参数 schema、tool call/result 的关联方式、并行工具行为、允许的数据区域与服务策略。切换前按目标模型重新检查序列化后的输入与输出预留量，不能假设 tokenizer 和上下文上限相同。

“都兼容某个 HTTP 接口”或“都能接 MCP”不证明行为相同。将已确认的业务历史转换为内部规范表示，再由目标适配器生成请求；不要直接搬运另一个 provider 的私有回放字段、不完整 assistant 消息或半段工具 JSON。模型不支持必要工具/模态时应退出该候选，不能悄悄删掉约束；若允许改成纯文本建议，必须是已定义的产品降级方案。

### 2. 总预算、退避与熔断共同约束切换

入口设置单调时钟上的绝对 `deadline = start + total_budget`。路由、排队、连接、模型、工具、退避及恢复都使用同一预算；另给最终状态落盘、响应收尾留余量。单次 timeout 受剩余预算约束，不能每换一个模型就重置整段等待时间。首 Token 超时、流中无进展超时与整次调用超时分别计时，收到一个心跳或首 Token 不应无限续期总 deadline。

对限流、暂时服务错误和网络故障，先确认是否适合重试。认证失败、请求 schema 不合法、用户取消等不能靠换模型掩盖；安全拒绝也不应触发绕过限制的轮询。限流应区分短期容量与配额耗尽，备用通道还须满足租户总预算、并发和数据流向限制。

采用有上限的指数退避和 jitter，并限制总 attempts。若 SDK、网关和业务层同时重试，很容易把一次任务放大成多次实际请求；应指定重试负责人，其他层关闭自动重试或把每次尝试纳入同一账本和预算。`Retry-After` 可是秒数或 HTTP-date，适配器需解析成等待时长并映射到单调时钟。对于受该限制约束的配额域，不得为满足本地上限把服务端等待缩短；等不起就停止。同一账户或网关下的备用模型可能仍共享配额，不能只看模型名。

熔断控制的是一段时间内的准入，不能把单次 timeout 就叫完整熔断机制。按 provider/区域/配额域观察符合条件的故障：closed 正常放行，达到门槛后 open 暂停；冷却后 half-open 只允许少量探测，成功才恢复。权限错误不应计成全站故障，429 的账户级配额限制也不应误伤其他租户。备用与主模型若共享故障依赖，切换可能只会扩大重试风暴。

### 3. 三种失败路径先看“已经发生什么”

| 失败位置 | 无副作用时的处理 | 必须保留的边界 |
| --- | --- | --- |
| 429 限流，尚无可见输出 | 标记受限配额域；预算允许时按退避等待原域，或切至合格且独立的域 | 不把永久配额问题当短暂抖动；不绕过租户总体限额；记录每个真实 attempt |
| 首 Token 前 timeout | 尝试取消旧请求、封存旧 attempt；确认动作未发送后，按同一业务请求重新生成 | 没看到 Token 不证明服务端没计算、没计费、没调用托管工具；本地取消不证明服务端已停止 |
| 已展示半句后断流或 error event | 本题选择标为“回答中断”，保留明确的不完整标记，停止自动切换 | 不把备用模型的续文直接拼到主模型半句后，不把失败半句存为已完成历史或执行依据 |

每个 attempt 带独立 ID/epoch，失败或切换后迟到的旧片段不能进入当前输出。HTTP 200 只说明流建立，后续仍可能出现错误事件；工具参数流也可能只有半个 JSON。示例选择在完整调用结束、参数/schema/当前授权及业务规则校验通过后才进入动作执行，不用片段级“看起来完整”替代提交条件。

流式产品有两种合理策略：先缓冲完整结果再提交，切换时可丢弃未展示的失败草稿，但首字体验较慢；边生成边展示则更快，却需要显式中断和“重新生成”版本，不能承诺完全无感。若业务允许重启，应创建新的 answer/attempt，把失败版本标清；继续生成必须基于已确认的检查点，不能假设两个模型的文本、工具状态和私有推理状态可直接接续。

工具动作另有持久账本：`NOT_SENT → PREPARED → IN_FLIGHT → COMMITTED`，连接中断可能把状态变为 `UNKNOWN`。PREPARED 必须明确表示尚未发送，而非“已发但未收到确认”。只有确定未发送的动作才可按正常规划继续；IN_FLIGHT/UNKNOWN 先按业务操作 ID 查询权威结果或进入人工处理，不能盲目重放。COMMITTED 复用已确认的工具结果，从检查点生成解释，不再次执行动作。

幂等键应绑定“同一个业务意图”，跨模型保持稳定，由工具服务在其作用域内原子去重并校验参数一致；不能每次重试生成新键，也不能仅因参数相同就假定是同一次意图。LLM API 的 request ID 不等于退款工具的幂等保证。若服务不支持幂等、状态查询也无法定论，应返回待核查状态，不能承诺恰好执行一次。恢复查询本身也占预算；本轮时间用完后可结束为 pending，后续恢复需由持久任务机制承担。

### 4. 实际运行一个有限的切换决策模拟

下列所有目标名称、能力标签、配额域和时间都是**教学设定**，没有调用真实模型、SDK、网关或退款服务。任务需要 `text + tool:refund-v1 + json:answer-v1`，已核验输入加输出预留共 3000 个教学 Token 单位、只允许指定区域；真实系统须逐模型重新计量与验证。`incompatible` 缺少必要能力，必须跳过。

从任务起点算起总预算 8000 ms，收尾预留 500 ms；最多 2 个 attempts，包含已经发送的主模型；备用单次最多 4000 ms，留不足 1000 ms 不启动。退避为 full jitter 的教学固定抽样值 0.5，首次从 `[0,500]` ms 得到 250 ms。`Retry-After` 已由适配器解析成非负整数毫秒；它只限制被确认共享的配额域 Q1，Q2 在本例中确认为独立且准入允许。

代码返回 `(决策, 目标, 计划开始时刻ms, 单次timeout_ms)`。RETRY 同时表示重试调度，目标可为兼容备用模型；其它结果不发新模型请求，两个 0 表示无调度。RESUME_CHECKPOINT 只是交给上层恢复流程的状态，不是自动重放工具。

这是顺序运行的状态与调度计算模拟：RETRY 分支把时钟视为推进到计划开始时刻，不执行真实 sleep/I/O；实际执行器还必须在真正发送时重检 deadline、准入和契约，按计时器取消流，并用相同 attempt 标识过滤所有晚到回调。Breaker 的 `finish` 由调用方在已准入请求的真实结果上调用，只记录选定的可用性故障；本例的连续 3 次失败、5000 ms 冷却是教学参数，不是生产阈值。代码不实现跨线程锁、分布式动作账本或 SDK 重试控制。

```python
from dataclasses import dataclass, field

NEED = frozenset({"text", "tool:refund-v1", "json:answer-v1"})

@dataclass
class Breaker:
    failures: int = 0
    open_until: int | None = None
    probe: bool = False

    def admit(self, now):
        if self.open_until is None:
            return True
        if now < self.open_until or self.probe:
            return False
        self.probe = True  # 冷却后只放一个half-open探测。
        return True

    def finish(self, ok, now):
        if ok:
            self.failures, self.open_until, self.probe = 0, None, False
        else:
            self.failures += 1
            if self.probe or self.failures >= 3:
                self.open_until = now + 5000
            self.probe = False

@dataclass
class Target:
    name: str
    caps: frozenset
    quota: str
    region: str = "allowed-region"
    context: int = 8000
    breaker: Breaker = field(default_factory=Breaker)

@dataclass
class Run:
    deadline: int = 8000
    reserve: int = 500
    attempts: int = 1  # 已发出的主模型请求也计入上限2。
    epoch: int = 1
    visible: str = ""
    effect: str = "NOT_SENT"
    accepting: bool = True

    def chunk(self, epoch, text):
        if not self.accepting or epoch != self.epoch:
            return False
        self.visible += text
        return True

    def fail(self, reason, now, targets, retry_after=0, source_quota="Q1"):
        # 输入是适配器/动作账本确认的状态。先封存旧attempt，迟到片段不再可见。
        self.epoch += 1
        self.accepting = False
        if self.effect in {"IN_FLIGHT", "UNKNOWN"}:
            return "RECONCILE", None, 0, 0
        if self.effect == "COMMITTED":
            return "RESUME_CHECKPOINT", None, 0, 0
        if self.effect not in {"NOT_SENT", "PREPARED"}:
            raise ValueError("unrecognized effect state")
        if self.visible:
            return "INTERRUPTED", None, 0, 0
        if reason not in {"RATE_LIMIT", "TIMEOUT", "TRANSPORT", "SERVER"}:
            return "STOP_ERROR", None, 0, 0
        if self.attempts >= 2:
            return "STOP_ATTEMPTS", None, 0, 0
        if any(type(v) is not int or v < 0 for v in (now, retry_after)):
            raise ValueError("nonnegative integer milliseconds required")
        # full jitter的固定抽样值0.5，仅供复现；生产使用独立随机值。
        delay = int(0.5 * min(2000, 500 * 2**(self.attempts-1)))
        for target in targets:
            if not NEED <= target.caps or target.region != "allowed-region" or target.context < 3000:
                continue
            wait = max(delay, retry_after) if target.quota == source_quota else delay
            start = now + wait
            available = self.deadline - self.reserve - start
            if available < 1000:  # 留不出至少1秒的尝试窗口，不启动。
                continue
            if not target.breaker.admit(start):
                continue
            self.attempts += 1
            self.accepting = True  # 模拟在start时启动新attempt；没有真实sleep或I/O。
            return "RETRY", target.name, start, min(4000, available)
        return "STOP_NO_ROUTE", None, 0, 0

def targets():
    return [Target("incompatible", frozenset({"text"}), "Q2"),
            Target("backup", NEED, "Q2")]

rate = Run()
print("rate_limit", rate.fail("RATE_LIMIT", 200, targets(), retry_after=1000))
timeout = Run()
print("before_first_token", timeout.fail("TIMEOUT", 2500, targets()))
print("late_primary_chunk", timeout.chunk(1, "迟到的主模型文本"))
partial = Run()
partial.chunk(1, "退款条件是")
print("partial_output", partial.fail("TRANSPORT", 1200, targets()))
print("unknown_effect", Run(effect="UNKNOWN").fail("TIMEOUT", 2500, targets()))
print("committed_effect", Run(effect="COMMITTED").fail("TIMEOUT", 2500, targets()))
print("shared_quota", Run().fail("RATE_LIMIT", 200, [Target("shared", NEED, "Q1")], retry_after=1000))
print("budget_exhausted", Run().fail("TIMEOUT", 6501, targets()))
```

**真实运行 stdout：Python 3.11.8，2026-09-15。** 实测对象为本地模拟状态机及预算运算，不是模型可用性、真实性能或实际退款行为：

```text
rate_limit ('RETRY', 'backup', 450, 4000)
before_first_token ('RETRY', 'backup', 2750, 4000)
late_primary_chunk False
partial_output ('INTERRUPTED', None, 0, 0)
unknown_effect ('RECONCILE', None, 0, 0)
committed_effect ('RESUME_CHECKPOINT', None, 0, 0)
shared_quota ('RETRY', 'shared', 1200, 4000)
budget_exhausted ('STOP_NO_ROUTE', None, 0, 0)
```

限流路径在 200 ms 失败，独立 Q2 的备用计划于 450 ms 开始；若共享 Q1，则至少等到 1200 ms，不能忽略 1000 ms 的 Retry-After。首 Token 前超时在 2500 ms 发生，备用于 2750 ms 开始，最多运行至 6750 ms；加 500 ms 收尾也没有超出 8000 ms。6501 ms 才失败时，加退避只剩 749 ms 的尝试窗口，因此停止，不能再给备用一个全新 8 秒。

部分输出保留中断状态；未知动作返回 RECONCILE；已提交动作返回 RESUME_CHECKPOINT。这三个结果都不增加模型 attempts、不调用工具。旧主模型的迟到片段被 epoch 拒绝。另用独立边界检查验证 half-open 单探测、恢复/重开、契约不兼容、预算等号和 attempts 上限。

### 5. 如何证明路由值得上线

分别评估每个任务类别的质量底线，再比较固定路由、规则路由和候选升级策略。记录首选成功率、fallback 成功率、全部失败率、错误升级/错误降级、工具参数正确率、重复动作、部分输出中断率、p95/p99 端到端延迟及每个任务的全部 attempts 成本。备用成功不抹掉主模型的耗时、费用和潜在副作用。

用故障注入覆盖 429/Retry-After、首 Token 超时、流中错误、旧片段晚到、完成响应丢失、动作已提交但客户端未知、熔断冷却和半开竞争；除返回结果外，还核对实际模型调用数与工具执行次数。上线前验证所有 fallback 边都通过能力、格式和授权测试，先小流量灰度。模拟通过只能证明模拟范围内的状态和算术；真实配额关联、模型质量、取消语义与工具去重需要相应的集成验证。

## 延伸 / 追问

**追问 1：主模型 5 秒超时，备用也给 5 秒，能否保证 5 秒完成？**

不能。两次尝试、等待和收尾都会累积。设置绝对 deadline，把备用 timeout 限制在剩余预算内，剩余不足就结束或转入明确的异步流程，而不是反复重置计时器。

**追问 2：没有收到任何 Token，为什么不能直接让备用再次调用退款工具？**

因为动作和文本是两条状态线：托管工具或外部执行器可能已执行，只是确认丢失。先查业务操作账本与权威结果；状态未明不重放，已提交就复用结果。退款成功与否不能由模型超时推断。

**追问 3：给所有 fallback 加同一个 tool schema 就足够了吗？**

不够。模型可能不支持该 schema 子集、严格输出、并行工具或所需模态；参数形状相同也不代表业务语义正确。适配器版本与模型组合要通过同一契约集，不合格的候选不能接管。

## 常见误区

- **“备用模型一定能理解同一种工具格式。”** 能力、schema、参数语义和调用生命周期都须验证，接口相似不等于可替换。
- **“超时就是没执行，重新发一遍即可。”** 副作用可能已提交；UNKNOWN 应对账，COMMITTED 应恢复检查点。
- **“已经输出半句，换模型接着写就无感了。”** 容易混合结论、重复内容或伪造工具状态，应标记中断或显式开启新版本。
- **“加更多备用就一定更可靠。”** 共享配额和故障依赖、累计等待及多层重试都可能使系统更差。
- **“熔断冷却结束后全部流量立即恢复。”** 先限制 half-open 探测，再根据结果恢复，避免瞬间压垮刚恢复的服务。

## 参考

- 课程线索：洛小山《AI 产品从入门到精通》learn-ai，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/cost-eval.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/cost-eval.html)、[slides/9-4.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/9-4.html)、[slides/dsh-22.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-22.html)。只用作选题线索；正文、参数和代码独立设计，未搬运 AGPL 素材，未把课程项目的降级策略或运行时细节当作普遍保证。
- IETF，[RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)，2022-06，§9.2.2、§10.2.3：幂等与非幂等请求重试边界、Retry-After 格式。业务工具是否幂等仍由服务契约决定。
- AWS Builders' Library，[Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)，caller-provided request identifier、相同参数与不同意图、迟到请求及去重语义。
- Google Cloud，[Retry strategy](https://docs.cloud.google.com/storage/docs/retry-strategy)，暂时故障与幂等性、退避、总重试预算及多层重试风险。该文档描述 Cloud Storage，本题只引用通用机制，不将其 SDK 默认值套用于模型 API。
- Microsoft Azure Architecture Center，[Circuit Breaker pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)，closed/open/half-open 状态及有限探测。
- Anthropic，[Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming)，Messages API 的 in-stream error、tool_use 的 partial JSON 与内容块完成事件；正文的“完整调用结束后才执行”是本例更保守的应用提交策略，不声称是所有协议的唯一选择。

以上一手文档于 **2026-09-15** 核验。示例不使用真实模型版本；实际部署应在注册表锁定经过测试的模型 snapshot、API、适配器与工具 schema 版本，不能仅凭本文标签推断兼容性。
