---
id: llm-0042
title: 大模型无训练权重合并（Task Arithmetic、TIES-Merging、DARE 与 SLERP）是如何通过任务向量算术、符号冲突消解、随机稀疏重缩放与超球面测地线插值实现多能力融合的？
category: llm
tags: [model-merging, task-arithmetic, ties-merging, dare, slerp, mergekit]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开模型合并工程指南与模式库（f-o-x11/dreaming-press / nibzard/awesome-agentic-patterns）扩展改编；Task Arithmetic（ICLR 2023）、TIES-Merging（NeurIPS 2023）、DARE（ICML 2024）、DELLA（2024）及 Arcee MergeKit / Hugging Face PEFT 源码核实（见参考）
status: published
updated: 2026-11-14
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-11-14
    updated: 2026-11-14
---

## 问题

在多任务大模型迭代与开源后训练（Post-Training）流水线中，团队往往基于同一个预训练底座模型（Base Model, $\theta_{\text{pre}}$）微调出了多个领域专家模型或 LoRA 适配器（例如数学推理模型 $\theta_{\text{math}}$、代码生成模型 $\theta_{\text{code}}$、人类偏好对齐模型 $\theta_{\text{chat}}$）。如果将所有数据混合重新做联合多任务微调（Joint Multi-Task Training），不仅训练算力成本高昂，还常受限于上游闭源微调数据集不可得；而如果采用多模型集成（Ensembling），推理显存与延迟又会随模型数量线性倍增。**模型合并（Model Merging / Weight Fusion）**允许在不进行任何梯度更新、甚至无需训练数据的情况下，直接在权重空间（Weight Space）将多个同源微调模型融合为单一模型，并在 `arcee-ai/mergekit` 与 Hugging Face `peft` 中成为工业界标准范式。

请深入剖析以下三个核心问题：
1. **线性模式连通性与任务向量算术及干扰瓶颈（Task Arithmetic vs TIES-Merging）**：为什么只有源自**同一底座检查点（Homologous Base Checkpoint）**的微调模型才能在权重空间直接相加或平均，而将两个独立随机初始化的模型权重求平均会彻底失效？**Task Arithmetic（任务向量算术）**是如何通过定义任务向量 $\tau_t = \theta_t - \theta_{\text{pre}}$ 实现技能叠加（Addition）与有害能力擦除（Negation）的？当合并多个任务向量时，为什么朴素线性加权会遭遇严重的平庸化退化？**TIES-Merging（Trim, Elect Sign, and Merge）**是如何通过“幅值剪枝（Trim）$\to$ 主导符号选举（Elect Sign）$\to$ 不相交均值合并（Disjoint Merge）”三步法精确消除冗余噪声与正负符号冲突的？
2. **极度稀疏重缩放与无偏期望保持（DARE 与 DELLA 的数学机制）**：为什么微调产生的参数增量（Delta Weights）可以被随机丢弃 $90\%$ 甚至 $99\%$ 而不损失模型能力？**DARE（Drop And REscale）**是如何通过伯努利随机掩码与 $\frac{1}{1-p}$ 重缩放因子，在大幅削减多模型参数碰撞率的同时，严格保证线性层前向输出期望无偏（$\mathbb{E}[\tilde{\tau} x] = \tau x$）的？针对随机丢弃可能误杀极少数高幅值关键参数的缺陷，**DELLA（Drop and rEscale via MagPrune）**是如何通过基于幅值排名的自适应丢弃概率优化 DARE 的？在 `mergekit` 与 `peft` 中，`dare_linear` 与 `dare_ties` 的计算链路有何本质区别？
3. **超球面测地线插值与范数保持（SLERP vs LERP 线性插值）**：在融合两个全量微调模型时，为什么标准线性插值（LERP / Model Soups，$\theta_{\text{LERP}} = (1-t)\theta_0 + t\theta_1$）会在夹角较大时导致中间点权重范数坍缩（Norm Shrinkage）并弱化深层激活信号？**球面线性插值（SLERP, Spherical Linear Interpolation）**是如何沿着超球面大圆测地线（Geodesic）保持几何模长恒定过渡的？请给出 SLERP 的闭式三角系数推导，并说明工程源码（如 `mergekit` 的 `slerp.py`）中如何处理两向量近似共线（$\cos \Omega \to 1$）时的除零奇点与数值下溢边界？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-11-14

**大模型无训练权重合并的物理基石是同源微调模型在损失曲面上的线性模式连通性（Linear Mode Connectivity），而算法演进的核心主线则是消除多任务参数增量之间的结构性干扰（Parameter Interference）：（1）源自同一预训练底座 $\theta_{\text{pre}}$ 的微调模型位于同一个低损失盆地（Low-Loss Basin）内且共享神经元排列对称性；Task Arithmetic 将微调增量抽象为任务向量 $\tau_t = \theta_t - \theta_{\text{pre}}$ 并执行线性组合 $\theta_{\text{new}} = \theta_{\text{pre}} + \lambda \sum_t w_t \tau_t$，但多模型合并时会因“小幅值冗余参数叠加”与“同坐标正负符号相消”而退化；TIES-Merging 通过仅保留各任务向量前 $k\%$ 最大幅值（Trim）、按总幅值或频次选举每个坐标的主导符号 $\gamma_j = \text{sgn}(\sum_t \hat{\tau}_t^{(j)})$（Elect Sign），并仅对符号与 $\gamma_j$ 一致的非零分量求不相交均值（Disjoint Merge），彻底阻断了反向梯度抵消；（2）DARE 发现微调增量 $\tau_t$ 具有极高的过参数化冗余度，通过以概率 $p \in [0.9, 0.99]$ 随机置零增量并以 $\frac{1}{1-p}$ 放大幸存参数（$\tilde{\tau}_t = \frac{m_t \odot \tau_t}{1-p}$，$m_t \sim \text{Bernoulli}(1-p)$），使单层激活增量期望严格满足 $\mathbb{E}[\tilde{\tau}_t x] = \tau_t x$，同时将 $M$ 个模型的非零参数重叠碰撞概率压降至 $(1-p)^M$；DELLA 进一步将均匀随机丢弃改造为按幅值升序排名分配保留概率 $q_i = (q - \epsilon) + \frac{\text{rank}(|\tau^{(i)}|)-1}{N-1}\cdot 2\epsilon$，兼顾了高幅值特征保护与随机无偏性；（3）针对双模型融合中线性插值 LERP 使中间权重范数收缩为 $\|\theta\|\cos(\Omega/2)$ 的缺陷，SLERP 通过弧长参数化公式 $\text{SLERP}(\theta_0, \theta_1; t) = \frac{\sin((1-t)\Omega)}{\sin\Omega}\theta_0 + \frac{\sin(t\Omega)}{\sin\Omega}\theta_1$ 沿超球面测地线插值以保持权重流形范数不变，并在 $|\cos\Omega| > 0.9995$ 时自动回退至 LERP 消除 $\sin\Omega \to 0$ 的数值奇点。**

在展开数学推导与源码分析前，建议结合题库内已有题目建立完整知识图谱：关于 LoRA 低秩微调的基础矩阵分解 $\Delta W = \frac{\alpha}{r}BA$ 与合并回底座权重的原理，请参阅 [llm-0001](llm-0001-lora-fine-tuning.md)；关于 DoRA 幅度-方向解耦、PiSSA 主奇异值初始化与 rsLoRA 秩稳定缩放，请参阅 [llm-0040](llm-0040-dora-pissa-rslora-loraplus-peft.md)；关于 DPO、SimPO、ORPO、IPO 与 KTO 等偏好对齐训练阶段如何塑造权重增量，请参阅 [llm-0041](llm-0041-simpo-orpo-kto-ipo-preference-optimization.md)；关于通过知识蒸馏（Knowledge Distillation）将多教师能力迁移至单学生模型的有训练替代方案，请参阅 [llm-0015](llm-0015-knowledge-distillation-tradeoffs.md)；关于在业务落地中如何权衡 Prompt、RAG 与微调的工程边界，请参阅 [llm-0014](llm-0014-prompt-rag-finetuning-choice.md)。

---

### 1. 线性模式连通性、Task Arithmetic 与 TIES-Merging 符号冲突消解

#### （1）为什么只有“同源底座模型（Homologous Models）”才能直接做权重算术？
神经网络的损失曲面是高度非凸的，且隐层神经元具有**排列对称性（Permutation Symmetry）**：在 Transformer 的 FFN 或多头注意力层中，任意置换两个中间神经元的排列顺序（同时置换输入投影矩阵的行与输出投影矩阵的列），网络的前向函数完全不变，但参数张量在欧氏空间中的坐标却天差地别。
- **跨底座合并必然失败**：如果两个模型 $\theta_A, \theta_B$ 是从不同随机种子独立预训练出来的（或者一个是 Llama-3、另一个是 Qwen-2.5），它们的同一参数坐标 $(i, j)$ 编码的是毫不相关的特征子空间；直接求平均 $\frac{1}{2}(\theta_A + \theta_B)$ 会跨越损失曲面上的高耸能量壁垒（High-Loss Energy Barrier），导致合并后的模型彻底输出乱码；
- **同源微调的线性模式连通性（Linear Mode Connectivity, Frankle et al., 2020; Model Soups, Wortsman et al., ICML 2022）**：当多个专家模型 $\theta_1, \dots, \theta_M$ 均从**同一个预训练检查点 $\theta_{\text{pre}}$** 出发进行微调时，由于预训练已经固定了特征坐标系的排列对称性，且微调学习率较小，各专家模型仍然停留在以 $\theta_{\text{pre}}$ 为中心的同一个平坦低损失盆地（Low-Loss Basin）内。因此，在该盆地内部对增量做线性或凸组合，依然落在低损失流形上。

#### （2）Task Arithmetic（任务向量算术）与两大参数干扰源
**Task Arithmetic**（Ilharco et al., ICLR 2023）提出将第 $t$ 个任务微调前后的权重差定义为**任务向量（Task Vector / Delta Weight）**：

$$\tau_t = \theta_t - \theta_{\text{pre}} \in \mathbb{R}^d, \qquad (\text{若为 LoRA 适配器，则 } \tau_t = \frac{\alpha_t}{r_t} B_t A_t)$$

通过在任务向量空间执行加减法，可以实现无需训练的模型编辑：
- **多技能叠加（Multi-Task Addition）**：$\theta_{\text{merged}} = \theta_{\text{pre}} + \lambda \sum_{t=1}^M w_t \tau_t$（例如合并数学 $\tau_{\text{math}}$ 与代码 $\tau_{\text{code}}$）；
- **能力擦除 / 机器遗忘（Task Negation / Unlearning）**：$\theta_{\text{unlearn}} = \theta_{\text{pre}} - \lambda \tau_{\text{toxic}}$（先在有害数据或隐私数据上微调出 $\tau_{\text{toxic}}$，再从底座中**减去**该向量，即可定向抹除有害行为而保持通用能力）；
- **类比推理（Task Analogy）**：$\hat{\theta}_D = \theta_C + (\theta_B - \theta_A)$。

然而，**TIES-Merging**（Yadav et al., NeurIPS 2023）通过深入剖析发现，当用朴素 Task Arithmetic 合并 $M \ge 3$ 个模型时，性能会急剧衰减，根源在于两类致命的**参数干扰（Parameter Interference）**：
1. **冗余小幅值参数的噪声累积（Interference from Redundant Parameters）**：在单任务微调中，超过 $80\%$ 的参数坐标变化量 $|\tau_t^{(j)}|$ 极其微弱，对该任务本身毫无贡献；但在多模型相加时，十几个模型的微弱漂移叠加在原本对某个特定任务至关重要的坐标 $j$ 上，就会污染该关键参数；
2. **同坐标正负符号冲突相消（Interference from Sign Disagreement）**：对于第 $j$ 个参数坐标，模型 1 要求大幅正向更新（如 $\tau_1^{(j)} = +0.70$），模型 2 也要求正向更新（$\tau_2^{(j)} = +0.50$），而模型 3 却要求反向更新（$\tau_3^{(j)} = -0.90$）。朴素求和得到 $+0.70 + 0.50 - 0.90 = +0.30$（再除以 $3$ 仅剩 $+0.10$），正负增量相互抵消，使得合并后的参数退化回接近底座 $\theta_{\text{pre}}$ 的平庸值，导致所有任务同时掉点！

#### （3）TIES-Merging 的三步走算法与 `peft` / `mergekit` 源码核实
对照 Hugging Face `peft` 官方源码（`src/peft/utils/merge_utils.py::ties`，第 185–214 行）与 `arcee-ai/mergekit`（`mergekit/merge_methods/generalized_task_arithmetic.py`，第 91–172 行），TIES-Merging 对每个参数张量的 $M$ 个任务向量 $\{\tau_1, \dots, \tau_M\}$ 依次执行以下三步：

1. **Step 1 — Trim（按幅值剪枝冗余参数）**：
   给定保留密度超参 $k \in (0, 1]$（源码中的 `density`，典型值 $0.2 \sim 0.75$），对每个任务向量 $\tau_t$ 独立保留绝对值最大的前 $\lfloor k \cdot d \rfloor$ 个坐标，将其余 $1 - k$ 比例的小幅值漂移直接归零，得到稀疏修剪向量 $\hat{\tau}_t$（对应 `peft` 的 `magnitude_based_pruning` 与 `mergekit` 的 `sparsify(..., method="magnitude")`）。
2. **Step 2 — Elect Sign（跨模型主导符号选举）**：
   对于每个参数坐标 $j \in \{1, \dots, d\}$，计算所有模型在该坐标上的主导符号 $\gamma_j \in \{+1, -1\}$。源码中支持两种选举策略（`peft` 中的 `majority_sign_method="total" | "frequency"`，对应 `mergekit` 的 `ConsensusMethod.sum | count`）：
   - **按总幅值选举（`total` / `sum`，TIES 原论文默认）**：由正负双方累积幅值绝对值更大的一方胜出：
     $$\gamma_j^{\text{total}} = \text{sgn}\!\left( \sum_{t=1}^M w_t \hat{\tau}_t^{(j)} \right) = \begin{cases} +1, & \text{if } \sum_{t=1}^M w_t \hat{\tau}_t^{(j)} \ge 0 \\ -1, & \text{otherwise} \end{cases}$$
   - **按投票频次选举（`frequency` / `count`）**：统计非零正号与负号的模型个数：
     $$\gamma_j^{\text{freq}} = \text{sgn}\!\left( \sum_{t=1}^M \text{sgn}(\hat{\tau}_t^{(j)}) \right)$$
3. **Step 3 — Disjoint Merge（不相交同号子集聚合）**：
   在坐标 $j$ 上，构造二值共识掩码 $M_t^{(j)} = \mathbb{I}\!\left(\text{sgn}(\hat{\tau}_t^{(j)}) == \gamma_j\right)$，**彻底剔除所有符号与主导符号相反的模型分量（以及已归零的分量）**，仅对方向一致的模型子集 $\mathcal{A}_j = \{t \mid M_t^{(j)} = 1\}$ 求加权平均：
   - 在 `peft`（`disjoint_merge`，第 139–141 行）中，按保留的模型个数 $|\mathcal{A}_j|$ 归一化：
     $$\tau_{\text{TIES}}^{(j)} = \frac{\sum_{t=1}^M M_t^{(j)} \cdot w_t \hat{\tau}_t^{(j)}}{\max\!\left(1, \sum_{t=1}^M M_t^{(j)}\right)}$$
   - 在 `mergekit`（`GeneralizedTaskArithmeticMerge.merge_group`，第 133–145 行，当开启 `normalize=True` 时）中，按保留的权重之和归一化：
     $$\tau_{\text{TIES}}^{(j)} = \lambda \cdot \frac{\sum_{t=1}^M M_t^{(j)} \cdot w_t \hat{\tau}_t^{(j)}}{\sum_{t=1}^M M_t^{(j)} \cdot w_t}$$

---

### 2. DARE 与 DELLA：极度稀疏随机丢弃、无偏重缩放与幅值排名采样

#### （1）DARE（Drop And REscale）：为什么随机扔掉 $90\%\sim 99\%$ 的微调增量还能保持能力？
**DARE**（Yu et al., *"Language Models are Super Mario: Absorbing Abilities from Homologous Models as a Free Lunch"*, ICML 2024）揭示了一个反直觉的科学发现：全量微调（SFT）产生的参数增量 $\tau_t = \theta_t - \theta_{\text{pre}}$ 具有极端的冗余性（数值范围通常在 $10^{-3}$ 量级以内），而与 TIES 按幅值确定性剪枝不同，**DARE 并不是一种合并算法，而是一种极其强大的合并前预处理（Preprocessing）机制**。

给定丢弃率 $p \in (0, 1)$（或保留密度 $q = \text{density} = 1 - p$，例如 $p = 0.9 \implies q = 0.1$），DARE 对任务向量 $\tau_t$ 执行两步操作（对照 `peft/utils/merge_utils.py::random_pruning` 第 56–72 行）：
1. **Drop（伯努利随机掩码）**：独立同分布地从伯努利分布采样掩码 $m_t^{(j)} \sim \text{Bernoulli}(1 - p)$，将比例为 $p$ 的增量随机置为 $0$：
   $$\check{\tau}_t = m_t \odot \tau_t$$
2. **REscale（除以保留率 $1 - p$ 恢复期望尺度）**：将幸存的 $1 - p$ 比例非零参数放大 $\frac{1}{1 - p}$ 倍：
   $$\tilde{\tau}_t = \frac{m_t \odot \tau_t}{1 - p} = \frac{m_t \odot \tau_t}{\text{density}}$$

**为什么除以 $1 - p$ 能零成本恢复原始微调模型的能力？（前向激活无偏性证明）**：
考虑某个线性层权重 $W_{\text{SFT}} = W_{\text{pre}} + \Delta W$，输入激活向量为 $x \in \mathbb{R}^{d_{\text{in}}}$。原始微调增量对该层输出的第 $i$ 个维度的贡献为：

$$\Delta y_i = \sum_{j=1}^{d_{\text{in}}} \Delta W_{i, j} x_j$$

经过 DARE 处理后，由于 $\mathbb{E}[m_{i, j}] = 1 - p$，稀疏重缩放后的输出增量期望为：

$$\mathbb{E}\!\left[\Delta \tilde{y}_i\right] = \sum_{j=1}^{d_{\text{in}}} \mathbb{E}\!\left[\frac{m_{i, j}}{1 - p}\right] \Delta W_{i, j} x_j = \sum_{j=1}^{d_{\text{in}}} \frac{1 - p}{1 - p} \Delta W_{i, j} x_j = \Delta y_i$$

且由于大语言模型的隐藏层维度 $d_{\text{in}}$ 极大（如 $4096$ 或 $8192$），根据大数定律，数千个独立随机项加权求和的相对方差随 $\frac{1}{d_{\text{in}}(1-p)}$ 迅速收敛，使得单层输出的实际值高度集中于精确期望 $\Delta y_i$ 附近！与此同时，当合并 $M$ 个经过 DARE 稀疏化的模型时，任意坐标上两个模型同时保留非零参数的碰撞概率从 $1$ 暴降至 $(1-p)^2$（例如 $p=0.9$ 时碰撞率仅为 $1\%$），从根本上化解了多任务权重的干扰。

> **源码细节对比（`peft` 解析缩放 vs `mergekit` 经验范数缩放）**：
> 在 Hugging Face `peft`（`random_pruning` 第 71 行）中，直接采用理论解析缩放 `pruned_tensor = pruned_tensor / density`；而在 `arcee-ai/mergekit`（`mergekit/sparsify.py::rescaled_masked_tensor` 第 40–53 行）中，为了消除小尺寸张量上的采样方差，当 `rescale=True` 时采用精确的经验 $L_1$ 范数匹配：`masked * (tensor.abs().sum() / masked.abs().sum())`（在大张量极限下 $\frac{\|\tau\|_1}{\|m \odot \tau\|_1} \to \frac{1}{1-p}$）。

#### （2）DELLA（Drop and rEscale via MagPrune）：幅值排名自适应采样
尽管 DARE 在大多数密度下表现出色，但当保留率极低（如 $\text{density} = 0.05$）时，完全均匀的随机采样仍有 $95\%$ 的概率把微调中极少数幅度最大的核心特征权重误杀归零；反之，如果像 TIES 那样只保留 top-$k$ 最大幅值，又会破坏随机采样的无偏期望性质。

**DELLA**（Deep et al., 2024）在 `mergekit`（`mergekit/sparsify.py::della_magprune`，第 137–175 行）中将两者完美结合：**按参数绝对值在当前行内的升序排名（Rank）线性分配保留概率**。
设某行有 $N$ 个参数，将 $|\tau_{i, j}|$ 按从小到大排序得到名次 $r_{i, j} \in \{1, 2, \dots, N\}$，归一化排名为 $\tilde{r}_{i, j} = \frac{r_{i, j} - 1}{N - 1} \in [0, 1]$。给定目标平均密度 $q = \text{density}$ 与摄动半径 $\epsilon$（需满足 $0 < q - \epsilon < q + \epsilon < 1$），每个元素的保留概率为：

$$q_{i, j} = (q - \epsilon) + 2\epsilon \cdot \tilde{r}_{i, j} \in [q - \epsilon, \; q + \epsilon]$$

可以看到，全行平均保留率恰好等于 $\frac{1}{N}\sum_j q_{i, j} = q$，但幅值最大的参数拥有最高保留概率 $q + \epsilon$，幅值最小的参数仅以 $q - \epsilon$ 概率保留，采样后再通过范数重缩放恢复整体尺度。

#### （3）`dare_linear` 与 `dare_ties` 的流水线组合
在 `peft` 与 `mergekit` 中，DARE 作为前置稀疏器可与不同后端融合器自由正交组合：
- **`dare_linear`（DARE + Task Arithmetic）**：对各任务向量执行 $\text{DARE}(\tau_t, \text{density}, \text{rescale}=\text{True})$ 后，直接做加权线性求和 $\sum_t w_t \tilde{\tau}_t$；
- **`dare_ties`（DARE + TIES Consensus）**：先用 DARE 随机稀疏并重缩放替代 TIES 的确定性幅值剪枝，随后继续执行 TIES 的主导符号选举（Elect Sign）与不相交同号合并（Disjoint Merge）。

---

### 3. SLERP（球面线性插值）：超球面测地线、范数坍缩防治与共线奇点保护

#### （1）为什么在双模型合并中，线性插值（LERP）会导致“权重范数坍缩（Norm Shrinkage）”？
假设我们要以比例 $t \in [0, 1]$ 融合两个同源全量模型权重向量 $v_0, v_1 \in \mathbb{R}^d$。在高维参数空间中，同源微调后的权重行向量通常具有极其相近的 $L_2$ 模长 $\|v_0\|_2 \approx \|v_1\|_2 = R$，但方向存在夹角 $\Omega \in (0, \pi)$（即 $\cos\Omega = \frac{v_0 \cdot v_1}{\|v_0\|_2 \|v_1\|_2}$）。

如果使用标准的**线性插值（LERP / Linear Merge）**：

$$v_{\text{LERP}}(t) = (1 - t) v_0 + t v_1$$

计算其在中点 $t = 0.5$ 处的欧氏范数平方：

$$\left\| v_{\text{LERP}}(0.5) \right\|_2^2 = \frac{1}{4}\|v_0\|_2^2 + \frac{1}{4}\|v_1\|_2^2 + \frac{1}{2}\|v_0\|_2 \|v_1\|_2 \cos\Omega = \frac{R^2}{2}(1 + \cos\Omega) = R^2 \cos^2\!\left(\frac{\Omega}{2}\right)$$

$$\implies \left\| v_{\text{LERP}}(0.5) \right\|_2 = R \cos\!\left(\frac{\Omega}{2}\right) < R \quad (\forall \Omega \in (0, \pi))$$

例如，当两个微调方向正交（$\Omega = 90^\circ, \cos\Omega = 0$）时，中点权重的模长直接缩水为原来的 $\cos 45^\circ = \frac{\sqrt{2}}{2} \approx 70.71\%$！在未经过后续重训练的深层 Transformer 中，权重矩阵范数的系统性萎缩会改变 Attention Logits 的有效温度与 RMSNorm 前的特征尺度分布。

#### （2）SLERP 的球面测地线公式与 `mergekit/slerp.py` 源码级工程边界
**球面线性插值（SLERP，Shoemake, SIGGRAPH 1985）** 不沿穿过球体内部的弦（Chord）走直线，而是沿着连接 $v_0$ 与 $v_1$ 的**超球面大圆测地线（Great-Circle Geodesic）**以恒定角速度 $\Omega$ 旋转。

设插值点旋转角度为 $t\Omega$，在由 $v_0, v_1$ 张成的二维平面内作斜交分解，可得唯一保范闭式解：

$$\text{SLERP}(v_0, v_1; t) = \frac{\sin\!\big((1 - t)\Omega\big)}{\sin\Omega} v_0 + \frac{\sin(t\Omega)}{\sin\Omega} v_1, \qquad \Omega = \arccos\!\left( \frac{v_0 \cdot v_1}{\|v_0\|_2 \|v_1\|_2} \right)$$

验证其模长（当 $\|v_0\|_2 = \|v_1\|_2 = R$ 时）：

$$\left\| \text{SLERP}(v_0, v_1; t) \right\|_2^2 = \frac{R^2}{\sin^2\Omega} \left[ \sin^2((1-t)\Omega) + \sin^2(t\Omega) + 2\sin((1-t)\Omega)\sin(t\Omega)\cos\Omega \right] = R^2$$

无论 $t \in [0, 1]$ 取何值，SLERP 插值后的权重向量模长恒等于 $R$！

对照 `arcee-ai/mergekit` 官方源码（`mergekit/merge_methods/slerp.py::slerp`，第 20–78 行），工业级实现包含三项关键数值工程设计：
1. **按输出行（Per-Row / Leading Axis）独立做球面插值与分块防溢出**：
   源码第 35–36 行执行 `a = v0.reshape(v0.shape[0], -1)`，并按 `_CHUNK_ELEMENTS = 1024 * 1024` 分块计算范数，且**先将分块除以总范数 `norm_a` 再做点积**（第 58–61 行），彻底杜绝了半精度/单精度下大张量原始点积的上溢（Overflow）；
2. **共线与反平行奇点的线性回退保护（`dot_threshold = 0.9995`）**：
   当两个模型的某层权重几乎未变或完全共线时，点积 $|\cos\Omega| \to 1 \implies \Omega \to 0 \text{ 或 } \pi \implies \sin\Omega \to 0$，分母出现 $0/0$ 数值奇点！源码第 64–70 行设定阈值 `dot_threshold = 0.9995`（对应夹角约 $1.81^\circ$）：
   $$\text{coef}_0, \text{coef}_1 = \begin{cases} 1 - t, \;\; t & \text{if } |\cos\Omega| > 0.9995 \;\; (\text{回退为 LERP}) \\ \dfrac{\sin((1-t)\Omega)}{\sin\Omega}, \;\; \dfrac{\sin(t\Omega)}{\sin\Omega} & \text{otherwise} \end{cases}$$
3. **仅限恰好 2 个同构模型**：SLERP 定义在二维大圆弧上，源码 `InputContract(base=BasePolicy.REQUIRED, min_inputs=2, max_inputs=2)` 严格限制每次只能融合两个模型（若需融合多个模型，需采用层次化二叉树 SLERP 或改用 NuSLERP / Karcher Mean / TIES）。

```text
大模型无训练权重合并 (Model Merging) 主流算法演进与工程选型全景:

  [ 前置硬性约束: 待合并模型是否微调自同一个 Base Checkpoint (满足线性模式连通性)? ]
         │
         ├── 否 (异构架构或不同预训练底座) ──► 不可直接加权! 需做 Git Re-Basin 排列对齐 / FuseLLM 蒸馏 / Passthrough 拼接
         │
         └── 是 (同源 Homologous Models) ──► [ 待合并的模型数量 M 是多少? ]
                                                    │
                    ┌───────────────────────────────┴───────────────────────────────┐
                    ▼ (M = 2: 双模型精细融合, 支持逐层梯度曲线 t)                     ▼ (M >= 3: 多专家技能合成或负面能力擦除)
      ┌───────────────────────────────────┐                           ┌───────────────────────────────────┐
      │ SLERP (球面线性插值)               │                           │ 提取任务向量 τ_t = θ_t - θ_base    │
      │ • 沿超球面大圆测地线恒定角速度旋转│                           └─────────────────┬─────────────────┘
      │ • 消除 LERP 的 cos(Ω/2) 范数坍缩  │                                             │
      │ • |cos Ω| > 0.9995 自动回退 LERP  │                       [ 步骤 A: 稀疏化与重缩放预处理 (Sparsify) ]
      └───────────────────────────────────┘                                             │
                                                          ┌─────────────────────────────┼─────────────────────────────┐
                                                          ▼ (无稀疏化)                   ▼ (确定性幅值剪枝)             ▼ (随机稀疏 + 期望恢复)
                                                 ┌─────────────────┐           ┌─────────────────┐           ┌─────────────────────────┐
                                                 │ Raw Task Vector │           │ Magnitude Prune │           │ DARE / DELLA            │
                                                 │ 保留 100% 参数  │           │ 仅留 Top-k% 幅值│           │ • DARE: Bernoulli(1-p)  │
                                                 └────────┬────────┘           └────────┬────────┘           │   并乘 1/(1-p) 保期望   │
                                                          │                             │                    │ • DELLA: 按幅值排名赋概率│
                                                          └──────────────┬──────────────┴────────────────────┴────────────┬────────────┘
                                                                         │                                                │
                                                                         ▼                                                ▼
                                                    [ 步骤 B: 跨模型符号冲突消解与聚合 (Consensus & Aggregation) ]
                                                                         │
                                           ┌─────────────────────────────┴─────────────────────────────┐
                                           ▼ (直接加权线性求和: 无符号过滤)                             ▼ (主导符号选举 + 不相交同号平均)
                                ┌───────────────────────────┐                               ┌───────────────────────────┐
                                │ • Task Arithmetic (无剪枝)│                               │ • TIES-Merging (幅值剪枝) │
                                │ • DARE-Linear (随机稀疏后)│                               │ • DARE-TIES / DELLA-TIES  │
                                └───────────────────────────┘                               └───────────────────────────┘
```

| 合并算法 / 范式 | 模型数量限制 | 是否需要 $\theta_{\text{base}}$ | 稀疏化与重缩放机制 | 符号冲突消解机制 | 核心数学公式（增量或权重） | 最佳工程适用场景 |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- |
| **Linear / Model Soups** (ICML 2022) | $M \ge 2$ | 否 | 无 | 无（直接加权平均） | $\theta_{\text{new}} = \sum_{t=1}^M w_t \theta_t \;\; (\sum w_t = 1)$ | 同一任务不同超参微调 Checkpoint 平均以提升鲁棒性 |
| **SLERP** (SIGGRAPH 1985 / MergeKit) | **严格 $M = 2$** | 否（将其中之一视作端点） | 无 | 无（测地线旋转） | $\frac{\sin((1-t)\Omega)}{\sin\Omega}\theta_0 + \frac{\sin(t\Omega)}{\sin\Omega}\theta_1$ | 两个强力同源全量模型的平滑融合（支持按层配置 $t$ 曲线） |
| **Task Arithmetic** (ICLR 2023) | $M \ge 1$ | **是** | 无 | 无（正负直接抵消） | $\theta_{\text{base}} + \lambda \sum_{t=1}^M w_t (\theta_t - \theta_{\text{base}})$ | 少量正交任务叠加，或通过负权重 $-w_t$ 执行有害能力擦除 |
| **TIES-Merging** (NeurIPS 2023) | $M \ge 2$ | **是** | Top-$k\%$ 幅值剪枝（通常不重缩放） | **是**（Elect Sign + Disjoint Merge） | $\theta_{\text{base}} + \lambda \frac{\sum_{t \in \mathcal{A}_j} w_t \hat{\tau}_t^{(j)}}{|\mathcal{A}_j| \text{ 或 } \sum_{t \in \mathcal{A}_j} w_t}$ | 多领域模型（或高冲突多 LoRA）融合，消除符号抵消 |
| **DARE-Linear / DARE-TIES** (ICML 2024) | $M \ge 2$ | **是** | 随机丢弃 $p$ 并放大 $\frac{1}{1-p}$（或 $L_1$ 保范） | `dare_linear` 否 / `dare_ties` **是** | $\tilde{\tau}_t = \frac{m_t \odot \tau_t}{1-p}, \;\; m_t \sim \text{Bern}(1-p)$ | 增量冗余度极高的 SFT 模型低碰撞融合（常取 $\text{density} \in [0.1, 0.5]$） |
| **DELLA** (2024 / MergeKit) | $M \ge 2$ | **是** | 幅值升序排名概率 $q_i = q - \epsilon + 2\epsilon\tilde{r}_i$ + 保范 | 常配合 TIES 共识掩码 | $P(\text{keep } \tau^{(i)}) \propto \text{rank}(|\tau^{(i)}|)$ | 极低保留密度下兼顾高幅值特征保护与随机无偏性 |

---

### 4. Python 3 标准库实现：TIES 符号消解、DARE/DELLA 期望保持与 SLERP 仿真

下面的零依赖 Python 3 标准库代码严格对齐 Hugging Face `peft`（`src/peft/utils/merge_utils.py`）与 `arcee-ai/mergekit`（`slerp.py`、`generalized_task_arithmetic.py`、`sparsify.py`）官方源码，验证了：
1. **Task Arithmetic 符号抵消 vs TIES-Merging 三步消解**：构造 3 个模型在 4 个参数坐标上的任务向量（包含微弱噪声与剧烈正负符号冲突 $+0.70, +0.50, -0.90$），对比朴素求和的信号衰减与 TIES 剪枝、主导符号选举及不相交均值合并后的清晰特征恢复；
2. **DARE 随机稀疏重缩放 $\frac{1}{1-p}$ 的前向内积无偏期望与 DELLA 排名概率**：在 $\text{density}=0.2$（丢弃 $80\%$ 参数）下进行蒙特卡洛仿真，验证重缩放后 $\mathbb{E}[\tilde{\tau}\cdot x] \approx \tau \cdot x$，而不重缩放则缩水至 $20\%$，并精确复现 `mergekit` 的 DELLA 排名保留概率；
3. **SLERP 超球面保范插值 vs LERP 范数坍缩及共线回退保护**：验证两个模长为 $10.0$ 的正交权重向量在 $t=0.5$ 时 LERP 模长坍缩至 $7.0711$ 而 SLERP 严格保持 $10.0000$，以及当 $\cos\Omega > 0.9995$ 时自动触发线性回退。

```python
import math
import random
from typing import Dict, List, Literal


def magnitude_prune_1d(vec: List[float], density: float) -> List[float]:
    """
    对齐 huggingface/peft `magnitude_based_pruning` 与 arcee-ai/mergekit `magnitude`:
    保留绝对值最大的 top-k (k = int(density * N)) 个元素，其余置 0
    """
    n = len(vec)
    k = int(density * n)
    if k <= 0:
        return [0.0] * n
    if k >= n:
        return list(vec)
    indexed = sorted(range(n), key=lambda i: abs(vec[i]), reverse=True)
    keep = set(indexed[:k])
    return [vec[i] if i in keep else 0.0 for i in range(n)]


def ties_merge_1d(
    task_vectors: List[List[float]],
    weights: List[float],
    density: float = 0.75,
    majority_sign_method: Literal["total", "frequency"] = "total",
    normalize_by_weights: bool = False,
) -> Dict[str, List[float]]:
    """
    对齐 huggingface/peft `ties` (normalize_by_weights=False, 按保留模型数均值)
    与 arcee-ai/mergekit `GeneralizedTaskArithmeticMerge` (normalize_by_weights=True):
    Step 1 (Trim): 按幅值剪枝保留 top-k%
    Step 2 (Elect Sign): 计算每个坐标的主导符号 (+1 或 -1)
    Step 3 (Disjoint Merge): 仅聚合符号与主导符号一致的分量
    """
    m = len(task_vectors)
    d = len(task_vectors[0])
    trimmed = [magnitude_prune_1d(tv, density) for tv in task_vectors]

    effective = [
        [trimmed[t][j] * (weights[t] if normalize_by_weights else 1.0) for j in range(d)]
        for t in range(m)
    ]
    elected_signs: List[int] = []
    for j in range(d):
        if majority_sign_method == "total":
            s_val = sum(effective[t][j] for t in range(m))
        elif majority_sign_method == "frequency":
            s_val = sum(
                (1 if effective[t][j] > 0 else (-1 if effective[t][j] < 0 else 0))
                for t in range(m)
            )
        else:
            raise ValueError(f"Unknown method: {majority_sign_method}")
        elected_signs.append(1 if s_val >= 0 else -1)

    naive_sum = [
        round(sum(weights[t] * task_vectors[t][j] for t in range(m)), 4)
        for j in range(d)
    ]

    merged: List[float] = []
    for j in range(d):
        num = 0.0
        den = 0.0
        for t in range(m):
            val = trimmed[t][j]
            sgn = 1 if val > 0 else (-1 if val < 0 else 0)
            if sgn == elected_signs[j]:
                num += weights[t] * val
                den += weights[t] if normalize_by_weights else 1.0
        merged.append(
            round(
                num / max(den, 1.0)
                if not normalize_by_weights
                else (num / den if den != 0 else 0.0),
                4,
            )
        )

    return {
        "naive_task_arithmetic": naive_sum,
        "elected_signs": elected_signs,
        "ties_merged": merged,
    }


def simulate_dare_expectation_and_della(
    delta: List[float],
    x_input: List[float],
    density: float = 0.2,
    epsilon: float = 0.15,
    trials: int = 4000,
    seed: int = 42,
) -> Dict[str, object]:
    """
    验证:
    1. DARE (Yu et al., ICML 2024 & peft `random_pruning`):
       保留率 q = density = 1 - p, 重缩放 1/q 后前向内积期望无偏, 不重缩放则缩水为 q 倍
    2. DELLA (Deep et al., 2024 & mergekit `della_magprune`):
       按幅值升序排名分配保留概率 probs = (density - epsilon) + rank_norm * 2 * epsilon
    """
    rng = random.Random(seed)
    exact_dot = sum(d * x for d, x in zip(delta, x_input))
    rescaled_dots = []
    unscaled_dots = []
    for _ in range(trials):
        r_dot = 0.0
        u_dot = 0.0
        for d_val, x_val in zip(delta, x_input):
            if rng.random() < density:
                u_dot += d_val * x_val
                r_dot += (d_val / density) * x_val
        rescaled_dots.append(r_dot)
        unscaled_dots.append(u_dot)

    n = len(delta)
    sorted_indices = sorted(range(n), key=lambda i: abs(delta[i]))
    ranks = [0] * n
    for pos, idx in enumerate(sorted_indices):
        ranks[idx] = pos + 1
    min_r, max_r = min(ranks), max(ranks)
    della_probs = [
        round((density - epsilon) + ((r - min_r) / (max_r - min_r)) * 2.0 * epsilon, 4)
        for r in ranks
    ]
    return {
        "exact_dot": round(exact_dot, 4),
        "dare_rescaled_mean": round(sum(rescaled_dots) / trials, 4),
        "dare_unscaled_mean": round(sum(unscaled_dots) / trials, 4),
        "della_keep_probs": della_probs,
    }


def compare_lerp_vs_slerp(
    v0: List[float],
    v1: List[float],
    t: float = 0.5,
    dot_threshold: float = 0.9995,
) -> Dict[str, object]:
    """
    严格对齐 arcee-ai/mergekit `mergekit/merge_methods/slerp.py::slerp`:
    对比等模长正交/大夹角向量在 t=0.5 时 LERP 的范数坍缩与 SLERP 的测地线保范特性,
    以及 |dot| > dot_threshold 时的共线线性回退保护
    """
    norm0 = math.sqrt(sum(a * a for a in v0))
    norm1 = math.sqrt(sum(b * b for b in v1))
    dot = sum((a / norm0) * (b / norm1) for a, b in zip(v0, v1))
    dot = max(-1.0, min(1.0, dot))

    lerp_vec = [(1.0 - t) * a + t * b for a, b in zip(v0, v1)]
    lerp_norm = math.sqrt(sum(c * c for c in lerp_vec))

    if abs(dot) > dot_threshold:
        coef_a, coef_b = 1.0 - t, t
        used_fallback = True
    else:
        theta = math.acos(dot)
        sin_theta = math.sin(theta)
        coef_a = math.sin((1.0 - t) * theta) / sin_theta
        coef_b = math.sin(t * theta) / sin_theta
        used_fallback = False

    slerp_vec = [coef_a * a + coef_b * b for a, b in zip(v0, v1)]
    slerp_norm = math.sqrt(sum(c * c for c in slerp_vec))
    return {
        "input_norm": round(norm0, 4),
        "cos_theta": round(dot, 4),
        "lerp_norm": round(lerp_norm, 4),
        "slerp_norm": round(slerp_norm, 4),
        "norm_shrink_ratio": round(lerp_norm / slerp_norm, 4),
        "used_fallback": used_fallback,
    }


# --- 1. 验证 TIES-Merging 消除小幅值噪声与正负符号冲突 ---
tv_list = [
    [0.80, 0.70, -0.60, 0.04],
    [0.60, 0.50, -0.80, -0.03],
    [-0.05, -0.90, 0.02, -0.50],
]
ties_res = ties_merge_1d(
    tv_list, weights=[1.0, 1.0, 1.0], density=0.75, majority_sign_method="total"
)
assert ties_res["naive_task_arithmetic"] == [1.35, 0.30, -1.38, -0.49]
assert ties_res["elected_signs"] == [1, 1, -1, -1]
assert ties_res["ties_merged"] == [0.70, 0.60, -0.70, -0.50]

# --- 2. 验证 DARE 1/(1-p) 无偏期望恢复与 DELLA 幅值自适应保留概率 ---
delta_demo = [0.02, -0.15, 0.40, -0.85, 1.20]
x_demo = [1.5, -2.0, 0.8, -1.2, 0.5]
dare_res = simulate_dare_expectation_and_della(
    delta_demo, x_demo, density=0.2, epsilon=0.15
)
assert abs(dare_res["dare_rescaled_mean"] - dare_res["exact_dot"]) < 0.08
assert abs(dare_res["dare_unscaled_mean"] - dare_res["exact_dot"] * 0.2) < 0.05
assert dare_res["della_keep_probs"] == [0.05, 0.125, 0.2, 0.275, 0.35]

# --- 3. 验证 SLERP 球面测地线保范 vs LERP 范数坍缩 & 共线保护 ---
ortho_res = compare_lerp_vs_slerp([10.0, 0.0], [0.0, 10.0], t=0.5)
collinear_res = compare_lerp_vs_slerp([10.0, 0.0], [9.9999, 0.01], t=0.5)
assert ortho_res["slerp_norm"] == 10.0 and ortho_res["lerp_norm"] == 7.0711
assert ortho_res["used_fallback"] is False
assert collinear_res["used_fallback"] is True

print(
    f"1. TIES vs Naive: naive={ties_res['naive_task_arithmetic']}, "
    f"signs={ties_res['elected_signs']}, ties={ties_res['ties_merged']}"
)
print(
    f"2. DARE & DELLA: exact_dot={dare_res['exact_dot']:.4f}, "
    f"dare_rescaled={dare_res['dare_rescaled_mean']:.4f}, "
    f"dare_unscaled={dare_res['dare_unscaled_mean']:.4f}, "
    f"della_probs={dare_res['della_keep_probs']}"
)
print(
    f"3. LERP vs SLERP: input_norm={ortho_res['input_norm']:.2f}, "
    f"lerp_norm={ortho_res['lerp_norm']:.4f}, slerp_norm={ortho_res['slerp_norm']:.4f}, "
    f"shrink={ortho_res['norm_shrink_ratio']:.4f}, collinear_fallback={collinear_res['used_fallback']}"
)
print("All Task Arithmetic, TIES, DARE, DELLA, and SLERP assertions passed!")
```

实际运行输出：

```text
1. TIES vs Naive: naive=[1.35, 0.3, -1.38, -0.49], signs=[1, 1, -1, -1], ties=[0.7, 0.6, -0.7, -0.5]
2. DARE & DELLA: exact_dot=2.2700, dare_rescaled=2.3101, dare_unscaled=0.4620, della_probs=[0.05, 0.125, 0.2, 0.275, 0.35]
3. LERP vs SLERP: input_norm=10.00, lerp_norm=7.0711, slerp_norm=10.0000, shrink=0.7071, collinear_fallback=True
All Task Arithmetic, TIES, DARE, DELLA, and SLERP assertions passed!
```

---

## 延伸 / 追问

**追问 1：在使用 Hugging Face `peft` 的 `add_weighted_adapter` 合并多个 LoRA 适配器（如 `combination_type="linear"` vs `"cat"` vs `"ties"` vs `"dare_ties"`）时，为什么 `"linear"` 直接对低秩矩阵 $A_i, B_i$ 求加权平均会产生严重的“交叉项污染（Cross-Term Interference）”，而转换到全秩增量空间 $\Delta W_i = B_i A_i$ 或使用 `"cat"` 拼接才能保持真实算术语义？**
1. **低秩因子分别求和的“交叉项泄漏”数学本质**：
   对于第 $i$ 个 LoRA 适配器，其真实注入线性层的全秩权重增量为 $\Delta W_i = s_i B_i A_i$（其中 $s_i = \frac{\alpha_i}{r_i}$）。如果我们试图在不展开全秩矩阵的情况下，直接令合并后的低秩矩阵为 $\bar{B} = \sum_{i=1}^M w_i B_i, \; \bar{A} = \sum_{i=1}^M w_i A_i$，则合并后的实际等效权重增量为：
   $$\Delta W_{\text{factor-avg}} = \bar{B}\bar{A} = \left(\sum_{i=1}^M w_i B_i\right)\left(\sum_{j=1}^M w_j A_j\right) = \underbrace{\sum_{i=1}^M w_i^2 B_i A_i}_{\text{真实平方加权项}} + \underbrace{\sum_{i \neq j} w_i w_j B_i A_j}_{\text{跨适配器伪交叉项!}}$$
   由于不同 LoRA 独立训练时其内部低秩隐空间（秩 $r$ 维坐标系）存在任意正交旋转变换，$B_i$ 的列与 $A_j$（$i \neq j$）的行毫无对应关系，交叉项 $\sum_{i \neq j} w_i w_j B_i A_j$ 纯属高幅值随机噪声！
2. **PEFT 源码中的三种工程解法与权衡**：
   - **`combination_type="cat"`（秩拼接，零交叉污染但秩膨胀）**：将所有适配器的缩放矩阵在秩维度拼接：$B_{\text{cat}} = [w_1 s_1 B_1, \dots, w_M s_M B_M] \in \mathbb{R}^{d_{\text{out}} \times (Mr)}$，$A_{\text{cat}} = [A_1^\top, \dots, A_M^\top]^\top \in \mathbb{R}^{(Mr) \times d_{\text{in}}}$，此时 $B_{\text{cat}} A_{\text{cat}} = \sum_{i=1}^M w_i s_i B_i A_i$ 严格等于精确的 Task Arithmetic，代价是合并后 LoRA 的秩变为 $M \cdot r$；
   - **`combination_type="svd"` / `"ties_svd"` / `"dare_ties_svd"`（全秩展开 $\to$ TIES/DARE 融合 $\to$ 截断 SVD 压回目标秩 $r$）**：先计算每个适配器的乘积增量 $\tau_i = s_i B_i A_i \in \mathbb{R}^{d_{\text{out}} \times d_{\text{in}}}$，在全秩空间执行 TIES 或 DARE-TIES 得到 $\tau_{\text{merged}}$，随后对 $\tau_{\text{merged}} = U \Sigma V^\top$ 做截断奇异值分解，令 $B_{\text{new}} = U_{:, :r}\sqrt{\Sigma_{:r, :r}}, \; A_{\text{new}} = \sqrt{\Sigma_{:r, :r}}V_{:, :r}^\top$，从而在不增加推理秩的前提下消除交叉项污染。

**追问 2：当微调模型相较于底座模型新增了特殊词元（Added Special Tokens，如 Chat 模板中的 `<|im_start|>`、`<tool_call>`）导致词表大小 `vocab_size` 不一致，或者参数增量在局部出现极端离群值（Outliers）时，模型合并会遇到什么故障？工程上如何通过 Tokenizer 对齐与 `magnitude_outliers` / `breadcrumbs` 处理？**
1. **词表维度失配（Tokenizer & Embedding Mismatch）的对齐协议**：
   当模型 A 的词表为 $128256$、模型 B 扩展了 $4$ 个特殊 Token 变为 $128260$ 时，`embed_tokens.weight` 与 `lm_head.weight` 张量形状不一致，直接运行矩阵减法会触发维度报错。即使两者同为 $128260$，若相同 Token ID 对应的文本字符串不同，直接平均 Embedding 也会摧毁特殊指令识别。`mergekit` 的标准处理协议是：先构建联合目标词表，对共同的基础词表区段执行标准 Task Arithmetic / TIES / SLERP，而对某个专家模型独有的新增 Token 行，采用均值初始化或直接从该专家模型 Passthrough 拷贝（并在 `mergekit` 配置中显式声明 `tokenizer_source: union` 或 `base`）。
2. **极端大离群值干扰与 Model Breadcrumbs（`magnitude_outliers`）**：
   TIES 仅剪除小幅值尾部，认为幅值越大越重要；然而 Davari et al.（*Model Breadcrumbs*, ECCV 2024，对应 `mergekit/sparsify.py::magnitude_outliers`，第 81–115 行）发现，微调增量中位于最顶端 $\gamma$ 比例（如前 $1\%$）的**极端大离群值（Extreme Outliers）**往往是对特定微调批次的过拟合，合并进通用底座后会破坏其他任务的激活分布。`magnitude_outliers` 通过双向截尾——先切除前 $\gamma$（如 $1\%$）的最大绝对值离群点，再切除底部 $1 - \text{density} - \gamma$ 的微小噪声，仅保留中间核心频段的增量，显著提升了多任务合并的稳健性。

**追问 3：除了同构合并（Homologous Weight Averaging），开源社区常说的“缝合怪模型（Frankenmerging / Passthrough）”与“免训练混合专家合成（Training-Free MoE / FrankenMoE，如 `mergekit-moe`）”是什么原理？它们的工程收益与能力边界在哪里？**
1. **层间堆叠缝合（Passthrough / Frankenmerging，如將 70B 扩增为 120B）**：
   不同于在相同层号之间对权重求加权平均，Passthrough 直接将模型 A 的第 $[0, 32)$ 层与模型 B（或模型 A 自身）的第 $[16, 48)$ 层在深度维度上交错串联起来。由于微调后的同源模型相邻层之间的残差流表征（Residual Stream Representation）具有高度的平滑连续性，重复插入中间层相当于在隐空间延长了特征精炼的常微分方程（ODE）积分步数。这能以零训练成本增强复杂角色扮演或长链路感知，但会实打实地增加模型总参数量、KV Cache 显存与推理延迟，且在交界层容易出现激活范数跳变。
2. **免训练 MoE 组装（FrankenMoE / Upcycling to MoE via `mergekit-moe`）**：
   给定一个通用底座模型与 $K$ 个同源垂直领域稠密微调模型（如数学、代码、医疗、法律），保持共享的 Self-Attention 层权重（可通过 TIES/SLERP 合并），将每个稠密模型的 FFN（MLP）层直接作为 MoE 架构中的一个独立专家（Expert $1 \dots K$）。至于门控路由器（Router Gate $W_g \in \mathbb{R}^{K \times d_{\text{model}}}$），在完全无训练的冷启动阶段，可以通过计算各领域代表性正面 Prompt 与负面 Prompt 在该层输入隐藏状态的平均聚类中心（Centroid Vectors）并做归一化来直接初始化 $W_g$ 的行向量！这样既完全避免了多专家 FFN 权重合并时的参数干扰，又利用稀疏 Top-2 激活控制了单 Token 的推理 FLOPs。

---

## 常见误区

- **误区一：“只要两个大模型的参数量一样、架构类名相同（比如都是 7B 的 LlamaForCausalLM 结构），就可以用 SLERP 或 TIES 把它们的权重合并在一起，集百家之长。”**
  事实：**同架构（Same Architecture）绝不等于同源（Homologous）！** 如果两个 7B 模型是从不同预训练随机种子训出来的（或者一个是 DeepSeek-7B、另一个是 Mistral-7B 改了词表与层宽后强行对齐形状），由于神经网络隐藏层神经元的排列对称性（Permutation Invariance），模型 A 的第 $100$ 号神经元与模型 B 的第 $100$ 号神经元语义完全正交。直接做权重算术会落入损失曲面的高能壁垒区，产出彻底报废的乱码模型。无训练权重合并的硬性前提是**所有参与合并的模型必须源自同一个预训练祖先检查点（Shared Base Checkpoint）**。
- **误区二：“DARE 随机把 $90\%$ 的微调参数增量置零，就等于把整个大模型变成了 $90\%$ 稀疏度的稀疏网络，从而能在推理时直接获得 10 倍的矩阵乘法加速与显存压缩。”**
  事实：**DARE 稀疏化的是微调增量 $\tau_t = \theta_t - \theta_{\text{pre}}$，而不是最终的模型权重 $\theta_{\text{merged}}$！** 当稀疏化后的增量 $\tilde{\tau}_t$ 被加回到稠密的预训练底座权重 $\theta_{\text{pre}}$ 上（$\theta_{\text{merged}} = \theta_{\text{pre}} + \sum_t \tilde{\tau}_t$）之后，由于 $\theta_{\text{pre}}$ 本身是 $100\%$ 稠密的，最终得到的合并模型依然是一个标准的稠密张量！DARE 稀疏化的真正目的是**在合并瞬间大幅降低多个任务增量在同一坐标上发生碰撞干扰的概率**，或者用于稀疏存储/传输 Delta Checkpoints，而不会减少底座模型本身的推理计算量。
- **误区三：“TIES-Merging 和 DARE 都包含剪枝（Pruning）操作，所以它们是互相排斥的替代关系，用了一个就不能用另一个。”**
  事实：**DARE（随机丢弃 + $\frac{1}{1-p}$ 重缩放）作用于单模型增量的预处理阶段，而 TIES 的核心贡献（Elect Sign 主导符号选举 + Disjoint Merge 不相交同号平均）作用于跨模型的冲突消解阶段，两者完全正交且天然互补！** 在 Hugging Face `peft` 与 `arcee-ai/mergekit` 中，专门提供了结合两者的 `dare_ties`（以及结合 DELLA 与 TIES 的 `della`）方法：先用 DARE/DELLA 稀疏化并保持前向激活期望，再用 TIES 过滤剩余碰撞坐标上的反号分量。

---

## 参考

- 选题线索：[f-o-x11/dreaming-press (`content/posts/model-merging-ties-vs-dare-vs-slerp.md`)](https://github.com/f-o-x11/dreaming-press/blob/2c2eb9c90e15cce501cc8296ab736a34829b8487/content/posts/model-merging-ties-vs-dare-vs-slerp.md)（固定 commit `2c2eb9c`）与 [nibzard/awesome-agentic-patterns (`patterns/merged-code-language-skill-model.md`)](https://github.com/nibzard/awesome-agentic-patterns/blob/6b766b8c5b5e183e39ec16ae8c1d0b49769470f5/patterns/merged-code-language-skill-model.md)（固定 commit `6b766b8`），独立推导数学机制并扩展源码级对比。
- Ilharco et al., [Editing Models with Task Arithmetic](https://arxiv.org/abs/2212.04089)，ICLR 2023：任务向量 $\tau_t = \theta_t - \theta_{\text{pre}}$ 定义、多任务线性叠加与负权重能力擦除（Task Negation）。
- Yadav et al., [TIES-Merging: Resolving Interference When Merging Models](https://arxiv.org/abs/2306.01708)，NeurIPS 2023，及 Hugging Face 官方源码 [huggingface/peft (`src/peft/utils/merge_utils.py`)](https://github.com/huggingface/peft/blob/5d3916b304a24734e5acb37116b8e3bcf0c9eae4/src/peft/utils/merge_utils.py)（固定 commit `5d3916b`）：冗余参数剪枝（Trim）、主导符号选举（Elect Sign）与不相交合并（Disjoint Merge）实现。
- Yu et al., [Language Models are Super Mario: Absorbing Abilities from Homologous Models as a Free Lunch (DARE)](https://arxiv.org/abs/2311.03099)，ICML 2024：微调增量随机伯努利丢弃与 $\frac{1}{1-p}$ 无偏期望恢复证明。
- Goddard et al., [Arcee's MergeKit: A Toolkit for Merging Large Language Models](https://arxiv.org/abs/2403.13257)，2024，及官方源码 [arcee-ai/mergekit (`mergekit/merge_methods/slerp.py`, `generalized_task_arithmetic.py`, `sparsify.py`)](https://github.com/arcee-ai/mergekit/blob/0f1423ecf0f06f46f17b045b333b6c445705390e/mergekit/merge_methods/slerp.py)（固定 commit `0f1423e`）：SLERP 球面插值与共线回退、DELLA 幅值排名稀疏化与广义任务算术实现。
- Deep et al., [DELLA-Merging: Reducing Interference in Model Merging through Magnitude-Based Sampling](https://arxiv.org/abs/2406.11617)，2024，及 Wortsman et al., [Model Soups: Averaging Weights of Multiple Fine-Tuned Models Improves Accuracy Without Increasing Inference Time](https://arxiv.org/abs/2203.05482)，ICML 2022。

来源访问与示例核验日期：**2026-11-14**。仅执行标准库下 Task Arithmetic / TIES 符号消解、DARE 无偏期望与 DELLA 排名概率、SLERP 测地线保范与共线回退的数值验证，未运行多卡大模型权重合并基准评测。
