---
id: agent-0066
title: 递归改进与进化搜索怎样优化 Harness，为什么保留多样候选可能优于只保留当前最高分？
category: agent
tags: [recursive-improvement, stop, quality-diversity, archive, harness, evaluation]
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

递归改进与进化搜索怎样优化 Harness，为什么保留多样候选可能优于只保留当前最高分？请以三个候选比较下一轮结果，说明公平搜索预算、保留集隔离、失败与停止规则，并区分改改善器、改模型权重和持续进步保证。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**递归改进把“产生改进的方法”也变成候选；多样候选档案则为未来搜索保留不同的出发点。两者能结合，但都不保证下一轮更好。** 当前低分方案可能通向另一个高质量区域，丢弃它就失去这条搜索路径；反过来，维护和评估大量分支也可能浪费有限预算。

[agent-0053](agent-0053-agent-bootstrapping-degradation-control.md) 讨论退化，[agent-0054](agent-0054-self-improving-agent-trust-root-boundary.md) 讨论信任根，[agent-0065](agent-0065-workflow-search-aflow-adas.md) 讨论工作流搜索。本题聚焦改善器的递归应用与候选保留策略，不把它们扩展成允许 Agent 修改评价规则或权限。

### 1. STOP 改的是改善器程序，不是底层模型权重

STOP 是 **Self-Taught Optimizer**。Zelikman 等的 `2310.02304v1`（2023-10-03）用一个可执行的脚手架程序调用固定语言模型，改进输入程序；然后把改善器自己的代码也当作待改进对象。它不是仅调整一条提示词，也不是把模型权重放进训练循环。

| 层级 | 输入与输出 | 衡量什么 |
| --- | --- | --- |
| 下游改善 | 改善器 I 接收解/程序 s、任务效用 u 和固定模型 M，提出候选并返回一个新程序 | 新程序在该任务上的效用、错误及成本 |
| 改善器的改善 | 旧 I 的代码成为输入；元效用评价“这个 I 在一组下游任务中能把解改善到什么程度” | 下游改善结果的聚合效用，而非代码看起来更复杂或自评更聪明 |
| 递归继续 | 用新得到的改善器产生后续候选，达到迭代/调用预算等条件后停止 | 有限实验结果；不自动产生单调提升或收敛定理 |

所以“STOP不改善解，只改善改善器”不准确：内层仍改善下游解，递归的外层优化对象是改善器。论文算法1在固定模型和任务集合上迭代，图4展示特定实验中的改善与退化；不能把某条均值曲线当成换任务、换模型后仍持续进步的保证。

**固定源码要看实际接纳条件。** 在 `microsoft/stop@0d6780c54306b2486dd36e9c4ae9b49aceb27ea4`，runner导入 `tasks/meta_optimization/secret_seed_algorithm.py` 的种子函数；该公开源文件的 `improve_algorithm:18–23` 对生成的 `new_solutions` 取 `max(..., key=utility)`，没有把原输入明确加入这组备选。因此“选出最好生成候选”不等于“一定胜过原解”。文件名中的secret是作者公开种子/评估实现的命名，本题未读取任何本机秘密。

`run_improver.py:141–144` 的后验数值门槛在 `checked_utility == 0` 时拒绝；异常也会走失败分支，但没有比较新旧效用大小；变量名 `successful_improvement` 不构成单调改善证明。`:166–179` 按配置的迭代数运行，并在iterative分支更新改善器代码后加载新函数。是否形成递归自身改善还取决于目标与配置，不能把所有运行模式混成一条递归保证。

runner实际使用的 `tasks/meta_optimization/secret_utility.py` 返回validation聚合值；但在 `log_usage` 分支（`:127–137`）还会计算并写出test指标。调用与返回值的区分不等于严格的保留集访问隔离，也不是本文mock的“冻结后只查一次”协议。以上只读源码，不执行其生成代码、sandbox或模型调用。

### 2. 为什么多样档案不是多留几个高分名字

普通全局top-k可能全是同一个局部解的近邻。**质量多样性（quality diversity）同时关注质量和行为覆盖：先定义有意义的行为描述，再在各区域保留较好的解。** 文本换名、换措辞不自动形成行为差异；描述符应来自规定的行为测量，且不能偷看保留集来设计。

MAP-Elites（Mouret与Clune，`1504.04909v1`，2015-04-20）在用户指定的低维特征空间分区，寻找各区域的高质量解。某个区域的局部精英可以低于全局冠军，却仍值得保留。它也不同于只保留Pareto非支配点：质量多样性可以保留并非全局最优、也不在全局Pareto前沿的区域代表。

| 保留方式 | 适用条件 | 代价与失败边界 |
| --- | --- | --- |
| 单一冠军 | 预算紧、局部改进相对有效，不需要维护大量分支 | 容易反复开发一个区域，失去低分跳板；不能证明已探索其它路径 |
| 全局top-k | 希望多起点，尚无可靠行为描述符 | 简单，但候选可能高度相似；k个文件不等于k种能力 |
| 按行为区域留优 | 能定义有价值的描述符，跨区域搜索可能有帮助 | 要付出测量、存储和探索成本；分区太细会稀疏，太粗会掩盖差异，描述符错误会保留无用多样性 |

保留档案不要求把每个候选都部署。还要区分**可被选作父代的池**与**审计历史**：被淘汰的候选、失败原因、父子关系与评估版本可以保留为证据，而不再获得繁衍预算。不能为了显得进步而删除失败记录。

### 3. 固定质量多样性实现的范围

本文选用作者团队的 `resibots/pymap_elites@d9cb18774ea154a03aa52a99679be53fcf94a24f` 作源码例证。README明确这是 **CVT-MAP-Elites** 等变体的参考实现，不能称作2015论文原始网格实现。其genotype是数值向量，不是现成的Harness代码搜索器；迁移到Harness仍需另外定义编码、变异和评估，本题只借用档案保留机制。

`map_elites/cvt.py::__add_to_archive:51–63` 根据行为描述找最近centroid；空区域可加入候选，已占区域仅在新fitness严格更高时替换。`:109–118` 从档案key中均匀抽取两个父代、允许重复，调用传入的variation_operator；缺省 `common.variation:162–165` 实际调用SBX，并非因为文件定义了多个算子就会自动混用它们。

这说明“格内质量竞争”与“父代抽样”是两个环节，不能直接说父代概率总与全局fitness成正比。相同固定评价下，格内保存的数值可保持不下降；噪声、换评价版本和真实保留集表现仍可能退化。

停止也要看粒度：`cvt.py:101` 在批次开始检查 `n_evals < max_evals`，`:126` 才累加整个批次，最后一批可能超出目标数。它不是逐样本硬配额或整体硬时限保证。本文使用自己的有界计数器，不运行作者的并行进程池或变异代码。

### 4. 原创对照：同样三个候选，下一轮怎样不同

以下是有限二分类回复表mock，不运行STOP、MAP-Elites或真实模型。三个候选A/B/C在同一search set的8个样本上逐条与固定gold比较；另有两个行为探针，其返回的两个bit形成描述符，**不计入质量分数**。保留集另有6个样本。

| 初始候选 | search正确/8 | 实测探针描述符 | 两种策略怎样保留 |
| --- | ---: | --- | --- |
| A | 7 | (0,0) | 全局冠军；两种策略都可保留 |
| B | 6 | (1,0) | 非冠军，但代表另一个行为区域 |
| C | 5 | (0,1) | 非冠军，代表第三个区域 |

下一轮作为**同一个批次**，开始时固定父代日程：冠军策略用A发出3个提案，档案策略按A/B/C各发1个；两者使用相同编号0/1/2的变异槽位，批次中不随新成绩重新选父代。这里不是CVT源码的随机有放回抽样复现，也没有LLM学出变异算子；它只比较一项已登记的预算分配政策。

每组预算严格相同：3次提案、66次mock评估调用。66=`3个初始候选×(8质量+2探针) + 3个子代×(8质量+2探针) + 6保留集`。两组共同的初始化成本、探针成本和失败调用都计入。逻辑亲代池分别是1条和3条；没有把更多档案的存储/上下文开销假装测成相同费用。

#### “跳板”场景：低分B通向更好后代

预先登记的回复与变异表给出下列真实本地结果（2026-09-16，Python3.11.8）：

| 策略 | 下一轮三个结果 | 本轮结束时最高search分 | 冻结后保留集 |
| --- | --- | ---: | --- |
| 单一冠军 | A→A0得7/8；A→A1得6/8；A→A2有1次模拟执行失败、记录为6/8且不得接纳 | 保留A，7/8 | 4/6 |
| 多样档案 | A→A0得7/8；B→B1得8/8；C→C2得6/8，描述符分别保持原区域 | 选B1，8/8 | 6/6 |

A0与A同分且同行为，不替换旧精英；改个名字不能增加覆盖。B1/C2分别替换本区域较弱精英。A2的失败发生在`search/3`，作为失败样本保留，仍完成并计入本次10个评估调用；它不是被删除的分母，也不是测试自身错误。

#### 相反场景：集中开发冠军也可能更好

另一个预先固定的变异表保留完全相同的A/B/C起点与预算，但使A的槽位1通向8/8的A1plus，B/C的对应槽位没有改进。冠军策略于是选A1plus、保留集6/6；档案策略只给A槽位0，仍保留7/8的A、保留集4/6。这个反例说明档案有机会成本，不能将前一场景当作无条件优势。

四个试验均实际调用66次、使用3次提案；两个场景与所有回复均人为预设，**结果证明的是代码按协议执行，不是档案算法或模型取得了经验性收益**。同一保留集用于这组预先设计的对照，也不构成真实分布上的独立统计实验。

下列为已测试mock的原样接纳方法摘录。quality是8个search样本的正确数，descriptor来自两次探针调用；字段校验、无错误、格内严格改善是本文自己的局部规则，不能反推作者实现拥有同样的校验或安全能力。

```python
def consider(self,record):
        if (record.errors or type(record.quality) is not int or not 0<=record.quality<=8
                or type(record.descriptor) is not tuple or len(record.descriptor)!=2
                or any(type(x) is not int or x not in (0,1) for x in record.descriptor)):
            return False
        key='global' if self.policy=='champion' else record.descriptor
        incumbent=self.cells.get(key)
        if incumbent is None or record.quality>incumbent.quality:
            self.cells[key]=record
            return True
        return False
```

### 5. 预算、保留集与停止不能被改善器接管

本实验在3个提案槽位耗尽后冻结所选程序hash，才允许通过实验接口查询一次保留集；查询失败也消耗该机会，之后禁止继续变异。评估预算不足会立即中止，部分结果不进入档案。审计历史保留全部初始候选，但冠军策略的可选亲代池仍只有A，不能从日志中偷偷多选B/C。

真实递归优化还要分配**嵌套预算**：改改善器花的提案/调试成本，加上元效用里每个下游任务的运行、反思和重复评估，不能只数外层代数。修复失败、无效候选、缓存命中、探针测量与最终确认要分别记账。本文66次是mock单位，不是LLM请求数、Token或金额。

评价器、任务定义、资源上限与保留集权限放在改进循环之外。search/validation反复参与选择后已经是优化信号，应另留不反馈给提案器的测试；必要时按任务家族做嵌套划分与多种子重复。部署须检查关键回归和现实成本，不能从最高search分、格内不降或“递归完成”推出业务成功。

本地最终**30 tests通过**，30次GOLD/回复表不变检查、30个专属临时根全部清理。测试覆盖两种相反结果、共同初始化成本、每组66次实际调用、固定父代日程、格内替换/同分/换名、错误候选拒收、预算中止、冻结后一次保留集与失败状态。原始候选、探针、父子记录、失败记录、预算和可复跑脚本随交接附件提供。

实验只有同进程的有限程序ID与回复表，没有真实代码变异、递归调用模型或模型训练；接口分区不提供生产权限隔离，研究者知道全部合成标签。没有启动真实Agent/服务、修改运行时或验证长期改进、真实并发、硬时限、部署接纳。课程11-5/11-6/11-7中的演示与其它方法效果不作为本实验结果，也不补造未核实的收益。

## 延伸 / 追问

- **候选越多越好吗？** 不一定。应按有价值的行为维度设容量和淘汰规则；评估慢、描述符不可靠或预算很小时，精简冠军/小池可能更合适，审计历史仍可另外保存。
- **为什么不是直接留top-3？** top-3可能集中在一个区域。行为档案旨在保留不同区域的精英，但是否有用取决于描述符与未来可达路径，不能只按名称或代码相似度判断。
- **改善器把自己的分数定义改了算进步吗？** 不算同一目标下的改善。标准变化需独立批准和版本化，旧新成绩不能直接混比；优化代码的写权限不等于评价与发布权限。
- **什么时候停止递归？** 达到总预算、无有效候选、反复失败、确认的退化或预设无进展条件时停止并保留证据。停止只表示结束搜索，不等于模型训练成功或已经获得部署授权。

## 常见误区

- **“改改善器就是训练模型权重。”** STOP优化的是调用模型的程序，底层模型保持不变。
- **“一条上升曲线证明持续自我提升。”** 那只是特定任务、模型、预算与评价下的有限观察，固定实现的成功标记也未必做新旧比较。
- **“进化天然保证多样性。”** 选择压力可使候选坍缩；描述符、容量、采样和格内选择都需要明确设计。
- **“存进档案就是可以部署。”** 父代价值、审计价值和部署资格不同；低分跳板、执行错误、保留集表现与真实资源约束必须分别处理。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定`5a933d287dd5074cc1543cb849146f3261d47521`：[slides/11-5.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/11-5.html)、[slides/11-6.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/11-6.html)、[slides/11-7.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/11-7.html)。仅作学习线索，未搬运AGPL正文、代码或图片。
- Eric Zelikman、Eliana Lorch、Lester Mackey、Adam Tauman Kalai，[*Self-Taught Optimizer (STOP): Recursively Self-Improving Code Generation*，arXiv:2310.02304v1](https://arxiv.org/pdf/2310.02304v1)，2023-10-03，算法1、§3、§5.1。固定作者代码`0d6780c54306b2486dd36e9c4ae9b49aceb27ea4`：[实际导入的种子函数](https://github.com/microsoft/stop/blob/0d6780c54306b2486dd36e9c4ae9b49aceb27ea4/tasks/meta_optimization/secret_seed_algorithm.py)、[run_improver.py](https://github.com/microsoft/stop/blob/0d6780c54306b2486dd36e9c4ae9b49aceb27ea4/run_improver.py)、[实际meta_utility实现](https://github.com/microsoft/stop/blob/0d6780c54306b2486dd36e9c4ae9b49aceb27ea4/tasks/meta_optimization/secret_utility.py)。只读公开源文件，未执行作者实现或读取本机配置。
- Jean-Baptiste Mouret、Jeff Clune，[*Illuminating search spaces by mapping elites*，arXiv:1504.04909v1](https://arxiv.org/html/1504.04909v1)，2015-04-20，§1–3。作者团队参考实现固定`d9cb18774ea154a03aa52a99679be53fcf94a24f`：[README明确CVT等变体](https://github.com/resibots/pymap_elites/blob/d9cb18774ea154a03aa52a99679be53fcf94a24f/README.md)、[map_elites/cvt.py](https://github.com/resibots/pymap_elites/blob/d9cb18774ea154a03aa52a99679be53fcf94a24f/map_elites/cvt.py)、[map_elites/common.py](https://github.com/resibots/pymap_elites/blob/d9cb18774ea154a03aa52a99679be53fcf94a24f/map_elites/common.py)。只读核对，未运行其并行评估或变异实现。
