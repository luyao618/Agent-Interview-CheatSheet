---
id: engineering-0030
title: 如何让 Agent 使用外部服务却拿不到原始凭据，并在轮换与网络重定向时维持边界？
category: engineering
tags: [credentials, proxy, egress, rotation, redirection, redaction]
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

如何让 Agent 使用外部服务却拿不到原始凭据，并在轮换与网络重定向时维持边界？请推演旧环境变量遮蔽新凭据、跨域重定向两个案例，说明凭据引用、注入时机、目标限制和日志脱敏。

## 答案 · GPT-6

让 Agent 提交受限操作和**凭据引用**，由独立可信网关验证授权及目的地，在真正发出请求前解析引用、注入认证，再把受控结果交回 Agent。原始凭据应只存在于受保护的存储与代理执行环境中，不能同时暴露给 Agent 的提示词、子进程环境、可读文件或日志。

这需要真实的进程/权限隔离和出站约束配合。单纯“把 key 放在 prompt 外”不够：Agent 运行的代码可能读取继承环境、凭据文件、异常堆栈或调试日志；它还可能绕开代理直连，或诱导代理把请求转发到错误目标。身份选择见 [agent-0051](agent-0051-agent-virtual-identity-vs-user-identity.md)，一般沙箱边界见 [engineering-0011](engineering-0011-agent-code-execution-sandbox-tradeoff.md)，本题聚焦原始凭据经过哪些通道、何时重新读取。

### 1. 引用不是值，持有引用也不自动获得权限

一次调用的主线是：**可信入口识别调用主体 → 检查主体可用的引用及操作 → 固定引用与服务路由 → 校验目标 → 解析当前凭据 → 注入认证并发送 → 处理重定向/错误 → 投影结果和审计元数据**。模型不能自己指定任意 secret store 路径、Host、认证头或出站域名；一个 `report-read` 引用应只映射到受信配置中的服务和最小权限。

引用可以是 opaque ID、环境变量名或其他解析句柄，但这些形式并不自带权限。代理还要校验“谁可借这个引用，对哪个服务、路径、方法执行什么操作”，并限制速率和业务副作用。隐藏 token 只缩小凭据泄露面，不意味着 Agent 不会滥用获准服务。

| 方案 | 适用条件与收益 | 代价及不适用场景 |
| --- | --- | --- |
| 应用层工具网关持有凭据，Agent 只提交结构化操作 | 可明确控制目标、方法、参数与返回 schema；适合少量明确的服务能力 | 要维护服务适配器和授权策略。不能把一个可访问任意 URL 的通用转发口当成受限工具 |
| 受管出站代理为兼容客户端注入凭据 | 希望复用已有 SDK/工具，且可约束客户端网络通道、识别服务与认证位置 | 更复杂：TLS、认证头替换、代理绕行、客户端自带凭据源都要处理。普通 HTTPS CONNECT 隧道看不到加密后的请求头；不能只设置代理环境变量就声称已完成注入与隔离 |

本文实现第一种方案的原创教学模型。真实部署中，secret store 的访问权限属于代理身份，Agent 不应能读取代理内存或调试接口；网络层还应限制直连和其他出口。若采用 TLS 终止/受管中间代理，需要明确证书信任、上游验证和适用客户端，不能把这些前提藏在“加个代理”三个字里。

### 2. 旧环境遮蔽新凭据：来源优先级和读取时机都要查

先定义权威来源及回退规则，再讨论轮换。下面是2026-09-16实际运行原创 fixture 的结果；所有值都是明确虚构的 `FICTIONAL-ONLY-NOT-A-SECRET-*` 标记，环境只是 Python 字典，未读取真实 `os.environ`、vault 或凭据文件。

| 状态/输入 | 解析动作 | 结果与判断 |
| --- | --- | --- |
| 初始 store 为版本1；合成环境 `FICTIONAL_API_TOKEN` 持有 OLD | 环境副本留在旧配置中 | 旧值不会因为另一处写入而自动改变 |
| 管理方将 store 更新为版本2 NEW | 错误迁移逻辑仍执行“环境有值就用环境，否则读 store” | `old_environment_wins=true`，新 store 被遮蔽；在高优先级来源仍存在时，反复更新低优先级来源没有帮助 |
| 新合同规定 store 为权威来源，Agent 只拿 `report-read` | 代理解析 store；Agent 环境按允许字段重建，只保留合成 LANG | 本次出站选择版本2；Agent view 不含 OLD/NEW，也不包含认证头。store 失败时不偷偷回退到旧环境 |
| 另一个解析器在教学时间 t=0 缓存版本2，TTL=5秒；store 随后变为版本3 | t=1继续命中缓存，t=5到达过期边界后读取 store | 实测版本序列 `[2,2,3]`；配置已更新，不代表当前请求使用的新值已更新 |

如果产品明确允许“环境优先”，旧值继续生效可能是合同本身，而非实现 bug。应展示“已配置、当前来源、版本/更新时间、是否可在此处写入”等非敏感诊断；当写入不能影响有效值时应说明原因。迁移要调整实际来源或重建受控环境，不能静默改变用户已选择的优先级。

读取时机有取舍。每次请求现取更容易观察轮换，但增加存储访问成本，存储不可用也可能阻断调用；TTL 缓存可降低开销、提高短时可用性，却增加旧值存活窗口。紧急吊销通常还需服务端撤销、缓存主动失效或短期凭据，不能只等待配置刷新。缓存有效期间甚至可能继续拿出已从 store 删除的旧值；本例专门验证了这一事实，未把它说成即时撤权。

本文默认 TTL=0，在**每个即将发送的 HTTP 请求，即每一跳**读取凭据；不是整个重定向链只读一次。已经构造或发出的请求保留当时的凭据版本，轮换不会修改在途字节。同源下一跳可读到新版本；需要整个业务操作固定版本的产品可以采用另一合同，但必须定义旧版本存活窗口、失败处理及目标绑定。进程缓存、SDK 缓存、代理缓存、存储读取一致性都可能影响实际生效时刻。

### 3. 跨域重定向：下一跳是新的出站判定

本例只允许 GET 到 `https://reports.example.test:443`，路径限定为四个合成报告端点；域名仅作字符串标签，不做 DNS 查询。引用 `report-read` 绑定该路由，调用主体必须有对应 grant。代理拒绝客户端自带 Authorization、Cookie、Host、Proxy-Authorization、自定义密钥头及重复 header；每跳从允许字段重新构造请求头，认证值由代理注入。

| 重定向阶段 | 必须确认的事情 | 本例实测结果 |
| --- | --- | --- |
| 首次请求 `/v1/report` | 主体有 grant；引用匹配路由；HTTPS、主机、有效端口和路径都符合约束 | 读取版本2并向批准的服务记录1次 mock 发送 |
| 返回302，Location为 `https://collect.example.test/drop` | 解析相对/绝对 Location，重新核对下一跳目标；不能默认沿用上一跳授权与 headers | 返回 `redirect_blocked`；只有 reports 主机出现在发送记录中，没有第二次读凭据或发送 |
| 对照：Location为同源 `/v1/page2` | 再检查当前 grant 与路由，重新读取凭据、构造 headers | 允许下一跳；若期间轮换，本例记录的凭据版本从1变为2 |
| 授权撤销、路由改变、环路或超过预算 | 无论此前是否获准，都要停止继续使用旧条件 | 分别返回 `reference_denied`、`route_changed`、`redirect_loop` 或 `redirect_limit`；默认最多跟随2次，最多发送3个 mock 请求 |

第一跳已经把凭据交给获准目标，后来阻止跨域不能撤销这件事。若获准服务自身恶意、凭据 scope 过大或返回值反射秘密，还需要服务信任、最小权限和输出限制。

“SDK 会去掉 Authorization”也不等于任意跨域跟随都安全：自定义密钥头、Cookie、URL 查询串或请求 body 仍可能敏感；307/308等状态还涉及保留方法/内容。本文只模拟无 body 的 GET，遇到跨 origin、HTTP 降级、非允许端口、userinfo、query/fragment、编码歧义或未知路径一律拒绝，不把此规则推广为所有 HTTP 客户端的默认行为。

真正出站还需约束 DNS 解析、目标 IP、TLS 对端、代理绕行与实际网络连接。按字符串核对 hostname 不证明可以抵御 DNS rebinding、内网路由变化或 TLS 校验失效；也不能用域名后缀字符串相似来授予凭据。

### 4. 日志只收必要元数据，示例不冒充隔离设施

记录请求关联、服务、凭据版本、成功/拒绝原因和耗时等受控元数据，通常比记录完整请求再做替换更可靠。不要记录 token、完整 headers、带敏感 query 的 URL、合成/真实环境全量、原始异常文本或任意 response body。版本号和引用本身也应按业务敏感度处理；它们不是来源签名。

本例模型可见结果只返回固定状态和经过类型/范围检查的 count，丢弃服务返回的其他字段；日志只含固定事件、服务名及凭据版本。测试故意把虚构凭据放入错误文本、响应 debug 字段、URL 和客户端 headers，确认没有进入公开结果/日志。这样的限定 schema 不是通用自由文本 DLP，更不是对编码、拆分或其他隐蔽通道的完整防护。

<details>
<summary>可运行原创 fixture：全部凭据与网络均为内存 mock</summary>

保存为 `credential_fixture.py`，用 Python3.11.8 执行 `python3 credential_fixture.py`。仅依赖标准库；`urllib.parse` 只解析字符串，不发请求。Store、Resolver、Proxy 与 MockTransport 全在同一测试进程中；为了验证注入，MockTransport私有记录含虚构标记，这不是生产可向 Agent 开放的日志。示例不证明物理进程隔离、内存擦除或真实身份认证。

```python
# file: credential_fixture.py
"""Original synthetic credential boundary model: no environment/secret/network I/O."""
from copy import deepcopy
from dataclasses import dataclass,field
import json,math
from urllib.parse import urljoin,urlsplit,urlunsplit

OLD='FICTIONAL-ONLY-NOT-A-SECRET-OLD'
NEW='FICTIONAL-ONLY-NOT-A-SECRET-NEW'
THIRD='FICTIONAL-ONLY-NOT-A-SECRET-THIRD'
REF='report-read'
ORIGIN='https://reports.example.test'


class Denied(ValueError):pass
class Unavailable(RuntimeError):pass


@dataclass(frozen=True)
class Secret:
    version: int
    token: str=field(repr=False)


class Store:
    def __init__(self):self.entries={REF:Secret(1,OLD)};self.reads=[];self.available=True
    def read(self,ref):
        self.reads.append(ref)
        if not self.available or ref not in self.entries:raise Unavailable('credential unavailable')
        return self.entries[ref]
    def rotate(self,ref,token):
        if token not in (OLD,NEW,THIRD):raise ValueError('only declared fictional markers')
        self.entries[ref]=Secret(self.entries[ref].version+1,token)


class Clock:
    def __init__(self):self.now=0
    def advance(self,seconds):
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<0:
            raise ValueError('invalid synthetic time')
        self.now+=seconds


class Resolver:
    def __init__(self,store,clock,ttl=0):
        if type(ttl) not in (int,float) or not math.isfinite(ttl) or not 0<=ttl<=60:
            raise ValueError('invalid teaching TTL')
        self.store=store;self.clock=clock;self.ttl=ttl;self.cache={}
    def read(self,ref):
        cached=self.cache.get(ref)
        if cached and self.clock.now<cached[0]:return cached[1]
        value=self.store.read(ref)  # no legacy environment fallback on failure
        if self.ttl:self.cache[ref]=(self.clock.now+self.ttl,value)
        return value
    def invalidate(self,ref):self.cache.pop(ref,None)


def legacy_resolve(env,store,ref):
    # Deliberately wrong for a migration to a store-authoritative policy.
    return env.get('FICTIONAL_API_TOKEN') or store.read(ref).token


def child_environment(env):
    # Explicit projection; never os.environ, subprocess inheritance or secret discovery.
    language=env.get('LANG')
    return {'LANG':language if language in ('C','C.UTF-8') else 'C'}


@dataclass(frozen=True)
class Route:
    ref: str=REF
    host: str='reports.example.test'
    paths: tuple=('/v1/report','/v1/page2','/v1/page3','/v1/page4')


@dataclass(frozen=True)
class Response:
    status: int
    location: object=None
    payload: object=None


class MockTransport:
    def __init__(self,responses,on_send=None):
        self.responses=list(responses);self.on_send=on_send;self.recorded=[]
    def send(self,url,headers):
        # Private test observation includes fictional markers; never a model/UI/log channel.
        self.recorded.append(dict(url=url,headers=deepcopy(headers)))
        if self.on_send:self.on_send(len(self.recorded))
        if not self.responses:raise RuntimeError('mock response exhausted')
        response=self.responses.pop(0)
        if isinstance(response,Exception):raise response
        return response


def checked_url(url,route):
    if (type(url) is not str or not url or len(url)>2048 or
            any(ord(c)<33 or ord(c)>126 for c in url) or '\\' in url):
        raise Denied('target_blocked')
    try:
        p=urlsplit(url)
        if (p.scheme!='https' or p.username is not None or p.password is not None or
                p.hostname!=route.host or p.port not in (None,443) or
                p.netloc.lower() not in (route.host,route.host+':443') or
                p.path not in route.paths or p.query or p.fragment):raise Denied('target_blocked')
    except ValueError:raise Denied('target_blocked') from None
    return urlunsplit(('https',route.host,p.path,'',''))


def checked_client_headers(headers):
    if headers is None:return
    if type(headers) is not dict:raise Denied('headers_blocked')
    names=set()
    for name,value in headers.items():
        if type(name) is not str:raise Denied('headers_blocked')
        key=name.lower()
        if key in names or key!='accept' or value!='application/json':raise Denied('headers_blocked')
        names.add(key)


class Proxy:
    def __init__(self,resolver,transport,max_redirects=2):
        if type(max_redirects) is not int or not 0<=max_redirects<=3:raise ValueError('invalid redirect budget')
        self.resolver=resolver;self.transport=transport;self.route=Route();self.max_redirects=max_redirects
        self.grants={('agent-demo',REF)};self.logs=[]
    def event(self,status,version=None):
        # Allowlisted metadata only: no raw URL/header/body/environment/exception text.
        row=dict(event=status,service='reports')
        if version is not None:row['credential_version']=version
        self.logs.append(row)
    def result(self,status,count=None):
        self.event(status)
        result={'status':status}
        if count is not None:result['count']=count
        return result
    def request(self,actor,ref,url,client_headers=None):
        if type(actor) is not str or type(ref) is not str:return self.result('reference_denied')
        try:checked_client_headers(client_headers)
        except Denied as exc:return self.result(str(exc))
        seen=set();expected_route=self.route
        for hop in range(self.max_redirects+1):
            route=self.route  # immutable route/ref snapshot for this hop
            if route!=expected_route:return self.result('route_changed')
            if (actor,ref) not in self.grants or ref!=route.ref:return self.result('reference_denied')
            try:current=checked_url(url,route)
            except Denied:return self.result('redirect_blocked' if hop else 'target_blocked')
            if current in seen:return self.result('redirect_loop')
            seen.add(current)
            try:secret=self.resolver.read(route.ref)
            except Exception:return self.result('credential_unavailable')
            if (not isinstance(secret,Secret) or type(secret.version) is not int or secret.version<1 or
                    secret.token not in (OLD,NEW,THIRD)):return self.result('credential_unavailable')
            headers={'Accept':'application/json','Authorization':'Bearer '+secret.token}
            self.event('sending',secret.version)
            try:response=self.transport.send(current,headers)
            except Exception:return self.result('transport_error')
            if not isinstance(response,Response) or type(response.status) is not int:
                return self.result('invalid_response')
            if response.status==401:
                self.resolver.invalidate(route.ref)
                return self.result('auth_failed')  # no automatic retry or remote rollback
            if response.status in (301,302,303,307,308):
                if hop==self.max_redirects:return self.result('redirect_limit')
                if type(response.location) is not str:return self.result('redirect_invalid')
                try:
                    # Validate Location before urljoin can normalize away whitespace/control.
                    location=response.location
                    if not location or any(ord(c)<33 or ord(c)>126 for c in location) or '\\' in location:
                        return self.result('redirect_invalid')
                    url=urljoin(current,location)
                except ValueError:return self.result('redirect_invalid')
                continue  # next hop rechecks grant/target, rereads, and builds fresh headers
            if response.status!=200:return self.result('upstream_error')
            data=response.payload
            if (type(data) is not dict or type(data.get('count')) is not int or
                    not 0<=data['count']<=1200):return self.result('invalid_response')
            return self.result('ok',data['count'])  # discard all other fields, not a free-text scrubber
        raise AssertionError('unreachable')


def demo():
    env={'LANG':'C.UTF-8','FICTIONAL_API_TOKEN':OLD,'DEBUG':'enabled'}
    store=Store();store.rotate(REF,NEW)
    shadowed=legacy_resolve(env,store,REF)==OLD
    clock=Clock();per_request=Resolver(store,clock)
    transport=MockTransport([Response(302,'https://collect.example.test/drop')])
    proxy=Proxy(per_request,transport)
    result=proxy.request('agent-demo',REF,ORIGIN+'/v1/report')
    cached=Resolver(store,clock,ttl=5);before=cached.read(REF).version
    store.rotate(REF,THIRD);clock.advance(1);during=cached.read(REF).version
    clock.advance(4);after=cached.read(REF).version
    return dict(old_environment_wins=shadowed,agent_view={'credential_ref':REF,'environment':child_environment(env)},
                redirect_result=result,sent_hosts=[urlsplit(r['url']).hostname for r in transport.recorded],
                logs=proxy.logs,cache_versions=[before,during,after],synthetic_times=[0,1,5])


if __name__=='__main__':print(json.dumps(demo(),ensure_ascii=False,indent=2))
```

</details>

2026-09-16实测：**22 个测试通过**，其中43次检查确认公开结果、模型环境投影或日志不含三个虚构凭据标记。覆盖来源遮蔽、在途/下一跳轮换、TTL边界、缓存下的延迟撤销、401失效且不自动重试、store/transport错误、跨域/降级/authority攻击、header注入、引用授权、路由变更、重定向环路与上限、返回schema。唯一合成输入文件逐字节未变，专属临时目录已删除；没有真实 transport、SDK初始化或秘密来源访问。

401在本例中清除对应缓存并返回 `auth_failed`，下一次调用重新解析；没有自动重试，因为认证失败与业务执行是否发生、调用是否幂等仍是不同问题。日志失败持久性、跨进程轮换传播、并发撤权/发送原子性及远端 exactly-once 均不在这组实验的证明范围内。

### 5. 一手实现说明来源与缓存不能一概而论

以下是固定源码阅读，未导入或运行这些 SDK：

- **Botocore1.35.99**：`create_credential_resolver` 的常规链把 EnvProvider 放在 profile/container 等来源前；显式 profile 等配置会改变是否保留这个 provider。`CredentialResolver.load_credentials` 返回链中首个非 None 结果。因此不能假设新写入的另一来源天然优先。
- 同版本 `EnvProvider.load` 在有 expiry 时返回 RefreshableCredentials，否则返回普通 Credentials；`Session.get_credentials` 缓存 credential 对象。缓存对象可能自身支持刷新，不能据此声称“所有 Botocore 凭据都永久不轮换”。本例的5秒TTL是原创数字，未冒充SDK配置或生效保证。
- **Requests2.32.3**：`should_strip_auth` 对 hostname 改变返回 true；`rebuild_auth` 条件移除 Authorization，但 `trust_env` 启用时还可能从新目标的 `.netrc` 重新取得认证。scheme/port规则也有例外。本文未读取任何 `.netrc`，且采用更严格的拒绝跨 origin 教学策略；不把 Requests 对一个头的处理当成完整凭据代理。

课程的 Codex/DSH等实现是学习线索，未在本题固定一手调用链中核验的产品保证不采用。尤其“配置只存引用”“环境已清理”“网络只能经过代理”“日志没有泄露”是四个需要分别验证的条件。

## 追问

**追问：密钥轮换后新请求仍用旧值，先查什么？**

先查实际命中的来源及优先级，再查 SDK/进程/代理的读取时机和缓存；用非敏感版本元数据确认本次请求使用的版本。不要把“设置保存成功”当作读取链已改变，也不要把真实 key 打到日志排查。

**追问：Agent只持有凭据引用，还需要审批和授权吗？**

需要。引用只定位凭据，不能证明调用主体有权使用。代理应限制主体、服务、路径、方法和业务scope，并支持撤销；否则 Agent 虽拿不到key，仍可能借代理执行越权操作。

**追问：重定向到同公司另一个域名，可以沿用认证吗？**

不能靠品牌或域名相似判断。需要单独登记目标和凭据适用范围，并明确方法/body/headers的迁移规则；没有明确授权就拒绝或交回调用方处理。原目标获准不意味着Location也获准。

**追问：把日志中的完整key替换成星号就够了吗？**

不够，秘密可能被编码、拆分或藏在URL、异常与返回body中。优先减少采集、采用结构化允许字段和访问控制，再按需要补充脱敏检测；本题的字面标记检查只覆盖声明的合成通道。

## 常见误区

- **“不把key放进提示词就不会泄露。”** 环境、文件、子进程、日志和服务回显仍是独立通道。
- **“配置里只有引用，所以Agent一定拿不到值。”** 还要核对谁能resolve、谁能访问存储，以及执行环境是否继承原始凭据。
- **“缓存只影响性能，不影响轮换。”** 它会延长旧值存活；在途请求和服务端撤销也有各自边界。
- **“第一次目标合法，后续重定向可以自动沿用。”** 每一跳都需要重新决定目标和凭据是否适用。
- **“代理已经返回成功，就证明身份、OS隔离和所有日志都安全。”** 数据流合同与真实部署控制、持久性、认证证据必须分开验证。

## 参考

来源核对于2026-09-16；固定版本用于可复查说明，不声称是所有产品当前默认值。正文与fixture独立编写，未搬运AGPL课件内容。

- 洛小山《AI 产品从入门到精通》，learn-ai固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/codex-20.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-20.html)（网络与凭据代理）、[slides/dsh-24.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-24.html)（来源与轮换）、[slides/10-16.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/10-16.html)（凭据与执行边界）；[AGPL-3.0 LICENSE](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/LICENSE)。
- Requests / PSF，**v2.32.3**，tag对应固定 `0e322af87745eff34caffe4df68456ebc20d9068`：[sessions.py](https://github.com/psf/requests/blob/0e322af87745eff34caffe4df68456ebc20d9068/src/requests/sessions.py)，127–157行的 `should_strip_auth`，282–300行的 `rebuild_auth`；[Apache-2.0 LICENSE](https://github.com/psf/requests/blob/0e322af87745eff34caffe4df68456ebc20d9068/LICENSE)。
- AWS / Botocore，**1.35.99**，tag对应固定 `26a4f341d5496e12696692904d1dc83b939b71b5`：[credentials.py](https://github.com/boto/botocore/blob/26a4f341d5496e12696692904d1dc83b939b71b5/botocore/credentials.py) 的resolver构造（94–158）、EnvProvider（1089起）和凭据链领取（2066–2076）；[session.py](https://github.com/boto/botocore/blob/26a4f341d5496e12696692904d1dc83b939b71b5/botocore/session.py#L503-L516) 的 `get_credentials`；[Apache-2.0 LICENSE](https://github.com/boto/botocore/blob/26a4f341d5496e12696692904d1dc83b939b71b5/LICENSE.txt)。
- IETF，**RFC9110（2022）**，[HTTP Semantics §15.4 Redirection](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.4)：跟随重定向时解析Location、更新目标相关字段、考虑认证/Cookie等字段的安全含义，并检测环路。本文更严格的同origin规则和重定向预算是教学策略，不是RFC统一要求。
