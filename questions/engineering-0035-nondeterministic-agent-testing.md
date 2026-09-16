---
id: engineering-0035
title: 如何测试非确定性的 Agent 运行时，让回放、故障注入与性质测试各自覆盖真实风险？
category: engineering
tags: [runtime-testing, deterministic-replay, fault-injection, property-testing, streaming]
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

如何测试非确定性的 Agent 运行时，让回放、故障注入与性质测试各自覆盖真实风险？请为重复 block-end、缺 block-start、工具超时选择测试层，并说明怎样发现分片顺序、取消竞态及测试断言自身的问题。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**先固定可控的外部输入和调度条件，再用独立的预期结果与状态不变量检查运行时；不能要求真实模型每次说同一句话，也不能只重放几条成功轨迹。** 运行时协议是否正确、模型决策质量如何、真实服务能否接通，是不同的测试目标。

[engineering-0013](engineering-0013-llm-as-judge-bias-calibration.md) 讨论 Judge 校准，[engineering-0014](engineering-0014-agent-benchmark-leakage-resistant-evaluation.md) 讨论评估数据污染，[agent-0032](agent-0032-parallel-tool-calling.md) 讨论并行一致性。本题测试协议与时序，不用一次模型评分或 benchmark 分数代替这些检查；流内执行的收尾机制另见 [engineering-0026](engineering-0026-streaming-tool-transcript-closure.md)。

### 1. 固定的不只是模型文本，还包括时间和边界

| 不确定性来源 | 可重复测试怎样控制 | 需要保留的证据 |
| --- | --- | --- |
| provider 响应与协议形状 | 固定 raw response/SSE fixture；保留外部字段名与版本，不先转换成自己喜欢的内部对象 | 原始字节、fixture hash、协议/adapter 版本、独立标注的预期计划 |
| 工具返回、错误和副作用 | 用有约束的 mock 返回值/异常，并在派发处记录调用 ID 与次数 | 输入、结果、错误类别、派发次数；断言实际 mock 状态而非 Agent 的“成功”文案 |
| 时间、重试、随机值 | 注入虚拟 clock、固定随机 seed、ID/generation；等待点用 barrier/Event 控制 | 时间单位、deadline 边界、事件顺序和 seed；不能只说“加了 sleep” |
| 并发完成与取消 | 在特定切点释放结果、触发 timeout/cancel，检查每步不变量 | 第一份终态、迟到回调处置、任务 done/结果消费/资源释放记录 |

“生产格式 fixture”说的是外部契约形状，不要求读取生产日志。本题用固定 Anthropic Python SDK v1.6.0 的 raw event 类型命名组织原创合成 SSE，所有 ID、工具名、参数、usage 和 model 都是虚构值。golden 文件直接写成外部字节，预期参数另写为 `{"q":"茶","n":12}`，不是先用被测序列化器生成输入，再用同一份逻辑生成答案。

真实系统若有经过授权、脱敏的录制样本，可补充真实 SDK/网关产生的格式变化；也要保留独立 oracle 和负例。不能因为一份 fixture 来自真实录制就认为其中所有行为都正确，更不能把生产日志中的秘密搬进测试。本次没有读取生产日志、用户会话或凭据。

### 2. 三个例子分别放在哪一层

| 用例与输入 | 首选层及关键步骤 | 应断言什么 |
| --- | --- | --- |
| `start → delta → end → end` | block 组装器的状态机单测；再把重复 `content_block_stop` 插入外部 SSE 做 adapter 契约测试 | 本例严格策略报 `duplicate_stop`，整份计划不可交付；不能生成两份相同调用。若某产品支持重投递，必须先定义有身份/世代的去重契约，不能看到同名 end 就盲目吞掉 |
| 没有 start 却出现 delta 或 end | 非法轨迹/负面 fixture；从字节解码到 block 状态过一遍 | 报 `missing_start`，不得补造空 block、假调用 ID 或默认参数；半截消息不能假装完整。只测已构造好的内部 block 对象会漏掉这一层 |
| 工具超时，随后结果或取消到达 | 虚拟时钟下的 lease/调度器集成测试，加实际协作式 mock task 的取消/drain 检查 | deadline 后到达的结果不能变成功；终态只接受一次，旧 generation 不改变新任务；timeout/cancel 后 task 已结束、异常已消费、资源已释放，而非只设置一个 timeout 标志 |

deadline 取舍要提前写清。本例用逻辑 tick：开始在 t=4，deadline=5，只有 `t<5` 的当前 generation 结果可成功；结果恰在 t=5 到达，即使 timeout 回调还没执行，也归为 timed_out。这个选择是教学 host 契约，不是供应商或 asyncio 默认时限语义。

取消竞态也不能只跑一次顺序。对 result、timeout、cancel 的六个排列，本例用显式 oracle 指定“第一份合法终态保持不变”，逐步断言终态记录不超过一条。在一个真实系统里，若选择别的优先级，测试要验证那份契约，而不是把偶然调度顺序当规范。

### 3. 回放、故障注入与性质测试互相补什么

| 方法 | 适合与收益 | 代价及不能替代的检查 |
| --- | --- | --- |
| 固定 trace 回放 / golden | 将已知输入下的解析、组装和决策变成稳定回归，便于定位版本变化 | 样本窄，容易把旧 bug 固化为正确答案；不能覆盖未录到的顺序、重试或真实服务可达性 |
| 故障注入 / 受控调度 | 明确制造缺帧、重复 end、超时、取消、异常及迟到回调；定位失败边界 | 切点若绕开真实入口，可能只测 mock；内存抛异常不证明真实 HTTP reset、TLS、重连或 OS 清理正确 |
| 性质测试 / 小状态空间枚举 | 生成多种数据/动作序列，用独立模型或 invariant 检查，保存最小反例 | 不变量可能写错，输入域/步骤上限仍有限；固定 seed 不冻结 provider、系统时间或全部线程调度 |
| 少量真实端到端评测 | 补真实 SDK、协议版本、部署、权限和模型行为的集成证据 | 有费用与波动，需要隔离数据/额度及稳定副作用验证；不适合替代每次提交的确定性边界测试，本次未执行 |

字节分片与逻辑事件乱序要分开。对同一条有序字节流，在 UTF-8 字符、SSE 行或 JSON 字段中间切开，解码结果应不变。单条有序传输不会因为分包就自动打乱字节；“把 delta 换顺序”应标为应用队列/回调故障或额外协议场景，不能随意当合法传输。

一个有用的反例是：参数分片为 `{"n":`、`1`、`2`、`}` 时得到 12；交换中间两个分片仍是合法 JSON，却得到 21。没有序号、原始顺序凭证或更强语义约束，block 生命周期检查无法识别这个变化。本例测试明确记录这种局限，不宣称“所有乱序都被拒绝”。生产中若需要恢复乱序，应在已定义的排序/世代边界验证，而不是按内容猜顺序。

### 4. 一组可复跑的原创建模与反例

下面两份文件用于 Python3.11.8。本例只支持一条有工具调用的 message、tool_use/input_json_delta 与列明终止事件，执行前先读取完整有界 capture；不实现流内提前派发、text/thinking、服务端工具、全部 usage 更新或完整 Anthropic SDK。重复 end 失败、未知关键事件拒绝、严格 UTF-8/JSON 校验都是这里明确选定的 host 策略，不冒称实际 SDK 的全部行为。

SSE 部分覆盖 UTF-8/BOM、LF/CRLF/CR、event/data 行和注释，忽略的 id/retry 不代表已实现重连。固定 W3C 2021 EventSource 快照说明 EOF 不派发未完成事件；本 fixture 额外把未完整 capture 报成错误，且选择严格拒绝非法 UTF-8，并非完整浏览器 EventSource。上限为65,536 bytes和64事件，是本地实验口径。

<details>
<summary>展开原创外部格式 golden 与被测状态模型</summary>

```text
# file: golden.sse（保存时去掉这一行标记）
event: message_start
data: {"type":"message_start","message":{"id":"msg_synthetic","type":"message","role":"assistant","model":"synthetic-model","content":[],"stop_reason":null,"stop_sequence":null,"usage":{"input_tokens":4,"output_tokens":0}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"call_synthetic","name":"lookup","input":{}}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\"q\":\"茶\",\"n\":"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"12}"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"tool_use","stop_sequence":null},"usage":{"output_tokens":8}}

event: message_stop
data: {"type":"message_stop"}

```

```python
# file: runtime_fixture.py
"""Original bounded test target: SSE subset, strict tool-block model and virtual-time lease."""
import codecs
from copy import deepcopy
import json


class ProtocolError(Exception):
    pass


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ProtocolError('duplicate_json_key')
        result[key] = value
    return result


def constant(_):
    raise ProtocolError('nonfinite_number')


def parse(text):
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError) as exc:
        raise ProtocolError('invalid_json') from exc


def field(obj, key, kind):
    if type(obj) is not dict or key not in obj or type(obj[key]) is not kind:
        raise ProtocolError('invalid_field:' + key)
    return obj[key]


class SSE:
    """Bounded capture reader. Not an HTTP client, reconnect layer or general SDK."""
    def __init__(self):
        self.decoder = codecs.getincrementaldecoder('utf-8-sig')('strict')
        self.total, self.line, self.skip_lf = 0, '', False
        self.event, self.data, self.frames = '', [], []
        self.closed = False

    def _line(self):
        line, self.line = self.line, ''
        if not line:
            if self.data:
                value = parse('\n'.join(self.data))
                if field(value, 'type', str) != (self.event or 'message'):
                    raise ProtocolError('event_type_mismatch')
                self.frames.append(value)
                if len(self.frames) > 64:
                    raise ProtocolError('too_many_events')
            self.event, self.data = '', []
        elif not line.startswith(':'):
            key, separator, value = line.partition(':')
            if separator and value.startswith(' '): value = value[1:]
            if key == 'event': self.event = value
            elif key == 'data': self.data.append(value)
            # id/retry and unknown SSE fields are not used by this offline reader.

    def feed(self, chunk):
        if self.closed or type(chunk) is not bytes:
            raise ProtocolError('invalid_feed')
        self.total += len(chunk)
        if self.total > 65536:
            raise ProtocolError('capture_too_large')
        try:
            text = self.decoder.decode(chunk)
        except UnicodeError as exc:
            raise ProtocolError('invalid_utf8') from exc
        for char in text:
            if self.skip_lf:
                self.skip_lf = False
                if char == '\n': continue
            if char in ('\r', '\n'):
                self._line()
                self.skip_lf = char == '\r'
            else:
                self.line += char

    def finish(self):
        if self.closed:
            raise ProtocolError('reader_closed')
        self.closed = True
        try:
            self.decoder.decode(b'', final=True)
        except UnicodeError as exc:
            raise ProtocolError('invalid_utf8') from exc
        if self.line or self.data or self.event:
            raise ProtocolError('truncated_frame')
        return deepcopy(self.frames)


class Blocks:
    """Strict host policy for one tool-use message; no incremental tool dispatch."""
    def __init__(self):
        self.state, self.blocks, self.tools = 'new', {}, []
        self.ids, self.stop_reason = set(), None

    def _block(self, index):
        if index not in self.blocks:
            raise ProtocolError('missing_start')
        return self.blocks[index]

    def apply(self, event):
        try:
            self._apply(event)
        except ProtocolError:
            self.state = 'failed'
            raise

    def _apply(self, event):
        kind = field(event, 'type', str)
        if self.state in ('failed', 'closed'):
            raise ProtocolError('stream_terminal')
        if kind == 'ping': return
        if kind == 'message_start':
            if self.state != 'new': raise ProtocolError('duplicate_message_start')
            message = field(event, 'message', dict)
            if field(message, 'type', str) != 'message' or field(message, 'role', str) != 'assistant':
                raise ProtocolError('invalid_message')
            if not field(message, 'id', str) or field(message, 'content', list):
                raise ProtocolError('unsupported_initial_content')
            self.state = 'open'
            return
        if self.state != 'open': raise ProtocolError('message_start_required')
        if kind.startswith('content_block_'):
            index = field(event, 'index', int)
            if index < 0: raise ProtocolError('invalid_index')
            if kind == 'content_block_start':
                if index != len(self.blocks): raise ProtocolError('invalid_start_index')
                block = field(event, 'content_block', dict)
                if field(block, 'type', str) != 'tool_use' or field(block, 'input', dict) != {}:
                    raise ProtocolError('unsupported_block')
                cid, name = field(block, 'id', str), field(block, 'name', str)
                if not cid or not name or cid in self.ids: raise ProtocolError('invalid_call_identity')
                self.ids.add(cid)
                self.blocks[index] = dict(id=cid, name=name, chunks=[], closed=False)
            elif kind == 'content_block_delta':
                block = self._block(index)
                if block['closed']: raise ProtocolError('delta_after_stop')
                delta = field(event, 'delta', dict)
                if field(delta, 'type', str) != 'input_json_delta': raise ProtocolError('unsupported_delta')
                block['chunks'].append(field(delta, 'partial_json', str))
            elif kind == 'content_block_stop':
                block = self._block(index)
                if block['closed']: raise ProtocolError('duplicate_stop')
                args = parse(''.join(block['chunks']) or '{}')
                if type(args) is not dict: raise ProtocolError('invalid_arguments')
                block['closed'] = True
                self.tools.append(dict(id=block['id'], name=block['name'], args=args))
            else:
                raise ProtocolError('unknown_event')
        elif kind == 'message_delta':
            if self.stop_reason is not None: raise ProtocolError('duplicate_message_delta')
            self.stop_reason = field(field(event, 'delta', dict), 'stop_reason', str)
        elif kind == 'message_stop':
            if self.stop_reason != 'tool_use' or not self.blocks or not all(b['closed'] for b in self.blocks.values()):
                raise ProtocolError('incomplete_message')
            self.state = 'closed'
        else:
            raise ProtocolError('unknown_event')

    def finish(self):
        if self.state != 'closed': raise ProtocolError('incomplete_message')
        return deepcopy(self.tools)


def replay(chunks):
    reader = SSE()
    for chunk in chunks: reader.feed(chunk)
    model = Blocks()
    for event in reader.finish(): model.apply(event)
    return model.finish()


class Clock:
    def __init__(self): self.now = 4
    def advance(self, value):
        if type(value) is not int or value < self.now: raise ValueError('clock_moved_backwards')
        self.now = value


class Lease:
    """Virtual-time decision model; task cancellation/drain is tested separately."""
    def __init__(self, clock, generation='attempt-1'):
        self.clock, self.generation, self.deadline = clock, generation, 5
        self.status, self.value, self.records = 'pending', None, []

    def _finish(self, status, value=None):
        if self.status != 'pending': return False
        self.status, self.value = status, deepcopy(value)
        self.records.append(dict(status=status, value=deepcopy(value)))
        return True

    def resolve(self, generation, value):
        if generation != self.generation: return False
        if self.clock.now >= self.deadline: return self.timeout()
        return self._finish('succeeded', value)

    def timeout(self):
        if self.clock.now < self.deadline: return False
        return self._finish('timed_out')

    def cancel(self): return self._finish('cancelled')
    def fail(self): return self._finish('failed')


if __name__ == '__main__':
    import sys
    with open(sys.argv[1], 'rb') as source:
        captured = source.read(65537)
    print(json.dumps(replay([captured]), ensure_ascii=False, indent=2))
```

</details>

将代码保存为 `runtime_fixture.py`，将外部数据保存为 `golden.sse`，运行 `python3 runtime_fixture.py golden.sse`，实际得到一份 `call_synthetic / lookup` 计划，参数为 `q=茶, n=12`；没有派发真实工具。附件的 `python3 test_runtime.py` 运行完整正向/负向断言。

2026-09-16 实跑28 tests通过、0 failures/errors：包括覆盖949-byte golden所有950个单切点、32个固定seed的多切点、六种小型终态顺序，以及4个实际 asyncio mock task 的成功、异常、取消和超时收尾。24个协议测试目录删除、24次输入字节检查通过；4个任务都在兜底finally之前断言done、结果已消费且mock资源已释放。mock用Event等待，测试guard为1秒，只适用于协作式有限任务，不证明不合作任务的硬抢占或生产墙钟SLA。

为检验断言是否有检错能力，另在专属副本中各移除一道检查，原样运行同一测试脚本：

| 植入缺陷 | 同一套断言的实际结果 | 定位的风险 |
| --- | --- | --- |
| 允许重复 stop | exit1，1个断言失败 | 重复 end 被接受，完整计划可能包含重复调用 |
| 缺 start 时补造 block | exit1，4个断言失败 | 缺帧被默认数据掩盖，错误语义或计划发生变化 |
| resolve 不检查 deadline | exit1，1个断言失败 | timer 回调尚未运行时，已过期结果被记为成功 |
| 允许覆盖已有终态 | exit1，7个断言失败 | 取消/超时/结果互相覆盖，终态记录超过一次 |

四组测试脚本 hash 相同，每组都有目标断言失败且未处理测试错误为0；变异副本、diff、退出码和完整stderr均保留。4/4仅表示这四个选择的植入缺陷被检出，不是全系统 mutation score，也不是正式证明。本次没有测量代码覆盖率，更没有用覆盖率数字证明时序正确。

### 5. 失败要区分被测缺陷、oracle 错误和环境问题

看到红灯先保留输入、代码/fixture版本、顺序、clock/seed、预期与实际、失败堆栈和收尾状态，再定位责任。导入失败、损坏的fixture、错误的断言类型或“没读到结果就判失败”，都可能是测试问题；来自被测代码的未预期异常也可能是产品缺陷，不能仅凭 unittest 把它记为 error 就归咎 harness。

本次变异汇总曾把 `SystemExit(True)` 直接序列化成JSON布尔值，而非整数退出码。保留该旧记录后，改用独立子进程的真实 `returncode` 重跑四组，均为整数1，失败数仍是1/4/1/7。这个报告字段错误与四个被测植入缺陷分开登记，没有把它算成新增运行时缺陷。

回归维护也要避免“快照更新即修复”：对语义变化先核对外部契约和独立oracle，再更新预期；把缩小后的失败轨迹固定为专门测试。生成器与消费者若共享同一错误规则，成功回放可能永远测不出格式错误。性质测试也应在每个可观察步骤检查不变量，而不只看最终一句“完成”。

本次只有原创合成协议数据、虚拟时钟和协作式mock，没有访问生产日志、用户会话、凭据或收费模型，没有修改真实运行时。没有启动故障HTTP服务器、真实SDK、网络乱序器或跨进程执行器；未验证生产认证、远端取消/副作用回滚、分布式exactly-once、生产性能与持久性。

## 延伸 / 追问

- **把temperature设为0，能否省掉回放fixture？** 不能据此冻结外部服务、工具、检索数据、版本与调度。对运行时回归固定边界输入；真实模型能力另做带统计口径的评测。
- **重复block-end应该幂等忽略还是报错？** 取决于交付/重连契约。若有可靠事件ID及世代，可在定义好的层去重；没有这些依据时不能把重复结算当正常。本例选严格拒绝，并测试不生成重复计划。
- **性质测试全部通过，能证明没有竞态吗？** 只能证明所选输入域、顺序空间与oracle下没有找到反例；本例六种顺序不是全调度空间。还要检查真实实现的并发原子区、异常出口和集成行为。
- **工具timeout后是否可以直接丢弃Task？** 不行。终态决定与资源回收分别检查；要有owner取消/收集结果，迟到回调还需generation和终态守卫。mock收尾通过不等于远端工具已经撤销副作用。

## 常见误区

- **“覆盖率高就代表时序正确。”** 相同代码行可以按不同顺序执行；需要显式切点、事件排列和不变量。
- **“模型写几条成功路径测试就够了。”** 自产输入、自产oracle容易共享盲点；要对齐外部格式、独立预期、错误轨迹并验证检错能力。
- **“固定seed或回放成功能代替真实集成。”** 它们不能证明SDK/网络/鉴权/供应商当前行为或生产性能。
- **“测试报错都算发现产品bug。”** 必须定位错误来自SUT、oracle、harness还是环境，保留原记录，不能靠改预期把失败洗成通过。

## 参考

- 洛小山《AI 产品从入门到精通》learn-ai，固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/dsh-26.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-26.html)、[slides/dsh-22.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-22.html)、[slides/codex-03.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-03.html)。仅为学习线索，不采用课程特定覆盖率门槛、默认超时、首次发现bug或私有/restored源码行为作为本文事实；不搬运AGPL正文、代码或图片。
- Anthropic Python SDK **v1.6.0**，固定commit `7e5ca5c94126a6d7de159a169ff43eb9b1cac57f`：[RawContentBlockStartEvent](https://github.com/anthropics/anthropic-sdk-python/blob/7e5ca5c94126a6d7de159a169ff43eb9b1cac57f/src/anthropic/types/raw_content_block_start_event.py)、[RawContentBlockDeltaEvent](https://github.com/anthropics/anthropic-sdk-python/blob/7e5ca5c94126a6d7de159a169ff43eb9b1cac57f/src/anthropic/types/raw_content_block_delta_event.py)、[RawContentBlockStopEvent](https://github.com/anthropics/anthropic-sdk-python/blob/7e5ca5c94126a6d7de159a169ff43eb9b1cac57f/src/anthropic/types/raw_content_block_stop_event.py)、[InputJSONDelta](https://github.com/anthropics/anthropic-sdk-python/blob/7e5ca5c94126a6d7de159a169ff43eb9b1cac57f/src/anthropic/types/input_json_delta.py)、[RawMessageDeltaEvent](https://github.com/anthropics/anthropic-sdk-python/blob/7e5ca5c94126a6d7de159a169ff43eb9b1cac57f/src/anthropic/types/raw_message_delta_event.py)。用于校准wire形状；MIT源码只阅读引用，没有运行SDK，也不声称该SDK使用本例的严格状态策略。
- W3C [EventSource，2021-01-28固定快照](https://www.w3.org/TR/2021/SPSD-eventsource-20210128/)，第6/7节UTF-8、行终止、event/data与EOF规则。该版本标为Superseded Recommendation，用于可追溯的格式依据，不冒充当前完整浏览器实现。
- Hypothesis Python **6.112.1**：[stateful.rst](https://github.com/HypothesisWorks/hypothesis/blob/hypothesis-python-6.112.1/hypothesis-python/docs/stateful.rst)，动作生成、与简化模型比较、逐步invariant及可复现反例。本例采用标准库有限枚举和固定seed，没有执行Hypothesis引擎或其自动缩减流程；MPL-2.0材料只阅读引用。
- CPython **v3.11.8**：[asyncio-task.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/asyncio-task.rst)，Task取消、wait_for及gather结果收集语义。实验中的1秒guard仅验证协作式mock收尾，不证明强制中断任意代码。
