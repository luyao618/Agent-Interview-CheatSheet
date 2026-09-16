---
id: engineering-0039
title: AI 协作跨会话后，如何保留决策理由、被否决方案和用户可读的发布记录？
category: engineering
tags: [adr, decision-record, documentation, changelog, release-notes]
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

AI 协作跨会话后，如何保留决策理由、被否决方案和用户可读的发布记录？假设把方案 A 改为 B，应分别更新哪些文档，如何防止旧决策被当成现行规则、文档已写却实现未完成？

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**把决策变成可定位、可追溯、有状态的记录，再按读者需要生成变更摘要。** 接任者应能回答：当时解决什么问题、在什么约束下选了谁、为何放弃其他方案、谁确认了决定、哪次变更实现了它、现在还适用吗。聊天摘要可以帮助寻找线索，却不能替这些问题提供可靠答案。

本题聚焦开发决策与文档生命周期；用户记忆写回见 [agent-0028](agent-0028-long-term-memory-writeback-decay-conflict.md)，现行 Prompt 维护见 [agent-0045](agent-0045-system-prompt-entropy-control.md)，长任务验收交接见 [agent-0063](agent-0063-long-task-initializer-handoff.md)。记录“当时选 A”是历史事实；把它提升为“此后必须使用 A”的规则，需要明确作用域、批准来源及复议条件。

### 1. 决策记录保存理由，变更记录保存交付关联

ADR 或设计笔记至少包含稳定 ID、标题、日期、问题与约束、状态、选定方案、被否决方案及理由、后果、复议条件，以及需求、PR/commit、验证记录的引用。不要只写“讨论后选 B”，也不要补造未曾验证的收益。引用原始讨论时保留必要出处即可，避免复制密钥、全量输入或整段私人对话。

可采用 `proposed → accepted / rejected`、`accepted → superseded` 的决策状态流。**accepted 表示决定被接受，不表示已实现、已验证或已发布。** 实现状态与发布状态要另行记录。若新条件推翻旧选择，创建新 ID，保留旧理由并补双向替代关系；纠正历史记录中的笔误可以走有说明的修订，不应偷偷重写成“我们一直都选 B”。

Nathaniel Pryce 的固定 `adr-tools` 模板有 Status、Context、Decision、Consequences；`src/adr-new:108–119` 实际会默认写入 Accepted，并为 `-s` 添加替代链接。它不是自动审批器，也没有实现本文的完整生命周期门禁。其 `_adr_generate_toc:57–62` 输出标题与链接，不能据此声称已经核对状态一致性。本文增加的替代方案、复议条件及校验规则是示例设计。

| 记录 | 主要读者与内容 | 与其他记录的关系 |
| --- | --- | --- |
| ADR / 设计笔记 | 接任开发者、评审者；问题、理由、取舍、适用条件及状态 | 用稳定决策 ID 关联需求和具体变更，保留被否决与被替代记录 |
| changelog | 维护者与升级者；某版本有哪些值得关注的变化、兼容性影响 | 从已实现变更归纳并链接 ADR/PR；未发布内容留在 Unreleased，不直接倾倒 git log |
| release notes | 该版本的使用者；能做什么、行为变化、操作或迁移要求、已知限制 | 绑定具体版本与交付范围，从 changelog 筛选、改写；文稿存在不证明实际发布 |

Keep a Changelog 1.1.0 强调按版本精选重要变化、面向人阅读，并将 Unreleased 在发布时归入版本。changelog 也可以面向最终用户，不能机械规定它只能写技术细节。release notes 中若 API 兼容性、配置变化或安全事项影响使用者，就应写清楚；“不出现任何技术信息”不是通用标准。GitHub 官方文档还区分 tag 与 release：两者可以有不同日期，不能拿文档日期冒充发布时间。

### 2. 原创 A→B 案例：先改变决定，再验证交付

下面全部是原创合成数据，日期为本次验证日期，不是产品事故或发布历史。R1 的模拟机器读取方接受无 BOM 的 UTF-8 CSV，因此 ADR-0001 选择 A。R2 新增一个 **明确要求 `EF BB BF` 前缀的 toy importer**，输入仍是两列 `city,count` 和一行 `宁波,2`。这个要求由教学 fixture 定义，不代表所有电子表格软件的实际行为。

新建 ADR-0002，选择 B：仅为 `desktop-csv-export` 增加 UTF-8 BOM，API 导出不在范围内。重审 A：它满足旧 R1，但不满足新增 R2；拒绝 C“运行时猜测导入器”，因为检测条件与失败回退尚未定义。后果是每个样例多 3 bytes，需要确认消费者是否接受前缀；复议条件是支持的消费者或编码要求改变。没有声称这能提升真实产品兼容率。

设计记录保留上述完整理由，关联合成变更 C2。C2 验证后，changelog 的 Unreleased 增加“桌面 CSV 加入 UTF-8 BOM”，链接 ADR-0002，并保留 artifact digest。示例 `0.2.0-demo` release notes 改写为“模拟导入器无需手工选择编码即可读取桌面 CSV”，同时写明旧文件不回写、真实电子表格测试 `not_run`。C2 是合成变更编号，不是真实 PR；`0.2.0-demo` 是虚构版本，所有快照均为 `real_release=false`。

2026-09-16 在 Python 3.11.8 中实跑五个磁盘快照，每次重新读取记录，并逐对验证状态迁移：

| 快照 | ADR-0001 / ADR-0002 | 当前目标决策与实现证据 | changelog / release notes |
| --- | --- | --- | --- |
| initial | accepted / 不存在 | A，旧 R1 样例已验证 | 无 C2 条目 / 无 |
| proposed | accepted / proposed | 仍为 A；B 只是提案 | 无 C2 条目 / 无 |
| accepted | superseded / accepted | B，但 C2 仍为 planned | 无 C2 条目 / 无 |
| delivered | superseded / accepted | B，C2 样例已验证 | C2 在 Unreleased / 无 |
| demo_release | superseded / accepted | B，同一 C2 artifact | C2 归入虚构版本 / 1 份明确标示为示例的 notes |

样例 A 实测为 20 bytes，B 为 23 bytes，增量为固定前缀的 3 bytes；其余字节相同。toy importer 拒绝 A、接受 B 并检查解码后的原始行。该结果只验证既定 fixture。决策层的“当前目标”是 B，并不表示 B 已部署；接任者还必须读取 C2 的实现状态及对应证据。

另一个分支将 B 提案置 rejected，A 仍是当前决策，B 的理由继续可检索。若以后重新考虑，应说明新条件并建立新记录或经批准的复议过程，不能直接把旧 rejected 文档当成已接受方案。

### 3. 文档生命周期也需要可检出的反例

示例采用 `decisions/<status>/<ID>.md`，JSON frontmatter 是便于标准库解析的教学格式，并非 ADR 标准要求。目录位置、正文元数据和索引状态必须一致；迁移时同步更新路径与引用，稳定 ID 用于查询替代链。若用平铺目录，则不必移动文件，但仍要校验元数据和索引。把状态同时复制到多处而不校验，会给下一班提供冲突答案。

校验器检查必需章节、ID 唯一性、目录/状态/索引一致、替代链接存在且双向对应、无环，以及同一作用域恰好一个 accepted 决策。当前目标投影只能引用该 accepted 记录；历史查询则展示 superseded/rejected 状态和后继。C2 的实现记录绑定 artifact，changelog 与 notes 关联同一变更与版本；planned、缺失或摘要不匹配都不能作为已验证交付。

仅检查当前快照还不能发现历史理由被悄悄改写，因此下面这段实际测试代码同时读取前后版本。它是附件中完整校验器的摘录，依赖 `validate`、`load_records` 和 `require`，不能单独代替生产工具：

```python
def validate_transition(previous, current):
    validate(previous); result = validate(current)
    old, new = load_records(previous), load_records(current)
    allowed = {'proposed': {'proposed', 'accepted', 'rejected'},
               'accepted': {'accepted', 'superseded'},
               'rejected': {'rejected'}, 'superseded': {'superseded'}}
    for rid, before in old.items():
        require(rid in new, 'history_deleted')
        after = new[rid]
        require(after['meta']['status'] in allowed[before['meta']['status']], 'state_regression')
        if before['meta']['status'] != 'proposed':
            require(before['body'] == after['body'], 'history_rewritten')
            for key in ('id', 'topic', 'change', 'supersedes', 'approval'):
                require(before['meta'][key] == after['meta'][key], 'history_rewritten')
    return result
```

保留的错误快照中，ADR-0001 已在 superseded 目录且元数据正确，索引却仍标 accepted。同一 `probe_contract.py` 的三项断言实跑得到 **3 tests / 1 failure / 0 errors，exit 1**；只修正 `index.json` 后 **3 tests 全绿，exit 0**。旧理由、当前 B 目标与 C2 planned 状态不变，测试文件 hash 相同。这是故意构造的文档不一致反例，不是生产事故，也不计作测试脚本错误。

另有 **30 tests 通过**，覆盖重复 ID、过时目标、空替代方案、断链/环、双 accepted、错误变更关联、artifact 漂移、未验证变更混入发布记录、历史重写、状态倒退、拒绝提案、解析边界和读取失败；22 次负例校验保持输入不变，30 个测试根及回放临时根均已清理。更新 hash 后仍错误的无 BOM artifact 会被 importer 行为检查拒绝，说明“一致的文档与摘要”本身不能证明行为正确。

附件保留六组原始快照、错误输出、修正对照和复跑脚本。解压后可运行 `python3 test_decisions.py` 与 `python3 verify_lifecycle.py`；后一命令回放保留快照，不在评估路径调用生成器。

### 4. 按规模选择记录方式，并限定保证

| 方案 | 适用情况与代价 | 不适用或不足 |
| --- | --- | --- |
| 单份设计日志，使用稳定锚点、状态和变更链接 | 小项目、少量决策；维护成本低，可直接全文检索 | 内容多时容易冲突、检索噪声大；只有流水账而无状态不能可靠决定当前方案 |
| 每项决策独立 ADR，派生索引并校验关系 | 长期协作、经常复议；取舍和替代链易查，适合随变更评审 | 元数据与迁移成本较高；每个拼写修改都建 ADR 会制造噪声，目录本身不证明审批或代码正确 |

接任时先核对代码与文档版本、未提交变更，再按需求/组件/决策 ID 查询；读取当前决策及替代链，核对实现/验证引用和未发布条目，最后记录本班变化。记录缺失、引用失效或状态冲突时，应停在可说明的未知状态，修复证据或请有权方确认。重放全部聊天既增加成本，也可能把被否决方案、一次性意见或无关敏感内容重新注入。

本题测试只读取静止的专属目录，模拟跨会话是重新解析磁盘文件，没有派发真实 Agent。批准字段只是 mock 标签：测试明确展示改成虚构标签仍能通过，因而它只检查完整性，不验证批准者身份。正式项目须使用受控评审与权限校验；hash 不是签名，当前快照校验不是并发事务、外部写者 CAS、持久存储保证或真实记忆管理。自然语言理由是否充分、发布日期是否真实、兼容性是否满足，也不能只靠结构校验决定。

### 5. 常见误区与追问

- **“保存全部对话就保存了可检索决策。”** 对话含试探和否决；需要提炼 ID、约束、理由、状态与证据引用，并在接任时实际检索核验。
- **“目录移动了就完成状态流转。”** 元数据、索引、替代关系和引用也要一致；同时 accepted 两个互斥方案应拒绝给出当前结论。
- **“历史上否决过 A，所以以后禁止 A。”** 旧结论依赖旧条件；新约束可以触发复议。持久事实不会自动升级为现行指令，本题示例也不修改本项目的记忆或协作规则。
- **“changelog 有一行就可以写已发布。”** 接受决定、实现、验证与发布是不同事实；用户可读记录必须绑定实际交付范围，mock notes 不证明真实发布。
- **追问：两个会话同时创建同一 ID 或分别改目录、索引怎么办？** 本地先检测重复和不一致，再基于共同基线合并并重验；在一个受控变更中提交相关文档。仅在保存前检查 hash 不能阻止任意外部写者，不能把该做法宣传成 CAS。
- **追问：上线后发现 B 不合适，能把旧 ADR 改回 accepted 吗？** 应保留 B 的实施和故障事实，为回退建立明确决定与变更关联，验证恢复后的行为，再更新发布/撤回说明。直接倒退状态会丢失时间线；本题的严格 toy 状态机不实现完整生产回滚。

## 参考

- 洛小山《AI 产品从入门到精通》，learn-ai 固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/vibe-7.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-7.html)、[slides/dsh-27.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-27.html)、[slides/vibe-10.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-10.html)。作为文档分工、设计笔记与约束复核的学习线索；固定文件名、自动记忆写入、DSH 内部数量/门禁描述均不作为通用保证，未核实或执行其所述私有实现。没有将课件正文、代码或图片搬入本题。
- Nathaniel Pryce，`adr-tools` 固定 `b3279baf9be2207d1a4f4bbd608fd0b591c72aee`：[模板](https://github.com/npryce/adr-tools/blob/b3279baf9be2207d1a4f4bbd608fd0b591c72aee/src/template.md#L1-L19)、[adr-new](https://github.com/npryce/adr-tools/blob/b3279baf9be2207d1a4f4bbd608fd0b591c72aee/src/adr-new#L108-L132)、[目录生成](https://github.com/npryce/adr-tools/blob/b3279baf9be2207d1a4f4bbd608fd0b591c72aee/src/_adr_generate_toc#L57-L63)。静态核对模板、默认 Accepted 和替代链接行为；未执行作者脚本，未声称它验证审批、完整状态机或多文件原子更新。
- Olivier Lacan 等，Keep a Changelog **1.1.0**，固定 `08d0df5a7e93b71d902def8be0f0d40025b56289`：[英文正文源码](https://github.com/olivierlacan/keep-a-changelog/blob/08d0df5a7e93b71d902def8be0f0d40025b56289/source/en/1.1.0/index.html.haml#L21-L145)。重点为精选版本变化、面向人、Unreleased 和 commit log 的区别。
- GitHub 官方文档，固定 `d79d9d354377b9f8b820e16c12b91734881a0f93`：[About releases](https://github.com/github/docs/blob/d79d9d354377b9f8b820e16c12b91734881a0f93/content/repositories/releasing-projects-on-github/about-releases.md#L19-L31)。release 基于 tag，可手工或自动生成 notes；没有创建或发布本题的虚构产品版本。
