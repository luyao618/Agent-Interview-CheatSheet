---
id: agent-0061
title: 父 Agent 如何持久管理子 Agent 的关系、隔离、取消与结果回收，避免孤儿任务？
category: agent
tags: [subagent, supervision, durable-graph, lifecycle, isolation, recovery]
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

父 Agent 如何持久管理子 Agent 的关系、隔离、取消与结果回收，避免孤儿任务？父进程退出时，子任务 A 已完成、B 仍运行，应该保存哪些状态，恢复者下一步做什么？

## 答案 · GPT-6

把父子关系、执行尝试、结果交付和资源释放分别记账，再让一个生命周期独立于父进程的监督者负责恢复。**spawn 只说明任务被接受或发起；完成、结果已落盘、父端已收到、资源已回收，是不同事实。** 恢复时保留已完成的结果，按稳定任务 ID 查询未完成的尝试，而不是把所有子任务重新 spawn 一遍。

协作拓扑和拆分收益见 [agent-0026](agent-0026-multi-agent-collaboration-patterns.md)、[agent-0027](agent-0027-why-multi-agent.md)。本题讨论生命周期责任；连接恢复中的迟到事件归属可对照 [agent-0060](agent-0060-mcp-connection-recovery.md)。下文的数据库字段、join/close 和预算是原创教学契约，不是某个 Agent 产品 API 的默认语义。

### 1. 持久图回答“归谁管”，运行状态回答“现在怎样”

任务图至少保存 `run_id / parent_id / child_id`、父子边的开放/关闭状态、创建请求幂等键、当前 owner/epoch、attempt、外部 job/session 标识、预算和 deadline、结果引用/校验信息、交付回执以及资源定位信息。子任务完成后，关系边和结果可以继续保留；卸载运行时也不必删除关系。把这些都塞进一个 `alive` 布尔值，会丢掉恢复所需的信息。

所有权边通常保持一棵有根树：一个子任务有明确的监督父级。任务依赖可以另建 DAG，汇总前检查依赖与循环，不能把“依赖谁”误当成“谁负责取消和回收”。多层派生还要检查根 run 的总节点数、深度、祖先预算及允许的子类型，不能让孩子各自宣布一份全新总预算。

| 持久事实 | 能证明什么 | 仍需什么动作 |
| --- | --- | --- |
| `queued` / spawn 请求已登记 | 逻辑 child 存在，配额已预留 | 不证明 worker 已启动，更不证明结果已交付 |
| `starting` + attempt/job key | 启动意图已持久化 | 对照执行器确认启动；回复丢失时按同一 key 对账，不能盲开新 attempt |
| `running` / `unknown` | 最后观察到运行中，或当前无法确认 | 查询原 attempt；unknown 不等于失败、取消成功或从未执行 |
| 终态 + 持久 result/error | 某次尝试的结果已记录 | `join` 汇总、提供可重放回执，等待接收方确认；失败也要保留来源与部分成果 |
| 已确认交付 + 资源收集 + closed edge | 监督作用域可以逻辑关闭 | 历史可继续保留；删除真实 worktree 等破坏性清理还要遵守产物留存规则 |

数据库中的运行状态可能过期。恢复者先获得新的监督 epoch，再读取图；旧父端的写入必须在同一事务里被 fence 拒绝。child attempt 的身份则不能因为监督者换届就随意重置：B 可能仍在执行同一个 job。旧 epoch 的观察不可写回，新监督者可以重新查询这个 job 并记录结果。lease 到期只表示旧 owner 不能继续拥有写权，**不证明远端执行已经停止**。

父进程一旦退出，必须确实有其他服务、启动恢复流程或有预算的 reconciler 接管扫描、超时和结果投递。只有一份磁盘记录、却没有任何恢复触发器，仍然可能长期无人处理。这个接管约定需要宿主明确支持；不能假定一次普通 spawn 会自动获得持久调度。

### 2. join、close、取消与预算各有边界

本题把 `join` 定义为冻结这一批成员并收集其终态：没收齐就返回显式 pending；收齐后持久化一个稳定回执，按创建顺序包含每个 child 的成功或失败。回执准备好不等于父端已经收到，所以接收者还需 `ack(receipt_id)`。父端若在返回途中退出，恢复者重放同一回执；接收者按 ID 去重，再确认。不能为了避免重复投递，先标“已交付”然后丢掉唯一结果。

`request_close` 先停止新准入并标记取消意图；它不等于 `close` 完成。未发出的 queued 工作可以本地取消，已经存在启动意图或 job 的工作必须对账。收到取消确认或其他可信终态后，才能收集任务结果、释放其资源。真正的 close 还需 join 回执确认和资源收集完成；不能只从活跃列表删除一个 ID，就宣称没有孤儿任务。

失败传播应按业务选择：`collect_all` 保留独立兄弟的运行与部分成果；`fail_fast` 在一个关键 child 失败后取消其余成员，但仍要等待确认、保存错误、收集资源。本例的聚合结果只要含 failed 就是 failed，同时保留成功兄弟的内容；不会把“有一份答案”伪装成全部成功。取消和父进程退出也不会回滚已经发生的工具副作用。

资源预算要同时约束 fan-out、嵌套深度、活跃 attempt 数、每个 child 与根 run 的累计用量、重试次数、墙钟 deadline，以及汇总/取消/清理的余量。重试和恢复不能自动清零累计消费。示例使用合成 work units：根额度 100，A 预留 30、B 预留 40，故 `30+40≤100`，剩余 30；实际模拟消费 `12+20=32`。预留额度在本 run 内保守保留，不能在一次尝试失败后给另一个子任务重复许诺。它不是模型 Token 计量或供应商账单。

fixture 的限制是直接子任务最多 4 个、深度仅 1、最多同时有 2 个已发起/未知 attempt、每个 child 最多 2 次尝试、deadline 为逻辑 tick 50。reconcile 每轮最多检查指定数量的任务，持久旋转游标避免长时间运行的 A 让 B 饥饿。真实系统要用可信时钟和执行网关落实墙钟/CPU/Token/费用限制；一次完成报告不能事后阻止已经超支的真实工具调用。

### 3. 隔离是一组独立决策

| 维度 | 需要明确的契约 | 不能推导出的保证 |
| --- | --- | --- |
| 上下文与会话 | 新会话、受控 fork 或恢复；哪些消息/摘要/工具状态被带入，记录来源和 session ID | 新窗口不代表独立文件空间；复制 transcript 不等于复制了当前权限、可靠执行状态或剩余预算 |
| 工作目录与文件改动 | 指定 cwd、独立 worktree/branch、恢复用的 commit/patch/artifact，冲突如何合并 | Git worktree 分开 HEAD/index/工作目录，但仍共享部分 refs、对象和默认仓库配置；不是 OS 文件权限边界 |
| 身份、工具与网络权限 | 由可信 host 取父授权、子定义与组织策略的交集；敏感能力单独审批 | Persona、不同 Agent 名称、独立进程或“在沙箱里”都不能凭空扩大授权 |
| 计算资源与运行位置 | 进程/容器/远端 worker 的资源限制、取消句柄、日志/凭据注入边界 | worktree 不能限制 CPU、堆或出站网络；进程不同也不自动防止共享环境、文件或凭据泄露 |

恢复要同时核对代码/产物版本、session 来源、模型与配置兼容性、当前权限和剩余预算；不能只找到一个 session ID 就全部沿用。每个维度可以分别选择，因而“隔离低/中/高”不足以表达契约。本例只持久化不同的 **mock worktree/session 标签**，不创建真实 worktree、访问用户会话或宣称实现了认证、文件沙箱。

### 4. 两类监督方案与适用范围

| 方案 | 适用场景与收益 | 代价与不适用场景 |
| --- | --- | --- |
| 进程内结构化作用域 | 生命周期短、父端持续在线的任务，把创建、取消、等待收集绑定在同一个 scope；易追踪失败 | CPython 3.11 的 TaskGroup 会等待成员，并在相应非取消异常时取消其余成员、聚合错误；它不能单靠内存任务对象跨进程崩溃恢复，不适合把长任务成功交付寄托在父进程存活上 |
| 持久任务图 + 独立监督/执行器 | 长任务或可重启父端；持久化启动意图、attempt、结果与回执，恢复后先查询/接管，再有限重试 | 要处理存储与执行器之间的非原子窗口、幂等键、owner fence、结果重放和未知状态，运维成本更高；没有可信对账/幂等契约的副作用任务不能自动重发 |

Temporal API **v1.63.6** 的 `ParentClosePolicy` 明确区分 `TERMINATE`、`ABANDON` 与 `REQUEST_CANCEL`；这些是父 **workflow 逻辑完成** 时的处理选项，不能照搬成 OS 父进程死亡的机制。`ABANDON` 也不是替你安排接管、预算和交付责任。不同运行时可能把 join、关闭关系边、卸载会话和终止进程映射到不同操作，必须按其固定一手契约分别确认。

### 5. 示例：P 退出，A 已完成，B 仍运行

假设 job 执行器的生命周期独立于父端；本地演示用一个纯内存 `Jobs` 字典代表它，不会真的运行子进程。持久图是 `P → A`、`P → B` 两条直接所有权边。所有数据原创，预算/时间均为教学数值。

| 时点 | 持久状态 | 恢复或关闭动作 |
| --- | --- | --- |
| P/epoch1 派发两子任务 | A、B 各有 parent、open edge、attempt1、稳定 job key、quota 和 mock session/worktree 标签 | 启动意图先落盘，再请求 mock 执行器；这里只增加了2个 mock job |
| A 完成，P 的运行时退出 | A=`succeeded`、result=`A complete`、used=12；B=`running`；receipt为空，acked=false；两边仍open | 模拟父端丢失只关闭其 DB handle；没有把运行中 B 误记为 cancelled，也没有丢掉 A |
| 恢复者取得 epoch2 | A 结果原样保留；查询 B 原 key 后仍为 running | 不重新 spawn A/B；mock starts仍为2，join返回pending B |
| B 完成 | B=`succeeded`、result=`B complete`、used=20 | join准备稳定回执，包含A/B结果；模拟回执尚未确认时再次丢失父端 |
| epoch3 再次恢复 | 相同 receipt ID/内容，acked仍false | 重放回执并获得ack，收集两个mock资源，再close；两边closed，累计used=32 |

若启动回复丢失，持久 `starting + job key` 让恢复者查询同一个 job。示例 mock 的 `ensure(key)` 保证同键只创建一个模拟任务；这是它的明确假设，不证明任意平台具有相同幂等性。若查询缺失，保存 `unknown` 并阻止自动新 attempt/close：即便此刻查不到，旧启动请求仍可能迟到。后来查询确认它已启动，再请求取消并确认终态；没有这种证据就保留待人工/外部监督处理的责任，不能补造结果。

<details>
<summary>可运行的原创 Python 3.11.8 fixture：只读写专属临时 SQLite 文件与模拟任务</summary>

保存为 `supervision_fixture.py`，运行 `python3 supervision_fixture.py`。本例只实现一层直接子任务，不实现多层 DAG、真实调度、工具权限或真实文件隔离；完整系统还需逐祖先核对深度/预算并监督整个子树。`dispose()` 关闭本地数据库连接，`close()` 关闭已经收集完成的逻辑 scope，两者刻意分开。输入路径由 demo 自建临时目录提供；没有真实 Agent 派发或进程退出实验。

```python
# file: supervision_fixture.py
"""Original SQLite + simulated jobs. No real agents, processes, worktrees or sessions."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile

TERMINAL = {'succeeded', 'failed', 'cancelled'}


class Rejected(Exception):
    pass


class SimulatedExit(Exception):
    pass


def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}', value):
        raise Rejected('invalid_id')
    return value


def natural(value):
    if type(value) is not int or value < 0:
        raise Rejected('invalid_integer')
    return value


class Jobs:
    """An idempotent mock launcher; the dictionary has no running OS work."""
    def __init__(self, auto_cancel=True):
        self.jobs, self.starts = {}, 0
        self.auto_cancel = auto_cancel

    def ensure(self, key, limit):
        if key not in self.jobs:
            self.jobs[key] = dict(key=key, state='running', used=0, limit=limit,
                                  result=None, error=None, cancel_requested=False)
            self.starts += 1
        elif self.jobs[key]['limit'] != limit:
            raise Rejected('idempotency_conflict')
        return key

    def query(self, key):
        return deepcopy(self.jobs.get(key))

    def spend(self, key, units):
        natural(units)
        job = self.jobs[key]
        if job['state'] != 'running':
            raise Rejected('not_running')
        if job['used'] + units > job['limit']:
            job.update(state='failed', error='budget_exhausted')
            return False  # Reject simulated work BEFORE charging more units.
        job['used'] += units
        return True

    def finish(self, key, result='synthetic-result', error=None):
        job = self.jobs[key]
        if job['state'] != 'running':
            raise Rejected('not_running')
        job.update(state='failed' if error else 'succeeded', result=None if error else result,
                   error=error)

    def cancel(self, key):
        job = self.jobs.get(key)
        if job is not None and job['state'] not in TERMINAL:
            job['cancel_requested'] = True
            if self.auto_cancel:
                job.update(state='cancelled', error='cancel_confirmed')
        # Missing is UNKNOWN, not proof that a delayed launch cannot still arrive.


class Ledger:
    """One root and direct children (depth cap=1); ownership epoch is a host policy."""
    def __init__(self, path, *, create=False, run='P', limit=100, deadline=50,
                 max_children=4, max_parallel=2, max_attempts=2, fail_fast=False):
        self.epoch, self.disposed = None, False
        self.db = sqlite3.connect(path, isolation_level=None, timeout=0.2)
        try:
            if create:
                identifier(run)
                if type(fail_fast) is not bool:
                    raise Rejected('invalid_failure_policy')
                for number in (limit, deadline, max_children, max_parallel, max_attempts):
                    if natural(number) == 0:
                        raise Rejected('zero_budget')
                state = dict(run=run, epoch=0, phase='open', limit=limit, deadline=deadline,
                             clock=0, max_children=max_children, max_parallel=max_parallel,
                             max_attempts=max_attempts, fail_fast=bool(fail_fast), nodes={},
                             receipt=None, acked=False, scan_cursor=0)
                self.db.execute('BEGIN IMMEDIATE')
                self.db.execute('CREATE TABLE ledger (id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
                self.db.execute('INSERT INTO ledger VALUES (1, ?)', (json.dumps(state),))
                self.db.commit()
            self.snapshot()  # Opening for recovery must find an existing ledger.
        except BaseException:
            self.dispose()
            raise

    def dispose(self):
        if not self.disposed:
            self.db.close()
            self.disposed = True  # Does NOT mean logical close/cancel of children.

    def snapshot(self):
        return json.loads(self.db.execute('SELECT body FROM ledger WHERE id=1').fetchone()[0])

    @contextmanager
    def transaction(self, *, claim=False, abort=False):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            s = self.snapshot()
            if not claim and (self.epoch is None or self.epoch != s['epoch']):
                raise Rejected('stale_supervisor')
            yield s
            self.db.execute('UPDATE ledger SET body=? WHERE id=1', (json.dumps(s),))
            if abort:
                raise SimulatedExit('before_commit')
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def takeover(self):
        with self.transaction(claim=True) as s:
            s['epoch'] += 1
            epoch = s['epoch']
        self.epoch = epoch
        return epoch  # Trusted supervisor input in this mock, NOT authentication.

    @staticmethod
    def clock(s, now):
        natural(now)
        if now < s['clock']:
            raise Rejected('clock_regression')
        s['clock'] = now
        if now >= s['deadline'] and s['phase'] != 'closed':
            Ledger.request_close_state(s)

    def advance(self, now):
        with self.transaction() as s:
            self.clock(s, now)  # Persist deadline/clock even when later admission is rejected.

    @staticmethod
    def request_close_state(s):
        if s['phase'] != 'closed':
            s['phase'] = 'closing'
            for n in s['nodes'].values():
                if n['state'] not in TERMINAL:
                    n['cancel_requested'] = True

    def spawn(self, name, quota, *, parent='P', abort=False):
        identifier(name)
        if natural(quota) == 0:
            raise Rejected('zero_quota')
        with self.transaction(abort=abort) as s:
            if parent != s['run'] or name == parent:
                raise Rejected('not_a_direct_child')
            if name in s['nodes']:
                if s['nodes'][name]['quota'] != quota:
                    raise Rejected('spawn_conflict')
                return name  # Same logical request; never create another node.
            if s['phase'] != 'open':
                raise Rejected('admission_closed')
            if len(s['nodes']) >= s['max_children']:
                raise Rejected('fanout_exhausted')
            if sum(n['quota'] for n in s['nodes'].values()) + quota > s['limit']:
                raise Rejected('quota_exhausted')
            s['nodes'][name] = dict(parent=parent, edge='open', ordinal=len(s['nodes']),
                state='queued', attempt=0, key=None, quota=quota, used=0, prior_used=0,
                result=None, error=None, cancel_requested=False, released=False,
                worktree=f'mock-wt:{s["run"]}:{name}', session=None, history=[])
        return name

    def dispatch(self, name, jobs, now, *, lose_response=False):
        self.advance(now)
        with self.transaction() as s:
            n = s['nodes'][name]
            if s['phase'] not in ('open', 'joining') or n['cancel_requested']:
                raise Rejected('admission_closed')
            if n['state'] == 'queued':
                active = sum(v['state'] in ('starting', 'running', 'unknown') for v in s['nodes'].values())
                if active >= s['max_parallel']:
                    raise Rejected('parallel_exhausted')
                if n['attempt'] >= s['max_attempts'] or n['used'] >= n['quota']:
                    raise Rejected('attempt_or_quota_exhausted')
                n['attempt'] += 1
                n['key'] = f'{s["run"]}:{name}:a{n["attempt"]}'
                n['session'] = f'mock-session:{n["key"]}'
                n['state'] = 'starting'
            elif n['state'] != 'starting':
                raise Rejected('already_dispatched_or_unknown')
            key, remaining = n['key'], n['quota'] - n['prior_used']
        # Durable launch intent precedes this mock call. A lost reply keeps the key.
        jobs.ensure(key, remaining)
        if lose_response:
            raise SimulatedExit('after_launch_before_observation')
        self.reconcile(name, jobs, now)
        return key

    def ticket(self, name, now):
        self.advance(now)
        with self.transaction() as s:
            n = s['nodes'][name]
            if n['state'] == 'queued' and n['cancel_requested']:
                n.update(state='cancelled', error='not_launched')
            return dict(epoch=self.epoch, name=name, attempt=n['attempt'], key=n['key'],
                        cancel=n['cancel_requested'], state=n['state'])

    def apply(self, ticket, report):
        with self.transaction() as s:
            n = s['nodes'][ticket['name']]
            if (ticket['epoch'] != self.epoch or ticket['key'] != n['key'] or
                    ticket['attempt'] != n['attempt']):
                raise Rejected('stale_attempt')
            if ticket['key'] is None or n['state'] == 'queued':
                raise Rejected('no_launch_intent')
            if n['state'] in TERMINAL:
                return  # Terminal records cannot be overwritten by a late callback.
            if report is None:
                n['state'] = 'unknown'
                return
            if (report['key'] != n['key'] or report['state'] not in TERMINAL | {'running'} or
                    type(report['used']) is not int or
                    not n['used'] - n['prior_used'] <= report['used'] <= n['quota'] - n['prior_used']):
                raise Rejected('invalid_job_report')
            if ((report['state'] == 'succeeded' and type(report['result']) is not str) or
                    (report['state'] != 'succeeded' and report['result'] is not None) or
                    (report['state'] in {'failed', 'cancelled'} and type(report['error']) is not str)):
                raise Rejected('invalid_result')
            n.update(state=report['state'], used=n['prior_used'] + report['used'],
                     result=report['result'], error=report['error'])
            if n['state'] == 'failed' and s['fail_fast']:
                self.request_close_state(s)

    def reconcile(self, name, jobs, now):
        t = self.ticket(name, now)
        if t['state'] in TERMINAL or t['key'] is None:
            return
        report = jobs.query(t['key'])  # No external operation while holding the DB lock.
        if t['cancel'] and (report is None or report['state'] not in TERMINAL):
            jobs.cancel(t['key'])
            report = jobs.query(t['key'])
        self.apply(t, report)

    def recover(self, jobs, now, max_checks=4):
        if natural(max_checks) == 0:
            raise Rejected('zero_check_budget')
        # Exactly one bounded pass. Pending/unknown needs another explicit decision.
        self.advance(now)
        state = self.snapshot()
        nodes = state['nodes']
        names = sorted((k for k in nodes if nodes[k]['state'] not in TERMINAL),
                       key=lambda k:nodes[k]['ordinal'])
        if names:
            start = state['scan_cursor'] % len(names)
            order = names[start:] + names[:start]
            checked = order[:max_checks]
            for name in checked:
                self.reconcile(name, jobs, now)
            with self.transaction() as s:
                s['scan_cursor'] = (start + len(checked)) % len(names)
        return self.snapshot()

    def retry(self, name):
        with self.transaction() as s:
            n = s['nodes'][name]
            if (s['phase'] not in ('open', 'joining') or s['receipt'] is not None or
                    n['state'] != 'failed' or n['error'] != 'transient' or
                    n['attempt'] >= s['max_attempts'] or n['used'] >= n['quota']):
                raise Rejected('retry_denied')
            n['history'].append(dict(attempt=n['attempt'], used=n['used'], error=n['error']))
            n.update(state='queued', key=None, prior_used=n['used'], result=None, error=None)

    def request_close(self):
        with self.transaction() as s:
            self.request_close_state(s)

    def join(self):
        with self.transaction() as s:
            if s['phase'] == 'open':
                s['phase'] = 'joining'  # Freeze membership before collecting a result set.
            pending = [k for k,n in s['nodes'].items() if n['state'] not in TERMINAL]
            if pending:
                return dict(ready=False, pending=pending)
            if s['receipt'] is None:
                rows = [dict(name=k, state=n['state'], result=n['result'], error=n['error'])
                        for k,n in sorted(s['nodes'].items(), key=lambda item:item[1]['ordinal'])]
                digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
                outcome = 'failed' if any(n['state']=='failed' for n in rows) else (
                    'cancelled' if any(n['state']=='cancelled' for n in rows) else 'succeeded')
                s['receipt'] = dict(id=f'{s["run"]}:join:{digest}', outcome=outcome, rows=rows)
            return dict(ready=True, receipt=deepcopy(s['receipt']))

    def ack(self, receipt_id):
        with self.transaction() as s:
            if s['receipt'] is None or receipt_id != s['receipt']['id']:
                raise Rejected('wrong_receipt')
            s['acked'] = True  # Synthetic receiver acknowledgement, not proof of human reading.

    def release(self, name):
        with self.transaction() as s:
            n = s['nodes'][name]
            if not s['acked'] or n['state'] not in TERMINAL:
                raise Rejected('not_collected')
            n['released'] = True  # Bookkeeping for MOCK handles; never removes a real worktree.

    def close(self):
        with self.transaction() as s:
            if (not s['acked'] or any(n['state'] not in TERMINAL or not n['released']
                                      for n in s['nodes'].values())):
                raise Rejected('children_or_delivery_outstanding')
            s['phase'] = 'closed'
            for n in s['nodes'].values():
                n['edge'] = 'closed'


def demo():
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='yao392-owned-', dir=root) as name:
        path = Path(name)/'graph.sqlite'
        jobs, opened = Jobs(), []
        try:
            p = Ledger(path, create=True); opened.append(p); p.takeover()
            p.spawn('A', 30); p.spawn('B', 40)
            a, b = p.dispatch('A', jobs, 0), p.dispatch('B', jobs, 0)
            jobs.spend(a, 12); jobs.finish(a, 'A complete')
            p.reconcile('A', jobs, 1)
            before = p.snapshot()
            p.dispose()  # Simulates loss of parent-side runtime, not SIGKILL or power loss.
            q = Ledger(path); opened.append(q); q.takeover(); recovered = q.recover(jobs, 2)
            waiting = q.join()
            jobs.spend(b, 20); jobs.finish(b, 'B complete'); q.reconcile('B', jobs, 3)
            receipt = q.join()['receipt']
            q.dispose()  # Lose delivery reply; prepared receipt persists, ack remains false.
            r = Ledger(path); opened.append(r); r.takeover()
            replay = r.join()['receipt']; assert replay == receipt
            r.ack(replay['id'])
            for child in ('A', 'B'):
                r.release(child)
            r.close(); final = r.snapshot()
            result = dict(before_exit={k:n['state'] for k,n in before['nodes'].items()},
                after_recovery={k:n['state'] for k,n in recovered['nodes'].items()},
                join_before_b_done=waiting, starts=jobs.starts,
                receipt_replayed=replay==receipt, outcome=replay['outcome'],
                final_phase=final['phase'], edges=[n['edge'] for n in final['nodes'].values()],
                used=sum(n['used'] for n in final['nodes'].values()))
        finally:
            for ledger in opened:
                ledger.dispose()
            assert all(x.disposed for x in opened)
    assert not Path(name).exists()
    result['owned_directory_removed'] = True
    return result


if __name__ == '__main__':
    print(json.dumps(demo(), indent=2))
```

</details>

2026-09-16 在 Python **3.11.8**、实际链接 SQLite **3.19.3** 上运行，输出 `before_exit={A: succeeded, B: running}`，`after_recovery` 相同；B未完成时 `join_before_b_done={ready: false, pending: [B]}`；最终 `starts=2, receipt_replayed=true, outcome=succeeded, final_phase=closed, edges=[closed, closed], used=32`，专属临时目录已删除。

配套 `python3 test_supervision.py` 的 **32 个测试通过**：覆盖父端重开、spawn与交付分离、事务中断、启动回复丢失、回执重放/错误ack、关闭门槛、取消请求与确认、保留A成果、unknown阻止重试/关闭、迟到启动、旧owner/attempt、预算/重试不重置、deadline、fail-fast/collect-all、报告校验、数据副本、会话/工作树标签保留，以及小扫描预算的恢复公平性。32个测试根目录已删除，42个测试数据库连接已显式关闭；两个demo另做连接关闭和临时目录清理断言，不计入这些测试计数。

测试真实验证了已提交 SQLite 状态在 handle 关闭/重开后可读；“父进程退出”由此模拟，未执行 SIGKILL、断电或真实远端 worker 实验。接管 epoch 不是身份认证，回执 hash 不是来源认证；mock 的原子幂等/预算计数不证明远端 exactly-once、生产硬时限或计费准确性。负向测试故意保存 unknown 以验证 close 被拒绝，清理它的测试文件不代表真实任务已停止。

## 延伸 / 追问

**追问 1：B 没心跳了，可以直接重试吗？**

不能仅据此判断原任务未执行。先按原 attempt/job key 查询、请求有界取消或撤销执行 lease；没有确认时保留unknown和已分配预算。只有可安全幂等重发、已确认失败或经明确人工决策，才开启受预算限制的新尝试。

**追问 2：A 已经写出结果，父端还没收到，怎样避免丢失或重复消费？**

保存不可变结果或可验证的持久引用，准备稳定回执，接收端按ID去重并ack；超时重放同一回执。接收确认和发起外部副作用仍要各自的幂等/事务契约，不能仅靠本地acked位证明端到端exactly-once。

**追问 3：一个子任务失败，父端应该立刻返回失败吗？**

可以先记录失败并停止新准入，但不能随即抛弃未收集的兄弟任务。关键依赖可fail-fast取消，独立任务可collect-all；两者都要保留已完成结果、确认剩余任务状态并收集资源。若收集期限耗尽，报告未完成责任及新owner，不能伪装成已close。

**追问 4：子 Agent 的 worktree 不同，为什么还要单独配置权限？**

worktree解决的是代码工作区和合并冲突的一部分，不是OS读写/出站权限。不同会话也可能共享cwd或凭据来源；需分别设置上下文、身份、文件、网络和资源边界，并在工具网关执行当前授权。

## 常见误区

- **“spawn 返回了ID，结果就已经交付。”** ID是任务身份；执行终态、持久结果、回执、ack与资源收集仍未必完成。
- **“隔离就是选择低、中、高。”** 会话、工作树、身份/工具授权、计算/网络限制是独立维度，任何单项都不自动带来其他项的保证。
- **“父退出就等于逻辑close，或者cancel等于子任务已停止。”** 运行时死亡、作用域关闭、取消请求和取消确认不同；未知状态不能被改名成cancelled。
- **“有持久图就没有孤儿任务。”** 还必须有外部接管者、唤醒/扫描机制、预算和结果投递责任；只落盘不调度会留下无人处理的工作。
- **“恢复就重新spawn；重试就重新获得一份预算。”** 先对账旧attempt，保留已用预算和完成结果，防止重复副作用、花费放大与旧回调覆盖新状态。

## 参考

- 学习线索：洛小山《AI 产品从入门到精通》learn-ai，固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/codex-24.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-24.html)、[slides/12-15.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/12-15.html)、[slides/12-16.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/12-16.html)。[LICENSE](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/LICENSE) 为 AGPL-3.0。仅保留链接线索，未搬运正文、代码或图片；课程中的产品特定边状态、唤醒行为、恢复阈值及还原源码结论不作为本文的一手产品保证。
- 一手关闭策略：Temporal API **v1.63.6**，固定 `46ee8b820cff353e92fa8c9d052414d4e573feb7`，[temporal/api/enums/v1/workflow.proto](https://github.com/temporalio/api/blob/46ee8b820cff353e92fa8c9d052414d4e573feb7/temporal/api/enums/v1/workflow.proto) 的 `ParentClosePolicy`；[MIT LICENSE](https://github.com/temporalio/api/blob/46ee8b820cff353e92fa8c9d052414d4e573feb7/LICENSE)。只据其区分逻辑完成时的选项，不外推为父OS进程死亡或本例实现的保证。
- 一手运行与存储语义：CPython **v3.11.8**，[Doc/library/asyncio-task.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/asyncio-task.rst) 的 Task Groups/Task Cancellation；[Doc/library/sqlite3.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/sqlite3.rst) 的 commit/rollback/close、connection context manager；[LICENSE](https://github.com/python/cpython/blob/v3.11.8/LICENSE) 记录PSF许可与历史。本例自主定义持久恢复协议，不把TaskGroup当成持久任务引擎。
- 一手文件隔离边界：Git **v2.46.0**，[Documentation/git-worktree.txt](https://github.com/git/git/blob/v2.46.0/Documentation/git-worktree.txt) 的 Description、Refs、Configuration File；[COPYING](https://github.com/git/git/blob/v2.46.0/COPYING) 说明GPLv2。只引用共享/独立资源的事实，未复制其源码或文档正文。
