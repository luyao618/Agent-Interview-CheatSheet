---
id: agent-0065
title: 如何把 Agent 工作流设计变成搜索问题，ADAS 与 AFlow 的探索、评估和停止条件如何不同？
category: agent
tags: [workflow-search, adas, aflow, mcts, evaluation, budget]
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

如何把 Agent 工作流设计变成搜索问题，ADAS 与 AFlow 的探索、评估和停止条件如何不同？请对 Plan→Execute 提出两种结构变体，定义验证、预算和停止规则，避免把最高训练分当作可部署的证明。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**把工作流表示成可执行、可版本化的候选，用独立评估获得反馈，在有限预算内提出和选择变体；停止搜索与验收通过是两件事。** 要先固定模型、任务、工具接口与评价规则，再讨论增删节点、连边、提示词或有界循环，否则无法判断改善来自结构还是换了实验条件。

[agent-0036](agent-0036-loop-vs-graph-engineering.md) 和 [agent-0026](agent-0026-multi-agent-collaboration-patterns.md) 讨论编排结构；本题讨论如何搜索结构。[agent-0064](agent-0064-automated-context-optimization.md) 比较上下文优化对象，这里进一步关注候选生成、搜索反馈和停止。

### 1. 分清工作流图与搜索树

工作流图的一条边表示一次任务中数据或控制如何流动，例如 Execute 的输出送给 Reflect。搜索树的一条边表示“从哪个旧候选提出了哪个新候选”，两个端点各是一整套工作流。增加一个反思节点不会自动让搜索树增加一层反思计算，两种图的语义不同。

搜索空间可以是固定组件的有限组合，也可以是受约束的程序：节点接口、参数、prompt、分支、循环上限和输出 schema 都属于候选的一部分。搜索器给出的是**提案**；能解析、能执行、取得正确结果、满足部署约束，需要分别检查。执行器、评价器、数据权限和资源预算应处于候选不能自行改写的控制面。

| 方案 | 适合的条件 | 代价与不适用情形 |
| --- | --- | --- |
| 手工设计或枚举有限模板 | 结构少、需求稳定、评估昂贵，容易逐项解释与复现 | 覆盖范围有限；不能把未枚举空间当作已排除 |
| Meta-agent 提案并积累 archive | 需要开放的代码组合与新结构，评估有明确反馈 | 新颖性与正确性依赖提案能力；失败调试、重复设计和评估噪声都要计费，不适合缺少可靠评价器时无界探索 |
| 带显式选择机制的搜索 | 候选很多，希望平衡复用高分设计与探索低分分支 | 需要管理候选池、得分和失败经验；不保证比手工或其它搜索更便宜，也不保证找到全局最优 |

### 2. 论文中的 ADAS 与 AFlow

ADAS 是 **Automated Design of Agentic Systems** 研究方向；Hu、Lu、Clune 的论文提出 **Meta Agent Search** 作为示例算法，不能将所有 ADAS 方法等同于这一实现。本文固定论文 `2408.08435v1`（2024-08-15）与 AFlow 论文 `2410.10762v1`（2024-10-14），不把课程出版/会议年份混作原始版本日期。

| 维度 | ADAS 论文的 Meta Agent Search（§3） | AFlow 论文（§3.2、§4、算法1） |
| --- | --- | --- |
| 表示 | meta-agent 在给定基础 API 上编写 `forward` 程序，表达调用、提示和控制流 | 代码表示的工作流；节点是调用动作，operator封装常见组合，边表达数据/控制关系 |
| 探索 | 参考不断增长的设计 archive，提出有趣的新设计；两次自反思检查新颖性/正确性，运行出错时最多三次修订 | MCTS **变体**：软混合概率选候选，LLM基于父候选和经验修改代码/提示/连接，不是始终贪心选最高分 |
| 评估 | 在目标域 validation 数据上评估性能及bootstrap置信区间，再把设计与指标加入archive | 每个生成工作流在validation上重复5次，记录均值/标准差；修改及相对父候选的成功/失败回写经验，全局分数用于后续选择 |
| 停止 | 到预设最大迭代数；不是新颖性满足就宣布任务完成 | top-k均分连续若干轮不再改善时早停，否则到最大轮数；这不是最优性证明 |

AFlow 的选择将均匀概率与分数权重混合：`P(i)=λ/n+(1−λ)·exp(α(s_i−s_max))/Σ_j exp(α(s_j−s_max))`。均匀项给候选保留探索概率，指数项偏向高分。其论文候选池包含优先的top-k与初始节点；不能把该公式替换成标准UCT，或凭“MCTS”三个字推导固定的访问次数/价值回传实现。论文中的经验回传包括修改、得分及相对父节点的成败，既记录改进也记录失败，不是低分就把历史证据删除。

### 3. 固定源码支持到哪里

以下只读核对实际分支，没有安装或执行作者代码；完整位置和hash随来源证据交付。论文算法、具体移植版本和本地mock要分开。

**ADAS：** 固定 `ShengranHu/ADAS@2702bee8fefda42255efc5be9f60e3bd3db96ae4` 的 `_mgsm/search.py` 中，`search:179` 按 `n_generation` 循环，默认30；`:187、:193、:197` 是初次提案与两次反思，`:205` 的 `debug_max` 默认3。常规评估后到 `:235` 追加archive，代码没有“必须超过已有最高分才追加”的判断。失败分支里的 `n -= 1` 不会回退Python的for迭代器，不能据此承诺补足成功代数。

该路径也不是严格的候选/分数回执协议：低分但非空的 `acc_list` 会触发debug；若最后一次在 `:217` 改了代码，循环结束后没有再次评估便可能在 `:227–235` 沿用前次结果。这里只指出静态可达的绑定风险，不宣称动态复现作者故障。真实系统应把代码hash、评估配置与结果绑定，不能仅信archive有fitness。`evaluate_forward_fn:296–299` 按SEARCHING_MODE选择打乱后的validation/test切片，主入口先search再evaluate；这不是对恶意代码的数据访问隔离，而且 `:282` 会执行生成代码。

**AFlow：** 固定 `FoundationAgents/AFlow@3f457218fc716093fe53f6df8a5d5e6379d66346` 的 `DataUtils.get_top_rounds:40–59` 先取分数靠前的sample个不同round，再把**已入选**的round1移到前面；不是无条件把初始节点补回候选池。`select_round:61–76` 将score乘100后调用混合概率并抽样，默认α=0.2、λ=0.3。`EvaluationUtils.evaluate_graph` 按可配置validation_rounds反复评估并保存结果，`ExperienceUtils.update_experience` 按是否优于父节点标记succeed，较差结果仍可留下记录。

外层 `Optimizer.optimize:80` 受max_rounds限制，启用check_convergence时才因早停退出；`ConvergenceUtils.check_convergence:68、:101` 默认top_k=3、z=0、连续5轮，判据是均值变化绝对值不超过误差阈值，默认z=0时要求零变化。但 `_optimize_graph:132` 内层是while True，解析或修改检查不通过可持续再生成，**最大外层轮数不能直接当作最大提案次数、费用或硬时限**。应另设调用与执行资源预算。

`Evaluator._get_data_path:63–65` 区分validate/test文件；然而该版 `Optimizer.test:238–251` 默认 `rounds=[1]`、读取workflows_test，并非自动测试搜索冠军，也没有本文mock的“一次test后禁止再搜”状态协议。不能把分开文件路径等同于未泄漏或强制冻结。

### 4. 原创 Plan→Execute 对照与预算

下面使用小型“整数加法”合成任务和固定答案表，只检验编排与搜索验收协议。两个变体由脚本预设，没有LLM提出代码，也没有真实运行ADAS或AFlow；Plan→Execute是本题自选起点，不声称两篇论文都用这个初始图。

| 候选 | 结构与执行规则 | 要检验的取舍 |
| --- | --- | --- |
| W0 | Plan→ExecuteA→输出 | 便宜，但单次回答有预设错误 |
| WR | Plan→ExecuteA→Reflect；flag为true时Repair一次，再输出，否则沿用原回答 | 能修复也可能误改；修复次数上限1，反思不能无限续跑 |
| WD | Plan分别供给ExecuteA/B，两路结果进入Select→输出 | selector按mock置信度选答案，不能读取gold；置信度可能错。两路在本实验中顺序执行，未证明并行加速 |

例如validation输入`21+1`：ExecuteA预设返回0，Reflect预设指出需修复，Repair返回22；WD的第二路预设返回22并有更高置信度。另一个输入的Repair仍返回错误，训练集还预设一次错误反思把正确答案改坏。因此“加反思”或“双路投票/选择”都不内建正确性保证。

train共6例作开发诊断，validation共4例用于本轮搜索选优，test另4例在冻结后只评所选候选。输入与ID跨分区不重复；但样本和答案由研究者人工构造、机制固定，共享简单算术规律，不能把分区检查当现实泛化证明。执行器拿到输入和独立的mock回复表，评价器才比较gold；Select不使用gold。

预算预先设为：**2次提案、34次样本评估、128次mock节点执行**。34=`(基线+两变体)×(6train+4validation)+4test`；每次实际节点执行先扣1 unit，包括Plan、Select和失败调用，不代表真实LLM调用或Token费用。无效/重复提案也扣次数；节点或样本预算耗尽直接终止，不继续调用。mock超时是有界同步异常注入，没有sleep、远端取消或后台任务。

可部署候选在本实验中须满足：评估无执行错误，validation平均节点数≤3.5；随后按validation正确率优先、平分更低成本选定。这里的“可部署”仅指满足本地toy门槛，不代表真实发布许可。提案预算耗尽才冻结候选hash，随后一次test；测试失败也消耗机会，不能拿test结果继续搜索。

为演示探索，第一次只有W0可选；第二次W0/WR的validation得分为0.5/0.75。下列原样函数使用**toy参数**α=4、λ=0.3及0–1分数，得到概率约`0.3383/0.6617`。预设均匀抽样值0.1选择较低分的W0，再提出WD，说明抽样不是取argmax。抽样只检验概率和父子记录，结构提案仍是脚本预设；参数尺度也不同于上述作者源码。

```python
def mixed_probabilities(scores, alpha=4.0, exploration=0.3):
    if (not scores or not all(math.isfinite(x) and 0 <= x <= 1 for x in scores)
            or not math.isfinite(alpha) or alpha < 0 or not 0 <= exploration <= 1):
        raise ProtocolError('invalid_sampling_input')
    weights = [math.exp(alpha*(x-max(scores))) for x in scores]
    return [exploration/len(scores) + (1-exploration)*w/sum(weights) for w in weights]
```

2026-09-16，Python3.11.8真实本地记录：

| 候选 | train正确/6 | validation正确/4 | validation平均节点数 | 门槛与选择 |
| --- | ---: | ---: | ---: | --- |
| W0 | 6 | 2 | 2.0 | 合格，但不是选优结果 |
| WR | 5 | 3 | 3.5 | 合格并选定；冻结后test为3/4 |
| WD | 4 | 4 | 4.0 | 分数最高，但超成本门槛而拒收；未用其test选优 |

正常运行总计**108次节点执行**，128额度剩20，34次样本额度用完，停止原因为提案预算耗尽。它同时说明最高训练分W0、最高validation分WD都不等于最终选择。节点数只衡量本mock的工作量，不能用来声称真实方法排名、收益或费用。

另一次独立故障场景在`validation-2/Repair`抛出MockTimeout：该样本保留为失败，WR出现执行错误而不合格；WD仍超成本，回退W0，冻结后test为1/4，总节点数102。不是删掉超时样本再提高均分，故障也不是错误的测试代码。本实验不模拟真实网络超时或OS硬时限。

最终**30 tests通过**，30次DATA/GOLD/回复表不变检查，30个专属临时根全部清理。两个刻意弱化门槛的副本由同一测试bytes检出：去掉成本门槛产生真实exit1/5个断言失败，去掉错误门槛产生exit1/2个断言失败，未处理unittest错误均0。多个断言失败不是多个独立缺陷，外层驱动exit0只表示检出了预期错误。源码静态依据、完整fixture、候选/父子/预算记录、故障记录、红绿日志与便携脚本随交接附件提供。本地协议处于同一进程，不提供生产权限隔离；未验证真实模型、网络、并发、硬时限或部署接纳。

### 5. 停止、评估和发布分层

生产实验还需登记模型版本、所有prompt/operator版本、任务家族划分、随机种子、重复次数、评价器与资源预算，记录每个候选的代码hash、来源父节点、有效/失败运行和成本。搜索反复使用的validation已成为优化信号，最终test应隔离，不能读完答案再当作未知样本。记录配对差异、波动与置信区间，不只汇报最好一次。

停止可以由最大提案/调用/费用、时间预算、连续无进展或无合法候选触发；这些条件表示“不再搜索”，不等于已完成业务验收。top-k均分稳定也可能来自搜索空间不足、重复候选或噪声。发布前还要做关键场景回归、权限/接口检查、真实调用链验证以及回滚准备；评估器本身不能由候选偷偷放宽。

课程`slides/11-4.html`中的逐步搜索结构和分数是教学示意，本文未搬运其数列、图像或效果宣称。不能把“选择最高分父节点”“低分永久剪枝”等示意步骤当作两篇论文或固定源码的完整算法，也不能据此断言AFlow普遍优于ADAS。本文的有限模板、预算计数和冻结协议是原创mock，不是对作者实现的复现或强化保证。

## 延伸 / 追问

- **为什么不一直选最高分父节点？** 可能陷入同一局部结构，得分也含噪声。保留探索概率和失败经验有助于覆盖其它分支，但不会带来全局最优保证；探索同样消耗评估预算。
- **反思版train下降，是否立刻丢弃？** 先查是哪类样本退化、评价是否可信；按预先约定的validation及关键回归门槛决定。本例train只诊断，真实关键能力不能因均分更高就被牺牲。
- **一次评估失败后能否无限debug到通过？** 不应。按候选/尝试分别计费，错误与分数分开留存，修复后重新绑定代码hash再评估；到限停止，不拼接旧版本成绩。
- **工作流能运行就能进生产吗？** 还差输出契约、资源与权限边界、可靠性和业务验收。尤其生成代码需要受控执行环境；论文或源码中的exec不提供安全隔离。

## 常见误区

- **“最高训练分代表可部署。”** 泛化、关键回归、成本和权限是额外条件，搜索停止也不是部署授权。
- **“课程示意就是算法原文。”** 论文版本、作者具体路径、课程动画与本地mock应分别归因。
- **“MCTS等于固定UCT和标准回传。”** AFlow明确使用变体，应核对候选池、概率与经验更新，而非套术语。
- **“多一个节点一定更强，轮数一样就公平。”** 错误反思、错误选择与成本膨胀都可能发生；还需核对实际调用、重复评估和失败重试。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定`5a933d287dd5074cc1543cb849146f3261d47521`：[slides/11-4.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/11-4.html)、[slides/interview-5.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/interview-5.html)。仅作学习线索，未搬运AGPL正文、代码或图片。
- Shengran Hu、Cong Lu、Jeff Clune，[*Automated Design of Agentic Systems*，arXiv:2408.08435v1](https://arxiv.org/html/2408.08435v1)，2024-08-15，§3；[作者MGSM实现](https://github.com/ShengranHu/ADAS/blob/2702bee8fefda42255efc5be9f60e3bd3db96ae4/_mgsm/search.py)，固定`2702bee8fefda42255efc5be9f60e3bd3db96ae4`，`search:145`、`evaluate:243`、`evaluate_forward_fn:278`。
- Jiayi Zhang 等，[*AFlow: Automating Agentic Workflow Generation*，arXiv:2410.10762v1](https://arxiv.org/html/2410.10762v1)，2024-10-14，§3.2、§4与算法1；作者仓库固定`3f457218fc716093fe53f6df8a5d5e6379d66346`：[optimizer.py](https://github.com/FoundationAgents/AFlow/blob/3f457218fc716093fe53f6df8a5d5e6379d66346/scripts/optimizer.py)、[data_utils.py](https://github.com/FoundationAgents/AFlow/blob/3f457218fc716093fe53f6df8a5d5e6379d66346/scripts/optimizer_utils/data_utils.py)、[convergence_utils.py](https://github.com/FoundationAgents/AFlow/blob/3f457218fc716093fe53f6df8a5d5e6379d66346/scripts/optimizer_utils/convergence_utils.py)、[experience_utils.py](https://github.com/FoundationAgents/AFlow/blob/3f457218fc716093fe53f6df8a5d5e6379d66346/scripts/optimizer_utils/experience_utils.py)、[evaluation_utils.py](https://github.com/FoundationAgents/AFlow/blob/3f457218fc716093fe53f6df8a5d5e6379d66346/scripts/optimizer_utils/evaluation_utils.py)、[evaluator.py](https://github.com/FoundationAgents/AFlow/blob/3f457218fc716093fe53f6df8a5d5e6379d66346/scripts/evaluator.py)。实际函数分支仅静态读取，未执行作者实现。
