---
id: agent-0058
title: 工具发现与注册动态变化时，怎样保证一次采样看到的工具菜单和实际分发能力一致？
category: agent
tags: [tool-registry, mcp, snapshot, discovery, authorization, generation]
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

工具发现与注册动态变化时，怎样保证一次采样看到的工具菜单和实际分发能力一致？如果模型拿到菜单后 MCP 断开，重连时同名工具的 schema 已改变，旧调用应如何处置？

## 答案 · GPT-6

每次模型采样前，host 都应生成一份不可变的工具快照，把**送给模型的菜单与执行时的具体绑定**一起保存。模型返回调用后，分发器先找该次采样的快照，再检查当前权限和绑定是否仍有效。有效才执行；失效就明确拒绝，让下一次采样使用新菜单。这里的一致性是“不把旧菜单上的调用悄悄解释成新工具”，并不承诺菜单上的工具一定能成功执行。

目录的基本设计见 [agent-0014](agent-0014-tool-registry-design.md)，重叠工具的语义选择见 [agent-0050](agent-0050-overlapping-mcp-tool-selection.md)。本题只讨论从采样到分发之间的时间差；连接重启策略、业务幂等和审批系统另有各自的契约。

### 1. 注册、广告和执行是三道边界

注册表记录 host 已知的工具描述与处理入口；广告是本次模型请求里实际带上的工具定义；执行则是当前请求在授权、可用性和版本检查后真正进入某个实现。注册可以早于连接就绪，也可以保留断线工具的描述，因此注册成功不等于对模型可见，更不等于当前可执行。

下表是**本题 host 的策略定义**，不是 MCP 标准字段，也不声称所有运行时都这样解释 `hidden`：

| 状态 | 本次模型菜单 | 按需发现 | 模型调用的分发规则 |
| --- | --- | --- | --- |
| 可见 `visible` | 在线且有权限时包含完整 schema | 可直接使用 | 必须属于本步快照，并再次通过当前授权与版本检查 |
| 延迟 `deferred` | 默认不包含完整 schema | 只返回调用方获准发现的描述 | 本例在发现后由 host 激活到**下一步快照**，本步不能猜名字抢先调用 |
| 隐藏 `hidden` | 不包含 | 不泄露名称与描述 | 本例的模型分发入口拒绝；内部维护入口若需要调用，须另有明确权限和审计 |

隐藏与执行权限是独立维度。有些框架的 hidden 仅指“不广告但内部仍能解析”，不能照搬为安全隔离。若模型还能调用 shell、Code Mode 或通用 RPC 代理，同一受保护能力也必须在这些入口的网关检查；仅从 `tools` 数组删掉名字或提示模型“不要用”不够。

每个 step 指一次模型采样，不是整段用户对话，也不是一次工具调用。采样快照至少绑定以下信息：

- host 认定的 tenant、principal、run、step 与 snapshot ID；这些身份由可信请求上下文提供，不能从模型参数采信。
- 本步公开名到 `(provider identity, raw tool name)` 的明确映射，完整 schema、工具描述及曝光决策。本例使用 `docs__lookup`，并拒绝会造成别名歧义的名字。
- 连接 generation、目录或定义 revision、采样时 policy version。重连使 generation 单调增加；同连接内完整目录替换增加 revision。schema hash 可辅助检测变化，不能代替连接身份或实现版本。

把目录拉取结果先完整校验，再一次发布；分页过程中不要边收到边更新模型菜单。异步目录请求还要携带发起时的 generation/revision，发布时做比较，防止旧连接的响应或较早的刷新结果覆盖新目录。收到已知变更时，host 可以先阻止旧绑定准入，再刷新并重新采样。**本例 `refresh` 只模拟完整结果发布，不实现分页或变更通知接收器**；真实分页读取是否得到服务端一致快照，需要服务端另行保证。

当前权限仍然具有否决权：采样后的撤权不能被快照绕过，撤销后再授权也不能靠旧 policy version 自动复活旧请求。本例对任何 policy version 变化保守地要求重采样。已准入的副作用不能因为后来撤权就自动回滚。

### 2. 两种有效方案与各自代价

| 方案 | 适用条件与做法 | 代价与不适用场景 |
| --- | --- | --- |
| 检出失效即拒绝，重新采样 | 动态 MCP 或不能保留旧版本时，旧 generation/revision 调用返回明确失败；刷新后让模型根据新 schema 决定下一步。本例采用此方案 | 增加模型往返，变更频繁时可能反复失效；应给刷新次数和整个 step 设预算。不能把已有副作用的重试当成安全自动重放 |
| 有界保留旧绑定，等待本步结束 | 能同时保留旧实现或固定版本 endpoint 时，快照持有旧版本 lease；新 step 走新版本，旧 step 继续走旧版本，但执行仍复核当前权限 | 需要 lease 到期、引用计数和旧资源回收；已断开的旧 endpoint 无法靠“留着旧 schema”继续执行。紧急撤权也不能等待 lease 到期 |

不推荐收到旧调用后按裸名字查 `latest` 再补参数：例如 `doc_id` 改成 `slug`，即使都是字符串，语义和授权对象也可能不同。若提供兼容适配器，它本身就是受版本管理、经过测试的契约，不能在分发器里静默猜测。

MCP **2025-06-18** 的 `tools/list` 支持分页，`listChanged` 能力对应目录变更通知；`tools/call` 的标准参数是 `name` 和可选 `arguments`，没有通用的“必须执行该 schema revision”参数（固定源码见参考）。所以 host 快照只能约束自己观察到的状态与分发行为：它不能检测服务端未通知的实现替换，也不能仅靠一次 `tools/list` 证明远端执行的线性一致性。更强的保证需要服务端提供版本化工具身份、固定 endpoint 或显式版本校验支持。

### 3. 示例：采样之后断线，重连后参数从 doc_id 变为 slug

以下输入均为合成数据，`v1`、`v2` 只是原创 mock 的实现标签。假设权限允许 `docs/lookup`，没有业务副作用。step 1 的快照 `s1` 固定 `(generation=1, revision=1, required=[doc_id])`；重连后目录变成 `(2, 1, required=[slug])`。

| 顺序 | 事件或输入 | host 的判断与 mock 执行次数 |
| --- | --- | --- |
| 1 | 采样 step 1，发出 `s1` 菜单 | 模型看到 `docs__lookup(doc_id: string)`；0 次 |
| 2 | generation 1 断开，收到 `s1 + {doc_id: "D7"}` | `provider_offline`；0 次 |
| 3 | 重连 generation 2，仍收到 `s1 + {doc_id: "D7"}` | `stale_generation`，不调用 v2；0 次 |
| 4 | 有人把旧请求改成 `s1 + {slug: "intro"}` | 仍是 `stale_generation`，参数修正不能更新绑定；0 次 |
| 5 | step 2 重新采样得到 `s2`，却传 `{doc_id: "D7"}` | `invalid_arguments`；0 次 |
| 6 | 使用 `s2 + {slug: "intro"}` | `ok / v2 / ["intro"]`；累计 1 次 |

这些 status 是教学模型的 host 结果，**不是 MCP 标准错误码**。返回给模型的失败应保留 call ID、step、快照与已观察到的失败原因，不伪造工具业务结果。真正的 MCP 适配器还要区分协议错误、工具 `isError` 以及结果未知。这里没有实现 call ID 去重，重复的有效调用会再次执行；观察到一次执行不代表 exactly-once。

若旧调用已经在断线前被准入，允许它在原绑定上完成；若断线或重连先被处理，则拒绝。禁止的结果是“旧 `s1` 调到了 v2”。真实 RPC 的处理方式应是短临界区内复核并取得固定 generation 的 lease，再向那个连接发送；不能解锁后重新找最新连接，也不能把 Python lock 持有到网络返回。断线时远端是否已有副作用可能未知，不能靠刷新目录推断。

<details>
<summary>可运行的原创 Python 3.11.8 fixture（仅内存目录与即时 mock）</summary>

保存为 `catalog_fixture.py`，运行 `python3 catalog_fixture.py`。`required` 只实现“恰好这些字段且值均为字符串”的 schema 子集；不是通用 JSON Schema 校验器。内部描述与快照不可变，给模型的菜单是独立投影。`Context` 参数代表已认证的 host 输入；普通 Python 对象和私有属性不是认证系统或防恶意代码的沙箱。

```python
# file: catalog_fixture.py
"""Original in-memory teaching model. No MCP SDK, network or credentials."""
from dataclasses import dataclass, replace
import json
import re
from threading import Lock


@dataclass(frozen=True)
class Context:
    tenant: str
    subject: str
    run: str


@dataclass(frozen=True)
class Tool:
    name: str
    required: tuple[str, ...]  # deliberately only required string properties
    implementation: str     # label for a constant-time mock, not executable code
    visibility: str = 'visible'

    def schema(self):
        return {'type': 'object',
                'properties': {k: {'type': 'string'} for k in self.required},
                'required': list(self.required), 'additionalProperties': False}


@dataclass(frozen=True)
class Inventory:
    generation: int
    revision: int
    online: bool
    tools: tuple[Tool, ...]


@dataclass(frozen=True)
class Binding:
    provider: str
    generation: int
    revision: int
    tool: Tool

    @property
    def alias(self):
        return self.provider + '__' + self.tool.name


@dataclass(frozen=True)
class Snapshot:
    context: Context
    step: int
    policy_version: int
    bindings: tuple[Binding, ...]


class Catalog:
    def __init__(self):
        self._lock = Lock()
        self._inventories = {}
        self._policies = {}
        self._snapshots = {}
        self._steps = {}
        self._serial = 0
        self._calls = []

    @staticmethod
    def _definitions(provider, tools):
        tools = tuple(tools)
        names = [t.name for t in tools]
        identifiers = [provider, *names]
        if any(not re.fullmatch(r'[a-z][a-z0-9_]*', n) or '__' in n
               for n in identifiers) or len(set(names)) != len(names):
            raise ValueError('invalid or duplicate tool identity')
        for t in tools:
            if (type(t.required) is not tuple or
                    any(type(k) is not str or not k for k in t.required) or
                    len(set(t.required)) != len(t.required) or
                    type(t.implementation) is not str or
                    t.visibility not in ('visible', 'deferred', 'hidden')):
                raise ValueError('unsupported definition')
        return tuple(sorted(tools, key=lambda t: t.name))

    def connect(self, provider, tools):
        definitions = self._definitions(provider, tools)
        with self._lock:
            old = self._inventories.get(provider)
            generation = old.generation + 1 if old else 1
            self._inventories[provider] = Inventory(generation, 1, True, definitions)
            return generation

    def disconnect(self, provider, generation):
        with self._lock:
            old = self._inventories[provider]
            if old.generation != generation:
                return False  # late callback from an old connection
            self._inventories[provider] = replace(old, online=False)
            return True

    def version(self, provider):
        with self._lock:
            current = self._inventories[provider]
            return current.generation, current.revision

    def refresh(self, provider, expected, tools):
        definitions = self._definitions(provider, tools)  # validate all before publish
        with self._lock:
            old = self._inventories[provider]
            if not old.online:
                raise ValueError('provider offline')
            if (old.generation, old.revision) != expected:
                raise ValueError('stale inventory fetch')
            self._inventories[provider] = replace(old, revision=old.revision + 1,
                                                  tools=definitions)

    def policy(self, context, allowed):
        # Trusted host input, keyed by tenant AND principal; run has its own snapshot.
        allowed = frozenset(allowed)
        with self._lock:
            key = (context.tenant, context.subject)
            version, _ = self._policies.get(key, (0, frozenset()))
            self._policies[key] = (version + 1, allowed)

    def _policy(self, context):
        return self._policies.get((context.tenant, context.subject), (0, frozenset()))

    def discover(self, context):
        with self._lock:
            _, allowed = self._policy(context)
            return [dict(name=p + '__' + t.name, inputSchema=t.schema())
                    for p, i in sorted(self._inventories.items()) if i.online
                    for t in i.tools
                    if t.visibility == 'deferred' and (p, t.name) in allowed]

    def sample(self, context, step, activate=()):
        activate = frozenset(activate)
        with self._lock:
            if type(step) is not int or step <= self._steps.get(context, 0):
                raise ValueError('step must increase')
            version, allowed = self._policy(context)
            bindings = tuple(Binding(p, i.generation, i.revision, t)
                             for p, i in sorted(self._inventories.items()) if i.online
                             for t in i.tools if (p, t.name) in allowed and
                             (t.visibility == 'visible' or
                              (t.visibility == 'deferred' and p + '__' + t.name in activate)))
            self._serial += 1
            sid = 's' + str(self._serial)
            self._snapshots[sid] = Snapshot(context, step, version, bindings)
            self._steps[context] = step
            # Only a detached projection goes to the caller/model.
            menu = [dict(name=b.alias, inputSchema=b.tool.schema()) for b in bindings]
            return sid, menu

    def dispatch(self, context, step, sid, alias, arguments):
        # Instant local mocks execute under this lock. NEVER hold it across real RPC.
        with self._lock:
            snapshot = self._snapshots.get(sid)
            if snapshot is None:
                return {'status': 'unknown_snapshot'}
            if snapshot.context != context:
                return {'status': 'wrong_context'}
            if snapshot.step != step or self._steps.get(context) != step:
                return {'status': 'stale_step'}
            binding = next((b for b in snapshot.bindings if b.alias == alias), None)
            if binding is None:
                return {'status': 'not_advertised'}
            version, allowed = self._policy(context)
            if (binding.provider, binding.tool.name) not in allowed:
                return {'status': 'forbidden'}
            if version != snapshot.policy_version:
                return {'status': 'stale_policy'}
            current = self._inventories[binding.provider]
            if not current.online:
                return {'status': 'provider_offline'}
            if current.generation != binding.generation:
                return {'status': 'stale_generation'}
            if current.revision != binding.revision:
                return {'status': 'stale_definition'}
            # revision covers removal/visibility/schema/implementation changes.
            tool = binding.tool
            if (type(arguments) is not dict or set(arguments) != set(tool.required) or
                    any(type(v) is not str for v in arguments.values())):
                return {'status': 'invalid_arguments'}
            event = dict(provider=binding.provider, generation=binding.generation,
                         revision=binding.revision, tool=tool.name,
                         implementation=tool.implementation)
            self._calls.append(event)
            return dict(status='ok', implementation=tool.implementation,
                        value=[arguments[k] for k in tool.required])

    def calls(self):
        with self._lock:
            return [dict(c) for c in self._calls]


def demo():
    context = Context('synthetic-tenant', 'reader', 'run-1')
    catalog = Catalog()
    catalog.policy(context, {('docs', 'lookup')})
    catalog.connect('docs', [Tool('lookup', ('doc_id',), 'v1')])
    old, menu1 = catalog.sample(context, 1)
    catalog.disconnect('docs', 1)
    offline = catalog.dispatch(context, 1, old, 'docs__lookup', {'doc_id': 'D7'})
    catalog.connect('docs', [Tool('lookup', ('slug',), 'v2')])
    stale = catalog.dispatch(context, 1, old, 'docs__lookup', {'doc_id': 'D7'})
    wrong_repair = catalog.dispatch(context, 1, old, 'docs__lookup', {'slug': 'intro'})
    before = catalog.calls()
    new, menu2 = catalog.sample(context, 2)
    invalid = catalog.dispatch(context, 2, new, 'docs__lookup', {'doc_id': 'D7'})
    valid = catalog.dispatch(context, 2, new, 'docs__lookup', {'slug': 'intro'})
    return dict(menu1=menu1, menu2=menu2, offline=offline, stale=stale,
                wrong_repair=wrong_repair, invocations_before_resample=len(before),
                invalid=invalid, valid=valid, calls=catalog.calls())


if __name__ == '__main__':
    print(json.dumps(demo(), ensure_ascii=False, indent=2))
```

</details>

### 4. 验证什么，仍不能证明什么

2026-09-16 在 CPython 3.11.8 上运行上述 fixture 及原创 `test_catalog.py`：**16 个测试通过**。测试覆盖新增注册只影响下一步、离线目录保留但不广告、隐藏/延迟工具猜名拒绝、发现只影响下一步、当前撤权与 policy ABA、跨 tenant/principal/run 和 step 拒绝、菜单被修改不改变分发 schema、相同 schema 重连仍换世代、同连接目录修订、移除与隐藏、重复/非法定义整批拒绝、迟到断线与刷新响应、同名跨 provider 和参数边界。

还验证了断线/重连/旧调用的 **6 种事件排列**，以及分发与重连、分发与撤权各 **20 次双线程竞态**。全部 **80 个线程已 join 并检查退出**；竞态只允许旧 v1 执行或明确拒绝，旧快照没有到达 v2。线程调度次序不固定，不用某种次序出现的次数估计生产概率。demo 输出的关键字段为：`invocations_before_resample=0`，最终 `calls` 只有 `generation=2, revision=1, implementation=v2` 一条。

这是本地受控模型的运行记录，没有启动 MCP server/client、读取凭据或更改业务权限；锁只覆盖有界的即时 mock。实验没有验证真实 SDK、远端并发授权、服务端分页快照、生产性能/持久性或 exactly-once。它也不提供快照 TTL、持久审计、故障恢复与 lease 回收实现；生产系统必须给旧快照数量和生命周期设置上限。课程中具体运行时的隐藏语义和连接行为不能由此实验倒推。

## 延伸 / 追问

**追问：下一次采样才改变菜单，会不会阻止紧急撤权？**

不会。模型已经收到的菜单无法收回，但分发入口仍使用当前授权决定是否准入。拒绝时告诉模型需要新的上下文；已经发出的远端操作另行处理取消或补偿，不能宣称快照失效等于回滚。

**追问：schema 的 hash 完全一样，旧调用是否就可以走重连后的连接？**

不能据此断言。hash 只比较被纳入计算的内容，不证明连接属于同一服务身份、实现语义没变或权限仍相同。即使 schema 相同，本例也增加 generation；要跨世代复用必须有明确的兼容性和授权契约。

**追问：`tools/list_changed` 晚到，或者列举了多页以后服务端又变了呢？**

通知不是锁，客户端完整发布只能避免自己暴露半批数据。若要求调用严格匹配服务端版本，就需要版本化列表/调用或固定 endpoint；普通 MCP 字段不足以提供这种证明。无法取得一致视图时应拒绝或重试发现，并限制预算。

**追问：发现了 deferred 工具后能否立刻调用，hidden 能否被内部调用？**

这取决于运行时契约。本例在下一步激活 deferred，hidden 不进入模型分发。另一个运行时可以给发现结果发受限 capability，或给内部调用单独授权；必须写明 capability 绑定的身份、版本、有效期及执行检查，不能仅凭一个可猜的名字通行。

## 常见误区

- **“注册成功就已对模型可见。”** 注册、广告、执行资格分开；断线时也可能保留目录但拒绝执行。
- **“隐藏了名称，提示模型别调用就安全了。”** 模型会猜名，也可能通过其他代理入口访问；必须在实际网关执行授权，覆盖间接路径。
- **“同名或同 schema hash 就是同一个工具。”** 名字和 hash 不证明 generation、实现语义或身份相同，不能把旧调用自动转给新实现。
- **“一次采样冻结目录，就冻结了整个世界。”** 快照不冻结远端状态、权限或副作用；它用于约束解释与分发，仍可能得到拒绝或未知结果。

## 参考

以下来源核对于 2026-09-16，固定到指定版本。课程作为选题线索；本文机制、表格与 fixture 独立编写，不复制课件正文、代码或图片，也不把课程中的源码判断当成已复核的上游保证。

- 洛小山《AI 产品从入门到精通》，learn-ai 固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/codex-10.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-10.html)（采样边界与广告）、[slides/dsh-21.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-21.html)（动态工具与世代）、[slides/12-7.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/12-7.html)（preset 注册与公开枚举）。[LICENSE](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/LICENSE) 为 AGPL-3.0；这里只链接和独立讨论。
- Model Context Protocol，协议 **2025-06-18**，固定 commit `cd0623765886c8cc282e3e5e1a03ab7469055fab`：[server/tools.mdx](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/docs/specification/2025-06-18/server/tools.mdx) 的 Capabilities、Listing Tools、Calling Tools、List Changed Notification、Security Considerations；支持本题有关枚举、通知、输入校验及 access control 的协议边界。[schema.ts](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/schema/2025-06-18/schema.ts#L795-L867) 的 `ListToolsRequest`、`CallToolRequest`、`ToolListChangedNotification` 给出实际字段，未定义本题的 snapshot/generation/visibility。
- MCP 同一 commit 的 [LICENSE](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/cd0623765886c8cc282e3e5e1a03ab7469055fab/LICENSE) 明示许可迁移：新代码与规范贡献采用 Apache-2.0，非规范文档采用 CC-BY-4.0，未同意重许可的原贡献仍按原 MIT 条款；不能笼统标为全库 MIT。本文只引用接口事实，没有搬入其实现。
- CPython **v3.11.8**：[Doc/library/threading.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/threading.rst) 的 Lock Objects 与 Thread.join，支持本地互斥和线程回收的解释；锁不保证等待者公平顺序。[LICENSE](https://github.com/python/cpython/blob/v3.11.8/LICENSE) 包含 PSF 许可及历史许可声明。该文档不提供远端原子分发保证。
