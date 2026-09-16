---
id: agent-0063
title: 长任务跨多个上下文窗口时，Initializer 与执行 Agent 如何交接并防止过早宣布完成？
category: agent
tags: [initializer, long-running-agent, handoff, acceptance, evidence]
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

长任务跨多个上下文窗口时，Initializer 与执行 Agent 如何交接并防止过早宣布完成？假设有三项功能，第一班只完成一项就换班，接任者应读取、验证哪些持久产物，依据什么继续工作或终止？

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**Initializer 留下可复现的起点和待批准的验收基线；执行 Agent 每班交付可验证的小增量；接任者重建现场，验收方按当前产物独立决定是否完成。** 上一班的文字总结帮助定位，却不能替代本班对代码、环境和功能行为的核验。一次上下文窗口结束也不表示整个任务结束。

[agent-0016](agent-0016-checkpoint-resume.md) 讨论运行状态如何恢复，[agent-0054](agent-0054-self-improving-agent-trust-root-boundary.md) 讨论标准由谁控制。本题把两者落到功能交付：保存了 checkpoint 不代表功能正确，拥有不可改的测试也不代表接任者拿到的是被测版本。子任务进程所有权另见 [agent-0061](agent-0061-subagent-supervision-durable-graph.md)。

### 1. 先建立验收基线，再建立可重复的起点

Initializer 应从用户需求提炼稳定的功能 ID、输入、操作、预期结果、依赖和完成口径，并把未知项留为待确认。功能表要覆盖失败路径和横跨功能的关键流程。自动生成的列表可能漏需求，须由有权验收者确认；“Initializer 写过”不是批准来源。

每项要求的定义与每次执行的结果应分开。定义属于版本化的标准；`pending / failed / passed` 是某个候选版本上的验证结果。初始状态应是未验证，不能因脚手架可启动就标成功。后续回归失败必须撤销旧的通过投影，不能只允许 `false → true`。

初始化还应产出环境版本、依赖锁定信息、启动及停止说明、测试命令、基础 smoke 结果、初始提交和阻塞清单。初始化脚本要明确所有权、重复执行行为和清理责任；接任者应先核对其版本与允许操作，再运行。真实项目若缺少授权依赖或配置，应报阻塞，不能改用户配置来伪造环境一致。

“初始化完成”与“所有功能完成”是两个不同的门槛。初始化中断后，不能只凭 `feature_list.json` 是否存在就宣布可以继续，也不能无条件重新初始化覆盖上一班成果。

### 2. 一次换班交付哪些东西

| 持久产物 | 写入方 / 作用 | 接任者核验 |
| --- | --- | --- |
| 需求与验收功能表 | Initializer 提案，有权方批准版本；列出全部必需功能与明确预期 | 版本、完整 ID 集、批准来源；有增删或放宽则重新审核，不能只看通过比例 |
| 源码提交 / 候选 artifact | 执行方交付明确的版本 | commit/tree 或 artifact digest、工作区差异；未提交改动要明确作为 WIP，不混入已验版本 |
| 环境与初始化说明 | 记录依赖、运行条件、smoke 和资源所有权 | 重建可用环境，检查版本与 smoke；环境改变可能使旧结果失效 |
| 验证回执与原始结果引用 | 验证方产生，绑定候选、标准、测试套件和环境 | 来源是否可信、绑定是否当前、必需检查是否全部结束；缺失、超时、跳过不能当通过 |
| 交接清单 | 指向上述版本，列出已验项、未验项、回归、阻塞和下一步 | 引用是否存在且互相一致；部分写入或旧引用应停止并修复交接 |
| 进度文本 | 执行方解释改动原因、尝试和待办 | 作为索引线索，必要时查具体证据；自报“完成”不拥有验收权 |

上下文里只需放当前任务所需的摘要、版本和证据引用，不必重灌全部聊天记录。持久记录也受保留策略、权限、存储故障约束，不能把“有 Session”描述成无限容量或永不丢失。

接任流程可以按五步讲清：核对标准与交接版本 → 检查工作区并重建环境 → 重验关键已完成项 → 选一项增量实现并回归 → 发布新证据及交接清单。日常 smoke 可先检查核心路径，但最终完成门槛仍需全部必需检查；只抽查两项不能推出整张表通过。

### 3. 完成权在执行循环之外

独立完成条件至少包括：全部必需功能在**同一交付候选、当前标准和适用环境**上通过；集成检查结束；没有未知或未收集结果；交接产物完整；需要的人工验收已取得。完成结论也要绑定候选，验证后再修改代码，就要重新验收。

不能只写一句“禁止改测试”。候选代码、进度和提案可由执行方写入；标准、验证器、结果来源及控制这些东西的门禁，应由独立受控的身份和变更通道管理。验证器从已批准版本取规则，在适当隔离环境中检验候选，不能加载候选附带的“总是返回 true”的测试入口。hash 只能帮助核对内容，不能证明批准者身份；同目录放一份 hash 也不能阻止有权限的写者同时修改两份文件。

SLSA v1.2 对 provenance 的来源、产物 digest 和控制面抗篡改有具体要求，可借鉴其证据绑定思路；它没有替项目判断功能正确。本题也不把独立脚本或另一个模型等同于完整权限隔离。

循环停止还需与成功分开：预算到限、连续无可验证进展、关键环境不可用、需求矛盾、验证器出错，应进入相应的暂停/阻塞状态。停止时保留已完成成果和原因，而不是把剩余项删除后宣布完成。预算由监督方跨班次保存，重新建上下文、改任务名或再次调用 Initializer 都不能自动重置它。

| 组织方式 | 适用条件及好处 | 代价 / 不适用场景 |
| --- | --- | --- |
| 单一上下文完成一个短任务 | 范围小、环境稳定，交接成本低 | 不适合长期多班次工作；窗口容量不是持久交付协议 |
| Initializer + 每班一个可验增量 | 多功能长任务，接任成本可控，容易发现哪班引入回归 | 需要维护标准、环境和证据；强耦合功能可选最小可验纵向切片，不能机械拆成互不工作的碎片 |
| 并行分工 + 集成验收 | 依赖可分离，具备隔离工作区、冲突处理和统一集成候选 | 多个分支各自通过不等于合并通过；缺少集成 owner 时不宜靠并发加速 |

### 4. 三项功能，只完成一项就换班

以下是原创的离线“订单报价”合成项目。金额单位为虚构整数分；mock 解释器读取 `app.json` 的三个有限开关，不执行候选代码、不启动真实 Agent 或服务。

| 功能 | 固定输入及预期 | 第一班候选 |
| --- | --- | --- |
| F1 数量计入小计 | `(数量2,单价300) + (数量1,单价200)` 得到 `800`；空订单小计 `0` | 通过 |
| F2 运费边界 | 小计 `999 / 1000 / 1001` 时，运费为 `100 / 0 / 0` | 实际均为 `100`，失败 |
| F3 拒绝负数量 | `(-1,300)` 必须抛出 `InvalidOrder` | 实际允许，失败 |

初始化生成 `acceptance.json`、`environment.json`、未完成功能的 `app.json` 和进度说明。标准中的 F1/F2/F3 不因第一班只完成 F1 而缩小。每次发布由模拟监督方执行固定行为断言，将回执保存在 `control/state.json`，再把同一回执发布到项目的 `handoff.json`；进度说明最后写入。回执绑定三个输入文件的原始 bytes hash 和验证器 hash，`seq` 标识发布次序。

第一班发布后的实际持久状态如下（2026-09-16，Python 3.11.8 本地运行）：

- `app.json`：数量按乘法计算，运费仍固定，负数量仍允许。
- `acceptance.json`：完整保留三项定义；`environment.json` 仍为 `mock-quote-v1`、合成整数分。
- `control/state.json`：`seq=1`，回执结果为 `F1=true,F2=false,F3=false`；演示初始五次发布额度，剩余四次。
- `handoff.json`：与控制面当前回执及内容绑定一致。
- `progress.md`：故意写入虚构的 `ALL COMPLETE`，用于反例，不作为判定输入。

在**同一个前台调用内**删除旧 `Supervisor` 对象，再创建新对象打开这些文件模拟换班。接任者核验标准/环境的预设 pin、完整候选、当前回执与交接一致性，并重新运行固定断言，实际得到 `accepted=[F1]`、`pending=[F2,F3]`、`status=continue`。第二班补 F2 后为 2/3；第三班补 F3、回归 F1/F2 后为 3/3，才返回 `complete`。这不是依靠结束本轮或遗留后台任务实现的恢复。

下列 `decide` 是可复跑 fixture 中的原样函数。它是最后的判定步骤，调用前还必须完成上述来源、绑定、完整性和重验检查；单独调用它不能替代整套验收。

```python
def decide(results, remaining, stalls):
    """Called only after authority, complete feature set, artifacts and receipt checks."""
    if set(results) != set(FEATURES) or any(type(v) is not bool for v in results.values()):
        raise GateError('invalid_results')
    if all(results.values()):
        return 'complete'
    if remaining == 0:
        return 'blocked_budget'
    if stalls >= 2:
        return 'blocked_stalled'
    return 'continue'
```

`FEATURES` 固定为 F1/F2/F3。五次额度和连续两次无进展阈值只是本实验的监督策略，单位是控制面已登记的验收回合（含功能失败及后续交接中断），不是 Token 计费；结构/写出错误直接停止，由调用方处理。本实验没有自动重试循环。最后一次额度若全部通过，允许完成；额度耗尽仍有失败则为 `blocked_budget`。重新打开对象保留计数，重复初始化会被拒绝。

反例不止是修改进度：删掉 F2/F3、放宽 F2 定义、换环境或换验证器都不能沿用旧回执；未批准的标准/环境不能产生新回执。代码在验收后改变则返回 stale；回归会使旧 `passed` 重新变失败。旧交接文件重放、篡改项目侧结果、回执已写而交接未写等路径也会被拒绝，不能简单拿“最新一份 JSON”猜测成功。

本地最终 **33 tests** 通过，33 个测试临时目录全部移除，28 次只读核验确认文件 bytes 未改变。另保留两个刻意植入的缺陷副本：把全量 `all` 改为 `any` 会过早完成；跳过标准/环境 pin 校验会允许未批准基线进入新验收。原样断言均检出，实际进程 exit1 且无未处理测试错误；这只是对所选缺陷的检出证据，不是完备证明。附件提供完整原创 fixture、测试、逐班产物、反例 diff 与日志，便携脚本在专属临时副本复跑。

实验边界必须保留：`control/` 与项目目录的分离是**模拟可信控制面**，没有实现生产身份认证或同进程防篡改；所有调用按确定顺序执行，没有验证真实并发、进程崩溃接管或分布式调度。逐文件 `os.replace` 不能提供多文件事务、断电持久性或对任意外部写者的 CAS；校验后仍有外部修改窗口。本例的内存 snapshot 和回执只证明所验候选，实际消费/发布时还须绑定相同产物。真实服务、UI、第三方依赖及部署接纳需要各自的独立验证。

### 5. 一手来源能支持到哪里

Anthropic `claude-quickstarts` 固定提交 `8826387af1d23280996f0a0892e0cfd764becb57` 的 `autonomous-coding/prompts/initializer_prompt.md` 要求建立功能表、初始化脚本、初始提交与进度说明；`coding_prompt.md` 要求新上下文先定位现场、验证已有功能、增量推进。它的浏览器验证要求服务于该 Web 应用示例，不能推广为所有后台任务都必须用浏览器测试。

同一版本的 `progress.py::count_passing_tests` 读取列表中的 `passes` 做统计，不执行行为验收；`agent.py::run_autonomous_agent` 以 `feature_list.json` 存在与否选择初始角色，循环受 `max_iterations` 控制，未见基于全量独立验收结果的成功退出分支。因此“显示已通过”“循环结束”“功能获验收”不能混写。示例 prompt 中的强措辞及“可一直继续”也不构成实际权限与预算保证。

课程是学习线索，本文没有照搬其正文、代码、图片或效果数字；JSON 比 Markdown 更不易被模型误改、固定数量功能能自动交付等效果没有在本实验验证。格式可解析有助于验证，却不保护标准的修改权限。

## 延伸 / 追问

- **接任者发现上一班写“通过”的功能现在失败，先继续下一项吗？** 先记录当前候选上的失败并复查版本、环境及回执。若是回归，先修复或明确隔离；不能把旧结果当永久认证。抽查发现问题也不能仅把文本改回来，应重新产生对应版本的证据。
- **需求真的变了，是否永远禁止修改测试？** 可以提议新标准，经有权方批准新版本，保留变更理由与旧基线，说明哪些旧回执作废并重新验证。执行方不能独自通过删掉失败项来缩小任务范围。
- **下一班能沿用上一班开着的服务吗？** 只有宿主生命周期、所有权、访问权限、结果及清理责任有明确交接时才行；进度文件写一个 PID 或 URL 不能提供可靠托管。否则保存可重建产物，并在本班回收自己启动的资源。
- **十班都没完成，是不是再加上下文窗口就好？** 先看需求是否不清、环境是否不可复现、工作是否反复回归、验收是否本身错误。到预算或无进展阈值应带证据停止，由有权方决定调整；换上下文不延长授权。

## 常见误区

- **“进度文本写完了，任务就完了。”** 文本属于执行方叙述，验收结果属于绑定当前版本的验证证据。
- **“禁止改测试”足以保护标准。** 需要受控版本、独立修改权限、验证器和结果来源；模型遵守提示的概率不是权限边界。
- **“读完进度/看到 commit 就恢复完成。”** 还要核对环境、候选与证据。Git commit 记录内容，不自动证明测试通过；干净工作区也可能完整地保存着错误代码。
- **“每班一个功能，因此最终三个旧通过记录可相加。”** 后续增量可能破坏前项，应对统一交付候选重新检查；三次不同版本上的局部通过不是一次整体通过。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定版本 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/10-11.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/10-11.html)、[slides/10-12.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/10-12.html)、[slides/10-14.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/10-14.html)。仅作研究线索，AGPL 素材未进入本题。
- Anthropic，`claude-quickstarts`，固定提交 `8826387af1d23280996f0a0892e0cfd764becb57`：[Initializer prompt](https://github.com/anthropics/claude-quickstarts/blob/8826387af1d23280996f0a0892e0cfd764becb57/autonomous-coding/prompts/initializer_prompt.md)、[Coding prompt](https://github.com/anthropics/claude-quickstarts/blob/8826387af1d23280996f0a0892e0cfd764becb57/autonomous-coding/prompts/coding_prompt.md)、[agent.py](https://github.com/anthropics/claude-quickstarts/blob/8826387af1d23280996f0a0892e0cfd764becb57/autonomous-coding/agent.py)、[progress.py](https://github.com/anthropics/claude-quickstarts/blob/8826387af1d23280996f0a0892e0cfd764becb57/autonomous-coding/progress.py)。源码只读，未安装或运行其 Agent。
- SLSA，[v1.2 Build requirements](https://slsa.dev/spec/v1.2/build-requirements)：Provenance generation、Unforgeable 与 Isolation strength；来源完整性和功能验收不能互相替代。
- Git，[v2.46.0 `git-commit`](https://github.com/git/git/blob/v2.46.0/Documentation/git-commit.txt)：提交记录的内容与说明，不等于执行测试。
- CPython，[v3.11.8 `os.replace`](https://github.com/python/cpython/blob/v3.11.8/Doc/library/os.rst)：成功 rename 的原子性范围；不是跨文件事务或外部写者 CAS。
