---
id: engineering-0034
title: 工具命令超出一次调用时限后，exec、wait 与宿主进程应怎样管理输出、超时和清理责任？
category: engineering
tags: [exec-wait, subprocess, process-ownership, lifecycle, output-retention]
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

工具命令超出一次调用时限后，exec、wait 与宿主进程应怎样管理输出、超时和清理责任？客户端已经断开，但启动的进程还在运行，谁继续排空管道、执行超时和回收，谁能读取最后结果？

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**把一次调用的等待、客户端连接、执行资源和结果保存分开管理，并给执行资源指定持续存在的 owner。** exec 返回运行句柄时，通常只是让出控制权；必须还能追到持有进程、实施预算、收尾和保存结果的宿主。wait 只负责按契约观察或继续等待，不能凭名字假设它会杀进程、重启任务或永久保留输出。

[agent-0016](agent-0016-checkpoint-resume.md) 讨论 Agent 状态恢复，[agent-0057](agent-0057-code-mode-tool-orchestration.md) 讨论执行预算，[engineering-0026](engineering-0026-streaming-tool-transcript-closure.md) 讨论工具结果收口。本题新增 OS 进程、管道与宿主的实际持有关系。某些 exec/wait 管的是 JS cell，有些管 shell/PTY 会话或远端 job，必须先查具体协议，不能把这些句柄混为一类。

### 1. 先辨认返回了哪一种事实

| 观察 | 可以得出的结论 | 还不能得出的结论 |
| --- | --- | --- |
| yielded / session ID / cell ID | 本次观察窗口结束，后续可按协议查询 | 进程已退出、结果已交付、服务已被可靠托管 |
| OS exit code 已取得 | 直接子进程有可观察的退出结果 | stdout/stderr 已读完、子孙进程已结束、结果已持久保存 |
| pipes EOF + wait/reap + 收尾完成 | 指定执行资源与输入输出已按约定回收 | 工作负载成功；超时、非零退出或日志失败仍是失败 |
| 当前页无输出 | 这次没有可交付的新字节 | 程序完成、卡死，或 stdin 已关闭 |
| 终态页仍有 has_more | 进程/owner 已终结，但保留日志还有未读尾部 | 客户端已经消费完整结果 |

一个可审计的注册项应有 job/attempt、owner 和宿主世代、创建参数、开始时间、最大寿命、状态、退出结果、输出位置与截断标记。操作句柄还须经过身份、所有权与权限校验；能猜到 ID 或持有某个 Python 对象都不等于生产授权。

exec 的响应丢失也不应直接再 spawn：若支持幂等 request ID，可先查询已登记的 attempt；否则标记启动结果待核实。重试命令可能重复副作用。返回一个编号，没有建立可靠的注册、接管和结果渠道，就只是提供了一个短期引用。

### 2. owner 要活得比客户端请求久

| 方案 | 适用情形 | 代价与不适用场景 |
| --- | --- | --- |
| 前台执行到结束或明确取消 | 很短、单次任务，不需要跨调用交互 | 简单，但长任务受请求窗口约束；不适合借一个短 RPC 偷偷运行长期服务 |
| 宿主持有进程 + yield/wait + 输出游标 | 同一宿主存活期间的编译、交互工具、较长命令 | 要有独立排空/超时循环和显式 shutdown；不能承诺宿主崩溃后仍可使用内存句柄 |
| 独立服务管理器 / 持久 job 系统 | 要跨客户端、Agent 或宿主重启继续运行的工作 | 需部署、权限、日志保留、重连、重试/去重和接管协议；不必为每个毫秒级工具都引入这套成本 |

客户端断开时，可选择继续、取消，或限时等重新连接，但必须明确：由谁执行这个选择，多久后截止，谁保存退出结果。不能把清理只挂在客户端的下一次 wait 上。owner shutdown 也要关闭新任务准入、处理已启动集合、等待资源释放并留下结果，不能只清空句柄表。

宿主自身死亡是另一种故障。进程可能被容器/服务管理器回收，也可能存活并失去原通道，取决于 OS、进程组、管道、父子关系和部署策略。模型停止或一次回调取消不自动给子进程发送终止信号；父进程退出也不是跨平台的“所有后代已回收”证明。若要跨宿主恢复，应由独立、持久的执行所有者保存可重新认证的 job 身份和状态，不能拿重启前的 PID 盲目发信号。

具体一手实例是 systemd v256：`KillMode=control-group` 针对该 unit 的剩余进程，`process` 只针对主进程；文档警告后者可能让进程脱离服务生命周期管理。`TimeoutStopSec` 与后续终止策略也有明确语义。这只是 Linux 服务管理器的一个固定版本实例，不是下面 Python fixture、任意容器或所有 Agent 平台的保证。

### 3. 三类等待，三类输出边界

| 项目 | 应明确的契约 | 常见错误 |
| --- | --- | --- |
| yield / poll 窗口 | 一次 API 等多久、是否返回新输出；等待结束后资源由谁继续持有 | 每次 wait 都重新给任务一份总寿命预算 |
| job 寿命与清理宽限 | 从哪个阶段开始计时、超时如何请求停止、何时升级、何时 wait/reap | 把请求 timeout 当作进程已杀；发了信号就报告资源释放 |
| stdin | 是否可写、编码、短写/背压、输入序列化及显式 EOF | 空 poll 当作 Enter/EOF；把 pipe 中的 Ctrl-C 字节当作通用 OS 信号 |
| stdout/stderr 保存与展示 | 持续排空、字节游标、保留额度、截断/丢弃计数和保留期 | UI 显示截断冒充完整日志；只读 stdout 导致 stderr 塞满阻塞 |

CPython v3.11.8 的 `Popen.poll()` 返回 None 表示尚未取得退出结果；`wait(timeout)` 超时不杀进程，且只 wait 不排空 PIPE 可能死锁。`communicate(timeout)` 会处理三条流，但超时后也不会自动杀子进程，调用方还要收尾；`subprocess.run(timeout=...)` 的行为不同，会终止并等待其直接子进程。不能笼统说“Python timeout 都会回收”。communicate 将数据缓存在内存，也不适合无限输出。

长输出可由 owner 持续写入受限 spool，再把分页片段交给客户端。达到保留上限时仍应排空或明确终止生产者，否则停读管道会制造新的阻塞。若丢弃字节，要返回完整性标记；log flush 不等于 fsync、断电持久性或跨宿主可访问。流式文本页也可能切开编码边界，原始字节与显示文本应分开看。

取消应先定位仍由本 owner 持有的资源，再按策略发送停止请求/信号、给有界宽限、必要时升级，最后取回退出状态并排空/关闭管道。只 kill 主 PID 不一定处理后代；只有在已证明所有权的进程组、cgroup 或 job object 上，才能使用相应集合清理。按可执行文件名杀进程可能误杀平台 daemon，本例完全不这样做。

### 4. 客户端断开后的真实进程示例

实验是原创 Python 3.11.8 / POSIX fixture，客户端断开仅表示移除本轮内的 mock attachment，不是真实网络断流。一个宿主 Python 进程创建有限的无害 worker；宿主中的 supervisor 线程独立于客户端请求，持续读两条输出管道、实施最大寿命并 wait/reap。整个测试驱动始终在前台等待这些资源收完，没有通过结束 Agent 本轮制造断开。

| 时间顺序 | 谁执行 | 实际结果 |
| --- | --- | --- |
| worker 启动并报告 PID/PPID/nonce | owner 创建并持有 Popen；worker 发送合成握手 | owner 登记直接子进程，客户端 A 获取进程内 attachment |
| A wait 一个很短窗口 | 客户端观察 | `phase=yielded, exit_code=null`；进程仍等待输入 |
| A 发送 go，随后 disconnect | A 的 attachment 被移除 | 子进程此时仍活着；旧句柄不能继续读、写或取消 |
| 没有客户端再 poll | supervisor 自行运行 | worker 输出 DONE，owner 排空 stdout/stderr、取得 exit_code=0、关闭管道；前台驱动 join supervisor |
| owner 给 B 发新 attachment | 同一活宿主内的受控测试入口 | B 从保留日志的 byte cursor=0 分页读取；取得 DONE 与最后诊断，直到 has_more=false |

本例回答“谁回收”是 owner 的 supervisor，“谁读结果”是宿主明确发放 attachment 的 B；B 不负责推进进程或清理。attachment 只是演示授权路由的登记对象，不做真实身份认证。owner.close 后失效，也不能在另一个宿主上恢复。

另测了工作负载 exit7、墙钟超时、正常取消和忽略 SIGTERM 后升级 SIGKILL。超时/取消的终态保留负退出码和 outcome；日志短写返回 supervisor_failed，不伪装成功。每个实际信号前均检查保留的 Popen 对象、登记 PID、创建参数和自建 worker 的 PID/PPID/nonce，并与刚由 `multica daemon status` 取得的 daemon PID 快照比较。快照必须小于 120 秒；实际测试的信号使用年龄小于 3 秒的快照。该核对仅服务本地自制进程，不是恶意子进程认证、跨重启 PID 接管或任意远端进程控制。

### 5. 可复跑实现及责任上限

将下面两段分别保存为标注的文件。worker 只处理固定 ASCII 输入，空环境、无 shell/网络/业务文件、无子孙进程；自己的 4 秒退出后备只用于实验兜底。真正独立于 child 的外部监督是宿主 supervisor，普通 job 寿命最多 2 秒，SIGTERM 后宽限 0.15 秒；清理 wait 上限 5 秒、线程 join 上限 6 秒，不把这些教学值说成生产硬 SLA。创建进程本身、宿主崩溃和 OS 停顿也未得到硬时限保证。

<details>
<summary>展开无害 worker 与 exec/wait 教学 supervisor</summary>

```python
# file: harmless_worker.py
"""Owned, finite test child: no shell, network, credentials, descendants or business files."""
import json,os,select,signal,sys,threading,time
nonce, mode = sys.argv[1:]
if mode == 'ignore_term':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
# Independent last resort for this synthetic child, including a blocked pipe write.
backstop = threading.Timer(4.0, lambda: os._exit(97))
backstop.start()
try:
    print(json.dumps(dict(pid=os.getpid(), ppid=os.getppid(), nonce=nonce)), flush=True)
    print('READY', flush=True)
    print('diagnostic-start', file=sys.stderr, flush=True)
    if mode == 'burst':
        os.write(1, b'O' * 50_000)
        os.write(2, b'E' * 50_000)
    pending = b''
    while True:
        if not select.select([0], [], [], 0.05)[0]:
            continue
        data = os.read(0, 64)
        if not data:
            print('EOF', flush=True)
            break
        pending += data
        if len(pending) > 256:
            raise SystemExit(9)
        if b'go\n' in pending:
            print('RUNNING', flush=True)
            time.sleep(0.15)
            print('DONE', flush=True)
            print('diagnostic-end', file=sys.stderr, flush=True)
            if mode == 'fail':
                raise SystemExit(7)
            break
finally:
    backstop.cancel()
    backstop.join()
```

```python
# file: process_fixture.py
"""Original POSIX test supervisor; all jobs are our finite harmless_worker.py."""
import json,math,os,selectors,signal,subprocess,sys,threading,time,uuid
from pathlib import Path
import tempfile

AUDITS = []
START_FAILURES = []


class Refused(Exception):
    pass


def daemon_pid_from_snapshot(path):
    path = Path(path)
    if not 0 <= time.time() - path.stat().st_mtime <= 120:
        raise Refused('refresh_daemon_status')
    data = json.loads(path.read_text())
    if data.get('status') != 'running' or type(data.get('pid')) is not int or data['pid'] <= 1:
        raise Refused('invalid_daemon_status')
    return data['pid']


def check_identity(pid, owner, registered_pid, handshake, nonce, daemon_pid):
    if (pid <= 1 or pid in (owner, daemon_pid) or pid != registered_pid or
            handshake != dict(pid=pid, ppid=owner, nonce=nonce)):
        raise Refused('process_ownership_mismatch')


class Owner:
    """Supervisor is outside the child and independent of attached clients, not durable."""
    def __init__(self, root, daemon_state, mode='normal', lifetime=2.0, cap=4096):
        if mode not in ('normal', 'fail', 'burst', 'ignore_term'):
            raise Refused('invalid_mode')
        if type(cap) is not int or not 128 <= cap <= 65536:
            raise Refused('invalid_cap')
        if type(lifetime) not in (int, float) or not math.isfinite(lifetime) or not 0.1 <= lifetime <= 2:
            raise Refused('invalid_lifetime')
        self.root = Path(root)
        self.root.mkdir(exist_ok=False)
        self.daemon_state = Path(daemon_state).resolve()
        daemon_pid_from_snapshot(self.daemon_state)  # Check before spawning anything.
        self.cap, self.owner_pid, self.nonce = cap, os.getpid(), uuid.uuid4().hex
        self.lock = threading.RLock()
        self.ready, self.done, self.stop = threading.Event(), threading.Event(), threading.Event()
        self.clients, self.handshake, self.signals = {}, None, []
        self.reason, self.fault, self.closed = 'exited', None, False
        self.kept = dict(stdout=0, stderr=0)
        self.seen = dict(stdout=0, stderr=0)
        self.eof = dict(stdout=False, stderr=False)
        self.logs = {k: (self.root/(k+'.log')).open('wb') for k in self.kept}
        self.args = (sys.executable, '-I', '-u', str(Path(__file__).with_name('harmless_worker.py').resolve()), self.nonce, mode)
        try:
            self.process = subprocess.Popen(self.args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=self.root, env={}, start_new_session=True, bufsize=0)
        except BaseException:
            for out in self.logs.values(): out.close()
            raise
        self.pid = self.process.pid
        self.deadline = time.monotonic() + lifetime
        try:
            os.set_blocking(self.process.stdin.fileno(), False)
            self.thread = threading.Thread(target=self._run, name='owned-process-supervisor')
            self.thread.start()
        except BaseException:
            # Failed supervisor startup: close stdin and drain our finite child.
            # communicate(timeout) never sends an unchecked signal.
            try:
                self.process.communicate(timeout=5)
            finally:
                for stream in (self.process.stdin,self.process.stdout,self.process.stderr):
                    if not stream.closed: stream.close()
                for out in self.logs.values(): out.close()
            START_FAILURES.append(dict(pid=self.pid,exit_code=self.process.returncode,
                reaped=self.process.returncode is not None,supervisor_started=False,
                pipes_closed=all(f.closed for f in (self.process.stdin,self.process.stdout,self.process.stderr)),
                logs_closed=all(f.closed for f in self.logs.values())))
            raise

    def _signal(self, sig):
        p = self.process
        if p.poll() is not None:
            return
        daemon_pid = daemon_pid_from_snapshot(self.daemon_state)
        check_identity(p.pid, self.owner_pid, self.pid, self.handshake, self.nonce, daemon_pid)
        if tuple(p.args) != self.args or os.getpid() != self.owner_pid:
            raise Refused('process_handle_mismatch')
        # Only the retained Popen object is signalled, never an arbitrary PID/name/group.
        p.send_signal(sig)
        self.signals.append(dict(pid=self.pid, owner_pid=self.owner_pid, daemon_pid=daemon_pid,
            signal=int(sig), identity_checked=True, source='fresh_cli_snapshot', snapshot_age_s=round(time.time()-self.daemon_state.stat().st_mtime, 3)))

    def _run(self):
        p, selector, prefix = self.process, selectors.DefaultSelector(), b''
        stopping, escalated = None, False
        try:
            for name, stream in (('stdout', p.stdout), ('stderr', p.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while True:
                now = time.monotonic()
                if stopping is None and (self.stop.is_set() or now >= self.deadline):
                    if self.ready.is_set():
                        self.reason = 'cancelled' if self.stop.is_set() else 'timed_out'
                        self._signal(signal.SIGTERM)
                        stopping = time.monotonic()
                if stopping is not None and not escalated and now - stopping >= 0.15:
                    self._signal(signal.SIGKILL)
                    escalated = True
                for key, _ in selector.select(0.01):
                    stream, name = key.fileobj, key.data
                    data = os.read(stream.fileno(), 8192)
                    if not data:
                        selector.unregister(stream)
                        stream.close()
                        self.eof[name] = True
                        continue
                    if name == 'stdout' and self.handshake is None:
                        prefix += data
                        if b'\n' in prefix:
                            self.handshake = json.loads(prefix.split(b'\n', 1)[0])
                            check_identity(self.pid, self.owner_pid, self.pid, self.handshake,
                                           self.nonce, daemon_pid_from_snapshot(self.daemon_state))
                            self.ready.set()
                    with self.lock:
                        self.seen[name] += len(data)
                        part = data[:max(0, self.cap-self.kept[name])]
                        if part:
                            if self.logs[name].write(part) != len(part):
                                raise OSError('short_log_write')
                            self.logs[name].flush()
                            self.kept[name] += len(part)
                if p.poll() is not None and not selector.get_map():
                    break
        except BaseException as exc:
            self.fault, self.reason = type(exc).__name__ + ':' + str(exc), 'supervisor_failed'
            try:
                self._signal(signal.SIGKILL)
            except BaseException as guard_error:
                self.fault += ';cleanup:' + type(guard_error).__name__
                # No unsafe signal fallback. Our synthetic child self-exits by 4s.
        finally:
            # wait(timeout) itself does not kill. Child backstop is specific to this fixture.
            reaped = False
            try:
                p.wait(timeout=5)
                reaped = True
            except subprocess.TimeoutExpired:
                self.fault, self.reason = 'cleanup_deadline_exceeded', 'cleanup_unresolved'
            finally:
                with self.lock:
                    for resource in (p.stdin,p.stdout,p.stderr,*self.logs.values(),selector):
                        try:
                            resource.close()
                        except BaseException as close_error:
                            self.fault = self.fault or 'close:' + type(close_error).__name__ + ':' + str(close_error)
                            self.reason = 'supervisor_failed'
                closed_all = all(f.closed for f in (p.stdin,p.stdout,p.stderr,*self.logs.values()))
                if reaped and closed_all:
                    self.done.set()
                else:
                    self.reason, self.fault = 'cleanup_unresolved', self.fault or 'resources_still_open'

    def attach(self):
        with self.lock:
            if self.closed: raise Refused('host_closed')
            handle = object()  # Host-issued mock attachment, not production authentication.
            self.clients[handle] = dict(stdout=0, stderr=0)
            return handle

    def disconnect(self, handle):
        with self.lock:
            self._client(handle)
            del self.clients[handle]  # Client lifetime does not own process cleanup.

    def _client(self, handle):
        if self.closed or handle not in self.clients:
            raise Refused('detached_or_unknown_handle')
        return self.clients[handle]

    def send(self, handle, data):
        if type(data) is not bytes or len(data) > 64:
            raise Refused('invalid_stdin')
        with self.lock:
            self._client(handle)
            if self.process.stdin.closed or self.process.poll() is not None:
                raise Refused('stdin_closed')
            try:
                return os.write(self.process.stdin.fileno(), data)  # Empty bytes is not EOF.
            except BlockingIOError as exc:
                raise Refused('stdin_would_block') from exc
            except BrokenPipeError as exc:
                raise Refused('stdin_closed') from exc

    def eof_stdin(self, handle):
        with self.lock:
            self._client(handle)
            if not self.process.stdin.closed: self.process.stdin.close()

    def wait(self, handle, seconds=0, limit=64):
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= 0.25:
            raise Refused('invalid_wait')
        if type(limit) is not int or not 1 <= limit <= 4096:
            raise Refused('invalid_page_limit')
        with self.lock: self._client(handle)
        self.done.wait(seconds)
        with self.lock:
            cursor = self._client(handle)  # Recheck attachment after the wait.
            result = {}
            for name in cursor:
                with (self.root/(name+'.log')).open('rb') as source:
                    source.seek(cursor[name]); data = source.read(min(limit, max(0, self.kept[name]-cursor[name])))
                cursor[name] += len(data)
                result[name] = data.decode('utf-8', errors='replace')
            result.update(phase='completed' if self.done.is_set() else ('cleanup_unresolved' if self.reason=='cleanup_unresolved' else 'yielded'),
                exit_code=self.process.returncode if self.done.is_set() else None,
                outcome=self.reason if self.done.is_set() or self.reason=='cleanup_unresolved' else None, fault=self.fault,
                next_cursor=dict(cursor), has_more=any(cursor[k]<self.kept[k] for k in cursor),
                dropped={k:self.seen[k]-self.kept[k] for k in cursor}, pipes_eof=dict(self.eof))
            return result

    def cancel(self, handle):
        with self.lock:
            self._client(handle)
            self.stop.set()  # Request only; join still required.

    def join(self):
        self.thread.join(6)
        if (self.thread.is_alive() or self.process.poll() is None or
                not all(f.closed for f in (self.process.stdin,self.process.stdout,self.process.stderr,*self.logs.values()))):
            raise RuntimeError('owned_resources_not_reclaimed')

    def close(self):
        if self.closed: return self.audit
        self.stop.set()
        self.join()
        with self.lock:
            self.closed = True
            self.clients.clear()
        row = dict(pid=self.pid, exit_code=self.process.returncode, reaped=True,
            supervisor_joined=True, pipes_closed=all(s.closed for s in
                (self.process.stdin,self.process.stdout,self.process.stderr)),
            logs_closed=all(f.closed for f in self.logs.values()), signals=list(self.signals), fault=self.fault,
            kept=dict(self.kept), seen=dict(self.seen), pipes_eof=dict(self.eof),
            captured_logs={k:(self.root/(k+'.log')).read_text(errors='replace') for k in self.kept})
        AUDITS.append(row)
        self.audit = row
        return row

    def __enter__(self): return self
    def __exit__(self, *_): self.close()


def demo(daemon_state):
    with tempfile.TemporaryDirectory(prefix='yao396-owned-',dir=Path(__file__).resolve().parent) as root:
        with Owner(Path(root)/'job', daemon_state) as owner:
            first = owner.attach()
            assert owner.ready.wait(1)
            first_poll = owner.wait(first, 0)
            assert first_poll['phase'] == 'yielded' and first_poll['exit_code'] is None
            owner.send(first, b'go\n')
            owner.disconnect(first)
            live_at_disconnect = owner.process.poll() is None
            owner.join()  # Foreground supervisor collection, while no client is attached.
            second = owner.attach(); parts=[]
            while True:
                page=owner.wait(second, 0, 32);parts.append(page)
                if not page['has_more']: break
            out=''.join(p['stdout'] for p in parts);err=''.join(p['stderr'] for p in parts)
            result=dict(initial_phase=first_poll['phase'],live_at_disconnect=live_at_disconnect,
                second_client_reads_done='DONE' in out and 'diagnostic-end' in err,
                final_phase=page['phase'],exit_code=page['exit_code'],outcome=page['outcome'],
                pipes_eof=page['pipes_eof'],all_retained_output_consumed=not page['has_more'])
        result['cleanup']=AUDITS[-1]
    result['owned_directory_removed']=not Path(root).exists()
    return result


if __name__=='__main__':
    print(json.dumps(demo(Path(sys.argv[1]).resolve()),indent=2))
```

</details>

在专属目录先执行 `multica daemon status --output json > daemon-status.json`，再运行 `python3 process_fixture.py daemon-status.json`。这只读取 daemon 状态；信号目标只能是本程序刚创建并核对的 worker。没有 Multica 的环境应先替换成可验证的本机保护进程清单提供方，不能填一个随意 PID 伪称完成了本实验核对。

2026-09-16 实跑：22 tests 通过，0 failures / 0 errors；19 个真实自建 worker 均 wait/reap（18 个正常创建的 owner 加 1 个 supervisor 启动失败后的收尾），18 个 supervisor 线程 join，全部 stdin/stdout/stderr 与日志句柄关闭，22 个测试根目录及 demo 根目录删除。5 次实际信号均有所有权/daemon PID 核对记录；两条预期 fault 是注入的日志短写和日志关闭错误；线程启动失败另行记录为 constructor 失败，已创建的 child 通过关闭 stdin、排空输出并等待退出收回。这意味着断言通过，不意味着故意超时、退出 7 或日志失败的工作负载成功。

输出测试向 stdout 和 stderr 各写 50,000 个合成字节，而每流只保留 128 bytes；owner 仍排空到 EOF，显式报告 dropped。原始字节留在受限本地日志，API 页按 byte cursor 移动，显示用 UTF-8 replacement 解码；本例 ASCII 页不会损坏文本，不宣称任意多字节编码分页无损。终态页可还有尾部，客户端仍需读到 has_more=false。

所有权失败时不绕过核对乱发信号；专用 worker 的自退出后备不应推广到任意程序。若真实系统清理无法确认，应该保留 unresolved 与负责者，不能标完成后抛下资源。本实现只验证仍存活的本地宿主、直接子进程和有限输入；没有演示宿主崩溃/重启接管、真实 TCP/PTY、递归进程树、生产授权、持久服务托管或断电恢复。没有修改既有业务进程、凭据、平台调度或运行时。

## 延伸 / 追问

- **拿到 session ID 后，Agent 能直接结束本轮吗？** 先看宿主的生命周期契约。若任务随本轮结束而失去 owner/唤醒渠道，就不能结束并期待后台自动交付；应在同轮收集，或先完成明确的独立托管交接。
- **wait 返回 completed，但还有 has_more，算成功交付了吗？** completed 说明执行监督达到终态，不代表 exit0、日志完整或客户端读完。检查 outcome/exit_code/fault/截断标记，再读完保留尾部并记录交付状态。
- **客户端重连带旧 PID，能否直接 kill？** 不能。PID 可能复用，旧宿主/世代也可能失效；要重新定位持久 job，验证当前 owner 与授权、执行实例身份和清理范围，不能凭编号猜测。
- **日志已经保存了，为何还不能算可靠托管？** 还缺执行持有者、宿主故障时的回收/接管、权限、保留与检索渠道。即使内容在本地文件中，另一机器或重启后也未必能找到或获准读取。

## 常见误区

- **“返回 session ID 就是服务已被可靠托管。”** 它可能只是当前宿主的内存索引；没有持久 owner 和结果通路就没有这个保证。
- **“模型结束等于进程退出。”** 模型、调用、连接和 OS 资源是不同生命周期，停止与回收必须有明确负责人。
- **“空 poll、stdin EOF 和中断是一回事。”** 读结果不应隐式注入输入；关闭 stdin、向 PTY 发控制字符、发送 OS 信号各有不同条件。
- **“kill 已发送或 exit code 已有，结果就完整了。”** 还要检查退出是否真正取得、所有权范围、管道尾部、保存错误和客户端消费进度。

## 参考

- 洛小山《AI 产品从入门到精通》learn-ai，固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/codex-12.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-12.html)、[slides/codex-22.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-22.html)、[slides/codex-23.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-23.html)、[slides/dsh-17.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-17.html)。只作学习线索；课件的具体产品默认值、工具面、重连/持久性、审批或私有/restored 源码行为未作为本文的一手确认，不搬运 AGPL 正文、代码或图片。
- CPython **v3.11.8**：[Doc/library/subprocess.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/subprocess.rst)，poll/wait/communicate/run 的超时差别、PIPE 死锁与内存缓冲警告；[Lib/subprocess.py · send_signal](https://github.com/python/cpython/blob/v3.11.8/Lib/subprocess.py#L2174) 在信号前 poll 以减少 PID 复用竞态，也指出剩余竞态，不能据此建立跨重启身份协议。PSF/history 许可材料只阅读引用。
- systemd **v256**：[man/systemd.kill.xml](https://github.com/systemd/systemd/blob/v256/man/systemd.kill.xml)，KillMode 范围、SIGTERM/SIGKILL 及停止策略；[man/systemd.service.xml](https://github.com/systemd/systemd/blob/v256/man/systemd.service.xml)，ExecStop/TimeoutStopSec 的等待与生命周期语义。文件标注 LGPL-2.1-or-later；本次没有运行或修改 systemd 服务。
