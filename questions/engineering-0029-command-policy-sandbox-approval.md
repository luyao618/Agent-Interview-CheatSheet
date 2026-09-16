---
id: engineering-0029
title: 命令策略、沙箱与人工审批各管什么，如何避免组合命令和授权范围扩大绕过检查？
category: engineering
tags: [command-policy, sandbox, approval, parsing, authorization, scope]
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

命令策略、沙箱与人工审批各管什么，如何避免组合命令和授权范围扩大绕过检查？请对“只读命令后接写操作”和“路径含空格”分别给出完整判定链，解释一次批准与持久规则的差别。

## 答案 · GPT-6

**命令策略判断这次具体操作是否可自动执行、需审批或必须拒绝；审批提供范围明确的授权决定；沙箱及宿主权限限制获准进程实际能做什么。** 三者应共同约束执行，不能把命令首词、一次 allow 或一个“安全”标签当成完整权限证明。

可讲清的主线是：**接收原始请求 → 按执行语言解析结构 → 确定每段 argv、程序、路径与环境 → 逐段匹配策略并聚合 → 必要时取得绑定该请求的批准 → 在执行入口复核当前状态 → 以受限能力执行并记录结果**。没有可靠解释的部分不能从检查中删掉；执行的对象必须和检查、展示、批准的对象一致。一般隔离取舍见 [engineering-0011](engineering-0011-agent-code-execution-sandbox-tradeoff.md)，参数级风险评估见 [agent-0041](agent-0041-dynamic-tool-risk-assessment.md)，这里聚焦可测试的命令及授权边界。

### 1. 检查的是语义结构，不能只检查字符串开头

如果输入本来就是结构化 `argv`，应保留参数边界，通常不再把它拼成字符串交给 shell。若输入是 shell 脚本，则需要对应语言/版本的 parser：识别顺序连接、条件连接、管道、重定向及嵌套求值。`&&` 的右侧不是注释，`;` 后仍有动作，`cat a > b` 的写入来自重定向；只看到 cat 就判只读会漏掉实际能力需求。即使真正只读，也可能读出敏感数据，不能自动等同低风险。

每个可能执行的分段都要校验，且整条请求通过之前不要先启动第一个分段。这样可避免“先跑只读前半段，后面才发现拒绝”的不完整准入。某个条件分支可能不运行，并不意味着可以不检查；若产品选择在分支实际调度时检查，则必须把每次调度都置于强制网关下，不能检查完首段就把剩余脚本交给不受控 shell。

程序身份也要绑定：`git`、`/some/path/git`、同名替代程序、alias/function、`env ...` 或 `sh -c ...` 包装未必代表同一个动作。`PATH`、cwd、语言环境、配置文件、插件、解释器参数都可能改变行为。前缀匹配是策略的一部分，不能代替对参数、目的地、程序身份和副作用的判断。

| 方案 | 适用条件与收益 | 代价及不适用场景 |
| --- | --- | --- |
| 提供结构化工具或限制到小型命令语法 | 已知动作和参数 schema；可以确定目标、限制选项并直接调用受控执行器，审计较清楚 | 兼容性较低，不能假装支持任意 shell；复杂构建脚本可能需要独立受限任务入口 |
| 完整 shell parser 与受限执行环境结合 | 需要 shell 的组合能力；用 AST 保留调用、连接符、重定向和动态结构，再按策略处理 | 语言/平台差异和动态行为增加成本。静态分析结果不能证明任意脚本无副作用；不适合只靠几条正则就作免审放行 |

解析失败可选择拒绝，或将**完整原请求**升级到更严格的审核/隔离流程；后者也只能在宿主允许的能力内工作。不能把失败片段丢弃后宣称其余段安全。本文 fixture 选择拒绝未支持语法；Codex 固定版本的复杂脚本处理另见第5节，二者不等价。

### 2. 批准必须绑定执行对象，持久规则必须展示扩大了什么范围

建议一次批准绑定主体、任务/请求 ID、完整命令结构与参数、解析器版本、cwd、实际目标、程序身份、有效环境、沙箱档案及策略世代，并设置有效期或撤销条件。审批 UI 应展示完整脚本和解析后的参数数组、目标路径、环境变化、能力变化以及“仅本次/记住规则”的范围差异。模型说“用户已同意”不是批准记录。

路径要按实际 cwd 和文件系统规则解释；目录包含关系按路径组件判定，`/lab/outside` 不属于 `/lab/out`。符号链接、挂载、路径大小写与检查后替换都可能改变访问对象。词法归一化和检查一次 `realpath` 不能消除 TOCTOU；真实执行还需操作时的 OS 权限约束、合适的文件句柄/解析方式与策略复核。环境必须是执行器收到的有效环境，不能检查一个干净 env 后继承另一个包含启动脚本配置的环境。

| 授权方式 | 应绑定及展示的范围 | 失效/扩大范围时怎么办 |
| --- | --- | --- |
| 一次批准 | 当前请求的完整语义与执行上下文；原子领取一次执行资格 | 命令、参数、目标、主体、环境或策略发生变化时重新判定。超时/失败后的重试不是自动再获一次授权；领取一次也不证明业务 exactly-once |
| 持久规则 | 明确的参数前缀/选项约束、主体与项目、目标范围、程序和环境条件、策略来源；必要时含有效期 | “同类命令”可能包含新参数和新目标，必须审查正反例、冲突优先级和撤销机制。不能把一次批准自动写成宽泛 shell/解释器规则 |

持久规则也可以只是一条简单前缀规则，但那样就不能声称它自动包含 cwd、路径、参数上限等约束；这些须由其他策略或执行边界补齐。本文模拟的可复用规则更窄：绑定 context、字面 argv 前缀及目标子目录。它只驻留内存，用来验证匹配范围，**没有写入真实规则文件，也不提供跨进程持久化**。

审批与沙箱也不能简化成“批准后始终使用原沙箱”。平台可能允许经审批改用更宽的执行档案；此时应展示并复核实际能力变化。一个 allow 决定本身不能赋予宿主未授予的 OS 权限、解除不可覆盖的组织 deny，或替代数据库/业务系统的认证授权。若外层约束禁止该操作，批准不应触发绕过或偷偷换环境重试；若某次根本没应用 OS 沙箱，也不能把审批弹窗当成内核隔离。

### 3. 两个例子的完整判定链

以下全部是原创合成命令，**只交给 mock 执行器**。教学环境：虚构 cwd=`/lab`，显式 env=`LANG=C.UTF-8, PATH=/mock/bin`；cat/touch/rm 映射到固定的 mock 程序身份。读取只允许 `/lab` 内目标；写入只允许 `/lab/out` 内目标且需批准；删除被强制策略拒绝。每个程序只接受一个路径操作数，可加字面的 `--`。这些是实验合同，不是对真实 cat/touch/rm 的安全分级或系统权限设置。

| 输入与阶段 | 解析、路径和权限判定 | 实际 mock 结果 |
| --- | --- | --- |
| A：`cat "Team Docs/plan.txt" && touch out/result.txt` | 两段 argv 为 `['cat','Team Docs/plan.txt']`、`['touch','out/result.txt']`，连接符为 `&&` | 不能只检查首词 cat |
| A：逐段检查 | 目标分别为 `/lab/Team Docs/plan.txt`、`/lab/out/result.txt`；前者 allow，后者 prompt；聚合取更严格的 prompt | 审批前 `approval_required`，**0条 mock 动作**，首段也没启动 |
| A：批准、复核和领取 | 本次批准绑定完整请求 key；执行入口用当前 context 重算，核对一致后原子消费批准记录 | `mock_executed`，依次记录 read、write 共2条；相同批准再用一次返回 `approval_required`，不追加动作 |
| A 的拒绝变体：`cat read.txt; rm read.txt` | 两段分别 allow、deny；整体 deny，不是 prompt | `denied`，0条动作；假造 allow 或调用 mock 审批入口都不能撤销强制拒绝 |
| B：`cat "Team Docs/plan.txt"` | 引号保留空格的参数边界，argv 恰有2项；绑定 mock cat 身份与 cwd，解析目标 `/lab/Team Docs/plan.txt`，位于读取范围内 | plan 为 allow；若 dispatch，仅记录这一条 read |
| B 的错误变体：`cat Team Docs/plan.txt` | argv 为 `['cat','Team','Docs/plan.txt']`，变成两个操作数 | 本例单路径 schema 拒绝，原因 `arity/options`；不会自行把两个参数拼回一个路径 |

真实 cat 可以接收多个操作数，所以 B 的错误变体在真实系统中未必语法报错，而可能尝试读两份不同文件。审批展示和路径检查必须忠实反映实际 argv，不能按用户“可能想表达什么”偷偷修复。带引号的 `"notes;fake"` 中分号是文件名字符，不是命令分隔符；反过来，去掉引号也不能仍沿用旧批准。

实测反例中的错误策略 `script.split()[0] == 'cat'` 对 A 和删除变体都返回 true，而完整判定分别得到 prompt、deny；两例未获准时都是0条动作。这验证了首词规则的漏检形状，没有执行任何真实写入或删除。

### 4. 可运行的原创 fixture 与证据边界

本例先用引号状态扫描识别**引号外**的 `;`、`&&`，再用 `shlex.split` 解出每段字面 argv；这不是完整 Bash parser。明确拒绝管道、重定向、变量/命令替换、后台任务、控制流、未闭合引号、未引用通配符和换行；包装程序、环境赋值及未登记程序不能获得批准。限制输入4096 UTF-8 bytes、最多8段，是教学资源限制，不是生产性能保证。

路径只在虚构 POSIX 命名空间中作词法处理，拒绝 `..` 和合成 symlink 标记，不读取真实文件系统。程序身份中的 `@v1` 也是 mock 标签，不是可执行文件内容 hash。`approve_once` 与 `add_rule` 是受信宿主的模拟入口；它们没有验证真实审批人身份，模型文本不能被当成调用这些入口的授权依据。

审批记录由 Gate 持有；dispatch 不信任传入 Plan 的 steps/decision，会在同一把锁内重新生成当前计划、比较 key、消费一次批准并记录 mock 动作。规则增加/撤销也会使旧计划失效。这个锁只协调本模型的接口，不能同步真实文件系统或远端权限变化；生产还需在真实执行入口落实约束。

<details>
<summary>保存为 command_fixture.py：不调用 shell，不执行任何系统命令</summary>

使用 Python3.11.8，运行 `python3 command_fixture.py`；仅依赖标准库。输出包含两条示例判定链、一次批准的消费与重放结果、错误首词判定及 mock 动作列表。mock 动作总是假设成功，本文没有实现真实 `&&` 的失败短路、管道流转、事务或持久执行台账。

```python
# file: command_fixture.py
"""Original, deliberately small command language. Never executes an OS command."""
from dataclasses import asdict,dataclass
import hashlib,json,posixpath,shlex,threading
from pathlib import PurePosixPath


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


class Unsupported(ValueError):pass


def parse(script):
    # Only literal words/quotes/escapes and ; / &&. No expansion, pipes or redirects.
    if type(script) is not str or not script or len(script.encode())>4096:
        raise Unsupported('size/type')
    if any(ord(c)<32 or ord(c)==127 for c in script) or '$' in script or '`' in script:
        raise Unsupported('control/expansion')
    pieces=[];operators=[];start=0;i=0;quote=None
    while i<len(script):
        c=script[i]
        if c=='\\' and quote!="'":
            if i+1==len(script):raise Unsupported('trailing escape')
            i+=2;continue
        if quote:
            if c==quote:quote=None
        elif c in ("'",'"'):quote=c
        elif c in ';&':
            op='&&' if script[i:i+2]=='&&' else c
            if op=='&':raise Unsupported('background')
            pieces.append(script[start:i]);operators.append(op);i+=len(op);start=i;continue
        elif c in '|<>()*?[]{}#~':raise Unsupported('unsupported syntax')
        i+=1
    if quote:raise Unsupported('unclosed quote')
    pieces.append(script[start:])
    if len(pieces)>8:raise Unsupported('segment limit')
    commands=[]
    for piece in pieces:
        try:words=tuple(shlex.split(piece,posix=True))
        except ValueError as exc:raise Unsupported('tokenization') from exc
        if not words:raise Unsupported('empty segment')
        commands.append(words)
    return tuple(commands),tuple(operators)


@dataclass(frozen=True)
class Context:
    principal: str='synthetic-reader'
    workspace: str='demo-workspace'
    cwd: str='/lab'
    env: tuple=(('LANG','C.UTF-8'),('PATH','/mock/bin'))
    executable_ids: tuple=(('cat','/mock/bin/cat@v1'),('touch','/mock/bin/touch@v1'),('rm','/mock/bin/rm@v1'))
    read_root: str='/lab'
    write_root: str='/lab/out'
    policy_epoch: int=1
    filesystem_epoch: int=1
    symlinks: tuple=('/lab/link',)


def beneath(path,root):
    return PurePosixPath(path).is_relative_to(PurePosixPath(root))


def target_path(raw,ctx):
    if not raw or '..' in PurePosixPath(raw).parts or raw.startswith('//'):
        raise Unsupported('empty/parent/ambiguous path')
    path=posixpath.normpath(posixpath.join(ctx.cwd,raw))
    if any(beneath(path,link) for link in ctx.symlinks):
        raise Unsupported('synthetic symlink requires stronger resolver')
    return path


@dataclass(frozen=True)
class Step:
    argv: tuple
    executable: str
    target: str
    action: str
    decision: str
    reason: str


@dataclass(frozen=True)
class Plan:
    request_id: str
    script: str
    key: str
    steps: tuple
    operators: tuple
    decision: str


@dataclass(frozen=True)
class Rule:
    rule_id: str
    prefix: tuple
    target_root: str
    context_key: str


class Gate:
    def __init__(self,ctx=Context()):
        self.ctx=ctx;self.rules=();self.rule_epoch=0;self.once={};self.serial=0
        self.effects=[];self.lock=threading.RLock()

    def replace_context(self,ctx):
        with self.lock:self.ctx=ctx

    def _prepare(self,script,request_id):
        if type(request_id) is not str or not request_id:raise Unsupported('request id')
        ctx=self.ctx
        if (not ctx.cwd.startswith('/') or posixpath.normpath(ctx.cwd)!=ctx.cwd or
                dict(ctx.env).get('PATH')!='/mock/bin' or
                len(dict(ctx.env))!=len(ctx.env) or set(dict(ctx.env))!={'PATH','LANG'}):
            raise Unsupported('unbound cwd/environment')
        commands,ops=parse(script);rows=[];context_key=digest(asdict(ctx))
        for argv in commands:
            program=argv[0];exe=dict(ctx.executable_ids).get(program,'')
            if program not in ('cat','touch','rm') or not exe:
                rows.append(Step(argv,exe,'','unknown','deny','unknown program'));continue
            operands=argv[2:] if len(argv)>1 and argv[1]=='--' else argv[1:]
            if len(operands)!=1 or (len(argv)>1 and argv[1]!='--' and operands[0].startswith('-')):
                rows.append(Step(argv,exe,'','unknown','deny','arity/options'));continue
            path=target_path(operands[0],ctx);action={'cat':'read','touch':'write','rm':'delete'}[program]
            decision='allow' if action=='read' else 'prompt';reason='base read' if action=='read' else 'write needs approval'
            if action=='delete':decision='deny';reason='mandatory delete prohibition'
            elif not beneath(path,ctx.read_root) or (action=='write' and not beneath(path,ctx.write_root)):
                decision='deny';reason='host boundary'
            elif action=='write' and any(r.context_key==context_key and argv[:len(r.prefix)]==r.prefix and
                                         beneath(path,r.target_root) for r in self.rules):
                decision='allow';reason='scoped reusable rule'
            rows.append(Step(argv,exe,path,action,decision,reason))
        decision=max((r.decision for r in rows),key={'allow':0,'prompt':1,'deny':2}.get)
        key=digest(dict(request_id=request_id,script=script,context=asdict(ctx),
                        rule_epoch=self.rule_epoch,steps=[asdict(r) for r in rows],operators=ops))
        return Plan(request_id,script,key,tuple(rows),ops,decision)

    def prepare(self,script,request_id):
        with self.lock:return self._prepare(script,request_id)

    def _current(self,plan):
        current=self._prepare(plan.script,plan.request_id)
        if current.key!=plan.key:raise Unsupported('stale plan')
        return current  # never trust supplied steps or decision

    def approve_once(self,plan):
        # Trusted mock approver entry; model text cannot add an entry to this registry.
        with self.lock:
            current=self._current(plan)
            if current.decision!='prompt':raise Unsupported('not approvable')
            self.serial+=1;token=f'approval-{self.serial}'
            self.once[token]=current.key
            return token

    def add_rule(self,plan,prefix,target_root):
        # Separate trusted configuration action; an allow-once never calls this.
        with self.lock:
            current=self._current(plan)
            if (current.decision!='prompt' or len(current.steps)!=1 or type(prefix) is not tuple or
                    prefix not in (('touch',),('touch','--'))):raise Unsupported('invalid rule proposal')
            step=current.steps[0]
            root=target_path(target_root,self.ctx)
            if (step.argv[:len(prefix)]!=prefix or not beneath(root,self.ctx.write_root) or
                    not beneath(step.target,root)):raise Unsupported('rule scope exceeds reviewed target')
            self.serial+=1;rule=Rule(f'rule-{self.serial}',prefix,root,digest(asdict(self.ctx)))
            self.rules+= (rule,);self.rule_epoch+=1
            return rule.rule_id

    def revoke_rule(self,rule_id):
        with self.lock:
            self.rules=tuple(r for r in self.rules if r.rule_id!=rule_id);self.rule_epoch+=1

    def dispatch(self,plan,token=None):
        with self.lock:
            try:current=self._current(plan)
            except Unsupported:return dict(status='stale_or_invalid',executed=0)
            if current.decision=='deny':return dict(status='denied',executed=0)
            if current.decision=='prompt':
                if self.once.get(token)!=current.key:return dict(status='approval_required',executed=0)
                del self.once[token]  # atomic claim; no refund/automatic retry promised
            # Entire chain checked before the first mock effect; no shell, I/O or callbacks.
            for step in current.steps:
                self.effects.append(dict(request_id=current.request_id,argv=step.argv,
                                         executable=step.executable,target=step.target,action=step.action))
            return dict(status='mock_executed',executed=len(current.steps))


def view(plan):return asdict(plan)


def demo():
    gate=Gate();script='cat "Team Docs/plan.txt" && touch out/result.txt'
    plan=gate.prepare(script,'chain-1');before=gate.dispatch(plan)
    token=gate.approve_once(plan);after=gate.dispatch(plan,token);replay=gate.dispatch(plan,token)
    quoted=gate.prepare('cat "Team Docs/plan.txt"','spaces-1')
    bad_split=gate.prepare('cat Team Docs/plan.txt','spaces-2')
    denied=gate.prepare('cat "Team Docs/plan.txt"; rm "Team Docs/plan.txt"','deny-1')
    return dict(chain=view(plan),before_approval=before,after_once=after,replayed_once=replay,
                quoted=view(quoted),unquoted=view(bad_split),forbidden_chain=view(denied),
                naive_first_word_allows=script.split()[0]=='cat',effects=gate.effects)


if __name__=='__main__':print(json.dumps(demo(),ensure_ascii=False,indent=2))
```

</details>

2026-09-16实际运行：**20 个测试通过**。覆盖完整链准入、引号/转义空格、引号内分隔符、未支持 shell 语法、包装/环境赋值、选项与路径、目录组件边界、强制 deny、一次批准重放、参数/请求/context 变化、规则匹配与撤销、伪造 Plan 字段、输入上限和临时数据清理。两个并发领取线程已 join，只有一个取得本次执行资格；无外部超时取消兜底。唯一合成输入文件逐字节未变，专属临时目录已删除。

“20 tests 通过”表示这些原创反例和不变量符合声明合同，**不表示真实 Codex/其他 shell、OS 沙箱、持久规则、审批身份或远端 exactly-once 已验证**。先完整检查也不使整个组合命令具有事务性：真实执行若第二段失败，第一段的效果可能已发生；批准已被消费也不代表执行结果已可靠保存。应另外记录真实状态并处理幂等性/补偿。

### 5. 固定产品源码与教学策略分开

OpenAI 官方 Rules 文档说明规则匹配参数列表、允许简单命令链逐段评估，并区分复杂 shell 的处理。本文进一步核对 **Codex rust-v0.154.0**（2026-09-09发布），固定 commit `6b9826e3aa83b1a5947db50f4332cb9c65f1b340`：

- `shell-command/src/bash.rs` 的 `try_parse_word_only_commands_sequence` 和 `parse_shell_lc_plain_commands` 使用 tree-sitter，接受白名单节点及 `&&`、`||`、`;`、`|`，不支持的结构返回 None。它支持的语法比本文 fixture 多。
- `core/src/exec_policy.rs:876–904` 在无法得到可用拆分时保留原调用 argv；不是删掉看不懂的内容，也不是在该函数直接断言“整条命令禁止”。随后还要评估整个调用及 fallback。不要给通用 shell 包装器宽泛 allow，再期待内部每段总能被识别。
- `execpolicy/src/policy.rs` 的 `check_multiple_with_options` 收集各段匹配，`Evaluation::from_matches` 取严格程度的最大值；`decision.rs` 的顺序为 Allow、Prompt、Forbidden。未匹配时的 fallback 还由宿主上下文决定，不能从几条规则推断所有请求的默认结果。
- `core/src/exec_policy.rs:395–459` 把 Forbidden、Prompt、Allow 映射到执行审批要求；其中只有每个解析段都有显式 allow 匹配时，Allow 分支才把 `bypass_sandbox` 标为 true。这个具体字段也说明要区分可选择的内层执行档案与不可覆盖的外层边界，不能把“批准”和“仍在原沙箱”画等号。

这些结论来自指定函数及调用关系的阅读，**没有运行 Codex CLI 或读取本机真实 rules/Profile/Home 配置**。本文的完整 context key、一次批准消费、固定目录合同及可复用规则范围均为原创教学设计，不声称是 Codex 的实际批准缓存键。课程中的其他运行时习惯及未在一手源码中追踪的细节，不作为跨产品保证。

## 追问

**追问：只要每段都以一个允许的前缀开头，就能执行吗？**

不能直接推出。前缀后可能有改变动作的参数，重定向和嵌套执行可能不在普通 argv 中；环境和可执行文件身份也可能改变行为。还要满足参数、目标及当前宿主约束，并按产品对复杂结构的合同处理。

**追问：用户批准后 cwd 或 symlink 被改了，旧批准还有效吗？**

不能默认有效。重新绑定实际目标和执行环境，变化时重新判定；真实路径竞争还需要操作时的强制权限约束。仅比较显示路径、做字符串前缀匹配或引用旧 hash 都不够。

**追问：为什么持久规则风险比一次批准更难说明？**

它授权的是一类未来请求，通常允许参数变化、跨调用复用。应展示范围、增加必须不匹配的反例、限制来源和撤销权限；尤其解释器或脚本前缀可能代表大量未知行为。低频高风险动作通常更适合明确的一次批准。

**追问：用户点了 allow，宿主仍拒绝写入怎么办？**

保留实际拒绝，说明哪个能力或策略不满足。可以在授权范围内改用可行目标，或提交具体的管理员策略变更请求；不能悄悄切换执行环境或扩大批准。allow 也不证明任何业务操作已完成。

## 常见误区

- **“只看首词就能判断整条命令。”** 后续分段、参数、重定向、包装与环境都可能增加行为。
- **“按空格 split 就能得到路径。”** 引号和转义决定 argv；错误分割会改变授权对象。
- **“审批允许就能越过宿主硬边界。”** 审批决定、实际执行档案和外层强制权限是不同层；批准不能凭空创造能力。
- **“一次同意可以顺手变成持久 allow。”** 扩大到未来调用属于新的授权范围，须明确审查和记录。
- **“逐段检查完就是事务成功或 exactly-once。”** 准入、执行效果、结果记录、重试与补偿各有独立合同。

## 参考

以下来源核对于2026-09-16；答案、fixture 与测试独立编写。AGPL 课程只作学习线索，未搬运正文、代码或图片。

- 洛小山《AI 产品从入门到精通》，learn-ai 固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/codex-17.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-17.html)（规则与反例）、[slides/codex-18.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-18.html)（审批范围）、[slides/12-18.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/12-18.html)（权限链与执行边界）、[slides/dsh-15.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-15.html)（审批与沙箱线索）；[AGPL-3.0 LICENSE](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/LICENSE)。
- OpenAI 官方文档：[Rules](https://learn.chatgpt.com/docs/agent-configuration/rules) 与 [Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security)。原 developers.openai.com 文档入口在本次访问时重定向到此官方站点；网页会更新，本文的版本化源码结论以后一条固定 commit 为准。文档涉及具体模式/平台，不能当成当前宿主已启用某种防护的证据。
- OpenAI / Codex **rust-v0.154.0**，固定 `6b9826e3aa83b1a5947db50f4332cb9c65f1b340`：[bash.rs](https://github.com/openai/codex/blob/6b9826e3aa83b1a5947db50f4332cb9c65f1b340/codex-rs/shell-command/src/bash.rs#L21-L133)、[core exec_policy.rs](https://github.com/openai/codex/blob/6b9826e3aa83b1a5947db50f4332cb9c65f1b340/codex-rs/core/src/exec_policy.rs)、[policy.rs](https://github.com/openai/codex/blob/6b9826e3aa83b1a5947db50f4332cb9c65f1b340/codex-rs/execpolicy/src/policy.rs#L251-L288)、[decision.rs](https://github.com/openai/codex/blob/6b9826e3aa83b1a5947db50f4332cb9c65f1b340/codex-rs/execpolicy/src/decision.rs#L7-L17)。`policy.rs:401–410` 给出最大严格程度的归并；`core exec_policy.rs` 的具体入口位置见正文。[Apache-2.0 LICENSE](https://github.com/openai/codex/blob/6b9826e3aa83b1a5947db50f4332cb9c65f1b340/LICENSE)。没有执行这些源码或把课程实现搬入题库。
