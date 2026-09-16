---
id: engineering-0040
title: 如何用 Prompt Playground 做可复现的对照实验，再判断改动是否能安全接入真实业务？
category: engineering
tags: [prompt-playground, reproducibility, regression, sampling, cache]
difficulty: medium
role: both
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

如何用 Prompt Playground 做可复现的对照实验，再判断改动是否能安全接入真实业务？同一组输入比较两版 prompt 时，应固定和记录哪些条件，如何处理缓存、采样及 mock 与真实接口之间的差异？

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**Playground 的价值是缩短实验反馈，不是替业务系统签发验收结论。** 先把一次运行定义为可核对的输入、执行条件、输出及评分记录，再只改变要研究的变量。对两版 prompt 使用相同案例与预算，保留每次结果和失败；随后区分实验装置是否正确、固定案例是否回归、真实业务是否适用。

本题讲开发期复现契约；评分器偏差见 [engineering-0013](engineering-0013-llm-as-judge-bias-calibration.md)，线上评估闭环见 [product-0006](product-0006-ai-product-iteration-loop.md)，前缀布局见 [agent-0047](agent-0047-tool-context-layout-for-prompt-cache.md)。仅保存一张“新版回答更好”的截图，无法判断差异来自 prompt、模型更新、参数、输入变化还是缓存旧结果。

### 1. 保存有效请求和执行证据，不只保存界面状态

实验前固定假设、主要指标、关键案例、重复次数及停止条件，明确哪些输入用于调参、哪些用于后续独立验证。评分规则应在看结果前确定，不能为新版临时换评分器。请求模板和变量渲染后的有效 messages 都要可追溯；界面显示 P2、实际请求仍用 P1 是实验装置缺陷。

| 契约项 | 最少应保存的内容 | 失配处理 |
| --- | --- | --- |
| prompt 与输入 | prompt ID/revision、完整模板及 hash、角色/工具/schema、渲染后的 messages；案例 ID、输入与数据集版本 | 内容与摘要不一致、角色丢失或案例变更时停止比较；不能只信版本标签 |
| 模型与接口 | provider、endpoint/adapter 版本、请求的模型标识、返回的实际版本或 fingerprint | 别名可能漂移；未暴露字段记 unknown，mock 明示 mock，不补造供应商版本 |
| 参数与采样 | 有效 temperature、top_p、输出上限、支持时的 seed、样本编号、请求/重试次数及失败 | 区分默认值与显式值；缺样本、重复回执、未知结果不能偷偷丢弃 |
| 缓存 | 完整响应缓存的模式、key 版本和命中；provider 前缀缓存的独立观测 | 回放结果不能算新增采样；没有观测不写 0，也不能把关闭本地缓存当成关闭 provider 缓存 |
| 评分与环境 | 数据划分、预期结果/rubric 与评分器版本、adapter/渲染器版本、运行日期、代码与依赖版本 | 评分器或环境变了，须分组重跑并解释，不能直接拼成同一对照 |
| 结果与链路 | 每个案例/样本的原始输出、状态、异常、来源 ID、可用的用量/时延口径，真实模型与业务集成是否执行 | 超时和写出失败不是空成功；not_run、失败和通过是不同状态 |

生产输入可能敏感，保存什么、谁能读、保留多久应按授权和数据策略确定；本题只保存原创合成输入，不要求导出用户上下文或密钥。hash 帮助核对内容，不证明来源身份，也不能防止同一个有权写者同时修改内容与摘要。

### 2. 三种“重复”不能混算

**完整响应缓存/录制回放**直接返回之前的输出，适合复查解析、评分和界面展示；它没有产生一个新的模型样本。**provider Prompt Caching**复用前缀 KV 状态，仍会生成新输出。OpenAI 官方说明明确区分两者，并说明相同请求不保证相同输出；缓存路由或命中情况应单独观测，不能用 mock 的 cache_hit 冒充服务端 cached_tokens。

**真实重复采样**是在固定条件下重新执行推理，也不自动保证独立同分布。后端版本、时间、限流、重试及并发合并都可能影响结果。应按案例成对比较，预先规定重复次数、失败处理和预算，报告分布与关键分层；共同案例或反复挑选的开发集不能冒充独立保留集。

截至 2026-09-16，OpenAI Chat Completions 的所引官方页面把 seed 标为 Deprecated，并在字段说明中保留 Beta / best effort 的确定性限定；它不保证确定性，还提示核对 system_fingerprint。不要把某一接口的 seed 字段当成所有模型通用契约，或把 temperature=0 说成逐字可复现保证。未支持的参数应明确拒绝或记不适用，不能在界面里保存后假装实际生效。

固定 promptfoo 源码也说明了为什么要区分缓存层：`src/cache.ts:859–902` 在缓存命中时反序列化旧响应；默认生成的 key 与调用方提供的 key 走不同分支。`getFetchCacheKey:557–584` 包含请求身份并处理 repeat 后缀，但这不意味着任意自定义 key 都完整。其配置文档区分 repeat 与 filterSampleSeed，后者选取测试案例，不是模型采样 seed。本文未运行 promptfoo 或其 provider，仅静态核对这些行为。

### 3. 原创实验：单例更好，整体与关键案例如何判断

目标是识别客服文本意图，合法标签为 refund、track、handoff、other，输出只允许 `{"label":"…"}`。P1 要求分类并返回 JSON；P2 增加“判断否定表达和最终意图，账户关闭交人工”。两份完整 prompt 保存为 `prompts.json` 的 p1/p2，模板 hash 和实际 messages 导出到每份实验记录，预期标签只交给评分器，不放进请求。

**执行身份全部为 mock**：adapter=`mock://intent / adapter-r1`，模型=`mock-intent / table-r1`，渲染器 messages-r1、评分器 label-exact-v1、数据集 synthetic-intents-v1。参数记录为 temperature=0.2、top_p=1.0、max_output_tokens=40；seed=11/23/37 在这个 mock 中只是三个预编程表槽，不调用随机数生成器，也不实现这些模型采样参数。字段记录齐全不代表真实接口已接纳它们。

主对照关闭完整响应缓存，provider 前缀缓存记 not_applicable。两版各 4 案例 × 3 槽 = 12 条计划记录，合计 24 次顺序 mock 调用；这是单份实验的调用次数预算，不是 Token、费用、平台总预算或独立随机样本数。tokens/cost 均为 null。真实模型、业务集成、独立保留集均为 **not_run**。

2026-09-16，Python 3.11.8 实跑的预编程响应如下。表中收益不能外推为模型质量，三槽只是验证记录与判断逻辑的固定数据：

| 同组输入 / 预期 | P1 三槽输出（11、23、37） | P2 三槽输出（11、23、37） | 固定案例判断 |
| --- | --- | --- | --- |
| C1：退货后多久退款 / refund | refund、refund、other | refund、refund、refund | 2/3 → 3/3 |
| C2：包裹到哪里了 / track | track、track、track | track、track、other | 3/3 → 2/3 |
| C3：先不要退款，我只想查物流 / track | refund、refund、track | track、track、track | 1/3 → 3/3 |
| C4：请关闭我的账户 / handoff，关键案例 | handoff、handoff、handoff | other、handoff、other | 3/3 → 1/3，触发关键退化 |

如果只展示 C1 的第 37 槽，会看到 P2 进步；全部计划槽的准确数却都是 **9/12**，关键案例从 **3/3 降到 1/3**，所以本地判定为 reject_critical_regression。即使 mock 结果全部变好，也只能说明这组预写表与评分逻辑的结果，不能宣布真实模型或业务收益；production_approved 始终 false。

另一次独立故障运行在 P2/C2/23 同步注入 TimeoutError。保留 24 条计划记录和 12 的分母，其中一条明确标 timeout，判定 blocked_execution；没有删掉失败后只算成功调用。这个实验验证错误记录与传播，不验证真实网络 deadline、异步取消或服务稳定性。

### 4. 用失配反例验证实验装置

完整记录应能导出、重新读取并按同一契约评分。示例校验 prompt/模型/参数/数据集/评分器版本、有效请求及响应指纹，要求成对矩阵完整、样本 ID 与来源调用不重复，并拒绝把缓存命中或 mock 结果标成真实执行。未知程序错误和写出故障继续传播，不变成“对照通过”。

缓存反例先对 C3/11 运行 P1，再请求 P2。故意不完整的 key 只含 input/model/params，漏掉 prompt 等请求身份；第二次取回 P1 响应时，其 request_sha 与 P2 请求不符，被拦住。改为完整有效请求的 canonical hash 后，P2 取得自己的 track，重复同一请求才返回已标注的缓存结果。以下为实际代码摘录，依赖完整复跑包中的 helper，不是供应商 SDK 或生产缓存实现：

```python
def observe(m, pid, case, slot, adapter, cache, enabled=False):
    request=render_request(m,pid,case,slot)
    try:
        response,hit=cache.resolve(request,adapter,enabled)
    except TimeoutError:
        response=dict(request_sha=fingerprint(request),model_revision=MODEL['revision'],source='preprogrammed',
                      source_call=adapter.calls,status='error',output=None,error='timeout')
        hit=False
    require(response['request_sha'] == fingerprint(request), 'cache_or_response_request_mismatch')
    require(response['model_revision'] == m['model']['revision'], 'response_model_mismatch')
    return dict(prompt_id=pid,case_id=case['id'],slot=slot,request=request,response=response,
                response_cache_hit=hit,provider_prefix_cache='not_applicable',tokens=None,cost=None)
```

同一 `probe_cache.py` 对不完整 key 实跑 **3 tests / 1 failure / 0 errors，exit 1**，对完整 key **3 tests 全绿，exit 0**。probe 与输入/prompt/响应表 hash 不变；它揭示的是人工设置的缓存键缺陷，不能说成发现了 promptfoo 或真实 provider 的 bug。

另有 **32 tests 通过**，覆盖版本/参数漂移、bool 冒充数值、实际请求与响应失配、缺失/重复样本和来源调用、缓存伪装新样本、虚构用量/真实执行、调用预算、超时、JSON 边界、输出写失败与导出重读。32 次输入不变检查通过，测试根和导出临时根均已清理。解压原创证据包可运行 `python3 test_playground.py`、`python3 run_experiment.py`；原始红绿 stderr、全部有效请求和原始 mock 输出随包保留。

### 5. 从实验装置走向业务验收

| 测试方式 | 适用与代价 | 不能据此证明 |
| --- | --- | --- |
| mock / 录制回放 + 固定案例 | 低成本核对渲染、协议、缓存 key、记录完整性与评分回归；输出可稳定重放 | 新模型质量、真实服务参数接纳、网络表现或业务集成 |
| 隔离 Playground 的真实接口对照 | 在获授权的环境观察真实采样、输出与用量；需冻结版本、控制缓存/重复与费用，保留失败 | 固定案例外的总体收益，或 UI、权限、检索、工具副作用等完整链路正确 |
| 业务集成与独立评估 | 验证实际输入组装、schema/工具、权限、超时重试、用户体验及受影响链路；成本和环境要求较高 | 无条件未来收益；仍需范围、已知限制、受控发布与回滚证据 |

本题只完成第一层及记录校验，没有搭建真实 Playground 页面，也没有运行后两层。业务接入前应核对经过评审的 prompt/代码版本与部署候选一致，使用未用于反复调参的代表性评估数据，检查关键分层、真实异常路径与集成依赖；缺证据应记 not_run 或阻塞，不能补造“通过”。固定案例全绿证明的范围取决于案例和断言，不等于需求覆盖。

### 常见误区与追问

- **“可视演示顺畅就是生产验收。”** 页面能展示回答只覆盖有限路径；mock、真实接口和完整业务链路必须分别标注与验证。
- **“一次样本更好就是总体提升。”** 先看预先规定的全部对照与关键分层，再考虑独立评估和不确定性；不能用反复挑选的最好回答替代完整结果。
- **“固定 seed、温度和缓存就一定可复现。”** 字节回放、mock 表槽与真实采样不同；参数支持范围和后端版本要核实，provider KV cache 也不是旧答案缓存。
- **追问：团队升级了模型别名，历史实验怎么比较？** 保留当时返回的版本/fingerprint与有效请求；缺少精确后端信息就注明限制。旧记录可继续做解析/评分回归，要评价新模型则建立新实验组，不能改历史标签冒充同一条件。
- **追问：缓存命中率高，新版时延更低，能上线吗？** 先区分应用响应缓存、请求合并与 provider 前缀缓存，核对实际新请求次数、冷/热条件、时延口径和质量约束。命中率不能替代内容正确、失败恢复或业务集成验收；本题未测真实时延与费用。

## 参考

- 洛小山《AI 产品从入门到精通》，learn-ai 固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/vibe-3.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-3.html)、[slides/build-2.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/build-2.html)、[slides/cost-eval.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/cost-eval.html)。作为隔离试验与评估的学习线索；vibe-3 主要讲组件 Playground，不能当作本文完整 Prompt 实验契约的实现。其固定维护习惯不推广为普遍规则，未复制 AGPL 课件正文、代码或图片。
- OpenAI 官方文档：[Prompt Caching](https://developers.openai.com/api/docs/guides/prompt-caching) 与 [Chat Completions Create](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。2026-09-16 读取快照，核对 KV 前缀复用、新响应生成、seed 的接口限定及 fingerprint；在线文档会更新，不将网页快照冒充固定模型版本。
- promptfoo 作者仓库固定 `7867eb24b2635e259e1dc05999e50f775ba7a5e2`：[src/cache.ts](https://github.com/promptfoo/promptfoo/blob/7867eb24b2635e259e1dc05999e50f775ba7a5e2/src/cache.ts#L557-L584)、[响应缓存分支](https://github.com/promptfoo/promptfoo/blob/7867eb24b2635e259e1dc05999e50f775ba7a5e2/src/cache.ts#L839-L929)、[配置参考](https://github.com/promptfoo/promptfoo/blob/7867eb24b2635e259e1dc05999e50f775ba7a5e2/site/docs/configuration/reference.md#L185-L218)。静态核对自动/自定义 key、缓存响应、repeat 与 filterSampleSeed；没有执行作者工具、读取凭据或调用模型。
