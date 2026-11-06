---
id: llm-0035
title: 大模型训练后量化（PTQ）中，GPTQ、AWQ 与 SmoothQuant 是如何分别通过 Hessian 二阶误差补偿、显著激活通道保护与跨层离群值平滑迁移解决精度崩塌的？
category: llm
tags: [ptq, gptq, awq, smoothquant, quantization, activation-outlier]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开 AI 量化面试题库与系统设计指南扩展改编；GPTQ（ICLR 2023）、AWQ（MLSys 2024）、SmoothQuant（ICML 2023）原论文及官方源码核实（见参考）
status: published
updated: 2026-11-07
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-11-07
    updated: 2026-11-07
---

## 问题

在将百亿至千亿参数的大语言模型（LLM）压缩部署到生产环境时，最朴素的四舍五入均匀量化（Round-to-Nearest, RTN）一旦降到 4-bit 权重（W4A16）或 8-bit 权重加激活（W8A8），往往会导致困惑度（Perplexity）暴涨甚至输出乱码。工业界主流推理引擎（如 vLLM、SGLang、TensorRT-LLM）广泛采用 **GPTQ**、**AWQ** 与 **SmoothQuant** 三大训练后量化（Post-Training Quantization, PTQ）方案。

请深入剖析以下三个核心问题：
1. **为什么 LLM 的训练后量化比传统视觉模型更难，且 W4A16 与 W8A8 面临的瓶颈截然不同**：大模型在参数规模超过约 $6.7\text{B}$ 后涌现出的“系统性激活离群值（Emergent Activation Outliers）”具有怎样的维度分布规律？为什么它对激活量化（W8A8）是致命灾难，同时又使权重不同输入通道的量化误差敏感度产生百倍差异？
2. **GPTQ、AWQ 与 SmoothQuant 的核心数学机制**：
   - **GPTQ** 是如何基于最优脑外科医生（OBS）二阶泰勒展开，利用逆 Hessian 矩阵 $H^{-1}$ 的上三角 Cholesky 分解对未量化权重执行逐列（及分块）误差补偿的？
   - **AWQ** 为什么主张“不靠回传误差修改权重值，而是按激活幅值缩放保护 $1\%$ 显著权重通道”？其缩放搜索公式 $s = s_X^\alpha$ 是如何定义的？
   - **SmoothQuant** 是如何通过対角平滑矩阵 $S = \operatorname{diag}(s_1, \dots, s_K)$ 将激活离群值迁移给权重的？如何将其无开销地融合（Fuse）进上游 `LayerNorm` / `RMSNorm`？
3. **工程落地与 Roofline 硬件亲和性选型**：在 Prefill（计算受限）与 Decode（访存带宽受限）两个阶段，W4A16（GPTQ/AWQ）与 W8A8（SmoothQuant/FP8）各自的真实加速收益来自哪里？GPTQ 的 `act_order`（`desc_act`）重排为什么能救回极低位宽精度，却可能导致解码吞吐下降？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-11-07

**大模型 PTQ 的核心矛盾源于固定通道上的高幅值激活离群值（Activation Outliers，幅值可达常规通道的 $50\times \sim 100\times$）：（1）GPTQ（W4A16）从“输出重构误差二阶补偿”切入，将逐层量化建模为 $\min_{\hat{W}} \|XW^\top - X\hat{W}^\top\|_F^2$，基于 Hessian 矩阵 $H = \frac{2}{B}X^\top X$ 的逆矩阵上三角 Cholesky 因子 $U$，在量化第 $q$ 列权重后按 $\delta_{\cdot, j>q} = -\frac{w_q - \operatorname{ quant }(w_q)}{U_{qq}} U_{q, j>q}$ 精确调整右侧未量化权重；（2）AWQ（W4A16）从“显著通道缩放保护”切入，指出乘上大激活的权重通道一旦产生舍入误差就会被成倍放大，故引入等价对角变换 $Y = (X S^{-1})(W S)^\top$，以激活均值幂次 $s_j = (\mathbb{E}|X_{\cdot, j}|)^\alpha$（网格搜索 $\alpha \in [0, 1]$）放大显著权重列以压低其相对量化误差，避免了 GPTQ 对校准集分布的过拟合；（3）SmoothQuant（W8A8）从“激活-权重量化难度平衡”切入，针对激活沿内积维（$K$ 维）无法独立缩放硬伤，用 $s_j = \max(|X_{\cdot, j}|)^\alpha / \max(|W_{\cdot, j}|)^{1-\alpha}$（常取 $\alpha=0.5$）削平激活尖峰并转嫁给易量化的权重，且可将 $S^{-1}$ 静态融合进上游 `RMSNorm`/`LayerNorm` 参数，实现零额外运行开销的 INT8 Tensor Core 矩阵乘。**

在展开数学推导与代码实现前，建议结合仓内相关题目建立完整知识坐标系：关于量化后模型显存容量账本、分组元数据开销与 Roofline 带宽上界估算，请参阅 [llm-0016](llm-0016-quantization-local-memory-budget.md)；关于预填充（Prefill）计算受限与解码（Decode）访存带宽受限的算力特征，请参阅 [llm-0018](llm-0018-kv-cache-prefill-decode.md)；关于量化与知识蒸馏、SFT 微调的维度差异，请参阅 [llm-0015](llm-0015-knowledge-distillation-tradeoffs.md)。

---

### 1. 为什么 LLM 量化极易崩塌？系统性激活离群值与内积维度的硬件约束

#### （1）系统性激活离群值（Emergent Outliers）的二维不对称分布
在参数量达到 $6.7\text{B}$ 以上的 Transformer 中（Dettmers et al., *LLM.int8()*, NeurIPS 2022），隐藏层激活张量 $X \in \mathbb{R}^{(B\cdot L) \times K_{\text{in}}}$ 呈现出高度结构化的各向异性：
- **沿通道维（Channel / Hidden 维 $K_{\text{in}}$）高度集中**：仅有约 $0.1\% \sim 1\%$ 的特定隐藏通道会出现幅值高达 $50 \sim 100$ 的极端离群值，而其余 $99\%$ 通道的幅值均在 $[-1, 1]$ 附近。
- **跨 Token 维（Sequence 维 $B\cdot L$）高度稳定**：这些离群值始终固定出现在相同的几个通道索引 $j \in \mathcal{O}$ 上，几乎在所有输入 Token 上持续触发。

#### （2）为什么激活不能像权重一样做“按通道（Per-Channel）”量化？
设线性层计算为 $Y = X W^\top$，其中激活 $X \in \mathbb{R}^{M \times K}$（$M = B\cdot L$ 为 Token 数，$K$ 为输入通道维），权重 $W \in \mathbb{R}^{N \times K}$（$N$ 为输出通道维）：

$$\hat{Y}_{m, n} = \sum_{k=1}^{K} X_{m, k} W_{n, k}$$

若想利用硬件 INT8 Tensor Core（如 `mma.sync.aligned.m16n8k32.s32.s8.s8`）加速矩阵乘法，整数累加器必须在整个内积求和维 $k \in \{1, \dots, K\}$ 上直接对整数求和，再在矩阵乘循环外部一次性乘回浮点缩放因子（Scale）：

$$Y_{m, n} \approx s_X^{(m)} \cdot s_W^{(n)} \sum_{k=1}^{K} Q_X(m, k) \, Q_W(n, k)$$

- **允许的缩放维度（外维 $M$ 与 $N$）**：$s_X^{(m)}$ 仅依赖行号 $m$（即 **Per-Token 激活量化**），$s_W^{(n)}$ 仅依赖列号 $n$（即 **Per-Output-Channel 权重量化**）。二者都与求和内积下标 $k$ 无关，可以提到 $\sum_{k=1}^K$ 求和号外面！
- **禁止的硬件缩放维度（内积维 $K$）**：激活离群值恰好沿通道维 $k$ 分布。如果我们对激活做 Per-Input-Channel 量化（即每个通道 $k$ 一个独立的 $s_X^{(k)}$），求和项就变成了 $\sum_{k=1}^K s_X^{(k)} Q_X(m, k) Q_W(n, k)$——缩放因子无法提出求和号外，硬件整数 GEMM 流水线彻底无法使用（除非像 W4A16 那样在寄存器内先反量化回 FP16，或采用每 $16/32$ 个元素硬件微块缩放的 Blackwell MXFP4/NVFP4）。

因此，在 Per-Token 激活量化下，那 $1\%$ 的离群通道会把整行 Token 的 $s_X^{(m)} = \max_k |X_{m, k}| / 127$ 撑大几十倍，导致其余 $99\%$ 的正常通道除以巨大的 $s_X^{(m)}$ 后全部被舍入成 $0$ 或 $\pm 1$，有效位宽瞬间归零！

#### （3）四大主流量化路线全景对比

| 维度 | RTN（朴素四舍五入） | GPTQ（ICLR 2023） | AWQ（MLSys 2024） | SmoothQuant（ICML 2023） |
| :--- | :--- | :--- | :--- | :--- |
| **目标位宽配置** | W8A16 / W4A16 | **W4A16 / W3A16**（Weight-Only） | **W4A16 / W3A16**（Weight-Only） | **W8A8**（Weight + Activation） |
| **核心数学机制** | 按分组极值独立舍入 $\operatorname{round}(W/s)$，无跨列补偿 | 基于逆 Hessian $H^{-1} = U^\top U$ 的 **OBS 二阶逐列误差回传补偿** | 基于激活幅值 $s_X^\alpha$ 的**显著权重通道等价放大保护** | 对角平滑变换 $Y=(XS^{-1})(SW^\top)$ **将激活离群值迁移给权重** |
| **对校准集（Calib）的依赖** | 无需校准集（Zero-shot） | 强依赖（需计算 $H = \frac{2}{B}X^\top X$ 并改写权重数值） | 弱依赖（仅统计通道平均激活幅值搜索标量 $\alpha$，不改写原始分布） | 弱依赖（仅统计校准集各通道最大绝对值 $\max|X_{\cdot, j}|$） |
| **分布外（OOD）泛化性** | 差（W4/W3 严重掉点） | 中（校准集过小或领域单一时易过拟合校准分布） | **极佳**（保留权重原始相对几何结构，多模态/代码泛化稳健） | 佳（W8A8 下接近 FP16 无损） |
| **主要加速阶段** | Decode（省显存带宽） | **Decode**（省 $4\times$ 权重访存带宽，配合 Marlin 内核） | **Decode**（省 $4\times$ 权重访存带宽，无重排开销） | **Prefill + 大 Batch Decode**（激活 INT8 Tensor Core $2\times$ 算力） |

---

### 2. 三大算法的核心数学推导与官方源码对齐

#### （1）GPTQ：基于 OBS 二阶泰勒展开与 Cholesky 因子的逐列误差补偿

GPTQ（Frantar et al., ICLR 2023，官方仓库 `IST-DASLab/gptq`）针对单层权重的每一行 $\mathbf{w} \in \mathbb{R}^{K}$，最小化校准集输入 $X \in \mathbb{R}^{M \times K}$ 下的层输出重构平方误差：

$$\mathcal{L}(\hat{\mathbf{w}}) = \|X \mathbf{w}^\top - X \hat{\mathbf{w}}^\top\|_2^2 = (\hat{\mathbf{w}} - \mathbf{w}) \left(X^\top X\right) (\hat{\mathbf{w}} - \mathbf{w})^\top$$

在原权重 $\mathbf{w}$ 处作二阶泰勒展开，其 Hessian 矩阵为 $H = \frac{2}{M} X^\top X \in \mathbb{R}^{K \times K}$（注意：**同一线性层的所有 $N$ 个输出通道共享同一个 $H$**！）。为防止校准集中存在死通道导致 $H$ 奇异，官方源码（`gptq.py` 第 88–90 行）先注入阻尼项：

$$H \leftarrow H + \lambda_{\text{damp}} \cdot \left(\frac{1}{K}\sum_{i=1}^K H_{ii}\right) I, \quad \lambda_{\text{damp}} = 0.01$$

**拉格朗日乘子法推导 OBS 最优补偿步**：
假设当前准备将第 $q$ 个输入通道权重 $w_q$ 量化为离散值 $q_q = \operatorname{quant}(w_q)$，即施加硬约束 $\mathbf{e}_q^\top \boldsymbol{\delta} = q_q - w_q$（其中 $\boldsymbol{\delta} = \hat{\mathbf{w}} - \mathbf{w}$）。构造拉格朗日函数：

$$\mathcal{F}(\boldsymbol{\delta}, \mu) = \frac{1}{2} \boldsymbol{\delta}^\top H^{(q)} \boldsymbol{\delta} + \mu \left(\mathbf{e}_q^\top \boldsymbol{\delta} - (q_q - w_q)\right)$$

对 $\boldsymbol{\delta}$ 求偏导并令其为 $0$，得 $H^{(q)} \boldsymbol{\delta} = -\mu \mathbf{e}_q \implies \boldsymbol{\delta} = -\mu \left(H^{(q)}\right)^{-1} \mathbf{e}_q$。代入约束条件解出乘子 $\mu = -\frac{q_q - w_q}{[(H^{(q)})^{-1}]_{qq}}$，从而得到**量化第 $q$ 列后对所有剩余未量化列 $j > q$ 的最优权重补偿公式**：

$$\boldsymbol{\delta}_{j > q}^* = -\frac{w_q - \operatorname{quant}(w_q)}{\left[\left(H^{(q)}\right)^{-1}\right]_{qq}} \cdot \left[\left(H^{(q)}\right)^{-1}\right]_{q, j > q}, \quad \Delta \mathcal{L}_q^* = \frac{\left(w_q - \operatorname{quant}(w_q)\right)^2}{2 \left[\left(H^{(q)}\right)^{-1}\right]_{qq}}$$

**为什么要用 Cholesky 分解？（`gptq.py` 第 91–94 行核心技巧）**
如果每量化完一列 $q$，都要重新按高斯消元更新剩余 $(K-q) \times (K-q)$ 的子矩阵逆 $(H^{(q)})^{-1}$，不仅面临累计浮点舍入误差导致的非正定崩溃，而且计算繁琐。GPTQ 证明了一个精妙的线性代数性质：对全局逆矩阵 $H^{-1}$ 执行**上三角 Cholesky 分解**：

$$H^{-1} = U^\top U \quad (\text{其中 } U \in \mathbb{R}^{K \times K} \text{ 为上三角矩阵})$$

由于 $U$ 是上三角矩阵，$H^{-1}$ 的右下角子块无需重复求逆，**$U$ 的第 $q$ 行元素 $U_{q, q:K}$ 恰好与消元后条件逆矩阵 $(H^{(q)})^{-1}$ 的首行元素严格成正比**：

$$\frac{\left[\left(H^{(q)}\right)^{-1}\right]_{q, j}}{\left[\left(H^{(q)}\right)^{-1}\right]_{qq}} \equiv \frac{U_{q, j}}{U_{q, q}} \quad (\forall j \ge q)$$

结合 $B_{\text{block}} = 128$ 的延迟分块更新（Lazy Batch Updates），GPTQ 在块内先用 $U_{q, j}$ 逐列更新，块结束时再用一次矩阵乘法 `W[:, i2:] -= Err1 @ Hinv[i1:i2, i2:]` 批量更新右侧所有块，将耗时从数十小时缩短至数十分钟。

---

#### （2）AWQ：基于激活幅值的显著权重通道保护与一维网格搜索

AWQ（Lin et al., MLSys 2024 Best Paper，官方仓库 `mit-han-lab/llm-awq`）提出了截然不同的洞察：
1. **权重并非生而平等**：仅占总数 $0.1\% \sim 1\%$ 的显著权重通道（Salient Weight Channels）一旦保持 FP16 不量化，W3/W4 模型的 PPL 就能从崩盘边缘瞬间恢复；且挑出这 $1\%$ 显著通道的标准**不是看权重 $|W|$ 自身有多大，而是看它对应的输入激活通道平均幅值 $s_X = \mathbb{E}[|X|]$ 有多大**！
2. **如何不用混合精度（避免硬件分支碎片），也能保护显著通道？——等价缩放放大**：
   对第 $j$ 个输入通道引入缩放系数 $s_j > 1$，由于在量化时通常按固定分组（如 `group_size = 128`）共享一个缩放步长 $\Delta = \frac{\max(\mathbf{w}_g)}{2^{b-1}-1}$，将被放大后的显著权重 $w_j' = w_j \cdot s_j$ 量化再除回 $s_j$ 时，其等效量化误差为：

   $$\text{Err}(w_j') = \left|\frac{\operatorname{round}(w_j s_j / \Delta') \cdot \Delta'}{s_j} - w_j\right| \approx \frac{\Delta'}{s_j} \cdot \left|\text{round\_err}\right|$$

   只要被放大的单个通道 $w_j s_j$ 没有把整个 128 元素分组的极值撑大过多（即 $\Delta' \approx \Delta$），该显著通道的**有效量化步长就缩小到了原来的 $\frac{1}{s_j}$**！

3. **平衡显著通道与非显著通道的网格搜索（`auto_scale.py` 第 126–149 行）**：
   若 $s_j$ 过大，反而会把分组极值 $\Delta'$ 撑爆，连累同组内的其余 127 个非显著权重。AWQ 将全通道缩放向量参数化为激活均值的幂函数，并在区间 $[0, 1]$ 上做 $n_{\text{grid}} = 20$ 步的快速网格搜索：

   $$\mathbf{s}_X = \frac{1}{M}\sum_{m=1}^{M} |X_{m, \cdot}|, \quad \tilde{\mathbf{s}}(\alpha) = \left(\mathbf{s}_X\right)^\alpha, \quad \mathbf{s}(\alpha) = \frac{\tilde{\mathbf{s}}(\alpha)}{\sqrt{\max(\tilde{\mathbf{s}}) \cdot \min(\tilde{\mathbf{s}})}}$$

   $$\alpha^* = \underset{\alpha \in \{0, 0.05, 0.10, \dots, 0.95\}}{\arg\min} \left\| \operatorname{Block}(X; W) - \operatorname{Block}\left(X \cdot \operatorname{diag}(\mathbf{s})^{-1}; \; Q(W \cdot \operatorname{diag}(\mathbf{s}))\right) \right\|_2^2$$

---

#### （3）SmoothQuant：激活离群值平滑迁移与跨算子静态融合

SmoothQuant（Xiao et al., ICML 2023，官方仓库 `mit-han-lab/smoothquant`）专为 **W8A8（权重与激活均采用 INT8 Tensor Core 运算）** 设计。既然激活 $X$ 有巨型离群值难量化、而权重 $W$ 分布平坦极易量化，SmoothQuant 通过对角矩阵 $S = \operatorname{diag}(s_1, \dots, s_K)$ 在激活与权重之间按比例 $\alpha \in [0, 1]$ 分摊最大动态范围（`smooth.py` 第 30–36 行）：

$$Y = X W^\top = \underbrace{\left(X \operatorname{diag}(\mathbf{s})^{-1}\right)}_{\hat{X} \text{（平滑后的激活）}} \underbrace{\left(W \operatorname{diag}(\mathbf{s})\right)^\top}_{\hat{W}^\top \text{（吸收离群值后的权重）}}, \quad s_j = \frac{\max\left(|X_{\cdot, j}|\right)^\alpha}{\max\left(|W_{\cdot, j}|\right)^{1 - \alpha}}$$

当取对称平衡点 $\alpha = 0.5$ 时，变换后的激活第 $j$ 通道极值与权重第 $j$ 列极值相等：

$$\max|\hat{X}_{\cdot, j}| = \frac{\max|X_{\cdot, j}|}{\max|X_{\cdot, j}|^{0.5} / \max|W_{\cdot, j}|^{0.5}} = \sqrt{\max|X_{\cdot, j}| \cdot \max|W_{\cdot, j}|} = \max|\hat{W}_{\cdot, j}|$$

```text
SmoothQuant / AWQ 跨算子零开销融合 (Zero-Overhead Operator Fusion) 拓扑流转:

[上游 RMSNorm / LayerNorm]                        [下游 Q / K / V 或 Gate / Up 投影层]
  原始输出: X = Norm(h) ⊙ γ + β                     原始权重: W
        │                                                 │
        ▼ (离线融合 γ' = γ / s, β' = β / s)               ▼ (离线融合 W' = W · diag(s), 再量化为 Q(W'))
  平滑输出: X_hat = X · diag(s)^{-1}  ───────────►  推理期直接执行 INT8 GEMM (W8A8) 或 W4A16 GEMM
  (运行时无任何额外逐元素除法算子!)                  Y ≈ dequant( Q(X_hat) @ Q(W')^T )
```

---

### 3. 工程权衡与生产落地陷阱

1. **为什么 W4A16（GPTQ/AWQ）在单并发 Decode 加速明显，但在长文本 Prefill 或大 Batch 下反而可能比 FP16 慢？**
   - 在 **W4A16** 中，由于激活仍是 FP16，GPU 底层无法调用 INT4 Tensor Core，只能在寄存器/共享内存（SRAM）中先将 INT4 权重**实时反量化（On-the-fly Dequantization）回 FP16**，再送入 FP16 Tensor Core 计算。
   - **Decode 阶段（小 Batch）**：算术强度极低（$\sim 1 \sim 16\text{ FLOPs/Byte}$），完全受限于 HBM 显存读取带宽（Memory-Bound）。W4A16 将从 HBM 读取的权重字节数砍掉约 $75\%$（含分组 Scale 后为 $4.125\text{ bits}$），省下的 HBM 传输时间远大于片上寄存器反量化指令开销，因此获得 $2.5\times \sim 3.5\times$ 真实加速。
   - **Prefill 阶段（或超大 Batch Decode）**：算术强度极高（Compute-Bound），瓶颈在于 Tensor Core 的 FP16 乘加吞吐。此时 W4A16 不仅没有减少半点 FP16 乘加计算量，反而额外塞入了大量位移、掩码与类型转换等反量化指令，导致吞吐低于原生 FP16 或 **W8A8（SmoothQuant / FP8）**——后者直接调用硬件级 8-bit Tensor Core，理论算力翻倍（$2\times$ TFLOPS）。
2. **GPTQ 的 `act_order`（`desc_act=True`）为什么是一把双刃剑？**
   - **精度收益**：默认按列顺序 $q=0, 1, \dots, K-1$ 量化时，排在最后的列只能被动承受前面所有列倾倒过来的累积误差。若开启 `act_order=True`（`gptq.py` 第 80–84 行：`perm = torch.argsort(torch.diag(H), descending=True)`），先量化 Hessian 对角元最大（即激活最显著）的列，并把它们的误差分摊给不太敏感的弱通道，可大幅提升 W3/W2 及复杂模型精度。
   - **推理吞吐代价**：一旦按激活大小打乱了列顺序，在 Group-wise（如 `group_size=128`）量化下，原本内存连续的 128 个通道在物理权重矩阵中变得支离破碎。GPU Kernel 在做矩阵乘法时必须通过 `g_idx` 索引表随机跳转读取不同分组的 Scale，或者对输入激活向量 $X$ 做全局重排（Permutation），破坏了内存合并访问（Coalesced Memory Access）。（注：生产引擎如 vLLM 的 **Marlin Kernel** 通过离线重排权重并在加载时对齐分组，才缓解了 `desc_act` 的部分惩罚，但若配合 `static_groups=True` 则无需在线重排激活）。
3. **哪些线性层无法做无开销的缩放融合（Scale Fusion）？**
   - 在 Transformer 的 `q_proj / k_proj / v_proj` 以及 MLP 的 `gate_proj / up_proj` 之前，紧挨着 `RMSNorm`，因此 $S^{-1}$ 可以直接除进 `RMSNorm.weight`（$\gamma \leftarrow \gamma / \mathbf{s}$）。
   - 在 `o_proj` 之前，可以将 $S^{-1}$ 吸收进上游 `v_proj` 的输出通道权重（`auto_scale.py` 第 51–68 行 `scale_fc_fc`；GQA 下需按头广播）。
   - 但在 SwiGLU MLP 的 `down_proj` 之前，输入为 $\operatorname{SiLU}(X W_{\text{gate}}) \odot (X W_{\text{up}})$。由于非线性激活函数 $\operatorname{SiLU}(z) = z \cdot \sigma(z)$ 不满足线性齐次性（$\operatorname{SiLU}(z / s) \neq \operatorname{SiLU}(z) / s$），不能把缩放系数直接塞进 `gate_proj`！工程上只能把 $S^{-1}$ 吸收进线性的 `up_proj` 输出通道，或者在激活函数后插入一个轻量级融合算子 `ScaledActivation`。

---

### 4. Python 3 标准库实现：GPTQ (Cholesky OBS)、AWQ 网格搜索与 SmoothQuant 仿真验证

下面的零依赖 Python 3 标准库代码完整复现并验证了：
1. **GPTQ**：显式证明逆 Hessian 的上三角 Cholesky 因子 $U$（满足 $H^{-1} = U^\top U$）与逐步条件子矩阵逆 $(H^{(q)})^{-1}$ 首行比值的数值等价性（误差 $< 10^{-15}$），并验证在强激活离群通道下 GPTQ 相比 RTN 将重构均方误差（MSE）降低 $95\%$ 以上；
2. **AWQ**：按 `mit-han-lab/llm-awq` 官方公式在 $\alpha \in [0, 1]$ 上执行 20 步网格搜索，自动定位最优保护指数 $\alpha^*$；
3. **SmoothQuant**：验证 $(X S^{-1})(W S)^\top = X W^\top$ 的浮点精确恒等性，以及将激活峰值削平后在低比特权重+激活联合量化下的精度恢复。

```python
import math
from typing import Dict, List, Tuple


def matmul(A: List[List[float]], B: List[List[float]]) -> List[List[float]]:
    """计算矩阵乘法 A [m, k] @ B [k, n] -> [m, n]"""
    m, k, n = len(A), len(B), len(B[0])
    return [[sum(A[i][p] * B[p][j] for p in range(k)) for j in range(n)] for i in range(m)]


def transpose(M: List[List[float]]) -> List[List[float]]:
    return [[M[r][c] for r in range(len(M))] for c in range(len(M[0]))]


def mse_matrix(Y_ref: List[List[float]], Y_hat: List[List[float]]) -> float:
    m, n = len(Y_ref), len(Y_ref[0])
    return sum((Y_ref[i][j] - Y_hat[i][j]) ** 2 for i in range(m) for j in range(n)) / (m * n)


def cholesky_lower(A: List[List[float]]) -> List[List[float]]:
    """对称正定矩阵 A 的下三角 Cholesky 分解: A = L @ L^T"""
    n = len(A)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                val = A[i][i] - s
                assert val > 0.0, "Matrix must be symmetric positive definite"
                L[i][j] = math.sqrt(val)
            else:
                L[i][j] = (A[i][j] - s) / L[j][j]
    return L


def invert_spd(A: List[List[float]]) -> List[List[float]]:
    """通过 Cholesky 分解求对称正定矩阵的逆矩阵 A^{-1}"""
    n = len(A)
    L = cholesky_lower(A)
    Linv = [[0.0] * n for _ in range(n)]
    for i in range(n):
        Linv[i][i] = 1.0 / L[i][i]
        for j in range(i + 1, n):
            Linv[j][i] = -sum(L[j][k] * Linv[k][i] for k in range(i, j)) / L[j][j]
    return matmul(transpose(Linv), Linv)


def sym_quant_dequant_vec(vec: List[float], n_bits: int, scale: float = 0.0) -> Tuple[List[float], float]:
    """对向量执行对称均匀量化与反量化"""
    q_max = (1 << (n_bits - 1)) - 1
    q_min = -(1 << (n_bits - 1))
    if scale <= 0.0:
        max_abs = max(abs(v) for v in vec)
        scale = max(max_abs / q_max, 1e-8)
    deq = [max(q_min, min(q_max, round(v / scale))) * scale for v in vec]
    return deq, scale


def gptq_quantize_layer(
    W: List[List[float]], X: List[List[float]], n_bits: int = 3, damp_ratio: float = 0.01
) -> Tuple[List[List[float]], List[List[float]], float]:
    """
    对比 W3A16 下 RTN 与 GPTQ (OBS 逐列误差补偿 + 上三角 Cholesky 因子等价验证):
    W: [N_out, K_in], X: [B_tokens, K_in], 输出 Y = X @ W^T
    """
    n_out, k_in = len(W), len(W[0])
    q_max = (1 << (n_bits - 1)) - 1

    # 1. 基线 RTN: 每行按初始最大绝对值计算固定 scale，独立舍入不补偿
    row_scales = [max(max(abs(v) for v in row) / q_max, 1e-8) for row in W]
    W_rtn = [sym_quant_dequant_vec(W[r], n_bits, scale=row_scales[r])[0] for r in range(n_out)]

    # 2. GPTQ: 计算 H = (2/B) X^T X + damp * I
    Xt = transpose(X)
    bsz = len(X)
    H = [[(2.0 / bsz) * sum(Xt[i][b] * X[b][j] for b in range(bsz)) for j in range(k_in)] for i in range(k_in)]
    mean_diag = sum(H[i][i] for i in range(k_in)) / k_in
    for i in range(k_in):
        H[i][i] += damp_ratio * mean_diag

    # 官方 IST-DASLab/gptq 实现: H^{-1} = U^T @ U (U 为下三角 Cholesky 因子的转置)
    H_inv = invert_spd(H)
    Hinv_U = transpose(cholesky_lower(H_inv))

    W_work = [row[:] for row in W]
    W_gptq = [[0.0] * k_in for _ in range(n_out)]
    max_cholesky_diff = 0.0

    for q in range(k_in):
        # 验证定理: Hinv_U[q, q:] / Hinv_U[q, q] 与剩余子矩阵逆 H_{q:,q:}^{-1} 首行除以其对角元完全相等
        H_sub_inv = invert_spd([row[q:] for row in H[q:]])
        d_q = Hinv_U[q][q]
        for offset in range(k_in - q):
            ratio_chol = Hinv_U[q][q + offset] / d_q
            ratio_exact = H_sub_inv[0][offset] / H_sub_inv[0][0]
            max_cholesky_diff = max(max_cholesky_diff, abs(ratio_chol - ratio_exact))

        for r in range(n_out):
            w_rq = W_work[r][q]
            q_rq = sym_quant_dequant_vec([w_rq], n_bits, scale=row_scales[r])[0][0]
            W_gptq[r][q] = q_rq
            err = (w_rq - q_rq) / d_q
            for j in range(q + 1, k_in):
                W_work[r][j] -= err * Hinv_U[q][j]

    return W_rtn, W_gptq, max_cholesky_diff


def awq_search_scale(
    W: List[List[float]], X: List[List[float]], n_bits: int = 3, n_grid: int = 20
) -> Dict[str, float]:
    """
    复现 mit-han-lab/llm-awq/awq/quantize/auto_scale.py:
    按 s_x = mean(|X|, axis=0) 搜索 s = s_x^alpha / sqrt(max*min) 最小化量化重构 MSE
    """
    n_out, k_in = len(W), len(W[0])
    bsz = len(X)
    Y_fp = matmul(X, transpose(W))
    s_x = [max(sum(abs(X[b][c]) for b in range(bsz)) / bsz, 1e-4) for c in range(k_in)]

    best_alpha = 0.0
    best_mse = float("inf")
    rtn_mse = 0.0

    for idx in range(n_grid + 1):
        alpha = idx / n_grid
        raw_s = [v ** alpha for v in s_x]
        norm_factor = math.sqrt(max(raw_s) * min(raw_s))
        scales = [v / norm_factor for v in raw_s]

        W_deq = []
        for r in range(n_out):
            scaled_row = [W[r][c] * scales[c] for c in range(k_in)]
            q_row, _ = sym_quant_dequant_vec(scaled_row, n_bits)
            W_deq.append([q_row[c] / scales[c] for c in range(k_in)])

        mse = mse_matrix(Y_fp, matmul(X, transpose(W_deq)))
        if idx == 0:
            rtn_mse = mse
        if mse < best_mse:
            best_mse = mse
            best_alpha = alpha

    return {"rtn_mse": rtn_mse, "best_alpha": best_alpha, "awq_mse": best_mse}


def smoothquant_wa_eval(
    W: List[List[float]], X: List[List[float]], alpha: float = 0.5, n_bits: int = 4
) -> Dict[str, float]:
    """
    复现 mit-han-lab/smoothquant/smoothquant/smooth.py:
    对比直接做 Weight+Activation 联合对称量化 vs 经 s_j = max(|X_j|)^alpha / max(|W_j|)^(1-alpha) 平滑迁移后量化
    """
    n_out, k_in = len(W), len(W[0])
    bsz = len(X)
    Y_fp = matmul(X, transpose(W))

    # 1. 未平滑直接对 X (per-token) 与 W (per-output-channel) 量化
    X_naive_q = [sym_quant_dequant_vec(row, n_bits)[0] for row in X]
    W_naive_q = [sym_quant_dequant_vec(row, n_bits)[0] for row in W]
    naive_mse = mse_matrix(Y_fp, matmul(X_naive_q, transpose(W_naive_q)))

    # 2. SmoothQuant 平滑因子计算与等价变换
    x_max = [max(abs(X[b][c]) for b in range(bsz)) for c in range(k_in)]
    w_max = [max(max(abs(W[r][c]) for r in range(n_out)), 1e-5) for c in range(k_in)]
    scales = [(x_max[c] ** alpha) / (w_max[c] ** (1.0 - alpha)) for c in range(k_in)]

    X_smooth = [[X[b][c] / scales[c] for c in range(k_in)] for b in range(bsz)]
    W_smooth = [[W[r][c] * scales[c] for c in range(k_in)] for r in range(n_out)]

    # 验证浮点精确等价性: (X * S^{-1}) @ (S * W)^T == X @ W^T
    fp_equiv_err = mse_matrix(Y_fp, matmul(X_smooth, transpose(W_smooth)))

    # 对平滑后的 X_smooth 与 W_smooth 执行相同位宽量化
    X_smooth_q = [sym_quant_dequant_vec(row, n_bits)[0] for row in X_smooth]
    W_smooth_q = [sym_quant_dequant_vec(row, n_bits)[0] for row in W_smooth]
    smooth_mse = mse_matrix(Y_fp, matmul(X_smooth_q, transpose(W_smooth_q)))

    return {
        "fp_equiv_err": fp_equiv_err,
        "naive_wa_mse": naive_mse,
        "smooth_wa_mse": smooth_mse,
        "x_max_before": max(x_max),
        "x_max_after": max(max(abs(v) for v in row) for row in X_smooth),
    }


# 构造带有强相关性输入通道与显著激活离群通道 (channel 0 幅值约 12.0，其余通道 < 1.0) 的校准集 X [8, 6] 与权重 W [4, 6]
X_calib = [
    [12.0, 0.8, -0.6, 0.9, 0.5, -0.7],
    [-11.5, -0.7, 0.5, -0.8, -0.6, 0.6],
    [10.8, 0.9, -0.4, 0.7, 0.4, -0.5],
    [-12.2, -0.6, 0.7, -0.9, -0.5, 0.8],
    [11.0, 0.75, -0.55, 0.85, 0.45, -0.65],
    [-10.5, -0.85, 0.45, -0.75, -0.55, 0.55],
    [11.8, 0.65, -0.65, 0.8, 0.6, -0.75],
    [-11.2, -0.7, 0.6, -0.85, -0.4, 0.7],
]
W_orig = [
    [0.18, 0.42, -0.38, 0.31, -0.27, 0.35],
    [-0.22, 0.36, 0.44, -0.29, 0.33, -0.41],
    [0.15, -0.48, 0.26, 0.39, -0.45, 0.28],
    [-0.19, -0.33, -0.41, 0.46, 0.29, -0.37],
]

Y_fp = matmul(X_calib, transpose(W_orig))
W_rtn, W_gptq, chol_diff = gptq_quantize_layer(W_orig, X_calib, n_bits=3)
mse_rtn = mse_matrix(Y_fp, matmul(X_calib, transpose(W_rtn)))
mse_gptq = mse_matrix(Y_fp, matmul(X_calib, transpose(W_gptq)))

awq_res = awq_search_scale(W_orig, X_calib, n_bits=3, n_grid=20)
sq_res = smoothquant_wa_eval(W_orig, X_calib, alpha=0.5, n_bits=4)

assert chol_diff < 1e-12
assert mse_gptq < mse_rtn * 0.1
assert awq_res["awq_mse"] < awq_res["rtn_mse"] * 0.1
assert sq_res["fp_equiv_err"] < 1e-24
assert sq_res["smooth_wa_mse"] < sq_res["naive_wa_mse"] * 0.2

print(f"1. GPTQ vs RTN (W3A16): RTN_MSE={mse_rtn:.6f} -> GPTQ_MSE={mse_gptq:.6f} (Cholesky diff={chol_diff:.2e})")
print(
    f"2. AWQ Grid Search (W3A16): RTN_MSE={awq_res['rtn_mse']:.6f} -> "
    f"AWQ_MSE={awq_res['awq_mse']:.6f} (best_alpha={awq_res['best_alpha']:.2f})"
)
print(
    f"3. SmoothQuant (W4A4 sim): X_max {sq_res['x_max_before']:.2f}->{sq_res['x_max_after']:.2f}, "
    f"Naive_MSE={sq_res['naive_wa_mse']:.6f} -> Smooth_MSE={sq_res['smooth_wa_mse']:.6f}"
)
print("All PTQ (GPTQ, AWQ, SmoothQuant) mathematical and numerical assertions passed!")
```

实际运行输出：

```text
1. GPTQ vs RTN (W3A16): RTN_MSE=0.285799 -> GPTQ_MSE=0.012050 (Cholesky diff=4.44e-16)
2. AWQ Grid Search (W3A16): RTN_MSE=0.285799 -> AWQ_MSE=0.000842 (best_alpha=0.55)
3. SmoothQuant (W4A4 sim): X_max 12.20->1.64, Naive_MSE=0.476754 -> Smooth_MSE=0.009075
All PTQ (GPTQ, AWQ, SmoothQuant) mathematical and numerical assertions passed!
```

---

## 延伸 / 追问

**追问 1：为什么 SmoothQuant 能够胜任 W8A8，但当目标进一步下探到 W4A4（4-bit 权重 + 4-bit 激活）时却会失效？QuaRot 与 SpinQuant 是如何用正交旋转（Hadamard / Stiefel 流形旋转）解决 W4A4 的？**
SmoothQuant 只是通过**对角缩放矩阵 $S$** 把激活通道的极端幅值“转移”给了权重的对应行。在 W8A8 下，8-bit 有 255 个离散台阶，权重吸收 $\sqrt{100} = 10\times$ 的离群放大后仍能靠 Per-Channel INT8 轻松容纳；但在 **W4A4** 下，4-bit 仅有 15 个非零对称台阶（$[-7, 7]$），无论把 $100\times$ 的离群尖峰留在激活侧还是挪到权重侧，总有一方（或双方）会因仅有的 15 个刻度被撑爆而严重失真。
为此，**QuaRot（Ashkboos et al., NeurIPS 2024）**与 **SpinQuant（Liu et al., ICLR 2025）**引入了满足 $R^\top R = I$ 的**稠密正交旋转矩阵**（如快速 Walsh-Hadamard 变换矩阵 $H_K \in \{+\frac{1}{\sqrt{K}}, -\frac{1}{\sqrt{K}}\}^{K \times K}$）：

$$Y = X W^\top = (X R) (W R)^\top$$

与对角矩阵只在原地缩放单个通道不同，Hadamard 正交旋转将单个通道上的极端离群能量**均匀打散（Spread out）到全部 $K$ 个通道的线性组合上**，使旋转后的激活 $XR$ 和权重 $WR$ 均趋近于平滑的高斯分布（消除了任何单一维度的尖峰），从而使 W4A4 甚至 KV Cache INT4 量化成为可能（代价是推理时部分位置需额外执行 $O(K \log K)$ 的在线 Fast Hadamard Transform）。

**追问 2：KV Cache 的量化（如 KIVI、KVQuant）中，Key Cache 和 Value Cache 的离群值分布有什么本质差异？应该分别按哪个维度量化？**
实验（Liu et al., *KIVI*, ICML 2024）表明：在注意力层中，**Key Cache 的离群值严格沿 Channel（即 `head_dim` 维）固定出现**（与线性层输入激活类似，少数几个维度在所有 Token 上幅值极大），而 **Value Cache 没有明显的固定 Channel 离群值，其幅值波动主要沿 Token 方向变化**。
因此，2-bit / 4-bit KV Cache 量化的黄金准则是：**Key Cache 必须采用 Per-Channel（沿 Token 维度分组，同一 Channel 共享 Scale）量化，而 Value Cache 必须采用 Per-Token（同一 Token 的各维共享 Scale）量化**。由于自回归生成每次只新增 1 个 Token，Per-Token 的 Value 可以立即量化落盘；而 Per-Channel 的 Key 需要凑够一个分组窗口（如 32 或 64 个 Token）才能沿时间维做完分组量化，故工程上常保留最近 $R=32 \sim 128$ 个残差 Token 的 Key 为 FP16 滑动窗口。

**追问 3：在 Hopper（H100/H800）和 Blackwell（B200）架构上，原生 FP8（E4M3）与 SmoothQuant INT8（W8A8）相比有什么优势？什么场景下仍然需要 SmoothQuant？**
FP8（特别是 1 位符号、4 位指数、3 位尾数的 `E4M3` 格式，动态范围达 $\pm 448$）采用**非线性（对数级）刻度**：小数值附近刻度极密、大数值附近刻度自动变宽，天然对温和的激活离群值具有比均匀线性 INT8 更高的信噪比（SNR），因此在许多模型上仅需简单的 Per-Tensor 或 Per-Token 动态缩放即可直接跑 FP8 Tensor Core，无需复杂的离线平滑校准。
然而，（1）在不支持原生 FP8 Tensor Core 的存量主力卡（如 NVIDIA A100、RTX 3090、昇腾 910B 等）上，硬件只有 INT8 Tensor Core，SmoothQuant W8A8 仍是唯一能跑满 8-bit 算力的方案；（2）对于存在极端离群通道（幅值 $> 100$）的模型或在激进的 Per-Tensor 静态 FP8 量化下，结合 SmoothQuant 预平滑依然能显著减少 E4M3 尾数下溢（Underflow）与上溢裁剪损失。

---

## 常见误区

- **误区一：“AWQ 在识别 $1\%$ 显著权重时，是把这些权重的数值保留为 FP16、其余 $99\%$ 存为 INT4 的混合精度格式。”**
  事实：如果在同一矩阵内混存 1% 的随机列为 FP16、99% 为 INT4，GPU 的内存对齐和 SIMD 向量化访存会彻底碎片化（这也是早期 `LLM.int8()` 在推理延迟上常常变慢的原因）。AWQ **只在最初的动力学科研对照实验中用混合精度证明了显著通道的重要性**，而在实际算法与部署格式中，**AWQ 100% 的权重全部被量化为统一的 INT4**——它只是在量化前将显著通道乘上 $s_j > 1$ 放大（减少其在组内的相对舍入误差），并将 $s_j^{-1}$ 融合进上游算子，从而保持了完全规整的 INT4 内存布局。
- **误区二：“GPTQ 在逐列量化并更新未量化权重时，由于依赖校准集输入 $X$，属于需要反向传播（Backpropagation）和梯度下降的 QAT 微调。”**
  事实：GPTQ 完全不需要任何反向传播或梯度下降迭代！单层线性重构目标 $\min \|XW^\top - X\hat{W}^\top\|_F^2$ 是一个二次型凸函数，其局部二阶导数 $H = \frac{2}{M}X^\top X$ 只依赖校准集在该层的**前向输入激活 $X$**，闭式解通过一次 Cholesky 分解即可一步算完。
- **误区三：“把模型从 FP16 量化成 GPTQ/AWQ 的 W4A16（INT4）后，不仅显存降为约 $1/4$，而且无论是长 Prompt 预填充（Prefill）还是解码（Decode）速度都会快 3~4 倍。”**
  事实：W4A16 仅压缩了**权重的存储与 HBM 传输体积**，计算时仍需反量化回 FP16 喂给 FP16 Tensor Core。因此它只能在受限于显存带宽的**小 Batch Decode 阶段**带来 $2.5\times \sim 3.5\times$ 提速；而在受限于算力的 **长序列 Prefill 或大 Batch 阶段**，由于没有激活低比特 Tensor Core 且多了反量化开销，W4A16 的吞吐通常与 FP16 持平甚至略慢（要加速 Prefill 必须使用 W8A8 / FP8 / W4A4 等激活也参与低位宽矩阵乘的方案）。

---

## 参考

- 选题线索：[wanshuiyin/Auto-claude-code-research-in-sleep, docs/tutorials/quantization_tutorial.md](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/edc49254f949c6122879b3f1c42d54886091762d/docs/tutorials/quantization_tutorial.md)（固定 commit `edc4925`），独立重构拓展。
- Frantar et al., [GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers](https://arxiv.org/abs/2210.17323)，ICLR 2023，及官方源码 [IST-DASLab/gptq (`gptq.py`)](https://github.com/IST-DASLab/gptq/blob/2d65066eeb06a5c9ff5184d8cebdf33662c67faf/gptq.py)（固定 commit `2d65066`）：OBS 二阶误差补偿公式、逆 Hessian 上三角 Cholesky 分解与 `actorder` 实现。
- Lin et al., [AWQ: Activation-aware Weight Quantization for LLM Compression and Acceleration](https://arxiv.org/abs/2306.00978)，MLSys 2024 Best Paper，及官方源码 [mit-han-lab/llm-awq (`awq/quantize/auto_scale.py`)](https://github.com/mit-han-lab/llm-awq/blob/d6e797a42b9ef7778de8ee2352116e0f48a78d61/awq/quantize/auto_scale.py)（固定 commit `d6e797a`）：显著通道激活感知缩放、网格搜索与跨层算子融合。
- Xiao et al., [SmoothQuant: Accurate and Efficient Post-Training Quantization for Large Language Models](https://arxiv.org/abs/2211.10438)，ICML 2023，及官方源码 [mit-han-lab/smoothquant (`smoothquant/smooth.py`)](https://github.com/mit-han-lab/smoothquant/blob/c61476d728e42ae0d8a35e7e78494edcac3237b5/smoothquant/smooth.py)（固定 commit `c61476d`）：激活-权重离群值平滑迁移因子 $\alpha$ 与 W8A8 融合。
- Dettmers et al., [LLM.int8(): 8-bit Matrix Multiplication for Transformers at Scale](https://arxiv.org/abs/2208.07339)，NeurIPS 2022：$6.7\text{B}$ 规模涌现的系统性激活离群值特征分析。

来源访问与示例核验日期：**2026-11-07**。仅执行标准库下 Cholesky 逆 Hessian 等价性、GPTQ 逐列补偿、AWQ 网格搜索及 SmoothQuant 数值仿真验证，未运行百亿参数 GPU 实机校准。
