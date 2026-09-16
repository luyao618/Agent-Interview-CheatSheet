---
id: engineering-0032
title: 同一 Agent 内核接不同 provider、CLI 和 Web 时，怎样设计协议投影并安全迁移历史？
category: engineering
tags: [protocol-projection, history-migration, schema-evolution, provider-state, compatibility]
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

同一 Agent 内核接不同 provider、CLI 和 Web 时，怎样设计协议投影并安全迁移历史？请分别推演旧客户端读取新事件，以及切换 provider 后遇到不可迁移字段的处理，解释版本兼容、数据损失和日志分流的边界。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**内核保存有明确语义和版本的事实，adapter 按目标契约生成请求，前端按自己的协议展示。迁移前先证明哪些内容可解释、可保留；无法解释的关键事件应阻止恢复，可识别的私有状态损失则需要明确选择新的会话分支。** 把几个对象的字段名改成一样，无法完成这件事。

[agent-0022](agent-0022-prompt-mcp-abstraction.md) 讨论 Prompt/MCP 抽象，[agent-0016](agent-0016-checkpoint-resume.md) 讨论执行进度保存，[engineering-0025](engineering-0025-event-log-model-projection.md) 讨论事件真源和投影。本题补充跨版本读取、provider 私有状态迁移和协议输出兼容。

### 1. 共享内核，保留三种契约

| 层次 | 负责什么 | 需要独立约定什么 |
| --- | --- | --- |
| 领域事件 / 历史容器 | 谁说了什么、工具调用与结果关联、哪些上下文被撤下等事实 | 容器版本、event kind/version、ID、顺序、来源、引用完整性；不把 debug 文本当事件 |
| provider adapter / wire schema | 将可表达的事实变成特定 API 请求，并解释其响应 | role、内容块类型、调用 ID、增量/结束语义、错误、私有状态及版本能力；不能直接 dump 内部对象 |
| CLI / Web 协议与视图 | 向消费者传送有类型的帧或可展示状态 | 协议版本、能力、顺序/恢复游标、错误帧与诊断通道；UI 文本不是可逆的历史格式 |

可以让 CLI 与 Web 使用同一套应用协议，但必须显式定义。若 CLI 只支持最终文本，而 Web 支持流式块和工具状态，内核相同也不等于功能等价。适配器可以聚合已知增量成最终消息，前提是保留失败、取消、未完成与调用关联；把未知内容块统一转成字符串，会丢掉这些语义。

生产设计应保留原始 provider 材料的受控引用和命名空间，由对应 adapter 解释。它既不必进入所有前端，也不能因为 UI 不显示就从恢复材料中删除。UI 的拼接、脱敏或摘要是一份派生视图，不能反向补造 provider 历史。

### 2. 版本升级要能拒绝，不只要能读 JSON

建议固定 `container version + event kind/version + projector build + target API/model + frontend protocol`，对同一历史前缀生成可复核的投影。升级器采用纯函数：旧事件经已知转换成为当前表示，原始历史保留；如果必须落盘新格式，则写新版本/新分支，校验后再切换引用，不能半途覆盖唯一副本。

| 遇到的数据 | 本文教学兼容策略 | 理由 |
| --- | --- | --- |
| 已知 `message/v1`，新 reader 支持 `v2` | 把单个 text 升为文本 parts，记录 upcast 的 seq | 转换有定义且可测，字段名相似不是转换规则 |
| 预先登记为纯显示用途的 `ui.hint`，payload 版本更新 | 跳过投影并记录 ignored seq，原始数据保留 | 可忽略来自读取端已知契约；该 kind 永远不得承载执行控制 |
| 新 `message.hide/v2`，旧 reader 不理解 | `upgrade_required`，整次重放失败 | 它改变模型可见内容，跳过会复活被撤下的上下文 |
| 未知 kind、关键字段或没有转换器的新版本 | 拒绝；升级 reader 或取得受控转换方案 | 不能由写入方自行加 `critical=false` 就获得跳过许可 |

扩展区也要预先约定只承载非语义元数据；核心字段不能悄悄移入扩展区。分布式在线事件流可先协商支持的版本和能力，但磁盘旧文件没有协商对端，reader 仍须逐条检查。发现文件尾的关键事件不兼容时，不能已经把前半段当完整请求发出去；先完成一次有界、完整的预检，再输出请求或明确错误。

### 3. 私有状态不能靠改名跨 provider 迁移

固定一手源码给出的实际差异是：Anthropic Python SDK **v1.6.0** 的 `ThinkingBlock.signature` 是 opaque `str`，注释要求回传时保持收到的 thinking block 与 signature 完整；`RedactedThinkingBlock.data` 是加密的不透明内容，续接时保持 block 不变。Google Gen AI Python SDK **v2.23.0** 的 `Part.thought_signature` 是 `Optional[bytes]`，描述为后续请求可复用的不透明签名。**这些定义没有建立 `signature → thought_signature` 的跨供应商转换规则，也不允许解码加密内容来“补回推理”。**

真实 adapter 要依据固定版本的完整协议保存块、顺序、工具调用关系及适用的续接条件，不能只拷贝一个字段。相同 provider 也可能因 API、模型、上下文编辑或状态过期而不再接受旧状态；具体限制要逐产品核对。以下精确 namespace 与历史前缀匹配是本 fixture 的保守 host 策略，不宣称所有供应商都执行相同 hash 检查。

| 架构方案 | 适用条件 | 代价与不适用场景 |
| --- | --- | --- |
| 版本化领域事件 + 显式 provider / frontend adapter | 需要多个入口、长期演进和受控 provider 切换 | 要维护能力矩阵、upcaster 和损失报告；不适合承诺任意 provider 功能都能无损互换 |
| 保留 provider 原生历史，并固定对应 provider / 版本 | 单一 provider、希望尽量保留原生块和续接关系 | 仍须版本校验，且受供应商保留期等限制；耦合更强，不适合透明跨 provider 恢复 |

两种方案都可以保留原始材料。切换时进一步选择：**严格续接**要求所有必需语义都可迁移，否则拒绝；**有损新分支**仅在已理解全部关键事件的前提下，列出不能带走的私有状态，以可表达的公开内容重新开始。结果不能标成无损 resume。未完成工具调用、权限变化等未知语义不是一个通用“我接受损失”开关可以放行的内容。

### 4. 两个可复跑反例：旧 reader 与新 provider

原创 fixture 使用 **Python 3.11.8**；Alpha/Beta 及其 model、API、私有标记全部虚构。输入是最多 **1,000,000 bytes、1000 events** 的单文件合成快照，只实现已结束的 user/assistant 文本、私有状态、显示提示和可见性变更。system/tool 事件、图片和部分流式响应没有实现，因此拒绝；这些限值与拒绝策略都是教学口径。

`history()` 创建容器 `fixture-history/version=1`，默认事件如下。`basis` 是该 assistant 当时可见消息前缀的 hash；这里只是绑定合成状态，不能认证来源。

| seq | 事件 | 输入 |
| --- | --- | --- |
| 1 | `message/v1` | `u1/user`，`Synthetic request` 加换行和 `second line` |
| 2 | `message/v1` | `a1/assistant`，`Synthetic public reply` |
| 3 | `provider.state/v1` | owner=`a1`，scope=`alpha/alpha-wire-1/alpha-model-1`，opaque=`FICTIONAL_ALPHA_PRIVATE_STATE`，basis 绑定前缀 |
| 4 | `ui.hint/v2` | `progress_percent=75`，不参与模型输入 |

**反例 A：旧客户端读新事件。** reader=1 读取上述文件时，可以处理 message/v1 和 provider.state/v1，记录 seq=4 被忽略。另建 `history(private=False)`，其 hint 为 seq=3，再追加 seq=4 的 `message.hide/v2 {id:u1}`。reader=1 必须只输出 `error / upgrade_required / seq=4`，没有任何 prepared 请求前缀；reader=2 则把旧文本升级为 parts，应用 hide，模型视图仅有 `a1`。这可能不满足某真实 provider 的会话起始要求，fixture 不据此声称供应商会接纳；它验证的是读取语义。hide 也只是模型可见性示例，不是完整隐私删除机制。

**反例 B：Alpha 历史改投 Beta。** 同 scope、owner 与可见前缀匹配时，Alpha adapter 原样保留虚构私有标记。目标换成 `beta/beta-wire-2/beta-model-1`，`prepare` 返回损失 `[[3,"a1",["foreign_namespace"]]]`；没有匹配的 `loss_ack` 时返回 `loss_ack_required`。选择当前计划后，只生成 Beta 的 `turns/speaker/segments`，不带 Alpha opaque 字段，模式为 `lossy_fork`，输入字节不变。正文中的 Alpha `messages/blocks/alpha_state` 与 Beta 字段都是虚构 wire schema，不是实际 Anthropic/Gemini 请求。

`prepare` 还生成独立的 `view.1` 视图，并将原始字节 hash、reader、projector、目标、损失和输出绑定到不可变 Plan。`frame` 重新读取源快照、重算计划；源文件、目标或候选输出变化时拒绝 stale/modified plan。**这里的 `loss_ack` 仅表示选择当前计划，不是经过生产身份认证的用户授权**；真实授权须由可信入口绑定操作者和这份计划，见 [agent-0062](agent-0062-goal-budget-origin-authorization.md)。

本例假定输入是独占的不可变快照；重读能发现预览后已经发生的变化，不证明之后没有并发替换。在线系统需以版本化存储、确定前缀和发送边界校验建立并发契约。hash 也不证明“这是最新历史”，不能还原缺失材料。

### 5. 协议输出与诊断分流，错误也要有边界

CLI 机器模式需要明确 framing。JSON 本身不是分帧协议；重复写多个 JSON 值不会自动构成合法单个 JSON 文档。本例每帧一行，正文换行由 JSON 编码转义，协议流只输出 `prepared/error` 对象，诊断流只写不含正文的类型提示。CPython 的 parser 默认行为也不等于严格契约，本例额外拒绝重复键、非有限数和非法 UTF-8。

这是应用协议设计原则，也有具体标准实例：MCP **2025-06-18** 的 stdio transport 要求以换行分隔有效协议消息，stdout 不得混入非 MCP 消息，stderr 可写日志。**本例 `protocol=1` 不是 MCP 或 JSON-RPC 实现**。Web 的 HTTP/SSE/WebSocket 也须遵守各自 framing 和内容类型，诊断去服务端日志或单独定义的诊断消息，不能把调试文字插入事件数据。分流之外还需脱敏、访问与保留策略；将秘密从 stdout 移到 stderr 并不消除泄露。

语义预检失败可以在写入前变成一个完整错误帧；真正的流写入失败可能已经留下部分字节，此时不应追加第二个“重试成功”或“已回滚”帧。本例短写会报错，诊断在完整协议帧之后失败也会传播错误，但不会撤回已写帧；调用方不能据异常盲目重放。消费者需检查完整帧，真实 transport 还需请求 ID、去重/对账与重连策略。

下面的原创代码与附件中受 37 个测试验证的 fixture 逐字一致。保存为 `migration_fixture.py`，运行 `python3 migration_fixture.py` 即可独立复跑两例；只创建并清理脚本所在目录下的专属临时文件。

<details>
<summary>展开历史读取、兼容检查、两个 adapter 与协议帧实现</summary>

```python
# file: migration_fixture.py
"""Original journal/projectors with fictional Alpha/Beta wire formats. No provider calls."""
from dataclasses import asdict, dataclass
import hashlib
import io
import json
from pathlib import Path
import tempfile


class Refused(Exception):
    def __init__(self, code, seq=None):
        self.code, self.seq = code, seq
        super().__init__(code)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise Refused('duplicate_json_key')
        result[key] = value
    return result


def invalid_constant(_):
    raise Refused('invalid_json_number')


def keys(value, required, optional=()):
    if type(value) is not dict or not set(required) <= set(value) <= set(required) | set(optional):
        raise Refused('invalid_fields')


def text(value):
    if type(value) is not str or len(value) > 8192:
        raise Refused('invalid_text')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise Refused('invalid_unicode') from exc
    return value


def positive(value):
    if type(value) is not int or value < 1:
        raise Refused('invalid_version_or_sequence')
    return value


@dataclass(frozen=True)
class Target:
    provider: str
    api: str
    model: str


ALPHA = Target('alpha', 'alpha-wire-1', 'alpha-model-1')
BETA = Target('beta', 'beta-wire-2', 'beta-model-1')


@dataclass(frozen=True)
class Plan:
    source_sha: str
    target: Target
    reader: int
    losses: tuple
    ignored: tuple
    upcast: tuple
    request_json: str
    view_json: str
    token: str


def read_history(raw, reader):
    if reader not in (1, 2) or type(reader) is not int:
        raise Refused('unsupported_reader')
    if len(raw) > 1_000_000:
        raise Refused('history_too_large')
    try:
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise Refused('invalid_json') from exc
    keys(doc, ('format', 'version', 'events'))
    if doc['format'] != 'fixture-history' or type(doc['version']) is not int or doc['version'] != 1:
        raise Refused('unsupported_container_version')
    if type(doc['events']) is not list or len(doc['events']) > 1000:
        raise Refused('invalid_events')
    messages, hidden, private, ignored, upcast = [], set(), [], [], []
    ids, owners = set(), set()
    for seq, event in enumerate(doc['events'], 1):
        keys(event, ('seq', 'kind', 'version', 'data'), ('ext',))
        if positive(event['seq']) != seq:
            raise Refused('sequence_gap', seq)
        version = positive(event['version'])
        if 'ext' in event and type(event['ext']) is not dict:
            raise Refused('invalid_extension', seq)
        kind, data = event['kind'], event['data']
        if type(kind) is not str or type(data) is not dict:
            raise Refused('invalid_event', seq)
        # This ONE registered kind is display-only for every payload version.
        # A writer cannot hide new control semantics in it. Unknown kinds fail closed.
        if kind == 'ui.hint':
            ignored.append(seq)
            continue
        if kind == 'message':
            if version == 1:
                keys(data, ('id', 'role', 'text'))
                parts = [text(data['text'])]
                if reader == 2:
                    upcast.append(seq)  # Pure in-memory v1 -> canonical parts conversion.
            elif version == 2 and reader == 2:
                keys(data, ('id', 'role', 'parts'))
                if type(data['parts']) is not list or not data['parts']:
                    raise Refused('invalid_parts', seq)
                parts = []
                for part in data['parts']:
                    keys(part, ('type', 'text'))
                    if part['type'] != 'text':
                        raise Refused('unsupported_part', seq)
                    parts.append(text(part['text']))
            else:
                raise Refused('upgrade_required', seq)
            mid = text(data['id'])
            if not mid or mid in ids or data['role'] not in ('user', 'assistant'):
                raise Refused('invalid_message_identity_or_role', seq)
            ids.add(mid)
            messages.append(dict(id=mid, role=data['role'], parts=parts))
        elif kind == 'message.hide':
            if reader < 2 or version != 2:
                raise Refused('upgrade_required', seq)
            keys(data, ('id',))
            mid = text(data['id'])
            if mid not in ids or mid in hidden:
                raise Refused('invalid_hide_target', seq)
            hidden.add(mid)  # Affects the model projection, so old readers must not skip it.
        elif kind == 'provider.state':
            if version != 1:
                raise Refused('upgrade_required', seq)
            keys(data, ('owner', 'scope', 'opaque', 'basis'))
            keys(data['scope'], ('provider', 'api', 'model'))
            for value in data['scope'].values():
                text(value)
            owner = text(data['owner']); text(data['opaque']); text(data['basis'])
            visible = [m for m in messages if m['id'] not in hidden]
            if (not visible or visible[-1]['id'] != owner or visible[-1]['role'] != 'assistant'
                    or owner in owners or data['basis'] != digest(visible)):
                raise Refused('invalid_private_binding', seq)
            owners.add(owner)
            private.append(dict(seq=seq, **data))
        else:
            # Even ext={"critical":false} cannot authorize ignoring an unknown kind.
            raise Refused('unsupported_critical_event', seq)
    return [m for m in messages if m['id'] not in hidden], private, ignored, upcast


def prepare(path, target, reader=2):
    if (type(target) is not Target or target.provider not in ('alpha', 'beta') or
            target.api != {'alpha':'alpha-wire-1', 'beta':'beta-wire-2'}[target.provider] or
            not text(target.model)):
        raise Refused('unsupported_target')
    try:
        with Path(path).open('rb') as source:
            raw = source.read(1_000_001)  # Bound the read before JSON decoding.
    except OSError as exc:
        raise Refused('source_unavailable') from exc
    messages, private, ignored, upcast = read_history(raw, reader)
    losses, reusable = [], {}
    for item in private:
        owner = item['owner']
        indices = [i for i, m in enumerate(messages) if m['id'] == owner]
        reasons = []
        if not indices:
            reasons.append('owner_not_visible')
        elif digest(messages[:indices[0]+1]) != item['basis']:
            reasons.append('context_changed')
        if item['scope'] != asdict(target):
            reasons.append('foreign_namespace')
        if reasons:
            losses.append((item['seq'], owner, tuple(reasons)))
        else:
            reusable[owner] = item['opaque']  # Opaque bytes represented as a synthetic string.
    if target.provider == 'alpha':
        rows = []
        for m in messages:
            row = dict(role=m['role'], blocks=[dict(type='text', text=p) for p in m['parts']])
            if m['id'] in reusable:
                row['alpha_state'] = reusable[m['id']]
            rows.append(row)
        request = dict(schema='alpha.request.1', model=target.model, messages=rows)
    else:
        rows = []
        for m in messages:
            row = dict(speaker={'user':'human', 'assistant':'agent'}[m['role']],
                       segments=[dict(text=p) for p in m['parts']])
            if m['id'] in reusable:
                row['beta_continuation'] = reusable[m['id']]
            rows.append(row)
        request = dict(schema='beta.request.2', model=target.model, turns=rows)
    sha = hashlib.sha256(raw).hexdigest()
    view = dict(schema='view.1', source_sha=sha,
                rows=[dict(id=m['id'], role=m['role'], text=''.join(m['parts'])) for m in messages])
    # A view is deliberately lossy (part boundaries, private state) and not a journal.
    manifest = dict(source_sha=sha, target=asdict(target), reader=reader,
                    projector='fixture-projector-1', losses=losses, ignored=ignored, upcast=upcast,
                    request=request, view=view)
    return Plan(sha, target, reader, tuple(losses), tuple(ignored), tuple(upcast),
                encode(request), encode(view), digest(manifest))


def frame(path, target, *, reader=2, proposal=None, loss_ack=None):
    current = prepare(path, target, reader)
    if proposal is not None and proposal != current:
        raise Refused('stale_or_modified_plan')
    if current.losses and loss_ack != current.token:
        raise Refused('loss_ack_required')
    return dict(protocol=1, type='prepared', source_sha=current.source_sha, plan=current.token,
                mode='lossy_fork' if current.losses else 'local_projection',
                losses=current.losses, ignored=current.ignored, upcast=current.upcast,
                request=json.loads(current.request_json))


def write_frame(stream, value):
    line = encode(value)+'\n'
    if stream.write(line) != len(line):
        raise OSError('short_protocol_write')
    # A partial/failed write cannot be rolled back on a real stream. Never append a retry here.


def emit(path, target, output, diagnostics, *, reader=2, proposal=None, loss_ack=None):
    if output is diagnostics:
        raise Refused('channels_must_differ')
    try:
        value = frame(path, target, reader=reader, proposal=proposal, loss_ack=loss_ack)
    except Refused as exc:
        value = dict(protocol=1, type='error', code=exc.code, seq=exc.seq)
    # ALL preflight happens before the first protocol byte, including errors late in history.
    write_frame(output, value)
    diagnostics.write('migration '+value['type']+'\n')  # No body or private state in diagnostics.
    return value


def event(seq, kind, data, version=1, **extra):
    return dict(seq=seq, kind=kind, version=version, data=data, **extra)


def history(*, private=True):
    rows = [event(1,'message',dict(id='u1',role='user',text='Synthetic request\nsecond line')),
            event(2,'message',dict(id='a1',role='assistant',text='Synthetic public reply'))]
    if private:
        basis = digest([dict(id='u1',role='user',parts=['Synthetic request\nsecond line']),
                        dict(id='a1',role='assistant',parts=['Synthetic public reply'])])
        rows.append(event(3,'provider.state',dict(owner='a1',scope=asdict(ALPHA),
                          opaque='FICTIONAL_ALPHA_PRIVATE_STATE',basis=basis)))
    rows.append(event(len(rows)+1,'ui.hint',dict(progress_percent=75),version=2))
    return dict(format='fixture-history',version=1,events=rows)


def demo():
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='yao394-owned-',dir=root) as name:
        path = Path(name)/'synthetic-history.json'
        path.write_text(encode(history()),encoding='utf-8')
        original = path.read_bytes()
        same = prepare(path,ALPHA,reader=1)
        cross = prepare(path,BETA)
        out, diag = io.StringIO(), io.StringIO()
        blocked = emit(path,BETA,out,diag,proposal=cross)
        out, diag = io.StringIO(), io.StringIO()
        migrated = emit(path,BETA,out,diag,proposal=cross,loss_ack=cross.token)
        assert path.read_bytes() == original
        assert 'FICTIONAL_ALPHA_PRIVATE_STATE' not in out.getvalue()+diag.getvalue()
        newer = Path(name)/'newer-history.json'
        doc = history(private=False)
        doc['events'].append(event(len(doc['events'])+1,'message.hide',dict(id='u1'),version=2))
        newer.write_text(encode(doc),encoding='utf-8')
        old_out, old_diag = io.StringIO(), io.StringIO()
        old = emit(newer,BETA,old_out,old_diag,reader=1)
        modern = prepare(newer,BETA,reader=2)
        result = dict(same_namespace_private_preserved='FICTIONAL_ALPHA_PRIVATE_STATE' in same.request_json,
            foreign_private_without_ack=blocked['code'], losses=cross.losses,
            migration_mode=migrated['mode'], old_reader_error=old['code'],
            new_reader_visible_ids=[m['id'] for m in json.loads(modern.view_json)['rows']],
            source_unchanged=True, protocol_lines=len(out.getvalue().splitlines()),
            diagnostic_lines=len(diag.getvalue().splitlines()))
    assert not Path(name).exists()
    result['owned_directory_removed'] = True
    return result


if __name__ == '__main__':
    print(json.dumps(demo(),ensure_ascii=False,indent=2))
```

</details>

2026-09-16 实跑结果：**37 个测试通过，0 failures / 0 errors**；37 个测试临时目录已删除，每个测试均检查当前输入字节未被投影/拒绝路径改写。测试内及汇总 demo 分别核对其临时目录已删除。独立 demo 输出 `same_namespace_private_preserved=true`、`foreign_private_without_ack=loss_ack_required`、`migration_mode=lossy_fork`、`old_reader_error=upgrade_required`、`new_reader_visible_ids=["a1"]`；成功输出一行协议和一行诊断，`source_unchanged=true`。附件另覆盖未知关键事件伪称可忽略、私有前缀变化、计划篡改、解析错误、短写和诊断失败等边界。

这些结果仅验证本地转换、拒绝和输出契约。没有调用真实 provider/SDK、迁移用户会话或修改运行时配置；没有验证供应商接纳、原生续接保真、流式网络、持久提交、远端 exactly-once 或计费。`prepared` 明确只表示本地准备完成，未表示发送成功。

## 延伸 / 追问

- **新字段有默认值，能否直接让所有旧 reader 跳过？** 不能。先判断它是否改变恢复或执行语义；若会改变，旧 reader 必须知道兼容转换或拒绝。展示字段可经预先登记的扩展契约忽略，且保留原始记录，不能仅相信生产者宣称“可忽略”。
- **同一 provider 的旧 signature 还能读取，是否就能续接？** 不能由可读取推导可接受；还要核对 API/model、块与工具关系、当前上下文和供应商状态条件。fixture 的 namespace/prefix 检查只是保守局部规则，真实 adapter 必须按对应协议验证。
- **用户选择有损迁移后，能把未知 tool 事件转成普通文字吗？** 不应这样实现。用户接受已知私有状态损失，不等于工具执行状态已经确定。先由能解释该版本的组件核实调用与结果；不能解释时停止，而不是伪造一次完成。
- **UI 可以正确显示整段聊天，为什么仍不能作为恢复输入？** 它可能拼接 parts、隐藏状态或丢失调用 ID，显示完整不等于语义完整。恢复要从权威历史重新投影；需要导出 UI 时应标明不可续接的展示格式。

## 常见误区

- **“`signature` 和 `thought_signature` 看起来一样，改名即可。”** 名称、类型或可序列化性都不是跨 provider 语义契约。
- **“未知事件先跳过，旧客户端至少还能用。”** 静默丢弃关键事件可能恢复被撤下的上下文或误判任务状态；应先分类，不能理解时拒绝整次恢复。
- **“迁移 JSON 校验成功就是 provider 迁移成功。”** 本地 schema、源快照一致性、发送结果和供应商接纳是不同证据；有损分支也不是无损 resume。
- **“shared kernel 意味着 CLI/Web wire 和内部事件无需分别版本化。”** 每个边界都有消费者与演进节奏，诊断输出也不能混作协议事件。

## 参考

- 洛小山《AI 产品从入门到精通》learn-ai，固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/codex-27.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-27.html)、[slides/codex-28.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-28.html)、[slides/codex-29.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-29.html)、[slides/dsh-23.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-23.html)、[slides/dsh-25.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-25.html)。仅作学习线索，独立组织问答及 fixture，不复制 AGPL 课件正文、代码或图片；课程特定产品的字段数、默认跳过/迁移策略、性能或私有源码行为未独立验证，不作为本文结论。
- Anthropic Python SDK **v1.6.0**，commit `7e5ca5c94126a6d7de159a169ff43eb9b1cac57f`：[ThinkingBlock.signature](https://github.com/anthropics/anthropic-sdk-python/blob/7e5ca5c94126a6d7de159a169ff43eb9b1cac57f/src/anthropic/types/thinking_block.py#L9)、[RedactedThinkingBlock.data](https://github.com/anthropics/anthropic-sdk-python/blob/7e5ca5c94126a6d7de159a169ff43eb9b1cac57f/src/anthropic/types/redacted_thinking_block.py#L9)。类型及注释支持 opaque / 原样回传的表述；MIT 源码仅阅读引用。
- Google Gen AI Python SDK **v2.23.0**，commit `e384b55b8fdd7f0d816ca335223598e9bf460c17`：[google/genai/types.py · Part.thought_signature](https://github.com/googleapis/python-genai/blob/e384b55b8fdd7f0d816ca335223598e9bf460c17/google/genai/types.py#L2296)。支持 opaque bytes 字段及后续复用描述，不提供与 Anthropic 的转换保证；Apache-2.0。
- MCP **2025-06-18**，commit `cd0623765886c8cc282e3e5e1a03ab7469055fab`：[basic/transports.mdx · stdio](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/docs/specification/2025-06-18/basic/transports.mdx)。仅用作换行 framing 与 stdout/stderr 分流的一手实例，不把它的 transport 契约推广为所有 CLI/Web 标准。
- CPython **v3.11.8**：[Doc/library/json.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/json.rst)。JSON 不自行分帧、解析选项及默认兼容行为；严格校验规则由本文 fixture 自行定义。实验日期 2026-09-16，无供应商性能、价格或效果测量。
