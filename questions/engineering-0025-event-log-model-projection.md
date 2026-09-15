---
id: engineering-0025
title: 为什么模型可见上下文与持久事件日志应能对应，如何设计日志真源和 UI、索引投影？
category: engineering
tags: [event-sourcing, model-context, projections, auditability, snapshots]
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

为什么模型可见上下文与持久事件日志应能对应，如何设计日志真源和 UI、索引投影？请用“上下文补充只出现在内存”的反例说明怎样发现并阻止审计漂移，并解释读模型回填与快照取舍。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**真正要守住的是“这次客户端送出的请求，能由已提交事实和固定组装规则解释”，不是“程序打印过日志”。** 若关键上下文只存在于内存，事后即使看见完整的用户/assistant 对话，也可能不知道模型为什么作出那个决定。UI 又可能隐藏、压缩或翻译消息，不能拿它补造历史事实。

[agent-0016](agent-0016-checkpoint-resume.md) 讨论保存执行进度，[engineering-0006](engineering-0006-ai-app-monitoring.md) 讨论监控，[agent-0044](agent-0044-agent-status-bar-design.md) 讨论只读状态栏。本题新增请求与事件的可验证关系，以及派生读模型的重建；不要求所有应用都升级为完整事件溯源系统。

### 1. 事件是真源，投影各自回答不同问题

在选用事件溯源的设计中，命令经校验后产生有身份、版本、顺序与来源的事件，先提交到权威存储，再供不同 projector 使用。普通 debug 文本、临时对象或消息总线本身，不自动具备完整性、顺序、并发版本校验与保留能力。

```text
受控命令 → 校验 / expected revision → 持久事件流（确定前缀 k）
                                     ├→ model projector → 最终请求校验 → 请求准备记录 → transport
                                     ├→ UI projector    → 可丢弃的显示/列表缓存
                                     └→ index projector → 可回填的检索读模型
UI 编辑意图 → 新命令 / 新事件；不把 UI 缓存反向覆盖事件流
```

例如一次用户补充可以记为 `ContextAdded`，一次请求准备记为 `RequestPrepared`。前者能影响模型输入，后者记录发送意图但不必再进入模型上下文。一个事件也可能生成多条模型消息，或参与有版本的摘要；**“可对应”不是每个事件与每条消息逐条相等，更不是 UI、模型和索引三个数组都相同。**

| 投影 | 需要保留的内容/关系 | 不能成为的东西 |
| --- | --- | --- |
| 模型请求 | role、顺序、工具调用关联、系统指令、上下文与实际采样/工具配置的确定组装结果 | 不能包含来源不明的内存补丁或悄悄变化的外部内容 |
| UI / 会话列表 | 展示顺序、状态、可见性、摘要和处理到的 watermark | 隐藏的上下文、partial、错误状态不能靠界面文字反向猜测或改写 |
| 搜索/索引 | 稳定 document/event ID、来源版本、权限过滤和投影进度 | 索引缺项不等于源事件不存在；搜索结果也不能回灌为原始事实 |

UI 可以接受编辑操作，但应将它提交给命令处理器，生成校正/新版本/分支事件；不是直接修改事实镜像。读模型损坏时从真源回填，而不是“哪个界面看起来完整就信哪个”。

### 2. 把模型可见不变量放在最终请求边界

对某次请求定义：

```text
E[1..k] = 已提交的同一会话/分支事件前缀
P_v     = 固定版本的模型投影、模板与序列化规则
A       = 可按版本/hash取回的上下文、附件与工具定义等不可变材料
B       = P_v(E[1..k], A) 产生的客户端请求字节
要求：实际交给 transport 的字节 == B
```

日志除了对话还要覆盖模型 ID/配置、system prompt、工具 schema、RAG 结果及其顺序、注入来源、裁剪/摘要策略和材料版本。只保存“查过文档 X”，重放时却读取今天的 X，会产生另一份输入；只保存 hash 而没有可取回的材料，也不能从 hash 还原正文。

一种做法是在提交前记录 `request_id、cut=k、projector/artifact version、材料引用、最终 request blob/hash`，并在受控 transport 边界核对。比较或保存的位置若早于 SDK 的后续转换，仍可能遗漏字段；真实系统要在最后一个会改请求的适配层捕获或验证最终表示。哈希适合识别差异与绑定材料，不是签名，也不能认证有能力同时改写日志和哈希的攻击者。

`RequestPrepared` 只证明准备记录已提交，不证明请求已经发送、供应商接收或模型理解。发送未知/重试需另记 attempt/outcome，必要时用 outbox、领取与对账；不能把本地准备事务和远端 API 当成同一事务。这里要求复现客户端输入，**不承诺复现随机模型输出、供应商内部模板或全部内部推理条件**。

发现不一致应拒绝这次请求、保留可定位的 event IDs/version/hash，再重新记录缺失事实并重建。只告警后继续发送，会留下已知审计缺口；将整个进程崩掉也不是唯一策略。敏感正文可按授权存储为受保护 blob，诊断不必输出全文；删除/过期后无法重建的材料应明确标记不可用，不从 UI 猜回来。

### 3. 一个“只在内存注入”的反例和修复

以下是原创单会话 fixture，固定 **Python 3.11.8、sqlite3 模块实际链接 SQLite 3.19.3**；仅使用新建临时库和基础 SQL，没有真实模型调用，也不建议照此旧 SQLite 版本部署生产。

初始已提交事件：

| seq / ID | 事件 | fixture 内容 |
| --- | --- | --- |
| 1 / cfg | Configured | model=`fixture-model-v1`，system=`你是演示助手` |
| 2 / m1 | MessageAdded | `安排明天活动` |
| 3 / ctx1 | ContextAdded | `预算100元` |

`model-v1` 将 Configured 组成 system 与 model 字段，将 MessageAdded 组成 user 消息，将 ContextAdded 组成带“补充上下文：”前缀的 user 消息，并固定 `tools=[]、temperature=0`。这些规则和常量都属于该 projector 版本；正式系统应绑定不可变构建/模板，而不是只写一个可随意复用的版本名。

错误路径在调用前偷偷追加 `补充上下文：只选室内活动` 到内存消息数组。日志重放仍只有 3 条模型消息（含 system），候选却有 4 条：

```text
head=3 → 构建候选 → 内存追加“只选室内活动”
prepare(candidate, cut=3) → AUDIT_DRIFT
结果：事件头仍为3，没有RequestPrepared，没有调用fake transport

修复：append ContextAdded(ctx2) → head=4
从E[1..4]重建 → prepare成功，RequestPrepared(req1)成为seq=5
send_prepared(req1) → 只读取已记录并核对过的字节
结果：fake transport调用1次，模型消息4条；UI公开消息1条，context_count=2
```

UI 的 1 条消息是 m1；本例只显示补充上下文的数量，索引也仅收公开 MessageAdded。它们不是少记了事实，前提是这些过滤是明确的投影规则。故意篡改 UI 缓存中的文本不会改变请求；完整回填能恢复显示内容。

下面的核心实现可复跑。`BEGIN IMMEDIATE` 内比较 event head、重建、拒绝漂移并记录准备事件；网络发送放在事务之后。此处 JSON 编码是本 fixture 的固定 Python 规则，不宣称符合跨语言 canonical JSON 标准。

<details>
<summary>展开临时日志、请求门禁和读模型重建实现</summary>

```python
"""Original single-session fixture. Python3.11.8; no real model/network."""
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from copy import deepcopy


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(pack(value)).hexdigest()


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("invalid sequence")


def source_body(kind, body):
    fields = {"Configured": {"model", "system"},
              "MessageAdded": {"text"}, "ContextAdded": {"text"}}
    if kind not in fields or type(body) is not dict or set(body) != fields[kind]:
        raise ValueError("unknown event or fields")
    if any(type(v) is not str or not v or len(v) > 500 for v in body.values()):
        raise ValueError("invalid source body")
    return pack(body).decode("utf-8")


def validate_prefix(rows):
    ids = set()
    for seq, row in enumerate(rows, 1):
        if (type(row["seq"]) is not int or row["seq"] != seq
                or type(row["version"]) is not int or row["version"] != 1
                or row["id"] in ids):
            raise ValueError("gap, duplicate or unsupported schema")
        ids.add(row["id"])
        if row["kind"] != "RequestPrepared":
            source_body(row["kind"], row["body"])


def model_wire(rows, version="model-v1"):
    if version != "model-v1":
        raise ValueError("unknown model projector")
    validate_prefix(rows)
    if not rows or rows[0]["kind"] != "Configured":
        raise ValueError("missing configuration")
    config = rows[0]["body"]
    messages = [{"role": "system", "content": config["system"]}]
    for row in rows[1:]:
        if row["kind"] == "MessageAdded":
            messages.append({"role": "user", "content": row["body"]["text"]})
        elif row["kind"] == "ContextAdded":
            messages.append({"role": "user", "content": "补充上下文：" + row["body"]["text"]})
        elif row["kind"] != "RequestPrepared":
            raise ValueError("invalid configuration position")
    # These fixed defaults and the context prefix are part of model-v1.
    return pack({"model": config["model"], "messages": messages, "tools": [], "temperature": 0})


def manifest(rows, wire):
    return {"cut": len(rows), "projector": "model-v1", "prefix_sha": digest(rows),
            "wire": wire.decode("utf-8"), "wire_sha": hashlib.sha256(wire).hexdigest()}


class Log:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, "
                        "id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL)")

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def head(self):
        return self.db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]

    def rows(self, cut=None):
        if cut is None:
            cut = self.head()
        integer(cut)
        rows = [dict(seq=s, id=i, kind=k, version=v, body=json.loads(b))
                for s, i, k, v, b in self.db.execute(
                    "SELECT seq,id,kind,version,body FROM events WHERE seq<=? ORDER BY seq", (cut,))]
        validate_prefix(rows)
        if len(rows) != cut:
            raise ValueError("missing prefix")
        return rows

    def put(self, event_id, kind, body, expected):
        if type(event_id) is not str or re.fullmatch(r"[a-z0-9_-]{1,40}", event_id) is None:
            raise ValueError("invalid id")
        integer(expected)
        encoded = source_body(kind, body)  # Validate before duplicate comparison.
        with self.transaction():
            old = self.db.execute("SELECT seq,kind,body FROM events WHERE id=?", (event_id,)).fetchone()
            if old:
                if old[1:] != (kind, encoded):
                    raise ValueError("conflicting event id")
                return old[0]
            head = self.head()
            if head != expected or ((kind == "Configured") != (head == 0)):
                raise ValueError("stale head or invalid configuration position")
            self.db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (head+1, event_id, kind, 1, encoded))
            return head+1

    def prepare(self, request_id, cut, candidate):
        if type(request_id) is not str or re.fullmatch(r"[a-z0-9_-]{1,40}", request_id) is None:
            raise ValueError("invalid request id")
        integer(cut)
        if type(candidate) is not bytes:
            raise ValueError("candidate must be immutable bytes")
        with self.transaction():
            if self.head() != cut:
                raise ValueError("stale preparation cut")
            rows = self.rows(cut)
            expected = model_wire(rows)
            if candidate != expected:
                raise ValueError("AUDIT_DRIFT: request differs from committed event projection")
            body = pack(manifest(rows, expected)).decode("utf-8")
            self.db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (cut+1, request_id, "RequestPrepared", 1, body))

    def send_prepared(self, request_id, transport):
        row = self.db.execute("SELECT seq,version,body FROM events WHERE id=? AND kind='RequestPrepared'",
                              (request_id,)).fetchone()
        if not row or row[1] != 1:
            raise ValueError("missing or unsupported prepared request")
        saved = json.loads(row[2])
        integer(saved["cut"])
        if saved["cut"] != row[0]-1:
            raise ValueError("invalid prepared cut")
        rows = self.rows(saved["cut"])
        wire = model_wire(rows, saved["projector"])
        if saved != manifest(rows, wire):
            raise ValueError("prepared payload or source drift")
        return transport(wire)  # No caller-supplied mutable messages after this gate.


def rebuild_views(rows, snapshot=None, version="views-v1"):
    if version != "views-v1":
        raise ValueError("unknown view projector")
    validate_prefix(rows)
    cut = 0
    state = {"messages": [], "context_count": 0, "index": {}}
    if snapshot is not None:
        cut = snapshot["cut"]
        integer(cut)
        if (snapshot["version"] != version or cut > len(rows)
                or snapshot["prefix_sha"] != digest(rows[:cut])
                or snapshot["state_sha"] != digest(snapshot["state"])):
            raise ValueError("invalid snapshot")
        state = deepcopy(snapshot["state"])  # Only trusted projector snapshots are accepted.
    for row in rows[cut:]:
        if row["kind"] == "MessageAdded":
            state["messages"].append({"event_id": row["id"], "text": row["body"]["text"]})
            state["index"][row["id"]] = row["body"]["text"].casefold()
        elif row["kind"] == "ContextAdded":
            state["context_count"] += 1
    return {"version": version, "cut": len(rows), "prefix_sha": digest(rows),
            "state": state, "state_sha": digest(state)}
```

</details>

正式验证包含：未记事件的内存上下文、模型字段和消息顺序变化均被拒；补齐事件后可发送；关闭并重开临时库后可重建同一请求；准备后的字节或前缀被改写会在发送门禁失败。fake transport 只接收 immutable bytes，不再接收可被其他回调继续修改的 messages 对象。

不变量针对明确的 cut k。准备之后才到达的新事件不自动改写旧请求；由 [agent-0055](agent-0055-turn-loop-input-semantics.md) 所述投递生命期决定它属于下一 step/turn。如果业务要求“发送前不能过期”，还需核对该轮有效 revision/fence；本例不把输入可重建与输入始终最新混为一谈。

### 4. 读模型回填与快照不能产生第二份真源

回填时为每个会话/分支及 projector 版本记录连续 watermark；以稳定事件/文档 ID 写读模型，结果与进度一并提交。重复交付不能重复计数，遇到缺口、乱序、未知 schema/version 不能直接把游标跳到最大值后宣称完成。投影升级可建 shadow read model，从固定前缀回放、追平增量，核对数量/内容摘要/权限条件后切换指针；不要边用新逻辑改旧表、边让读者读到混合版本。

本例 `rebuild_views` 从有连续 seq 的事件前缀生成 UI 与小型字典索引。重复全量重建相同前缀得到相同结果；从 cut=3 的快照续放 ctx2 和 RequestPrepared 后，与全量回放到 cut=5 完全相同。它不实现真实消息总线消费或投影表的分布式提交，只演示确定性回填和边界校验。

| 方案 | 适用情形 | 成本与边界 |
| --- | --- | --- |
| 每次从事件起点重建 | 小会话、审计校验、排查缓存错误 | 逻辑简单，长历史重放代价随事件数增加 |
| 可信快照 + 后缀事件 | 长历史、需要缩短恢复路径且可验证版本/前缀 | 增加写入、存储、迁移和失效处理；快照不能取代原事件及历史请求所需材料 |
| 持久读模型异步增量更新 | UI 列表/搜索需要低读取成本，可接受有界滞后 | 需消费幂等、进度、重建与切换机制；不能把落后投影拿来作要求最新事实的写决策 |

快照至少绑定 `(stream/branch, cut, projector version, event-prefix digest, state digest)`。本例单库单会话，隐含 stream/branch；校验不符直接拒绝快照，再从源重建。state hash 只发现未同步改摘要的损坏，不能证明状态一定是正确 projector 生成的；只接纳可信构建的快照，并用周期性/抽样全量回放比较，不能接受客户端 UI 上传的镜像作为恢复依据。

例如 10,000 个事件、快照位于 9,000，在已有可信前缀校验索引的假设下只需恢复快照并应用后面 1,000 个事件；这只是复杂度算例，不是实测加速。本 fixture 为核对正确性仍装载并校验整个前缀，没有宣称性能收益。若每次验证快照都扫描前 9,000 个事件，读取成本仍不能简单说降低了十倍。

对于简单 CRUD、只需当前状态且没有历史输入审计需求的应用，完整事件溯源可能不划算；也可保留事务型权威状态和每次最终请求的不可变快照。无论选择哪种，明确哪份记录是权威、请求材料怎样取回、派生视图怎样作废，比要求“所有东西都叫事件”更重要。

### 5. 一手运行时例子：转换钩子不自动等于审计记录

固定 Pi **v0.57.1 / `a9cedccdde77e9d765303463d8a6cd11c58f7a7f`** 的 [streamAssistantResponse](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/agent/src/agent-loop.ts#L204-L240) 先应用 transformContext，再 convertToLlm，随后添加 systemPrompt/tools 并调用 streamFunction。[类型说明](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/agent/src/types.ts#L24-L64) 允许转换时过滤 UI-only 消息，也允许在 transformContext 中注入外部上下文。

这能证明“模型消息有独立的组装阶段”，不能仅凭这段函数证明最终转换结果已经持久化；同样不能据此断言整个 Pi 产品有审计缺陷。宿主需要核对所有注入、配置和最终传输边界，再决定事件/请求快照如何覆盖。本文只读固定源码，没有运行 Pi、修改它的日志或调用模型。

## 延伸 / 追问

**为什么记录了检索 query 和文档 URL 还不能复现输入？** 重放时语料、权限、排序、截断甚至 URL 内容可能变化。应保存实际选中的材料快照或不可变版本/hash引用，以及组装规则；重放输入不是重新做一次今天的检索。

**摘要或上下文裁剪后，模型没有看到所有事件，违反不变量吗？** 不必然。只要记录所用 cut、摘要/裁剪版本、输入来源及确定的结果材料，能重建模型实际看到的表示即可。不能重新调用一个随机摘要模型后声称得到了原始输入。

**发现 UI 比日志多一句重要补充，能直接把 UI 补回日志吗？** 不能当作历史修复。先隔离差异、查原请求/输入来源及授权；若用户确认要补充，作为新命令和新事件记录，保留补录时间与来源，不伪造它过去已存在。历史材料缺失时如实标记不可重建。

## 常见误区

- “有日志就能复现模型输入”：普通 tracing 可能缺 system、注入、工具 schema、材料版本或最终序列化。
- “UI 镜像最完整，可以反向当真源”：显示过滤、压缩和用户编辑会把派生状态变成另一套历史。
- “快照正确，因为它有 hash”：hash 不证明来源可信或投影逻辑正确，快照仍应可丢弃重建。
- “请求准备成功等于模型已经收到”：本地提交、网络发送、远端响应是不同事件，重试也不天然 exactly-once。
- “重放就是把工具再执行一遍”：重建已记录的状态/输入不应再次触发外部副作用。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/dsh-2.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-2.html)、[slides/codex-06.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-06.html)、[slides/codex-09.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-09.html)。只保留学习来源，不搬运 AGPL 课件，不把二手课程里的退出/flush/恢复行为当通用保证。
- Microsoft Azure Architecture Center，固定文档 commit **`d73cd1632ffa489eff78a16bba4d101c510a1810`**：[Event Sourcing pattern](https://github.com/MicrosoftDocs/architecture-center/blob/d73cd1632ffa489eff78a16bba4d101c510a1810/docs/patterns/event-sourcing.md)（权威事件流、乐观并发、幂等、快照与取舍）、[CQRS pattern](https://github.com/MicrosoftDocs/architecture-center/blob/d73cd1632ffa489eff78a16bba4d101c510a1810/docs/patterns/cqrs.md)（读写模型、投影重建与同步边界）。引用机制，不直接采用其性能结论作为本例测量。
- CPython **v3.11.8**，[sqlite3 事务控制](https://github.com/python/cpython/blob/v3.11.8/Doc/library/sqlite3.rst#L2390-L2429)：本例使用 isolation_level=None 与显式 BEGIN/COMMIT/ROLLBACK，仅在专属临时库验证，不修改真实运行时存储。
- Pi **v0.57.1**，[package.json](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/packages/agent/package.json)、[MIT LICENSE](https://github.com/earendil-works/pi/blob/a9cedccdde77e9d765303463d8a6cd11c58f7a7f/LICENSE)，具体投影调用点见正文。
- 来源核对和本地 fixture 验证日期为 **2026-09-16**。没有真实模型/索引服务、业务数据、生产持久性或性能实验；SQLite API、事件 ID 和版本只是本例范围，不是完整生产事件存储协议。
