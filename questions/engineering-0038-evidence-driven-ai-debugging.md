---
id: engineering-0038
title: AI 协助排查故障时，如何从猜测修复转成可证伪假设，并避免吞错掩盖问题？
category: engineering
tags: [ai-debugging, hypothesis, observability, exception, counterfactual]
difficulty: medium
role: engineer
contributor: CX-Dev
source: 洛小山《AI 产品从入门到精通》learn-ai LA-052；Google SRE；CPython v3.11.8；OWASP Logging Cheat Sheet
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

AI 协助排查故障时，如何从猜测修复转成可证伪假设，并避免吞错掩盖问题？假设查询返回“成功但结果为空”，实际却是超时被catch转换为空数组，应怎样设计观测与最小反事实实验？

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 回答日期：2026-09-16

**先把猜测写成能被观察推翻的预测，再用最小实验区分原因；修复后重放原始失败，检查失败语义和正常行为是否都正确。** AI可以整理候选原因、定位可疑路径、编写复现和反例，但不能把“看起来像网络问题”当根因，也不能用一次成功替代验证。

本例要分开三件事：用户看到空结果是**症状**；捕获超时后返回正常空数组，是可复现的**错误转换缺陷**；真实服务为什么超时，可能还涉及截止时间、连接、排队或服务负载，属于需要另外验证的问题。修复错误传播，并不意味着已经消除了底层超时原因。

### 把假设写成预测与反证

先冻结最小复现：代码/依赖版本、必要配置、输入的允许使用部分、预期契约、实际输出及触发频率。敏感原始输入不得为了方便直接复制进日志或复现包；优先构造保留故障条件的合成样本。先利用已有错误栈、指标、测试或断点，再决定在哪个分界点补观测，不要求所有问题都先加大量日志。

| 假设 | 预期观察 | 什么会推翻它 |
| --- | --- | --- |
| H1：这次确实没有匹配数据 | 同一request/attempt中，client正常返回合法列表且count=0，adapter与API都正常返回0 | client实际上抛出超时，根本没有正常列表返回 |
| H2：超时被adapter吞成空成功 | transport记录timeout，随后adapter走fallback返回0，API却标为ok | 强制相同超时仍没有经过该catch，或只修此转换后API仍返回ok空结果，则应继续查其他边界 |
| H3：后处理丢掉了正常结果 | client返回count>0，数量在某个后续边界降为0 | 在本次受控复现中client从未返回数据，而是直接抛错 |

这里的反证只针对所观察的请求与实验条件。不同request混在一起、从开发机访问而故障发生在服务实例上、配置或缓存同时改变，都可能产生混淆。Google SRE《Effective Troubleshooting》以假设—检验描述排障，也提醒受控干预与混淆因素；实际要记录每轮改变了什么、保持了什么、观察到什么，而不是把相关性自动升级为因果关系。

### 相关ID与安全观测点

为逻辑请求使用可信入口生成的request_id，为每次实际尝试使用attempt_id，贯穿调用、适配、解码和对外边界。它们用于关联，不能承担授权，也不应嵌入query、token或用户秘密。模型转述的“上游成功”不能代替对应版本、位置和ID的原始事件。

| 位置 | 本例记录的白名单信息 | 可区分的情况 |
| --- | --- | --- |
| transport调用前后 | request_id、attempt_id、组件/事件、受控错误类别、list/other形状、成功列表数量、本地elapsed_ms | 正常空列表、正常非空、抛出超时与收到错误结构 |
| adapter异常/返回边界 | raise/fallback/return、错误类别、仅成功或旧fallback时的count | 错误是否被转换成了正常数据 |
| API边界 | 业务outcome及相关ID；成功时count，失败时code | return这个动作不等于业务成功；错误响应与真实空成功分别计数 |
| 实验记录 | 被验证版本、假设、合成场景、固定断言、退出码与结果 | 失败复现、干预效果与验证范围 |

**加日志不能记录密钥或全量敏感输入。** 也不要默认记录完整响应、SQL参数、请求headers、`str(exc)`或包含原始错误message的traceback。OWASP Logging Cheat Sheet固定`8aaf426de610ea603c21cf6a75222a6b7a30f820`说明interaction identifier、敏感数据排除与防日志注入；本例因此采用字段和枚举值白名单，而不是先把全部内容收集起来再寄望后处理。

数量、时间和相关ID在某些业务里也可能敏感，生产白名单仍需按数据规则批准，配访问控制与保留期。格式合法不证明来源可信；对输入做hash也不自动完成脱敏，低熵数据仍可能被枚举。本例没有对真实用户输入生成或记录指纹。

### 原创复现与最小反事实

原创同步MockClient有nonempty、empty、timeout等有限模式：nonempty返回`['demo-item']`，empty返回`[]`，timeout直接抛内置TimeoutError。请求含一个专为检查日志泄漏而设的非真实隐私标记；观测报告中不保留该值，也不保留异常原文。没有访问用户日志、真实服务或凭据。

旧adapter的关键行为是`except Exception: return []`；API把正常返回值包装为`status=ok`。先运行固定契约测试，再编写修复版，真实得到超时断言失败：预期error，实际ok。随后只替换adapter，保持共享client、输入、观测代码和同一份三项测试文件不变；这比同时调大超时、换依赖、加重试再看“好了没有”更容易解释干预效果。

**2026-09-16实跑结果**如下。表中是本地合成调用，不是生产事故或真实网络实验。

| client模式 | 旧adapter/API结果 | 修复后结果 | 判断 |
| --- | --- | --- | --- |
| nonempty | ok，`['demo-item']` | ok，`['demo-item']` | 正常非空行为保留 |
| empty | ok，`[]` | ok，`[]` | 真实空结果仍是成功，不能一律改成错误 |
| timeout | ok，`[]` | error，code=timeout，无items字段 | 原始缺陷被固定断言检出并修复 |
| connection | ok，`[]` | error，code=connection | 连接失败不伪装成零条数据 |
| payload | ok，`[]` | error，code=payload | 非法响应结构与合法空列表分开 |
| bug | ok，`[]` | RuntimeError继续传播 | 不把未预期的编程错误当业务空结果 |
| cancel | CancelledError传播 | CancelledError传播 | 保持取消语义；不声称旧版本吞掉了它 |

同一request/attempt的关键事件，旧版是`transport.raise(timeout) → adapter.fallback(timeout,count=0) → api.return(ok,count=0)`；新版是`transport.raise(timeout) → adapter.raise(timeout) → api.return(timeout)`，API返回显式失败对象。生产排查中应按相关ID核对整个链条，不能把别次请求的正常返回接到这次超时后面。

原始probe为 **3 tests、1 failure、0 errors、exit1**；修复版使用同一测试文件，**3 tests通过、exit0**。三项同时约束超时为失败、真实空为成功、非空为成功，防止用“所有请求都报错”的假修复过关。原始失败stdout/stderr、共享文件hash和后续红绿记录均保留，没有修改断言去迁就旧行为。

### 明确异常分类、传播与对外契约

CPython v3.11.8教程建议尽量具体地处理预期异常，并让未预期异常继续传播；`raise ... from exc`可以保留异常因果链。以下是附件中实际执行的修复函数，依赖共享模块里的SearchFailure、PayloadError与decode；它不是任意SDK通用的异常映射表。

```python
def search(client, request, trace):
    trace.emit('adapter','start')
    try:
        items=decode(client.fetch(request,trace))
    except TimeoutError as exc:
        trace.emit('adapter','raise',kind='timeout')
        raise SearchFailure('timeout') from exc
    except ConnectionError as exc:
        trace.emit('adapter','raise',kind='connection')
        raise SearchFailure('connection') from exc
    except PayloadError as exc:
        trace.emit('adapter','raise',kind='payload')
        raise SearchFailure('payload') from exc
    except CancelledError:
        trace.emit('adapter','cancel',kind='cancelled')
        raise
    except Exception:
        trace.emit('adapter','raise',kind='internal')
        raise
    trace.emit('adapter','return',kind='ok',count=len(items))
    return items
```

API边界只将已分类的SearchFailure转换成带code/request_id的失败响应，不附正常items；取消和未知编程错误继续传播。**在合适边界转换成显式错误响应是正常处理，转换成正常空数据才丢失了本例的失败语义。** 真实HTTP状态、业务outcome、日志与监控也应保持一致，本文未实现或验证真实HTTP服务。

因果链保留在内存中供受控诊断，不能因此默认打印完整异常。Python的默认traceback会显示原始异常细节，生产logger还需检查异常格式器和落盘路径；本例公开响应与观测报告均不序列化原message或cause。具体SDK可能定义不同异常类，应按固定版本查清来源和边界，不能假定所有超时都等于内置TimeoutError。

CPython v3.11.8的`Lib/asyncio/exceptions.py:10`中CancelledError继承BaseException，所以旧`except Exception`本来就不捕获它。示例的取消仅同步抛出这个标记，没有创建或取消异步任务；没有验证真实deadline、合作式清理或硬时限。elapsed_ms测的是本地实验经过时间，不证明某个网络等待预算真的耗尽。

### 一次恢复之后还要验证什么

再固定同一输入，手动重放“timeout—nonempty—timeout”，保持旧代码不变：旧版输出`ok空—ok非空—ok空`；新版输出`error—ok非空—error`。中间一次成功只表示那次条件允许成功，不能排除错误转换仍在。**一次恢复不证明根因已修复**；重启、缓存命中或延长预算可能暂时改变触发条件。

本例确认的是吞错语义修复：重复强制超时时仍报失败，正常空与非空没有回归。真实系统还应分别调查超时产生的位置与预算、配置/版本差异、依赖状态及重试行为，给每个假设设计可区分的检查。超时也不证明远端没有完成操作；若涉及副作用，重试前要核查幂等、结果查询和总预算。此fixture每次只调用一次mock，没有自动重试或业务副作用。

28项回归验证异常分类、cause保留、取消/未知错误传播、相关ID、同请求不同attempt、隐私标记不入观测、日志键和值校验、输入不变与临时目录清理。它们只证明这个有限同步示例；没有真实SDK、网络、日志后端故障、生产脱敏完整性或权限隔离验证，也未做题库页面图像布局渲染。教学故障不冒充生产事故，修复了空成功契约不冒充解决了真实服务的超时原因。

### 两种合理的诊断路径

- **先用只读观测与已有复现缩小范围**：适合不能主动干预、风险高或问题偶发的环境。改动少，但可能受采样、缺失事件与混淆因素限制；不能仅凭若干相邻日志断定因果。
- **在隔离环境做最小反事实与失败注入**：适合已有可控边界和明确契约的情况。可以反复验证同一预测、保留红绿证据，但mock可能缺少真实时序/网络条件；不适合未经授权直接在业务服务上注入故障。

### 常见误区与追问

- **“加catch就更稳定。”** 只有明确处理、传播或标记降级才有意义；空成功会破坏告警、重试与用户判断。可用缓存降级时应标明数据来源、陈旧性和失败状态，不能默认为本次查询成功。
- **“日志越详细越好。”** 先选择能区分假设的最少观测点，遵守敏感数据边界，避免日志注入、过量I/O和时序扰动；不直接打印密钥、query或异常原文。
- **追问：无法稳定复现怎么办？** 记录触发条件和失败率，保留相关ID与版本/配置，比较成功和失败样本的差异；逐步增加有界观测，写清尚不能排除的假设，不补造确定根因。
- **追问：应该先加重试还是先暴露错误？** 先建立正确的失败分类与契约，再由策略层决定哪些错误可重试、预算/退避/幂等条件是什么；不能用重试掩盖未知错误或放大负载。
- **追问：修复后看不到超时了，怎样继续证伪？** 在受控环境重复强制该失败，并保留正常空/非空对照；在获授权的真实环境观察足够窗口，检查失败是否只是换了错误码、被其他层吞掉或被流量变化隐藏。

相关题：[AI应用监控](./engineering-0006-ai-app-monitoring.md)、[研发变更独立验收](./engineering-0037-ai-change-independent-review.md)。本题聚焦诊断实验与错误传播，不复写完整监控体系。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定`5a933d287dd5074cc1543cb849146f3261d47521`：[vibe-5](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-5.html)、[vibe-4](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-4.html)、[7-6c](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/7-6c.html)。仅学习线索，未搬运AGPL正文、代码或图片，也未采用“所有问题第一步都加日志”作为普遍规则。
- Chris Jones，Google《Site Reliability Engineering》2016版第12章：[Effective Troubleshooting](https://sre.google/sre-book/effective-troubleshooting/)。官方在线章节按2026-09-16抓取快照核对，区别于不可变源码版本；关注假设检验、受控干预与混淆因素。
- Python官方CPython v3.11.8：[教程异常处理与传播](https://github.com/python/cpython/blob/v3.11.8/Doc/tutorial/errors.rst#L175-L218)、[异常链](https://github.com/python/cpython/blob/v3.11.8/Doc/library/exceptions.rst#L49-L80)、[asyncio异常源码](https://github.com/python/cpython/blob/v3.11.8/Lib/asyncio/exceptions.py#L10-L14)。仅核对固定语义，未执行下载的作者源码。
- OWASP Logging Cheat Sheet，固定`8aaf426de610ea603c21cf6a75222a6b7a30f820`：[相关ID、数据排除与日志校验](https://github.com/OWASP/CheatSheetSeries/blob/8aaf426de610ea603c21cf6a75222a6b7a30f820/cheatsheets/Logging_Cheat_Sheet.md#L176-L244)。日志白名单还需按业务数据规则与实际sink审核。
