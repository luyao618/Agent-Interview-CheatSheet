---
id: llm-0048
title: 超低比特微缩放浮点（FP8、MXFP4 与 NVFP4）是如何通过分块缩放、高精累加、二维权重一致性、随机 Hadamard 旋转与随机舍入打通大模型训练与推理的？
category: llm
tags: [fp8, nvfp4, mxfp4, microscaling, pretraining, tensor-core]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开 AI 系统面试指南与 CUDA 内核教材（ombharatiya/ai-system-design-guide 与 xlite-dev/LeetCUDA）扩展改编；DeepSeek-V3、NVIDIA NVFP4 Pretraining 论文及 DeepGEMM 官方源码核实（见参考）
status: published
updated: 2026-11-28
answers:
  - author: gemini-4-carbon
    type: ai
    model: gemini-4-carbon
    answered: 2026-11-28
    updated: 2026-11-28
---

## 问题

随着前沿大模型预训练迈入数十万亿 Token 与百亿亿次浮点运算规模，数据中心训练与在线推理精度正全面从 **BF16** 迁移至硬件原生 **FP8** 乃至 **4-bit 微缩放浮点（MXFP4 与 NVFP4）**。然而，单纯把浮点位宽砍半绝非“免费获得 $2\times \sim 4\times$ 吞吐加速”：在 Hopper 架构上直接做张量级 FP8 矩阵乘会遭遇激活离群值溢出与 Tensor Core 低位宽累加漂移；进一步下探到仅有 $1+2+1$ 位的 FP4（E2M1）时，朴素分块训练更会在早期直接发散；而在推理侧，盲目把线上服务从 BF16/FP8 切到 FP4 甚至可能因内核路径失配导致吞吐倒退。请深入剖析以下三个核心问题：

1. **细粒度 FP8 训练范式（DeepSeek-V3 / DeepGEMM）**：为什么传统张量级（Per-Tensor）延迟缩放与 `E4M3 + E5M2` 混合格式难以驯服百亿级 MoE 模型的特征离群值？DeepSeek-V3 是如何通过 **$1 \times 128$ 激活 Tile 与 $128 \times 128$ 权重 Block 在线缩放**实现全算子统一 `E4M3` 的？为什么 Hopper GPU 上的 FP8 WGMMA 必须每隔 $N_C = 128$ 个元素提升至 CUDA Core 做 FP32 累加，且激活梯度（Dgrad）绝对不能像权重那样采用二维 $128 \times 128$ 块量化？
2. **微缩放 FP4 格式对决（OCP MXFP4 vs NVIDIA NVFP4）**：在同为 `E2M1`（仅 $\pm\{0, 0.5, 1, 1.5, 2, 3, 4, 6\}$ 八档幅值）的数据位下，MXFP4（32 元素块 + `UE8M0` 2 的整数次幂缩放）为什么会在块最大值落入 $3 + \delta$ 等边界时白白浪费 $\pm 4, \pm 6$ 码点并损失近 1 个倍频程（Binade）的动态范围？NVFP4 是如何通过**两级微缩放（全局 FP32 量程对齐常数 $6 \times 448 = 2688$ + 每 16 元素 `UE4M3` 块缩放）**实现硬件 Block-Scaled MMA 零寄存器算术开销与更高有效精度的？
3. **万亿 Token 级 NVFP4 预训练四大支柱与生产推理选型边界**：在万亿 Token 预训练中，为什么前向与反向转置会导致一维块缩放破坏链式法则（$W_{\text{fprop}} \neq W_{\text{bprop}}$）？**$16 \times 16$ 二维权重块缩放、仅作用于 Wgrad 的随机 Hadamard 变换（RHT）、仅作用于梯度的随机舍入（Stochastic Rounding）以及敏感尾部层高精保留**各自解决了什么数值失效机制？线上推理从 FP8 迁移至 NVFP4/MXFP4 时应如何核查硬件、算子内核路径（如 Marlin vs CuTeDSL）与 KV Cache 配比？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-carbon

> 🤖 AI 答案 · 模型：gemini-4-carbon · 回答 2026-11-28

**从 BF16 演进到 FP8 与微缩放 FP4（MXFP4 / NVFP4），核心本质是用“硬件原生消费的分块共享缩放因子 + 正交旋转/无偏舍入算法契约”弥补超窄尾数与指数位宽的信息熵坍缩：（1）在 FP8 训练层，DeepSeek-V3 摒弃滞后的全局张量级延迟缩放，对激活按 $1 \times 128$ Tile、对权重按 $128 \times 128$ Block 在线计算缩放因子，以组内共享指数换取全链路统一采用高精度 3 位尾数的 `E4M3`，同时每隔 $N_C = 128$ 个内积元素（4 次 WGMMA）将 Hopper Tensor Core 仅约 14 位有效精度的局部累加器搬回 CUDA Core FP32 寄存器做大数吃小数纠偏与块缩放反量化，并对跨 Token 极度不均衡的激活梯度坚持一维 Tile 量化以防发散；（2）在 4-bit 编码层，OCP MXFP4 受限于 `UE8M0` 纯 2 的幂次缩放向上取整防饱和，最坏情形下块内峰值截断在 $3.0$、丢弃整整 1 个 Binade 动态范围（实验需多训约 $36\%$ Token 才能追平同等损失），而 NVFP4 借全局 FP32 缩放因子 $s_{\text{enc}} = 2688 / \text{amax}_x$ 将各 16 元素子块最大值精准映射入 `UE4M3` 尾数网格，使每块峰值元素（占 $6.25\%$）逼近 FP8 精度且平均仅占 $4.5\text{ bit/elem}$；（3）在万亿 Token FP4 训练与在线推理层，必须联用 $16 \times 16$ 二维权重缩放消除前反向转置引发的链式法则失配（$W_{\text{fprop}} = W_{\text{bprop}}$）、对 Wgrad 两侧施加 $16 \times 16$ 随机符号 Hadamard 正交旋转摊平单点离群值、仅对梯度开启随机舍入消除亚格点下溢死锁（激活/权重坚持最近偶数舍入防噪声放大）并保留约 $15\%$ 末层高精算子；而线上推理切换 `FP4 权重 + FP8 KV Cache` 前，必须实测具体 Batch/序列长度下的内核路径（如 CuTeDSL vs Marlin）而非盲信标称峰值算力。**

在展开位域编码与训练/推理内核推导之前，建议结合题库内已有题目串联完整知识网：关于训练后整数权重量化（GPTQ Hessian 补偿、AWQ 显著通道缩放与 SmoothQuant）的原理，请参阅 [llm-0035](llm-0035-ptq-gptq-awq-smoothquant.md)；关于量化模型静态显存核算与 MoE 总参数/激活参数边界，请参阅 [llm-0016](llm-0016-quantization-local-memory-budget.md)；关于 KV Cache 专用非对称低比特压缩（KIVI / KVQuant），请参阅 [llm-0038](llm-0038-kv-cache-quantization-kivi-kvquant.md)；关于 DeepSeek 架构中与 FP8/FP4 内核深度协同的 MLA 压缩注意力、Engram/mHC 拓扑及前缀缓存调度，请参阅 [llm-0034](llm-0034-mla-multi-head-latent-attention-rope-absorption.md)、[llm-0046](llm-0046-engram-conditional-memory-mhc.md) 与 [llm-0047](llm-0047-chunked-prefill-prefix-caching-radix-attention.md)。

---

### 1. 细粒度 FP8 混合精度训练：分组共享指数与 $N_C=128$ 跨核提升累加

#### 1.1 为什么“全 `E4M3` + 细粒度在线分块”优于传统“Per-Tensor 延迟缩放 + 混合格式”？

标准 IEEE/OCP 8-bit 浮点分为 **`E4M3`**（1 符号 + 4 指数 + 3 尾数，最大正规数 $448$，组内相邻码点相对步长 $2^{-3} = 12.5\%$ 至 $6.25\%$）与 **`E5M2`**（1 符号 + 5 指数 + 2 尾数，最大正规数 $57344$，相对步长劣化至 $25\%$）。早期框架（如初代 Transformer Engine Per-Tensor 方案）使用整张量单一缩放因子，并被迫在前向（Fprop）用 `E4M3`、反向（Dgrad/Wgrad）用 `E5M2` 以容纳梯度大动态范围，且依赖前若干步的历史峰值做**延迟缩放（Delayed Scaling）**。这在大规模 MoE 训练中有两大隐患：
1. **单点离群值绑架整张量尾数**：只要张量内某一个 Token 的某个激活通道出现尖峰（如幅值达正常值的 $100\times$），全局缩放因子就会把其余 $99.9\%$ 的正常元素集体压向零点附近，触发灾难性下溢；若突发尖峰超出历史窗口预测，更会直接引发上溢 NaN。
2. **细粒度在线分块（Tile & Block-Wise Online Quantization）**：DeepSeek-V3（`arXiv:2412.19437` §3.3.2）将缩放粒度沿矩阵乘内积轴 $K$ 切细——**激活张量按 $1 \times 128$ Tile（单 Token 每 128 个通道）在线求 `amax`，权重张量按 $128 \times 128$ Block（每 128 输入通道 $\times$ 128 输出通道）在线求 `amax`**。由于局部子块内的数值跨度大幅收窄，元素间等效共享了块缩放因子的指数位，从而允许 **Fprop、Dgrad、Wgrad 三大 GEMM 全部统一采用 3 位尾数的 `E4M3`（Mantissa over Exponents）**，彻底省去延迟历史状态维护。

#### 1.2 Hopper Tensor Core 14-bit 累加器缺陷与双 Warpgroup 流水掩盖

细粒度分块要求沿 GEMM 内积维度 $K$ 每隔 $128$ 个元素乘一次组缩放因子，而标准 Hopper H800/H100 FP8 Tensor Core 指令（`wgmma.mma_async`）原生只支持矩阵外围缩放；更致命的是，实测表明 **Hopper FP8 WGMMA 硬件内部累加器仅保留约 $14\text{ bit}$（1 位隐式整数位 + 13 位小数尾数）有效尾数精度**，远低于标准 FP32 的 24 位有效尾数！当模型隐藏层宽度或微批序列拉长（如 $K = 4096$）时，一旦前序局部和累积到较大基准值（如 $10.0$），后续数千个量级为 $4 \times 10^{-4}$ 的同号微小乘积在 `14-bit` 尾数对齐时会被直接截断归零（Swamping，大数吃小数），在随机矩阵测试中即可造成近 **$2\%$** 的最大相对误差。

DeepSeek-V3 与 `DeepGEMM` 通过 **CUDA Core 周期性高精度提升（Promotion to CUDA Cores）** 一箭双雕地同时解决了累加精度与内积轴块缩放：
$$\text{Acc}_{\text{FP32}} \leftarrow \text{Acc}_{\text{FP32}} + s^A_{m, g} \cdot s^B_{n, g} \cdot \underbrace{\sum_{k = g N_C}^{(g+1)N_C - 1} \tilde{A}_{m, k} \tilde{B}_{n, k}}_{\text{Tensor Core 4 次 WGMMA 局部累加 } (N_C = 128)}$$
每隔 $N_C = 128$ 个内积元素（恰好对应 $4$ 条 `wgmma` 指令与 $1 \times 128$ Tile 边界），就将 Tensor Core 局部累加结果拷贝到 CUDA Core 的完整 FP32 寄存器中乘上当前分块的缩放因子积 $s^A_{m,g} s^B_{n,g}$ 并累加；硬件调度上利用 H800 **两个并发驻留 Warpgroup 乒乓重叠**（一个 Warpgroup 在 CUDA Core 做 FP32 提升乘加，另一个 Warpgroup 满速发射下一组 WGMMA），在几乎不损失 Tensor Core 利用率（实测可达 $1550\text{ TFLOPS}$）的前提下消除了低位累加漂移。

#### 1.3 为什么激活梯度（Dgrad）严禁模仿权重使用 $128 \times 128$ 二维块量化？

训练时前向计算 $Y = X W^\top$ 沿通道维归约，反向计算权重梯度 $\nabla W = (\nabla Y)^\top X$ 却需要沿 **Token 维度** 归约，导致缓存的激活与激活梯度必须经历从 $1 \times 128$ 到 $128 \times 1$ 的跨维度重分组（DeepSeek-V3 对注意力输出投影前的敏感激活特制了 `E5M6` + 2 的整数次幂圆整缩放因子以实现转置无损保真）。看似省事的做法是把激活梯度也改成与权重相同的 $128 \times 128$ 二维块量化（转置即零开销复用）；但 DeepSeek-V3 附录 B.2 在 16B MoE 模型（300B Token）上的消融实验证实：**对 Dgrad 采用 $128 \times 128$ 二维块量化会直接引发模型训练发散！** 根本原因在于反向激活梯度在不同 Token 之间极度失衡（如个别特殊分隔符、推理转折词或高损失 Token 带有强烈的 **Token-Correlated Outliers**）；一旦跨 128 个连续 Token 共享同一个二维缩放因子，高梯度异常 Token 会瞬间抹平同块其余 127 个正常 Token 回传给浅层的梯度信号，经数十层残差链式反传放大后必然崩溃。

---

### 2. 微缩放 4-bit 浮点对决：OCP MXFP4 vs NVIDIA NVFP4

当数据位宽从 8-bit 进一步腰斩至 4-bit **`E2M1`**（1 符号位、2 指数位、1 尾数位，指数偏置 $b=1$，无 Inf/NaN）时，其非负可表示码表仅剩稀疏的 **8 个离散幅值点**：
$$\mathcal{G}_{\text{E2M1}}^{+} = \{0,\; 0.5,\; 1.0,\; 1.5,\; 2.0,\; 3.0,\; 4.0,\; 6.0\}$$
每个 2 的幂区间（Binade）内仅塞得下 **2 个码点**，区间下沿相对步长高达 **$50\%$**（上沿 $25\%$）。在 Blackwell / Rubin 与 AMD MI350+ 硬件生态中，围绕如何给 `E2M1` 配置块缩放因子形成了两大主流标准：

| 核心维度 | OCP MXFP4（Open Compute Project 标准） | NVIDIA NVFP4（两级微缩放格式） |
| :--- | :--- | :--- |
| **元素编码与满量程** | `E2M1`（幅值集合 $\{0 \dots 6.0\}$） | `E2M1`（幅值集合 $\{0 \dots 6.0\}$） |
| **共享块大小（Block Size）** | **32 个连续元素**（$1 \times 32$） | **16 个连续元素**（$1 \times 16$，训练权重可用 $16 \times 16$） |
| **局部块缩放格式（Level-2）** | 无符号 **`UE8M0`**（8 位纯指数，仅能表达 $2^k, k \in [-127, 127]$） | 无符号 **`UE4M3`**（4 指数 + 3 尾数，最大 $448$，最小次正规 $2^{-9}$） |
| **全局张量缩放（Level-1）** | 无（`UE8M0` 自身动态范围已覆盖 FP32 量级） | **FP32 全局/行/列缩放** $s_{\text{enc}} = \frac{6 \times 448}{\text{amax}_x} = \frac{2688}{\text{amax}_x}$ |
| **等效平均位宽（含元数据）** | $4 + 8 / 32 = \mathbf{4.25\text{ bits/elem}}$ | $4 + 8 / 16 (+ 32/N) \approx \mathbf{4.50\text{ bits/elem}}$ |
| **块最大值映射与码表利用率** | 向上圆整至 $2^k$ 防溢出，最坏丢失 $\pm 4, \pm 6$ 两档与 **1 个 Binade** | 峰值精准锚定至 $\approx 6.0$，每块至少 **$6.25\%$ 元素（1/16）达近 FP8 精度** |
| **原生硬件支持代表** | NVIDIA Blackwell (`SM100`+, 含 `UE8M0` 打包)、AMD MI350 / MI455X | NVIDIA Blackwell (`SM100`/`SM120`), Vera Rubin |

#### 2.1 MXFP4 的“倍频程浪费陷阱（Binade Waste）”定量推导

MXFP4 将块缩放因子限制为纯 2 的整数次幂 `UE8M0`。由于低精度训练中一旦发生饱和截断（Saturation）极易导致梯度爆炸发散，工程规范要求将理想解码缩放因子 $s_{\text{raw}} = \text{amax}_b / 6$ **向上取整（Round Up）** 到最近的 2 的幂：$s_{\text{ue8m0}} = 2^{\lceil \log_2(\text{amax}_b / 6) \rceil}$。
考虑一个极具代表性的边界子块，其最大绝对值略微跨过阈值：$\text{amax}_b = 3 + \delta$（$\delta > 0$ 极小）：
1. 理想缩放因子 $s_{\text{raw}} = (3 + \delta) / 6 = 0.5 + \delta / 6 > 2^{-1}$，被迫向上圆整一整档至 $s_{\text{ue8m0}} = 2^0 = 1.0$；
2. 块内所有元素除以 $1.0$ 后，最大元素 $3 + \delta$ 在 `E2M1` 码表上四舍五入落到 **$3.0$**（因为距离 $3.0$ 远近于 $4.0$）；
3. **灾难性后果**：整块 32 个元素没有任何一个能触及 $\pm 4.0$ 与 $\pm 6.0$ 这四个最外层码点！实际利用的有效动态范围从满格 $\log_2(6 / 0.5) = 3.58\text{ binades}$ 暴跌至 $\log_2(3 / 0.5) = 2.58\text{ binades}$，白白损失整整 **1 个倍频程**。NVIDIA 在 8B Mamba-Transformer 1T Token 对比实验（`arXiv:2509.25149` §5 Fig.6）中实测：MXFP4 相对 BF16 的训练损失误差约为 $2.5\%$（NVFP4 仅为 $1.5\%$），**MXFP4 必须额外多训练 $36\%$ 的数据（$1.36\text{T}$ vs $1.0\text{T}$ Token）才能追平 NVFP4 的最终验证集困惑度！**

#### 2.2 NVFP4 的两级折叠恒等式与硬件零算术开销

为什么 NVFP4 不能直接去掉全局 FP32 缩放、只留每 16 元素的 `UE4M3`？如 `LeetCUDA` 第 36 章与论文附录 B 所证，单级 `UE4M3` 面临**下溢归零**（最小正数 $2^{-9} \approx 0.001953$，一旦某组 $\text{amax}_b < 6 \times 2^{-10} \approx 0.00586$，缩放因子舍入为 $0$ 会把整组 16 个元素彻底抹零）与**量程浪费**（最大仅 $448$）。因此 NVFP4 设计了严密的两级编码流水线：
1. **Level-1 全局量程对齐**：统计张量峰值 $\text{amax}_x = \max_i |x_i|$，令全局编码缩放 $s_{\text{enc}} = \frac{6 \times 448}{\text{amax}_x} = \frac{2688}{\text{amax}_x}$，解码缩放 $s_{\text{dec}} = 1 / s_{\text{enc}}$（存 FP32），把最大子块的局部缩放精准推到 `UE4M3` 满量程 $448$；
2. **Level-2 局部高精度锚定与倒数重标定**：对每个 16 元素子块 $b$，将局部解码缩放量化为 `UE4M3`：$s_{\text{dec}, b, \text{e4m3}} = \text{e4m3}\!\left(\frac{\text{amax}_b}{6} \cdot s_{\text{enc}}\right)$；随后在 FP32 下**以量化后的真实解码值反求局部编码缩放** $s_{\text{enc}, b} = \frac{1}{\text{fp32}(s_{\text{dec}, b, \text{e4m3}}) \cdot s_{\text{dec}}}$，保证自洽恒等式 $s_{\text{enc}, b} \cdot s_{\text{dec}} \cdot s_{\text{dec}, b, \text{e4m3}} \approx 1$ 成立，最后将元素量化为 $\tilde{x}_i = q_{\text{e2m1}}(x_i \cdot s_{\text{enc}, b})$；
3. **Blackwell Block-Scaled MMA 折叠**：矩阵乘 $C_{m,n} = s_{\text{dec}}^A s_{\text{dec}}^B \sum_{b} s_{\text{dec}, b, \text{e4m3}}^A s_{\text{dec}, b, \text{e4m3}}^B \sum_{k \in b} \tilde{A}_{m,k} \tilde{B}_{n,k}$ 中，内层 `UE4M3` 局部缩放由 Tensor Core `block_scale` 硬件通路在 16 元素点积出口直接消费，**不占用任何 CUDA Core 寄存器算术指令**，外层标量 $s_{\text{dec}}^A s_{\text{dec}}^B$ 则在 Epilogue 一次性乘回（单侧正态输入理论与实测相对均方根误差约为 $10.2\%$，双侧 GEMM 为 $\sqrt{2} \times 10.2\% \approx 14.4\%$）。
---

### 3. 万亿 Token 级 NVFP4 预训练四大支柱与生产推理选型边界

NVIDIA 在 12B Mamba-Transformer 模型上完成史无前例的 **10 万亿（10T）Token NVFP4 预训练**（MMLU-Pro 达 $62.58\%$，紧贴 FP8 基线的 $62.62\%$），证明若只用朴素 $1 \times 16$ 最近偶数舍入，模型在训练早期就会彻底发散。必须协同部署以下四项数值工程支柱：

1. **支柱一：$16 \times 16$ 二维权重块缩放修复链式法则（Chain-Rule Consistency）**：
   线性层的三个 GEMM 中，前向 $Y = X W^\top$ 沿权重的行（输入通道 $C_{\text{in}}$）做内积，反向激活梯度 $\nabla X = \nabla Y \cdot W$ 却对权重做了**转置**，改为沿列（输出通道 $C_{\text{out}}$）做内积！如果对权重采用标准 $1 \times 16$ 一维块缩放，同一个离群权重在行方向与列方向会拉高完全不同的 15 个邻居元素的缩放因子，导致前向生效权重 $W_{\text{fprop}}$ 与反向生效权重 $W_{\text{bprop}}$ **不再是同一个矩阵（$W_{\text{fprop}} \neq W_{\text{bprop}}$）**，反向传播求出的梯度不再对应前向真实计算的函数！将权重量化改为 **$16 \times 16$ 二维对称块共享同一个 `UE4M3` 缩放因子**（送入 Tensor Core 时将该因子复制给块内 16 条 $1 \times 16$ 行/列切片），即可严格保证转置前后表示恒等（$\|W_{\text{fprop}} - W_{\text{bprop}}\|_F \equiv 0$）；而激活与梯度仍保留更精细的 $1 \times 16$ 一维块缩放。
2. **支柱二：仅作用于 Wgrad 输入的 $16 \times 16$ 随机 Hadamard 变换（RHT）**：
   当单个 Token 出现剧烈激活尖峰（如 $x_0 = 24.0$，同组其余 15 个正常值为 $\pm 0.8$）时，局部缩放因子 $s_{\text{dec}, b} = 4.0$ 会将所有 $|x_i| < 1.0$ 的同组元素全部量化归零，抹杀有效梯度内积。利用正交归一化随机符号 Hadamard 矩阵 $H = S_d H_d$（其中 $H_d = \frac{1}{\sqrt{2}} H_2 \otimes H_{d/2}$，$S_d = \text{diag}(\pm 1)$ 防结构化基对齐，取 $d = 16$ 平衡高斯化效果与访存开销），同时旋转 Wgrad 的两个输入张量：
   $$\nabla W = (\nabla Y^\top H)(H^\top X) = \nabla Y^\top (H H^\top) X = \nabla Y^\top X$$
   旋转将尖峰能量均匀摊平到 16 个坐标（幅值由 $24.0$ 降至 $\approx 6.0$），拯救被抹零的邻近信号！**注意边界**：RHT 绝不能施加于权重（否则再次破坏前反向转置一致性），消融实验也证实将其加到 Fprop 或 Dgrad 反而会因引入额外重分布量化噪声而劣化验证损失，故**严格限定仅用于 Wgrad 两侧输入**。
3. **支柱三：非对称舍入策略——仅对梯度开启随机舍入（Stochastic Rounding, SR）**：
   在稀疏的 `E2M1` 格点（最小非零步长 $0.5$）上，确定性最近偶数舍入（RTNE）会将所有缩放后幅值落在 $(0, 0.25)$ 内的梯度恒定截断为 $0$（造成参数更新死锁与系统性方向偏置）。**随机舍入**以距离反比概率跳变：对 $v \in [g_{\text{lo}}, g_{\text{hi}}]$，以 $p = \frac{v - g_{\text{lo}}}{g_{\text{hi}} - g_{\text{lo}}}$ 取 $g_{\text{hi}}$、以 $1-p$ 取 $g_{\text{lo}}$，数学期望严格无偏 $\mathbb{E}[q_{\text{SR}}(v)] = v$。但随机舍入的方差严格大于 RTNE——消融实验（`arXiv:2509.25149` Appendix E.3）表明：**若对前向激活或权重开启随机舍入，放大的前向方差会直接导致训练发散！** 因此铁律是“**梯度用 SR 保无偏，权重与激活坚持用 RTNE 控方差**”。
4. **支柱四：尾部敏感层高精保留、末期精度回切与线上推理四大核查清单**：
   - **训练层敏感度**：网络最后若干个 Block 的线性层对 Wgrad 量化噪声极度敏感，全网强上 FP4 必发散；保留约 $<15\%$ 线性层（主要是末尾 4~8 个 Block，外加 Embedding、LM Head、Norm、MoE 路由门控、Attention Softmax/BMM 与 FP32 Master Weights）在 BF16/FP8 即可稳健收敛；且在学习率衰减开启前（如最后 $\sim 18\%$ Token）切换回高精可进一步弥合残余损失间隙。
   - **生产推理选型铁律（FP8 $\to$ NVFP4 / MXFP4）**：数据中心主流推理配置为 **`FP4 权重 + FP8 KV Cache`**（兼顾权重减半与长上下文并发翻倍，SGLang 等引擎还支持加载时将 NVFP4 在线重量化为 MXFP4 跨厂迁移至 AMD GPU）。但面试与架构评审绝不能陷入“4-bit 一定比 8-bit/16-bit 快”的教条——公开基准（如 NVIDIA Dynamo 在 B200/GB200 上的 Nemotron 实测）显示，若落入未针对目标架构充分优化的反量化路径（如旧版 Marlin W4A16 甚至部分小 Batch CuTeDSL 内核），**BF16 反而可能比 NVFP4 快 $12\% \sim 80\%$**！上线前必须逐一核验：① 硬件原生 Tensor Core 代际（Blackwell `SM100` vs Hopper `SM90`）；② 精确引擎版本与算子内核后端（如 FlashInfer CuTeDSL vs Marlin）在真实并发与序列长度下的吞吐-延迟帕累托曲线；③ 推理/长思维链专项任务集（3-bit 及以下对复杂推理退化远甚于普通问答）；④ 长上下文下的 KV Cache 显存瓶颈重算。

```
超低比特微缩放矩阵乘与训练稳定性闭环（NVFP4 Linear Layer）：

  前向 Fprop:  X (1x16 E4M3 + RTNE) ──┐
                                      ├─► Block-Scaled FP4 MMA ─► BF16/FP32 Y
  权重 W:      16x16 2D E4M3 + RTNE ──┼── (转置严格一致 W_fprop == W_bprop!)
                                      ├─► Block-Scaled FP4 MMA ─► BF16/FP32 dX
  反向 Dgrad:  dY (1x16 E4M3 + SR)  ──┘

  权重梯度 Wgrad:
    dY^T ──► [16x16 RHT 正交旋转] ──► (1x16 E4M3 + SR)   ─┐
                                                          ├─► FP4 MMA ─► FP32 Master Grad
    X    ──► [16x16 RHT 正交旋转] ──► (1x16 E4M3 + RTNE) ─┘   (内部 H H^T = I 精确抵消!)
```

---

### 4. 可运行 Python 3 标准库仿真：MXFP4/NVFP4 编码、二维一致性、RHT、SR 与累加提升

下面的零依赖 Python 3 标准库脚本逐比特构建了 `E2M1` 与 `UE4M3` 码表，定量验证并断言了上述五大核心机制：（1）MXFP4 在 $\text{amax}=3.10$ 时浪费 $\pm 4, \pm 6$ 码点，而 NVFP4 两级微缩放将重建误差降低逾一半；（2）权重 $1 \times 16$ 一维缩放在前向与反向转置间产生显著失配（$\|W_f - W_b\|_F > 2.2$），$16 \times 16$ 二维缩放严格归零；（3）单点尖峰抹零同块 15 个正常 Token 导致 Wgrad 内积归零，经 $16 \times 16$ 随机 Hadamard 旋转大幅恢复；（4）亚格点梯度在 RTNE 下死锁为 $0$，而随机舍入无偏收敛；（5）Hopper $\sim 14\text{-bit}$ 累加器在 $K=4096$ 下发生 $14\%$ 大数吃小数漂移，经 $N_C=128$ 周期提升至 FP32 后误差压降至 $<0.5\%$：

```python
import math
import random
from typing import List, Tuple

# FP4 E2M1 positive grid (symmetric with sign bit): 8 levels in [0, 6]
E2M1_POS = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)


def build_ue4m3_table() -> List[float]:
    """Build unsigned FP8 E4M3 table (bias=7, max=448.0, min subnormal=2^-9)."""
    vals = [0.0]
    for exp_bits in range(16):
        for mant_bits in range(8):
            if exp_bits == 0 and mant_bits == 0:
                continue
            if exp_bits == 15 and mant_bits == 7:
                continue  # NaN in E4M3
            if exp_bits == 0:
                val = (mant_bits / 8.0) * (2.0 ** -6)
            else:
                val = (1.0 + mant_bits / 8.0) * (2.0 ** (exp_bits - 7))
            vals.append(val)
    return sorted(vals)


UE4M3_TABLE = build_ue4m3_table()


def quantize_nearest(val: float, grid: Tuple[float, ...]) -> float:
    sign = -1.0 if val < 0.0 else 1.0
    ax = abs(val)
    if ax >= grid[-1]:
        return sign * grid[-1]
    best = min(grid, key=lambda g: (abs(ax - g), g))
    return sign * best


def quantize_e2m1_sr(val: float, rng: random.Random) -> float:
    """Stochastic rounding onto signed E2M1 grid (unbiased inside [-6, 6])."""
    sign = -1.0 if val < 0.0 else 1.0
    ax = abs(val)
    if ax >= E2M1_POS[-1]:
        return sign * E2M1_POS[-1]
    for idx in range(len(E2M1_POS) - 1):
        lo, hi = E2M1_POS[idx], E2M1_POS[idx + 1]
        if lo <= ax <= hi:
            prob_hi = (ax - lo) / (hi - lo)
            picked = hi if rng.random() < prob_hi else lo
            return sign * picked
    return 0.0


def mxfp4_quant_dequant_block(block32: List[float]) -> Tuple[List[float], float, float]:
    """OCP MXFP4: 32-element block, UE8M0 power-of-two scale rounded up to avoid saturation."""
    amax = max(abs(x) for x in block32)
    if amax == 0.0:
        return [0.0] * len(block32), 1.0, 0.0
    s_raw = amax / 6.0
    s_ue8m0 = 2.0 ** math.ceil(math.log2(s_raw))
    q_vals = [quantize_nearest(x / s_ue8m0, E2M1_POS) for x in block32]
    max_code_used = max(abs(q) for q in q_vals)
    return [q * s_ue8m0 for q in q_vals], s_ue8m0, max_code_used


def nvfp4_quant_dequant_tensor(flat: List[float], block_size: int = 16) -> List[float]:
    """NVIDIA NVFP4: FP32 global scale (6*448/amax) + per-16 UE4M3 decode scale + E2M1."""
    amax_global = max(abs(x) for x in flat)
    if amax_global == 0.0:
        return [0.0] * len(flat)
    s_enc_global = (6.0 * 448.0) / amax_global
    s_dec_global = 1.0 / s_enc_global
    out: List[float] = []
    for s in range(0, len(flat), block_size):
        blk = flat[s : s + block_size]
        amax_b = max(abs(x) for x in blk)
        if amax_b == 0.0:
            out.extend([0.0] * len(blk))
            continue
        s_dec_b_e4m3 = min(UE4M3_TABLE, key=lambda g: abs(g - (amax_b / 6.0) * s_enc_global))
        if s_dec_b_e4m3 == 0.0:
            out.extend([0.0] * len(blk))
            continue
        s_enc_b = 1.0 / (s_dec_b_e4m3 * s_dec_global)
        for x in blk:
            q = quantize_nearest(x * s_enc_b, E2M1_POS)
            out.append(q * s_dec_b_e4m3 * s_dec_global)
    return out


def quantize_weight_1d_vs_2d(w_16x16: List[List[float]]) -> Tuple[float, float]:
    """Compare Fprop/Dgrad weight mismatch ||W_fprop - W_bprop||_F under 1x16 vs 16x16 scaling."""
    # 1D row-wise (Fprop: along input K) vs 1D col-wise (Dgrad: transposed along output N)
    w_fprop_1d = [nvfp4_quant_dequant_tensor(row, block_size=16) for row in w_16x16]
    cols = [[w_16x16[r][c] for r in range(16)] for c in range(16)]
    cols_q = [nvfp4_quant_dequant_tensor(col, block_size=16) for col in cols]
    w_bprop_1d = [[cols_q[c][r] for c in range(16)] for r in range(16)]

    # 2D 16x16 block scaling: single shared scale across both dimensions -> transpose invariant
    flat_all = [w_16x16[r][c] for r in range(16) for c in range(16)]
    q_2d_flat = nvfp4_quant_dequant_tensor(flat_all, block_size=256)
    w_fprop_2d = [q_2d_flat[r * 16 : (r + 1) * 16] for r in range(16)]
    cols_2d_flat = [w_16x16[r][c] for c in range(16) for r in range(16)]
    q_2d_cols = nvfp4_quant_dequant_tensor(cols_2d_flat, block_size=256)
    w_bprop_2d = [[q_2d_cols[c * 16 + r] for c in range(16)] for r in range(16)]

    diff_1d = math.sqrt(sum((w_fprop_1d[r][c] - w_bprop_1d[r][c]) ** 2 for r in range(16) for c in range(16)))
    diff_2d = math.sqrt(sum((w_fprop_2d[r][c] - w_bprop_2d[r][c]) ** 2 for r in range(16) for c in range(16)))
    return diff_1d, diff_2d


def hadamard_16(vec16: List[float], signs16: List[int]) -> List[float]:
    """Normalized 16x16 Random Hadamard Transform y = (S_16 H_16)^T x (orthogonal)."""
    v = [s * x for s, x in zip(signs16, vec16)]
    step = 1
    while step < 16:
        for i in range(0, 16, step * 2):
            for j in range(i, i + step):
                a, b = v[j], v[j + step]
                v[j], v[j + step] = a + b, a - b
        step *= 2
    return [x / 4.0 for x in v]


def simulate_low_mantissa_acc(prod_terms: List[float], interval_nc: int, mant_bits: int = 13) -> float:
    """Simulate Hopper Tensor Core ~14-bit (1 implicit + 13 frac) accumulator vs CUDA Core promotion."""
    def round_low_mant(v: float) -> float:
        if v == 0.0:
            return 0.0
        m, e = math.frexp(v)  # m in [0.5, 1.0)
        q_m = round(m * (1 << (mant_bits + 1))) / (1 << (mant_bits + 1))
        return math.ldexp(q_m, e)

    fp32_master = 0.0
    tc_partial = 0.0
    for idx, term in enumerate(prod_terms, 1):
        tc_partial = round_low_mant(tc_partial + term)
        if idx % interval_nc == 0:
            fp32_master += tc_partial
            tc_partial = 0.0
    fp32_master += tc_partial
    return fp32_master


# 1) MXFP4 binade waste at amax = 3.10 (32-elem UE8M0) vs NVFP4 (16-elem UE4M3 + FP32 two-level scale)
rng = random.Random(42)
worst_blk = [3.10] + [rng.gauss(0.0, 0.8) for _ in range(15)] + [rng.gauss(0.0, 0.35) for _ in range(16)]
mx_rec, mx_scale, mx_max_code = mxfp4_quant_dequant_block(worst_blk)
nv_rec = nvfp4_quant_dequant_tensor(worst_blk, block_size=16)
mx_rmse = math.sqrt(sum((a - b) ** 2 for a, b in zip(worst_blk, mx_rec)) / len(worst_blk))
nv_rmse = math.sqrt(sum((a - b) ** 2 for a, b in zip(worst_blk, nv_rec)) / len(worst_blk))
assert mx_scale == 1.0 and mx_max_code == 3.0  # ±4 and ±6 completely wasted in MXFP4!
assert nv_rmse < mx_rmse * 0.55 and abs(nv_rec[0] - 3.10) < 0.05

# 2) 1D vs 2D weight scaling chain-rule consistency (Fprop vs Dgrad transpose)
w_mat = [[(12.0 if (r == 0 and c == 3) else rng.gauss(0.0, 0.8)) for c in range(16)] for r in range(16)]
diff_1d, diff_2d = quantize_weight_1d_vs_2d(w_mat)
assert diff_1d > 0.5 and diff_2d == 0.0

# 3) Random Hadamard Transform (d=16) rescuing non-outlier tokens wiped by a single block spike in Wgrad
# Token 0 has an activation spike (24.0) with zero grad, while tokens 1..15 carry correlated normal signals (~0.8)
x_spike = [24.0] + [0.85, -0.80, 0.75, -0.90, 0.70, -0.65, 0.88, -0.82, 0.78, -0.86, 0.72, -0.76, 0.84, -0.68, 0.80]
dy_vec = [0.0] + list(x_spike[1:])
true_dot = sum(a * b for a, b in zip(x_spike, dy_vec))
qx_raw = nvfp4_quant_dequant_tensor(x_spike)
zeroed_neighbors = sum(1 for v in qx_raw[1:] if v == 0.0)
q_no_rht_dot = sum(a * b for a, b in zip(qx_raw, nvfp4_quant_dequant_tensor(dy_vec)))
signs = [(-1 if i in (1, 2, 5, 7, 9, 11, 14, 15) else 1) for i in range(16)]
rx, rdy = hadamard_16(x_spike, signs), hadamard_16(dy_vec, signs)
assert abs(sum(a * b for a, b in zip(rx, rdy)) - true_dot) < 1e-12  # Exact orthogonality (HH^T = I)
q_rht_dot = sum(a * b for a, b in zip(nvfp4_quant_dequant_tensor(rx), nvfp4_quant_dequant_tensor(rdy)))
err_no_rht, err_rht = abs(q_no_rht_dot - true_dot), abs(q_rht_dot - true_dot)
assert zeroed_neighbors == 15 and q_no_rht_dot == 0.0 and err_rht < err_no_rht * 0.30

# 4) Sub-grid gradient update: deterministic RTNE stalls to 0 vs Stochastic Rounding unbiased
sub_grad = 0.15  # Strictly below midpoint 0.25 of [0, 0.5] in E2M1
rtne_mean = sum(quantize_nearest(sub_grad, E2M1_POS) for _ in range(4000)) / 4000.0
sr_mean = sum(quantize_e2m1_sr(sub_grad, rng) for _ in range(4000)) / 4000.0
assert rtne_mean == 0.0 and abs(sr_mean - sub_grad) < 0.015

# 5) Hopper WGMMA ~14-bit accumulation swamping at K=4096 vs N_C=128 CUDA Core FP32 promotion
terms = [10.0] + [0.0004 for _ in range(4095)]  # Swamping 4095 small positives after an initial 10.0 partial sum
exact_acc = sum(terms)
err_tc_full = abs(simulate_low_mantissa_acc(terms, interval_nc=4096) - exact_acc) / exact_acc
err_nc128 = abs(simulate_low_mantissa_acc(terms, interval_nc=128) - exact_acc) / exact_acc
assert err_tc_full > 0.12 and err_nc128 < 0.01

print(f"MXFP4 vs NVFP4 (amax=3.10): MX max_code={mx_max_code:.1f}/6.0, RMSE={mx_rmse:.4f} vs NVFP4 RMSE={nv_rmse:.4f}")
print(f"Weight Fprop/Dgrad mismatch ||W_f - W_b||_F: 1D(1x16)={diff_1d:.4f} vs 2D(16x16)={diff_2d:.4f}")
print(f"Wgrad outlier-block dot (true={true_dot:.4f}): raw_zeroed={zeroed_neighbors}/15, no_RHT_err={err_no_rht:.4f} vs RHT_err={err_rht:.4f}")
print(f"Sub-grid grad (g=0.15) quantized mean: RTNE={rtne_mean:.4f} (underflow stall) vs SR={sr_mean:.4f}")
print(f"K=4096 low-mantissa acc rel error: full_TC={err_tc_full:.2%} vs N_C=128_promotion={err_nc128:.2%}")
print("All FP8/MXFP4/NVFP4 microscaling, 2D scaling, RHT, and SR checks passed.")
```

```text
MXFP4 vs NVFP4 (amax=3.10): MX max_code=3.0/6.0, RMSE=0.1346 vs NVFP4 RMSE=0.0640
Weight Fprop/Dgrad mismatch ||W_f - W_b||_F: 1D(1x16)=2.2360 vs 2D(16x16)=0.0000
Wgrad outlier-block dot (true=9.3463): raw_zeroed=15/15, no_RHT_err=9.3463 vs RHT_err=2.6460
Sub-grid grad (g=0.15) quantized mean: RTNE=0.0000 (underflow stall) vs SR=0.1465
K=4096 low-mantissa acc rel error: full_TC=14.07% vs N_C=128_promotion=0.43%
All FP8/MXFP4/NVFP4 microscaling, 2D scaling, RHT, and SR checks passed.
```

---

## 延伸 / 追问

**追问 1：为什么随机 Hadamard 变换（RHT）里的对角随机符号翻转矩阵 $S_d = \text{diag}(\pm 1)$ 在小模型短程实验里看不出差异，到了百亿参数长程预训练却不可或缺？为什么标准做法不在每个训练步重新采样新的随机矩阵？**
1. **防范“结构化离群值（Structured Outliers）”与固定 Hadamard 基共振**：标准确定性 Walsh-Hadamard 矩阵 $H_d$ 的行向量是高度规则的方波正交基（如全 $+1$ 行、交替 $+1/-1$ 行）。在大规模模型长达数万亿 Token 的演化中，特征或激活梯度可能自发形成与某条确定性 Hadamard 基向量高度对齐的周期性/常数结构模式——此时 $H_d x$ 非但不能摊平能量，反而会把整块 16 个元素的能量重新汇聚成新的旋转空间尖峰！左乘随机符号翻转 $S_d$ 以极低代价打碎了确定性相位对齐，使任意固定方向的离群向量以高概率均匀弥散为近似高斯分布。
2. **共享固定种子的工程零开销**：NVIDIA 消融实验（`arXiv:2509.25149` §4.2 & Appendix E.4.3）证实，**全网所有线性层在整个训练周期内共享同一个固定随机符号向量**，其收敛效果与每层/每步独立重采样完全相当，同时省去了跨流水线并行（PP）或重计算（Activation Checkpointing）阶段同步随机数发生器（RNG）状态的系统复杂度。

**追问 2：在 Blackwell（`SM100`）架构的 `DeepGEMM` 与原生硬件指令中，缩放因子（Scaling Factors）的显存布局与 Hopper（`SM90`）软件分块方案相比发生了什么本质变化？**
1. **`SM90`（Hopper）的外围软件乘加**：Hopper Tensor Core 本身不懂组缩放，因此 `DeepGEMM` 在 `SM90` 上要求缩放因子以 **FP32** 格式存放，并在每隔 $N_C=128$ 步把累加器搬到 CUDA Core 时用 FFMA 指令显式乘回。
2. **`SM100`（Blackwell）的硬件 TMA 打包直喂与原子块交错布局**：Blackwell 第五代 Tensor Core（`tcgen05.mma` Block-Scaled 指令）在硬件矩阵乘微架构内部原生集成了微缩放乘法器！如 `DeepGEMM` 文档与 `LeetCUDA` 所示，在 `SM100` 上 MX 路线必须将 **4 个 `UE8M0` 缩放字节紧凑打包进单个 32-bit `int`**（NVFP4 则按 `512 B` 原子块交错排列 `UE4M3` 字节），且左矩阵缩放因子须预先满足 **TMA（Tensor Memory Accelerator）对齐与转置布局**——算子在量化前处理（Prologue / 前序算子融合）阶段就要一次性写好硬件专属的 Swizzled 缩放布局，否则额外的布局重排访存会瞬间吞噬 FP4 省下的算力红利。

**追问 3：当团队持有 NVIDIA Blackwell 训练出的官方 NVFP4 权重 Checkpoint，却需要跨异构算力池部署到只支持 OCP MXFP4 的 AMD MI350X 集群（或混合云）时，能否直接无损转换？会遇到什么精度折损？**
1. **加载期在线重量化（On-Load Requantization）路径**：两者的底层数据格点同为 `E2M1`，但缩放元数据不兼容（NVFP4 为 `16 元素 + UE4M3 + FP32`，MXFP4 为 `32 元素 + UE8M0`）。现代推理框架（如 SGLang）的做法是在加载权重时，先将相邻两个 16 元素 NVFP4 子块反量化回高精浮点拼成 32 元素块，再重新提取 `UE8M0` 2 的幂次缩放并二次量化回 `E2M1`。
2. **二次量化折损边界**：由于经历了“两个独立 16 元素精细格 $\to$ 合并 32 元素粗糙幂次格”的有损重映射，会引入双重量化舍入与潜在的 Binade 压缩；尽管在大型冗余 MoE 专家权重上公开测试通常能保留约 $97.5\% \sim 100\%$ 的数学基准（如 GSM8K）表现，但对极小参数密度模型或高敏推理层，优先推荐从原始 BF16/FP8 主权重直接导出目标硬件原生格式，而非对已量化的 4-bit 权重做链式二转。

---

## 常见误区

- **误区一：“把线上推理从 BF16/FP8 换成 NVFP4 权重，吞吐和首字延迟（TTFT）在任何 Batch Size 下都会自动提升 2 到 4 倍。”**
  事实：**数据类型位宽不等于实际算子速度！** 在小 Batch 解码或特定模型形状下，若推理引擎选用了需要寄存器软件解包的反量化内核（如在 Blackwell 上误走旧版 Marlin W4A16 路径而非原生 Block-Scaled / FlashInfer CuTeDSL 路径，或张量维度未对齐硬件 Tile），反量化与缩放因子访存开销可能令 **BF16 实测吞吐反而比 NVFP4 快 $12\% \sim 80\%$**。低比特收益高度绑定“硬件代际 + 引擎版本 + 内核后端 + 负载算术强度”。
- **误区二：“既然随机舍入（Stochastic Rounding）在数学上是无偏估计，FP4 预训练就应该对权重、前向激活和反向梯度全部开启随机舍入以最大化精度。”**
  事实：**恰恰相反，对前向激活或权重开启随机舍入会导致训练直接发散！** 随机舍入虽然消除了确定性舍入的方向偏置（$\mathbb{E}[q(x)] = x$），但其单次采样方差显著高于最近偶数舍入（RTNE）。前向传播注入的高方差量化噪声会在深层网络中逐层累积放大破坏特征表达；只有梯度张量需要在跨步累加中严格消除亚格点截断死锁，因此必须执行“梯度用 SR、权重与激活用 RTNE”的非对称策略。
- **误区三：“为了避免前反向转置时重新分组量化，激活和激活梯度（Dgrad）也应该像权重一样直接采用二维块（如 $128 \times 128$ 或 $16 \times 16$）共享缩放因子。”**
  事实：**权重可以做二维块缩放，激活梯度做二维块缩放会引发灾难性发散！** 权重矩阵分布相对平稳且能在优化过程中自适应量化格点；而激活梯度在不同 Token 位置之间存在悬殊的突发尖峰（Token-Correlated Outliers）。一旦沿 Token 维度把几十上百个 Token 绑进同一个二维块缩放因子，单个异常 Token 就会把同块其余全部正常 Token 回传的浅层梯度冲刷归零。

---

## 参考

- 选题线索：[ombharatiya/ai-system-design-guide (`03-training-and-adaptation/07-quantization-deep-dive.md`)](https://github.com/ombharatiya/ai-system-design-guide/blob/10bdeb25e7e461247d25634f2cc4a0800ae368f6/03-training-and-adaptation/07-quantization-deep-dive.md)（固定 commit `10bdeb2`）与 [xlite-dev/LeetCUDA (`kernels/interview/book/chapters/ch36-fp4-gemm-quant.tex`)](https://github.com/xlite-dev/LeetCUDA/blob/ee05341345c09d2029dc75d1de8a48310ae33595/kernels/interview/book/chapters/ch36-fp4-gemm-quant.tex)（固定 commit `ee05341`），结合原论文与内核库源码对照核实。
- NVIDIA et al., [Pretraining Large Language Models with NVFP4](https://arxiv.org/abs/2509.25149)（`arXiv:2509.25149v2`）：NVFP4 两级微缩放（`FP32` 全局 $2688/\text{amax}$ + `16-elem UE4M3`）与 MXFP4（`32-elem UE8M0` 倍频程损失与 $+36\%$ Token 代价）对比、$16 \times 16$ 二维权重缩放、Wgrad 随机 Hadamard 变换与梯度随机舍入消融实验。
- DeepSeek-AI, [DeepSeek-V3 Technical Report](https://arxiv.org/abs/2412.19437)（`arXiv:2412.19437v2` §3.3 & Appendix B.2）：$1 \times 128$ 激活 Tile 与 $128 \times 128$ 权重 Block 在线 `E4M3` 量化、Hopper Tensor Core $\sim 14\text{-bit}$ 累加器缺陷、$N_C = 128$ CUDA Core FP32 提升及 Dgrad 二维块量化发散分析。
- 官方内核源码 [deepseek-ai/DeepGEMM (`README.md`)](https://github.com/deepseek-ai/DeepGEMM/blob/09e7d8e7edfb12b84042526bff814844b2c1dbbf/README.md)（固定 commit `09e7d8e`）与 Open Compute Project (OCP) *Microscaling Formats (MX) Specification v1.0*：`SM90` FP32 缩放 vs `SM100` 打包 `UE8M0` TMA 转置对齐规范。

来源访问与示例核验日期：**2026-11-28**。仅执行标准库下 `E2M1`/`UE4M3`/`UE8M0` 逐格编码、二维权重转置一致性、$16 \times 16$ 随机 Hadamard 变换、随机舍入无偏性与低尾数累加提升的确定性数值验证，未在多卡 Hopper/Blackwell 物理集群上运行万亿 Token 训练或真实内核吞吐压测。
