---
id: llm-0038
title: KV Cache 极低比特量化（KIVI 与 KVQuant）是如何通过键值非对称分组、流式残差窗口、Pre-RoPE 量化与稠密-稀疏离群值隔离实现 2-bit 无损长上下文推理的？
category: llm
tags: [kv-cache-quantization, kivi, kvquant, pre-rope, asymmetric-quantization]
difficulty: hard
role: engineer
contributor: 佚名
source: Hugging Face 官方技术博客与公开推理优化题库扩展改编；KIVI（ICML 2024）、KVQuant（NeurIPS 2024）及官方源码核实（见参考）
status: published
updated: 2026-11-10
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-11-10
    updated: 2026-11-10
---

## 问题

在长上下文（如 $128\text{K}\sim 1\text{M}$ Tokens）或大并发 Batch 推理服务中，即便模型权重已被压缩至 4-bit，以 FP16/BF16 存储的动态键值缓存（KV Cache）仍会迅速膨胀至数十乃至上百 GB，不仅限制了系统的最大并发吞吐，更让自回归 Decode 阶段彻底受困于高带宽显存（HBM）的访存带宽墙（Memory-bound）。然而，工程实践发现：如果简单套用传统的对称/非对称按 Token（Per-Token）统一量化，一旦将 KV Cache 压至 **2-bit**，模型在长文本大海捞针（Passkey Retrieval）与困惑度（Perplexity）评测中就会发生灾难性崩塌。为此，学术界与工业界提出了 **KIVI（ICML 2024）** 与 **KVQuant（NeurIPS 2024）** 等极低比特 KV Cache 量化方案，并被集成至 Hugging Face `transformers`（`QuantizedCache`）与主流推理引擎中。

请深入剖析以下三个核心问题：
1. **Key 与 Value 的非对称分布特性与流式残差窗口（KIVI 核心机制）**：为什么 KIVI 指出“Key Cache 必须按通道（Per-Channel）量化，而 Value Cache 必须按 Token（Per-Token）量化”？既然 Key 按通道量化需要跨多个 Token 统计缩放因子，而在自回归 Decode 阶段新 Token 是逐个生成的，KIVI 是如何通过**分组对齐的 FP16 残差缓存窗口（Residual Cache，$R=128$）**解决流式追加冲突与注意力计算拼接的？
2. **旋转位置编码（RoPE）对 Key 通道平稳性的破坏与 Pre-RoPE 量化（KVQuant 机制一）**：为什么在施加 RoPE 之后再对 Key 做按通道量化（Post-RoPE Quantization）会导致 2-bit/3-bit 精度显著恶化？请从二维旋转矩阵 $\mathbf{R}_{\Theta, t}$ 的跨位置混叠方程推导原因，并说明 KVQuant 是如何实现 **Pre-RoPE 缓存量化** 与融合内核中的动态在线旋转反量化的？
3. **非均匀量化（NUQ）、1% 稠密-稀疏离群值隔离与首词保护（KVQuant 机制二）**：在免微调（Tuning-Free）条件下冲击 2-bit 极限时，KVQuant 是如何结合**离线 Fisher 信息加权非均匀码本（Sensitivity-Weighted NUQ）**、**1% 稠密-稀疏分解（Dense-and-Sparse Quantization）**、**注意力汇聚点首词保护（Attention-Sink-Aware FP16 Retention）**以及 **Q-Norm 量化后矩校准**消除分布偏移的？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-11-10

**将 KV Cache 无损压缩至 2-bit 的核心，在于顺应 Key 与 Value 在张量维度上的异构离群值几何结构，并消除位置编码旋转混叠与极端离群点对量化网格的拉扯：（1）KIVI 揭示了 Key 张量的高幅值离群值高度集中在少数固定通道（Fixed Channels across Tokens），而 Value 张量无持久通道尖峰但不同 Token 间基线波动剧烈；因此必须对 Key 沿序列维分组做 Per-Channel 量化、对 Value 沿特征维分组做 Per-Token 量化；为解决 Per-Channel Key 无法单 Token 独立量化的自回归流式矛盾，KIVI 维护长度为 $R$（如 $128$，满足 $R \bmod G = 0$）的 FP16 残差窗口，仅当 `key_states_full` 攒满 $R$ 个 Token 时才按组批量转置打包为 2-bit，而 `value_states_full` 则在超出 $R$ 时逐个弹出最老 Token 量化；（2）KVQuant 进一步指出，RoPE 的正余弦旋转矩阵 $\mathbf{x}_t' = \mathbf{x}_t \cos(t\theta) + \operatorname{rotate\_half}(\mathbf{x}_t)\sin(t\theta)$ 会将固定离群通道的能量随位置 $t$ 周期性混入伙伴通道并产生包络震荡，彻底破坏 Key 通道的跨 Token 平稳性；通过在施加 RoPE 之前（Pre-RoPE）量化并存储 Key，并在 Decode 内核读取反量化时即时乘上 $\cos/\sin$ 相位，可大幅降低量化均方误差；（3）针对残余极端值与 2-bit 量化偏差，KVQuant 引入按向量移除上下各 $0.5\%$ 极值的稠密-稀疏存储（CSR/Top-$K$ 稀疏缓冲）、保留前 $F$ 个 Attention Sink Token 为 FP16、基于单样本校准的 K-Means 非均匀查找表（NUQ LUT）以及对齐量化前后均值与标准差的 Q-Norm 仿射修正，在接近零质量损失下实现约 $3.5\times\sim 4.8\times$ 的端到端 KV 显存缩减。**

在展开数学推导与源码级拆解之前，建议先关联本库内已有的相关题目建立全局视角：关于 KV Cache 的基本内存计算公式以及 Prefill（计算受限）与 Decode（访存受限）的算术强度对比，请参阅 [llm-0018](llm-0018-kv-cache-prefill-decode.md)；关于模型权重与激活的训练后量化（GPTQ、AWQ 与 SmoothQuant 跨层通道平滑迁移），请参阅 [llm-0035](llm-0035-ptq-gptq-awq-smoothquant.md)；关于本地部署量化模型时的总显存预算估算，请参阅 [llm-0016](llm-0016-quantization-local-memory-budget.md)；关于从注意力架构源头通过低秩联合压缩削减 KV Cache 的 MLA 机制，请参阅 [llm-0034](llm-0034-mla-multi-head-latent-attention-rope-absorption.md)。

---

### 1. KIVI 的非对称量化洞察：为什么 Key 按通道、Value 按 Token？流式残差窗口如何运作？

#### （1）Key 与 Value 的异构离群值结构及数学误差分析
设单层单个 KV Head 的历史缓存张量为 $\mathbf{K}, \mathbf{V} \in \mathbb{R}^{T \times D}$（其中 $T$ 为当前序列长度，$D$ 为单头维度 `head_dim`，如 $128$）。**KIVI**（Liu et al., ICML 2024）通过对 Llama-2、Mistral、Falcon 等主流模型的各层激活进行逐元素分布统计，发现了键值张量在离群值（Outliers）结构上的根本不对称性：

1. **Key Cache 的持续性通道离群值（Persistent Channel-wise Outliers）**：
   - 在 Key 张量 $\mathbf{K}$ 中，存在少数几个特定的通道索引 $c^* \in \{0, \dots, D-1\}$，其激活幅值在**几乎所有 Token 位置 $t \in [1, T]$ 上都恒定比普通通道高出 $5\times\sim 20\times$**（这与 RoPE 低频维度演化出的长程注意力偏置及线性层权重结构密切相关）。
   - 如果对 $\mathbf{K}$ 采用按 Token（Per-Token，即沿通道维 $D$ 分组）量化，每个 Token 组内的动态范围 $\Delta_t = \max_c K_{t,c} - \min_c K_{t,c}$ 都会被离群通道 $K_{t,c^*}$ 撑大数十倍！在 2-bit（仅 $2^2 = 4$ 个离散电平 $\{0, 1, 2, 3\}$）下，量化步长 $s_t = \Delta_t / 3$ 变得极其粗糙，导致其余 $95\%$ 的正常通道全部坍缩为同一个电平，注意力相关性分数 $\mathbf{q}_t \mathbf{K}^\top$ 彻底失真。
   - 反之，如果对 $\mathbf{K}$ 采用**按通道分组量化（Per-Channel Group Quantization，沿 Token 维 $T$ 每 $G$ 个连续 Token 为一组，如 $G=32$ 或 $64$）**，由于同一个通道 $c$ 内部在不同 Token 位置上的数值集中在狭窄区间内，每个通道组的动态范围 $\Delta_{g,c} = \max_{t \in g} K_{t,c} - \min_{t \in g} K_{t,c}$ 极小，2-bit 量化步长得以精细贴合该通道自身的局部波动！
2. **Value Cache 的 Token 级幅值异质性与 Softmax 凸组合效应**：
   - 在 Value 张量 $\mathbf{V}$ 中，并不存在跨越所有 Token 的固定离群通道，但**不同 Token 之间的整体基线与幅值方差差异巨大**（特别是句首的 Attention Sink Token 或关键实体词，其幅度与普通虚词截然不同），而在同一个 Token 内部各通道幅值相对均衡。
   - 更重要的是，注意力输出是 Value 行向量的加权凸组合 $\mathbf{o}_t = \sum_{j=1}^T A_{t,j} \mathbf{v}_j$（其中 $\sum_j A_{t,j} = 1$）。若对 $\mathbf{V}$ 按通道（跨 Token）量化，某一个高幅值 Token $\mathbf{v}_{j^*}$ 会撑爆同一时间窗口内所有其他普通 Token $\mathbf{v}_j$ 的量化步长；当当前步注意力权重 $A_{t,j}$ 恰好聚焦在这些普通 Token 上时，重构误差就会被直接放大。因此，**$\mathbf{V}$ 必须采用按 Token 分组量化（Per-Token Group Quantization，沿通道维 $D$ 每 $G$ 个通道为一组）**，把每个 Token 的幅值隔离在自身内部。

在 KIVI 官方源码 `jy-yuan/KIVI/quant/new_pack.py` 中，$b$-bit 分组非对称量化（Asymmetric Uniform Quantization）的精确公式为：

$$s = \frac{\max(\mathbf{x}_g) - \min(\mathbf{x}_g)}{2^b - 1}, \quad z = \min(\mathbf{x}_g), \quad q(\mathbf{x}_g) = \operatorname{clamp}\left(\left\lfloor \frac{\mathbf{x}_g - z}{s} \right\rceil, \, 0, \, 2^b - 1\right), \quad \hat{\mathbf{x}}_g = q(\mathbf{x}_g) \cdot s + z$$

在位打包（Bit-packing）布局上，`quant_and_pack_kcache` 将形状为 `[B, nh, T, D]` 的 Key 沿 Token 维 `pack_dim = 2`（或在 `triton_quantize_and_pack_along_last_dim` 中先 `.transpose(2, 3)` 转置为 `[B, nh, D, T]` 后沿最后一维 $T$）每 $32 / b = 16$ 个 2-bit 整数压入 1 个 `int32`；而 `quant_and_pack_vcache` 则沿通道维 `pack_dim = 3` 打包为 `[B, nh, T, D // 16]`。

#### （2）流式残差窗口（FP16 Residual Cache）的分组对齐刷新机制
面试中最常追问的工程难点是：**既然 Key 的 Per-Channel 量化必须沿 Token 维跨 $G$ 个 Token 计算 $\min/\max$，而在自回归 Decode 阶段每步只生成 1 个新 Token $\mathbf{k}_t \in \mathbb{R}^{1 \times D}$，如何避免每步重算或单元素退化？**
（注：若错误地对每个新生成的单 Token 直接调用 Per-Channel 量化，由于组内只有 1 个元素，必然导致 $\min = \max$，不仅退化为无压缩，且每 Token 都要存一套 FP16 的 $(s, z)$ 元数据，显存反而比原 FP16 更大！）

结合官方源码 `jy-yuan/KIVI/models/llama_kivi.py`（`LlamaFlashAttention_KIVI.forward`），KIVI 设计了容量为 $R$（`residual_length = 128`，要求 $R \bmod G = 0$，默认 $G = 32$）的 **FP16 残差缓存窗口（Residual Cache）**，其 Key 与 Value 遵循截然不同的异构刷盘状态机：

```text
KIVI 异构流式 KV 缓存状态机 (设 Group Size G=32, Residual Length R=128, Bit-width b=2):

1. Prefill 阶段 (输入长度 L_prompt = 300):
   - Key 切分: 前 256 个 Token (300 - (300 % 128) = 256, 整除 R=128) 立即转置并按 Per-Channel (G=32) 打包进 key_states_quant_trans (2-bit);
               尾部余数 300 % 128 = 44 个 Token 原样保留在 key_states_full (FP16)。
   - Value 切分: 前 300 - 128 = 172 个 Token 立即按 Per-Token (G=32) 打包进 value_states_quant (2-bit);
                 最后 R = 128 个 Token 原样保留在 value_states_full (FP16)。

2. Decode 阶段 (每步新增 1 个 Token k_new, v_new):
   - Step A (拼接与双分支注意力):
     key_states_full <- cat([key_states_full, k_new], dim=2)
     att_qkquant = cuda_bmm_fA_qB_outer(q, key_states_quant_trans)   # 融合反量化 GEMV 算历史 2-bit Key
     att_qkfull  = matmul(q, key_states_full^T)                      # 标准 FP16 GEMV 算近期残差 Key
     attn_weights = softmax(cat([att_qkquant, att_qkfull], dim=-1) / sqrt(D))

   - Step B (Key 批量整块刷盘 — 仅当 key_states_full 长度恰好达到 R=128 时触发!):
     if key_states_full.shape[-2] == 128:
         把这 128 个 FP16 Key 一次性切为 4 个 G=32 的 Per-Channel Group 量化追加到 key_states_quant_trans,
         并将 key_states_full 重置为 None (清空为 0)!

   - Step C (Value 滑动逐个刷盘 — 每次追加后只要 value_states_full 长度 > R=128 即触发!):
     value_states_full <- cat([value_states_full, v_new], dim=2)     # 此时长度为 129
     attn_output = cuda_bmm_fA_qB_outer(W_quant, value_states_quant) + matmul(W_full, value_states_full)
     if value_states_full.shape[-2] > 128:                           # 恒等于 129 == R + 1
         弹出最老的 1 个 Token value_states_full[:, :, :1, :] 按 Per-Token 量化追加到 value_states_quant,
         value_states_full <- value_states_full[:, :, 1:, :]         # 维持残差窗口恒为最新 128 个 Token!
```

这一设计的精妙之处在于：
- **精度红利**：自回归生成具有强烈的局部性（Locality），距离当前位置最近的 $R=128$ 个 Token 通常占据了极高比例的注意力权重。将这些近期 Token 保留为无损 FP16，天然屏蔽了近距离 2-bit 量化噪声。
- **硬件对齐与零重算**：所有进入 2-bit 缓存区的 Key 块永远是 $G=32$ 的整数倍，一生只被量化打包一次，后续绝不发生反量化再重新量化的二次舍入损失。

---

### 2. KVQuant 机制一：为什么必须在 RoPE 之前（Pre-RoPE）对 Key 缓存做按通道量化？

尽管 KIVI 通过 Per-Channel Key 量化大幅改善了精度，但在超长上下文（如 $128\text{K}\sim 1\text{M}$）或更激进的无分组/大分组 Per-Channel 量化下，后旋转量化（Post-RoPE Quantization）仍会出现明显退化。**KVQuant**（Hooper et al., NeurIPS 2024）找出了罪魁祸首：**旋转位置编码（RoPE）破坏了 Key 离群通道的跨位置平稳性！**

#### （1）RoPE 引发的“通道混叠与余弦调制”数学证明
在标准 Llama 架构中，线性层输出的未旋转键向量为 $\mathbf{k}_t^{\text{pre}} = \mathbf{W}_K \mathbf{h}_t \in \mathbb{R}^D$。RoPE 将第 $2m$ 维与第 $2m+1$ 维（在 Hugging Face 实现中为第 $m$ 维与第 $m + D/2$ 维，`rotate_half`）配对，按位置 $t$ 施加二维正交旋转（设角频率 $\theta_m = 10000^{-2m/D}$）：

$$\begin{bmatrix} k_{t, 2m}^{\text{post}} \\ k_{t, 2m+1}^{\text{post}} \end{bmatrix} = \begin{bmatrix} \cos(t\theta_m) & -\sin(t\theta_m) \\ \sin(t\theta_m) & \cos(t\theta_m) \end{bmatrix} \begin{bmatrix} k_{t, 2m}^{\text{pre}} \\ k_{t, 2m+1}^{\text{pre}} \end{bmatrix}$$

假设在旋转前的 $\mathbf{k}_t^{\text{pre}}$ 中，通道 $2m$ 是一个恒定偏高的显著离群通道（例如跨所有位置 $t$ 稳定在 $k_{t, 2m}^{\text{pre}} \approx A + \epsilon_t$，其中常量偏置 $A = 12.0$，局部标准差 $\sigma_\epsilon = 0.1$），而其配对的伙伴通道 $2m+1$ 是一个普通的零均值小幅值通道（$k_{t, 2m+1}^{\text{pre}} \in [-0.3, 0.3]$）：
1. **如果直接对旋转前的 $\mathbf{k}_t^{\text{pre}}$ 做 Per-Channel 量化（Pre-RoPE Quantization）**：
   - 通道 $2m$ 的数值区间仅仅是 $[11.8, 12.2]$，宽度 $\Delta^{\text{pre}}_{2m} \approx 0.4$；
   - 通道 $2m+1$ 的数值区间仅仅是 $[-0.3, 0.3]$，宽度 $\Delta^{\text{pre}}_{2m+1} \approx 0.6$；
   - 两个通道各自拥有极窄的动态范围，2-bit 量化误差微乎其微！并且由于二维旋转矩阵 $\mathbf{R}(t\theta_m)$ 是**严格正交保范的（Orthogonal / Norm-Preserving，$\|\mathbf{R}\mathbf{e}\|_2 = \|\mathbf{e}\|_2$）**，先在 Pre-RoPE 空间量化得到 $\hat{\mathbf{k}}_t^{\text{pre}}$ 再在读取时乘上 $\mathbf{R}(t\theta_m)$，其最终重构误差严格等于旋转前的极小量化误差：
     $$\left\| \mathbf{R}(t\theta_m) \mathbf{k}_t^{\text{pre}} - \mathbf{R}(t\theta_m) \hat{\mathbf{k}}_t^{\text{pre}} \right\|_2^2 = \left\| \mathbf{k}_t^{\text{pre}} - \hat{\mathbf{k}}_t^{\text{pre}} \right\|_2^2$$
2. **如果对旋转后的 $\mathbf{k}_t^{\text{post}}$ 做 Per-Channel 量化（Post-RoPE Quantization）**：
   - 经过旋转后，$k_{t, 2m}^{\text{post}} \approx A \cos(t\theta_m)$，随着位置 $t$ 的推进，该通道的值会在 $[-A, +A] = [-12.0, +12.0]$ 之间剧烈正余弦摆动，动态范围暴涨 $60\times$（$\Delta^{\text{post}}_{2m} \approx 24.0$）！
   - 更糟糕的是，原本干净的伙伴通道 $2m+1$ 被强行混入了 $A \sin(t\theta_m)$ 分量，其动态范围同样从 $0.6$ 被污染膨胀至 $24.0$！两个通道的 2-bit 量化步长双双劣化数十倍。

#### （2）KVQuant 的 Pre-RoPE 源码级实现与融合算子设计
结合官方源码 `SqueezeAILab/KVQuant`（`deployment/transformers/src/transformers/models/llama/modeling_llama.py`），KVQuant 对标准注意力管线做了如下重构：
- 在 `forward` 中，仅对当前步的 Query 向量调用 `query_states = apply_rotary_pos_emb_query(query_states, cos, sin, position_ids)`；
- 而新生成的 `key_states`（除前 `first_few_fp16` 个首词外）**不经过 `apply_rotary_pos_emb`**，直接以未旋转形态送入 `self.kcache.parallel_pack(key_states)`（Prefill）或 `vecquant{2,3,4}appendvecKsparse`（Decode）压入低比特缓存；
- 在 Decode 阶段计算 $\mathbf{q}_t \mathbf{K}^\top$ 时，调用融合 CUDA 内核 `vecquant{2,3,4}matmul_nuq_perchannel_transposed_rope_mha_batched_fused_opt2`：内核在寄存器中将 $b$-bit 索引查表反量化为 $\hat{k}_{j, c}^{\text{pre}}$ 后，**直接利用线程持有的历史位置下标 $j$ 与 `rope_theta` 在片上即时完成旋转并与已旋转的 $q_{t, c}^{\text{post}}$ 累加点积**，无需将旋转后的 FP16 Key 写回 HBM！

---

### 3. KVQuant 机制二：Fisher 非均匀码本（NUQ）、1% 稠密-稀疏隔离、Sink 首词保护与 Q-Norm

为了在全序列范围（消除每 32 个 Token 存一组 FP16 缩放因子的元数据开销）下实现 2-bit / 3-bit 逼近 FP16 的精度，KVQuant 在 `simquant_module_quantizer.py` 中进一步集成了四项关键技术：

1. **离线 Fisher 敏感度加权非均匀量化（Sensitivity-Weighted Non-Uniform Quantization, NUQ）**：
   - KV 激活在剔除极端点后呈现典型的钟形非均匀分布（大量数值密集分布在 0 附近，尾部稀疏），均匀网格会把宝贵的量化电平浪费在稀疏尾部。
   - KVQuant 利用离线校准集（如 Wikitext-2 的 16 个样本）提取各层 Key/Value 投影层的激活与二阶梯度平方近似的 Fisher 信息矩阵 $F_i = (\partial \mathcal{L} / \partial x_i)^2$，在归一化区间 $[-1, 1]$ 上运行带样本权重 `sample_weight = fisher_info` 的 **K-Means 聚类（$2^b$ 个簇）**：
     $$\min_{\{c_1, \dots, c_{2^b}\}} \sum_{i \in \text{inliers}} F_i \cdot \min_{k \in \{1, \dots, 2^b\}} \left( \tilde{x}_i - c_k \right)^2$$
   - 聚类所得的 $2^b$ 个质心（Signposts / LUT）在各层间共享（或按通道缩放映射为 `lookup_table[head, dim, 2^b]`），推理时通过硬件快速查表取代均匀乘加。
2. **1% 稠密-稀疏量化（Dense-and-Sparse Quantization）与中位数重定中心**：
   - 即使按通道量化 Key 或按 Token 量化 Value，单个向量内部仍会出现约 $0.1\%\sim 1\%$ 的极端突发离群点（Spike Outliers）。如果直接用含离群点的极值计算区间，2-bit 的 4 个质心仍会被拉偏。
   - 如 `SimQuant.quantize` 与 `quant_fn_nuq_recon` 所示，给定稀疏度阈值 `sparsity_threshold = 0.99`（即隔离 $1\%$ 离群值：上界分位数 $t = 1 - (1 - 0.99)/2 = 99.5\%$，下界 $0.5\%$），KVQuant 先将超出分位数阈值的离群点位置 `outlier_mask` 识别出来，在计算内点（Inliers）的 `maxval` 与 `minval` 前，**先将离群位置临时替换为通道中位数 `data_trimmed[outlier_mask] = med[outlier_mask]`**，再算出紧凑的内点中心 `offset = (maxval + minval) / 2` 与半宽 `rangeval = (maxval - minval) / 2`。
   - 落入 $[-1, 1]$ 的 $99\%$ 稠密内点以 2-bit/3-bit 打包存入 `kcache`/`vcache`；而溢出的 $1\%$ 稀疏离群点则在减去最近端点的量化值（如 `upper_outliers - lut[..., numvals - 1]`）后，以稀疏坐标格式（CSR 或每 Token 固定上限 `topK` 缓冲 `outliers` + `outlier_indices`）单独以 FP16 精确存储，并在 SpMV 内核中累加回注意力输出。
3. **注意力汇聚点首词保护（Attention-Sink-Aware Quantization, `first_few_fp16`）**：
   - 如 StreamingLLM 所示，自回归模型在训练期因因果掩码形成了一种结构性偏置：会将海量无处安放的冗余注意力权重倾倒在序列最开头的 $1\sim 4$ 个 Token（尤其是 BOS 首词，即 Attention Sink）上，且首词在经过层归一化与投影后呈现出与后续所有普通 Token 完全异质的超大激活范数。
   - KVQuant 在 `modeling_llama.py` 中引入 `first_few_fp16`（通常设为 $1$ 或 $4$）：不仅在离线校准计算通道分位数与 K-Means 时直接屏蔽前 $F$ 个 Token（防止首词扭曲全序列的通道缩放因子），而且在推理期单独开辟 `self.kcache_fp16` 与 `self.vcache_fp16` 原样保留前 $F$ 个 Token 为 FP16！
4. **2-bit Q-Norm（Quantization-Normalization 量化后矩匹配校准）**：
   - 在极低位宽（2-bit）下，非均匀量化后的离散质心集合 $Q = \operatorname{LUT}(\tilde{\mathbf{x}})$ 相比原连续内点分布 $\tilde{\mathbf{x}}$ 会发生系统性的方差收缩与均值漂移（Distribution Shift），在深层网络逐层累积后引发输出退化。
   - KVQuant 在 `SimQuant.quantize`（第 533–549 行）中统计内点量化前的真实均值 $m_1$、标准差 $\sigma_1$ 与量化后的均值 $m_2$、标准差 $\sigma_2$，计算线性校准系数并直接折叠进二级查找表 `lookup_table2` 中（运行期零额外算力开销）：
     $$\text{normscale} = \frac{\sigma_1}{\sigma_2}, \quad \text{normoffset} = m_1 - m_2 \cdot \frac{\sigma_1}{\sigma_2}, \quad \hat{Q}_{\text{Q-Norm}} = Q \cdot \text{normscale} + \text{normoffset}$$

| 对比维度 | Hugging Face 基础按 Token 量化 | KIVI（ICML 2024） | KVQuant（NeurIPS 2024） |
| :--- | :--- | :--- | :--- |
| **Key 量化粒度与阶段** | Post-RoPE 按 Token 分组（2-bit 崩塌） | **Post-RoPE 按通道分组**（沿序列每 $G=32$ 切组） | **Pre-RoPE 按通道全序列共享缩放**（读取时在线旋转） |
| **Value 量化粒度** | 按 Token 分组 | **按 Token 分组**（沿通道每 $G=32$ 切组） | **按 Token 动态缩放**（共享离线非均匀码本 LUT） |
| **数据网格与校准需求** | 均匀仿射 Min-Max（免校准） | **均匀仿射 Min-Max（100% 免校准、确定性）** | **Fisher 加权 K-Means 非均匀码本 NUQ + Q-Norm**（需轻量单样本校准） |
| **近期/特殊 Token 保护** | 无（或简单滑动窗） | **尾部 $R=128$ 个 Token 全精度残差缓存（Residual Cache）** | **头部 $F=1\sim 4$ 个 Attention Sink 首词 FP16 保护** |
| **极端突发离群值处理** | 无隔离（直接拉大组内 `scale`） | 依赖 $G=32$ 局部小分组限制影响范围 | **1% 稠密-稀疏分解（Dense-and-Sparse，FP16 CSR / Top-$K$ 旁路）** |
| **单元素有效平均位宽（2-bit）** | $2.50\text{ bits}$（$G=64$） | **约 $3.00\text{ bits}$**（$G=32$ 含 FP16 $(s,z)$ + 残差窗摊薄） | **约 $2.20\sim 2.35\text{ bits}$**（含 $1\%$ FP16 稀疏索引与按 Token 缩放） |

---

### 4. Python 3 标准库实现：KIVI 异构流式残差缓存与 KVQuant Pre-RoPE / 稀疏 Q-Norm 仿真

下面的零依赖 Python 3 标准库代码从底层复现并验证了：
1. **KIVI 键值非对称分组误差对比**：在含持续通道离群值的 Key 与含 Token 基线突变的 Value 上，对比 `per_channel` 与 `per_token` 2-bit 量化的重构均方误差（MSE）；
2. **KIVI 流式残差缓存窗口（`LlamaFlashAttention_KIVI`）状态机**：精确模拟逐 Token 解码中 Key 的分组对齐整块刷盘（每满 $R$ 步触发）与 Value 的 FIFO 逐 Token 弹出刷盘（超出 $R$ 后每步触发）；
3. **KVQuant Pre-RoPE vs Post-RoPE 量化与正交保范定理**：证明 RoPE 旋转后的通道混叠如何令 Post-RoPE Per-Channel 量化误差激增百倍，以及 Pre-RoPE 量化后在线旋转的误差恒等性；
4. **KVQuant 1% 稠密-稀疏隔离 + 中位数重定中心 + 2-bit NUQ + Q-Norm 矩校准**：验证稀疏离群值剥离与 Q-Norm 方差恢复的递进降噪收益。

```python
import math
from typing import Dict, List, Tuple


def affine_group_quant_mse(
    mat: List[List[float]], group_size: int, bits: int, axis: str
) -> Tuple[List[List[float]], float]:
    """
    对形状为 [T, D] 的矩阵按指定维度执行分组非对称 Min-Max 量化:
      - axis == 'per_channel': 沿 Token 维 T 分组 (每组 [G, 1], 同通道共享 scale/mn)
      - axis == 'per_token':   沿通道维 D 分组 (每组 [1, G], 同 Token 共享 scale/mn)
    严格对齐 jy-yuan/KIVI (quant/new_pack.py):
      scale = (mx - mn) / (2^bits - 1), q = clamp(round((x - mn) / scale), 0, 2^bits - 1)
    """
    T = len(mat)
    D = len(mat[0])
    max_int = (1 << bits) - 1
    recon = [[0.0] * D for _ in range(T)]

    if axis == "per_channel":
        assert T % group_size == 0, "Per-channel grouping requires T % group_size == 0"
        for c in range(D):
            for g_start in range(0, T, group_size):
                grp = [mat[t][c] for t in range(g_start, g_start + group_size)]
                mn, mx = min(grp), max(grp)
                scale = (mx - mn) / max_int if mx > mn else 1.0
                for offset, x in enumerate(grp):
                    q = max(0, min(max_int, int(round((x - mn) / scale)))) if mx > mn else 0
                    recon[g_start + offset][c] = q * scale + mn
    elif axis == "per_token":
        assert D % group_size == 0, "Per-token grouping requires D % group_size == 0"
        for t in range(T):
            for g_start in range(0, D, group_size):
                grp = mat[t][g_start : g_start + group_size]
                mn, mx = min(grp), max(grp)
                scale = (mx - mn) / max_int if mx > mn else 1.0
                for offset, x in enumerate(grp):
                    q = max(0, min(max_int, int(round((x - mn) / scale)))) if mx > mn else 0
                    recon[t][g_start + offset] = q * scale + mn
    else:
        raise ValueError(f"Unknown axis: {axis}")

    mse = sum(
        (mat[t][c] - recon[t][c]) ** 2 for t in range(T) for c in range(D)
    ) / (T * D)
    return recon, mse


def simulate_kivi_streaming_residual_cache(
    K_stream: List[List[float]],
    V_stream: List[List[float]],
    group_size: int = 4,
    residual_length: int = 8,
    bits: int = 2,
) -> Dict[str, object]:
    """
    严格对齐 jy-yuan/KIVI (models/llama_kivi.py::LlamaFlashAttention_KIVI):
    模拟逐 Token 解码流中 Key 与 Value 残差缓冲区的异构刷盘生命周期:
      - Key Cache (Per-Channel): 累积到 key_full 长度 == residual_length 时整块转置刷盘并清空 key_full
      - Value Cache (Per-Token): 每次追加后若 value_full 长度 > residual_length, 立即弹出最老 1 个 Token 量化
    """
    assert residual_length % group_size == 0
    k_quant_groups: List[List[List[float]]] = []
    k_full: List[List[float]] = []
    v_quant_tokens: List[List[float]] = []
    v_full: List[List[float]] = []

    k_flush_steps: List[int] = []
    v_flush_steps: List[int] = []

    for step, (k_tok, v_tok) in enumerate(zip(K_stream, V_stream), start=1):
        # 1. Key 流式更新: 先进入 FP16 残差池, 满 R 时整块按 Per-Channel 量化并清空
        k_full.append(k_tok)
        if len(k_full) == residual_length:
            k_recon_blk, _ = affine_group_quant_mse(
                k_full, group_size=group_size, bits=bits, axis="per_channel"
            )
            k_quant_groups.append(k_recon_blk)
            k_full = []
            k_flush_steps.append(step)

        # 2. Value 流式更新: 先进入 FP16 残差池, 超出 R 时弹出最老 1 个 Token 按 Per-Token 量化
        v_full.append(v_tok)
        if len(v_full) > residual_length:
            oldest_v = [v_full.pop(0)]
            v_recon_tok, _ = affine_group_quant_mse(
                oldest_v, group_size=group_size, bits=bits, axis="per_token"
            )
            v_quant_tokens.append(v_recon_tok[0])
            v_flush_steps.append(step)

    return {
        "k_quant_blocks": len(k_quant_groups),
        "k_full_remaining": len(k_full),
        "v_quant_count": len(v_quant_tokens),
        "v_full_remaining": len(v_full),
        "k_flush_steps": k_flush_steps,
        "v_flush_steps_head": v_flush_steps[:3],
    }


def apply_rope_2d_pairs(vec: List[float], pos: int, theta_base: float = 10000.0) -> List[float]:
    """对偶数维向量应用标准二维旋转位置编码 RoPE"""
    d = len(vec)
    out = [0.0] * d
    for i in range(0, d, 2):
        freq = 1.0 / (theta_base ** (i / d))
        angle = pos * freq
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        x0, x1 = vec[i], vec[i + 1]
        out[i] = x0 * cos_a - x1 * sin_a
        out[i + 1] = x0 * sin_a + x1 * cos_a
    return out


def compare_pre_rope_vs_post_rope_key_quant(
    K_pre: List[List[float]], group_size: int = 4, bits: int = 2
) -> Dict[str, float]:
    """
    对齐 SqueezeAILab/KVQuant:
    对比 Post-RoPE (旋转后按通道量化) 与 Pre-RoPE (旋转前按通道量化, 读取时再施加 RoPE) 的重构 MSE。
    在 K_pre 中通道 0 具有恒定显著幅值 (~12.0), 伙伴通道 1 为小幅值噪声 (~0.2)。
    旋转后通道 0 与通道 1 发生正余弦混叠, 破坏通道跨位置的平稳性。
    """
    T = len(K_pre)
    D = len(K_pre[0])
    K_post_true = [apply_rope_2d_pairs(K_pre[t], pos=t) for t in range(T)]

    # 方案 A (Post-RoPE 量化): 直接对旋转后的 K_post_true 做 Per-Channel 量化
    _, mse_post_rope = affine_group_quant_mse(
        K_post_true, group_size=group_size, bits=bits, axis="per_channel"
    )

    # 方案 B (KVQuant Pre-RoPE 量化): 先对平稳的 K_pre 做 Per-Channel 量化, 再施加正交旋转 RoPE
    K_pre_recon, mse_pre_raw = affine_group_quant_mse(
        K_pre, group_size=group_size, bits=bits, axis="per_channel"
    )
    K_pre_then_rope = [apply_rope_2d_pairs(K_pre_recon[t], pos=t) for t in range(T)]
    mse_pre_rope = sum(
        (K_post_true[t][c] - K_pre_then_rope[t][c]) ** 2 for t in range(T) for c in range(D)
    ) / (T * D)

    return {
        "mse_post_rope": mse_post_rope,
        "mse_pre_rope": mse_pre_rope,
        "mse_pre_raw": mse_pre_raw,
        "error_reduction_ratio": mse_post_rope / mse_pre_rope,
    }


def dense_and_sparse_qnorm_quant(
    vec: List[float], lut: List[float], outlier_ratio: float = 0.125
) -> Dict[str, float]:
    """
    严格对齐 SqueezeAILab/KVQuant (simquant_module_quantizer.py::quant_fn_nuq_recon + SimQuant.quantize):
    1. 隔离两端极端离群值 (Dense-and-Sparse), 用中位数替换离群位置后再计算内点区间 [min, max]
    2. 将内点归一化到 [-1, 1] 并查表映射到最近邻非均匀质心 LUT
    3. 执行 Q-Norm 矩匹配校准: normscale = stdev_inlier / stdev_q, normoffset = m_inlier - m_q * normscale
    """
    n = len(vec)
    k_half = max(1, int(round(n * outlier_ratio / 2.0)))
    indexed = sorted(enumerate(vec), key=lambda x: x[1])
    outlier_idx = {idx for idx, _ in indexed[:k_half]} | {idx for idx, _ in indexed[-k_half:]}

    # 1. Naive 非稀疏量化 (被极端离群值撑爆动态范围)
    mn_naive, mx_naive = min(vec), max(vec)
    off_naive, rng_naive = (mx_naive + mn_naive) / 2.0, (mx_naive - mn_naive) / 2.0
    recon_naive = []
    for x in vec:
        x_norm = (x - off_naive) / rng_naive
        q_c = min(lut, key=lambda c: abs(x_norm - c))
        recon_naive.append(q_c * rng_naive + off_naive)
    mse_naive = sum((a - b) ** 2 for a, b in zip(vec, recon_naive)) / n

    # 2. KVQuant Dense-and-Sparse + Q-Norm
    sorted_vals = [v for _, v in indexed]
    median_val = sorted_vals[n // 2]
    trimmed = [median_val if i in outlier_idx else vec[i] for i in range(n)]
    mn_in, mx_in = min(trimmed), max(trimmed)
    off_in, rng_in = (mx_in + mn_in) / 2.0, (mx_in - mn_in) / 2.0

    inlier_indices = [i for i in range(n) if i not in outlier_idx]
    aug_inliers = [(vec[i] - off_in) / rng_in for i in inlier_indices]
    q_inliers = [min(lut, key=lambda c: abs(a - c)) for a in aug_inliers]

    m1 = sum(aug_inliers) / len(aug_inliers)
    std1 = math.sqrt(sum((a - m1) ** 2 for a in aug_inliers) / len(aug_inliers))
    m2 = sum(q_inliers) / len(q_inliers)
    std2 = math.sqrt(sum((q - m2) ** 2 for q in q_inliers) / len(q_inliers))
    normscale = std1 / std2
    normoffset = -m2 * normscale + m1

    recon_sparse_no_qnorm = [0.0] * n
    recon_sparse_qnorm = [0.0] * n
    for i in range(n):
        if i in outlier_idx:
            # 稀疏分支: FP16 精确保留离群值
            recon_sparse_no_qnorm[i] = vec[i]
            recon_sparse_qnorm[i] = vec[i]
        else:
            a = (vec[i] - off_in) / rng_in
            q_c = min(lut, key=lambda c: abs(a - c))
            recon_sparse_no_qnorm[i] = q_c * rng_in + off_in
            q_cal = q_c * normscale + normoffset
            recon_sparse_qnorm[i] = q_cal * rng_in + off_in

    mse_sparse_no_qnorm = sum((a - b) ** 2 for a, b in zip(vec, recon_sparse_no_qnorm)) / n
    mse_sparse_qnorm = sum((a - b) ** 2 for a, b in zip(vec, recon_sparse_qnorm)) / n
    return {
        "mse_naive": mse_naive,
        "mse_sparse_no_qnorm": mse_sparse_no_qnorm,
        "mse_sparse_qnorm": mse_sparse_qnorm,
        "normscale": normscale,
        "normoffset": normoffset,
    }


# --- 执行验证与断言 ---
# 1. 构造具有典型异构特征的 Key [T=8, D=8] 与 Value [T=8, D=8]
# Key: 通道 0 和 4 是跨所有 Token 恒定偏高的离群通道 (~18.0 和 ~-14.0)
K_mat = [
    [
        18.0 + 0.08 * (t % 3) if c == 0 else (-14.0 - 0.08 * (t % 2) if c == 4 else 0.45 * math.cos(t * 0.7 + c * 1.1))
        for c in range(8)
    ]
    for t in range(8)
]
# Value: 无固定离群通道, 但不同 Token 间基线偏移剧烈变化, 同 Token 内各通道波动平缓
token_offsets = [12.0, -8.5, 6.2, -11.0, 9.5, -7.0, 10.5, -9.2]
V_mat = [
    [token_offsets[t] + 0.35 * math.sin(t * 1.3 + c * 0.8) for c in range(8)]
    for t in range(8)
]

_, k_mse_per_channel = affine_group_quant_mse(K_mat, group_size=4, bits=2, axis="per_channel")
_, k_mse_per_token = affine_group_quant_mse(K_mat, group_size=4, bits=2, axis="per_token")
_, v_mse_per_channel = affine_group_quant_mse(V_mat, group_size=4, bits=2, axis="per_channel")
_, v_mse_per_token = affine_group_quant_mse(V_mat, group_size=4, bits=2, axis="per_token")

# 验证 KIVI 核心发现: Key 按通道量化远优于按 Token 量化; Value 按 Token 量化远优于按通道量化
assert k_mse_per_channel < k_mse_per_token * 0.02
assert v_mse_per_token < v_mse_per_channel * 0.01

# 2. 验证 KIVI 流式残差窗口 (T=18 步, G=4, R=8)
K_stream_18 = [K_mat[t % 8] for t in range(18)]
V_stream_18 = [V_mat[t % 8] for t in range(18)]
stream_res = simulate_kivi_streaming_residual_cache(
    K_stream_18, V_stream_18, group_size=4, residual_length=8, bits=2
)
# Key 在 step 8 和 step 16 触发整块刷盘 (共 2 块 = 16 Tokens), 剩余 2 个在 key_full
assert stream_res["k_flush_steps"] == [8, 16]
assert stream_res["k_quant_blocks"] == 2 and stream_res["k_full_remaining"] == 2
# Value 从 step 9 到 step 18 每步弹出 1 个最老 Token 刷盘 (共 10 个), 剩余 8 个满载在 value_full
assert stream_res["v_quant_count"] == 10 and stream_res["v_full_remaining"] == 8
assert stream_res["v_flush_steps_head"] == [9, 10, 11]

# 3. 验证 KVQuant Pre-RoPE vs Post-RoPE 量化误差及旋转正交保范性
rope_res = compare_pre_rope_vs_post_rope_key_quant(K_mat, group_size=4, bits=2)
# 正交旋转不改变欧氏距离: Pre-RoPE 量化后再旋转的 MSE 严格等于旋转前的量化 MSE
assert abs(rope_res["mse_pre_rope"] - rope_res["mse_pre_raw"]) < 1e-12
assert rope_res["error_reduction_ratio"] > 500.0

# 4. 验证 KVQuant Dense-and-Sparse 离群值隔离与 2-bit NUQ + Q-Norm
sample_vec = [
    -14.5, -0.82, -0.55, -0.38, -0.24, -0.15, -0.08, -0.02,
    0.04, 0.11, 0.19, 0.29, 0.44, 0.61, 0.88, 16.2
]
nuq_lut_2bit = [-0.90, -0.25, 0.25, 0.90]
ds_res = dense_and_sparse_qnorm_quant(sample_vec, nuq_lut_2bit, outlier_ratio=0.125)
assert ds_res["mse_sparse_no_qnorm"] < ds_res["mse_naive"] * 0.01
assert ds_res["mse_sparse_qnorm"] < ds_res["mse_sparse_no_qnorm"]

print(
    f"1. KIVI Asymmetry (2-bit, G=4): K_MSE(per_ch={k_mse_per_channel:.5f} vs per_tok={k_mse_per_token:.3f}); "
    f"V_MSE(per_tok={v_mse_per_token:.5f} vs per_ch={v_mse_per_channel:.3f})"
)
print(
    f"2. Streaming Residual (T=18, R=8): K_flushes={stream_res['k_flush_steps']} (rem={stream_res['k_full_remaining']}), "
    f"V_quant={stream_res['v_quant_count']} (rem={stream_res['v_full_remaining']})"
)
print(
    f"3. Pre-RoPE vs Post-RoPE Key Quant: PostRoPE_MSE={rope_res['mse_post_rope']:.4f}, "
    f"PreRoPE_MSE={rope_res['mse_pre_rope']:.5f} ({rope_res['error_reduction_ratio']:.1f}x lower error)"
)
print(
    f"4. Dense-and-Sparse + Q-Norm: Naive_MSE={ds_res['mse_naive']:.3f} -> "
    f"Sparse_MSE={ds_res['mse_sparse_no_qnorm']:.5f} -> QNorm_MSE={ds_res['mse_sparse_qnorm']:.5f}"
)
print("All KIVI and KVQuant 2-bit KV cache quantization assertions passed!")
```

实际运行输出：

```text
1. KIVI Asymmetry (2-bit, G=4): K_MSE(per_ch=0.00138 vs per_tok=0.109); V_MSE(per_tok=0.00102 vs per_ch=2.058)
2. Streaming Residual (T=18, R=8): K_flushes=[8, 16] (rem=2), V_quant=10 (rem=8)
3. Pre-RoPE vs Post-RoPE Key Quant: PostRoPE_MSE=1.1117, PreRoPE_MSE=0.00138 (805.5x lower error)
4. Dense-and-Sparse + Q-Norm: Naive_MSE=8.362 -> Sparse_MSE=0.01661 -> QNorm_MSE=0.01613
All KIVI and KVQuant 2-bit KV cache quantization assertions passed!
```

---

## 延伸 / 追问

**追问 1：请精确核算 KIVI（2-bit，$G=32$，$R=128$）与 KVQuant（2-bit NUQ + 1% Sparse）在长序列下的真实有效位宽（Effective Bits per Element）与压缩比——为什么 2-bit KV 量化在真实系统中的显存压缩比不是理论上的 $16 / 2 = 8.0\times$？**
1. **KIVI-2bit 的元数据与残差窗口摊薄开销**：
   - 在已量化区域，每 $G=32$ 个元素（占 $32 \times 2 = 64\text{ bits}$）需要额外存储 $1$ 个 FP16 的缩放因子 `scale`（$16\text{ bits}$）与 $1$ 个 FP16 的零点 `mn`（$16\text{ bits}$），合共 $32\text{ bits}$ 元数据开销。因此，仅量化区的单元素有效位宽为：
     $$b_{\text{eff, quant}} = 2 + \frac{16 + 16}{32} = 3.0\text{ bits/element} \quad \implies \quad \text{理论渐近压缩比} = \frac{16}{3.0} \approx 5.33\times$$
     （若 `scale`/`mn` 存为 FP8 或 $G=64$，则有效位宽为 $2.5\text{ bits}$，渐近压缩比为 $6.40\times$）。
   - 若计入尾部尚未刷盘的 FP16 残差窗口（平均长度为 $R = 128$ 个 Token），对于总长 $T$ 的序列，实际压缩比为 $\frac{16 T}{3.0 (T - R) + 16 R}$。例如当 $T=2048, R=128$ 时，整体压缩比约为 $4.19\times$；当 $T \le 128$ 时，所有 Token 都留在残差窗口中，实际压缩比为 $1.0\times$！
2. **KVQuant-2bit 的稀疏索引与查找表开销**：
   - KVQuant 按通道共享 Key 的缩放因子（摊薄至 $T \gg 1000$ 时接近 $0\text{ bit}$），对 Value 每个 Token 存 1 个 FP16 缩放与偏移（摊薄到 $D_{\text{model}}=4096$ 个通道仅占 $32 / 4096 \approx 0.008\text{ bits}$）；
   - 其主要额外开销来自 **$1\%$ 稀疏离群值**：每个离群点需要存储 $1$ 个 FP16 数值（$16\text{ bits}$）和 $1$ 个 16-bit 坐标索引（CSR `col_indices`，约 $16\text{ bits}$），折合到每个普通元素增加 $1\% \times (16 + 16) = 0.32\text{ bits}$。因此有效位宽约为 $2.32\text{ bits}$，整体压缩比可达 $16 / 2.32 \approx 6.89\times$。

**追问 2：在 vLLM / SGLang 等采用 PagedAttention 的生产引擎中，集成 KIVI 或 Pre-RoPE KVQuant 会遇到哪些块表（Block Table）对齐与 Prefix Caching 冲突？该如何设计？**
1. **KIVI 分组大小 $G$ 与物理页大小 `block_size` 的耦合**：
   - 在 PagedAttention 中，KV Cache 被切分为离散的物理块（如 `block_size = 16` 或 `32` Tokens）。由于 KIVI 的 Key Cache 需要沿 Token 维每 $G$ 个连续 Token 共享一套 `(scale, mn)` 并打包进同一个 `int32`（16 个 2-bit 元素恰好填满 1 个 `int32`），工程上必须将物理页大小设为 **`block_size` 是 $\max(G, 16)$ 的整数倍（如 `block_size = 32` 且 $G = 32$）**！
   - 这样，当一个物理页被写满并脱离残差窗口时，刚好触发一次页内自包含的 Per-Channel 量化打包，不会出现同一个 `int32` 打包字横跨两个非连续物理页的情况。
2. **Pre-RoPE 缓存对 Prefix Caching 与上下文复用的天然增益**：
   - 在传统 Post-RoPE PagedAttention 中，缓存的 Key 已经焊死了绝对位置编码 $\mathbf{R}(t\theta)$，一旦长对话发生历史滑窗截断（如 StreamingLLM 丢弃中间段）或跨请求复用不同偏移的段落，原本必须重算 Key Projection。而 KVQuant 缓存的是**位置无关的 Pre-RoPE Key**，重定位到新位置 $t'$ 时只需在注意力内核中传入新的位置偏移 $t'$ 动态计算 $\cos(t'\theta), \sin(t'\theta)$，天然支持零重算的键值位置平移！

**追问 3：除了 KIVI 的“按通道分组”和 KVQuant 的“Pre-RoPE + 稀疏剥离”，还有没有办法把 Key 的通道离群值直接抹平，从而让 Key 也能像 Value 一样做简单的 Per-Token 量化（如 QuaRot / QoQ / SKVQ）？**
有！这正是后续 **QuaRot**（Ashkboos et al., 2024）、**QServe/QoQ** 与 **SKVQ**（Duanmu et al., COLM 2024）的演进方向：
- **Hadamard 随机正交旋转（QuaRot）**：在 RoPE 之后（或对 $W_Q, W_K$），同时对 Query 和 Key 右乘一个分块快速 Walsh-Hadamard 正交变换矩阵 $\mathbf{H}$（满足 $\mathbf{H}\mathbf{H}^\top = \mathbf{I}$，可在 $O(D \log D)$ 时间内无乘法完成）：
  $$\mathbf{q}_t' \left(\mathbf{k}_j'\right)^\top = (\mathbf{q}_t \mathbf{H}) (\mathbf{k}_j \mathbf{H})^\top = \mathbf{q}_t (\mathbf{H}\mathbf{H}^\top) \mathbf{k}_j^\top = \mathbf{q}_t \mathbf{k}_j^\top$$
  Hadamard 变换会将少数离群通道的尖峰能量均匀摊平到所有 $D$ 个通道中，使旋转后的 Key 近似服从各向同性高斯分布，从而允许 Key 直接使用硬件友好的 Per-Token 量化，免去了 KIVI 复杂的残差转置刷盘逻辑。
- **通道重排与裁剪（SKVQ）**：离线统计各通道的动态范围后，将幅度相近的 Key 通道置换重排（Channel Reordering）到同一个通道组 `[1, G]` 内，并把同样的置换矩阵融合进 Query 投影权重中，同样能用 Per-Token 分组实现高精度的 2-bit Key 压缩。

---

## 常见误区

- **误区一：“KIVI 的 Key 按通道量化可以在自回归 Decode 时每生成 1 个新 Token 就立即按通道量化追加到 2-bit 缓存中。”**
  事实：**如果每生成 1 个 Token 就单独对它做一次 Per-Channel 量化，整个算法会彻底失效！** 因为单步新生成的 Key 形状为 `[1, D]`，沿 Token 维切分出的每个通道组里只有 $1$ 个标量元素，此时组内最大值恒等于最小值（$\max = \min$），不仅算出的量化值全为 $0$、真实值全部退化保存在 FP16 零点 `mn` 中（毫无压缩效果），而且每个 Token 都要额外存一套 FP16 的 `(scale, mn)`。这正是 VeloxQuant-MLX Issue #162 曾踩过的真实工程陷阱。正确做法必须遵循 KIVI Algorithm 1：新 Token 先以 FP16 存入 `key_states_full` 残差窗口，攒满 `residual_length`（如 $128 = 4 \times 32$）个 Token 后，才一次性切分为 $G=32$ 的通道组批量量化打包。
- **误区二：“只要把 KV Cache 量化成 2-bit，无论在什么算子实现下都能立刻降低运行时峰值显存（Peak Memory）并带来 $4\times$ 以上的推理加速。”**
  事实：**存储压缩（Storage Compression）不等于峰值工作集下降或端到端加速！** 如果框架在计算注意力前先把整段 2-bit 历史 KV Cache 一次性反量化回完整的 FP16 张量 `[B, nh, T, D]` 再送入标准 SDPA / FlashAttention，那么：第一，反量化出的临时 FP16 张量依然会撑起相同的运行时峰值显存；第二，全部 HBM 带宽省下的时间都会被额外的反量化 Kernel 读写抵消。只有编写**融合反量化矩阵向量乘内核（Fused Dequantization-GEMV / FlashAttention Kernel，如 KIVI 的 `cuda_bmm_fA_qB_outer` 与 KVQuant 的 `vecquant2matmul_..._fused`）**，将 2-bit 打包字从 HBM 直接读入 GPU 寄存器并在寄存器内即时反量化点积，才能真正兑现峰值显存削减与访存加速。
- **误区三：“KVQuant 的 Pre-RoPE Key 量化之所以更准，是因为旋转前 Key 向量里没有离群值。”**
  事实：**恰恰相反，旋转前的 Key 向量里依然存在幅度高达 $10\times$ 以上的显著离群值！** 但旋转前（Pre-RoPE）的离群值**牢牢固定在少数几个特定通道上，且同一通道跨不同 Token 位置的数值极其平稳（方差极小）**，因此非常适合 Per-Channel 量化；而一旦施加了位置相关的 RoPE 旋转矩阵 $\mathbf{R}(t\theta_m)$，高幅值离群通道就会随位置 $t$ 以 $\cos(t\theta_m)$ 和 $\sin(t\theta_m)$ 的规律发生正负剧烈震荡，并把大振幅混叠传染给原本平缓的配对通道，从而摧毁了 Per-Channel 量化的静态通道假设。

---

## 参考

- 选题线索：[huggingface/blog (`zh/kv-cache-quantization.md`)](https://github.com/huggingface/blog/blob/2edbebbfa0cfc5d37bf66fd2d46899f26f815575/zh/kv-cache-quantization.md)（固定 commit `2edbebbfa`）与 [rajveer43/VeloxQuant-MLX (`docs-site/docs/algorithms/kivi.md`)](https://github.com/rajveer43/VeloxQuant-MLX/blob/7b1bc180df83038a2e165f473ca36261ca80e4d8/docs-site/docs/algorithms/kivi.md)（固定 commit `7b1bc18`），独立重构拓展。
- Liu et al., [KIVI: A Tuning-Free Asymmetric 2bit Quantization for KV Cache](https://arxiv.org/abs/2402.02750)，ICML 2024，及官方源码 [jy-yuan/KIVI (`models/llama_kivi.py` & `quant/new_pack.py`)](https://github.com/jy-yuan/KIVI/blob/876b4d2d08e3b1d5f70d0969c299d8c7c42ddfb6/models/llama_kivi.py)（固定 commit `876b4d2`）：Key 按通道与 Value 按 Token 非对称 2-bit 量化、32-bit 整型位打包及 `residual_length` 分组对齐流式残差窗口实现。
- Hooper et al., [KVQuant: Towards 10 Million Context Length LLM Inference with KV Cache Quantization](https://arxiv.org/abs/2401.18079)，NeurIPS 2024，及官方源码 [SqueezeAILab/KVQuant (`benchmarking/kvquant/simquant_module_quantizer.py` & `deployment/transformers/src/transformers/models/llama/modeling_llama.py`)](https://github.com/SqueezeAILab/KVQuant/blob/57a238357f0ffe50084670fcd5781c9848f80ea2/benchmarking/kvquant/simquant_module_quantizer.py)（固定 commit `57a2383`）：Pre-RoPE 按通道 Key 量化、Fisher 敏感度加权非均匀码本（NUQ）、1% 稠密-稀疏离群值隔离、`first_few_fp16` 首词保护与 Q-Norm 校准。
- Xiao et al., [Efficient Streaming Language Models with Attention Sinks](https://arxiv.org/abs/2309.17453)，ICLR 2024：Attention Sink 现象与首词高幅值激活机制。
- Ashkboos et al., [QuaRot: Outlier-Free 4-Bit Inference in Rotated LLMs](https://arxiv.org/abs/2404.00456)，NeurIPS 2024：基于 Hadamard 正交旋转抹平 Key 通道离群值的对比方案。

来源访问与示例核验日期：**2026-11-10**。仅执行标准库下非对称分组量化、流式残差窗口状态机、Pre-RoPE 正交旋转误差与稠密-稀疏 Q-Norm 数值验证，未运行多卡 GPU 百万上下文实机推理压测。
