---
id: engineering-0033
title: Coding Agent 如何在用户或其他 Agent 同时改文件时安全编辑，何时用 patch、精确替换或 AST？
category: engineering
tags: [coding-agent, optimistic-concurrency, file-editing, patch, ast]
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

Coding Agent 如何在用户或其他 Agent 同时改文件时安全编辑，何时用 patch、精确替换或 AST？请推演“读完后用户改一字再编辑”和“同名标识符出现在注释、字符串与不同作用域代码中”，说明版本检查、定位和语义校验各解决什么问题。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**一次编辑要绑定读到的版本，在提交处重新核对，并明确修改的范围与语义。** 先读约束证明存在一次观测；版本守卫判断这份观测是否仍能作为写入基线；patch、字符串匹配或 AST 负责生成候选修改。三者不能互相替代。

[agent-0032](agent-0032-parallel-tool-calling.md) 讨论并行工具的一致性，[engineering-0001](engineering-0001-redis-distributed-lock-failover.md) 讨论协调与 fencing。本题聚焦本地文件的观测版本及结构化修改，不将某个 Coding Agent 的工具文法或课件中的实现习惯当通用规范。

### 1. “读过”与“现在可写”是两个判定

| 信息 | 能回答的问题 | 不能据此推断 |
| --- | --- | --- |
| 由编辑服务记录的 read receipt | 哪个文件、哪个内容版本、什么观察范围被读过；能否追溯编辑基线 | 模型说“读过了”不是凭证；receipt 本身也不授予写权限 |
| 内容 hash / 精确字节、资源版本号 | 当前内容与基线是否一致；受控版本号还能识别部分 ABA | size/mtime 相同不保证字节相同；hash 不证明作者身份或所有中间写入历史 |
| hunk / old string / AST 节点位置 | 候选改动以哪段已知内容为依据 | 匹配成功不代表仍是旧版本，也不代表符号语义正确 |
| 提交结果与回读 | 写入了哪份候选、哪些文件成功、是否需要恢复 | 一次成功响应不冻结之后的文件，也不自动等于断电后仍持久 |

可采用这样的流程：读取并登记基线 → 从该不可变快照生成候选、检查定位和语法 → 展示 diff → 在实际写入边界比较当前版本 → 成功才提交；冲突则保留当前文件，重新读取、分析差异、重建计划。不能把旧计划的 expected version 直接改成新值，或者冲突后自动退化成整文件覆盖。

生产 receipt 应由可信服务绑定目标和调用上下文；展示给模型的行号、窗口或截断摘要不是完整内容证据。窗口读取只代表观察了该范围，不能推出模型理解了整份文件。写入权限与路径策略也须另行执行。下面的 fixture 只做全文件读取，用同一进程中的对象登记示意 receipt，不实现生产认证。

### 2. patch、精确替换和 AST 怎么选

| 方案 | 适合的修改 | 代价、必须校验的内容与不适用场景 |
| --- | --- | --- |
| 带上下文的 patch / hunk | 同一文件多个局部修改，需清楚展示前后差异 | 检查旧内容、上下文、位置、重叠和整份候选；行号可能偏移，重复锚点可能歧义。不同 patch 工具的搜索/fuzz/空白策略不同，不适合把“贴得上”当符号定位 |
| 精确替换 | 一个有足够上下文、能唯一识别的文字片段 | old string 为空、零命中或多处命中应明确处理；不能默选第一处，也不能偷偷启用 replace_all。不适合跨作用域变量重命名 |
| AST / 保留文本的语法树 + 符号分析 | 修改语法节点、批量结构重构；结合语言服务做绑定明确的 rename | 需要相应语言/版本、作用域、引用与类型信息；AST 本身不等于符号表，打印后也未必保留注释/格式。不适合用“按节点拼写替换”承诺动态语言或跨项目引用都正确 |

无论选哪种方案，都要绑定同一基线版本、保留修改意图并检查最终 diff。若已有无冲突基线和当前版本，可显式尝试三方合并；冲突或意图不清时让调用方重新决策，不把 fuzzy match 当自动授权覆盖。

固定 Git v2.46.0 文档中，`git apply --check` 只检查当前工作树/index 是否可应用，不写入；`--index` 还要求相关 index 与工作树内容、mode 等一致；`--reject` 会允许适用部分落地，与默认某 hunk 不适用时整份拒绝不同。这些都是该命令的条件和模式，不是任意编辑工具的共同语义，也不能将先 `--check` 后 `apply` 两个调用当成对外部写者的原子 CAS。

### 3. 两个具体例子

下面是自制 `sample.py`，其中全局变量、函数参数、注释和字符串都出现 `count`：

```python
# count is global
count = 1
def bump(count):
    return count + 1
label = "count"
answer = count
```

**例 A：用户只改注释里的一个字母。** Agent 读到内容 A，计划将唯一片段 `count = 1` 改成 `count = 2`；用户随后将 `global` 改为 `Global`，得到 B。旧替换片段在 B 里仍然存在，单靠匹配可以成功，但完整基线已经过期。

| 步骤 | 本 fixture 的实际判断 |
| --- | --- |
| read A | 服务记录文件名、A 的原始字节和 revision=0；向调用方返回 receipt、文本和 `(revision, hash)` |
| prepare | 仅在 A 上定位唯一片段并编译候选，产生只读 diff 计划；这一步不承诺磁盘仍是 A |
| 用户写 B，再 commit 旧计划 | 当前字节不等于 A，返回 `stale_version`，B 保持不变，即使 size 和恢复后的 mtime 与 A 相同也拒绝 |
| 重新 read B 并重建计划 | 候选保留 `Global`，只改赋值；提交成功后 revision=1，结果 hash 标识所写内容 |

代码中的版本条件比较完整字节和同一服务维护的 revision，hash 用作内容标识。两个调用方读到同一版本后，先提交者成功，后提交者冲突。合作写者通过同一服务完成 A→B→A 时 revision 已增加，旧 receipt 仍失效；外部写者绕过账本完成 A→B→A，则这份内容比较无法识别中间历史，不能声称检测了所有变化。

**例 B：把“替换拼写”误当重命名。** 对全文执行 `replace('count','total')` 会同时修改注释、字符串和不同作用域的代码；这只有在任务明确要求改全部文字时才符合意图。受守卫的精确替换遇到多个 `count` 返回 `ambiguous`；改用唯一的 `count = 1` 可以限定一处赋值，却不意味着其它引用都该随之变化。

fixture 另提供一个故意受限的 `syntax_only_rename`：只把 AST 的 `Name.id=count` 改为 `total`。它保留字符串常量，但 `ast.arg` 参数仍叫 count；函数体的 `return total + 1` 因而读取全局 total，原本读的是局部参数。结果仍能编译，`symtable` 的实际检查却显示 count 仍为参数、total 变为全局引用。它不是可交付的符号 rename；本文仅将它作为反例，不用它写文件。

可靠重命名要先确定目标声明与绑定，再修改该符号的引用，处理 shadowing、属性、import、反射和字符串约定等语言特例，检查类型/行为测试。注释是否同步要看语义，不能无差别删除或替换。CPython v3.11.8 明确说明 `ast.parse` 不做全部编译检查、`ast.unparse` 的文本不一定等于原文；有语法树不等于保留格式或正确重构。

### 4. 谁能保证“比较后没有人插进来”

| 机制 | 本文限定的保证 | 剩余边界 |
| --- | --- | --- |
| 同一个 Editor 实例的 lock | 合作调用者在比较当前字节/revision 到替换文件期间串行 | 别的实例、进程或编辑器若不走它，这把锁不约束对方 |
| 写入前 hash / 字节检查 | 发现检查时已经发生的内容分歧 | 检查后再写存在窗口；不自动变成文件系统条件写 |
| 同目录临时文件 + `os.replace` | 先准备完整候选，再切换目录项；固定 Python 文档说明成功 rename 的原子性及跨文件系统失败可能 | 不校验目标当前版本，不是多文件事务；不证明 fsync/断电持久性、所有文件属性或旧打开句柄都同步切换 |
| 统一资源所有者 / 存储端条件提交 | 在所有写者都受该边界约束时，将版本比较和写入作为一次决定 | 需要真实执行这个约束；若任意外部写者仍可直接写原文件，应改用受控副本、合并流程或诚实报告可能冲突 |

负例 `external_gap` 在自建文件上依次执行：持有自己的 lock → hash 对上 A → 模拟不配合的写者写 B → rename 覆盖为候选 C。实跑得到 `foreign_write_lost=true`，说明检查与 rename 之间确有逻辑窗口；这是有意展示的失败结果，不是把它包装成安全提交。它没有操纵用户文件，也不是跨进程攻击实验。

若不能控制所有写者，常见选择是在专属 worktree/副本上生成可审阅差异，再由版本化合并边界接入。worktree 隔离减少相互覆盖，不等于最终合并没有冲突。多文件操作还要区分“所有候选预检通过”与“所有文件作为一个事务提交”，失败后应报告实际落地范围，不能只返回一个含糊的整体失败。

### 5. 原创 fixture 与可复跑边界

下列实现固定 Python 3.11.8，只读取专属目录中 allowlist 内的普通 `.py` 文件。采用 UTF-8、64,000-byte 教学上限和最多 100 个结构化 hunks；不实现 Git unified diff parser、fuzz、跨文件编辑或新文件创建。hunk 坐标来自同一旧快照，要求顺序不重叠、旧行完全匹配，先全部在内存中计算，后反向应用坐标；任一失败不写原文件。

`Receipt` / `Plan` 是进程内登记句柄，不是可持久化、可跨进程认证的 capability。ledger/revision 不跨重启保留。成功仅说明本次 replace 返回；调用方可回读确认结果，但此后仍可能被改。fixture 保留普通 mode 和精确替换未涉及的换行，不保留所有 ACL/xattr/所有者属性；lstat/open 也没有解决恶意 namespace 竞态。临时目录独占是实验前提，不能把这段代码用于任意不可信文件作为沙箱。

<details>
<summary>展开单文件版本守卫、精确替换、结构化 hunk 与两个反例</summary>

```python
# file: edit_fixture.py
"""Original single-file teaching editor. Only use fresh, owned temporary roots."""
import ast
from dataclasses import dataclass
import difflib
import hashlib
import os
from pathlib import Path
import stat
import symtable
import tempfile
import threading

LIMIT = 64_000


class Refused(Exception):
    pass


class Receipt:
    __slots__ = ()


class Plan:
    __slots__ = ()


@dataclass(frozen=True)
class Observed:
    name: str
    raw: bytes
    revision: int


@dataclass(frozen=True)
class Hunk:
    start: int                 # Zero-based coordinate in the observed ORIGINAL.
    before: tuple              # Include context; context-free insertion is unsupported.
    after: tuple


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    if len(raw) > LIMIT:
        raise Refused('too_large')
    try:
        return raw.decode('utf-8')
    except UnicodeError as exc:
        raise Refused('invalid_encoding') from exc


def checked_source(text):
    if type(text) is not str:
        raise Refused('invalid_text')
    try:
        raw = text.encode('utf-8')
    except UnicodeError as exc:
        raise Refused('invalid_encoding') from exc
    decode(raw)
    try:
        compile(text, '<synthetic-source>', 'exec')  # Compile only, never execute.
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise Refused('syntax_invalid') from exc
    return raw


def exact(text, old, new):
    if type(old) is not str or not old or type(new) is not str:
        raise Refused('invalid_edit')
    hits, start = [], 0
    while (found := text.find(old, start)) >= 0:
        hits.append(found)
        start = found + 1      # Count overlapping matches too.
    if len(hits) != 1:
        raise Refused('no_match' if not hits else 'ambiguous')
    start = hits[0]
    return text[:start] + new + text[start + len(old):]


def patch_lines(text, hunks):
    if type(hunks) is not tuple or not hunks or len(hunks) > 100:
        raise Refused('invalid_hunks')
    lines, edits, end = text.splitlines(keepends=True), [], 0
    for h in hunks:            # Caller supplies original-coordinate order.
        if type(h) is not Hunk or type(h.start) is not int or h.start < end:
            raise Refused('unordered_or_overlapping_hunk')
        if type(h.before) is not tuple or not h.before or type(h.after) is not tuple:
            raise Refused('invalid_hunk_lines')
        for line in h.before + h.after:
            if type(line) is not str or not line or line.splitlines(keepends=True) != [line]:
                raise Refused('invalid_hunk_lines')
        end = h.start + len(h.before)
        if tuple(lines[h.start:end]) != h.before:
            raise Refused('hunk_context_mismatch')
        edits.append(h)
    for h in reversed(edits):  # Earlier coordinates cannot shift later edits.
        lines[h.start:h.start + len(h.before)] = h.after
    return ''.join(lines)


def replace_file(path, raw):
    """Same-directory rename; no fsync, multi-file transaction or external-writer CAS."""
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, temp = tempfile.mkstemp(prefix='yao395-stage-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            os.fchmod(out.fileno(), mode)
            if out.write(raw) != len(raw):
                raise OSError('short_write')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class Editor:
    """All cooperating writers must use THIS instance. This is not a sandbox."""
    def __init__(self, root, names):
        self.root = Path(root).resolve(strict=True)
        if not names or any(type(n) is not str or not n.endswith('.py') or
                            Path(n).name != n or n in ('.', '..') for n in names):
            raise Refused('invalid_scope')
        self.names = frozenset(names)
        self.revisions = dict.fromkeys(self.names, 0)
        self.lock = threading.Lock()
        self.reads, self.plans = {}, {}

    def path(self, name):
        if name not in self.names:
            raise Refused('outside_scope')
        p = self.root / name
        try:
            info = p.lstat()
        except FileNotFoundError as exc:
            raise Refused('missing_file') from exc
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Refused('unsupported_file_kind')
        # Owned flat directory; this lstat/open pair does not defeat namespace races.
        return p

    def bytes(self, name):
        with self.path(name).open('rb') as source:
            raw = source.read(LIMIT + 1)
        decode(raw)
        return raw

    def read(self, name):
        with self.lock:
            raw = self.bytes(name)
            receipt = Receipt()
            self.reads[receipt] = Observed(name, raw, self.revisions[name])
            return receipt, decode(raw), (self.revisions[name], sha(raw))

    def prepare(self, receipt, kind, *args):
        with self.lock:
            if type(receipt) is not Receipt or receipt not in self.reads:
                raise Refused('read_required')
            observed = self.reads[receipt]
        text = decode(observed.raw)
        if kind == 'exact':
            candidate = exact(text, *args)
        elif kind == 'hunks':
            candidate = patch_lines(text, *args)
        else:
            raise Refused('unsupported_strategy')
        raw = checked_source(candidate)
        if raw == observed.raw:
            raise Refused('no_change')
        plan = Plan()
        with self.lock:
            self.plans[plan] = (observed, raw)
        return plan

    def preview(self, plan):
        with self.lock:
            if type(plan) is not Plan or plan not in self.plans:
                raise Refused('plan_required')
            observed, candidate = self.plans[plan]
        return ''.join(difflib.unified_diff(decode(observed.raw).splitlines(True),
            decode(candidate).splitlines(True), fromfile=observed.name, tofile=observed.name))

    def commit(self, plan):
        with self.lock:
            if type(plan) is not Plan or plan not in self.plans:
                raise Refused('plan_required')
            observed, candidate = self.plans[plan]
            current = self.bytes(observed.name)
            if self.revisions[observed.name] != observed.revision or current != observed.raw:
                raise Refused('stale_version')
            replace_file(self.path(observed.name), candidate)
            self.revisions[observed.name] += 1
            del self.plans[plan]
            return dict(status='replaced', revision=self.revisions[observed.name], sha256=sha(candidate))


SOURCE = '# count is global\ncount = 1\ndef bump(count):\n    return count + 1\nlabel = "count"\nanswer = count\n'


def syntax_only_rename(text, old, new):
    """Deliberately NOT a symbol rename: Name nodes exclude parameters (ast.arg)."""
    if not new.isidentifier():
        raise Refused('invalid_identifier')
    class Names(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == old:
                node.id = new
            return node
    tree = Names().visit(ast.parse(text))
    result = ast.unparse(tree) + '\n'
    checked_source(result)
    return result


def external_gap(path):
    """Owned counterexample to hash-check + rename, NOT a safe commit helper."""
    before = path.read_bytes()
    candidate = before.replace(b'count = 1', b'count = 3')
    local_lock = threading.Lock()
    with local_lock:
        assert sha(path.read_bytes()) == sha(before)
        # Simulated non-cooperating writer after the last comparison, before rename.
        foreign = before.replace(b'global', b'Global')
        path.write_bytes(foreign)
        replace_file(path, candidate)
    return dict(foreign_write_lost=path.read_bytes() == candidate and path.read_bytes() != foreign,
                same_local_lock_held=True)


def demo():
    with tempfile.TemporaryDirectory(prefix='yao395-owned-', dir=Path(__file__).resolve().parent) as name:
        path = Path(name) / 'sample.py'; path.write_text(SOURCE, encoding='utf-8')
        editor = Editor(name, ('sample.py',))
        receipt, _, _ = editor.read('sample.py')
        plan = editor.prepare(receipt, 'exact', 'count = 1', 'count = 2')
        foreign = SOURCE.replace('global', 'Global'); path.write_text(foreign, encoding='utf-8')
        try:
            editor.commit(plan)
        except Refused as exc:
            conflict = str(exc)
        else:
            raise AssertionError('stale write accepted')
        assert path.read_text() == foreign
        receipt, _, _ = editor.read('sample.py')
        plan = editor.prepare(receipt, 'exact', 'count = 1', 'count = 2')
        editor.commit(plan)
        assert path.read_text() == foreign.replace('count = 1', 'count = 2')
        renamed = syntax_only_rename(SOURCE, 'count', 'total')
        scope = symtable.symtable(renamed, '<synthetic>', 'exec').get_children()[0]
        result = dict(conflict=conflict, foreign_change_preserved=True, reread_edit_succeeded=True,
            literal_replace_changes_comment='# total' in SOURCE.replace('count', 'total'),
            ast_string_literal_preserved="'count'" in renamed,
            ast_parameter_still_local=scope.lookup('count').is_parameter(),
            ast_body_now_reads_global=scope.lookup('total').is_global())
        gap = Path(name) / 'gap.py'; gap.write_text(SOURCE, encoding='utf-8')
        result['external_gap'] = external_gap(gap)
    assert not Path(name).exists()
    result['owned_directory_removed'] = True
    return result


if __name__ == '__main__':
    import json
    print(json.dumps(demo(), indent=2))
```

</details>

将代码保存为 `edit_fixture.py`，运行 `python3 edit_fixture.py` 可复跑 demo。2026-09-16 实测：`conflict=stale_version`，`foreign_change_preserved=true`，`reread_edit_succeeded=true`；AST 反例的参数仍是 local，函数体的新名字为 global；外部写入窗口反例为 `foreign_write_lost=true`。

附件 `test_editing.py` 的 31 个测试通过（0 failures / 0 errors）：31 个测试目录清理，32 次拒绝路径原始字节检查，测试内及汇总 demo 各自验证目录删除。另覆盖旧/伪造 receipt、计划重放、合作与外部 ABA、重复/重叠匹配、第二个 hunk 失败不写入、错误位置不猜测、编译失败、路径/文件类型、同大小同 mtime 的字节变化、replace 异常清理和 mode/CRLF 保留。

实验使用确定顺序模拟交错，没有派发真实 Agent、运行真实并发写者或测试跨进程锁；只编译合成 Python，不执行生成代码。不访问业务文件/会话/凭据，不改运行时或其他 Agent 工作区，不验证生产性能、恶意编译输入的资源隔离、通用文件系统 CAS、断电持久性或完整语言服务重命名。

## 延伸 / 追问

- **用户改的只是注释，能否自动忽略版本冲突？** 全文件守卫应先拒绝。可以重新读取后比较差异，确认与意图不冲突，再产生基于新版本的计划；不能偷偷把旧凭证升级成新版本。更细粒度的范围守卫需要明确其它上下文依赖。
- **没读过的新文件怎么创建？** “未读”不是“文件不存在”。采用独立的 create-if-absent 操作和路径权限检查，拒绝覆盖已存在目标；本 fixture 只编辑既有文件，没有实现创建协议。
- **AST 转换后能编译，为什么还可能改错行为？** 编译能发现部分语法/作用域违规，但合法代码也可能引用了错误绑定。要检查目标符号及调用行为，不能以 AST 节点类型或拼写替代语义关系。
- **加锁、hash、atomic rename 都用了，为什么还不能保证用户修改不丢？** 只有遵守同一提交边界的写者才被串行化。任意外部进程仍可能在最后比较后写入；要么收拢写权限到资源所有者，要么使用副本/合并并如实暴露剩余窗口。

## 常见误区

- **“字符串替换就是符号重命名。”** 注释、字符串、不同作用域的同名对象没有共同的 rename 语义；AST 按拼写替换也可能混淆绑定。
- **“这个会话读过文件，所以现在可以覆盖。”** receipt 只记录曾经观察到的版本；提交必须重新检查，旧计划不可套用新版本号。
- **“hunk 匹配或 `git apply --check` 通过，就没有并发冲突。”** 它们只说明当前定位/适用条件，不冻结之后的文件，也不证明修改意图正确。
- **“atomic rename 表示整条编辑链原子、持久。”** 单次目录项替换、版本条件提交、多文件事务和断电持久性是不同保证。

## 参考

- 洛小山《AI 产品从入门到精通》learn-ai，固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/dsh-14.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-14.html)、[slides/codex-21.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-21.html)、[slides/ds-7.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/ds-7.html)、[slides/vibe-4.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-4.html)。仅作学习线索；独立组织问答与 fixture，不搬运 AGPL 正文/代码/图片。课程涉及各产品的观察插件、错误码、匹配层数、私有或 restored 源码行为未在本文作一手确认，不沿用为通用保证；AST 保格式及本地临界区排除任意外部写者等推断也不采用。
- Git **v2.46.0**：[Documentation/git-apply.txt](https://github.com/git/git/blob/v2.46.0/Documentation/git-apply.txt)，`--check`、`--index`、`--3way`、`--reject`、`-C` 与 `--unidiff-zero` 的固定文档定义。本文结构化 hunk 是原创教学格式，不是该命令的实现或测试；GPL 源码/文档只阅读引用。
- CPython **v3.11.8**：[Doc/library/ast.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/ast.rst)，`Name`/`arg`、`NodeTransformer`、`parse` 与 `unparse` 的职责和限制；复杂 AST 输入可能触及解释器资源限制，编译不是隔离执行。
- CPython **v3.11.8**：[Doc/library/symtable.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/symtable.rst)，编译器符号表用于分析标识符作用域，本例用其核对 local/global 变化，不实现跨项目语言服务。
- CPython **v3.11.8**：[Doc/library/os.rst · replace](https://github.com/python/cpython/blob/v3.11.8/Doc/library/os.rst#L2466)，目标替换、跨文件系统限制和成功 rename 的原子性表述；该接口没有 expected-version 参数。实验日期 2026-09-16，未测性能或生产耐久性。
