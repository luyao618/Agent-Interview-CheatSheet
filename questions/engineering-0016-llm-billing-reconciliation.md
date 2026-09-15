---
id: engineering-0016
title: 多轮 Agent 的真实账单怎样计算和对账，如何处理缓存读写、隐藏调用与阶梯价格？
category: engineering
tags: [billing, reconciliation, cost, prompt-caching, observability]
difficulty: medium
role: both
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

多轮 Agent 的真实账单怎样计算和对账，如何处理缓存读写、隐藏调用与阶梯价格？请给出含缓存和重试的三次调用账本，说明 usage 缺失和字段包含关系怎样处理。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**以每次实际服务请求为计量单位，先把 usage 转成互斥计费类别，再匹配当时适用的价表，最后与供应商同口径的用量和费用核对。** 一次用户任务可能包含主 Agent、子 Agent、路由、摘要和重试；用户看到一条答案，不等于后台只发了一次请求。`任务费用 = Σ 每次已确认请求费用 + 其他计费项目`，逐次相加后不能再乘一次调用次数。

Token 的本地估算与容量预算见 [llm-0007](llm-0007-tokenization-bpe-budget.md)，KV 的计算复用机制见 [llm-0018](llm-0018-kv-cache-prefill-decode.md)。本题的增量是请求级账本、未知用量补证、时间/价表归属和对账，不重复 tokenizer 或缓存原理。

### 1. 先记录请求，再按任务归集

至少保存业务 `run_id`、父子 span、逻辑操作、attempt 序号、本地请求 ID、供应商 request ID、供应商/项目/区域、实际模型 snapshot、服务档位、币种和价表版本。保留原始 usage 与其来源、是否最终值、归一化版本，以及请求发起、供应商计量、客户端结束和费用入账的时间。

**真实重试与重复日志必须分开。** 同一逻辑操作重发为不同物理请求，可能各有费用；相同 request ID 的最终 usage 被采集两遍则不能收两遍。生产去重键要包含供应商与账户/项目等作用域，不能只按 prompt 文本或业务 run_id 去重。若供应商 ID 尚未知，先保留本地 attempt 记录，不能把所有空 ID 合成一条。

父 span 的聚合金额是展示结果，不是新的收费事件。汇总时只计底层服务请求，避免把“父 Agent 总额”和“子 Agent 明细”再相加。路由器、上下文压缩、翻译、评测器或框架自动重试可能不显示在聊天记录中，也应进入调用清单；embedding、搜索、存储和工具执行费等作为各自单位的独立项目。不能把所有工具使用都机械当作一次 LLM 调用。

多轮对话里，同一段内容本次作为输出、下次又作为输入，是**不同请求中的实际使用**；不能按文本去重抹掉下一次费用。需要避免的是同一请求中总字段与子字段重复入账。

### 2. 字段同名，不代表包含关系相同

以下一手文档核实日期为 **2026-09-15**，分别限定 API 口径。保留原始字段后，再形成普通输入 `N`、缓存读取 `R`、缓存写入 `W` 和计费输出 `O` 等互斥类别：

| 文档 / 接口口径 | 正确归一化 | 常见重复或漏记 |
| --- | --- | --- |
| OpenAI Responses；当日文档中 GPT-5.6 及以后具有独立缓存写入字段的路径 | `I=input_tokens` 包含读取 `R=input_tokens_details.cached_tokens` 与写入 `W=input_tokens_details.cache_write_tokens`，普通输入 `N=I-R-W` | 给完整 I 收普通输入费后，再给 R/W 收完整类别费；或把写入一概按普通输入价计费 |
| Claude Messages + Prompt Caching 文档 | `N=input_tokens` 是未读缓存、未写缓存部分；`R=cache_read_input_tokens`、`W=cache_creation_input_tokens`，总输入为 `N+R+W` | 把这个 input_tokens 误当总输入，再减一次缓存；或只统计它而漏掉缓存用量 |
| OpenAI Responses 的输出细分 | `O=output_tokens` 已包含其中的 `output_tokens_details.reasoning_tokens` | 把 reasoning 子计数再加到 O；只数可见回答而漏掉其他计费输出 |
| 写入 TTL、音频/图像或其他类别细分 | 按所选接口定义确认子类是否包含在父类里，以及是否适用不同单价 | 同时收费写入总量与全部 TTL 子量，或把多模态子类一律按文本价处理 |

归一化后应验证数量非负、已知父子字段关系一致。**缺失不等于零**：某模型/协议明确没有独立写入类别时，可按其合同口径处理为结构性零；原本应该返回的字段缺失、null 或流中断，则应标为未知。接口升级后不能继续沿用旧的“字段不存在就填 0”。

若写入价是该类别的**完整单价**，单次文本费用为：

```text
C_i = (N_i × p_N + R_i × p_R + W_i × p_W + O_i × p_O) / 1,000,000
```

这里单价单位为货币 / 百万 Token。写入若有多个 TTL/模式与价格，进一步拆分 W；若合同报价是附加费而非完整单价，也须相应改公式。不要用 `total_tokens × 某一个单价`，也不要把 `max_output_tokens` 预留量当成实际 O。

### 3. 什么时候计量，什么时候能确认完整

请求前的本地估算用于预算，不是最终计量。流式回包要按协议组装：OpenAI Chat Completions 的 `stream_options.include_usage` 可返回全请求最终 usage，但中断时可能收不到；Claude `message_delta.usage` 的 token 数是累计值，不能把各事件的累计数相加。两个接口的流式语义和字段命名不同，应使用各自适配器。

对某个请求，累计输出曾报告 20、60、100 Token，最终值若确认为 100，就不能按 180 算。若只收到 60 后中断，60 至多是已观测部分，不能据此认定最终输出恰为 60。已知部分可以支持单独的观测统计，**缺少最终证据的请求仍应保留待核实状态**。客户端失败、取消或没有可见文本都不自动代表零费用；例如 reasoning 模型可能已消耗计费输出而尚未返回可见答案。

同时记录多个时间，避免错日或错价：客户端开始/结束时间描述用户体验；供应商计量时间决定应归哪个结算桶；最终 usage 到达和费用入账可能更晚。按合同确认价表生效采用请求开始、完成还是其他时点，并统一时区及区间边界，如 `[start, end)`。延迟到达的记录应回填原计量窗口，不能因为今天收到就全算今天；新价格也不能回溯覆盖旧请求。

### 4. 自编的三次调用账本

下面所有 ID、usage、时间、价格和供应商对账金额都是**教学数据**，没有访问真实账户、账单或凭据。虚构模型为 `DEMO-v1`，价表版本 `DEMO-2026-09-15`；本例规定从 `2026-09-15T00:00:00Z` 生效，采用供应商请求开始时间 `meter_at` 选择价表和 UTC 日桶。

同一个业务任务 `demo-run-01` 有主 Agent 调用 A，以及子 Agent 同一逻辑操作的尝试 B、重试 C。本例编排器直接交付 C 的结果，不再调用主模型润色；实际若有最终汇总调用，必须另列账行。B 在收到请求 ID 后流式中断，本地没有最终 usage；本题稍后人为提供其最终计量记录作为补证。**这不意味着每个真实供应商都能导出逐请求 usage。** 没有等价证据时不能靠聚合账单猜出 B 的精确用量。

价格单位全部为 **USD / 百万 Token**；只有一个写入费率，且为完整写入价。按**单次总输入 `I=N+R+W`** 选档，并对该请求的四类用量全量应用该档价格；这不是任何实际厂商的阈值或报价：

| 教学档位 | 普通输入 p_N | 读取 p_R | 写入 p_W | 输出 p_O |
| --- | ---: | ---: | ---: | ---: |
| I ≤ 2000 | 2 | 0.5 | 2.5 | 8 |
| I > 2000 | 4 | 1 | 5 | 16 |

| request ID / 角色与尝试 | meter_at（UTC，当日） | N | R | W | O | 初始本地状态 → 补证后的结果 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| req-A / 主 Agent，第 1 次 | 00:00:01Z | 400 | 0 | 1600 | 200 | 最终 usage 已知；I=2000，低档 |
| req-B / 子 Agent，第 1 次 | 00:00:02Z | 600 | 1600 | 0 | 100 | 本地 usage 未知 → 人工补证为本行数字；I=2200，高档 |
| req-C / 同一子操作，第 2 次 | 00:00:04Z | 600 | 1600 | 0 | 150 | 重试成功，新的物理请求；I=2200，高档 |

表中 B 的数字属于**补证后**账本，不能在本地仍未知时提前当成事实。按给定价表：

- A：`(400×2 + 0×0.5 + 1600×2.5 + 200×8)/1e6 = 0.006400 USD`。
- B：`(600×4 + 1600×1 + 0×5 + 100×16)/1e6 = 0.005600 USD`。
- C：`(600×4 + 1600×1 + 0×5 + 150×16)/1e6 = 0.006400 USD`。

B 补证前只能报告“已知小计 **0.012800 USD，1 次调用待核实**”，不能报任务总额已经确定。补证后总计 **0.018400 USD**。B 和 C 是两次实际请求，虽然属于同一子任务、输入相同，仍各自计量；A 的同一最终日志被采集两遍则只记一次。

### 5. 可运行的快照计价与对账示例

代码只处理已归一化、同一虚构供应商/项目/模型/币种/价表下的快照，不实现生产 API 客户端或自动补证。usage 桶顺序为 `(N,R,W,O)`；None 保留未知，负数和布尔值拒绝。新的 resolved 快照不覆盖原始 observed，原始事件应另行保留审计。冲突快照主动报错，不靠“最后一条覆盖”掩盖矛盾。

```python
from decimal import Decimal as D

PRICE_VERSION = "DEMO-2026-09-15"  # 教学价格，不是真实模型报价。
MILLION = D(1_000_000)
LOW = tuple(map(D, ("2", "0.5", "2.5", "8")))
HIGH = tuple(map(D, ("4", "1", "5", "16")))

def quote(usage):
    # 已归一化互斥桶，顺序为普通输入、读取、写入、计费输出。
    if usage is None:
        return None
    if len(usage) != 4 or any(v is not None and (type(v) is not int or v < 0) for v in usage):
        raise ValueError("four nonnegative integer counts, or unknown None, required")
    if any(v is None for v in usage):
        return None
    normal, read, write, output = usage
    rates = HIGH if normal + read + write > 2000 else LOW
    return sum((D(n) * p for n, p in zip(usage, rates)), D(0)) / MILLION

def summarize(snapshot):
    # 同一虚构供应商/项目/模型/价表内，按物理request_id去重。
    # 只接收已选定的usage快照；冲突不能用“最后一条覆盖”掩盖。
    by_id = {}
    for request_id, usage in snapshot:
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("a physical request ID is required")
        if request_id in by_id and by_id[request_id] != usage:
            raise ValueError("conflicting usage snapshots")
        by_id[request_id] = usage
    known = D(0)
    pending = []
    for request_id, usage in by_id.items():
        amount = quote(usage)
        if amount is None:
            pending.append(request_id)
        else:
            known += amount
    return known, pending

observed = [
    ("req-A", (400, 0, 1600, 200)),       # 主Agent调用，写入缓存。
    ("req-B", None),                     # 子Agent首次尝试：流中断，最终usage未知。
    ("req-C", (600, 1600, 0, 150)),       # 子Agent重试，新的物理请求。
]
known, pending = summarize(observed)
print(f"before evidence: known={known:.6f} USD, pending={pending}, complete={not pending}")

# 人工补证数据，不是实际供应商导出；原始observed仍保留未知状态。
recovered = {"req-B": (600, 1600, 0, 100)}
resolved = [(rid, recovered.get(rid, usage)) for rid, usage in observed]
for request_id, usage in resolved:
    tier = "high" if sum(usage[:3]) > 2000 else "low"
    print(f"{request_id}: tier={tier}, cost={quote(usage):.6f} USD")
total, pending = summarize(resolved + [resolved[0]])  # A的重复日志不多收费。
supplier_token_subtotal = D("0.018400")              # 人工同口径对账金额。
print(f"after evidence: total={total:.6f} USD, pending={pending}")
print(f"reconciliation delta={total - supplier_token_subtotal:.6f} USD")
print(f"threshold 2000/2001: {quote((2000,0,0,0)):.6f} / {quote((2001,0,0,0)):.6f} USD")
```

**真实运行 stdout：Python 3.11.8、2026-09-15；实际执行的是教学数据的 Decimal 运算，不是访问真实账单。**

```text
before evidence: known=0.012800 USD, pending=['req-B'], complete=False
req-A: tier=low, cost=0.006400 USD
req-B: tier=high, cost=0.005600 USD
req-C: tier=high, cost=0.006400 USD
after evidence: total=0.018400 USD, pending=[]
reconciliation delta=0.000000 USD
threshold 2000/2001: 0.004000 / 0.008004 USD
```

### 6. 阶梯、计量时间和正式对账怎样衔接

先确认阶梯到底按单次输入、输出、模式还是账期累计量选档，再确认边界是否包含等号、缓存是否计入选档量，以及是否为全量价或仅超出部分的边际价。**不要把多个请求相加后套单请求长上下文档位。** 示例中全普通输入从 2000 到 2001 时，费用为 0.004000 → 0.008004；若合同是仅超出部分用高价，同样数据会是 0.004004，二者不能混用。这里的 2000 是教学阈值，不是通用“红线”，TPM/RPM 限额档也不自动等于价格档。

实际对账可分三步：

1. **请求级完整性。** 对照发出的 attempts 与最终 usage，找漏采、重复、流中断、自动重试、子 Agent 和缺失供应商 ID；未知行与已确认费用分开展示。原始快照、补证来源和归一化版本可追溯。
2. **同口径汇总。** 按供应商提供的时间桶、项目、模型、服务档和币种对齐请求数及各类别用量。OpenAI Usage API 文档提供聚合桶及 `num_model_requests` 等字段；供应商未提供逐请求明细时，只能确认到其可见粒度，不能强行精确分摊某笔未知请求。
3. **费用与调整项。** 比较本地复算、供应商费用明细和最终账单，分别解释工具/存储等项目、Batch/协议折扣、税费、credit、退款、舍入及迟到入账；不要把所有差异都归为 tokenizer 错误。OpenAI 文档的 Costs 结果与 usage token 聚合是不同对象，应按金额/币种及 line item 核对，不能把请求 Token 小计直接当全部应付额。

本例的 0.018400 只与人为指定的**同口径 Token 费用小计**比较，差额为零不证明真实系统账单已核准。真实差异未查清时应保留未决项，并标明覆盖率与对账截止时间。精度和舍入按合同处理；展示到六位小数，不代表每个服务都在同一层级或精度结算。尤其不要先把每次小额费用舍入到分，再无条件汇总。

只靠本地 tokenizer 估价适合请求前限额，延迟低但不能覆盖完整协议和服务计量；逐次 usage 账本能定位问题，却可能漏最终事件；账单/供应商聚合更适合结算核对，但可能延迟且粒度较粗。生产上通常组合使用，不以其中一个替代另外两个。优化方法可继续看 [agent-0038](agent-0038-reduce-agent-token-cost.md)，质量—成本指标见 [product-0003](product-0003-ai-product-metrics.md)。

## 延伸 / 追问

**追问 1：子 Agent 的费用是不是已经包含在父 Agent 里？**

父 span 的汇总可以包含它，但主 Agent 的某一次 API usage 不会自动代表所有子请求。先区分“聚合展示”和“收费事件”，只累计真实叶子请求，再归属到业务任务，避免父子重复相加。

**追问 2：客户端超时后自动重试，能否只算重试成功的一次？**

不能。第一次可能已在服务端处理，甚至产生了输出；应保留不同 attempt 与物理请求 ID，缺失最终 usage 时待补证。是否实际收费或退款由服务计量和合同决定，不按客户端成功/失败自行猜零。

**追问 3：reasoning_tokens 很大，是否再加到 output_tokens 上？**

在上述 OpenAI Responses 口径下，它已经包含在输出总量中，不再加一次；看不见的模型内部过程与后台额外 API 调用也是两个概念。对账需要计量字段和调用清单，不需要提取隐藏推理正文。

## 常见误区

- **“总 Token 乘一个单价就是真实费用。”** 输入、缓存读写、输出和其他项目必须按类别与适用价表计算。
- **“未知 usage 填 0，成功请求相加即可。”** 这会漏掉中断与重试成本，应报告已知小计和待核实项。
- **“缓存子字段、reasoning 子字段再加一次更保险。”** 总字段可能已经包含它们，重复相加会重复收费。
- **“教学价格就是现价，所有阶梯都是超出部分加价。”** 示例价格与阈值均虚构；实际按模型/服务/时间和合同解释全量价或边际价。

## 参考

- 课程线索：洛小山《AI 产品从入门到精通》learn-ai，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`；[slides/8-1.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/8-1.html)、[slides/8-4.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/8-4.html)、[slides/cost-3.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/cost-3.html)、[slides/cost-4.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/cost-4.html)、[slides/cost-5.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/cost-5.html)、[slides/cost-7.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/cost-7.html)。正文、账本和代码独立编写，未搬运 AGPL 素材；未将课程协议价、调用比例或降本百分比当作现价/普遍规律。
- OpenAI，[Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)，GPT-5.6 and later / Monitor cache performance：Responses 输入及缓存读写子集；[Reasoning models](https://developers.openai.com/api/docs/guides/reasoning)，Managing the context window：输出总量与 reasoning 子计数及 incomplete 情形。
- OpenAI，[Create Chat Completion API reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)，`stream_options.include_usage`；[Organization Usage API reference](https://developers.openai.com/api/reference/resources/organization/subresources/usage)，用量桶、请求数及 Costs 对象。本文只读取公开参考页面，没有调用组织 Usage/Costs API。
- Anthropic，[Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)，Tracking cache performance：三类输入字段的互斥关系；[Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming)：`message_delta.usage` 累计语义。以上 API 文档口径均于 **2026-09-15** 核实；落地须再绑定实际模型 snapshot、接口版本及价格生效日，不能混用 Responses、Chat Completions 和 Messages 的适配器。
