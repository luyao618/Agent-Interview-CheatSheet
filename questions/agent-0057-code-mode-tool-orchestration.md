---
id: agent-0057
title: Code Mode 用模型生成的程序编排工具时，何时能减少往返，如何控制执行预算和权限？
category: agent
tags: [code-mode, tools, orchestration, budget, sandbox, approval]
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

Code Mode 用模型生成的程序编排工具时，何时能减少往返，如何控制执行预算和权限？同步死循环和永不 resolve 的 Promise 分别消耗什么资源，执行失败后应返回什么？

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 回答 2026-09-16

Code Mode 把一段可确定的工具编排交给程序：中间值在执行器内传递、过滤和聚合，模型只接收必要的最终结果或失败状态。它适合“下一步如何计算已经明确，只缺工具返回的数据”的任务；遇到需要模型重新理解语义、用户确认或开放式决策的分支，仍要停下来交回控制权。程序不是额外权限来源，CPU、墙钟、内存和工具预算都必须由可信宿主约束。

生成代码的通用安全边界见 [engineering-0012](engineering-0012-artifact-generated-code-safety.md)，并行依赖与结果收口见 [agent-0032](agent-0032-parallel-tool-calling.md)，程序值与模型文本的可读范围见 [agent-0056](agent-0056-tool-result-value-projections.md)。本题聚焦程序化编排与执行预算，不把“换成代码”当成“工具更少、天然安全或一定便宜”。

### 1. 省的是哪些往返，不省哪些账

假设初始不知道三个 ID，先用 list_ids 获取，再分别 lookup，最后求和。工具绑定返回带 status/value 的结构化结果。编排示意如下，**没有运行真实模型生成的程序**：

```javascript
async function plan(tools) {
  const ids = await tools.list_ids({});
  if (ids.status !== 'ok') return ids;
  const rows = await Promise.all(ids.value.map(id => tools.lookup({id})));
  if (rows.some(r => r.status !== 'ok')) return {status: 'incomplete', results: rows};
  return {status: 'ok', total: rows.reduce((sum, r) => sum + r.value, 0)};
}
```

按这个特定数据依赖，原生调用需要两轮模型工具决策：先请求 ID，再请求可并行的三个 lookup；Code Mode 可以一轮提交程序，内部仍然调用 **4 次工具**。两边都可能还需要一次最终回答生成，本例没有把它假装省掉。若 ID 原本已知，或存在合适的批处理工具，原生调用也可能一轮完成。

总费用至少包括模型输入/输出 Token、执行器 CPU/内存/存活时间、工具调用、存储与重试。程序局部值不逐步回灌可以减少上下文搬运，但代码生成、编译、长时间等待、失败重试和工具返回的日志仍可能增加成本。并行缩短关键路径，不等于减少所有工具消耗的总资源；不能把一轮模型调用当作一笔总账。

| 方案 | 适合 | 代价与不适用场景 |
| --- | --- | --- |
| 原生逐步工具调用 | 每步都需要模型理解新事实、重新规划或请求确认 | 决策可见，但有更多模型往返和中间上下文；纯粹的数据循环不必逐条交给模型 |
| Code Mode | 固定的查询、映射、过滤、聚合；依赖明确，中间值有稳定 Schema | 可减少模型介入，但需要代码执行、资源限制和失败恢复；不适合靠程序猜测缺失审批或把无限任务塞进一次执行 |
| 固定 workflow / 类型化批处理 API | 常用且稳定、可预先审查的数据流 | 更易约束与观测，但灵活性较低；不应为了省一次往返暴露一个无限权的“任意执行”接口 |

### 2. 三类资源预算和工具网关

| 预算 | 同步 `while (true)` | `await new Promise(() => {})` | 应由谁执行限制 |
| --- | --- | --- | --- |
| CPU 时间 | 持续占用计算；同时挂一个未完成工具也不能让这部分 CPU 免计量 | 等待本身通常很少用 CPU，若夹带热循环仍要计入 | 可信运行时计量/中断，或进程 CPU 配额；不是 guest 自报的耗时 |
| 墙钟时间 | 也在增长，作为外部兜底 | 没有进展但持续占用会话和资源，必须有等待截止 | 宿主的独立计时与终止/回收路径，覆盖工具和 IPC 等等待 |
| 堆及其他内存 | 循环若分配对象可能耗尽堆；不分配则不一定 | 悬挂 Promise 及闭包也能保留大量对象 | 运行时堆上限，加进程/容器层的总体内存限制与异常退出处理 |

在被同一同步循环阻塞的事件循环里，`setTimeout` 回调没有机会运行；包一层 `Promise.race` 不会自动抢占同步代码。需要可信执行器的中断机制或外层进程监督。事件循环利用率、墙钟和 OS CPU 也不是同一个指标：本例用 OS 对整个子进程累计 CPU 的计量，不把某个框架的 busy-time 指标冒称为 OS CPU。

预算要绑定整次 run，重试、嵌套执行和并行子调用不能各自重新领一份无限额度。生产墙钟截止通常应包含排队、启动、编译、工具等待与收尾；本例会单独写明测量起点。若执行器有 yield/wait 协议，yield 间隔只是交还控制权，不能替代最大存活时间；必须保留持有者、累计预算与明确终止操作。本例没有实现可续跑 cell。

程序只拿受限工具能力，调用仍经宿主网关：验证当前主体/租户/run、工具白名单、参数 Schema、预算，再处理需要的审批。审批应绑定具体工具、参数、权限版本和有效期；“这段代码已获准运行”不自动批准它随后尝试的每个动作。凭据、审批控制接口和预算账本留在宿主，不能把整个宿主对象交给生成代码。

下面的原创 mock 网关把同一 run 的尝试次数限制为 8、实际派发限制为 4；每次派发记一个**合成 credit**，不是货币价格。approve_from_host 是测试中的可信控制面，不导出给程序。四线程同时提交 12 次请求的验证中只有 4 次派发成功；mock 写入确认丢失时，调用者得到 result_unknown，宿主仍保留已发生的 mock 效果，审批也已消费，不会自动重放。

<details>
<summary>mock_gateway.py：宿主网关的原创教学模型</summary>

```python
# file: mock_gateway.py
import json
from threading import Lock


class MockGateway:
    """Host-side teaching fixture. No business API, credentials or real approvals."""
    def __init__(self, clock):
        self.clock = clock
        self.context = ('tenant-fixture', 'subject-fixture', 'run-1', 1)
        self.allowed = {'list_ids', 'lookup', 'mock_write'}
        self.approvals, self.ledger, self.effects = {}, [], []
        self.attempts, self.spent = 0, 0
        self.lock = Lock()
        self.lose_write_ack = False

    def key(self, tool, args):
        return (self.context, tool, json.dumps(args, sort_keys=True))

    def approve_from_host(self, tool, args):
        # This method is NOT exported to generated code; tests act as the trusted host.
        with self.lock:
            self.approvals[self.key(tool, args)] = self.clock() + 5

    def call(self, context, tool, args):
        with self.lock:
            if context != self.context:
                return {'status': 'denied'}
            self.attempts += 1
            if self.attempts > 8:
                return {'status': 'attempt_budget'}
            if type(tool) is not str or tool not in self.allowed:
                return {'status': 'denied'}
            valid = type(args) is dict and (args == {} if tool == 'list_ids' else
                     set(args) == {'id'} and type(args['id']) is int and 1 <= args['id'] <= 3)
            if not valid:
                return {'status': 'schema_error'}
            key = self.key(tool, args)
            if tool == 'mock_write' and self.approvals.get(key, -1) <= self.clock():
                return {'status': 'approval_required'}
            if self.spent >= 4:
                return {'status': 'tool_budget'}
            if tool == 'mock_write':
                del self.approvals[key]  # Bound to run/policy/tool/arguments; one use.
            self.spent += 1  # One synthetic credit per dispatch, not a monetary price.
            op = f'op-{self.spent}'
            row = {'op_id': op, 'tool': tool, 'status': 'started'}
            self.ledger.append(row)
            if tool == 'list_ids':
                value = [1, 2, 3]
            elif tool == 'lookup':
                value = args['id'] * 10
            else:
                self.effects.append(args['id'])  # In-memory mock effect only.
                if self.lose_write_ack:
                    row['status'] = 'mock_effect_recorded_ack_lost'
                    return {'status': 'result_unknown', 'op_id': op}
                value = {'mock_written': args['id']}
            row['status'] = 'completed'
            return {'status': 'ok', 'op_id': op, 'value': value}


def orchestrate(gateway):
    context = gateway.context
    first = gateway.call(context, 'list_ids', {})
    if first['status'] != 'ok':
        return first
    results = [gateway.call(context, 'lookup', {'id': i}) for i in first['value']]
    if any(r['status'] != 'ok' for r in results):
        return {'status': 'incomplete', 'results': results}
    return {'status': 'ok', 'total': sum(r['value'] for r in results),
            'tool_calls': len(gateway.ledger), 'synthetic_credits': gateway.spent}
```

</details>

锁内只有即时 mock 运算，这个测试证明共享额度和条件判断，不证明真实网关吞吐。生产应在可信层原子预留额度、限制 in-flight 数量并为后端设置截止；不应持有一把全局锁等待远端 I/O。Node 预算实验与这个 Python mock 分别验证各自边界，没有伪称已经构成一套跨进程 Code Mode RPC 系统。

### 3. 自建受限子进程的实际预算对照

实验固定 Node **v22.18.0**、Python **3.11.8**，运行于 macOS arm64（2026-09-16）。每个样例都新建独占子进程：先设置 CPU soft/hard 为 **1/2 秒**、core dump 为 0、日志文件上限 64 KiB，再 exec Node。Node 使用 `--max-old-space-size=32 --max-semi-space-size=1`；`v8.getHeapStatistics().heap_size_limit` 实际报告 **36,700,160 bytes = 35 MiB**。这是 V8 堆范围，**不是整个进程 RSS 或外部 ArrayBuffer/原生内存上限**；本轮没有触发 OOM 压测。

宿主在放行前检查 PID、直接父进程、专属脚本路径和随机 nonce，并比较 daemon PID；需要发信号时重新核对，且只终止这个精确 PID。CPU 额度由 OS 限制这个已核对的子进程；墙钟到期由外部 Python 监督者核对身份后发 SIGKILL，使用 wait4 回收并取得资源使用量。子进程只运行本文自制片段，不运行任意不可信代码，也不接触业务工具或凭据。

两段关键工作负载分别在**受限子进程**内执行：同步循环，以及永不 resolve 的 Promise。两者都预先挂一个 100 ms 的提示定时器。pending 样例保留开放的 stdin 控制通道模拟长驻宿主；裸的未完成 Promise 本身未必能让 Node 进程一直存活。它的事件循环仍能打印 timer_fired，但 Promise 本身不完成。

该次实际结果如下；CPU 是 wait4 返回的整个子进程 user+system 时间，含启动器/Node 初始化；墙钟从宿主放行到回收，二者起点不同。数字仅是本次验证，不是生产性能承诺：

| 工作负载 | 子进程 CPU 秒 | 放行至回收秒 | 观测终态 | guest 的 100 ms 定时器 |
| --- | --- | --- | --- | --- |
| 正常返回 6 | 0.0391 | 0.0163 | COMPLETED，exit 0 | 完成前主动清除 |
| 同步死循环 | 1.0137 | 1.0055 | CPU_LIMIT，SIGXCPU / -24 | 未执行，事件循环被阻塞 |
| 未完成 Promise | 0.0335 | 0.4343 | WALL_LIMIT，宿主 SIGKILL / -9 | 已执行，但 Promise 仍未完成 |
| 自制语法错误 | 0.0335 | 0.0165 | SCRIPT_ERROR，exit 2 | 捕获错误后清除 |

pending 的墙钟配置为 0.4 秒，本次在约 0.4048 秒观察到到期，身份核对、发信号和回收后约 0.4343 秒结束。其他样例有 3 秒外部运行兜底。监督者还给启动、CLI/ps 核对和回收分别设置有限等待；不能把 guest 的 0.4 秒配置称为端到端 400 ms 硬 SLA。

初次环境检查发现 Python/macOS 启动加入 locale/platform 环境键，断言失败时所有样例已回收。后续在 exec 前重建白名单，并在可信 Node 前导代码移除启动期附加键；最终进入工作负载时仅有 LANG/TMPDIR。原失败记录保留，最终结果通过。最小环境不等于安全沙箱：Node 官方 `node:vm` 文档也明确它不是运行不可信代码的安全机制；本实验的子进程和堆标志没有替代 OS/容器隔离与工具授权。

<details>
<summary>预算实验的三个文件：仅经外部 supervisor 启动，不要直接在主进程/REPL 运行死循环</summary>

```javascript
// file: budget_child.cjs
'use strict';
const fs = require('node:fs');
const v8 = require('node:v8');
const mode = process.argv[2], nonce = process.argv[3];
const emit = value => fs.writeSync(1, JSON.stringify(value) + '\n');
const beforeEnvironment = Object.keys(process.env).sort();
// Trusted prelude removes any locale/platform keys inserted during process startup.
for (const key of beforeEnvironment) {
  if (!['LANG', 'TMPDIR'].includes(key)) delete process.env[key];
}
let input = '', admitted = false;
process.stdin.setEncoding('utf8');
// An open control channel keeps the pending-Promise fixture alive; EOF is a cleanup fallback.
process.stdin.on('end', () => process.exit(70));
process.stdin.on('data', async text => {
  input += text;
  if (admitted || !input.includes('\n')) return;
  if (input.trim() !== nonce) process.exit(71);
  admitted = true;
  emit({event: 'entered', mode});
  const timer = setTimeout(() => emit({event: 'timer_fired'}), 100);
  if (mode === 'spin') {
    while (true) {} // Runs ONLY in this owned, OS-limited child after the host opens the gate.
  } else if (mode === 'pending') {
    await new Promise(() => {});
  } else if (mode === 'syntax') {
    try { new Function('return )'); }
    catch (error) { clearTimeout(timer); emit({event: 'script_error', name: error.name}); process.exit(2); }
  } else if (mode === 'ok') {
    clearTimeout(timer); emit({event: 'completed', value: 6}); process.exit(0);
  } else {
    process.exit(72);
  }
});
emit({event: 'ready', node: process.version, pid: process.pid,
      heap_limit_bytes: v8.getHeapStatistics().heap_size_limit,
      environment_keys_before_prelude: beforeEnvironment,
      environment_keys: Object.keys(process.env).sort()});
```

```python
# file: limit_exec.py
"""Apply limits in the newly-created child, then exec Node with the same PID."""
import json,os,resource,sys
resource.setrlimit(resource.RLIMIT_CPU,(1,2))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536))
os.write(1,(json.dumps({'event':'limits','pid':os.getpid(),'cpu_seconds':list(resource.getrlimit(resource.RLIMIT_CPU)),
                     'core_bytes':0,'file_bytes':65536})+'\n').encode())
node,child,mode,nonce=sys.argv[1:]
os.execve(node,[node,'--max-old-space-size=32','--max-semi-space-size=1',child,mode,nonce],
          {'LANG':'C.UTF-8','TMPDIR':os.environ['TMPDIR']})
```

```python
# file: supervise_budgets.py
"""Only original fixtures in owned children. Unix / Python3.11.8 / Node22.18.0.
No untrusted code, business tools or inherited credentials. Never signal by executable name.
"""
import hashlib,json,os,platform,shutil,signal,subprocess,sys,tempfile,time,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parent
NODE=shutil.which('node')

def daemon_pid():
    data=json.loads(subprocess.run(['multica','daemon','status','--output','json'],
        check=True,capture_output=True,text=True,timeout=3).stdout)
    if data.get('status')!='running' or type(data.get('pid')) is not int:
        raise RuntimeError('cannot verify daemon PID')
    return data['pid']

def events(path):
    return [json.loads(line) for line in path.read_text().splitlines(keepends=True) if line.endswith('\n')]

def trial(mode):
    if mode not in ('ok','spin','pending','syntax'):
        raise ValueError('fixture not allowed')
    forbidden=daemon_pid()  # Refuse to launch without a known daemon PID.
    with tempfile.TemporaryDirectory(prefix='yao383-owned-',dir=ROOT) as folder:
        folder=Path(folder);nonce=uuid.uuid4().hex
        child=folder/'budget_child.cjs';launcher=folder/'limit_exec.py'
        shutil.copyfile(ROOT/'budget_child.cjs',child);shutil.copyfile(ROOT/'limit_exec.py',launcher)
        output,error=folder/'stdout.jsonl',folder/'stderr.txt'
        p=None;usage=None;checks=[];kills=[];released=None;expired_at=None
        def reap():
            nonlocal usage
            if p.returncode is not None:return True
            pid,status,usage_read=os.wait4(p.pid,os.WNOHANG)
            if pid:
                p.returncode=os.waitstatus_to_exitcode(status);usage=usage_read;return True
            return False
        def verify_owner(stage):
            # Compare fresh daemon state, direct parent identity, unique nonce and owned path.
            current_daemon=daemon_pid()
            if reap():return False
            row=subprocess.run(['ps','-p',str(p.pid),'-o','ppid=,command='],
                               capture_output=True,text=True,check=False,timeout=1).stdout.strip()
            if reap():return False
            fields=row.split(None,1)
            ok=(len(fields)==2 and fields[0]==str(os.getpid()) and nonce in fields[1]
                and str(child) in fields[1] and p.pid not in (forbidden,current_daemon,os.getpid()))
            checks.append({'stage':stage,'owned':ok,'not_daemon':p.pid!=current_daemon,
                'child_pid':p.pid,'expected_parent_pid':os.getpid(),'daemon_pid':current_daemon,
                'observed_parent_pid':int(fields[0]) if len(fields)==2 else None,
                'nonce_matches':len(fields)==2 and nonce in fields[1],
                'script_path_matches':len(fields)==2 and str(child) in fields[1]})
            if not ok:raise RuntimeError('child identity check failed; no signal sent')
            return True
        def stop(stage):
            if not reap() and verify_owner(stage):
                # This single-threaded owner alone reaps this child. Its PID cannot be reused before wait4.
                try:os.kill(p.pid,signal.SIGKILL);kills.append(stage)
                except ProcessLookupError:pass
        def collect_until(deadline):
            while not reap() and time.monotonic()<deadline:time.sleep(0.01)
            return reap()
        try:
            with output.open('wb') as out,error.open('wb') as err:
                p=subprocess.Popen([sys.executable,str(launcher),NODE,str(child),mode,nonce],
                    stdin=subprocess.PIPE,stdout=out,stderr=err,cwd=folder,
                    env={'LANG':'C','TMPDIR':str(folder)},start_new_session=True)
                assert p.pid not in (forbidden,os.getpid())
                startup=time.monotonic()+2
                while not any(e['event']=='ready' for e in events(output)):
                    if reap():raise RuntimeError('child exited before ready')
                    if time.monotonic()>=startup:raise TimeoutError('startup deadline')
                    time.sleep(0.01)
                if not verify_owner('before_release'):raise RuntimeError('child exited before release')
                released=time.monotonic();p.stdin.write((nonce+'\n').encode());p.stdin.flush()
                wall=0.4 if mode=='pending' else 3.0
                if not collect_until(released+wall):
                    expired_at=time.monotonic()-released
                    stop('wall_deadline')
                    if not collect_until(time.monotonic()+2):raise RuntimeError('child not reaped after kill')
            observed=events(output);ready=next(e for e in observed if e['event']=='ready')
            rc=p.returncode
            reason=('WALL_LIMIT' if 'wall_deadline' in kills else 'CPU_LIMIT' if rc==-signal.SIGXCPU
                    else 'COMPLETED' if rc==0 else 'SCRIPT_ERROR' if rc==2 else 'PROCESS_FAILURE')
            result={'mode':mode,'status':reason,'returncode':rc,'wall_budget_s':wall,
                    'deadline_observed_s':expired_at,'elapsed_since_release_s':time.monotonic()-released,
                    'cpu_user_s':usage.ru_utime,'cpu_system_s':usage.ru_stime,
                    'heap_limit_bytes':ready['heap_limit_bytes'],'environment_keys':ready['environment_keys'],
                    'events':observed,'ownership_checks':checks,'signals_sent':kills,
                    'reaped':p.returncode is not None,'stderr':error.read_text()}
        finally:
            if p is not None:
                try:
                    if not reap():stop('exception_cleanup')
                finally:
                    # EOF exits the cooperative pending fixture even if a verification command failed;
                    # the spin fixture also has an OS hard CPU limit. No unchecked signal fallback.
                    if p.stdin and not p.stdin.closed:
                        try:p.stdin.close()
                        except BrokenPipeError:pass
                    if not collect_until(time.monotonic()+3):
                        raise RuntimeError('owned child cleanup failed')
        result['control_pipe_closed']=p.stdin.closed
    result['temporary_directory_removed']=not folder.exists()
    return result

def main():
    assert platform.python_version()=='3.11.8' and sys.platform=='darwin'
    assert NODE and subprocess.run([NODE,'--version'],capture_output=True,text=True,check=True,timeout=2).stdout.strip()=='v22.18.0'
    report={'python':platform.python_version(),'platform':platform.platform(),'node':'v22.18.0',
            'script_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                for name in ('supervise_budgets.py','limit_exec.py','budget_child.cjs')},
            'trials':[trial(mode) for mode in ('ok','spin','pending','syntax')]}
    (ROOT/'budget-results.json').write_text(json.dumps(report,indent=2)+'\n')
    expected={'ok':'COMPLETED','spin':'CPU_LIMIT','pending':'WALL_LIMIT','syntax':'SCRIPT_ERROR'}
    for row in report['trials']:
        assert row['status']==expected[row['mode']],row
        assert row['reaped'] and row['control_pipe_closed'] and row['temporary_directory_removed']
        assert all(x['owned'] and x['not_daemon'] for x in row['ownership_checks'])
        assert set(row['environment_keys'])=={'LANG','TMPDIR'}
        assert row['heap_limit_bytes']==35*1024*1024
    spin,pending=report['trials'][1:3]
    assert not any(e['event']=='timer_fired' for e in spin['events'])
    assert any(e['event']=='timer_fired' for e in pending['events'])
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
```

</details>

将三个文件放在专属可写目录，确认固定版本和 Multica CLI 可读 daemon 状态后，以 Python 3.11.8 执行 `python supervise_budgets.py`。它只接受四个自制样例，主进程没有无限循环；每个运行都关闭控制管道、回收子进程、删除专属临时目录。另有两个故障回归模拟 daemon 查询失败和身份校验拒绝：零未经核对的信号，pending 样例通过控制通道 EOF 退出并被回收。该退路依赖本例已知的合作式控制通道；不构成任意恶意程序的通用回收证明。

### 4. 失败结果也是契约的一部分

至少区分编译/运行错误、权限拒绝、审批等待、CPU/墙钟到期、内存或其他进程失败；只有明确的运行时诊断才能把异常退出归因为堆不足，不能见到 SIGKILL 就写 OOM。超时终止与“仍在运行、可继续 wait”也应是不同状态。

失败响应应携带 run/调用 ID、已知用量、终止原因、可用的部分结果及每个工具的真实执行状态。上述 CPU/wall 样例没有派发工具，因此没有业务副作用；实际 Code Mode 可能已经发出工具请求，杀掉执行器不能撤销宿主或远端已执行的动作。需要先依据独立账本核实，再决定是否允许重试；日志丢失或确认缺失时保留 unknown，不伪造成功、失败或回滚。

mock 的 total=60 与 4 credits 只验证确定性数据流和配额，没有测模型往返的真实延迟、Token 或账单。实际收益要固定任务与数据，比较质量、模型调用、工具调用、重试、资源使用与总费用，不能只报“并行更快”或“一次模型调用”。

## 常见误区

- **“进了沙箱，就不需要逐个工具审批。”** 隔离执行资源与批准业务动作是不同边界；宿主仍需检查每次调用的当前权限及审批范围。
- **“并行更快、模型往返更少，所以总费用更低。”** 工具次数可能不变，CPU、存活时间、输出和重试还可能增加；要算全链路成本。
- **“Promise.race 或同线程 setTimeout 能终止所有脚本。”** 同步循环会阻塞该事件循环；可信外层的计量/中断和回收责任不能交给 guest。
- **“CPU 低就可以一直等，堆受限就不会拖垮宿主。”** 等待要有墙钟限制，堆之外还有进程和工具资源，预算也不能在重试时重置。

## 延伸 / 追问

**脚本先发慢工具，再一边等它一边热循环，CPU 该不该算？** 应照算正在消耗的计算；“有 pending I/O”不是免单信号。工具等待计入墙钟及后端自身预算，guest 的实际计算另计 CPU，不能把整段等待简单归为零 CPU。

**预算到期，但 mock/真实写工具已经执行，能否从头重跑程序？** 先查看宿主独立记录的动作状态和幂等键。确认缺失不等于没执行；可能需要查询、补偿或重新审批，不能把 worker 被杀当作事务回滚。

**哪些任务不值得引入 Code Mode？** 本来就是一次工具调用，或每一步都要新的语义判断/人工确认；固定批处理 API 已足够时也可能更简单。新增执行器的安全、观测和资源治理成本应进入取舍。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定版本 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/dsh-5.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-5.html)、[slides/codex-22.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-22.html)。仅为学习线索；课程对其他运行时的 busy-time、默认额度、yield、审批路径与费用收益未作为本文实测事实。不复制其 AGPL 正文、实现或图片。
- Node.js **v22.18.0**：[CLI 堆配置](https://github.com/nodejs/node/blob/v22.18.0/doc/api/cli.md#--max-old-space-sizesize-in-mib)、[V8 heap_size_limit](https://github.com/nodejs/node/blob/v22.18.0/doc/api/v8.md#v8getheapstatistics)、[node:vm 的安全边界说明](https://github.com/nodejs/node/blob/v22.18.0/doc/api/vm.md)、[process 与事件循环退出](https://github.com/nodejs/node/blob/v22.18.0/doc/api/process.md#event-beforeexit)、[许可证](https://github.com/nodejs/node/blob/v22.18.0/LICENSE)。固定文档与本机版本对应；未把 Node 子进程当成生产 Code Mode 实现。
- Python Software Foundation，CPython **v3.11.8**：[resource 的 RLIMIT_CPU/CORE/FSIZE](https://github.com/python/cpython/blob/v3.11.8/Doc/library/resource.rst)、[subprocess 生命周期](https://github.com/python/cpython/blob/v3.11.8/Doc/library/subprocess.rst)、[os.wait4](https://github.com/python/cpython/blob/v3.11.8/Doc/library/os.rst)、[许可证](https://github.com/python/cpython/blob/v3.11.8/LICENSE)。
