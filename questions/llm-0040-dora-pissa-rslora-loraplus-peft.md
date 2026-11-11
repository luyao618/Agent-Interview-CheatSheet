---
id: llm-0040
title: LoRA 进阶演进（DoRA、PiSSA、rsLoRA 与 LoRA+）是如何通过权重幅度-方向解耦、主奇异值分解初始化、秩稳定缩放与非对称学习率突破参数高效微调瓶颈的？
category: llm
tags: [peft, dora, pissa, rslora, loraplus, corda]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开 PEFT 与大模型微调面试题库（ARIS-in-AI-Offer / Awesome-AGI）扩展改编；DoRA（ICML 2024）、PiSSA（NeurIPS 2024）、rsLoRA（2023）、LoRA+（ICML 2024）及 Hugging Face PEFT 源码核实（见参考）
status: published
updated: 2026-11-12
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-11-12
    updated: 2026-11-12
---

## 问题

在参数高效微调（PEFT）中，经典 LoRA（$\mathbf{W}' = \mathbf{W}_0 + \frac{\alpha}{r}\mathbf{B}\mathbf{A}$）凭借低显存开销与可合并的零推理延迟成为工业界标准。然而在代码生成、数学推理与专业领域知识注入等复杂任务中，经典 LoRA 与全量微调（Full Fine-Tuning, FT）之间仍存在显著的能力差距（Capacity Gap）与收敛瓶颈：包括幅度与方向更新强耦合、随机-零初始化导致早期梯度落入噪声子空间、高秩（Large $r$）下梯度坍缩，以及大维度下 $\mathbf{A}/\mathbf{B}$ 两矩阵特征学习尺度失衡。围绕这四大短板，学术界与开源社区演进出了 **DoRA（ICML 2024）**、**PiSSA（NeurIPS 2024）**、**rsLoRA（2023）** 与 **LoRA+（ICML 2024）** 等核心变体，并均已集成进 Hugging Face `peft` 官方库。

请深入剖析以下三个核心问题：
1. **权重幅度-方向解耦（DoRA 机制与算子细节）**：全量微调与经典 LoRA 在权重矩阵的“幅度（Magnitude）”与“方向（Direction）”更新轨迹上有何本质差异？**DoRA（Weight-Decomposed Low-Rank Adaptation）**是如何将预训练权重按输出通道分解为可训练幅度向量 $\mathbf{m}$ 与低秩方向增量 $\Delta \mathbf{V} = \mathbf{B}\mathbf{A}$ 的？为什么在反向传播与 Hugging Face `peft` 实现中必须将分母方向范数 $\|\mathbf{V} + \frac{\alpha}{r}\mathbf{B}\mathbf{A}\|_c$ 从计算图中剥离（`.detach()`）？在执行 `merge()` 与 `unmerge()` 时为什么必须缓存原始未合并范数？
2. **主奇异子空间初始化与热插拔转换（PiSSA vs 随机初始化）**：为什么经典 LoRA 的高斯随机 $\mathbf{A}_0$ 与全零 $\mathbf{B}_0$ 初始化在训练初期收敛缓慢？**PiSSA（Principal Singular Values and Singular Vectors Adaptation）**是如何通过对 $\mathbf{W}_0$ 做奇异值分解（SVD），将前 $r$ 个主奇异分量放入可训练的 $\mathbf{B}_0, \mathbf{A}_0$ 并冻结残差矩阵 $\mathbf{W}_{\text{res}}$ 的？由于 PiSSA 修改了基座权重 $\mathbf{W}_0 \to \mathbf{W}_{\text{res}}$，训练完成后如何通过 **秩翻倍转换（`subtract_mutated_init`，$r \to 2r$）** 将其无损还原为直接挂载在原始基座 $\mathbf{W}_0$ 上的标准 LoRA 适配器？
3. **高秩缩放坍缩与非对称优化动力学（rsLoRA 与 LoRA+）**：为什么当把 LoRA 的秩 $r$ 从 $8$ 增大到 $256$ 或 $512$ 时，经典缩放因子 $\gamma_r = \frac{\alpha}{r}$ 会引发梯度消失与有效学习率坍缩？**rsLoRA** 为什么证明应当改用 $\gamma_r = \frac{\alpha}{\sqrt{r}}$？此外，在网络宽度 $d \to \infty$ 的算子尺度分析下，为什么给 $\mathbf{A}$ 和 $\mathbf{B}$ 设相同的学习率会导致特征学习退化？**LoRA+** 是如何通过设置非对称学习率 $\eta_B = \lambda \eta_A$（$\lambda \gg 1$）加速收敛的？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-11-12

**LoRA 进阶演进的本质，是从“空间参数化解耦”、“初始优化子空间对齐”与“高秩/宽网络尺度缩放”三个正交维度消除低秩微调对全量微调的逼近误差：（1）DoRA 针对经典 LoRA 幅度变化 $\Delta M$ 与方向变化 $\Delta D$ 呈强正相关耦合、难以像全量微调那样做“大方向微调伴随小幅度或负幅度微调”的结构缺陷，借鉴 Weight Normalization 将权重按输出通道分解为 $\mathbf{W}' = \operatorname{diag}(\mathbf{m}) (\mathbf{V}+\Delta \mathbf{V}) / \|\mathbf{V}+\Delta \mathbf{V}\|_r$，并在反向传播时对分母范数做停止梯度（`weight_norm.detach()`）以消除高维雅可比耦合与额外激活显存开销，推理前仍可无损折算回单一矩阵实现零延迟；（2）PiSSA 针对经典 LoRA 在训练起点 $\mathbf{B}_0=\mathbf{0}$ 处梯度受随机矩阵 $\mathbf{A}_0$ 支配而漫游在平坦奇异尾部的问题，对 $\mathbf{W}_0$ 做 SVD 提取前 $r$ 个最大奇异值与奇异向量初始化 $\mathbf{B}_0, \mathbf{A}_0$，同时令冻结基座保存残差 $\mathbf{W}_{\text{res}} = \mathbf{W}_0 - s \mathbf{B}_0 \mathbf{A}_0$，并在微调后通过分块拼接 $\mathbf{A}' = [\mathbf{A}; \mathbf{A}_0] \in \mathbb{R}^{2r \times d_{\text{in}}}$、$\mathbf{B}' = [\mathbf{B}, -\mathbf{B}_0] \in \mathbb{R}^{d_{\text{out}} \times 2r}$ 将增量 $\Delta \mathbf{W} = s(\mathbf{B}\mathbf{A} - \mathbf{B}_0\mathbf{A}_0)$ 无损转换为挂载在原始 $\mathbf{W}_0$ 上的秩 $2r$ 标准 LoRA；（3）rsLoRA 证明由中心极限定理，$r$ 个独立秩-1 分量之和 $\sum_{k=1}^r \mathbf{b}_k \mathbf{a}_k^\top$ 的方差与 $r$ 成正比、标准差与 $\sqrt{r}$ 成正比，唯有取 $\gamma_r = \alpha/\sqrt{r}$ 才能在 $r \to \infty$ 时维持前向激活与反向梯度的非退化 $O(1)$ 尺度；而 LoRA+ 基于无限宽神经网络（$\mu\text{P}$）尺度理论指出，降维矩阵 $\mathbf{A} \in \mathbb{R}^{r \times d_{\text{in}}}$ 与升维矩阵 $\mathbf{B} \in \mathbb{R}^{d_{\text{out}} \times r}$ 在输入维度 $d_{\text{in}} \gg r$ 下存在天然的算子范数不对称，必须令 $\eta_B = \lambda \eta_A$（典型 $\lambda \in [8, 16]$）才能让 $\mathbf{A}\mathbf{x}$ 与 $\mathbf{B}$ 同步对输出产生 $\Theta(1)$ 的有效特征更新。**

在深入推导之前，建议先结合题库内已有的相关题目建立系统视图：关于经典 LoRA 的低秩矩阵分解基础、可训练参数计算与零延迟合并原理，请参阅 [llm-0001](llm-0001-lora-fine-tuning.md)；关于何时应选择 Prompt、RAG、PEFT 微调还是全量继续预训练的工程决策边界，请参阅 [llm-0014](llm-0014-prompt-rag-finetuning-choice.md)；关于 Base 模型通过 Chat Template 与 SFT 对齐的完整链路，请参阅 [llm-0009](llm-0009-base-chat-template-sft.md)；关于在 SFT 之后如何进一步通过 DPO 或 PPO 进行偏好对齐，请参阅 [llm-0021](llm-0021-dpo-vs-ppo-preference-optimization.md)；关于训练后量化（GPTQ / AWQ / SmoothQuant）与部署显存预算估算，请参阅 [llm-0035](llm-0035-ptq-gptq-awq-smoothquant.md) 与 [llm-0016](llm-0016-quantization-local-memory-budget.md)。

---

### 1. DoRA（Weight-Decomposed Low-Rank Adaptation）：幅度-方向解耦与算子级剖析

#### （1）为什么经典 LoRA 在复杂任务上弱于全量微调？幅度与方向的耦合分析
设线性层权重为 $\mathbf{W} \in \mathbb{R}^{d_{\text{out}} \times d_{\text{in}}}$（遵循 PyTorch `nn.Linear.weight` 的 `[out_features, in_features]` 布局，每一行 $\mathbf{w}_i^\top \in \mathbb{R}^{1 \times d_{\text{in}}}$ 代表第 $i$ 个输出神经元的权重向量）。对于任意权重矩阵 $\mathbf{W}$，我们可以将其逐行（Per-Output Channel）唯一分解为**幅度向量（Magnitude Vector）** $\mathbf{m} \in \mathbb{R}^{d_{\text{out}}}$ 与**单位方向矩阵（Unit Direction Matrix）** $\mathbf{D} \in \mathbb{R}^{d_{\text{out}} \times d_{\text{in}}}$：

$$m_i = \|\mathbf{w}_i\|_2 = \sqrt{\sum_{j=1}^{d_{\text{in}}} W_{i,j}^2}, \qquad \mathbf{d}_i = \frac{\mathbf{w}_i}{\|\mathbf{w}_i\|_2}, \qquad \mathbf{W} = \operatorname{diag}(\mathbf{m}) \mathbf{D}$$

**DoRA**（Liu et al., ICML 2024）定义了微调后权重 $\mathbf{W}_t$ 相对于预训练权重 $\mathbf{W}_0$ 的平均幅度变化量 $\Delta M_t$ 与平均方向变化量 $\Delta D_t$（基于余弦距离）：

$$\Delta M_t = \frac{1}{d_{\text{out}}} \sum_{i=1}^{d_{\text{out}}} \left| m_{t,i} - m_{0,i} \right|, \qquad \Delta D_t = \frac{1}{d_{\text{out}}} \sum_{i=1}^{d_{\text{out}}} \left( 1 - \frac{\langle \mathbf{w}_{t,i}, \mathbf{w}_{0,i} \rangle}{\|\mathbf{w}_{t,i}\|_2 \|\mathbf{w}_{0,i}\|_2} \right)$$

通过对各个训练检查点的回归斜率统计，DoRA 揭示了一个根本差异：
- **全量微调（Full Fine-Tuning）呈现出负相关或微小幅度调整下的精细方向旋转**：预训练权重的范数分布本身已经高度适应下游激活尺度，因此全量微调往往在保持幅度变化 $\Delta M_t$ 较小（甚至略微减小）的同时，灵活地大幅旋转权重方向 $\Delta D_t$；
- **经典 LoRA 呈现出强正比例耦合（Proportional Coupling）**：由于经典 LoRA 直接做加法 $\mathbf{W}_{\text{LoRA}} = \mathbf{W}_0 + s \mathbf{B}\mathbf{A}$，低秩增量 $s\mathbf{B}\mathbf{A}$ 必须同时承担“改变向量长度”和“旋转向量角度”两项任务。在梯度下降中，要让方向发生显著旋转，往往不可避免地把权重范数 $\|\mathbf{w}_i\|_2$ 一并推高（反之亦然），导致优化器在低秩子空间中难以独立执行纯粹的方向微调。

#### （2）DoRA 的前向传播公式、停止梯度（`detach`）与 Hugging Face PEFT 实现
为了解耦幅度与方向，DoRA 冻结方向基底 $\mathbf{V} = \mathbf{W}_0 \in \mathbb{R}^{d_{\text{out}} \times d_{\text{in}}}$，仅用低秩旁路 $\Delta \mathbf{V} = \mathbf{B}\mathbf{A}$ 更新**方向分子**，同时引入一个仅有 $d_{\text{out}}$ 个标量的可训练参数向量 $\mathbf{m} \in \mathbb{R}^{d_{\text{out}}}$（初始化为 $m_i^{(0)} = \|\mathbf{w}_{0,i}\|_2$，而 $\mathbf{B}_0 = \mathbf{0}$，保证 $t=0$ 时 $\mathbf{W}'^{(0)} \equiv \mathbf{W}_0$）：

$$\mathbf{W}'_{\text{DoRA}} = \operatorname{diag}(\mathbf{m}) \, \frac{\mathbf{V} + s \Delta \mathbf{V}}{\|\mathbf{V} + s \Delta \mathbf{V}\|_r} = \operatorname{diag}\!\left(\frac{\mathbf{m}}{\|\mathbf{W}_0 + s \mathbf{B}\mathbf{A}\|_r}\right) (\mathbf{W}_0 + s \mathbf{B}\mathbf{A})$$

其中 $\|\cdot\|_r$ 表示沿输入维度（`dim=1`）求每一行的 $L_2$ 范数，缩放系数 $s = \frac{\alpha}{r}$（或 rsLoRA 的 $\frac{\alpha}{\sqrt{r}}$）。

结合 Hugging Face `peft` 官方源码（`src/peft/tuners/lora/dora.py::DoraLinearLayer` 与 `src/peft/tuners/lora/variants.py::DoraLinearVariant`），DoRA 在工程实现中有三个必考细节：
1. **为什么分母范数 $\|\mathbf{V} + s\Delta \mathbf{V}\|_r$ 必须调用 `.detach()`（DoRA 论文 Section 4.3）？**
   若对分母中的 $\|\mathbf{V}'\|_r$ 正常求导（其中 $\mathbf{V}' = \mathbf{V} + s\Delta \mathbf{V}$），则对第 $i$ 行方向增量的梯度为投影算子：
   $$\frac{\partial \mathcal{L}}{\partial \mathbf{v}'_i} = \frac{m_i}{\|\mathbf{v}'_i\|_2} \left( \mathbf{I} - \frac{\mathbf{v}'_i {\mathbf{v}'_i}^\top}{\|\mathbf{v}'_i\|_2^2} \right) \frac{\partial \mathcal{L}}{\partial \mathbf{w}'_i}$$
   这不仅要求在反向传播图里保留尺寸高达 $[d_{\text{out}}, d_{\text{in}}]$ 的完整中间权重张量 $\mathbf{V}'$（导致训练激活显存暴增约 $20\%\sim 30\%$），还会引入复杂的跨通道雅可比耦合。DoRA 论文 Section 4.3 证明：**在前向传播中动态重算 `weight_norm = ||W_0 + s * (B @ A).detach()||_r`，但将其通过 `weight_norm = weight_norm.detach()` 视为常数剥离出反向计算图**，此时梯度简化为纯净的逐通道缩放：
   $$\frac{\partial \mathcal{L}}{\partial \mathbf{v}'_i} = \frac{m_i}{\operatorname{sg}(\|\mathbf{v}'_i\|_2)} \frac{\partial \mathcal{L}}{\partial \mathbf{w}'_i}, \qquad \frac{\partial \mathcal{L}}{\partial m_i} = \frac{\langle \frac{\partial \mathcal{L}}{\partial \mathbf{w}'_i}, \, \mathbf{v}'_i \rangle}{\operatorname{sg}(\|\mathbf{v}'_i\|_2)}$$
   这一设计在不损失任何微调精度的前提下，将 DoRA 的反向显存开销拉回到与普通 LoRA 几乎一致的水平！
2. **如何在不实例化合并矩阵的前提下高效计算 `forward`？**
   在 `DoraLinearLayer.forward` 中，基座层已经算出了无偏置主路输出 $\mathbf{h}_{\text{base}} = \mathbf{x} \mathbf{W}_0^\top$，旁路算出了 $\mathbf{h}_{\text{lora}} = (\mathbf{x} \mathbf{A}^\top) \mathbf{B}^\top$。令逐输出通道的幅度-范数比向量为 $\boldsymbol{\rho} = \frac{\mathbf{m}}{\operatorname{sg}(\|\mathbf{W}_0 + s \mathbf{B}\mathbf{A}\|_r)} \in \mathbb{R}^{d_{\text{out}}}$（源码中的 `mag_norm_scale`），则总输出可写为基底输出加上增量修正项 `result_dora`：
   $$\mathbf{h}_{\text{DoRA}} = \boldsymbol{\rho} \odot (\mathbf{h}_{\text{base}} + s \mathbf{h}_{\text{lora}}) = \mathbf{h}_{\text{base}} + \underbrace{(\boldsymbol{\rho} - \mathbf{1}) \odot \mathbf{h}_{\text{base}} + \boldsymbol{\rho} \odot (s \mathbf{h}_{\text{lora}})}_{\text{PEFT 源码中的 }\texttt{result\_dora}}$$
   从而复用了基座的矩阵乘结果（包括 4-bit QDoRA 反量化算子输出），避免了重复执行高维矩阵乘法。
3. **为什么 `DoraLinearVariant.unmerge` 必须读取缓存的 `weight_norm` 而不能现场重算？**
   在 `merge_safe` 时，合并后的权重为 $\mathbf{W}_{\text{merged}} = \operatorname{diag}(\boldsymbol{\rho}) (\mathbf{W}_0 + s\mathbf{B}\mathbf{A})$。注意此时 $\mathbf{W}_{\text{merged}}$ 每一行的 $L_2$ 范数已经变成了 $\|\mathbf{w}_{\text{merged}, i}\|_2 \equiv m_i$，而不再是合并前的 $\|\mathbf{w}_{0,i} + s(\mathbf{B}\mathbf{A})_i\|_2$！如果在执行 `unmerge()` 时直接对 $\mathbf{W}_{\text{merged}}$ 求行范数来恢复 $\mathbf{W}_0$，得到的比值将恒等于 $m_i / m_i = 1$，从而无法除掉 $\boldsymbol{\rho}$ 缩放因子，导致还原出的基座权重彻底损坏。因此 `peft` 源码在 `merge` 时强制执行 `module._cache_store(f"{active_adapter}-weight_norm", weight_norm)`，并在 `unmerge` 时弹出该缓存值执行精确逆运算：
   $$\mathbf{W}_0 = \operatorname{diag}(\boldsymbol{\rho}^{-1}) \mathbf{W}_{\text{merged}} - s \mathbf{B}\mathbf{A}$$

---

### 2. PiSSA 与 CorDA：从盲目随机起点到主奇异子空间/协方差感知初始化

#### （1）经典 LoRA 早期梯度的“噪声子空间陷阱”与 PiSSA 的主奇异值分解
在经典 LoRA 中，$\mathbf{A}_0 \sim \mathcal{N}(0, \sigma^2)$（或 Kaiming Uniform），$\mathbf{B}_0 = \mathbf{0}$。在训练第 $0$ 步（$t=0$），设损失对线性层输出 $\mathbf{h}$ 的梯度为 $\mathbf{G}_h = \frac{\partial \mathcal{L}}{\partial \mathbf{h}}$，则对 $\mathbf{A}$ 与 $\mathbf{B}$ 的首步梯度分别为：

$$\left.\frac{\partial \mathcal{L}}{\partial \mathbf{A}}\right|_{t=0} = s \mathbf{B}_0^\top \mathbf{G}_h^\top \mathbf{X} = \mathbf{0}, \qquad \left.\frac{\partial \mathcal{L}}{\partial \mathbf{B}}\right|_{t=0} = s \mathbf{G}_h^\top \mathbf{X} \mathbf{A}_0^\top$$

可以看到：不仅 $\mathbf{A}$ 在第一步完全静止，而且 $\mathbf{B}$ 的首步更新方向被随机矩阵 $\mathbf{A}_0$ 强行投影到了一个与预训练权重主特征方向几乎正交的 $r$ 维随机子空间上。由于预训练大模型权重的奇异值谱呈陡峭的长尾衰减，随机方向大概率落在奇异值极小的平坦噪声尾部，导致早期梯度模长极小、收敛缓慢且易陷入局部次优解。

**PiSSA（Principal Singular Values and Singular Vectors Adaptation，Meng et al., NeurIPS 2024）** 的核心思想是：**与改善从 0 开始学习的随机旁路不同，直接把预训练权重 $\mathbf{W}_0$ 中最核心的前 $r$ 个主奇异分量（Principal Components）剥离出来放进可训练的 $\mathbf{B}, \mathbf{A}$ 中，而把次要的剩余奇异分量留在冻结的残差矩阵 $\mathbf{W}_{\text{res}}$ 中！**

对照 Hugging Face `peft` 源码 `src/peft/utils/loftq_utils.py::_pissa_decomposition`，对 $\mathbf{W}_0 \in \mathbb{R}^{d_{\text{out}} \times d_{\text{in}}}$ 执行经济型奇异值分解（或快速低秩随机 SVD `torch.svd_lowrank(..., niter=k)`，即 `init_lora_weights="pissa_niter_4"`）：

$$\mathbf{W}_0 = \mathbf{U} \operatorname{diag}(\boldsymbol{\sigma}) \mathbf{V}^\top = \underbrace{\mathbf{U}_{:, :r} \operatorname{diag}(\boldsymbol{\sigma}_{:r}) \mathbf{V}_{:, :r}^\top}_{\text{主奇异分量 (Principal)}} + \underbrace{\mathbf{U}_{:, r:} \operatorname{diag}(\boldsymbol{\sigma}_{r:}) \mathbf{V}_{:, r:}^\top}_{\text{尾部残差分量 (Residual)}}$$

在带有缩放系数 $s = \text{scaling}$（如 $\alpha/r$）的 PEFT 框架下，为了保证初始化时刻前向输出与原模型 $100\%$ 恒等（$\mathbf{W}_{\text{res}} + s \mathbf{B}_0 \mathbf{A}_0 \equiv \mathbf{W}_0$），源码先将前 $r$ 个奇异值除以 $s$：

$$\tilde{\boldsymbol{\sigma}}_{:r} = \frac{\boldsymbol{\sigma}_{:r}}{s}, \qquad \mathbf{A}_0 = \operatorname{diag}\!\left(\sqrt{\tilde{\boldsymbol{\sigma}}_{:r}}\right) \mathbf{V}_{:, :r}^\top \in \mathbb{R}^{r \times d_{\text{in}}}, \qquad \mathbf{B}_0 = \mathbf{U}_{:, :r} \operatorname{diag}\!\left(\sqrt{\tilde{\boldsymbol{\sigma}}_{:r}}\right) \in \mathbb{R}^{d_{\text{out}} \times r}$$

$$\mathbf{W}_{\text{res}} = \mathbf{W}_0 - s \mathbf{B}_0 \mathbf{A}_0 \quad (\text{冻结于 }\texttt{base\_layer.weight})$$

此时在 $t=0$ 起点：
1. **输出严格无损**：$\mathbf{W}_{\text{res}} + s \mathbf{B}_0 \mathbf{A}_0 = \mathbf{W}_0$；
2. **首步双向满秩梯度激活**：因为 $\mathbf{B}_0 \neq \mathbf{0}$ 且 $\mathbf{A}_0 \neq \mathbf{0}$，$\frac{\partial \mathcal{L}}{\partial \mathbf{A}}$ 与 $\frac{\partial \mathcal{L}}{\partial \mathbf{B}}$ 在第 1 步同时非零，且梯度直接沿着 $\mathbf{W}_0$ 能量最大的前 $r$ 个主奇异向量方向更新，直接模仿全量微调中最主导的特征演化轨迹！

#### （2）PiSSA 的工程痛点与 `subtract_mutated_init` 秩 $2r$ 无损转换技巧
PiSSA 看似完美，但在多任务部署（如 vLLM / S-LoRA 动态挂载数十个 Adapter）中有一个棘手问题：**PiSSA 修改了基座权重 $\mathbf{W}_0 \to \mathbf{W}_{\text{res}}$**！如果直接保存训练后的 $(\mathbf{B}_{\text{tr}}, \mathbf{A}_{\text{tr}})$，它只能挂在专用的残差模型 $\mathbf{W}_{\text{res}}$ 上运行，无法与共享原始基座 $\mathbf{W}_0$ 的其他标准 LoRA 适配器混用或动态卸载。

为了彻底解决这一部署障碍，Hugging Face `peft` 在 `PeftModel.save_pretrained(..., path_initial_model_for_weight_conversion=...)` 与 `LoraModel.subtract_mutated_init` 中实现了一个极为精妙的**分块矩阵恒等变换**：
- 训练完成后的等效全权重为：
  $$\mathbf{W}_{\text{final}} = \mathbf{W}_{\text{res}} + s \mathbf{B}_{\text{tr}} \mathbf{A}_{\text{tr}} = (\mathbf{W}_0 - s \mathbf{B}_0 \mathbf{A}_0) + s \mathbf{B}_{\text{tr}} \mathbf{A}_{\text{tr}} = \mathbf{W}_0 + s (\mathbf{B}_{\text{tr}} \mathbf{A}_{\text{tr}} - \mathbf{B}_0 \mathbf{A}_0)$$
- 注意到两个秩-$r$ 矩阵之差 $\mathbf{B}_{\text{tr}} \mathbf{A}_{\text{tr}} - \mathbf{B}_0 \mathbf{A}_0$ 可以**零误差地写成两个秩-$2r$ 矩阵的乘积**！只需将训练后的参数与初始分解参数按块拼接：
  $$\mathbf{A}_{\text{conv}} = \begin{bmatrix} \mathbf{A}_{\text{tr}} \\ \mathbf{A}_0 \end{bmatrix} \in \mathbb{R}^{2r \times d_{\text{in}}}, \qquad \mathbf{B}_{\text{conv}} = \begin{bmatrix} \mathbf{B}_{\text{tr}} & -\mathbf{B}_0 \end{bmatrix} \in \mathbb{R}^{d_{\text{out}} \times 2r}$$
- 验证其乘积：
  $$\mathbf{B}_{\text{conv}} \mathbf{A}_{\text{conv}} = \begin{bmatrix} \mathbf{B}_{\text{tr}} & -\mathbf{B}_0 \end{bmatrix} \begin{bmatrix} \mathbf{A}_{\text{tr}} \\ \mathbf{A}_0 \end{bmatrix} = \mathbf{B}_{\text{tr}} \mathbf{A}_{\text{tr}} - \mathbf{B}_0 \mathbf{A}_0$$
- 同时，源码自动将导出配置文件中的 `r` 翻倍为 $2r$，并将 `lora_alpha` 同步调整以保持缩放因子 $s$ 不变（标准模式下 `lora_alpha *= 2` 使 $\frac{2\alpha}{2r} = \frac{\alpha}{r}$；rsLoRA 模式下 `lora_alpha *= sqrt(2)` 使 $\frac{\sqrt{2}\alpha}{\sqrt{2r}} = \frac{\alpha}{\sqrt{r}}$）。
- **工程收益**：训练期完全享受 PiSSA 的极速主成分收敛，导出期一行代码无损转换为**直接挂载在未修改原始基座 $\mathbf{W}_0$ 上的标准秩-$2r$ LoRA 适配器**，无缝兼容所有现有推理引擎！

> **对比拓展：MiLoRA 与 CorDA（激活协方差感知分解）**
> - **MiLoRA / MiCA**（Minor Singular Component Adaptation）：与 PiSSA 相反，认为主奇异向量承载着预训练的核心世界知识，微调主奇异分量容易引发灾难性遗忘；因此冻结前 $n-r$ 个主奇异分量，仅用最小的 $r$ 个尾部奇异向量初始化可训练旁路；
> - **CorDA**（Context-Oriented Decomposition Adaptation, Yang et al., NeurIPS 2024，见 `peft/tuners/lora/corda.py`）：指出单纯对静态权重 $\mathbf{W}_0$ 做 SVD 忽略了输入激活分布。CorDA 先用少量校准样本收集输入激活协方差矩阵 $\mathbf{C} = \frac{1}{N}\sum \mathbf{x}\mathbf{x}^\top \in \mathbb{R}^{d_{\text{in}} \times d_{\text{in}}}$，然后对加权矩阵 $\mathbf{W}_0 \mathbf{C}$ 做 SVD：$\mathbf{W}_0 \mathbf{C} = \mathbf{U} \boldsymbol{\Sigma} \mathbf{V}^\top$，再右乘 $\mathbf{C}^{-1}$ 还原：$\mathbf{W}_0 = \mathbf{U} \boldsymbol{\Sigma} (\mathbf{V}^\top \mathbf{C}^{-1})$。其支持两种模式：**IPM（Instruction-Previewed Mode）**将下游任务协方差最大的前 $r$ 个分量放入可训练适配器以加速能力获取；**KPM（Knowledge-Preserved Mode）**将通用知识协方差最小的 $r$ 个尾部特征放入可训练适配器以最大化抵抗遗忘。

---

### 3. rsLoRA 与 LoRA+：高秩渐近方差稳定与无限宽非对称学习率

#### （1）rsLoRA（Rank-Stabilized LoRA）：为什么 $\frac{\alpha}{r}$ 在高秩下必然坍缩？
在面对复杂领域知识注入时，工程师往往希望把秩 $r$ 从 $8$ 提高到 $128, 256$ 甚至 $512$。然而实验表明，在经典缩放因子 $\gamma_r = \frac{\alpha}{r}$ 下，盲目调大 $r$ 不仅不会提升效果，在固定学习率下甚至会出现训练初期的梯度消失与收敛停滞。

**rsLoRA**（Kalajdzievski, 2023）通过随机矩阵与渐近方差分析给出了严格数学解释：
- 考察旁路乘积 $\Delta \mathbf{W} \mathbf{x} = \gamma_r \mathbf{B}\mathbf{A}\mathbf{x} = \gamma_r \sum_{k=1}^r \mathbf{b}_{:, k} (\mathbf{a}_{k, :}^\top \mathbf{x})$。
- 假设在第 $k$ 个秩通道上，向量 $\mathbf{a}_{k,:}$ 与 $\mathbf{b}_{:,k}$（在经历首步更新后）各分量独立同分布、均值为 $0$，且单通道内积项 $z_k = \mathbf{b}_{:,k}(\mathbf{a}_{k,:}^\top \mathbf{x})$ 的方差为常数 $\sigma_z^2 = \Theta(1)$。
- 由于 $r$ 个秩通道彼此独立，根据可加性，$r$ 项求和 $\sum_{k=1}^r z_k$ 的方差随 $r$ **线性增长**：
  $$\operatorname{Var}\!\left(\sum_{k=1}^r z_k\right) = r \sigma_z^2 \quad \implies \quad \operatorname{Std}\!\left(\sum_{k=1}^r z_k\right) = \sqrt{r} \, \sigma_z$$
- 当乘上外部缩放系数 $\gamma_r$ 后，旁路输出激活（以及反向传播回 $\mathbf{A}, \mathbf{B}$ 的梯度）的真实标准差尺度为：
  $$\operatorname{Std}(\gamma_r \mathbf{B}\mathbf{A}\mathbf{x}) = \gamma_r \sqrt{r} \, \sigma_z$$
  - **若采用经典 LoRA（$\gamma_r = \frac{\alpha}{r}$）**：有效标准差为 $\frac{\alpha}{r} \cdot \sqrt{r} \, \sigma_z = \frac{\alpha}{\sqrt{r}} \sigma_z \xrightarrow{r \to \infty} 0$！例如当 $\alpha=16$ 时，$r=4$ 的有效尺度为 $8\sigma_z$，而当 $r$ 增大到 $256$ 时，有效尺度坍缩到了 $1\sigma_z$（缩水 $8$ 倍），导致高秩下的初期梯度与特征更新被严重扼杀；
  - **若采用 rsLoRA（$\gamma_r = \frac{\alpha}{\sqrt{r}}$，即 PEFT 中开启 `use_rslora=True`）**：有效标准差恒为：
    $$\operatorname{Std}\!\left(\frac{\alpha}{\sqrt{r}} \mathbf{B}\mathbf{A}\mathbf{x}\right) = \frac{\alpha}{\sqrt{r}} \cdot \sqrt{r} \, \sigma_z \equiv \alpha \sigma_z = \Theta(1) \quad (\forall r \ge 1)$$
    从而彻底解耦了秩 $r$ 与激活/梯度尺度，使得增大秩 $r$ 能够平滑、单调地转化为模型微调容量的真实提升。

#### （2）LoRA+（ICML 2024）：为什么 $\mathbf{B}$ 的学习率必须远大于 $\mathbf{A}$（$\eta_B = \lambda \eta_A$）？
在经典 LoRA 与 rsLoRA 中，优化器（AdamW）默认对降维矩阵 $\mathbf{A} \in \mathbb{R}^{r \times d_{\text{in}}}$ 和升维矩阵 $\mathbf{B} \in \mathbb{R}^{d_{\text{out}} \times r}$ 使用完全相同的学习率 $\eta_A = \eta_B = \eta$。**LoRA+**（Hayou et al., ICML 2024）利用无限宽神经网络的张量程序理论（Maximal Update Parametrization, $\mu\text{P}$）证明：**在隐藏层维度 $d \gg r$（如 $d = 4096, r = 8$）的尺度下，$\eta_A = \eta_B$ 在数学上是病态的（Sub-optimal）！**

其核心尺度推导如下：
1. **输入输出维度的非对称性**：
   设输入向量 $\mathbf{x} \in \mathbb{R}^d$ 的每个元素量级为 $\Theta(1)$，则 $\|\mathbf{x}\|_2 = \Theta(\sqrt{d})$。
   - 降维矩阵 $\mathbf{A} \in \mathbb{R}^{r \times d}$ 将 $d$ 维输入压缩为 $r$ 维隐向量 $\mathbf{z} = \mathbf{A}\mathbf{x} \in \mathbb{R}^r$。为了保证初始化时 $z_k = \sum_{j=1}^d A_{k,j} x_j = \Theta(1)$，$\mathbf{A}_0$ 必须按方差 $\Theta(1/d)$（即元素量级 $\Theta(d^{-1/2})$）初始化；
   - 升维矩阵 $\mathbf{B} \in \mathbb{R}^{d \times r}$ 将 $r = \Theta(1)$ 维的隐向量 $\mathbf{z}$ 映射回 $d$ 维输出 $\Delta \mathbf{h} = \mathbf{B}\mathbf{z} \in \mathbb{R}^d$。由于求和仅跨越常数 $r$ 项，要使输出 $\Delta h_i = \sum_{k=1}^r B_{i,k} z_k$ 的每个元素达到 $\Theta(1)$ 的有效特征更新量级，$\mathbf{B}$ 的元素变化量 $\Delta B_{i,k}$ 必须达到 $\Theta(1)$ 量级！
2. **Adam 优化器下的更新步长失配**：
   在 Adam / AdamW 优化器中，参数单步更新的逐元素量级由各自的学习率直接控制（因为一阶动量与二阶动量比值将梯度归一化为了 $\pm \Theta(1)$ 符号量级）：
   $$\Delta \mathbf{A}_t \sim -\eta_A \cdot \operatorname{sign}(\mathbf{G}_A) \implies |\Delta A_{k,j}| = \Theta(\eta_A)$$
   $$\Delta \mathbf{B}_t \sim -\eta_B \cdot \operatorname{sign}(\mathbf{G}_B) \implies |\Delta B_{i,k}| = \Theta(\eta_B)$$
   考察一步更新后，两个矩阵各自的更新对层输出 $\Delta \mathbf{h}$ 产生的增量贡献：
   - **由 $\Delta \mathbf{A}$ 引起的隐层特征变化**：$\Delta \mathbf{z} = \Delta \mathbf{A} \, \mathbf{x}$。由于 $\mathbf{x}$ 有 $d$ 个 $\Theta(1)$ 元素且与梯度方向对齐（非随机抵消），内积求和会放大 $d$ 倍！要使 $\Delta \mathbf{z} = \Theta(1)$ 而不发生数值爆炸，学习率 $\eta_A$ 必须受控在 $\eta_A = \Theta(d^{-1})$ 量级；
   - **由 $\Delta \mathbf{B}$ 引起的输出特征变化**：$\mathbf{B}$ 的每一行仅对 $r = \Theta(1)$ 个元素求和（$\Delta \mathbf{B} \, \mathbf{z}$），要使 $\Delta \mathbf{B} \, \mathbf{z} = \Theta(1)$，学习率 $\eta_B$ 必须处于 $\eta_B = \Theta(1)$ 量级！
3. **结论与 Hugging Face PEFT 工程配方**：
   如果强行令 $\eta_A = \eta_B = \eta$：
   - 若将 $\eta$ 设得很大（如 $\Theta(1)$）以迁就 $\mathbf{B}$，则 $\Delta \mathbf{A} \, \mathbf{x}$ 会瞬间爆炸导致训练发散；
   - 若将 $\eta$ 设得很小（如 $\Theta(d^{-1})$）以保证 $\mathbf{A}$ 稳定，则 $\Delta \mathbf{B}$ 的更新量仅为 $\Theta(d^{-1}) \to 0$，导致升维矩阵 $\mathbf{B}$ 几乎处于“半冻结”的爬行状态！
   因此，**LoRA+**（对应 `peft/optimizers/loraplus.py::create_loraplus_optimizer`）将可训练参数显式拆分为 `groupA`（`lr = eta_A`）与 `groupB`（包含 `lora_B` 及 1D 参数，`lr = loraplus_lr_ratio * eta_A`），通过设置比率 $\lambda = \frac{\eta_B}{\eta_A} \in [8, 16]$（理论渐近比率 $\propto d$，有限宽模型实测甜点在 $8\sim 16$），在不增加任何显存与计算量的前提下将微调收敛速度提升约 $1.5\times \sim 2\times$。

```text
PEFT (LoRA 家族) 四大核心演进维度的正交解耦架构图:

                      [ 输入激活 x ∈ R^{d_in} ]
                                 │
          ┌──────────────────────┴──────────────────────┐
          ▼ (冻结主路)                                   ▼ (可训练低秩旁路)
  ┌─────────────────────────┐                  ┌─────────────────────────┐
  │ 基座权重 W_0 或残差 W_res │                  │ 降维矩阵 A ∈ R^{r×d_in}  │ ◄── [LoRA+] 小学习率 η_A
  │ (PiSSA: W_0 - s*B_0*A_0)│                  │ (PiSSA: Top-r 右奇异向量)│
  └───────────┬─────────────┘                  └───────────┬─────────────┘
              │                                            │ z = A x ∈ R^r
              │                                            ▼
              │                                ┌─────────────────────────┐
              │                                │ 升维矩阵 B ∈ R^{d_out×r} │ ◄── [LoRA+] 大学习率 η_B = λ η_A
              │                                │ (PiSSA: Top-r 左奇异向量)│
              │                                └───────────┬─────────────┘
              │                                            │
              │                                            ▼
              │                                [rsLoRA] 秩稳定缩放 s = α / √r (消除大 r 梯度坍缩)
              │                                            │
              └──────────────────┬─────────────────────────┘
                                 ▼
              [ 方向合成 V' = W_0 + s * B * A ]
                                 │
                                 ▼
              [DoRA] 逐输出通道方向归一化 + 可训练幅度向量 m ∈ R^{d_out}:
                     W_eff = diag( m / stop_grad(||V'||_row) ) @ V'
```

| 演进方法 | 核心解决的经典 LoRA 痛点 | 关键数学形式 / 改动点 | 额外可训练参数 | 合并后推理额外延迟 | Hugging Face `peft` 启用方式 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Vanilla LoRA** (ICLR 2022) | 全量微调优化器状态显存过高（$16\Psi$ Bytes） | $\mathbf{W}' = \mathbf{W}_0 + \frac{\alpha}{r}\mathbf{B}\mathbf{A}$，$\mathbf{A}_0 \sim \text{Kaiming}, \mathbf{B}_0 = \mathbf{0}$ | $r(d_{\text{in}} + d_{\text{out}})$ | **0**（直接相加合并） | `LoraConfig(r=r, lora_alpha=alpha)` |
| **DoRA** (ICML 2024) | 幅度变化与方向变化强耦合，低秩下方向调整受限 | $\mathbf{W}' = \operatorname{diag}\!\left(\frac{\mathbf{m}}{\operatorname{sg}(\|\mathbf{W}_0 + s\mathbf{B}\mathbf{A}\|_r)}\right)(\mathbf{W}_0 + s\mathbf{B}\mathbf{A})$ | 仅多一个向量 $\mathbf{m} \in \mathbb{R}^{d_{\text{out}}}$（约 $+0.01\%$） | **0**（折算 `dora_factor` 后合并） | `LoraConfig(..., use_dora=True)` |
| **PiSSA** (NeurIPS 2024) | $\mathbf{B}_0=\mathbf{0}$ 且 $\mathbf{A}_0$ 随机导致早期梯度落入平坦噪声奇异尾部 | 对 $\mathbf{W}_0$ 做 SVD 提取前 $r$ 个主奇异分量初始化 $\mathbf{B}_0, \mathbf{A}_0$，冻结 $\mathbf{W}_{\text{res}}$ | **0**（训练后可转为秩 $2r$ 标准 LoRA） | **0**（直接合并或转 $2r$ LoRA） | `LoraConfig(..., init_lora_weights="pissa_niter_4")` |
| **CorDA** (NeurIPS 2024) | 纯权重 SVD 忽略了真实上下文激活分布与抗遗忘需求 | 对激活协方差加权矩阵 $\mathbf{W}_0 \mathbf{C}$ 做 SVD（支持 IPM 主成分 / KPM 尾成分） | **0** | **0** | `LoraConfig(..., init_lora_weights="corda")` |
| **rsLoRA** (2023) | $\frac{\alpha}{r}$ 随秩 $r$ 增大过度压缩前向方差与反向梯度（$\propto 1/\sqrt{r}$） | 将缩放因子改为 $\gamma_r = \frac{\alpha}{\sqrt{r}}$，使 $\operatorname{Std}(\gamma_r \mathbf{B}\mathbf{A}\mathbf{x}) = \Theta(1)$ | **0** | **0** | `LoraConfig(..., use_rslora=True)` |
| **LoRA+** (ICML 2024) | 宽度 $d \gg r$ 时 $\eta_A = \eta_B$ 导致 $\mathbf{B}$ 更新过慢、特征学习退化 | 优化器分组设置非对称学习率：$\eta_B = \lambda \eta_A$（$\lambda \in [8, 16]$） | **0** | **0** | `create_loraplus_optimizer(..., loraplus_lr_ratio=16)` |

---

### 4. Python 3 标准库实现：DoRA 合并/卸载缓存守卫、PiSSA 秩 $2r$ 转换与 rsLoRA / LoRA+ 仿真

下面的零依赖 Python 3 标准库代码严格对齐 Hugging Face `peft` 官方实现，从底层验证了：
1. **DoRA（`DoraLinearLayer` & `DoraLinearVariant`）**：验证未合并增量公式 `base + (rho - 1) * base + rho * s * B(Ax)` 与合并后矩阵乘法的数值等价性；并对比证明为什么 `unmerge()` 必须使用合并时缓存的原始 `weight_norm`——若在 `unmerge` 时直接对已合并矩阵重算行范数（此时行范数已恒等于 $\mathbf{m}$），会导致还原出的基座权重产生高达 $0.2331$ 的严重损坏；
2. **PiSSA（`_pissa_decomposition` & `subtract_mutated_init`）**：验证用前 $r$ 个主奇异值/向量初始化 $\mathbf{A}_0, \mathbf{B}_0$ 在 $t=0$ 时的精确无损重建，以及微调后通过分块拼接 $[\mathbf{A}_{\text{tr}}; \mathbf{A}_0]$ 与 $[\mathbf{B}_{\text{tr}}, -\mathbf{B}_0]$ 转换为挂载在原始 $\mathbf{W}_0$ 上的秩-$2r$ 标准 LoRA 的零误差等价性；
3. **rsLoRA 与 LoRA+ 优化动力学**：验证 $r \in \{4, 16, 64, 256\}$ 时标准 $\alpha/r$ 有效尺度的坍缩 vs rsLoRA $\alpha/\sqrt{r}$ 的恒定尺度，以及从 $\mathbf{B}_0 = \mathbf{0}$ 出发时 LoRA+（$\eta_B = 8\eta_A$）相比同学习率 Vanilla LoRA 的收敛加速。

```python
import math
from typing import Dict, List


def mat_mul(A: List[List[float]], B: List[List[float]]) -> List[List[float]]:
    """计算矩阵乘积 A @ B"""
    rows_a, cols_a = len(A), len(A[0])
    rows_b, cols_b = len(B), len(B[0])
    assert cols_a == rows_b
    return [
        [sum(A[i][k] * B[k][j] for k in range(cols_a)) for j in range(cols_b)]
        for i in range(rows_a)
    ]


def mat_vec(W: List[List[float]], x: List[float]) -> List[float]:
    """计算矩阵向量乘积 W @ x"""
    return [sum(row[j] * x[j] for j in range(len(x))) for row in W]


def mat_add(A: List[List[float]], B: List[List[float]], scale_b: float = 1.0) -> List[List[float]]:
    return [
        [A[i][j] + scale_b * B[i][j] for j in range(len(A[0]))]
        for i in range(len(A))
    ]


def row_l2_norms(W: List[List[float]]) -> List[float]:
    """对齐 Hugging Face PEFT DoraLinearLayer.get_weight_norm: torch.linalg.norm(weight, dim=1)"""
    return [math.sqrt(sum(v * v for v in row)) for row in W]


def simulate_dora_forward_merge_unmerge(
    W0: List[List[float]],
    A: List[List[float]],
    B: List[List[float]],
    m: List[float],
    x: List[float],
    scaling: float,
) -> Dict[str, object]:
    """
    严格对齐 huggingface/peft (src/peft/tuners/lora/dora.py & variants.py):
    1. 未合并前向: base_result + (m / ||W0 + s*BA||_row - 1) * base_result + (m / ||W0 + s*BA||_row) * s * B(Ax)
    2. 合并权重: W_merged = diag(m / ||W0 + s*BA||_row) @ (W0 + s*BA), 缓存 weight_norm
    3. 逆向卸载: W_unmerged = diag(weight_norm / m) @ W_merged - s*BA
    """
    delta_W = mat_mul(B, A)
    V = mat_add(W0, delta_W, scale_b=scaling)
    weight_norm = row_l2_norms(V)  # 对应源码中的 weight_norm.detach()
    dora_factor = [m[i] / weight_norm[i] for i in range(len(W0))]

    # 1. 未合并前向 (DoraLinearLayer.forward)
    base_result = mat_vec(W0, x)
    lora_result = mat_vec(B, mat_vec(A, x))
    out_unmerged = [
        base_result[i] + (dora_factor[i] - 1.0) * base_result[i] + dora_factor[i] * scaling * lora_result[i]
        for i in range(len(W0))
    ]

    # 2. 合并权重与合并后前向 (DoraLinearVariant.merge_safe)
    W_merged = [
        [dora_factor[i] * (W0[i][j] + scaling * delta_W[i][j]) for j in range(len(W0[0]))]
        for i in range(len(W0))
    ]
    out_merged = mat_vec(W_merged, x)

    # 3. 正确卸载 (使用缓存的原始 weight_norm) vs 错误卸载 (重算合并后矩阵的行范数)
    W_unmerged_correct = [
        [W_merged[i][j] / dora_factor[i] - scaling * delta_W[i][j] for j in range(len(W0[0]))]
        for i in range(len(W0))
    ]
    wrong_norm = row_l2_norms(W_merged)  # 注意: ||W_merged||_row == m != weight_norm!
    wrong_factor = [m[i] / wrong_norm[i] for i in range(len(W0))]
    W_unmerged_wrong = [
        [W_merged[i][j] / wrong_factor[i] - scaling * delta_W[i][j] for j in range(len(W0[0]))]
        for i in range(len(W0))
    ]

    max_fwd_diff = max(abs(a - b) for a, b in zip(out_unmerged, out_merged))
    max_unmerge_err = max(
        abs(W0[i][j] - W_unmerged_correct[i][j])
        for i in range(len(W0))
        for j in range(len(W0[0]))
    )
    max_wrong_unmerge_err = max(
        abs(W0[i][j] - W_unmerged_wrong[i][j])
        for i in range(len(W0))
        for j in range(len(W0[0]))
    )
    return {
        "max_fwd_diff": max_fwd_diff,
        "max_unmerge_err": max_unmerge_err,
        "max_wrong_unmerge_err": max_wrong_unmerge_err,
        "weight_norm": [round(v, 4) for v in weight_norm],
        "merged_row_norm": [round(v, 4) for v in wrong_norm],
    }


def simulate_pissa_init_and_rank2r_conversion(
    U: List[List[float]],
    S: List[float],
    Vh: List[List[float]],
    r: int,
    scaling: float,
    delta_A_train: List[List[float]],
    delta_B_train: List[List[float]],
) -> Dict[str, object]:
    """
    严格对齐 huggingface/peft (_pissa_decomposition & subtract_mutated_init):
    1. 用前 r 个主奇异值/向量初始化 A_0, B_0, 残差 W_res = W_0 - scaling * B_0 @ A_0
    2. 训练后通过 [A | A_0] 与 [B | -B_0] 拼接为秩 2r 标准 LoRA, 实现无需改动 W_0 的无损热插拔
    """
    d_out, k_rank = len(U), len(S)
    d_in = len(Vh[0])
    # 重建原始满秩矩阵 W0 = U @ diag(S) @ Vh
    W0 = [
        [sum(U[i][p] * S[p] * Vh[p][j] for p in range(k_rank)) for j in range(d_in)]
        for i in range(d_out)
    ]

    # PiSSA 主奇异子空间分解 (除以 scaling 保证 W_res = W0 - scaling * B0 @ A0)
    Sr_scaled = [S[p] / scaling for p in range(r)]
    A0 = [[math.sqrt(Sr_scaled[p]) * Vh[p][j] for j in range(d_in)] for p in range(r)]
    B0 = [[U[i][p] * math.sqrt(Sr_scaled[p]) for p in range(r)] for i in range(d_out)]

    B0_A0 = mat_mul(B0, A0)
    W_res = mat_add(W0, B0_A0, scale_b=-scaling)

    # 验证训练起点 t=0 恒等性: W_res + scaling * B0 @ A0 == W0
    W_init_recon = mat_add(W_res, B0_A0, scale_b=scaling)
    init_recon_err = max(
        abs(W0[i][j] - W_init_recon[i][j]) for i in range(d_out) for j in range(d_in)
    )

    # 模拟训练后参数 A_trained = A0 + delta_A, B_trained = B0 + delta_B
    A_tr = mat_add(A0, delta_A_train)
    B_tr = mat_add(B0, delta_B_train)
    W_pissa_final = mat_add(W_res, mat_mul(B_tr, A_tr), scale_b=scaling)

    # 执行 subtract_mutated_init 转化为挂载在原始 W0 上的秩 2r 标准 LoRA:
    # A_conv = cat([A_tr, A0], dim=0) -> [2r, d_in]
    # B_conv = cat([B_tr, -B0], dim=1) -> [d_out, 2r]
    A_conv = A_tr + A0
    B_conv = [B_tr[i] + [-v for v in B0[i]] for i in range(d_out)]
    W_lora_2r_final = mat_add(W0, mat_mul(B_conv, A_conv), scale_b=scaling)

    conv_err = max(
        abs(W_pissa_final[i][j] - W_lora_2r_final[i][j])
        for i in range(d_out)
        for j in range(d_in)
    )
    return {
        "init_recon_err": init_recon_err,
        "conv_err": conv_err,
        "orig_rank": r,
        "converted_rank": len(A_conv),
        "principal_energy_ratio": sum(s * s for s in S[:r]) / sum(s * s for s in S),
    }


def compare_rslora_scaling_and_loraplus_steps(
    alpha: float,
    ranks: List[int],
    W_target_delta: List[List[float]],
    A_init: List[List[float]],
    lr_base: float = 0.1,
    loraplus_ratio: float = 8.0,
    steps: int = 5,
) -> Dict[str, object]:
    """
    验证:
    1. 标准 LoRA (alpha/r) vs rsLoRA (alpha/sqrt(r)) 在不同秩 r 下的有效分支标准差因子
       (当 A_ij ~ N(0, 1/d_in), B_ij ~ O(1) 时, sum_{k=1}^r B_ik A_kj 的标准差正比于 sqrt(r),
        乘上缩放因子 gamma_r 后, 稳定有效尺度为 gamma_r * sqrt(r))
    2. LoRA+ 非对称学习率 (eta_B = lambda * eta_A) 相比同学习率在 5 步更新后的目标逼近损失下降率
    """
    std_effective_scale = {r: round((alpha / r) * math.sqrt(r), 4) for r in ranks}
    rslora_effective_scale = {r: round((alpha / math.sqrt(r)) * math.sqrt(r), 4) for r in ranks}

    # 对比 Vanilla LoRA (eta_B = eta_A) 与 LoRA+ (eta_B = loraplus_ratio * eta_A) 在 F-范数拟合损失
    # L(A, B) = 0.5 * || B @ A - W_target_delta ||_F^2 下的梯度下降轨迹
    d_out, d_in = len(W_target_delta), len(W_target_delta[0])
    r = len(A_init)

    def run_steps(eta_a: float, eta_b: float) -> float:
        A = [row[:] for row in A_init]
        B = [[0.0] * r for _ in range(d_out)]  # B_0 = 0
        for _ in range(steps):
            BA = mat_mul(B, A)
            E = [[BA[i][j] - W_target_delta[i][j] for j in range(d_in)] for i in range(d_out)]
            # grad_B = E @ A^T, grad_A = B^T @ E
            grad_B = [
                [sum(E[i][j] * A[k][j] for j in range(d_in)) for k in range(r)]
                for i in range(d_out)
            ]
            grad_A = [
                [sum(B[i][k] * E[i][j] for i in range(d_out)) for j in range(d_in)]
                for k in range(r)
            ]
            B = [[B[i][k] - eta_b * grad_B[i][k] for k in range(r)] for i in range(d_out)]
            A = [[A[k][j] - eta_a * grad_A[k][j] for j in range(d_in)] for k in range(r)]
        BA_final = mat_mul(B, A)
        return 0.5 * sum(
            (BA_final[i][j] - W_target_delta[i][j]) ** 2
            for i in range(d_out)
            for j in range(d_in)
        )

    loss_init = 0.5 * sum(
        W_target_delta[i][j] ** 2 for i in range(d_out) for j in range(d_in)
    )
    loss_vanilla = run_steps(eta_a=lr_base, eta_b=lr_base)
    loss_loraplus = run_steps(eta_a=lr_base, eta_b=lr_base * loraplus_ratio)
    return {
        "std_effective_scale": std_effective_scale,
        "rslora_effective_scale": rslora_effective_scale,
        "loss_init": round(loss_init, 6),
        "loss_vanilla": round(loss_vanilla, 6),
        "loss_loraplus": round(loss_loraplus, 6),
    }


# --- 1. 验证 DoRA 前向等价性、权重合并与缓存范数卸载 ---
W0_demo = [
    [0.6, -0.8, 0.0, 1.0],
    [-0.5, 0.4, 0.8, -0.2],
    [0.3, 0.9, -0.4, 0.5],
]
A_demo = [
    [0.2, -0.1, 0.3, 0.15],
    [-0.25, 0.4, -0.1, 0.2],
]
B_demo = [
    [0.3, -0.2],
    [-0.15, 0.35],
    [0.25, 0.1],
]
# 模拟训练后可学习幅度向量 m 已偏离初始行范数
m_trained = [1.80, 1.25, 1.50]
x_demo = [1.2, -0.5, 0.8, -0.3]

dora_res = simulate_dora_forward_merge_unmerge(
    W0_demo, A_demo, B_demo, m_trained, x_demo, scaling=2.0
)
assert dora_res["max_fwd_diff"] < 1e-12
assert dora_res["max_unmerge_err"] < 1e-12
assert dora_res["max_wrong_unmerge_err"] > 0.15  # 若不缓存原 weight_norm 直接重算会导致严重损坏!

# --- 2. 验证 PiSSA 主奇异值分解初始化与 subtract_mutated_init 秩 2r 无损转换 ---
# 构造正交矩阵 U (3x3) 与 Vh (3x4)
U_orth = [
    [1.0, 0.0, 0.0],
    [0.0, 0.8, -0.6],
    [0.0, 0.6, 0.8],
]
S_vals = [10.0, 4.0, 0.5]  # 前 r=2 个主奇异值占总能量的 (100+16)/(100+16+0.25) = 99.78%
Vh_orth = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 0.6, 0.8, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]
dA = [[0.05, -0.02, 0.03, 0.01], [-0.03, 0.04, -0.01, 0.02]]
dB = [[0.04, -0.01], [0.02, 0.05], [-0.03, 0.02]]

pissa_res = simulate_pissa_init_and_rank2r_conversion(
    U_orth, S_vals, Vh_orth, r=2, scaling=2.0, delta_A_train=dA, delta_B_train=dB
)
assert pissa_res["init_recon_err"] < 1e-12
assert pissa_res["conv_err"] < 1e-12
assert pissa_res["converted_rank"] == 4  # 2 * r
assert pissa_res["principal_energy_ratio"] > 0.99

# --- 3. 验证 rsLoRA 秩稳定缩放与 LoRA+ 非对称学习率收敛优势 ---
W_delta_target = [
    [0.18, -0.12, 0.24, 0.09],
    [-0.15, 0.22, -0.08, 0.14],
    [0.12, 0.16, -0.10, 0.11],
]
opt_res = compare_rslora_scaling_and_loraplus_steps(
    alpha=16.0, ranks=[4, 16, 64, 256], W_target_delta=W_delta_target, A_init=A_demo
)
# 标准 alpha/r 的有效尺度随 r 增大坍缩 (8.0 -> 1.0), 而 rsLoRA 恒定为 16.0
assert opt_res["std_effective_scale"] == {4: 8.0, 16: 4.0, 64: 2.0, 256: 1.0}
assert opt_res["rslora_effective_scale"] == {4: 16.0, 16: 16.0, 64: 16.0, 256: 16.0}
assert opt_res["loss_loraplus"] < opt_res["loss_vanilla"] * 0.35

print(
    f"1. DoRA Sanity: max_fwd_diff={dora_res['max_fwd_diff']:.2e}, "
    f"cached_unmerge_err={dora_res['max_unmerge_err']:.2e}, "
    f"uncached_wrong_unmerge_err={dora_res['max_wrong_unmerge_err']:.4f}"
)
print(
    f"2. PiSSA Sanity: init_err={pissa_res['init_recon_err']:.2e}, "
    f"principal_energy={pissa_res['principal_energy_ratio']:.4f}, "
    f"rank_{pissa_res['orig_rank']}_to_lora_rank_{pissa_res['converted_rank']}_err={pissa_res['conv_err']:.2e}"
)
print(
    f"3. rsLoRA & LoRA+: std_scale={opt_res['std_effective_scale']} vs "
    f"rslora_scale={opt_res['rslora_effective_scale']}; "
    f"5-step loss: init={opt_res['loss_init']:.4f} -> vanilla={opt_res['loss_vanilla']:.4f} vs "
    f"loraplus={opt_res['loss_loraplus']:.4f}"
)
print("All DoRA, PiSSA, rsLoRA, and LoRA+ assertions passed!")
```

实际运行输出：

```text
1. DoRA Sanity: max_fwd_diff=2.22e-16, cached_unmerge_err=1.11e-16, uncached_wrong_unmerge_err=0.2331
2. PiSSA Sanity: init_err=0.00e+00, principal_energy=0.9978, rank_2_to_lora_rank_4_err=0.00e+00
3. rsLoRA & LoRA+: std_scale={4: 8.0, 16: 4.0, 64: 2.0, 256: 1.0} vs rslora_scale={4: 16.0, 16: 16.0, 64: 16.0, 256: 16.0}; 5-step loss: init=0.1358 -> vanilla=0.1086 vs loraplus=0.0359
All DoRA, PiSSA, rsLoRA, and LoRA+ assertions passed!
```

---

## 延伸 / 追问

**追问 1：当把 PiSSA 或 DoRA 与 4-bit 量化基座（即 QPiSSA / QDoRA）结合时，为什么不能直接在 4-bit 量化后的权重上做 PiSSA 的 SVD 分解？Hugging Face `peft`（`replace_lora_weights_pissa` 与 `LoftQ`）是如何解决“量化误差 + 低秩分解误差”双重叠加的？**
1. **直接在量化权重上做 PiSSA 的两个陷阱**：
   - 第一，bitsandbytes 的 `Linear4bit`（NF4）将权重打包存储在 `uint8` 紧凑张量中，不能直接传入 `torch.linalg.svd`；
   - 第二，即使先把 4-bit 权重 $\widehat{\mathbf{W}}_0 = \operatorname{Quant}(\mathbf{W}_0)$ 反量化回 FP32 再做 SVD 提取主成分 $\mathbf{B}_0 \mathbf{A}_0$，并把残差 $\mathbf{W}_{\text{res}} = \widehat{\mathbf{W}}_0 - s \mathbf{B}_0 \mathbf{A}_0$ **再次量化**回 4-bit，也会经历“两次有损量化”，且转换回标准 LoRA 时会遇到不可消除的非线性失配：
     $$\operatorname{Quant}(\mathbf{W}_{\text{res}}) + s \mathbf{B}\mathbf{A} \neq \operatorname{Quant}(\mathbf{W}_0) + s (\mathbf{B}\mathbf{A} - \mathbf{B}_0 \mathbf{A}_0)$$
2. **源码级解法（`replace_lora_weights_pissa` 与 `LoftQ` 交替投影）**：
   - 在 `src/peft/utils/loftq_utils.py::replace_lora_weights_pissa` 中，PEFT 通过 `_SafetensorLoader` 逐层从磁盘流式懒加载**原始未量化的 FP16/BF16 safetensors 权重** $\mathbf{W}_0$，在 FP32 下执行精确的 `_pissa_decomposition` 得到 $\mathbf{A}_0, \mathbf{B}_0$ 与高精度残差 $\mathbf{W}_{\text{res}} = \mathbf{W}_0 - s \mathbf{B}_0 \mathbf{A}_0$，随后**仅对残差矩阵 $\mathbf{W}_{\text{res}}$ 执行一次 4-bit NF4 量化**！由于主奇异分量（往往也是幅度最大的离群值来源）已经被剥离进全精度的 $\mathbf{B}_0 \mathbf{A}_0$ 中，残差矩阵 $\mathbf{W}_{\text{res}}$ 的数值分布更加集中均匀，其 4-bit 量化误差反而比直接量化原始 $\mathbf{W}_0$ 小得多！
   - 而在 **LoftQ**（Li et al., ICLR 2024）中，若希望在保留量化流程的同时补偿 NF4 量化误差，则通过 $T$ 步交替优化（Alternating Minimization）：第 $t$ 步先对当前低秩修正后的权重做 NF4 量化 $Q_t = \operatorname{Quant}_{\text{NF4}}(\mathbf{W}_0 - \mathbf{B}_{t-1}\mathbf{A}_{t-1})$，再用秩-$r$ SVD 拟合量化残差 $\mathbf{W}_0 - Q_t \approx \mathbf{B}_t \mathbf{A}_t$，使 $Q_T + \mathbf{B}_T \mathbf{A}_T$ 在训练起点最大程度逼近全精度 $\mathbf{W}_0$。

**追问 2：如果不用固定秩 $r$，而是希望在总参数预算不变的前提下为 Transformer 不同层、不同模块（如 `v_proj`/`down_proj` vs `q_proj`/`k_proj`）动态分配不同的有效秩，AdaLoRA（ICLR 2023）是如何通过拟奇异值分解与重要性剪枝实现的？**
1. **SVD 形式参数化与正交正则化**：
   如果直接对普通矩阵乘积 $\Delta \mathbf{W} = \mathbf{B}\mathbf{A}$ 剪掉某一列/行，由于列向量之间彼此非正交且高度耦合，剪掉一个维度会剧烈破坏其余维度的子空间表征。**AdaLoRA**（Zhang et al., ICLR 2023）直接将增量参数化为显式的三元组 SVD 形式：
   $$\Delta \mathbf{W}_k = \mathbf{P}_k \boldsymbol{\Lambda}_k \mathbf{Q}_k, \qquad \mathbf{P}_k \in \mathbb{R}^{d_{\text{out}} \times r}, \quad \boldsymbol{\Lambda}_k = \operatorname{diag}(\boldsymbol{\lambda}_k) \in \mathbb{R}^{r \times r}, \quad \mathbf{Q}_k \in \mathbb{R}^{r \times d_{\text{in}}}$$
   为了避免每步调用复杂度高达 $O(\min(d_{\text{out}}, d_{\text{in}})^3)$ 的真实 SVD，AdaLoRA 在损失函数中加入轻量级正交惩罚项（耗时仅 $O(r^2 (d_{\text{out}} + d_{\text{in}}))$）：
   $$\mathcal{R}(\mathbf{P}_k, \mathbf{Q}_k) = \|\mathbf{P}_k^\top \mathbf{P}_k - \mathbf{I}_r\|_F^2 + \|\mathbf{Q}_k \mathbf{Q}_k^\top - \mathbf{I}_r\|_F^2$$
   强制 $\mathbf{P}_k, \mathbf{Q}_k$ 在训练全程保持近似正交，从而无需重构就能安全地将单个三元组 $(\mathbf{P}_{k, *, i}, \lambda_{k,i}, \mathbf{Q}_{k, i, *})$ 直接置零剪枝。
2. **基于敏感度平滑的三元组重要性评分与三次预算衰减**：
   AdaLoRA 结合参数-梯度乘积的一阶泰勒敏感度 $I(\theta) = |\theta \cdot \nabla_\theta \mathcal{L}|$，通过指数移动平均（EMA）维护平滑敏感度 $\bar{I}(\theta)$ 与不确定性（波动度）$\bar{U}(\theta) = \text{EMA}(|I(\theta) - \bar{I}(\theta)|)$，定义单个参数重要性 $s(\theta) = \bar{I}(\theta) \cdot \bar{U}(\theta)$，并将第 $k$ 个模块第 $i$ 个奇异分量的整体重要性定义为奇异值与左右奇异向量平均重要性的加权和：
   $$S_{k,i} = s(\lambda_{k,i}) + \frac{1}{d_{\text{out}}} \sum_{u=1}^{d_{\text{out}}} s(P_{k, u, i}) + \frac{1}{d_{\text{in}}} \sum_{v=1}^{d_{\text{in}}} s(Q_{k, i, v})$$
   训练初期先以较高的初始秩 $b^{(0)} = 1.5 \, b^{\text{target}}$ 预热，随后按三次多项式调度（Cubic Schedule）逐步淘汰全局得分最低的奇异分量，最终自动把宝贵的秩预算集中分配给对下游任务最敏感的 FFN（`down_proj` / `up_proj`）与深层 Value/Output 投影矩阵。

**追问 3：Biderman et al.（TMLR 2024，《LoRA Learns Less and Forgets Less》）通过大规模实验发现了什么核心规律？在生产实践中，即使上了 DoRA + PiSSA + rsLoRA，什么场景下仍然必须放弃低秩微调、改用全量微调或 GaLore？**
1. **“学得更少，但也忘得更少（Learns Less and Forgets Less）”的双刃剑效应**：
   Biderman et al. (2024) 在持续预训练（Continued Pretraining）与高难度指令微调（Python 代码合成与 GSM8K/MATH 数学推理）上对比了不同秩 $r \in [4, 256]$ 的 LoRA 与全量微调，发现：
   - 当下游任务主要是**对齐输出格式、语气风格或激活预训练已有知识**时，低秩微调完全可以追平全量微调；
   - 当下游任务需要向模型**注入高密度的全新领域事实、全新编程语言语法或复杂多步推理模式**时，更新矩阵 $\Delta \mathbf{W}$ 的真实有效秩（Effective Rank）接近满秩，低秩约束构成了刚性的**信息容量瓶颈（Capacity Bottleneck）**——即便启用 DoRA 或 PiSSA，只要 $r \ll \min(d_{\text{out}}, d_{\text{in}})$，其在目标域上的上限依然低于全量微调；
   - 但与此同时，正因为低秩更新被限制在 $r$ 维子空间内（特别当结合 CorDA KPM 或 MiLoRA 时），模型对原预训练分布的偏离远小于全量微调，因此在通用基准上的**灾难性遗忘（Catastrophic Forgetting）显著更轻**，扮演了天然的谱正则化器（Spectral Regularizer）。
2. **何时必须走出低秩适配器？**
   当微调语料达到百亿 Token 级别（如垂直领域继续预训练或小语种扩词表训练）且必须突破低秩容量上限，但硬件又放不下全量微调的优化器状态时，应转向 **GaLore（Gradient Low-Rank Projection, Zhao et al., ICML 2024）**：GaLore **不把权重本身限制为低秩结构**，而是保持全量权重 $\mathbf{W} \in \mathbb{R}^{d_{\text{out}} \times d_{\text{in}}}$ 直接更新，仅每隔 $T$ 步（如 $T=200$）对梯度矩阵 $\mathbf{G}_t$ 做一次 SVD 提取投影矩阵 $\mathbf{P}_t$，在低维空间维护 Adam 的一阶/二阶动量，并随子空间切换让全量权重在训练全周期内跨越多个低秩子空间累积出**满秩更新（Full-Rank Update）**。

---

## 常见误区

- **误区一：“DoRA 既然把权重分解成了幅度向量 $\mathbf{m}$ 和归一化方向矩阵 $\frac{\mathbf{V} + \Delta \mathbf{V}}{\|\mathbf{V} + \Delta \mathbf{V}\|_r}$，包含非线性除法，因此推理时无法像普通 LoRA 那样合并回基座，必然带来额外的推理延迟。”**
  事实：**DoRA 在训练结束后同样可以 100% 合并进基座权重，实现真正的零额外推理延迟！** 因为在推理阶段，$\mathbf{m}$、$\mathbf{W}_0$、$\mathbf{B}$ 和 $\mathbf{A}$ 全部是已经固定下来的常数张量。只需在部署前一次性算出合并权重 $\mathbf{W}_{\text{merged}} = \operatorname{diag}\!\left(\frac{\mathbf{m}}{\|\mathbf{W}_0 + s\mathbf{B}\mathbf{A}\|_r}\right)(\mathbf{W}_0 + s\mathbf{B}\mathbf{A})$ 并写回 `base_layer.weight`，推理时的前向计算依然只是单一的标准矩阵乘法 $\mathbf{h} = \mathbf{x}\mathbf{W}_{\text{merged}}^\top$。
- **误区二：“PiSSA 只是改了 $\mathbf{A}$ 和 $\mathbf{B}$ 的初始化方式（用 $\mathbf{W}_0$ 的主奇异向量初始化），所以训练完保存出来的 `adapter_model.safetensors` 可以直接拿去挂载在原版 Hugging Face 基座模型 $\mathbf{W}_0$ 上推理。”**
  事实：**如果不经过转换直接把 PiSSA 训练出的适配器挂在原版基座 $\mathbf{W}_0$ 上，模型会因为主奇异分量被重复叠加两次（$\mathbf{W}_0 + s\mathbf{B}_{\text{tr}}\mathbf{A}_{\text{tr}} \approx \mathbf{W}_0 + \mathbf{W}_{\text{principal}}$）而直接输出乱码！** 因为 PiSSA 在初始化时已经从基座中减去了主奇异分量（$\mathbf{W}_{\text{res}} = \mathbf{W}_0 - s\mathbf{B}_0\mathbf{A}_0$）。要想挂载在未修改的原版基座 $\mathbf{W}_0$ 上，必须在保存时传入 `path_initial_model_for_weight_conversion` 调用 `subtract_mutated_init`，将其转换为秩为 $2r$ 的标准增量适配器 $[\mathbf{B}_{\text{tr}}, -\mathbf{B}_0][\mathbf{A}_{\text{tr}}; \mathbf{A}_0]$。
- **误区三：“想要提升 LoRA 在复杂任务上的拟合能力，只需要直接把 `LoraConfig` 里的 `r` 从 8 改到 256（保持其他配置和学习率不变），就能获得显著收益。”**
  事实：**在未开启 `use_rslora=True` 的默认配置下，固定 `lora_alpha` 和学习率直接把 $r$ 放大 32 倍，会导致缩放因子 $\alpha/r$ 缩小 32 倍，而分支求和标准差仅增长 $\sqrt{32} \approx 5.66$ 倍，最终导致有效前向激活与反向梯度尺度萎缩至原来的 $1/\sqrt{32} \approx 17.7\%$！** 不仅拿不到高秩红利，反而会因为有效学习率坍缩而学不动。冲击高秩（$r \ge 64$）时应当开启 `use_rslora=True`（改用 $\alpha/\sqrt{r}$），并配合 LoRA+ 的非对称学习率确保升维矩阵 $\mathbf{B}$ 得到充分训练。

---

## 参考

- 选题线索：[wanshuiyin/ARIS-in-AI-Offer (`docs/tutorials/lora_peft_tutorial.md`)](https://github.com/wanshuiyin/ARIS-in-AI-Offer/blob/904ffbcbc929769c4e5517e1a94daac7fa119bd5/docs/tutorials/lora_peft_tutorial.md)（固定 commit `904ffbc`）与 [ArronAI007/Awesome-AGI (`README.md`)](https://github.com/ArronAI007/Awesome-AGI/blob/87cf55c9bc44dbbb4eb0f57828311b08e3604480/README.md)，独立重构并扩展源码级对比。
- Liu et al., [DoRA: Weight-Decomposed Low-Rank Adaptation](https://arxiv.org/abs/2402.09353)，ICML 2024（Oral），及 Hugging Face 官方源码 [huggingface/peft (`src/peft/tuners/lora/dora.py` & `src/peft/tuners/lora/variants.py`)](https://github.com/huggingface/peft/blob/34d342a6156bd77a83f093b5be21fd8396edc451/src/peft/tuners/lora/dora.py)（固定 commit `34d342a`）：逐输出通道幅度-方向分解、分母范数 `weight_norm.detach()` 停止梯度与 `merge`/`unmerge` 范数缓存机制。
- Meng et al., [PiSSA: Principal Singular Values and Singular Vectors Adaptation of Large Language Models](https://arxiv.org/abs/2404.02948)，NeurIPS 2024（Spotlight），及 Hugging Face 官方源码 [huggingface/peft (`src/peft/utils/loftq_utils.py::_pissa_decomposition` & `src/peft/tuners/lora/model.py::subtract_mutated_init`)](https://github.com/huggingface/peft/blob/34d342a6156bd77a83f093b5be21fd8396edc451/src/peft/utils/loftq_utils.py)（固定 commit `34d342a`）：主奇异值分解初始化、残差基座构造与秩 $2r$ 标准 LoRA 转换公式。
- Kalajdzievski, [A Rank Stabilization Scaling Factor for Fine-Tuning with LoRA (rsLoRA)](https://arxiv.org/abs/2312.03732)，2023，及 Hugging Face 官方源码 [huggingface/peft (`src/peft/tuners/lora/layer.py`)](https://github.com/huggingface/peft/blob/34d342a6156bd77a83f093b5be21fd8396edc451/src/peft/tuners/lora/layer.py)（固定 commit `34d342a`）：$\gamma_r = \alpha/\sqrt{r}$ 渐近方差稳定推导。
- Hayou et al., [LoRA+: Efficient Low Rank Adaptation of Large Models](https://arxiv.org/abs/2402.12354)，ICML 2024，及 Hugging Face 官方源码 [huggingface/peft (`src/peft/optimizers/loraplus.py`)](https://github.com/huggingface/peft/blob/34d342a6156bd77a83f093b5be21fd8396edc451/src/peft/optimizers/loraplus.py)（固定 commit `34d342a`）：无限宽网络下 $\mathbf{A}/\mathbf{B}$ 算子尺度不对称分析与 $\eta_B = \lambda \eta_A$ 优化器分组实现。
- Yang et al., [CorDA: Context-Oriented Decomposition Adaptation of Large Language Models for Task-Aware Parameter-Efficient Fine-Tuning](https://arxiv.org/abs/2406.05223)，NeurIPS 2024，及 Biderman et al., [LoRA Learns Less and Forgets Less](https://arxiv.org/abs/2405.09673)，TMLR 2024。

来源访问与示例核验日期：**2026-11-12**。仅执行标准库下 DoRA 前向/合并/卸载范数校验、PiSSA 主奇异值分解与秩 $2r$ 转换、rsLoRA 缩放尺度及 LoRA+ 梯度下降数值验证，未运行多卡大模型微调基准压测。
