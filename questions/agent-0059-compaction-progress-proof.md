---
id: agent-0059
title: 上下文压缩后仍溢出时，如何证明重试取得了进展，并区分 UI 占用率与下一次请求预算？
category: agent
tags: [compaction, context-window, token-budget, progress, retry, observability]
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

上下文压缩后仍溢出时，如何证明重试取得了进展，并区分 UI 占用率与下一次请求预算？如果压缩器返回成功但内容不变，随后切换到更大窗口模型，系统应怎样行动？

## 答案 · GPT-6

让运行时给每次请求建立可核对的快照，并在提交压缩替换后重新组装、计量请求。允许恢复的依据应是**实际条件改变且新的预算检查成立**：例如一次确实减小输入的替换，或一次获授权、重新计量后可用的模型切换。压缩函数返回 `success` 只说明它报告成功；旧 UI 百分比只描述某个过去的观测，都不能单独证明继续重试会前进。

信息保留、工具台账与缓存取舍见 [agent-0043](agent-0043-kv-cache-friendly-context-compression.md)，长期记忆分层见 [agent-0023](agent-0023-long-context-memory-module.md)。本题关注压缩恢复循环如何终止，以及怎样解释当前请求的预算；Token 减少不证明摘要语义正确，信息完整性仍要单独验收。

### 1. 压缩触发与进展凭证

**主动压缩**发生在请求前：当前请求预计逼近窗口或下一次工具结果没有足够余量时，提前压缩。它能减少可预见的溢出，但依赖计量准确性。**被动压缩**是在已确认的 context overflow 后恢复：先把错误关联到失败请求的模型、输入世代与请求身份，再决定是否压缩或换模型。限流、认证失败、网络超时和取消有自己的处理方式，不能仅因“模型调用失败”就压缩并重发。

进展凭证至少有三个层次：

- **替换确实提交**：记录压缩前的内容摘要、请求快照及 `replacement_generation`；只有运行时实际替换模型可见历史后，才递增世代。本例对 no-op 和没有减量的候选先拒绝，世代不变；世代不是压缩尝试次数。
- **对同一口径有正向变化**：在相同模型、tokenizer、序列化器与预算规则下比较替换前后的完整输入计数，要求 `ΔI = I_before − I_after > 0`。只有字节变化或世代增加，仍可能得到更长的摘要，不能充分证明容量改善。
- **下一步确实可规划**：替换后重新检查当前请求和余量。减了 1 个 Token 仍然超限也算一次真实减量，却不足以发送；只能在剩余恢复预算内再采取动作，否则熔断。

压缩提案还必须匹配它读取的原请求快照。若期间用户插话、工具定义或模型发生变化，不能把旧提案覆盖到新上下文。本例在本地锁内比较请求 key 并提交；key 包含世代、完整输入、模型/encoding/版本和预算。hash 用于本地比对，不认证压缩插件身份，也不证明持久化成功。

### 2. 当前请求、未来余量与 UI 各算什么

| 数量 | 来源与口径 | 用途与限制 |
| --- | --- | --- |
| `I`：本次输入 Token 估计 | 组装**即将发送**的系统指令、事实、历史、工具 schema、最新输入及包装后计量；记录 tokenizer、serializer、模型版本 | 请求准入和压缩决策；不是只数历史文本。本地编码器不知道供应商全部隐藏包装或多模态规则 |
| `O`：本次输出预留 | 当前模型/API 的输出参数及上限；适用时还要核对 reasoning 是否计入同一额度 | 要同时满足该模型的单次输出限制，不能机械沿用上一模型的参数 |
| `S`：估计误差余量 | 本次计量方案的保守余量 | 降低低估风险；任何固定余量都不是供应商接纳保证 |
| `T`：未来工具结果余量 | 下一步工具结果及其包装的受控上界或规划额度 | 此时尚未生成，**不重复算入当前输入 I**；结果真的到达后重新计量，不能继续沿用旧估计 |
| UI 百分比/最近 usage | 已完成请求的统计或投影，带请求身份、模型、窗口、观测时点 | 用来展示并标记 stale/unknown；不要把旧 numerator 除以新模型窗口后当成当前请求测量 |

在“输入与输出共享一个上下文窗口”的**本题假设**下，令窗口为 `C`，当前本地预算条件为 `I + O + S ≤ C`；额外保留工具余量的主动规划条件为 `I + O + S + T ≤ C`。定义 `headroom = C − I − O − S`，前者要求 `headroom ≥ 0`，后者要求 `headroom ≥ T`。等号允许；未知或非正窗口应报口径错误，不能用 UI 的 0% 表示安全。

这只是给预计增长留空间。下一步还要计入已生成的 assistant 消息和下一次输出预留，T 本身不保证下一步完整请求可用；每个请求边界都要重新检查。

fixture 把规划条件作为自动准入门槛。产品也可以选择在当前请求满足硬预算时继续，同时严格限制后续工具增长；这是不同的恢复策略，应明确记录。

不同产品的输入/输出上限、reasoning、图片、工具协议包装和 cache usage 口径必须单独适配。不要把累计账单 Token 或 cached input 的优惠数量从上下文占用中随意扣除。模型切换时，窗口、tokenizer、输出上限、输出预留和误差余量一起重新确认；更大窗口并不保证旧配置有效，也不保证更便宜。

| 恢复方案 | 适用条件与收益 | 代价及不适用场景 |
| --- | --- | --- |
| 压缩或外置历史 | 历史存在冗余，关键约束和工具台账能保留；可降低后续输入体积 | 有摘要开销和信息损失风险。若主因是巨大工具 schema、固定指令或刚到达的工具结果，反复压旧历史可能无用 |
| 切换更大窗口模型 | 已有切换授权，任务、工具协议和模型能力兼容，重算后确有余量 | 可能提高成本/延迟，改变 tokenizer 与输出规则。新窗口仍不足、缺授权或能力不兼容时不能强行切换 |

无论采用哪种方案，都应限制恢复次数、压缩自身的 Token/墙钟预算、模型切换次数和总耗费。本例一个恢复 episode 最多调用压缩器 **2 次**、切换模型 **1 次**；相同请求 key 不重复调用压缩器，切换不重置计数，无可用恢复路径时进入熔断并停止自动准入。明确的用户修订或新任务可以由 host 创建新的 episode，不能把每次失败自动当成“重新开始”。若供应商再次拒绝，即使本地显示可容纳，也要保留这次拒绝事实。

### 3. 示例：no-op 成功之后切换窗口

以下是2026-09-16实际运行原创 fixture 的结果。上下文全部合成，两个模型只是 **mock-small/mock-large** 标签，窗口和预留数是教学配置，**不是这些 encoding 所对应真实模型的规格**。tiktoken 固定为0.9.0；本例只对 `synthetic-json-v1` 完整 JSON 包装编码，未模拟供应商真实 Chat Template，也未调用模型。

合成历史是 `步骤记录：查找合成文档，保留任务结论，继续分析。 item alpha beta.` 加换行，重复35次；固定 system/facts、read_mock 工具 schema 和当前 user 文本见下面代码。上一条 UI 观测为虚构的 `300 / 1024 = 29.296875%`，其 request key 与当前请求不匹配。

| 状态 | 世代与计量 | 本地判断 |
| --- | --- | --- |
| mock-small 请求 | `g=0`；cl100k_base 得 `I=1231`；`C=1024, O=200, S=24, T=300` | `headroom=1024−1231−200−24=−431`，当前请求已超预算；旧 UI 29.30% 是 stale |
| 压缩器返回 success=true，历史原样返回 | `g` 仍为0，内容和请求 key 不变，`I` 仍为1231 | 记录 `no_content_change`；不能因成功返回而重发原请求 |
| host 使用预授权 mock-large 合同 | `g=0`；改用 o200k_base 重算得 `I=914`；`C=2048, O=256, S=32, T=300` | `headroom=2048−914−256−32=846≥300`，返回 `local_budget_ready` |
| 若新请求又收到模拟 overflow | 错误关联到新请求 key；压缩仍 no-op，计数不因切换归零 | 用完剩余压缩预算后返回 `circuit_open`；本地 fit 不能抹掉已知拒绝 |

这里发生的是**模型合同变化后的容量恢复**，没有发生压缩替换；1231→914 还换了 tokenizer，不能把317计为压缩节省量。旧 UI 继续显示旧观测并标记 stale，不参与 gate。旧模型的迟到溢出错误也不能归到新模型请求上；缺少或不匹配的失败请求 key 在本例返回 `stale_overflow`。

若不提供允许的 fallback，no-op 后立即熔断；若把 mock-large 窗口改成1100，即便比1024大，重算后仍不足，也要熔断。真正短摘要会提交替换并推进世代；测试另外覆盖了连续两次各减1 Token但仍超限的情况，第三次不能继续压缩。

<details>
<summary>可运行的原创 fixture：公开 tokenizer 数据预取，随后只读本地缓存</summary>

使用 Python3.11.8、`tiktoken==0.9.0`。把两个代码块分别保存为对应文件，先运行 `python3 prefetch_tokenizers.py`，再运行 `python3 compaction_fixture.py`。前者仅下载公开 tokenizer 数据到脚本旁的专属 `tokenizer-cache`，不调用模型；后者禁止 pinned tiktoken 的 cache-miss 读取路径，缺缓存会报错。无需 API key。

```python
# file: prefetch_tokenizers.py
"""Fetch only public tokenizer data into this fixture's dedicated cache."""
import hashlib,json,os
from pathlib import Path
import tiktoken
ROOT=Path(__file__).resolve().parent
cache=ROOT/'tokenizer-cache'
os.environ['TIKTOKEN_CACHE_DIR']=str(cache)
for name in ('cl100k_base','o200k_base'):
    tiktoken.get_encoding(name)
rows=[dict(file=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
      for p in sorted(cache.iterdir()) if p.is_file()]
(ROOT/'tokenizer-cache-manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
print('Prepared public tokenizer cache:',len(rows),'files; no model call')
```

```python
# file: compaction_fixture.py
"""Original local budget planner. No provider call, real session or runtime config."""
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib,json,os
from pathlib import Path
from threading import RLock
from unittest.mock import patch
import tiktoken


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_encoders():
    os.environ['TIKTOKEN_CACHE_DIR'] = str(Path(__file__).resolve().parent/'tokenizer-cache')
    # Pinned tiktoken loader uses read_file only on a cache miss; forbid that path.
    with patch('tiktoken.load.read_file', side_effect=RuntimeError('prefetch tokenizer data first')):
        return {n: tiktoken.get_encoding(n) for n in ('cl100k_base', 'o200k_base')}


@dataclass(frozen=True)
class Contract:
    model: str
    encoding: str
    window: int
    max_output: int
    output: int
    tool_margin: int
    safety: int
    revision: str = 'mock-v1'

    def __post_init__(self):
        values=(self.window,self.max_output,self.output,self.tool_margin,self.safety)
        if (any(type(v) is not int or v < 0 for v in values) or
                self.window == 0 or self.max_output == 0 or self.output == 0 or
                self.output > self.max_output):
            raise ValueError('invalid budget contract')


SMALL=Contract('mock-small','cl100k_base',1024,256,200,300,24)
LARGE=Contract('mock-large','o200k_base',2048,512,256,300,32)
HISTORY='步骤记录：查找合成文档，保留任务结论，继续分析。 item alpha beta.\n' * 35


@dataclass(frozen=True)
class Proposal:
    success: bool
    source_key: str
    history: str


class Planner:
    def __init__(self, encoders, history=HISTORY, contract=SMALL, max_compactions=2):
        if type(max_compactions) is not int or not 0 <= max_compactions <= 10:
            raise ValueError('invalid recovery limit')
        if contract.encoding not in encoders:
            raise ValueError('unknown encoding')
        self._lock=RLock()
        self.encoders=encoders
        self.history=history
        self.contract=contract
        self.generation=0
        self.user='请根据合成记录继续。'
        self.tools=[{'name':'read_mock','description':'Read a synthetic document.',
                     'inputSchema':{'type':'object','properties':{'id':{'type':'string'}}}}]
        self.fixed={'system':'Use only synthetic data.', 'facts':'decision_id=F7; no external actions.'}
        self.max_compactions=max_compactions
        self.compactions=0
        self.switches=0
        self.attempted=set()
        self.rejected=set()
        self.circuit=False
        self.events=[]

    def meter(self, history=None):
        with self._lock:
            c=self.contract
            payload=canonical(dict(**self.fixed, history=self.history if history is None else history,
                                   user=self.user,tools=self.tools,serializer='synthetic-json-v1'))
            tokens=len(self.encoders[c.encoding].encode(payload, disallowed_special=()))
            headroom=c.window-tokens-c.output-c.safety
            return dict(key=digest(dict(payload=payload,contract=asdict(c),generation=self.generation)),
                        generation=self.generation, model=c.model, encoding=c.encoding,
                        input_tokens=tokens,window=c.window,output=c.output,safety=c.safety,
                        tool_margin=c.tool_margin,headroom=headroom,
                        request_fit=headroom >= 0,planning_fit=headroom >= c.tool_margin)

    def change_user(self, text):
        with self._lock:
            self.user=text  # models a new host input arriving while a proposal is being made

    def compact_once(self, compactor):
        with self._lock:
            before=self.meter()
            if self.circuit or self.compactions >= self.max_compactions or before['key'] in self.attempted:
                self.events.append({'event':'compaction_limit'})
                return False
            self.compactions += 1
            self.attempted.add(before['key'])
            source_history=self.history
        try:
            proposal=compactor(source_history,before['key'])  # bounded, trusted local mock
        except Exception as exc:
            self.events.append({'event':'compactor_error','type':type(exc).__name__})
            return False
        with self._lock:
            if (not isinstance(proposal,Proposal) or type(proposal.success) is not bool or
                    not proposal.success or type(proposal.history) is not str):
                self.events.append({'event':'invalid_or_failed_proposal'})
                return False
            if proposal.source_key != before['key'] or self.meter()['key'] != before['key']:
                self.events.append({'event':'stale_proposal'})
                return False
            if proposal.history == source_history:
                self.events.append({'event':'no_content_change','generation':self.generation})
                return False
            after=self.meter(proposal.history)
            if after['input_tokens'] >= before['input_tokens']:
                self.events.append({'event':'no_token_reduction'})
                return False
            self.history=proposal.history
            self.generation += 1  # only committed, reducing replacement advances this counter
            self.events.append(dict(event='replaced',generation=self.generation,
                                    before=before['input_tokens'],after=after['input_tokens']))
            return True

    def prepare(self, compactor, cause='proactive', fallback=None, failed_key=None):
        # A single recovery driver calls prepare; callback may update user through the lock.
        if cause not in ('proactive','context_overflow'):
            return self.result('not_context_overflow')
        if self.circuit:
            return self.result('circuit_open')
        if cause == 'context_overflow':
            if failed_key != self.meter()['key']:
                return self.result('stale_overflow')
            self.rejected.add(self.meter()['key'])
        for _ in range(self.max_compactions + 1):
            m=self.meter()
            if m['planning_fit'] and m['key'] not in self.rejected:
                return self.result('local_budget_ready')
            if not self.compact_once(compactor):
                break
        # fallback is supplied by the trusted host as a preauthorized fictional contract.
        if fallback is not None and self.switches < 1:
            with self._lock:
                if fallback.encoding in self.encoders and fallback.window > self.contract.window:
                    previous=self.contract.model
                    self.contract=fallback
                    self.switches += 1
                    self.events.append(dict(event='model_switched',previous=previous,
                                            current=fallback.model,generation=self.generation))
        m=self.meter()  # different encoding, output reserve and denominator must all be re-read
        if m['planning_fit'] and m['key'] not in self.rejected:
            return self.result('local_budget_ready')
        self.circuit=True
        return self.result('circuit_open')

    def result(self, status):
        return dict(status=status,meter=self.meter(),compactions=self.compactions,
                    switches=self.switches,events=deepcopy(self.events))

    def ui_view(self, previous):
        m=self.meter()
        return dict(last_percent=(100*previous['tokens']/previous['window'])
                    if previous['window'] > 0 else None,
                    stale=previous['key'] != m['key'] or previous['model'] != m['model'],
                    source='synthetic_previous_usage')


def no_op(history, key):
    return Proposal(True,key,history)


def demo(encoders):
    p=Planner(encoders)
    before=p.meter()
    previous=dict(key='previous-request',model=SMALL.model,window=1024,tokens=300)
    ui_before=p.ui_view(previous)
    result=p.prepare(no_op,cause='context_overflow',fallback=LARGE,failed_key=before['key'])
    return dict(before=before,ui_before=ui_before,result=result,ui_after=p.ui_view(previous))


if __name__ == '__main__':
    print(json.dumps(demo(load_encoders()),ensure_ascii=False,indent=2))
```

</details>

### 4. 真实验证的范围

CPython3.11.8 / tiktoken0.9.0 上的原创 `test_compaction.py` **17个测试通过**。覆盖 no-op、同 Token 数的不同文本、膨胀候选、失败/异常/非法提案、真实替换与固定部分不变、减量仍超限、过期提案、压缩中新增输入、工具 schema 增长、工具余量与当前预算的区别、等号边界、输出限制、模型切换重计量、旧模型迟到错误、二次 overflow 与计数不重置、非上下文错误和过期 UI。

测试只对合成输入操作；一项文件测试在专属临时目录写入合成历史，核对前后文件字节和集合未变化，并确认目录删除。两个公开 BPE 缓存文件的 SHA-256 与 tiktoken0.9.0 固定源码中的 expected_hash 一致，测试加载时阻止 cache-miss 下载。**收费模型调用数为0**；所有压缩与 overflow 都是本地 mock，不是供应商观测。

本例支持单个恢复驱动，锁仅保护本地快照比较和替换；没有验证多进程持久化、崩溃恢复、真实供应商准入或摘要语义质量。压缩器是即时且有界的原创函数，计数上限不能中断真实阻塞函数；生产还需独立的 deadline/取消监督和费用控制。`local_budget_ready` 只表示本地规划条件满足，不能当成实际请求已发送、已被接纳或已成功。

## 延伸 / 追问

**追问：为什么不能只看替换世代增加？**

世代证明运行时提交了一次替换；候选可能等长、更长，或丢了关键语义。还要在同一计量合同下验证 Token 改善并检查最终预算，语义与工具台账完整性另行验收。本例对无减量候选不提交，因而不会推进世代。

**追问：切换模型后 UI 从90%变成45%，能否直接重试？**

不能据此决定。比例降低可能只因为分母变大；应重新组装请求、确认 tokenizer/输出参数并计量。错误与 usage 必须绑定原请求，旧模型事件不能自动应用到新模型。

**追问：当前请求放得下，但下一个工具返回可能非常大，怎么办？**

提前留出 T，并给工具返回设置截断、分页或外置读取契约。T 是规划余量，不是无限扩容；返回到达后加进实际输入重新测量，不把 T 和该返回重复相加，也不因为只保留短 UI 文本就假设模型输入也变短。

**追问：已明显压短且本地 fit，供应商还报 overflow 呢？**

先核对供应商、具体模型版本、输入/输出/reasoning 与包装口径，保留拒绝对应的请求 key。在剩余恢复预算内修正计量或换获准模型；无法证明新的恢复条件就熔断。不能靠把同一个 key 的“成功压缩”再报告一次来无限重试。

## 常见误区

- **“压缩器成功返回就证明有进展。”** 需要实际提交、同口径减量和预算复查；no-op 不提供重试凭证。
- **“UI 占用率低就可以发送。”** 过期 usage、投影和新窗口可能不属于同一请求，必须标注来源并单独计量。
- **“换成大窗口后沿用原 Token 数和输出预留。”** tokenizer、输入包装和输出限制可能同时改变，必须重算；跨 tokenizer 差值不叫压缩率。
- **“给重试加次数上限就保证了硬时限与费用。”** 次数限制阻止循环增长，阻塞调用仍需监督，实际费用仍需对应计费口径。
- **“输入变短就等于答案质量、权限和供应商接纳都得到保证。”** 本题的进展证明只管可测的容量和有界恢复，其他保证各有独立证据。

## 参考

以下来源核对于2026-09-16；正文和实验均独立编写。课程是学习线索，未将其项目判断、阈值或数字当作通用产品保证，没有搬运 AGPL 正文、代码或图片。

- 洛小山《AI 产品从入门到精通》，learn-ai 固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/dsh-4.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-4.html)（主动/被动与世代线索）、[slides/dsh-9.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-9.html)（请求计量与 UI 投影）、[slides/12-11.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/12-11.html)（阈值边界与余量）。[LICENSE](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/LICENSE) 为 AGPL-3.0，只作链接与独立讨论。
- Mario Zechner / Pi **v0.57.1**，固定 commit `a9cedccdde77e9d765303463d8a6cd11c58f7a7f`：[agent-session.ts](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/coding-agent/src/core/agent-session.ts) 的 `_checkCompaction`（1673起）区分 threshold/overflow，检查同模型及压缩边界，并限制 overflow 恢复；`_runAutoCompaction`（1837附近）先记录和重建消息再发送完成事件；`getContextUsage`（2925起）在缺少压缩后 usage 时返回 null。[compaction.ts](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/coding-agent/src/core/compaction/compaction.ts#L209-L215) 的 `shouldCompact` 给出这个版本的具体阈值比较。以上为源码阅读，未运行 Pi；本文的世代/单调减量门禁是原创教学策略，不声称 Pi 使用同一算法。[MIT LICENSE](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/LICENSE)。
- OpenAI / **tiktoken0.9.0**，tag 对应固定 commit `e35ab0915e37b919946b70947f1d0854196cb72c`：[core.py](https://github.com/openai/tiktoken/blob/e35ab0915e37b919946b70947f1d0854196cb72c/tiktoken/core.py) 的 Encoding.encode；[openai_public.py](https://github.com/openai/tiktoken/blob/e35ab0915e37b919946b70947f1d0854196cb72c/tiktoken_ext/openai_public.py#L75-L120) 定义 cl100k_base/o200k_base 及词表数据校验哈希；[load.py](https://github.com/openai/tiktoken/blob/e35ab0915e37b919946b70947f1d0854196cb72c/tiktoken/load.py#L32-L83) 说明缓存命中与校验路径。[MIT LICENSE](https://github.com/openai/tiktoken/blob/e35ab0915e37b919946b70947f1d0854196cb72c/LICENSE)。库提供编码计数，不提供本例虚构模型的窗口规格或供应商准入保证。
