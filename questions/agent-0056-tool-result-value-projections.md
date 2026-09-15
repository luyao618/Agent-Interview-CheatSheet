---
id: agent-0056
title: 工具返回大量结构化数据时，如何分离程序值、模型文本和 UI 展示，并支持按需读取？
category: agent
tags: [tool-result, schema, code-mode, projection, pagination, redaction]
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

工具返回大量结构化数据时，如何分离程序值、模型文本和 UI 展示，并支持按需读取？SQL 返回 1200 行，只展示 50 行时，Code Mode 程序究竟能读到多少行，哪些字段？

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 回答 2026-09-16

先问**截断发生在哪一层**。如果只有模型文本和 UI 取前 50 行，而程序 value 含 1200 行，程序就能处理全部 1200 行；如果 value 的 rows 本身只剩 50 行，程序直接可读的也只有 50 行。`total=1200` 是数量信息，不会让缺失的 1150 行自动出现在程序内存里。只有另有合法的完整快照和受控读取入口，程序才可能按需补齐。

工具注册和输出 Schema 的关系见 [agent-0014](agent-0014-tool-registry-design.md)，减少模型上下文搬运见 [agent-0038](agent-0038-reduce-agent-token-cost.md)。本题强调信息在哪个通道丢失、完整结果是否还存在，以及谁有权取回，不把“省了展示文本”直接当成“少暴露了数据”。

### 1. 先定义规范值，再定义消费者

建议在可信工具边界完成授权、行过滤、字段白名单和 value Schema 校验，再生成各通道输出。不要从已格式化的 Markdown 表格反向解析出程序数据。

| 通道 | 契约内容 | 不能假定什么 |
| --- | --- | --- |
| 程序 value | 带版本的 JSON 值；字段名/类型、rows、offset、returned、total、truncated、可选结果引用/游标 | 模型只见 50 行不代表程序也只见 50 行；结构化字段不是天然的秘密通道 |
| 模型文本 | 从已批准 value 生成摘要、统计或有限行；保留范围和缺失提示 | JSON/text 都可能进入模型上下文；不能只清理一份展示副本 |
| UI 投影 | 用同一批准值生成表格/卡片数据，标示实际展示范围 | 纯投影不重新查库、不偷偷取下一页，也不能把 UI 编辑写回规范值 |
| spill / 分页读取 | 保存批准的完整快照或提供稳定查询游标；返回引用、页边界、有效期与读取错误 | 引用不是授权，分页不是绕过原字段/租户策略的后门 |

每个通道分别说明信息损失。本例 `truncated` 表示“当前这份 rows 不含整个授权结果”，不是 `has_more` 的同义词：最后一页仍只有 50/1200 行，`truncated=true`，但 `next_cursor=null`。`offset` 是当前页从零开始的位置，`returned` 是本页行数，`total` 是同一授权快照的总行数。若真实系统无法知道准确总量，应设计可空的 total 或单独的估计字段，不能把另一时刻的 COUNT 当同一快照事实；下面固定 Schema 只支持已知整数 total。

MCP **2025-06-18** 版规范在固定 commit `cd0623765886c8cc282e3e5e1a03ab7469055fab` 的 tools 文本中区分 `content` 与 `structuredContent`，支持可选 `outputSchema`，并要求服务端结构化结果符合已声明 Schema。它还建议为了兼容性附带序列化 JSON 文本。因此，“结构化结果给程序、文本给模型”是宿主需要落实的分流策略，**协议字段本身不承诺模型看不到结构化值**。资源链接可供客户端取回；`resources/list` 的分页也不自动赋予任意 SQL 结果分页能力，后者仍需工具自己的契约。

### 2. 大结果怎么取舍，安全在哪里做

| 方案 | Code Mode 直接可读 | 适用与代价 |
| --- | --- | --- |
| 全量批准 value，模型/UI 只投影 50 行 | 全部 1200 行的批准字段 | 程序要做全量聚合且数据规模可控；免分页往返，但搬运/内存大，已交出的副本无法靠撤权收回。不适合必须严格限制一次数据交付量的场景 |
| value 先给 50 行，完整批准结果 spill 后分页 | 当前 50 行；额外行要逐次通过读取授权 | 需要按需访问、可见边界和稳定快照；代价是存储、延迟、过期处理。超大快照或必须实时读取最新数据时应另选流式/服务端游标设计 |
| value 只留下 50 行，其余丢弃 | 只有 50 行，没有可补齐入口 | 只需要样例或 top-k，能接受损失；不适合在程序端计算全量总和。不要仅凭 total 宣称完整结果仍可获取 |

**脱敏应作用在批准值上，发生在分流和 spill 之前。** 最好从 SQL 列级、行级就减少不需要的数据，再对结果做白名单校验。只把模型文本里的私密字段删掉，程序仍可能读 `value.rows[i].private_note` 并把它打印到 stdout；把原值写入 spill，也会给后续 read 留一条旁路。模型文本、UI 数据、下载、程序 stdout、日志/错误消息和缓存副本都要沿同一数据策略检查。需要不同权限的消费者时，分别产生批准的数据视图，不能把低权限 UI 缓存复用成高权限程序值。

Schema 校验保证结构，不自动判断每段文字是否敏感。本例按明确的列策略删除 private_note、拒绝额外输出字段，不实现自由文本中的个人信息识别。

UI 的安全与数据脱敏也不同：即使字段允许公开，单元格里的 `<script>` 仍应作为文字展示。本例仅拼装静态 HTML 标签，动态单元格使用 `html.escape`；真实 Markdown/富文本渲染还需要其自身的 URL、HTML 等策略。工具返回的文本属于数据，不因为格式合法就变成可信的系统指令。

读取入口每次校验当前身份、租户/主体、权限版本、引用范围及有效期，然后才读存储并生成投影。游标绑定同一结果引用，不能拿另一查询的游标混用，也不接受调用方给出的文件路径。动态查询还应绑定查询与排序规则、Schema 和快照版本。本例查询固定，结果引用定位一次不可变快照；元数据中的 total 也是过滤到该租户后的数量，不暴露其他租户的计数。

撤权或权限版本变化会阻止后续读取，但不能删除先前已交给程序的副本。TTL 到期拒读也不等于物理删除，还要有独立的数据保留/回收策略。spill 存储失败时可明确报交付失败，或在约定范围内返回已脱敏的降级预览；不能悄悄把未脱敏全文内联出去。本例选择前者。

### 3. SQL 1200 行、展示 50 行的实际对照

原创 fixture 创建专属临时 SQLite 库：租户 A 有 1200 行，租户 B 有 1 行；只执行固定的参数化 SQL，先按当前租户过滤并按 id 排序。A 的 `id=1..1200`，`amount=id` 是无量纲合成数值；`private_note` 填入合成 canary，用来验证它不出现在任何交付通道。第一行 label 故意含 `<script>fixture</script>`，用于验证 UI 转义，不含真实个人信息。

固定输出 Schema 的公开行只有 `id:int`、`label:str`、`amount:int`。服务端先白名单过滤，再校验 value；raw SQL 结果中虽然故意含 private_note，它不会进入程序 value、模型文本、UI 或 spill。模型/UI 每次最多展示当前页的前 50 行，renderer 不访问数据库或文件。

下表是 Python 3.11.8 本地运行的结果。这里的 Code Mode 消费者是原创程序 `consume_all`，**不是实际运行时或模型生成代码的测试**：

`mode` 是测试用来对照三种部署契约的开关，生产应只暴露批准的策略，不能让客户端随意切换预算限制。cut 的“不可取回”针对当前结果；重新查询是另一项需要授权和预算的操作。

| 模式 | 初始 value 行数 / 求和 | 模型文本 / UI 行数 | 程序显式读取后 |
| --- | --- | --- | --- |
| full | 1200 / 720600 | 50 / 50 | 1200 / 720600，complete=true；无需额外读取 |
| paged | 50 / 1275 | 50 / 50 | 再读 23 页，共 1200 / 720600，complete=true |
| cut | 50 / 1275 | 50 / 50 | 无引用或游标，仍为 50 / 1275，complete=false |

独立算式：前 50 行总和为 `50×51÷2=1275`，全量为 `1200×1201÷2=720600`；差额来自没读到的行，不是模型算错。paged 初始 value 的关键字段为：

```json
{
  "schema_version": 1,
  "offset": 0,
  "returned": 50,
  "total": 1200,
  "truncated": true,
  "availability": "paged_snapshot",
  "result_ref": "<本次运行生成的不透明引用>",
  "next_cursor": "<绑定该引用的下一页游标>"
}
```

这段 JSON 只摘录元数据；实际 rows 也在 value 中，引用由程序随机生成，不是上面的占位字串。`availability` 说明完整结果保留的位置：inline_all 表示程序初始值内已有全量，paged_snapshot 表示有受控快照，discarded 表示未交付的行不可通过本结果取回。模型文本额外标明 `channel=model_text`，其 returned/truncated 描述它自己可见的行，不能拿程序通道的完整标志冒充模型已经看过全部内容。

程序读完第 24 页时 offset=1150、returned=50、total=1200、truncated=true、next_cursor=null。每一页和 spill 文件都检查没有 canary；其他租户、同租户其他主体、被撤销或旧权限版本、过期引用、跨结果游标均拒读。重新查询会生成新快照；修改源表不会改变已经发出的结果快照。

<details>
<summary>原创可运行 fixture（保存为 result_demo.py，Python 3.11.8）</summary>

```python
import hashlib
import html
import json
import secrets
import sqlite3
import tempfile
from pathlib import Path

PAGE = 50


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()


def public_row(raw):
    # Positive allowlist; never copy an unknown/nested source field to any consumer.
    if (type(raw['id']) is not int or type(raw['amount']) is not int
            or type(raw['label']) is not str or len(raw['label']) > 80):
        raise ValueError('row schema rejected')
    return {key: raw[key] for key in ('id', 'label', 'amount')}


def channels(value):
    # Pure projections of an ALREADY authorized and sanitized value; no fetching here.
    fields = {'schema_version', 'rows', 'offset', 'returned', 'total', 'truncated',
              'availability', 'result_ref', 'next_cursor'}
    if (set(value) != fields or type(value['schema_version']) is not int
            or value['schema_version'] != 1 or type(value['rows']) is not list
            or any(type(value[k]) is not int or value[k] < 0 for k in ('offset', 'returned', 'total'))
            or value['returned'] != len(value['rows'])
            or value['offset'] + value['returned'] > value['total']
            or type(value['truncated']) is not bool
            or value['truncated'] != (value['returned'] != value['total'])
            or value['availability'] not in ('inline_all', 'paged_snapshot', 'discarded')
            or any(value[k] is not None and type(value[k]) is not str for k in ('result_ref', 'next_cursor'))):
        raise ValueError('value schema rejected')
    for row in value['rows']:
        if set(row) != {'id', 'label', 'amount'} or row != public_row(row):
            raise ValueError('value schema rejected')
    value = json.loads(pack(value))
    preview = dict(value, channel='model_text', rows=value['rows'][:PAGE])
    preview['returned'] = len(preview['rows'])
    preview['truncated'] = preview['returned'] != value['total']
    cells = ''.join('<tr>' + ''.join('<td>' + html.escape(str(row[k])) + '</td>'
                    for k in ('id', 'label', 'amount')) + '</tr>' for row in preview['rows'])
    caption = f"{preview['returned']}/{value['total']} rows; truncated={preview['truncated']}"
    return {'value': value, 'model_text': pack(preview).decode(),
            'ui_html': '<p>' + html.escape(caption) + '</p><table>' + cells + '</table>'}


class Results:
    def __init__(self, db, folder, grants, clock):
        self.db, self.folder, self.grants, self.clock = db, Path(folder), grants, clock
        self.folder.mkdir()
        self.refs, self.cursors, self.positions = {}, {}, {}
        self.disk_reads = 0

    def authorized(self, who):
        # who is supplied by a trusted host after authentication, NOT a client claim.
        grant = self.grants.get(who) if type(who) is str else None
        if grant is None or not grant[3]:
            raise PermissionError('not authorized or unavailable')
        return grant[:3]  # tenant, subject, policy revision

    def cursor_for(self, ref, offset):
        key = (ref, offset)
        if key not in self.positions:
            token = secrets.token_hex(16)
            self.positions[key] = token
            self.cursors[token] = key
        return self.positions[key]

    def page(self, rows, offset, limit, availability, ref=None):
        selected = rows[offset:offset + limit]
        following = offset + len(selected)
        cursor = self.cursor_for(ref, following) if ref and following < len(rows) else None
        return {'schema_version': 1, 'rows': selected, 'offset': offset,
                'returned': len(selected), 'total': len(rows),
                'truncated': len(selected) != len(rows),
                'availability': availability, 'result_ref': ref, 'next_cursor': cursor}

    def query(self, who, mode='paged'):
        owner = self.authorized(who)
        if mode not in ('full', 'paged', 'cut'):
            raise ValueError('invalid mode')
        # Fixed query, parameters and row scope; only the synthetic database is used.
        raw = self.db.execute('SELECT id,label,amount,private_note FROM records '
                              'WHERE tenant=? ORDER BY id', (owner[0],)).fetchall()
        rows = [public_row(dict(r)) for r in raw]
        if mode == 'full':
            return channels(self.page(rows, 0, len(rows), 'inline_all'))
        if mode == 'cut':
            return channels(self.page(rows, 0, PAGE, 'discarded'))
        ref = secrets.token_hex(16)
        path = self.folder / (ref + '.json')  # No caller-supplied path.
        payload = pack({'schema_version': 1, 'rows': rows})
        try:
            with path.open('xb') as file:
                file.write(payload)
        except OSError:
            path.unlink(missing_ok=True)
            raise RuntimeError('result storage unavailable') from None
        # Publish only AFTER a successful write/close; stored rows are already sanitized.
        self.refs[ref] = {'owner': owner, 'expires': self.clock() + 30,
                          'path': path, 'sha': hashlib.sha256(payload).hexdigest()}
        return channels(self.page(rows, 0, PAGE, 'paged_snapshot', ref))

    def read(self, who, ref, cursor=None):
        owner = self.authorized(who)
        saved = self.refs.get(ref) if type(ref) is str else None
        if not saved or saved['owner'] != owner or self.clock() >= saved['expires']:
            raise PermissionError('not authorized or unavailable')
        if cursor is None:
            offset = 0
        elif type(cursor) is str and self.cursors.get(cursor, (None,))[0] == ref:
            offset = self.cursors[cursor][1]
        else:
            raise ValueError('invalid cursor')
        try:
            self.disk_reads += 1
            payload = saved['path'].read_bytes()
        except OSError:
            raise LookupError('result unavailable') from None
        if hashlib.sha256(payload).hexdigest() != saved['sha']:
            raise LookupError('result unavailable')
        snapshot = json.loads(payload)
        return channels(self.page(snapshot['rows'], offset, PAGE, 'paged_snapshot', ref))


def seed(db):
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE records(tenant TEXT,id INTEGER,label TEXT,amount INTEGER,private_note TEXT)')
    rows = [('A', i, '<script>fixture</script>' if i == 1 else f'item-{i}', i,
             f'SYNTHETIC-SECRET-A-{i}') for i in range(1, 1201)]
    rows += [('B', 1, 'other-tenant', 9999, 'SYNTHETIC-SECRET-B-1')]
    db.executemany('INSERT INTO records VALUES(?,?,?,?,?)', rows)
    db.commit()


def consume_all(api, who, response):
    # Original program, not generated code or a Code Mode sandbox.
    value = response['value']
    rows = list(value['rows'])
    while value['next_cursor'] is not None:
        value = api.read(who, value['result_ref'], value['next_cursor'])['value']
        rows.extend(value['rows'])
    return {'rows': len(rows), 'sum': sum(r['amount'] for r in rows),
            'complete': len(rows) == value['total']}


def demo():
    with tempfile.TemporaryDirectory(prefix='yao382-') as folder:
        db = sqlite3.connect(str(Path(folder) / 'synthetic.db'))
        try:
            seed(db)
            grants = {'alice': ('A', 'alice', 1, True), 'bob': ('B', 'bob', 1, True)}
            now = [0]
            api = Results(db, Path(folder) / 'spill', grants, lambda: now[0])
            report = {}
            for mode in ('full', 'paged', 'cut'):
                response = api.query('alice', mode)
                value = response['value']
                report[mode] = {'direct_rows': len(value['rows']),
                    'direct_sum': sum(r['amount'] for r in value['rows']),
                    'model_rows': json.loads(response['model_text'])['returned'],
                    'ui_rows': response['ui_html'].count('<tr>'),
                    'after_explicit_reads': consume_all(api, 'alice', response)}
            return report
        finally:
            db.close()


if __name__ == '__main__':
    print(json.dumps(demo(), ensure_ascii=False, indent=2))
```

</details>

运行 `python result_demo.py` 输出上述三种模式的计数与总和，并关闭数据库、删除本次临时目录。验证环境为 Python 3.11.8、实际链接 SQLite 3.19.3、macOS arm64（2026-09-16）；这里记录的是本机环境，不推荐把此旧 SQLite 版本作为生产部署选择。独立验证脚本从本文提取代码，检查三个通道及 24 页脱敏、游标/权限/TTL、UI 纯投影与转义、存储失败、快照损坏、0/1/49/50/51/1200 行边界，并核对题库双索引。

示例边界：`who` 来自可信宿主的已认证上下文，测试中的字符串不是可让客户端自行声称身份的认证方案；程序只通过交付值与读取接口消费数据。把所有对象放在同一个 Python 进程里不构成 Code Mode 沙箱，本文不证明恶意生成代码无法访问宿主文件。读取每页时会载入整个合成快照再切片，仅验证契约，不是生产分页性能实现；固定行宽和 50 行也不是通用 Token/字节预算，实际还要限制页字节、总读取成本和调用次数。本例不做并发权限变更的原子保证、跨进程引用恢复、磁盘加密或物理删除服务；文件只在本次临时目录生命周期内保留，30 秒 TTL 使用虚拟时钟测试。hash 检测相对于可信内存元数据的文件变化，不认证恶意存储方。

## 常见误区

- **“把展示文本里的敏感列删掉就脱敏了。”** 程序 value、spill、缓存或日志可能仍有原字段；要在分流前处理批准值，并验证所有交付通道。
- **“UI 显示 50 行，所以 Code Mode 也只能读 50 行。”** 看它实际拿到的 value，以及是否有可用且获授权的读取入口；本例三种模式有三个不同答案。
- **“total=1200、truncated=true，就一定能读回全部。”** total 不包含数据，truncated 不保证存在存档；最后一页也可能 truncated=true，却没有下一页。
- **“不透明引用、权限检查和撤销等于收回所有副本。”** 引用不是授权；检查控制未来交付，已经交出的副本与过期后的物理数据还需分别治理。

## 延伸 / 追问

**如果程序必须算全量均值，但只拿到 cut 模式的 50 行怎么办？** 先拒绝把样本均值称为全量均值。要求一个受授权的全量聚合工具、改用可分页快照，或明确只做样本统计；不能靠 total 给未见的行补值。

**权限在第 3 页读取前被撤销，前两页怎么算？** 后续 read 应在读存储前拒绝，程序把当前聚合标为 incomplete。先前已交付的数据仍可能在内存中，不能宣称已收回；因此敏感任务应尽量在服务端聚合，只返回最小必要结果。

**为什么 UI 的“加载更多”不应该藏在 renderer 中？** 纯投影应可重放且无 I/O。加载更多是另一次有权限、预算、失败和过期语义的操作，成功后再把新批准值交给 renderer；否则一次重渲染都可能额外查询、绕过预算或改变看到的数据。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定版本 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/dsh-10.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-10.html)、[slides/dsh-13.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-13.html)、[slides/10-5.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/10-5.html)。仅作为学习线索；课程所述其他运行时的 value 生命周期、spill 回退或 UI 分类未作为本文已验证实现，不复制其 AGPL 正文、代码或图片。
- Model Context Protocol，**2025-06-18** 版规范，固定 commit `cd0623765886c8cc282e3e5e1a03ab7469055fab`：[Tools：Structured Content、Output Schema、Security Considerations](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/docs/specification/2025-06-18/server/tools.mdx)、[Resources：读取、列表分页和权限](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/docs/specification/2025-06-18/server/resources.mdx)、[schema.ts：CallToolResult / Tool](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/schema/2025-06-18/schema.ts)、[该快照 LICENSE](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/LICENSE)。该快照注明许可证过渡及不同贡献的适用条款；本文链接规范并独立解释，不搬运实现。没有运行 MCP server/client，fixture 的 value 与 read 不是 MCP 自动提供的隔离或 SQL 分页保证。
- Python Software Foundation，CPython **v3.11.8**：[sqlite3 文档](https://github.com/python/cpython/blob/v3.11.8/Doc/library/sqlite3.rst)（参数绑定与结果获取）、[html.escape](https://github.com/python/cpython/blob/v3.11.8/Doc/library/html.rst)（动态文本转义）、[许可证](https://github.com/python/cpython/blob/v3.11.8/LICENSE)。
