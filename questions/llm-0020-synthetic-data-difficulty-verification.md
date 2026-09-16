---
id: llm-0020
title: 用强弱模型筛选合成训练题时，如何控制难度并证明数据有效而非筛选器偏好？
category: llm
tags: [synthetic-data, curriculum, verifier, contamination, evaluation]
difficulty: hard
role: engineer
contributor: CX-Dev
source: 洛小山《AI 产品从入门到精通》learn-ai LA-049；Autodata；Self-Instruct
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

用强弱模型筛选合成训练题时，如何控制难度并证明数据有效而非筛选器偏好？请给出“强能解、弱不能解”的筛选表，并解释强模型答错时怎样处理。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 回答日期：2026-09-16

**强弱差异是相对于固定 solver 配置的难度代理，训练价值要靠独立下游实验验证。** 一条可靠的主线是：先锁定目标能力与验收规则，再出题和独立验题，重复试解后分层，做污染检查与多样性配额，冻结数据及训练方案，最后在未参与筛选的任务上比较训练后的模型。筛选分数上升，只说明系统更擅长通过这个筛选器。

### 谁负责什么，谁不能自己证明自己

| 角色 | 输入与产物 | 不能替代的证据 |
| --- | --- | --- |
| Challenger | 根据允许的资料与目标能力提出题目、参考解和候选 rubric；接收失败反馈改题 | 自己写出的参考答案与 rubric 不是天然真值；不能为了过关修改 solver 或放松验收规则 |
| Weak solver | 在固定模型版本、上下文、工具权限、采样参数和推理预算下多次作答 | 一次失败不能证明不会；timeout、拒答和格式损坏要与答案错误分开 |
| Strong solver | 在声明的更强配置下给出可检查的解，帮助估计任务是否可解 | 参数更多、推理更长或自报正确都不是答案证明；也可能在特定题型上弱于 weak |
| Verifier / judge | 依据题目约束、独立真值或冻结的 rubric，验证答案与题目质量，输出通过、失败或不确定 | 不能只比较两模型是否同意；换一个角色名或模型名不自动获得独立性 |

算术或代码任务优先用精确计算、性质断言、执行结果或独立测试，但有限测试也不能证明任意程序正确。开放题需要核对资料、前提、可接受的多种答案及 rubric 覆盖；无法可靠判断时进入复核队列。**强模型能答不证明题目有正确答案**：它可能对缺条件、相互矛盾或有多解的题给出很自信的单一回答。即使最终答案正确，也不能顺带把未验证的长推理当成正确 SFT 标签。

### 论文机制、固定代码与工程建议分开说

Kulikov 等人的 *Autodata* 固定论文 `2606.25996v3`，§2.1 / 图2 描述 Agentic Self-Instruct：主 Agent 调用 Challenger、weak/strong solver 和 verifier，把判断反馈给下一轮出题。weak 与 strong 甚至可以是同一模型采用不同 inference compute、scaffolding 或额外信息，并非固定的大小模型配对。论文中的 LLM judge 与本文的精确算术 oracle 也不是同一验证机制。

它没有给所有领域规定一个通用“差距越大越好”的门槛。§3.1 的 CS 任务用分数与 gap 阈值；§3.2 的法律任务采用分析 rollout 模式及 GRPO 适用性的 judge，弱模型大量全零时会改成更可学习的题。§6 还记录了通过提示弱模型“表现得弱”来作弊、题目过度依赖论文实验细节等问题，并把更完整的数据集级多样性分析列为后续方向。正文与附录图7的 CS 阈值也不完全相同，不能据此拼成一个声称已复现的作者运行配置。本次核对的是论文与附录；所读论文未给出可据此核查的 Autodata 作者实现仓库链接，第三方同名项目不作为作者源码证据。

一个可核查的去重例子是 Wang 等人 Self-Instruct 作者仓库固定提交 `0b26ccaa415992100fa32df62d41b994cf928e23`：`self_instruct/bootstrap_instructions.py:152、:195–206` 用 ROUGE-L F1 与 seed / 已生成 instruction 比较，最大相似度 **大于 0.7** 时跳过。它是文本相似性过滤，既没有在该处比对隐藏 test，也不证明语义多样性或无污染；不能把这段代码描述成 Autodata 的实现。本题只静态阅读作者代码，不执行它。

课程固定版本用于确定学习线索；“难度差确保最大训练价值”的表述不作为本题结论。以下预算、比例和 mock 规则是原创教学设定，不是论文实测收益。

### 难度怎样控制，什么时候不该只挑差距大的题

先固定 solver 配置和每题尝试次数，用 verifier 的结果估计各自成功率。给比例写清分母，保留失败尝试；多次采样仍有相关性，小样本比例不等于能力参数。强模型的额外信息也要标出，否则 gap 可能只是信息不对称。阈值只能在开发集调整，不能根据最终 test 的分数回调。

| 方案 | 适用条件与代价 | 不适用场景 |
| --- | --- | --- |
| 严格差异筛选：strong 稳定通过、weak 多数失败 | 有可靠 verifier、想补目标模型薄弱项时直观；需要重复采样和复核，容易过度集中在一个 solver 的盲点 | 全是 weak 零成功、知识缺失或格式刁钻的题时，不一定有可用的 RL 学习信号 |
| 可学习性分层与混合：保留基础、过渡、挑战桶，再设能力配额 | 可覆盖能力谱并检查遗忘；需要设计混合比例、验证 rollout 方差及下游效果，成本更高 | 没有可靠标签或真实目标分布时，复杂分桶仍可能只优化 judge 偏好 |

对于 SFT，weak 暂时完全不会的题也可能因高质量、可理解的示范而有用；对于依赖组内相对 reward 的 RL，一组 rollout 全部同分会缺少组内区分信号。二者都不能从“难”直接推出“值得训练”。反向题——weak 能做而 strong 失败——应检查专业域、工具权限和 verifier，而不是硬塞进大小模型排序。

污染和多样性是另外两道门：先按来源文档、原始任务或衍生题簇划分 train/dev/test，再生成变体；使用文本指纹、语义近邻和来源谱系识别重复与跨集衍生，抽查无法自动判断的部分。改变 ID、措辞或数字不必然成为新任务。配额应基于可信的能力分类与来源记录，不能只相信 Challenger 自报“新题型”。隐藏 test 的内容由评测方保管，去污染服务只返回必要的重合结果；没有命中已知指纹也不证明模型预训练没见过该题。

### 原创示例：强答错、timeout 和重复题都留下记录

本例是固定回复表的本地 mock，没有生成式 Challenger、模型训练或付费调用。题目采用仅支持 `sum`、`max`、`count_even` 的整数 DSL；oracle 从运算和整数列表重新计算，不读取 solver 的 `claims_correct`。题目文本可以由 DSL 确定生成；不声称该 oracle 能判断任意自然语言题。

筛选设定：每个可试解候选各读 **4 条 weak / 4 条 strong 回复**，全部有效时，`strong >= 3` 且 `weak <= 1` 进入 gap 桶；每个运算能力最多选一题。候选按 C01–C14 的固定顺序检查，重合、错误 reference 和不支持的题在试解前拒绝。下表数值是 **2026-09-16 实际执行原创脚本得到的正确次数 / 4**；`—` 表示没有调用，不能当作 0 分。

| 候选与输入 | oracle 真值 | weak | strong | 判断 |
| --- | --- | --- | --- | --- |
| C01：sum `[2,3]` | 5 | 4/4 | 4/4 | easy，留基础桶，本策略不选 |
| C02：sum `[-3,7,2]` | 6 | 1/4 | 3/4 | gap，选入 |
| C03：count_even `[-3,0,2,5]` | 2 | 1/4 | 4/4 | gap，选入 |
| C04：sum `[8,-3,2]` | 7 | 0/4 | 0/4 | strong 不可靠；四次都自报正确但答 6 |
| C05：max `[-2,1,6]` | 6 | 0/4 | 0/4 | 两方均失败，复核或改题 |
| C06：max `[0,4,9]` | 9 | 4/4 | 0/4 | reverse，检查配置或领域差异 |
| C07：sum `[-3,2,7]` | 6 | — | — | 与 C02 在此 DSL 下等价，改 ID / 排序仍重复 |
| C08：sum `[1,9]` | 10 | — | — | 来源组命中预登记保护集合 |
| C09：count_even `[7,4,2]` | 2 | — | — | 新来源名仍命中保留题的运算指纹 |
| C10：divide `[1,0]` | 无受支持定义 | — | — | DSL 不支持，不猜答案 |
| C11：max `[-1,5]` | 5 | 0 正确、3 错、1 timeout | 4/4 | incomplete，不能据此宣称 weak 失败 4 次 |
| C12：max `[3,5]`，Challenger reference=3 | 5 | — | — | 错误 reference，在 solver 自证前拒绝 |
| C13：sum `[-4,8,3]` | 7 | 0/4 | 4/4 | gap，但 sum 配额已被 C02 使用 |
| C14：max `[1,4]` | 4 | 2/4 | 3/4 | middle，供另一混合策略考虑 |

C02 的 weak 回复为 `[5,5,5,6]`，strong 为 `[6,6,6,7]`；C04 两方都回复 `[6,6,6,6]`。用强模型的自报或共同答案作真值，会把 C04 的一致错误掩盖掉。C11 的 timeout 是 mock 主动抛出的有限故障，日志保留 `correct=null`；没有实际远端调用或遗留任务。

以下是复跑包 `selection_fixture.py` 中实际执行的分层函数；完整准入还包括前置验题/去重、有效回复计数和后置能力配额，不能单独调用这个函数就宣称数据可训练。

```python
def band(weak, strong, complete):
    if not complete:
        return 'incomplete'
    if strong < 3:
        return 'reverse' if weak >= 3 else 'strong_unreliable'
    if weak <= 1:
        return 'gap'
    return 'easy' if weak == 4 else 'middle'
```

实际产物选中 **C02、C03**：14 条提案枚举，9 个可试解候选 × 8 = **72 条 solver 回复读取**，含 1 次 timeout；5 个前置拒绝候选不消耗 solver 回复预算。枚举完、提案预算耗尽或回复预算耗尽即停止，不无限重试凑满配额。中途预算不足的候选也标为 incomplete。这里的提案数和回复读取数不是 Token、费用或训练 FLOPs。

### 怎样把“筛选成功”与“数据有效”分开验证

正式实验至少比较原始训练混合、等预算随机合成数据、差异筛选数据；固定目标模型起点、训练 token / 计算预算、优化器和推理设置，重复训练种子，报告均值、区间和各能力桶的退化，另列数据生成与筛选成本。用开发集选择配方后，冻结数据版本、checkpoint、评测协议，再测未用于选题、阈值、prompt 或 checkpoint 选择的保留集。最好加入不同来源与任务族、不同 evaluator 或人工审计的测试；同一个 Challenger/judge 生成并打分的留出题，不足以排除共同偏好。

Autodata v3 §3 的训练与下游实验是其论文证据；§4 的生成器优化指标与训练后能力不是同一个量。论文在特定配置下的结果不能替代你自己的目标分布评估。需要特别警惕只报筛选通过率、同源 judge 分数或每轮最优值，遗漏失败尝试与能力回退。

本 mock 的保留集接口仅演示操作纪律：预登记来源组和内容指纹；筛选方不读取保留集文件，冻结选中数据 hash 与一个预登记的 mock checkpoint 后才读取；数据、freeze receipt 或保留集 bytes 改动会拒绝，尝试失败后也不能在同一个 campaign 中重试。两个预设 mock checkpoint 各测 4 题，共 **8 条回复读取**，得到 baseline `3/4`、candidate_v1 `2/4`。这些回复事先写定，**没有训练出 candidate_v1**；两个分数既不证明训练退化，也不证明筛选无效，只演示保留集报分与筛选成绩是独立记录、不能互相代替。

复跑包含 **30 tests**、输入不变及目录清理检查。刻意植入“信任 strong 自报”和“timeout 当普通错答”的两个错误副本分别触发 3、4 个断言失败，修复版 30 tests 通过；这是两个预设缺陷被检出，不是 7 个真实系统漏洞。首轮测试把四个偶数误计为三个的测试自身错误也单独保留，没有算作实现缺陷。原始输入、完整回复、冻结记录、红/绿日志及便携步骤随本题 PR 的验收附件交付。

本例只识别有限 DSL 中的等价排列和已知来源/指纹，能力配额也只是运算类别代理。其同进程对象、hash 与文件检查不构成生产认证、权限隔离或对外部写者的 CAS；重新实例化可重新读取公开的合成 holdout，真实评测次数必须由独立服务持久记账。没有测真实模型质量、通用语义去重、并发与持久性，也未做题库页面图像布局渲染。

### 常见误区与追问

- **“强能解，所以参考解必然正确。”** 先验证题目本身及答案，再统计 strong 的成功率；自信、同意和可解性都不能由模型身份推出。
- **“难度越高，训练价值越大。”** 区分目标能力与偏题、SFT 示范与 RL 可学习信号，并检查下游迁移及遗忘。
- **“换个 judge 或给题换个 ID 就独立了。”** 共同资料、rubric、来源谱系及选择过程都可能泄漏；形式上的分离不足以排除相关偏差。
- **追问：weak 模型升级后要不要重筛？** 要重新校准相对难度，版本化 solver 配置与旧数据分层；用开发集改混合比例，避免边看最终 test 边改筛选规则。
- **追问：strong 和 verifier 都会错，怎么交付开放题？** 做来源核查、盲审与争议复核，验证 rubric 对已知好坏答案的区分能力；不确定样本留待人工审核，别强行变成高置信标签。
- **追问：通过率涨了但下游不涨，先查什么？** 分别消融答案质量、来源/能力覆盖和难度分层，检查评测污染、solver/judge 自偏好、训练预算及目标分布错位；把筛选器也作为需要验证的对象。

相关题：[标注质量](./engineering-0007-annotation-quality-eval.md)、[抗泄漏评估](./engineering-0014-agent-benchmark-leakage-resistant-evaluation.md)、[模拟用户可靠性](./engineering-0015-llm-user-simulator-quality.md)；本题聚焦合成训练题的相对难度与价值证据，不复写这些题的完整方案。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/11-4.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/11-4.html)、[slides/interview-5.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/interview-5.html)。仅作学习线索，未复制 AGPL 正文、代码或图片。
- Ilia Kulikov et al., *Autodata: An agentic data scientist to create high quality synthetic data*, 2026，固定 [arXiv:2606.25996v3](https://arxiv.org/html/2606.25996v3)：[§2.1 / 图2](https://arxiv.org/html/2606.25996v3#S2.SS1)、[§3.1 CS](https://arxiv.org/html/2606.25996v3#S3.SS1)、[§3.2 Legal](https://arxiv.org/html/2606.25996v3#S3.SS2)、[§6 限制与未来工作](https://arxiv.org/html/2606.25996v3#S6)。注意区别于 Ma 等人的同名 web 数据采集论文。
- Yizhong Wang et al., Self-Instruct 作者仓库，固定 `0b26ccaa415992100fa32df62d41b994cf928e23`：[README](https://github.com/yizhongw/self-instruct/blob/0b26ccaa415992100fa32df62d41b994cf928e23/README.md)、[bootstrap_instructions.py:152–206](https://github.com/yizhongw/self-instruct/blob/0b26ccaa415992100fa32df62d41b994cf928e23/self_instruct/bootstrap_instructions.py#L152-L206)。仅引用实际文本去重行为，不将其当作隐藏 test 污染检查或 Autodata 实现。
