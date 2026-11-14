---
id: llm-0043
title: 大模型训练后剪枝与稀疏化（SparseGPT、Wanda、2:4 半结构化稀疏与 ShortGPT）是如何通过逆海森误差补偿、激活感知重要性与层影响力评估突破压缩瓶颈的？
category: llm
tags: [model-pruning, sparsegpt, wanda, 2-4-sparsity, shortgpt, structured-pruning]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开模型剪枝工程指南与评测笔记（Orchestra-Research/AI-Research-SKILLs / prabakaranc98/nthExperiment）扩展改编；SparseGPT（ICML 2023）、Wanda（ICLR 2024）、LLM-Pruner（NeurIPS 2023）、ShortGPT（2024）及官方源码核实（见参考）
status: published
updated: 2026-11-15
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-11-15
    updated: 2026-11-15
---

## 问题

在百亿至千亿参数大语言模型（LLM）的推理部署与端侧压缩中，除低比特量化（PTQ）外，**训练后剪枝与稀疏化（Post-Training Pruning & Sparsification）** 是削减计算量（FLOPs）与显存带宽的另一条核心技术路径。然而，在百亿参数以上的大模型中，由于隐藏层涌现出极端激活离群值（Emergent Activation Outliers），传统的“按权重绝对值剪枝（Magnitude Pruning）”在无需重训练的单次剪枝（One-Shot Pruning，$50\%$ 稀疏度）下会导致困惑度（PPL）雪崩；同时，工程团队还常常面临“非结构化稀疏（Unstructured Sparsity）无法在 GPU 上获得真实推理加速”以及“宽度结构化剪枝 vs 深度层剪枝如何权衡”的系统设计抉择。

请深入剖析以下三个核心问题：
1. **单次逐层重构剪枝的数学演进（Magnitude vs SparseGPT vs Wanda）**：为什么传统的权重幅值剪枝（$S_{i,j} = |W_{i,j}|$）在大模型上会彻底失效？**SparseGPT** 是如何将全局剪枝转化为逐层二次重构问题 $\min_{\widehat{W}} \|WX - \widehat{W}X\|_F^2$，并利用局部 Hessian 逆矩阵 $H^{-1} = (2XX^\top + \lambda I)^{-1}$ 的 Cholesky 分解实现无掩码冻结的逐列权重更新补偿的？**Wanda（Pruning by Weights and Activations）** 又是如何通过激活感知准则 $S_{i,j} = |W_{i,j}| \cdot \|X_j\|_2$ 与**按输出行（Per-Output Comparison Group）**比较，在不求逆矩阵、不更新剩余权重的前提下逼近 SparseGPT 精度的？请从对角 Hessian 近似视角证明 Wanda 与 SparseGPT 的内在数学等价性。
2. **稀疏拓扑与 GPU 硬件加速鸿沟（Unstructured vs 2:4 Semi-Structured vs Width Structured Pruning）**：为什么 $50\%$ 非结构化稀疏在现代 GPU Dense GEMM 算子下几乎拿不到端到端延迟收益？NVIDIA Ampere/Hopper 架构的 **2:4 半结构化稀疏（2:4 Fine-Grained Structured Sparsity）** 是如何通过每连续 $4$ 个权重强制保留至多 $2$ 个非零值与 `2-bit` 列索引元数据，在 Sparse Tensor Core 上实现硬件级 $2\times$ 算力吞吐翻倍的？若硬件不支持 2:4 稀疏，**宽度结构化剪枝（如 LLM-Pruner）** 如何沿着注意力头（Attention Heads）与 FFN 中间通道构建耦合依赖图（Coupled Dependency Graph）并基于一阶/二阶泰勒展开评估群组重要性？
3. **深度结构化剪枝与层冗余度发现（ShortGPT 与 Block Influence）**：与裁剪矩阵内部元素的宽度剪枝相比，直接整层移除 Transformer Block 的**深度剪枝（Depth / Layer Pruning，如 ShortGPT）** 在工程部署与 KV Cache 削减上有何独特优势？**ShortGPT** 是如何利用残差流隐状态在层输入 $X_l$ 与层输出 $X_{l+1}$ 之间的余弦相似度定义 **Block Influence（$\text{BI}_l$）** 指标的？为什么大模型中后部深层（Mid-to-Deep Layers）的 $\text{BI}_l$ 显著低于浅层与末层，使得切除 $20\%\sim 25\%$ 的深层 Block 仍能保持主体能力？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-11-15

**大模型训练后剪枝的核心矛盾在于“激活离群值引发的局部重构失真”与“稀疏掩码拓扑同 GPU 矩阵算子硬件特性的匹配度”：（1）在单次无训练剪枝中，大模型高于 6.7B 规模后会涌现出数值放大数十倍的激活离群通道（Outlier Channels），使“小权重乘以大激活”依然主导航向输出，导致只看 $|W_{i,j}|$ 的 Magnitude 剪枝彻底崩盘；SparseGPT 通过最小化层输出重构误差 $\|WX - \widehat{W}X\|_F^2$，基于最优脑外科手术（OBS）准则以 $S_{i,j} = \frac{W_{i,j}^2}{[H^{-1}]_{j,j}^2}$ 选出被剪权重，并用 Cholesky 上三角因子 $U = \text{Chol}(H^{-1})$ 对右侧未剪枝列执行 $\Delta W_{:, j:} = -\frac{W_{:, j}}{[H^{-1}]_{j,j}} [H^{-1}]_{j, j:}$ 的闭式误差补偿；Wanda 则发现当忽略跨通道协方差（取对角海森近似 $H \approx \text{diag}(\|X_1\|_2^2, \dots, \|X_{d_{\text{in}}}\|_2^2)$）时，OBS 重要性直接退化为 $S_{i,j} = |W_{i,j}| \cdot \|X_j\|_2$，配合按输出行（Per-Output Row）独立排序截断，以 $O(d_{\text{out}} d_{\text{in}})$ 零求逆开销消除离群值误杀；（2）在硬件执行层，50% 非结构化稀疏因不规则访存开销无法加速 Dense Tensor Core；NVIDIA 2:4 半结构化稀疏通过约束每 4 个相邻权重必有 2 个为 0，将权重矩阵压缩 50% 并附带 2-bit/元素的列索引，由硬件多路复用器直接抽取对应激活送入 Sparse Tensor Core 达成理论 $2\times$ 算力加速；而 LLM-Pruner 则通过识别残差连接下的结构耦合组（如 $W_Q, W_K, W_V$ 与 $W_O$、$\text{gate/up\_proj}$ 与 $\text{down\_proj}$）按泰勒梯度整列裁切矩阵维度；（3）在深度方向，ShortGPT 利用层输入输出隐状态的余弦方向变化率定义 $\text{BI}_l = 1 - \mathbb{E}_{t}\!\left[\frac{X_{l,t}^\top X_{l+1,t}}{\|X_{l,t}\|_2 \|X_{l+1,t}\|_2}\right]$，揭示了大模型中后部深层主要在既有语义方向上做微幅修正（$\text{BI}_l \to 0$），整层切除低 $\text{BI}$ 层不仅完全兼容任何标准推理引擎，还能按比例线性削减端到端延迟与 KV Cache 显存。**

在展开数学推导与源码分析前，建议结合题库内已有题目建立完整的模型压缩知识图谱：关于 GPTQ 二阶海森量化、AWQ 显著激活通道保护与 SmoothQuant 跨层离群值迁移（其中 GPTQ 与 SparseGPT 共享同一套逆海森 Cholesky 求解器，AWQ 与 Wanda 共享激活感知思想），请参阅 [llm-0035](llm-0035-ptq-gptq-awq-smoothquant.md)；关于多模型微调增量层面的随机稀疏重缩放（DARE）与幅值剪枝合并（TIES-Merging），请参阅 [llm-0042](llm-0042-model-merging-task-arithmetic-ties-dare-slerp.md)；关于注意力序列维度上的 KV Cache 稀疏驱逐（StreamingLLM、H2O、SnapKV 与 PyramidKV），请参阅 [llm-0039](llm-0039-kv-cache-eviction-streamingllm-h2o-snapkv-pyramidkv.md)；关于量化模型部署时的显存带宽与 Roofline 吞吐预算核算，请参阅 [llm-0016](llm-0016-quantization-local-memory-budget.md)；关于通过知识蒸馏将大模型压缩为小架构模型的有训练替代方案，请参阅 [llm-0015](llm-0015-knowledge-distillation-tradeoffs.md)。

---

### 1. 单次逐层剪枝演进：从 Magnitude 崩塌到 SparseGPT 逆海森补偿与 Wanda 激活感知

#### （1）为什么传统 Magnitude Pruning 在百亿参数大模型上彻底失效？
给定线性层权重 $W \in \mathbb{R}^{d_{\text{out}} \times d_{\text{in}}}$ 与校准集输入激活矩阵 $X \in \mathbb{R}^{d_{\text{in}} \times N}$（其中 $N = B \times L$ 为校准集中总 Token 数，通常取 $128$ 条长度为 $2048$ 的序列），该层的前向输出为 $Y = W X$。
- **传统幅值剪枝（Magnitude Pruning，Han et al., 2015）** 仅根据权重自身的绝对值 $S_{i,j}^{\text{mag}} = |W_{i,j}|$ 评估重要性，直接将绝对值最小的 $s\%$ 权重置零。
- **涌现离群值（Emergent Outliers）导致的致命误杀**：Dettmers et al.（LLM.int8(), 2022）与 Sun et al.（Wanda, ICLR 2024）指出，当 Transformer 参数规模超过约 6.7B 时，特定少数的输入特征通道 $j^* \in \{1, \dots, d_{\text{in}}\}$ 上会出现全序列恒定的**高幅值激活离群点**，其 $L_2$ 范数 $\|X_{j^*}\|_2$ 可达普通通道的 $20 \sim 100$ 倍！若某个权重 $W_{i, j^*}$ 绝对值较小（如 $|W_{i, j^*}| = 0.12$），但它乘在幅值高达 $10.0$ 的离群通道 $X_{j^*}$ 上，对输出 $Y_i$ 的实际贡献高达 $1.20$；而普通通道上的权重即使 $|W_{i, k}| = 0.45$，乘以幅值 $1.0$ 的激活也仅贡献 $0.45$。Magnitude 剪枝会愚蠢地抹杀 $|W_{i, j^*}| = 0.12$，引发层输出剧烈偏移并逐层放大，使 LLaMA-7B 在 $50\%$ 稀疏度下 WikiText-2 困惑度从 $5.68$ 劣化至 $17.29$（更小或未对齐模型甚至飙升至上万）。

#### （2）SparseGPT：逐层重构目标、OBS 最优更新与 Cholesky 逆海森分块求解
为了在不进行全模型反向传播的前提下精确剪枝，**SparseGPT**（Frantar & Alistarh, ICML 2023）将问题解耦为每一层独立的**掩码选择 + 剩余权重重构问题**：

$$\min_{M, \, \widehat{W}} \mathcal{L}(\widehat{W}) = \frac{1}{N} \left\| W X - (M \odot \widehat{W}) X \right\|_F^2 = \sum_{i=1}^{d_{\text{out}}} \frac{1}{N} \left\| w_i x - \hat{w}_i x \right\|_2^2$$

其中 $w_i, \hat{w}_i \in \mathbb{R}^{1 \times d_{\text{in}}}$ 为第 $i$ 个输出行向量。由于不同输出行的误差相互独立，所有输出行**共享同一个输入海森矩阵（Hessian Matrix）**！对第 $i$ 行的二次损失做二阶泰勒展开（本身即为精确二次型），其关于行向量 $w_i$ 的 Hessian 矩阵为（对照 `IST-DASLab/sparsegpt` 官方源码 `sparsegpt.py` 第 45–57 行与第 81–87 行）：

$$H = \frac{2}{N} X X^\top + \lambda I \in \mathbb{R}^{d_{\text{in}} \times d_{\text{in}}}, \qquad \lambda = \text{percdamp} \cdot \frac{1}{d_{\text{in}}} \text{Tr}(H) \quad (\text{默认 } \text{percdamp} = 0.01)$$

根据**最优脑外科手术（Optimal Brain Surgeon, Hassibi et al., 1993）** 的拉格朗日乘子法推导，若将第 $i$ 行第 $q$ 列的权重强制置零（即施加约束 $\hat{w}_{i,q} = 0$，产生权重改动 $e_q^\top \delta w_i + w_{i,q} = 0$），在仅允许调整尚未剪枝的后续列集合 $U = \{q, q+1, \dots, d_{\text{in}}\}$ 时：
1. **剪枝误差增量（重要性得分 $S_{i,q}^{\text{SparseGPT}}$）**：将 $w_{i,q}$ 置零所引起的最小二阶输出误差增量为：
   $$\Delta \mathcal{L}_{i,q} = \frac{w_{i,q}^2}{\left[ H_{U,U}^{-1} \right]_{q,q}} \implies S_{i,q}^{\text{SparseGPT}} = \frac{w_{i,q}^2}{\left(\sqrt{\left[H_{U,U}^{-1}\right]_{q,q}}\right)^2}$$
2. **剩余未剪枝权重的闭式误差补偿（Optimal Weight Update）**：一旦决定将 $w_{i,q}$ 置零（或量化为 $q_{i,q}$），右侧所有未处理列 $j > q$ 的最优补偿更新量为：
   $$\delta w_{i, j:} = -\frac{w_{i,q} - q_{i,q}}{\left[ H_{U,U}^{-1} \right]_{q,q}} \cdot \left[ H_{U,U}^{-1} \right]_{q, j:}$$
3. **为什么不需要对每个输出行重新求逆？（Cholesky 消元等价定理）**：
   因为不同输出行的剪枝掩码 $M_{i, :}$ 不同，若按传统 OBS 对每行各自保留的子矩阵求逆，复杂度将高达不可接受的 $O(d_{\text{out}} \cdot d_{\text{in}}^3)$。SparseGPT 的核心突破在于证明了：**当严格按照从左到右的固定列顺序 $q = 1, 2, \dots, d_{\text{in}}$ 依次做消元时，子矩阵逆 $H_{U,U}^{-1}$ 的首行与首对角元完全只取决于列序号 $q$，而与前面哪些列被置零无关！**
   在 `sparsegpt.py` 第 84–87 行中，仅需在剪枝前执行**一次**全矩阵逆的上三角 Cholesky 分解（`H = cholesky(H) -> cholesky_inverse(H) -> cholesky(H, upper=True)`，记上三角因子为 $U$，满足 $U^\top U = H^{-1}$）。
   此时对角元 `d = Hinv[i, i]` 恰好等于 $\sqrt{[H_{U,U}^{-1}]_{i,i}}$，而第 $i$ 行元素 `Hinv[i, i:]` 恰好等于 $\frac{[H_{U,U}^{-1}]_{i, i:}}{\sqrt{[H_{U,U}^{-1}]_{i,i}}}$。配合默认 `blocksize = 128` 的分块延迟更新（Lazy Batch-Updates），先在 $128$ 列块内做向量外积更新，块结束后再用一次矩阵乘法 `W[:, i2:] -= Err1.matmul(Hinv[i1:i2, i2:])` 更新全局右侧，将复杂度压缩至单次 $O(d_{\text{in}}^3)$，在单张 A100 上 1 小时内即可完成 175B 模型的单次剪枝。

#### （3）Wanda：对角海森近似与按输出行（Per-Output）激活感知剪枝
尽管 SparseGPT 精度极高，但计算 $O(d_{\text{in}}^3)$ 的 Cholesky 逆与逐列更新依然有一定耗时且修改了原始权重数值。**Wanda**（Sun et al., *A Simple and Effective Pruning Approach for Large Language Models*, ICLR 2024）提出了一个极其精简却效果惊人的准则：
1. **数学推导：为什么 Wanda 等价于对角海森近似下的 SparseGPT？**
   在 SparseGPT 的重要性指标 $S_{i,j}^{\text{SparseGPT}} = \frac{W_{i,j}^2}{[H^{-1}]_{j,j}}$ 中，如果我们忽略不同输入通道之间的交叉相关性（即假设 Hessian 为对角矩阵 $H \approx \text{diag}(H_{1,1}, \dots, H_{d_{\text{in}}, d_{\text{in}}})$，其中 $H_{j,j} = \frac{2}{N} \sum_{t=1}^N X_{j,t}^2 = \frac{2}{N} \|X_j\|_2^2$），则逆矩阵对角元直接为：
   $$\left[ H^{-1} \right]_{j,j} \approx \frac{1}{H_{j,j}} = \frac{N}{2 \|X_j\|_2^2}$$
   代入 SparseGPT 准则并两边取平方根（单调变换不改变排序），立刻得到 **Wanda 重要性评分**：
   $$S_{i,j}^{\text{Wanda}} = |W_{i,j}| \cdot \|X_j\|_2$$
   对照 `locuslab/wanda` 官方源码（`lib/layerwrapper.py` 第 30–36 行与 `lib/prune.py` 第 162 行）：
   - `WrappedGPT.add_batch` 在校准集前向传播中累加每个输入维度的均方激活范数：`self.scaler_row += torch.norm(inp, p=2, dim=1) ** 2 / self.nsamples`（即 $\frac{1}{N}\|X_j\|_2^2$）；
   - `prune_wanda` 一行代码计算重要性矩阵：`W_metric = torch.abs(subset[name].weight.data) * torch.sqrt(wrapped_layers[name].scaler_row.reshape((1,-1)))`（注意相差常数因子 $\frac{1}{\sqrt{N}}$ 不影响同行内排序）。
2. **关键设计：为什么必须按输出行（Per-Output Row）而非全层全局（Layer-Wise）或按输入列（Per-Input）比较？**
   因为激活范数 $\|X_j\|_2$ 是按输入列 $j$ 广播的：如果在同一个输入列 $j$ 内部比较不同输出行 $i$，$\|X_j\|_2$ 成了公共乘数，Wanda 就会完全退化回普通的 Magnitude 剪枝！只有在**同一个输出行 $i$ 内部（`dim=-1`）跨所有输入通道 $j \in \{1, \dots, d_{\text{in}}\}$ 比较** $|W_{i,j}| \cdot \|X_j\|_2$，才能让高激活离群通道上的小权重获得高分保护，同时保证每个输出神经元保留完全均衡的非零连接密度。

---

### 2. 稀疏拓扑与硬件加速：2:4 半结构化稀疏 vs LLM-Pruner 宽度结构化剪枝

#### （1）为什么 $50\%$ 非结构化稀疏（Unstructured Sparsity）在 GPU 上无法直接加速？
在非结构化稀疏中，任意坐标 $(i,j)$ 均可置零。若采用 CSR/COO 等稀疏格式存储，不仅每个非零浮点数需额外附带 $16\text{-bit} \sim 32\text{-bit}$ 索引（抵消了 $50\%$ 稀疏带来的显存节省），而且在 GPU Warp 并发执行时会导致严重的随机非对齐访存（Uncoalesced Memory Access）与线程分支发散。除非稀疏度高达 $90\%$ 以上，否则在 GPU 上运行稀疏算子（SpMM）往往比直接运行填零的 Dense GEMM 还要慢！

#### （2）NVIDIA 2:4 半结构化稀疏（2:4 Fine-Grained Structured Sparsity）的硬件加速机制
为了兼顾细粒度剪枝的高精度与 Tensor Core 的规整流水线，NVIDIA 自 Ampere（A100）及 Hopper（H100）架构起在硬件层面原生引入了 **2:4 结构化稀疏 Tensor Core**（Mishra et al., 2021）：
1. **拓扑约束（$N:M = 2:4$）**：沿着矩阵乘法的内部归约维度 $K$（即权重矩阵 $W$ 的行方向输入维度 $d_{\text{in}}$），每连续 $4$ 个相邻权重元素为一组，强制将其中重要性最低的 $2$ 个元素置为 $0$，至多保留 $2$ 个非零值（严格对应 $50\%$ 稀疏度）。在 `locuslab/wanda`（`lib/prune.py` 第 166–170 行）与 `IST-DASLab/sparsegpt`（`sparsegpt.py` 第 110–112 行）中，均通过步长为 $m=4$ 的窗口调用 `torch.topk(tmp, prune_n, dim=1, largest=False)` 生成掩码。
2. **压缩存储布局与 2-bit 元数据开销**：
   每 $4$ 个 FP16 权重（原本占 $4 \times 16 = 64\text{ bits}$）仅存储 $2$ 个非零 FP16 值（$32\text{ bits}$），并用两个 `2-bit` 无符号整数（共 $4\text{ bits}$，取值 $00_2 \sim 11_2$）记录这两个非零元素在原 $4$ 元组中的局部列下标 $(idx_0, idx_1) \in \{0, 1, 2, 3\}^2$。因此压缩后总体积为：
   $$\text{Compressed Size Ratio} = \frac{32\text{ bits (values)} + 4\text{ bits (metadata)}}{64\text{ bits (dense)}} = 56.25\% \quad (\text{节省 } 43.75\% \text{ 显存与带宽})$$
3. **硬件多路复用器（Hardware Multiplexer）零气泡执行**：
   在推理或训练执行 $Y = W X$ 时，Sparse Tensor Core 根据 `2-bit` 列索引通过硬件多路选择器（MUX），在单时钟周期内直接从稠密激活向量 $X$ 的每 $4$ 个相邻元素中精准挑出对应的 $2$ 个激活值参与乘加（MMA），跳过全部零乘法，使 Tensor Core 算力峰值直接翻倍（例如 A100 FP16 Dense 为 $312\text{ TFLOPS}$，2:4 Sparse FP16 达 $624\text{ TFLOPS}$；在 PyTorch 中可通过 `torch.sparse.to_sparse_semi_structured` 调用 cuSPARSELt 算子）。

#### （3）宽度结构化剪枝（LLM-Pruner）：耦合依赖图与泰勒通道重要性
当部署目标是不支持 2:4 稀疏的通用硬件（如 Apple Silicon、消费级显卡或旧款 CPU/NPU），或者需要真实缩小隐藏维度以压降激活显存时，必须采用**宽度结构化剪枝（Width Structured Pruning，如 LLM-Pruner，Ma et al., NeurIPS 2023）**，直接整行/整列删减权重矩阵的通道。
1. **残差连接下的结构耦合组（Structural Coupled Dependency Groups）**：
   为了保持残差主干维度 $d_{\text{model}}$ 的通道顺序不被破坏，LLM-Pruner 仅在每个子块**内部**的瓶颈维度上识别最小可裁剪耦合单元 $\mathcal{G}$：
   - **MHA / GQA 注意力头耦合组**：裁剪第 $h$ 个注意力头（或 GQA 中的一整个 KV Group）时，必须同步裁掉 $W_Q, W_K, W_V$ 中对应该头的输出行，以及输出投影矩阵 $W_O$ 中对应该头的输入列；
   - **SwiGLU FFN 中间通道耦合组**：在 $\text{FFN}(x) = (\text{SiLU}(x W_{\text{gate}}) \odot (x W_{\text{up}})) W_{\text{down}}$ 中，裁剪第 $k \in \{1, \dots, d_{\text{ffn}}\}$ 个中间神经元时，必须同步裁掉 $W_{\text{gate}}$ 的第 $k$ 输出行、$W_{\text{up}}$ 的第 $k$ 输出行，以及 $W_{\text{down}}$ 的第 $k$ 输入列！
2. **基于校准集梯度的泰勒群组重要性（Taylor Importance Scoring）**：
   由于宽度结构化剪枝同时移除了几千个耦合参数，仅看权重幅值或前向激活已不足以衡量跨层影响。LLM-Pruner 在极少量校准样本上做一次反向传播，用损失函数 $\mathcal{L}$ 的一阶/二阶泰勒展开评估移除整個耦合组 $\mathcal{G} = \{w_1, \dots, w_M\}$ 引起的全局损失波动：
   $$I_{\text{Taylor}}(\mathcal{G}) = \left| \mathcal{L}(\theta) - \mathcal{L}(\theta_{\mathcal{G}=0}) \right| \approx \left| \sum_{m \in \mathcal{G}} \left( \frac{\partial \mathcal{L}}{\partial w_m} w_m - \frac{1}{2} w_m H_{m,m} w_m \right) \right| \approx \sum_{m \in \mathcal{G}} \left| \frac{\partial \mathcal{L}}{\partial w_m} \cdot w_m \right|$$
   裁剪掉 $20\%$ 低分通道后，模型直接坍缩为一个维度更窄的标准稠密模型（如 $d_{\text{ffn}}$ 从 $11008$ 变为 $8806$），通常配合数千步轻量级 LoRA 微调即可快速恢复大部分精度。

---

### 3. 深度结构化剪枝（ShortGPT）：Block Influence（BI）与深层冗余度机制

#### （1）为什么在 LLM 中后部深层存在极高的“层冗余（Layer Redundancy）”？
在 Pre-LN 结构的现代 Transformer 中，第 $l$ 层（$l \in \{0, 1, \dots, L-1\}$）的前向传播遵循残差范式：

$$X_{l+1} = X_l + f_l(\text{RMSNorm}(X_l))$$

**ShortGPT**（Men et al., *Layers in Large Language Models are More Redundant Than You Expect*, 2024）与 **SliceGPT / Gromov et al. (2024)** 通过几何分析发现：
- **浅层（Early Layers，$l \approx 0 \sim 4$）** 负责将离散 Token Embedding 剧烈旋转投射到上下文语义空间，层输入与层输出夹角很大；
- **末层（Final Layers，$l \approx L-2 \sim L-1$）** 负责将语义向量对齐到词表 Logits 分布空间，变换同样剧烈；
- **中后部深层（Mid-to-Deep Layers，如 32 层模型中的第 $20 \sim 28$ 层）** 的子块输出增量 $\|f_l(X_l)\|_2 \ll \|X_l\|_2$，或者增量方向与残差主干 $X_l$ 高度平行，仅在已有方向上做微小的尺度精炼（即在常微分方程 ODE 视角下步长极小）。

#### （2）ShortGPT 的 Block Influence（BI）数学定义与工程收益
为了无梯度、零训练地量化第 $l$ 层对隐状态流形方向的改变程度，ShortGPT 定义了**块影响力（Block Influence, $\text{BI}_l$）**——即校准集中所有 Token 在穿过第 $l$ 层前后隐状态向量 $X_{l, t}, X_{l+1, t} \in \mathbb{R}^{d_{\text{model}}}$ 的平均余弦距离：

$$\text{BI}_l = 1 - \mathbb{E}_{X, \, t} \left[ \frac{X_{l, t}^\top X_{l+1, t}}{\left\| X_{l, t} \right\|_2 \left\| X_{l+1, t} \right\|_2} \right] \in [0, 2]$$

- 当 $\text{BI}_l \to 0$ 时，说明 $\cos(X_{l, t}, X_{l+1, t}) \to 1$，第 $l$ 层前后的隐状态几乎完全共线，该层是一个“近似恒等映射（Near-Identity Layer）”，冗余度最高；
- 当 $\text{BI}_l$ 较大时，说明该层对特征表示施加了不可替代的子空间旋转变换。

**ShortGPT 深度剪枝相比非结构化 / 宽度剪枝的三大工程杀手锏**：
1. **$100\%$ 硬件与推理框架零改造兼容**：删掉 $K$ 个低 $\text{BI}$ 层后，只需修改 `config.json` 中的 `num_hidden_layers = L - K` 并重新按序编号权重键名，vLLM、SGLang、TensorRT-LLM 与 llama.cpp 即可零代码修改直接加载运行；
2. **真实的端到端串行延迟削减**：在 Batch Size = 1 的自回归 Decode 阶段，GPU 算子启动开销（Kernel Launch Overhead）与层间同步与层数 $L$ 成正比。宽度剪枝虽减少了每层矩阵大小，但层数不变；而深度剪枝直接砍掉 $25\%$ 的串行层数，使 TTFT 与 TPOT 严格按比例下降；
3. **KV Cache 显存同步削减**：非结构化剪枝与 2:4 稀疏仅压缩了权重 $W$，**完全不减少 KV Cache**；而深度剪枝每删掉一层，就彻底省去了该层全部历史 Token 的 Key/Value 缓存！

```text
大模型训练后剪枝与稀疏化 (Post-Training Pruning) 四大范式与工程决策树:

  [ 优化目标: 降低大模型推理显存 / 提升吞吐 / 削减延迟, 且无全量重训练预算 ]
         │
         ├── 1. 需要连同 KV Cache 显存与串行算子层数一起削减, 且追求零算子改造?
         │      └──► 【深度层剪枝: ShortGPT】
         │             • 指标: Block Influence BI_l = 1 - E[cos(X_l, X_{l+1})]
         │             • 动作: 整层移除中后部低 BI 冗余 Block (改 num_hidden_layers)
         │             • 边界: 知识密集型 QA 较稳健, 复杂多步数学/代码推理需控剪枝率 (<=15~20%)
         │
         ├── 2. 部署在 NVIDIA Ampere/Hopper (A100/H100/RTX4090) 上, 追求最小精度损失 + Tensor Core 2x 加速?
         │      └──► 【半结构化 2:4 稀疏: SparseGPT / Wanda (2:4 模式)】
         │             • 拓扑: 每连续 4 个输入权重强制置零 2 个 + 2-bit 列索引元数据 (体积缩至 56.25%)
         │             • 算子: Wanda (|W_ij|·||X_j||_2, 极速免求逆) 或 SparseGPT (H^{-1} 逐列补偿, 更高精度)
         │
         ├── 3. 部署在通用硬件 (CPU/Apple M系列/不支持 2:4 的 NPU), 需缩小矩阵维度且允许轻量 LoRA 恢复?
         │      └──► 【宽度结构化剪枝: LLM-Pruner】
         │             • 拓扑: 构建 MHA 头 (Q/K/V行 + O列) 与 FFN 通道 (gate/up行 + down列) 耦合组
         │             • 算子: 校准集一阶/二阶 Taylor 梯度评估 I(G) = |Σ (∂L/∂w · w)| 整组裁切
         │
         └── 4. 仅做学术探索 / 稀疏 Delta 差分传输 / CPU 专用高稀疏引擎 (DeepSparse)?
                └──► 【非结构化稀疏: Wanda / SparseGPT (Unstructured 50%~70%)】
                       • 警告: 标准 GPU Dense GEMM 下无加速收益!
```

| 剪枝方法 / 维度 | 稀疏拓扑粒度 | 重要性评分准则 $S_{i,j}$ 或 $I$ | 是否更新剩余权重 | 算法复杂度（每层） | 是否减少 KV Cache | GPU 实测加速条件与工程特点 |
| :--- | :--- | :--- | :---: | :--- | :---: | :--- |
| **Magnitude Pruning** | 非结构化 / $N:M$ | $\|W_{i,j}\|$ | 否 | $O(d_{\text{out}} d_{\text{in}} \log d_{\text{in}})$ | 否 | 忽略激活离群值，在 $\ge 7\text{B}$ 大模型上 $50\%$ 稀疏即崩溃 |
| **SparseGPT** (ICML 2023) | 非结构化 / **2:4 半结构化** | $\dfrac{W_{i,j}^2}{\left([H^{-1}]_{j,j}\right)^2}$ | **是**（逆海森逐列补偿） | $O(d_{\text{in}}^3 + d_{\text{out}} d_{\text{in}}^2)$ | 否 | 精度最高（与 GPTQ 可联合执行）；需在 2:4 模式下借 Sparse Tensor Core 加速 |
| **Wanda** (ICLR 2024) | 非结构化 / **2:4 半结构化** | $\|W_{i,j}\| \cdot \|X_j\|_2$（按输出行） | **否** | $O(d_{\text{out}} d_{\text{in}} \log d_{\text{in}})$ | 否 | 无需矩阵求逆，速度比 SparseGPT 快百倍且精度极接近 |
| **LLM-Pruner** (NeurIPS 2023) | **宽度结构化**（Head / FFN 通道） | $\left\|\sum_{m \in \mathcal{G}} \frac{\partial \mathcal{L}}{\partial w_m} w_m\right\|$ | 是（通常配轻量 LoRA） | 1 次校准反向传播 | 仅当裁 GQA KV 头时减少 | 产出更窄的稠密小模型，全平台通用加速 |
| **ShortGPT** (2024) | **深度结构化**（整层 Transformer Block） | $\text{BI}_l = 1 - \mathbb{E}[\cos(X_l, X_{l+1})]$ | 否（可直接推理或微调） | 1 次校准前向传播 | **是**（按删层比例线性削减） | 零算子改造，成比例降低权重显存、KV Cache 与串行延迟 |

---

### 4. Python 3 标准库实现：2:4 半结构化剪枝（Magnitude vs Wanda vs SparseGPT）与 ShortGPT 仿真

下面的零依赖 Python 3 标准库代码严格对齐 `locuslab/wanda`（`lib/prune.py`、`lib/layerwrapper.py`）、`IST-DASLab/sparsegpt`（`sparsegpt.py`）与 `ShortGPT` 论文公式，验证了：
1. **2:4 半结构化稀疏下 Magnitude、Wanda 与 SparseGPT 的误差对比**：构造一个 $2 \times 4$ 权重矩阵与包含显著激活离群通道（第 $0$ 通道激活幅值 $\approx 10.0$、但权重绝对值最小 $|W_{:,0}| \in \{0.12, 0.15\}$；第 $1, 2, 3$ 通道激活幅值 $\approx 1.0$ 且强相关）的校准输入 $X$：
   - **Magnitude 2:4** 误杀了离群通道 $0$，导致层输出重构误差高达 $22.7688$；
   - **Wanda 2:4** 通过 $|W_{i,j}| \cdot \|X_j\|_2$ 成功识别并保留了离群通道 $0$，在不修改任何权重的情况下将重构误差降至 $8.3848$；
   - **SparseGPT 2:4** 通过上三角 Cholesky 逆海森分解 `cholesky_upper_of_hinv` 与逐列误差补偿 `W[r][j] -= err * Hinv[i][j]`，利用通道 $1, 2, 3$ 的强相关性将剪枝掉的通道权重精准补偿到剩余保留列上，使重构误差进一步暴降至 $0.2681$！
2. **ShortGPT 的 Block Influence（$\text{BI}_l$）层冗余识别**：在 4 层隐状态轨迹上计算余弦变化率，准确识别出隐状态方向几乎未发生旋转的第 $2$ 层（$\text{BI}_2 = 0.0$）并予以裁剪。

```python
import math
from typing import Dict, List


def matmul(A: List[List[float]], B: List[List[float]]) -> List[List[float]]:
    rows, inner, cols = len(A), len(B), len(B[0])
    return [
        [sum(A[i][k] * B[k][j] for k in range(inner)) for j in range(cols)]
        for i in range(rows)
    ]


def transpose(A: List[List[float]]) -> List[List[float]]:
    return [[A[i][j] for i in range(len(A))] for j in range(len(A[0]))]


def cholesky_lower(A: List[List[float]]) -> List[List[float]]:
    n = len(A)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                L[i][j] = math.sqrt(max(A[i][i] - s, 1e-12))
            else:
                L[i][j] = (A[i][j] - s) / L[j][j]
    return L


def cholesky_upper_of_hinv(H: List[List[float]]) -> List[List[float]]:
    """
    严格对齐 IST-DASLab/sparsegpt `sparsegpt.py` 第 84-87 行:
      H = torch.linalg.cholesky(H)
      H = torch.cholesky_inverse(H)
      H = torch.linalg.cholesky(H, upper=True)
      Hinv = H
    返回上三角矩阵 U, 满足 U^T @ U = H^{-1},
    其中 U[j][j] = sqrt((H^{-1})[j][j]), U[j][j:] = (H^{-1})[j, j:] / sqrt((H^{-1})[j][j])
    """
    n = len(H)
    L = cholesky_lower(H)
    inv_L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        inv_L[i][i] = 1.0 / L[i][i]
        for j in range(i + 1, n):
            inv_L[j][i] = -sum(L[j][k] * inv_L[k][i] for k in range(i, j)) / L[j][j]
    inv_H = matmul(transpose(inv_L), inv_L)

    U = [[0.0] * n for _ in range(n)]
    for i in range(n):
        s = sum(U[k][i] ** 2 for k in range(i))
        U[i][i] = math.sqrt(max(inv_H[i][i] - s, 1e-12))
        for j in range(i + 1, n):
            s_ij = sum(U[k][i] * U[k][j] for k in range(i))
            U[i][j] = (inv_H[i][j] - s_ij) / U[i][i]
    return U


def frobenius_sq_error(
    W_ref: List[List[float]], W_hat: List[List[float]], X: List[List[float]]
) -> float:
    Y_ref = matmul(W_ref, X)
    Y_hat = matmul(W_hat, X)
    return sum(
        (Y_ref[i][t] - Y_hat[i][t]) ** 2
        for i in range(len(Y_ref))
        for t in range(len(Y_ref[0]))
    )


def compare_2to4_pruning_methods(
    W: List[List[float]],
    X: List[List[float]],
    prune_n: int = 2,
    prune_m: int = 4,
    percdamp: float = 0.01,
) -> Dict[str, object]:
    """
    在 2:4 半结构化稀疏约束下对比:
    1. Magnitude Pruning: S_ij = |W_ij|
    2. Wanda (locuslab/wanda `lib/prune.py`): S_ij = |W_ij| * sqrt(scaler_row_j)
    3. SparseGPT (IST-DASLab/sparsegpt `sparsegpt.py`): 逆海森 OBS 准则 + 逐列残差补偿
    """
    rows, cols = len(W), len(W[0])
    nsamples = len(X[0])

    # 1. Magnitude 2:4
    W_mag = [list(r) for r in W]
    for r in range(rows):
        for g in range(0, cols, prune_m):
            drop_cols = sorted(range(g, g + prune_m), key=lambda c: abs(W_mag[r][c]))[:prune_n]
            for c in drop_cols:
                W_mag[r][c] = 0.0

    # 2. Wanda 2:4 (对齐 WrappedGPT.scaler_row = sum_t X_{j,t}^2 / nsamples)
    scaler_row = [sum(X[c][t] ** 2 for t in range(nsamples)) / nsamples for c in range(cols)]
    W_wanda = [list(r) for r in W]
    for r in range(rows):
        for g in range(0, cols, prune_m):
            drop_cols = sorted(
                range(g, g + prune_m),
                key=lambda c: abs(W_wanda[r][c]) * math.sqrt(scaler_row[c]),
            )[:prune_n]
            for c in drop_cols:
                W_wanda[r][c] = 0.0

    # 3. SparseGPT 2:4 (对齐 fasterprune: H = (2/N) X X^T + damp * I, 逐列更新右侧未剪枝权重)
    XXT = matmul(X, transpose(X))
    H = [[(2.0 / nsamples) * XXT[i][j] for j in range(cols)] for i in range(cols)]
    mean_diag = sum(H[i][i] for i in range(cols)) / cols
    for i in range(cols):
        H[i][i] += percdamp * mean_diag
    Hinv = cholesky_upper_of_hinv(H)

    W_sgpt = [list(r) for r in W]
    mask_sgpt = [[False] * cols for _ in range(rows)]
    for i in range(cols):
        if i % prune_m == 0:
            for r in range(rows):
                scores = [(W_sgpt[r][j] ** 2) / (Hinv[j][j] ** 2) for j in range(i, i + prune_m)]
                for k in sorted(range(prune_m), key=lambda k: scores[k])[:prune_n]:
                    mask_sgpt[r][i + k] = True
        d = Hinv[i][i]
        for r in range(rows):
            w = W_sgpt[r][i]
            q = 0.0 if mask_sgpt[r][i] else w
            W_sgpt[r][i] = q
            err = (w - q) / d
            for j in range(i + 1, cols):
                W_sgpt[r][j] -= err * Hinv[i][j]

    return {
        "err_mag": round(frobenius_sq_error(W, W_mag, X), 4),
        "err_wanda": round(frobenius_sq_error(W, W_wanda, X), 4),
        "err_sparsegpt": round(frobenius_sq_error(W, W_sgpt, X), 4),
        "row0_mag_kept": [c for c in range(cols) if W_mag[0][c] != 0.0],
        "row0_wanda_kept": [c for c in range(cols) if W_wanda[0][c] != 0.0],
        "row0_sgpt_weights": [round(x, 4) for x in W_sgpt[0]],
    }


def shortgpt_block_influence(
    layer_states: List[List[List[float]]],
    num_prune_layers: int = 1,
) -> Dict[str, object]:
    """
    对齐 ShortGPT (Men et al., 2024) 的层冗余度指标 Block Influence (BI):
    BI_l = 1 - E_t [ (X_{l,t} · X_{l+1,t}) / (||X_{l,t}||_2 ||X_{l+1,t}||_2) ]
    """
    num_layers = len(layer_states) - 1
    bi_scores: List[float] = []
    for l in range(num_layers):
        X_in, X_out = layer_states[l], layer_states[l + 1]
        cos_list = []
        for x_i, x_o in zip(X_in, X_out):
            dot = sum(a * b for a, b in zip(x_i, x_o))
            n_i = math.sqrt(sum(a * a for a in x_i))
            n_o = math.sqrt(sum(b * b for b in x_o))
            cos_list.append(dot / max(n_i * n_o, 1e-12))
        bi_scores.append(round(1.0 - sum(cos_list) / len(cos_list), 4))

    pruned_layers = sorted(range(num_layers), key=lambda l: bi_scores[l])[:num_prune_layers]
    return {"bi_scores": bi_scores, "pruned_layers": pruned_layers}


# --- 1. 验证 2:4 半结构化剪枝: Magnitude vs Wanda vs SparseGPT ---
W_demo = [
    [0.12, 0.45, 0.50, 0.42],
    [-0.15, 0.38, -0.44, 0.40],
]
# 通道 0 为显著激活离群通道 (~10.0) 但权重绝对值小; 通道 1, 2, 3 强相关 (~1.0)
X_demo = [
    [10.0, -9.5, 10.5, -10.0, 9.8, -10.2],
    [1.2, -1.0, 1.1, -0.9, 1.0, -1.1],
    [1.1, -0.9, 1.2, -1.0, 0.9, -1.0],
    [1.0, -1.1, 0.9, -0.8, 1.1, -0.9],
]
prune_res = compare_2to4_pruning_methods(W_demo, X_demo, prune_n=2, prune_m=4)
assert prune_res["row0_mag_kept"] == [1, 2]
assert prune_res["row0_wanda_kept"] == [0, 2]
assert prune_res["err_mag"] > prune_res["err_wanda"] > prune_res["err_sparsegpt"]
assert prune_res["err_mag"] == 22.7688
assert prune_res["err_wanda"] == 8.3848
assert prune_res["err_sparsegpt"] == 0.2681

# --- 2. 验证 ShortGPT Block Influence (BI) 深度层剪枝识别 ---
states_demo = [
    [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    [[0.6, 0.8, 0.0], [-0.5, 0.866, 0.0]],
    [[0.2, 0.4, 0.8944], [0.1, 0.3, 0.9487]],
    [[0.205, 0.398, 0.894], [0.102, 0.299, 0.948]],
    [[0.707, -0.707, 0.0], [-0.707, 0.0, 0.707]],
]
bi_res = shortgpt_block_influence(states_demo, num_prune_layers=1)
assert bi_res["bi_scores"] == [0.267, 0.6751, 0.0, 0.7689]
assert bi_res["pruned_layers"] == [2]

print(
    f"1. 2:4 Pruning Error: mag={prune_res['err_mag']:.4f} (kept={prune_res['row0_mag_kept']}), "
    f"wanda={prune_res['err_wanda']:.4f} (kept={prune_res['row0_wanda_kept']}), "
    f"sparsegpt={prune_res['err_sparsegpt']:.4f}"
)
print(f"2. SparseGPT Row-0 Compensated Weights: {prune_res['row0_sgpt_weights']}")
print(
    f"3. ShortGPT Block Influence: bi_scores={bi_res['bi_scores']}, "
    f"pruned_layers={bi_res['pruned_layers']}"
)
print("All SparseGPT, Wanda, 2:4 Sparsity, and ShortGPT assertions passed!")
```

实际运行输出：

```text
1. 2:4 Pruning Error: mag=22.7688 (kept=[1, 2]), wanda=8.3848 (kept=[0, 2]), sparsegpt=0.2681
2. SparseGPT Row-0 Compensated Weights: [0.0, 0.0, 1.2772, 1.1302]
3. ShortGPT Block Influence: bi_scores=[0.267, 0.6751, 0.0, 0.7689], pruned_layers=[2]
All SparseGPT, Wanda, 2:4 Sparsity, and ShortGPT assertions passed!
```

---

## 延伸 / 追问

**追问 1：在生产部署中，“模型剪枝（如 2:4 稀疏或 50% 非结构化剪枝）”与“低比特权重量化（如 4-bit AWQ/GPTQ）”应该如何做选型对比？两者能否联合叠加使用（Joint Sparsification + Quantization）？**
1. **单独使用时的性价比对比（为什么工业界首选 4-bit 量化而非 50% 剪枝）**：
   - 从模型体积与显存带宽缩减看，$50\%$ 稀疏（即使是 2:4 结构化稀疏，压缩至原始体积的 $56.25\%$）仅相当于约 $8\text{-bit} \sim 9\text{-bit}$ 量化的压缩率；而 $4\text{-bit}$ 量化（GPTQ/AWQ）能将显存直接压缩至 $25\%\sim 28\%$（$3.5\times \sim 4\times$ 压缩），且在 $4\text{-bit}$ 下的困惑度损失往往比 $2:4$ 稀疏还要小！
   - 从推理算子生态看，$4\text{-bit}$ Weight-Only 量化在 Memory-Bound 的自回归 Decode 阶段通过减少 HBM 读取量即可在任何 GPU 上直接获得 $2.5\times \sim 3\times$ 加速；而 $2:4$ 稀疏主要加速 Compute-Bound 的矩阵乘算力，必须依赖 NVIDIA Ampere+ Sparse Tensor Core。
2. **正交叠加（SparseGPT 2:4 + 4-bit GPTQ 联合压缩）**：
   Frantar & Alistarh 在 SparseGPT 原论文与官方源码（`sparsegpt.py` 第 116–120 行：`if hasattr(self, 'quantizer'): q = quantize(...)`）中证明了**剪枝与 GPTQ 量化可以在同一个 Cholesky 逆海森循环内单趟（Single-Pass）同步完成**！当遍历到第 $i$ 列时，若掩码判定剪枝则令 $q = 0$，否则令 $q = \text{Quant}(w)$，随后计算合并残差 $\text{err} = (w - q) / d$ 统一补偿给右侧所有未处理列。这使模型同时享有 **2:4 稀疏 + INT4 量化（等效 2-bit 存储开销）**，且总误差显著低于“先剪枝再独立量化”的两阶段流水线。

**追问 2：各层均匀设置相同的稀疏率（Uniform Layer Sparsity，如每层固定剪掉 50%）是最优的吗？OWL（Outlier Weighed Layerwise Sparsity）等非均匀层间稀疏度分配算法是如何改进 Wanda 和 SparseGPT 的？**
1. **均匀稀疏率在极高稀疏度（$\ge 70\%$）下的木桶效应**：
   Transformer 不同层对剪枝的敏感度差异极大——包含大量极端激活离群值的层（或靠近输入/输出端的首尾层）一旦被强行剪掉 $70\%$ 权重，重构误差会急剧爆炸，成为全网精度的短板；而特征分布均匀的中间层即便剪掉 $80\%$ 依然稳健。
2. **OWL（Yin et al., ICML 2024）的离群值加权层间稀疏分配**：
   OWL 定义每一层 $l$ 的**离群值比例（Outlier Ratio, $D_l$）** 为该层所有 Wanda 激活加权得分 $A_{i,j} = |W_{i,j}| \cdot \|X_j\|_2$ 中超过全层均值 $M$ 倍（如 $M=5$）的元素占比。由于离群值越集中的层包含越多不可替代的骨干通道，OWL 为離群值比例 $D_l$ 越高的层分配越低的稀疏率 $s_l$（满足全局平均稀疏率为目标值 $S_{\text{target}}$ 且 $s_l \in [S_{\text{target}} - \lambda, S_{\text{target}} + \lambda]$）。实验表明，在 $70\%$ 全局稀疏度下，OWL 将 LLaMA-7B 的 Wanda 困惑度从 $80+$ 大幅压降至 $20$ 以内。

**追问 3：除了LLM-Pruner 的泰勒梯度剪枝和 ShortGPT 的整层删除，SliceGPT（Ashkboos et al., ICLR 2024）提出的“基于计算不变性（Computational Invariance）的正交旋转切片剪枝”是什么原理？**
1. **RMSNorm 下的正交旋转不变性（Orthogonal Transformation Invariance）**：
   对于任意正交矩阵 $Q \in \mathbb{R}^{d_{\text{model}} \times d_{\text{model}}}$（满足 $Q^\top Q = Q Q^\top = I$），向量旋转前后的 $L_2$ 范数严格不变，因此 $\text{RMSNorm}(x Q) = \text{RMSNorm}(x) Q$。若我们在每个子块的输入投影矩阵左乘 $Q^\top$（即 $W_{\text{in}}' = Q^\top W_{\text{in}}$），并在输出投影矩阵右乘 $Q$（即 $W_{\text{out}}' = W_{\text{out}} Q$），整个 Transformer 的数学输出完全恒等不变！
2. **PCA 主成分对齐与直接特征维度切片**：
   SliceGPT 在校准集上对每一层归一化后的隐状态协方差矩阵 $\Sigma_l = X_l^\top X_l$ 做特征值分解（PCA），选取特征向量组成正交矩阵 $Q_l$ 将残差流旋转到主成分空间。旋转后，隐状态能量高度集中在前 $d_{\text{new}}$ 个主成分维度上，末尾 $d_{\text{model}} - d_{\text{new}}$ 个维度的方差趋近于 $0$。此时无需任何梯度反传，直接像“切蛋糕”一样把权重矩阵与残差流末尾的次要特征行列整块切掉（并对残差跳跃连接补充轻量投影矩阵 $Q_l^\top Q_{l+1}$），即可实现无梯度、硬件友好的稠密维度压缩。

---

## 常见误区

- **误区一：“只要用 Wanda 或 SparseGPT 把大模型的 50% 权重置为 0（Unstructured 50% Sparsity），保存下来的模型文件就会直接缩小一半，并且在 PyTorch / vLLM 中推理速度直接翻倍。”**
  事实：**未转换存储格式与硬件专用稀疏拓扑前，非结构化置零既不减小模型体积，也不带来任何 GPU 推理加速！** 在内存中将 FP16 张量的一半元素改为 `0.0`，它依然是一个占满原空间的稠密 FP16 张量，Dense GEMM 算子照样会老老实实执行每一个乘零运算。若要获得真实的 GPU 推理加速，必须采用 **NVIDIA 2:4 半结构化稀疏模式**并调用 `cuSPARSELt` / TensorRT-LLM 的 Sparse Tensor Core 算子，或者采用 **LLM-Pruner / ShortGPT / SliceGPT** 等直接缩小张量形状或层数的结构化剪枝。
- **误区二：“Wanda 的重要性公式 $S_{i,j} = |W_{i,j}| \cdot \|X_j\|_2$ 很简单，所以在实现时直接对整层矩阵 `S.flatten()` 排序，删掉分数最低的 50% 元素即可。”**
  事实：**Wanda 取得高精度的核心灵魂之一是按输出行（Per-Output Row，`dim=-1`）独立排序截断，而不是全层全局排序（Layer-Wise）或按输入列排序（Per-Input Column）！** 在 `locuslab/wanda` 源码（`lib/prune.py` 第 172 行 `torch.sort(W_metric, dim=-1)`）与原论文 Table 5 消融实验中明确证明：如果按输入列比较，激活范数 $\|X_j\|_2$ 在同一列内是常数，Wanda 会 100% 退化为失效的 Magnitude 剪枝；如果全层拉平全局比较，某些输出神经元会被剪空导致特征坍塌；唯有在每个输出行内部跨不同输入通道比较，才能发挥激活范数保护离群通道并均衡保留每个输出容量的作用。
- **误区三：“ShortGPT 证明了可以零成本删掉大模型 25% 的深层 Block，因此任何生产业务场景都可以无脑删掉后四分之一的层来白嫖加速。”**
  事实：**ShortGPT 的无损表现在“知识检索/多选题基准（如 MMLU、HellaSwag）”与“多步生成式数学/代码推理（如 GSM8K、HumanEval）”之间存在显著分化！** 知识型多选题主要依赖浅中层提取的实体关联，中后部深层的微小修正对其排名影响不大；但在需要长链条逻辑演算的数学、代码生成与复杂工具调用任务中，中后部深层恰恰承担着中间推理状态的步进迭代，一旦单次删层比例超过 $15\%\sim 20\%$ 且不做后训练恢复（LaCo / LoRA Healing），生成式推理准确率会出现断崖式下跌。

---

## 参考

- 选题线索：[Orchestra-Research/AI-Research-SKILLs (`19-emerging-techniques/model-pruning/references/wanda.md`)](https://github.com/Orchestra-Research/AI-Research-SKILLs/blob/773a52944ba4747a18bd4ae9ade53fff041adcbc/19-emerging-techniques/model-pruning/references/wanda.md)（固定 commit `773a529`）与 [prabakaranc98/nthExperiment (`library/bricks/sparsegpt-wanda-one-shot-pruning.md`)](https://github.com/prabakaranc98/nthExperiment/blob/65d8b13912c29734c2e428d9e61394258512c9d6/library/bricks/sparsegpt-wanda-one-shot-pruning.md)（固定 commit `65d8b13`），独立推导数学机制并扩展源码级对比。
- Frantar & Alistarh, [SparseGPT: Massive Language Models Can Be Accurately Pruned in One-Shot](https://arxiv.org/abs/2301.00774)，ICML 2023，及官方源码 [IST-DASLab/sparsegpt (`sparsegpt.py`)](https://github.com/IST-DASLab/sparsegpt/blob/147d2159dc4f3e9f73e47b32c04d7b3708f44436/sparsegpt.py)（固定 commit `147d215`）：逐层海森矩阵构造、Cholesky 逆分解、OBS 最优列更新与 2:4 半结构化联合剪枝量化实现。
- Sun et al., [A Simple and Effective Pruning Approach for Large Language Models (Wanda)](https://arxiv.org/abs/2306.11695)，ICLR 2024，及官方源码 [locuslab/wanda (`lib/prune.py`, `lib/layerwrapper.py`)](https://github.com/locuslab/wanda/blob/8e8fc87b4a2f9955baa7e76e64d5fce7fa8724a6/lib/prune.py)（固定 commit `8e8fc87`）：激活感知权重重要性 $|W_{i,j}| \cdot \|X_j\|_2$ 与按输出行（Per-Output）比较分组实现。
- Mishra et al., [Accelerating Sparse Deep Neural Networks](https://arxiv.org/abs/2104.08378)，2021：NVIDIA Ampere Sparse Tensor Core 的 2:4 半结构化稀疏硬件架构与 2-bit 索引压缩格式。
- Ma et al., [LLM-Pruner: On the Structural Pruning of Large Language Models](https://arxiv.org/abs/2305.11627)，NeurIPS 2023，及官方源码 [horseee/LLM-Pruner](https://github.com/horseee/LLM-Pruner/tree/128a07d977f9b205d60ab14cfbc6a78f8a8e39d2)（固定 commit `128a07d`）：耦合结构依赖图发现与一阶/二阶泰勒通道重要性评估。
- Men et al., [ShortGPT: Layers in Large Language Models are More Redundant Than You Expect](https://arxiv.org/abs/2403.03853)，2024，及 Ashkboos et al., [SliceGPT: Compress Large Language Models by Deleting Rows and Columns](https://arxiv.org/abs/2401.15024)，ICLR 2024：基于 Block Influence（BI）的深度层剪枝与基于正交旋转不变性的特征切片剪枝。

来源访问与示例核验日期：**2026-11-15**。仅执行标准库下 2:4 半结构化剪枝（Magnitude、Wanda 与 SparseGPT 逆海森补偿）及 ShortGPT Block Influence 层冗余评估的数值验证，未运行百亿参数大模型 GPU 稀疏推理基准评测。
