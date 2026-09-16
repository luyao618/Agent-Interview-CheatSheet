---
id: engineering-0028
title: Agent Hook 与 Guard 的拒绝、异常、超时语义怎样定义，怎样防止后续插件撤销拒绝？
category: engineering
tags: [hooks, guard, failure-policy, authorization, audit, cancellation]
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

Agent Hook 与 Guard 的拒绝、异常、超时语义怎样定义，怎样防止后续插件撤销拒绝？请列出允许、拒绝、异常、超时、无效 JSON 的决策表，解释弃权、审计故障和不可绕过的权限边界。

## 答案 · GPT-6

先定义扩展点的职责，再定义故障策略。**观察用 Hook 提供通知；授权用 Guard 提供约束；最终工具网关负责执行门禁。** 这些名称没有跨运行时统一语义，不能看到一个 `before_tool` 回调就认定它可以可靠拦截工具。

一种可解释的契约是：基础授权决定请求是否具备资格，Guard 只能进一步收紧；显式 `deny` 一旦出现就在本次请求内保持，后续 `allow` 或 `abstain` 不能撤销。异常、超时和协议错误分别记录为故障，再按受信策略映射为拒绝或弃权，不能伪装成插件主动允许。权限的一般设计见 [agent-0005](agent-0005-tool-calling-security.md)，扩展不可修改的信任根见 [agent-0054](agent-0054-self-improving-agent-trust-root-boundary.md)；本题聚焦回调之间的故障契约。

### 1. 把决策、聚合与执行放在明确的边界

对一次工具请求，流程是：**固定请求与策略版本 → 基础授权 → 调用选定插件 → 验证响应并分类故障 → 聚合拒绝 → 复核有效权限 → 记录执行前决策 → 执行 → 记录结果**。插件只能收到允许它查看的请求快照，不应拿到可随意改写的聚合状态、执行参数或网关权限。

本题采用三态投票：`allow` 表示该 Guard 的检查通过，`deny` 表示否决，`abstain` 表示不作判断。它们都不是可授予任意权限的令牌。设基础授权为 B、聚合拒绝为 D，初始化 `D = not B`，每个插件响应后执行 `D = D or (vote == deny)`。D 只有 false→true 的变化，拒绝是吸收态。所有 Guard 都弃权时，只有基础授权本来允许、其余强制门槛也满足才可执行。

禁止用“最后一个响应覆盖总响应”，也不能把共享的 `denied` 字段交给插件修改。对于并行 Guard，应在网关持有的状态上归并拒绝，且等所有必需检查得到结论后才能准入；先返回的 allow 不是执行信号。发现 deny 后可以短路，也可以继续收集诊断，但都不能提前执行工具。

每条结论应绑定请求身份、工具、规范化参数以及所用策略/插件版本。参数改写后须重新检查，权限撤销应在实际执行入口生效。示例只用不可变合成请求、串行回调、单事件循环内的权限复核和同步 mock 执行；它不实现真实身份认证、策略世代或跨进程的检查/使用原子性。请求 hash 只用于关联内容，不能认证调用者或策略来源。

### 2. 决策表：fail-open 不会消除显式拒绝

下面是**本文原创 Guard 协议**，不是 Pi、MCP 或其他 SDK 的通用响应格式。假设基础权限已允许，没有其他 Guard 拒绝，执行前必需审计成功；JSON 必须恰好包含一个 `decision` 字段，值为 `allow`、`deny` 或 `abstain`。

| 输入/事件 | 记录的原始结论 | Guard fail-closed | Guard fail-open |
| --- | --- | --- | --- |
| `{"decision":"allow"}` | allow | 投 allow，可继续 | 投 allow，可继续 |
| `{"decision":"deny"}` | deny | 投 deny，禁止执行 | 投 deny，禁止执行 |
| `{"decision":"abstain"}` | abstain | 不增添否决；仍需基础授权 | 不增添否决；仍需基础授权 |
| handler 抛普通异常 | exception 及错误类型 | 合成 deny，禁止执行 | 合成 abstain，标记故障后继续 |
| 到达约定 deadline | timeout | 合成 deny，回收回调后拒绝 | 合成 abstain，回收回调后继续 |
| 无效 JSON / schema | invalid_json | 合成 deny，禁止执行 | 合成 abstain，标记故障后继续 |

空输出、`null`、未知决策、额外字段、重复 key、非有限数字和超长响应都不等于显式弃权。本例限制响应为4096 UTF-8 bytes；这是教学限制，实际大小/嵌套/解析预算由接口约定。**fail-open 只描述故障如何参与决策，不会把 deny 改为 allow，也不会授予基础权限。** 必需 Guard 缺失或未注册也应由可信配置校验拦截，不能通过删除插件把“全部弃权”变成隐式批准；fixture 不实现注册发现。

观察 Hook 的返回值不进入上述投票协议，即使返回一段含 deny 的文本也不否决；其异常和超时仍应可见。需要让某个检查失败就阻止执行时，应明确把它登记为必需 Guard 或强制门槛。反过来，调用方取消本次请求不应被 fail-open 捕获成弃权；本例回收子任务后继续传播 `CancelledError`。插件自行取消则是插件故障，两者不能混淆。

### 3. 策略取舍与固定运行时的差异

| 方案 | 适用条件与收益 | 代价及不适用场景 |
| --- | --- | --- |
| 必需 Guard fail-closed，网关统一持有拒绝状态 | 检查决定高风险工具是否可执行，缺结论就不能建立执行前提；审计归因清楚 | Guard 服务故障会阻断正常工作，需要限时、健康检查及人工恢复。纯可选埋点不宜因此把整个业务关停 |
| 基础授权独立强制，可选检查故障时 fail-open | 辅助评分、提示或非必需观察失败时仍维持可用性；显式 deny 仍有效 | 故障期间失去该检查的保护，必须暴露降级状态。不能用于唯一的权限、审批或强制审计条件 |

失败策略应由受信配置预先决定，记录其来源；出错后临时把 closed 改为 open 属于改变策略，需要相应授权。这里的 Hook/Guard 协议单调性只保证“通过返回值不能撤销 deny”。若插件与宿主共享任意执行能力，仍可能直接调用底层工具、改内存或写文件，必须另外控制能力和执行入口；提示词、事件通知和可观测日志都不是不可绕过的权限边界。

以下为2026-09-16对固定源码的阅读结论，未运行这些产品。检查的是指定函数及类型，不据此推断整个产品的安全属性。

| 固定来源与入口 | 读到的具体语义 | 不能推出的结论 |
| --- | --- | --- |
| Pi v0.57.1，`runner.ts:549–578` 的通用 `emit` | 捕获 handler 异常并调用 `emitError`；特定 session-before 事件可因 `cancel` 提前返回 | 不能把所有扩展入口都称为吞异常，也不能把错误通知等同权限隔离 |
| 同一 Pi 版本，`runner.ts:631–652` 的 `emitToolCall`；`types.ts:851–854` | 顺序等待 `tool_call` handler；遇到 truthy `block` 立即返回，后续插件不再运行。该方法对 handler await 没有局部 catch，拒绝的 Promise 从此处传播；类型含可选 `block`/`reason` | 它不是本文的三态 JSON 协议；仅这些代码不足以断言外层执行、超时回收或所有调用通道都 fail-closed |
| Kubernetes v1.32.0 的 validating webhook，**用作非 Agent 的契约对照** | `failurePolicy` 的 Ignore/Fail 区分调用故障；dispatcher 对 `ErrCallingWebhook` 的 Ignore 分支可继续，但 `ErrWebhookRejection` 仍进入拒绝结果。类型声明 timeout 为1–30秒、默认10秒，failurePolicy 默认 Fail | 不能把 Ignore 理解成忽略显式拒绝，也不能把 Kubernetes 的部署与授权保证移植到 Agent 插件 |

课程提到的其他实现是学习线索；没有在固定一手调用链中证实的产品行为不写成事实。尤其“某个 Hook 会打印错误继续”和“整个运行时允许执行”之间，还隔着调用者、其他门禁与实际工具入口。

### 4. 原创实验：拒绝不可被覆盖，超时必须回收

输入固定为合成主体 `synthetic-reader` 对 `mock.append` 的请求，目标 `mem:demo`。基础权限来自内存 allowlist，执行仅向 `Gate.effects` 列表 append 一条记录。demo 依次运行上表六类事件的 closed/open 两种配置，共12行：closed 的 deny/exception/timeout/invalid_json 四行均为 `denied`；open 只有显式 deny 为 `denied`；其余为 `executed`。这两个状态描述模拟工具是否执行，超时或异常用例预期被拦截不代表插件成功。

另一个测试链是 `deny → 可选 Guard 抛异常（open）→ allow`：三条诊断的 `denied_after` 均为 true，最终 effects 为空。六种 allow/deny/abstain 排列也全部保留拒绝。每个 handler 得到新的嵌套快照，修改自己的参数副本不能影响下一个 handler 或实际执行目标。

deadline 用事件循环的单调时钟计算，demo 配置每个回调20毫秒。`asyncio.wait` 超时不会自动取消任务，本例明确 cancel 后 gather；即使回调吞掉取消并返回迟到 allow，也只回收它，保留已经判定的 timeout。调用方再次取消时也先收集已创建任务，再传播取消。串行链最多8个插件，每个配置 deadline 不超过1秒；**这不是总墙钟硬上限**，合作式取消与清理可能超过 deadline。

fixture 只运行能合作结束的 async mock，没有 CPU 死循环或无限抵抗取消的代码。若要接纳任意插件，必须另有隔离进程/外部有界监督、资源预算和失联处置；仅靠 `asyncio` 无法提供生产硬时限。这里也没有覆盖插件私自派生的任务、真实网络请求或远端副作用回滚。

<details>
<summary>可运行的原创 fixture：合成请求、mock 插件与内存审计</summary>

保存为 `guard_fixture.py`，使用 Python3.11.8 运行 `python3 guard_fixture.py` 即可输出12行决策结果；仅依赖标准库，不需要凭据、真实 Hook 或运行时配置。`required_audit` 和 plugin failure 是本例的可信宿主输入，不从模型响应读取。

```python
# file: guard_fixture.py
"""Original in-memory Hook/Guard model; no real hooks, permissions or business tools."""
import asyncio
from copy import deepcopy
from dataclasses import asdict,dataclass
import hashlib,json,math


@dataclass(frozen=True)
class Request:
    request_id: str = 'synthetic-1'
    principal: str = 'synthetic-reader'
    tool: str = 'mock.append'
    target: str = 'mem:demo'
    value: str = 'synthetic value'

    def __post_init__(self):
        if any(type(v) is not str or not v for v in asdict(self).values()):
            raise ValueError('request fields must be nonempty strings')

    def view(self):
        return dict(request_id=self.request_id,principal=self.principal,tool=self.tool,
                    arguments=dict(target=self.target,value=self.value))

    @property
    def key(self):
        return hashlib.sha256(json.dumps(self.view(),sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Plugin:
    name: str
    handler: object
    kind: str = 'guard'
    failure: str = 'closed'
    timeout_s: float = 0.2

    def __post_init__(self):
        if (not self.name or not callable(self.handler) or self.kind not in ('guard','observer') or
                self.failure not in ('open','closed') or type(self.timeout_s) not in (int,float) or
                not math.isfinite(self.timeout_s) or not 0 < self.timeout_s <= 1):
            raise ValueError('invalid plugin specification')


def parse_vote(text):
    if type(text) is not str or len(text.encode()) > 4096:
        raise ValueError('invalid response size/type')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    def bad_constant(_):raise ValueError('non-finite JSON number')
    data=json.loads(text,object_pairs_hook=unique,parse_constant=bad_constant)
    if type(data) is not dict or set(data)!={'decision'} or data['decision'] not in ('allow','deny','abstain'):
        raise ValueError('invalid decision schema')
    return data['decision']


class Audit:
    def __init__(self, fail_phases=()):
        self.fail_phases=frozenset(fail_phases)
        self.records=[]

    def write(self,event):
        if event['phase'] in self.fail_phases:
            raise OSError('synthetic audit acknowledgement failure')
        self.records.append(deepcopy(event))


class Gate:
    def __init__(self,audit=None,required_audit=True):
        self.audit=audit if audit is not None else Audit()
        if type(required_audit) is not bool or not callable(getattr(self.audit,'write',None)):
            raise ValueError('invalid audit configuration')
        self.required_audit=required_audit
        self.allowed=frozenset({('synthetic-reader','mock.append')})
        self.tasks=[]
        self.collected=[]
        self.effects=[]

    def authorized(self,request):
        return (request.principal,request.tool) in self.allowed and request.target.startswith('mem:')

    async def invoke(self,plugin,request):
        loop=asyncio.get_running_loop()
        finished={}
        async def call():
            try:return await plugin.handler(request.view())
            finally:finished['at']=loop.time()
        deadline=loop.time()+plugin.timeout_s
        task=asyncio.create_task(call(),name='yao387-'+plugin.name)
        self.tasks.append(task)
        fault=None;raw=None;parent_cancelled=False
        try:
            done,_=await asyncio.wait({task},timeout=plugin.timeout_s)
            if task not in done or finished.get('at',math.inf) > deadline:
                fault='timeout'
            elif task.cancelled():
                fault='plugin_cancelled'
            else:
                try:raw=task.result()
                except Exception as exc:fault='exception:'+type(exc).__name__
        except asyncio.CancelledError:
            parent_cancelled=True
        finally:
            if not task.done():task.cancel()
            collector=asyncio.gather(task,return_exceptions=True)
            while not collector.done():
                try:await asyncio.shield(collector)
                except asyncio.CancelledError:parent_cancelled=True
            collector.result()  # consume even a late value/exception; do not change fault
            self.collected.append(dict(name=plugin.name,done=task.done(),cancelled=task.cancelled()))
        if parent_cancelled:
            raise asyncio.CancelledError  # caller cancellation is never an allow/abstain
        if fault is None and plugin.kind=='guard':
            try:vote=parse_vote(raw)
            except (ValueError,TypeError,RecursionError):fault='invalid_json'
        elif fault is None:
            vote='abstain'  # observational output is not a decision protocol
        if fault is not None:
            vote='deny' if plugin.kind=='guard' and plugin.failure=='closed' else 'abstain'
        return dict(plugin=plugin.name,kind=plugin.kind,failure=plugin.failure,
                    outcome=fault or ('observed' if plugin.kind=='observer' else vote),vote=vote)

    def record(self,event):
        try:self.audit.write(event);return True,None
        except Exception as exc:return False,type(exc).__name__

    async def run(self,request,plugins):
        plugins=tuple(plugins)
        if len(plugins)>8 or len({p.name for p in plugins})!=len(plugins):
            raise ValueError('at most eight uniquely named plugins')
        denied=not self.authorized(request)
        rows=[]
        for plugin in plugins:
            row=await self.invoke(plugin,request)
            denied=denied or row['vote']=='deny'  # absorbing: never assign a later allow
            row['denied_after']=denied
            rows.append(row)
        # Recheck current synthetic base permissions after all awaited callbacks.
        denied=denied or not self.authorized(request)
        pre_ack,pre_error=self.record(dict(phase='decision',request_id=request.request_id,key=request.key,
                                           denied=denied,plugins=rows))
        result=dict(request_id=request.request_id,key=request.key,denied=denied,executed=False,
                    audit_decision_ack=pre_ack,audit_result_ack=None,plugins=deepcopy(rows),
                    audit_faults=[] if pre_ack else [dict(phase='decision',type=pre_error)])
        if denied:
            return dict(result,status='denied')
        if self.required_audit and not pre_ack:
            return dict(result,status='audit_blocked')
        # Instant, original mock effect: no await between final gate and this append.
        self.effects.append(dict(request_id=request.request_id,key=request.key,target=request.target))
        result['executed']=True
        post_ack,post_error=self.record(dict(phase='result',request_id=request.request_id,key=request.key,status='mock_done'))
        result['audit_result_ack']=post_ack
        if not post_ack:result['audit_faults'].append(dict(phase='result',type=post_error))
        return dict(result,status='executed' if pre_ack and post_ack else 'executed_audit_failed')


def reply(decision):
    async def handler(snapshot):return json.dumps({'decision':decision})
    return handler


async def broken(snapshot):
    raise RuntimeError('synthetic failure')


async def waiting(snapshot):
    await asyncio.Event().wait()


async def malformed(snapshot):
    return '{broken'


async def demo():
    matrix=[]
    cases=[('allow',reply('allow')),('deny',reply('deny')),('abstain',reply('abstain')),
           ('exception',broken),('timeout',waiting),('invalid_json',malformed)]
    for failure in ('closed','open'):
        for name,handler in cases:
            gate=Gate()
            result=await gate.run(Request(),[Plugin(name,handler,failure=failure,timeout_s=0.02)])
            matrix.append(dict(case=name,failure=failure,vote=result['plugins'][0]['vote'],
                               status=result['status'],effects=len(gate.effects),
                               collected=len(gate.collected)))
    return matrix


if __name__=='__main__':
    print(json.dumps(asyncio.run(demo()),indent=2))
```

</details>

2026-09-16实测：**18 个测试通过**，创建的64个 mock task 全部完成并被收集；测试在调用返回后检查完成状态，teardown 仅断言、不补救取消。覆盖12行决策表、六种投票顺序、基础权限缺失/撤销、观察输出不能投票、JSON 边界、参数副本隔离、迟到 allow、插件自行取消、调用方取消与重复取消，以及下节的审计故障。唯一合成输入文件逐字节未变，专属临时目录已移除。源码阅读、fixture 合同测试和真实运行时集成验证是不同证据层级，本次没有后者。

### 5. 审计失败不能改写已经发生的事

建议决策事件至少关联请求、插件和策略版本、原始故障、映射后的投票与最终结果；按权限控制和脱敏规则记录参数，不能为排错倾倒秘密。执行前记录说明“依据什么准备执行”，执行后记录说明“知道发生了什么”，两者不可混用。观察 Hook 丢日志与强制审计存储不可用也应分别建模。

| 故障时点 | 本例返回和 effects | 结论与处置边界 |
| --- | --- | --- |
| 必需 decision 审计失败，尚未执行 | `audit_blocked`，executed=false，0条 effect | 缺少必需审计确认，禁止新执行；不是声称业务操作已回滚 |
| 非必需 decision 审计失败 | 无其他否决时为 `executed_audit_failed`，1条 effect；有 deny 仍为 denied | 可用性策略允许继续，但必须保留 audit_faults，不得报告完整审计成功 |
| result 审计失败，mock effect 已发生 | `executed_audit_failed`，executed=true，1条 effect | 拒绝下一次调用无法撤销过去；需状态核对、幂等键或业务补偿，不能自动安全重试 |
| 审计先 append，再抛“确认丢失” | `audit_blocked`，decision ack=false，但内存已有1条审计记录 | 未获确认不等于未写入；按关联 ID 核对，不能补造不存在的执行结果 |

这里 `Audit` 是会立即返回或抛错的受信同步内存 sink；并非持久日志服务，也不执行任意重入回调。若换成异步、可能阻塞或能改权限的 sink，需要独立的写入预算、失败传播与执行前身份/策略复核，不能照搬“中间无 await”的局部条件。若请求在插件阶段被外层取消，本例只回收并传播取消，不生成最终审计行；需要完整取消/崩溃审计的产品还必须在外层记录请求生命周期。

测试有意展示 result 审计失败后对同一请求再调用一次会得到2条 mock effect：此 fixture **没有幂等性或 exactly-once 保证**。它也不证明生产持久性、审计服务可用性、真实主体身份或远端事务回滚。响应中的 audit_faults 只是本地可见诊断，不保证故障报告自身已成功送达运维系统。

## 追问

**追问：一个 Guard 拒绝后，后续插件有管理员权限，可以返回 allow 撤销吗？**

不能通过同一轮返回值覆盖。若业务允许人工覆盖，应走独立、受权且可审计的策略变更/新请求流程，绑定新决策依据；否则插件顺序就变成权限提升通道。是否允许这种覆盖由强制策略决定。

**追问：为什么不让 Guard 只返回 deny 或 abstain？**

这是合理的收紧型接口：基础授权负责正向许可，Guard 只否决。本文额外保留 allow 方便诊断“检查明确通过”，但聚合时 allow 与 abstain 都不能授予基础权限；缺输出仍是协议故障，不能偷换成弃权。

**追问：超时后回调仍在运行，fail-open 能先执行吗？**

需要先界定回调能否产生副作用、是否还可能修改共享状态以及谁负责回收。本文等自建任务收集完再返回；生产中可在隔离边界撤销其能力或交给受监督生命周期管理，但不能一边遗留可写回调，一边宣称门禁已结束。超时本身也不证明远端操作取消。

**追问：记录过一次 allow，重试同一请求能直接使用吗？**

不能默认复用。主体、参数、权限、策略世代和审批范围可能变化；旧 allow 也不说明工具是否已经执行。先区分授权有效性与业务幂等性，再决定重新评估、状态查询或补偿。

## 常见误区

- **“可观测 Hook 就是不可绕过的权限边界。”** 是否强制经过、能否绕到其他执行入口、插件能否改策略，需要独立证明；有日志只能说明观察到某条路径。
- **“各运行时 Hook 同名，所以异常语义相同。”** 同一 Pi 版本的不同入口已有差异，应追踪固定函数、外层调用链和配置。
- **“fail-open 会放过显式 deny，异常就是 allow。”** 故障映射和显式决策不同，弃权也不是授权。
- **“把 deny 存在共享对象里就能保持单调。”** 后续插件可以改写共享字段；拒绝状态应由可信聚合器持有。
- **“超时等于资源释放，审计失败等于操作没发生。”** 任务需回收，副作用需核对；迟到 allow 和结果日志故障都不能改写已确认的事实。

## 参考

以下来源核对于2026-09-16；题干、答案与 fixture 独立编写。课程只作学习线索，未搬运 AGPL 正文、代码或图片。

- 洛小山《AI 产品从入门到精通》，learn-ai 固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/12-19.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/12-19.html)、[slides/dsh-12.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-12.html)、[slides/codex-25.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-25.html)，分别提供扩展点、Guard 与故障处理的学习线索。[LICENSE](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/LICENSE) 为 AGPL-3.0。
- Mario Zechner / Pi **v0.57.1**，固定 commit `a9cedccdde77e9d765303463d8a6cd11c58f7a7f`：[runner.ts](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/coding-agent/src/core/extensions/runner.ts) 的 `emit`（549–578）与 `emitToolCall`（631–652）；[types.ts](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/coding-agent/src/core/extensions/types.ts#L851-L854) 的 `ToolCallEventResult`。[MIT LICENSE](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/LICENSE)。本文仅据这些入口比较响应及局部异常传播，没有运行 Pi 或证明外层安全隔离。
- Kubernetes **v1.32.0**，tag 解析到 commit `70d3cc986aa8221cd1dfb1121852688902d3bf53`：[admissionregistration/v1/types.go](https://github.com/kubernetes/kubernetes/blob/70d3cc986aa8221cd1dfb1121852688902d3bf53/staging/src/k8s.io/api/admissionregistration/v1/types.go#L805-L901) 的 `ValidatingWebhook` failurePolicy 与 timeout；[validating/dispatcher.go](https://github.com/kubernetes/kubernetes/blob/70d3cc986aa8221cd1dfb1121852688902d3bf53/staging/src/k8s.io/apiserver/pkg/admission/plugin/webhook/validating/dispatcher.go#L199-L228) 区分调用故障与显式拒绝，277–280行为 context 设置 timeout。[Apache-2.0 LICENSE](https://github.com/kubernetes/kubernetes/blob/70d3cc986aa8221cd1dfb1121852688902d3bf53/LICENSE)。这是非 Agent 的契约对照，并非宣称 Agent 使用 Kubernetes 的实现。
- CPython **v3.11.8**：[asyncio-task.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/asyncio-task.rst)，`Task Cancellation`、`shield`、`wait_for`、`wait` 说明取消传播、等待清理及 `wait` 超时不自动取消的差异。[LICENSE](https://github.com/python/cpython/blob/v3.11.8/LICENSE) 含 PSF License Version 2、历史许可及文档示例的 Zero-Clause BSD 条款；本题代码为原创，未复制文档示例。
