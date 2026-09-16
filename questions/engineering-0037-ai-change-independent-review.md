---
id: engineering-0037
title: AI 同时写实现和测试时，怎样独立验收一次变更，并防止发布混入未完成或未声明的内容？
category: engineering
tags: [ai-coding, code-review, acceptance, integration, release]
difficulty: medium
role: both
contributor: CX-Dev
source: 洛小山《AI 产品从入门到精通》learn-ai LA-051；Google Engineering Practices；Git v2.46.0文档
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

AI 同时写实现和测试时，怎样独立验收一次变更，并防止发布混入未完成或未声明的内容？如果声明“仅改夜间模式”，实际 diff 却包含协议修改和依赖升级，应怎样判断与处理？

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 回答日期：2026-09-16

**验收要建立“需求—实际变更—独立证据—发布产物”的对应关系，不能只接收作者的成功叙述。** AI 写的实现和测试可能共享同一个错误假设：实现漏掉需求，测试也没有断言它，结果依然全绿。把同一份解释再交给另一个 Agent复述，也不自动获得独立性；reviewer必须能回到原始需求、真实diff、既有契约和可复核的执行记录。

### 先界定验收对象，再决定证据强度

固定需求版本、基线、候选commit/产物digest、配置和依赖锁文件，避免审的是A、测的是B、发的是C。需求本身含糊时先澄清，例如“夜间模式”到底包含配色、设置开关、系统偏好跟随还是刷新后保持；不能让实现者写出的测试反过来定义产品承诺。

随后做双向检查：每个需求都有实现与证据，每一块diff都有需求或必要的支撑理由。测试、文档和兼容性调整可以是合理支撑改动，但要能解释联系；文件名在白名单里也不证明所有新增行为都属于需求。必要时看完整函数、调用方、构建入口与生成文件，不能只看变更摘要或统计数字。

| 检查层 | 独立依据与动作 | 能说明什么、还缺什么 |
| --- | --- | --- |
| 需求与范围 | 原始验收项、已批准的范围；逐hunk核对新增、删除、重命名、配置和依赖 | 揭示漏做与夹带；只看路径不能证明语义范围完整 |
| 行为契约 | 既有客户端/格式契约、人工确认的golden case、错误与边界输入 | 检查正确性与兼容性；不能让新实现自动生成唯一“标准答案” |
| 测试有效性 | 检查断言、测试收集、skip/xfail、mock替代位置；让明确错误的反例挑战断言 | 验证测试能否抓住相关缺陷；全绿、覆盖率和反例被抓都不是完整证明 |
| 集成与用户路径 | 在获授权环境走真实入口、协议/服务和UI操作，核对副作用与错误恢复 | 证明特定版本/配置下的链路；未执行时写not_run，mock结果不能补位 |
| 发布与回退 | 构建/打包清单、发布说明、未完成内容去向、回滚版本与恢复读回 | 防止审测发对象脱节；回退代码不等于撤销数据、客户端或外部副作用 |

独立性既有“证据从哪里来”，也有“谁有权做最终判断”。实现者可以准备复现和资料，独立reviewer应审查假设与反例；涉及协议、依赖或数据迁移时请相应owner参与。另换一个模型或会话能减少上下文锚定，但仍可能共享盲点，不能代替职责与可信依据的分离。

Google Engineering Practices固定`3bb3ec25b3b0199f4940b1aa75f0ac5c5753301c`的review指南要求检查功能是否满足用户、测试是否有用及代码坏了会不会失败，并提醒UI影响往往需要实际查看行为。其Small CLs强调自洽的单一改动及相关测试，不是机械限定行数；Standard of Code Review也不要求追求不存在的完美。本文据此按风险选择证据，不把某团队的工作习惯升级成所有项目必须照搬的流程。

### “只改夜间模式”却夹带协议和依赖：先暂停当前发布结论

原创例子约定本次只增加夜间配色，同时保持浅色行为、V1主题消息与依赖版本。最终产品仍需浏览器交互和真实服务链路证据。作者说明写“Night palette only”，附带的两项检查只验证浅色结果有两个key、消息返回dict。

在专属临时目录生成baseline和mixed候选后，实际运行`git diff --no-index --no-ext-diff --no-textconv --no-color -- base mixed`。得到5个变化路径，下面按真实内容映射；这些代码、版本名和数据全部是原创合成输入，`synthetic-transport`不是被安装或调用的真实依赖。

| 实际diff | 与声明的关系 | 判断及下一步 |
| --- | --- | --- |
| `src/theme.py`：dark返回背景`#121212`、文字`#eeeeee`，light保留原配色 | 对应夜间配色 | 用固定light/dark期望值检查；仍未证明真实设置开关、视觉效果或刷新行为 |
| `src/protocol.py`：`{version:1, theme:mode}`变成`{version:2, appearance:{mode:mode}}` | 未声明的协议变化 | 本地旧V1消费者拒绝新envelope；需要独立范围决定、兼容方案与协议owner审查 |
| `package.json`：依赖`1.0.0 → 2.0.0` | 未声明的依赖升级 | 核对必要性、变更内容、许可证/供应链与构建兼容；版本号本身不是已证实故障 |
| `package-lock.json`：解析版本同样升到`2.0.0` | 与升级关联，不能漏看lock文件 | 声明清单与锁文件都要核对；没有安装或执行该依赖，不能补造升级测试结果 |
| `src/unfinished.py`：新增未完成导出实验，虽写着`ENABLED=False`仍在候选目录 | 未声明的额外产物 | 默认关闭不证明隔离；应拆出并检查最终产物、入口、导入与配置引用 |

本例不能因为“测试绿了”就发，也不能只补几行Release Notes把未授权范围变成已授权。先请作者解释协议与升级是否确为夜间模式所需：无关则拆成独立变更；确有必要则由需求/接口/依赖owner批准扩展范围，补齐证据并重审新的head。保留原始diff和未完成工作，避免直接reset或覆盖别人的内容。

隔离也要读回验证：在本例中从baseline加上已确认的theme变更构造clean候选，协议、manifest和lock恢复为原值；未声明部分保留成候选目录外的`deferred-unapproved.patch`。clean产物清单只含baseline的4个文件，没有unfinished模块，也没有该patch。这个检查只证明本例产物没带这些文件；真实feature flag还要排查启动副作用、导入、后台任务、打包与默认配置，不能仅凭`false`认定安全。

### 原创实跑：相同绿色检查，三个不同结论

本地模块只做配色返回与消息编码；没有浏览器、真实服务、模型或收费API。固定palette期望和V1消费者来自候选之外的控制数据，未按新协议“同步修改测试答案”。下面是 **2026-09-16实际运行**的结果；“2/2绿”只指那两项本地shape检查，不是项目CI状态。

| 候选 | 两项现有检查 | 独立检查与反例 | 本次结论 |
| --- | --- | --- | --- |
| mixed | 2/2绿 | 5个变化路径中4个未映射；V1消费者失败、依赖改变、产物夹带、说明遗漏 | reject_scope，拒绝当前范围 |
| broken | 2/2绿 | 只改theme文件，但dark仍返回light颜色；固定dark断言失败 | reject_local_acceptance，路径合规仍未满足需求 |
| clean | 2/2绿 | 配色、旧消费者、依赖保留、产物、说明、回滚点及限制披露7项本地检查均通过 | await_real_evidence，仍不批准发布 |

三个候选使用**同一份两断言探针**：要求dark配色准确、V1 envelope保持不变。mixed和broken分别真实退出1、各1个assertion failure/0 errors；clean退出0、两项通过。它们是刻意构造的协议变更和缺失dark分支反例，不是发现了两个真实产品事故，也不是测试框架报错。30个回归测试进一步检查遗漏证据、虚假“已集成”说明、review快照漂移、依赖/产物差异和回滚失败边界，均已通过。

验收结果必须绑定被检查的候选与需求版本。本例记录candidate、baseline与contract的digest，拒绝候选hash不匹配；未执行的真实检查由runner固定记录为`not_run`，作者说明声称“已通过”不会改变它。下面是实际使用的分流函数，依赖固定的7项LOCAL_CHECKS和2项REAL_CHECKS清单；缺项也不能靠空集合的“全部通过”放行。

```python
def choose_verdict(unmapped, checks, real):
    if unmapped:
        return 'reject_scope'
    if set(checks) != LOCAL_CHECKS or any(value is not True for value in checks.values()):
        return 'reject_local_acceptance'
    if set(real) != REAL_CHECKS or any(status != 'pass' for status in real.values()):
        return 'await_real_evidence'
    return 'ready_for_release_review'
```

返回ready也只是进入发布评审，不是取得执行权限。本例三个报告的`release_approved`均为false；`browser_e2e`和`real_service_integration`都没有运行。模拟接口演示只能说明本地编码/消费契约，不能证明真实服务能访问、认证可用、网络超时处理正确或实际UI可用。

### 发布说明与回滚点应当能对应具体产物

clean候选的交接应写清：本次仅有配色逻辑；协议V1与依赖未改；本地验证命令及结果；浏览器/服务验证未执行；协议V2、依赖升级和导出实验另行保留、未包含在本次产物；候选与baseline的digest以及恢复步骤。未完成内容既不能写成“已完成”，也不能藏在默认关闭的代码或含糊的“优化若干问题”里。

本例确实在临时clean目录做了回滚演练：先确认目标仍等于已检查的clean digest、备份内容等于已登记baseline digest，再顺序恢复本地文件；读回内容等于baseline，`git diff --no-index base clean`退出0且无输出。之前非空diff的退出1是Git文档规定的差异信号，不是命令故障。本次Git实际版本为`2.53.0.vfs.0.7`，命令与patch均留证。

这个恢复不是原子事务，也不是对外部写者的CAS，更没有演练数据库、真实部署或远端状态恢复。Git v2.46.0文档说明`git revert`用新的commit反转既有patch；这不能自动撤销已发出的消息、完成的数据迁移或已升级客户端。真实发布要说明不能直接回退的部分、兼容窗口、备份可恢复性与失败时的责任人，不能以“有旧commit”替代恢复验证。

### 按变更风险选择合理方案

- 对低风险、范围清晰的改动，可采用独立reviewer加固定契约/反例与针对性手工检查；反馈快、维护成本低，但不适合用来证明跨服务协议和数据迁移的正确性。
- 对混有协议、依赖或状态迁移的改动，应先拆出自洽变更或批准范围扩展，再做兼容矩阵、真实集成与发布/回滚演练；证据更强但环境和协调成本更高。无需把每个纯文档修改都升级成完整系统演练。

证据不足的部分按风险阻止相应交付或明确缩减经批准的承诺。不要伪造结果，也不要用“独立验收”要求无关的完美；目标是有依据地判断这份具体变更是否满足当前承诺、是否可以进入下一道门禁。

### 常见误区与追问

- **“测试全绿就测到了需求。”** 检查实际断言和收集结果，给每个验收项找证据，再用会破坏该需求的反例挑战测试。
- **“mock集成成功，真实链路一定成功。”** 明确替代了哪一段；真实认证、网络、协议版本、服务状态和UI路径仍需相应环境证据。
- **“更新发布说明就可以接受额外改动。”** 说明补齐不等于范围获批，更不等于额外风险已经验证。
- **追问：协议升级确实是夜间模式所需怎么办？** 先给出依赖关系与兼容方案，由相关owner确认扩展范围；更新需求映射和发布说明，重审新head，而非假装仍是原来的一项UI改动。
- **追问：真实服务当前不可访问，能不能交付？** 本地证据可以交接，但把真实链路标为未执行并说明影响；若它是发布必需条件，就停在待验证状态，由有权限的人补齐，不用假响应冒充通过。
- **追问：review后又改了一行，旧结果还算数吗？** 核对新diff及影响，重新绑定候选；至少复核受影响的需求、兼容性和产物，不能让旧SHA的批准覆盖未审内容。

相关题：[执行后验证](./engineering-0010-execute-verify-feedback-loop.md)、[抗泄漏评估](./engineering-0014-agent-benchmark-leakage-resistant-evaluation.md)、[协作规则契约](./engineering-0036-agent-rules-executable-contracts.md)。本题聚焦一次研发变更的独立验收与发布边界。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定`5a933d287dd5074cc1543cb849146f3261d47521`：[vibe-3](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-3.html)、[vibe-6](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-6.html)、[vibe-9](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-9.html)、[interview-7](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/interview-7.html)。仅学习线索；未搬运AGPL正文、代码、图片，课程演示成本数字未当作实测。
- Google Engineering Practices，固定`3bb3ec25b3b0199f4940b1aa75f0ac5c5753301c`：[What to look for in a code review](https://github.com/google/eng-practices/blob/3bb3ec25b3b0199f4940b1aa75f0ac5c5753301c/review/reviewer/looking-for.md#L16-L79)，功能、UI与测试有效性；[Small CLs](https://github.com/google/eng-practices/blob/3bb3ec25b3b0199f4940b1aa75f0ac5c5753301c/review/developer/small-cls.md#L42-L73)，自洽的单一变更；[The Standard of Code Review](https://github.com/google/eng-practices/blob/3bb3ec25b3b0199f4940b1aa75f0ac5c5753301c/review/reviewer/standard.md)，有依据地改善代码而非追求完美。
- Git固定版本v2.46.0：[git-diff文档](https://github.com/git/git/blob/v2.46.0/Documentation/git-diff.txt#L34-L41)，no-index比较与退出码；[git-revert文档](https://github.com/git/git/blob/v2.46.0/Documentation/git-revert.txt#L16-L31)，反转patch与新commit。仅作命令语义依据，未将源码文档冒充生产恢复实验。
