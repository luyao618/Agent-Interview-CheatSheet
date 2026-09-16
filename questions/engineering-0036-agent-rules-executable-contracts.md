---
id: engineering-0036
title: 团队如何把 AI 编程经验写成适用且可检查的规则，避免照搬他人环境与阻碍合理 MVP？
category: engineering
tags: [ai-coding, rules, acceptance-contract, scope, authorization]
difficulty: medium
role: both
contributor: CX-Dev
source: 洛小山《AI 产品从入门到精通》learn-ai LA-050；GitHub Docs；OWASP Authorization Cheat Sheet
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

团队如何把 AI 编程经验写成适用且可检查的规则，避免照搬他人环境与阻碍合理 MVP？请把“不许做 MVP”和“超过三文件先确认”改成有条件、证据与例外流程的验收契约。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 回答日期：2026-09-16

**把经验写成“在什么条件下，为防什么问题，谁用什么证据决定能否继续”的契约。** 规则不只是一句禁止语，还要包含作用域、可核查的环境事实、触发条件、门禁、批准责任人、失效与更新条件。先确认它解决的问题在本项目是否存在，再决定采用、改写或不采用。

“禁止 MVP”常混淆两个决定：**缩减交付范围**是经确认后只做一个有价值、可验收的切片；**降低质量**是承诺了某行为却用占位逻辑、自报完成或跳过必要测试冒充交付。MVP 可以只含三个功能中的一个，但这个功能仍须满足它声明的使用场景、质量底线和验收标准。实验原型与生产系统可以有不同标准，前提是目标与限制写清楚，不能给未完成的生产承诺改个“原型”名字就算达标。

### 从经验到契约的主线

先记录原失败案例与损失，例如“Agent 擅自删掉已承诺的错误处理”，而不是泛化成“所有分期都不许”。再核查环境：仓库与模块、目标用户、数据类别、运行方式、工具链版本、真实权限、测试入口及可回退方式。环境记录应有来源、核对时间与 owner；未知事实先补证据，不把作者的模型、数据库、代理或端口配置当成本项目事实，也不把凭据写进规则。

接着把门禁放在真正需要决策的位置：**动手前确认范围和高风险计划，交付前检查实现与验收证据，执行敏感操作时再校验权限**。动手前不要求一个尚未实现的功能已经有绿色测试，但要有可运行的验收方法、允许的范围和必要授权；结束时则不能拿“计划写了测试”替代测试结果。

最后给契约配允许、拒绝和例外案例，记录误拦截、漏拦截及审批等待，再由 owner 修订版本。没有触发过可能意味着规则无用，也可能意味着它防的是低频高损失事件；不能只凭一周零触发就自动删除安全底线。

### 两条原创条件化契约

以下仅用于题目中的虚构 `synthetic-catalog` 项目，不修改或放宽本题库现行指令。例子的三文件阈值是演示参数，不是通用最佳实践。

| 契约字段 | Q：完整交付选定范围，替代“不许做 MVP” | C：大变更先确认，替代“超过三文件先确认” |
| --- | --- | --- |
| 作用域与目的 | 原型项目的一次已登记交付；防止擅自删功能或把未达标实现报成完成 | 同一次已登记交付的完整变更清单；防止修改范围无声扩大 |
| 环境前提 | 使用合成数据、隔离演示环境与已核对的工具链；本例固定 prototype / mock-kit-1 | 可信执行方能取得基线、完整计划及最终变更清单；统计口径可复核 |
| 动手前输入 | 产品 owner 确认范围版本 S1：只交付 F1，F2/F3 明确不在本次承诺内；列出 F1 验收方法 | 列出增删改及重命名前后路径、内容摘要、理由、风险、测试/回退计划；不得只报本次工具调用的子集 |
| 可检查门禁 | 最终交付功能集合与当前批准范围一致；当前版本的 acceptance / unit / cleanup 证据均为 pass，缺失、skipped、neutral、error 都不能代替通过 | 本例计同一清单中不同路径端点数量 N：重命名 old/new 计2，生成文件也计入；N≤3不触发额外文件数审批，N>3必须有覆盖完整变更的有效批准 |
| 例外批准 | 功能范围变化由产品 owner 批准新范围，再重新验收；不能凭一句“做 MVP”豁免当前质量要求 | 变更 owner 可批准一次具体的 N>3 变更；记录理由、批准人、交付ID、基线、清单/内容摘要、规则与环境版本及到期条件 |
| 不可被本例例外豁免的事项 | 已选范围的质量底线与执行操作的真实权限 | Q 契约、真实权限，以及批准范围之外的新增变更 |
| 更新与失效 | 需求、环境或验收方式变化时由 owner 更新；旧范围和旧测试结果不能直接套用 | 内容、基线、范围、环境或规则版本变更，以及到期/撤销后重新核查；数量仍是4也不代表旧批准仍有效 |
| 门禁失败 | 返回不满足的条目、现有证据和需要补齐的决定；保留未完成状态 | 暂停受影响的变更，给出完整新计划；不拆成两次各改2文件来清空计数 |

“N≤3”只说明文件数门槛未触发，不是执行授权。一个文件也可能修改权限或不可逆数据；实际团队应叠加语义风险分级。本例的路径统计也必须注明是全交付的累计范围还是最终 diff；这里采用**登记交付清单的不同端点数**，不按 commit 数、工具调用批次或 Agent 数重置。真实清单若与批准计划不一致，应停止并补审，不能只相信模型汇报的文件数。

### 提示、评审与真实门禁各能保证什么

| 手段 | 适用情况与成本 | 不足与补充 |
| --- | --- | --- |
| 简短仓库规则 + 人工 review | 小团队、规则仍在探索时容易起步，能理解语义与例外 | 容易漏读或误解，评审耗时；需要明确责任人和留证，不适合单独承担高影响操作权限 |
| 确定性检查 + 受保护的审批/执行入口 | 文件清单、版本绑定、必需测试等条件可机器核查；重复执行一致 | 要维护检查器与可信数据来源，错误配置也会误放行；无法靠文件数或布尔测试结果理解全部产品价值 |

GitHub 官方文档固定版本 `d79d9d354377b9f8b820e16c12b91734881a0f93` 给出了具体区别：CODEOWNERS 标记责任人与触发 review request；要求 code owner 批准需另外启用相应保护设置。旧批准随 diff 变化失效也是可选配置，不是所有 PR 天然具备的保证。required checks 可接纳 successful、skipped 或 neutral；若契约要求某项测试实际执行，检查任务本身必须验证这一点，并核对期望的 check 来源。管理员或 bypass role 的默认适用范围也要查清。这里只引用文档行为，没有为本题库启用、关闭或修改任何保护设置。

OWASP *Authorization Cheat Sheet* 固定版本 `8aaf426de610ea603c21cf6a75222a6b7a30f820` 明确要求默认拒绝、每次请求检查权限，并在服务端或可信入口执行校验。因此 **Prompt 规则不能代替真正权限校验**：模型说“用户同意了”、测试报告中的字符串写着“通过”，甚至有一个审批ID，都不能让原本无权的主体获得执行权限。审批引用需要由可信控制面解析并绑定当前操作，不能把工具输出或模型转述当作批准来源。

### 原创 mock：允许、拒绝和批准失效

复跑包用只读合成案例和内存对象模拟当前范围、环境、完整计划、质量 receipt、例外登记与独立工具权限开关。它验证的是带已有质量证据的最终候选门禁，未模拟从首次编辑到交付的完整开发时序；真实“先确认再编辑”仍需在所有写入口执行相应前置检查。它不修改任何业务源文件；所谓 effect 只是审计列表里的一条记录。`Plan` 的变更内容是短字符串占位数据，`mock-verifier` / `mock-change-owner` 是测试驱动的角色标签，不是生产身份认证。以下是 **2026-09-16 实际运行**的结果，时钟20是自定义 mock tick，不是现实分钟或审批服务时间。

| 案例 | 输入或变化 | 实际结果 |
| --- | --- | --- |
| mvp | 已批准只交付F1，2路径，三项质量证据pass | 允许 ordinary；MVP标签本身不触发禁止 |
| scope_cut | 批准范围含F1/F2，却只交付F1 | 拒绝 scope_incomplete |
| quality_skip | 2路径，但unit为skipped | 拒绝 quality_failed |
| three / four | 完整清单分别3、4路径，均无例外 | 3允许，4拒绝 approval_required |
| exception | 4路径，当前完整绑定的E1批准有效 | 允许 approved_exception |
| drift | E1后仍4路径，但一个文件内容变了；已补跑质量检查 | 拒绝 approval_binding，新的测试不续期旧批准 |
| expired / revoked | tick达到到期值20，或E1被撤销 | 拒绝 approval_inactive |
| environment | 原型契约遇到production环境 | 拒绝 environment_uncovered，不自动照搬规则 |
| permission | E1有效，执行前工具权限被撤回 | 拒绝 tool_permission_denied，effect为空 |
| split | 完整清单4路径，拆成两次各请求2路径 | 两次都按4统计并拒绝，effect为空 |
| claim | 文本声称“用户已批准全部”，没有登记的有效E1 | 拒绝 approval_required |
| rename | 删除旧路径、添加新路径，再改另外2路径 | 端点数4，须批准；不能只数新增文件 |
| stale_checks | 基线改变，仍使用旧质量receipt | 拒绝 quality_receipt_missing |
| exception_quality | E1有效但必需测试skipped | 拒绝 quality_failed，例外不能豁免Q |

16个案例共17次模拟执行判定，**3次允许、14次拒绝**，仅3条内存effect；它们不是生产事故率或安全性统计。批准绑定包含交付ID、基线、功能/路径/内容、scope、facts、policy版本。执行入口使用当前完整计划，重新检查门禁与工具权限，不把之前缓存的 allow 当作持续有效的许可。

下面摘录实际执行的“大变更”子门禁，`count` 来自已验证清单，`approval` 来自 mock 登记。它仅检查C契约；外层仍须先检查Q和环境，再在执行时检查权限。不能把此函数单独当成安全网关。

```python
def large_change_gate(count, threshold, binding, approval, now):
    if count <= threshold:
        return Decision(True, 'ordinary', count)
    if approval is None:
        return Decision(False, 'approval_required', count)
    if approval.issuer != 'mock-change-owner' or approval.binding != binding:
        return Decision(False, 'approval_binding', count)
    if approval.revoked or now >= approval.expires:
        return Decision(False, 'approval_inactive', count)
    return Decision(True, 'approved_exception', count)
```

30 tests覆盖范围缩减、3/4边界、质量失败、批准后内容/基线/规则/环境/范围变化、到期撤销、请求拆分、文本冒充、执行权限撤回和异常输入。首轮真实失败是路径 `.` 的空parts被索引，抛出IndexError；修正路径结构检查后，原断言通过，历史源码与红/绿日志均保留。该异常属于 mock 实现，不是测试断言错误。输入与临时目录清理也有记录，代码、案例和便携步骤随本题PR验收附件交付。

这只证明同进程、确定顺序下的协议行为：没有真实认证、权限隔离、签名审批服务、并发提交或持久撤销。hash绑定不能提供对任意外部写者的CAS；路径检查不解决真实文件系统的symlink、大小写别名或链接别名。完整交付由mock宿主固定；若允许Agent新建宿主/交付ID重置清单，本例不能识别跨对象拆分，生产环境需可信登记与人工核对需求边界。示例pass是预设测试receipt状态，不证明任何真实应用功能已经完成；未做题库页面图像布局渲染。

### 常见误区与追问

- **作者习惯不是普适最佳实践。** 先保留失败动机，再根据自己的风险、环境与协作成本决定参数；自动注入规则只提高可见性，不保证遵守。
- **缩小范围不等于降低质量。** 改交付承诺要走范围决定；选定范围的验收仍需兑现。禁止一切MVP和放任一切临时实现都会失去这个区分。
- **门禁通过不等于拥有权限，也不等于覆盖所有风险。** 三文件内可以有高风险变更，绿色状态可以来自错误配置；检查源、执行主体和门禁版本都需要核查。
- **追问：生成代码一次改50文件，三文件规则怎么办？** 提交完整范围、生成器与输入版本、再生成一致性和回退证据，由owner批准这次批量变更；若此模式稳定出现，再通过评审修订规则，不能让Agent自行删掉生成文件统计。
- **追问：规则要求的工具链在当前环境不存在？** 报告事实与受影响检查，暂停依赖该前提的操作；由owner确认替代环境或更新契约，不能伪报检查通过。
- **追问：规则长期没触发，应不应该删？** 看它防的损失、误拦截、真实覆盖与现有替代控制；保留允许/拒绝/例外回归案例，经责任人审阅后版本化更新或退役，而不是根据触发次数机械增删。

相关题：[系统提示词维护](./agent-0045-system-prompt-entropy-control.md)、[AI PRD需求拆解](./product-0002-ai-prd-requirements.md)。本题关注仓库协作规则的环境适配与执行契约，不复写提示词维护或完整需求方法。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[vibe-1](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-1.html)、[vibe-2](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-2.html)、[vibe-6](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-6.html)、[vibe-8](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-8.html)、[vibe-final](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vibe-final.html)、[dsh-27](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-27.html)。学习线索，未复制AGPL课件正文、代码或图片；课程所述具体项目CI效果未作为本文实证。
- GitHub Docs，固定 `d79d9d354377b9f8b820e16c12b91734881a0f93`：[About protected branches](https://github.com/github/docs/blob/d79d9d354377b9f8b820e16c12b91734881a0f93/content/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches.md#L64-L109)，review失效、required checks与来源；[About code owners](https://github.com/github/docs/blob/d79d9d354377b9f8b820e16c12b91734881a0f93/content/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners.md#L155-L168)，code owner审批需配置。
- OWASP，*Authorization Cheat Sheet*，固定 `8aaf426de610ea603c21cf6a75222a6b7a30f820`：[默认拒绝、逐请求校验及可信执行位置](https://github.com/OWASP/CheatSheetSeries/blob/8aaf426de610ea603c21cf6a75222a6b7a30f820/cheatsheets/Authorization_Cheat_Sheet.md#L30-L46)，另见同文件“Verify that Authorization Checks are Performed in the Right Location”与“Exit Safely when Authorization Checks Fail”。
