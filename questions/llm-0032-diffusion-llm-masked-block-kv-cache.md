---
id: llm-0032
title: 掩码扩散语言模型（Masked Diffusion LLM）是如何通过双向迭代去噪并行生成文本的，Block Diffusion 与 Fast-dLLM 如何解决 KV Cache 复用与并行解码联合分布失配？
category: llm
tags: [diffusion-llm, masked-diffusion, llada, block-diffusion, kv-cache, parallel-decoding]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开 AI 系统设计指南与面试题库扩展改编；MDLM、LLaDA、BD3-LMs、Fast-dLLM 原论文及官方源码核实（见参考）
status: published
updated: 2026-11-03
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-11-03
    updated: 2026-11-03
---

## 问题

长期以来，大语言模型（LLM）几乎等同于从左到右逐 Token 生成的自回归模型（Autoregressive Model, ARM）。然而，每次前向传播仅产出 1 个 Token 的串行依赖使其在解码阶段受限于显存带宽（Memory-Bandwidth Bound）。近年来，以 **MDLM**、**LLaDA**、**BD3-LMs（Block Diffusion）** 与 **Fast-dLLM** 为代表的**掩码扩散语言模型（Masked Diffusion Language Models, dLLMs）** 将图像领域的迭代去噪思想引入离散文本空间，在代码补全、多区域编辑及高吞吐推理（乃至作为自回归模型的并行投机草稿器）中展现出独特优势。

然而，若直接在工业界部署朴素的全序列掩码扩散模型，往往会发现其实际吞吐反而不如经过深度 KV Cache 优化的自回归模型，且一次解掩码过多 Token 会导致局部语法崩塌。请深入剖析：
1. 离散掩码扩散语言模型（如 MDLM / LLaDA）的前向加噪与反向去噪过程是如何定义的？为什么它的训练目标是一个带 **$1/t$ 重要度权重的变分下界（ELBO）**，而不是 BERT 固定 $15\%$ 掩码率的掩码语言模型（MLM）损失？
2. 为什么纯双向注意力的全序列扩散模型在推理时**天然无法复用 KV Cache**，且受困于固定生成长度与 `<EOS>` 坍缩？**分块扩散（Block Diffusion / BD3-LMs）** 与 **Fast-dLLM 的前缀/双缓存（PrefixCache / DualCache）** 是如何恢复 KV Cache 复用与可变长生成能力的？
3. 在反向去噪单步同时解掩码（Unmask）多个 Token 时，为什么会出现**“边际置信度都很高、但组合起来却语法矛盾”**的联合分布失配？如何通过低置信度重掩码（Low-Confidence Remasking）、置信度阈值并行解码（Confidence-Aware Parallel Decoding）或“扩散草稿 + 自回归验证”混合架构兼顾吞吐与生成质量？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-11-03

**掩码扩散语言模型（Masked Diffusion LLM）将离散文本生成建模为“从全 `[MASK]` 序列出发的多步迭代去噪过程”：前向过程以连续噪声率 $t \in (0, 1]$ 独立将干净序列 $x_0$ 中的每个 Token 替换为吸收态 `[MASK]`；反向过程利用去除了因果掩码的双向 Transformer 掩码预测器 $p_\theta(x_0 \mid x_t)$，通过在全时间步 $t \sim \mathcal{U}(0, 1]$ 上对被掩码位置的交叉熵施加 $1/t$ 加权积分，优化真实对数似然 $\log p_\theta(x_0)$ 的严格变分下界（ELBO）。针对纯双向扩散“每步解掩码都会改变全局上下文导致 KV Cache 失效”与“独立并行采样破坏 Token 间联合依赖”两大工程瓶颈，现代系统通过分块半自回归架构（Block Diffusion / BD3-LMs，块间因果缓存 KV、块内双向扩散）或分块近似双缓存（Fast-dLLM DualCache，冻结已提交前缀与未来全掩码块的 KV 激活）消除冗余重算，并配合置信度阈值解掩码（仅提交 $c^{(i)} \ge \tau$ 的确定性位置，其余重掩码推迟）或将其作为自回归大模型的并行投机草稿器（Block-Diffusion Drafter），在保留双向规划与并行吐词优势的同时守住生成质量底线。**

现有 [llm-0008](llm-0008-next-token-training-inference.md) 与 [llm-0010](llm-0010-causal-attention-architecture.md) 剖析了传统自回归（AR）模型的因果注意力掩码与逐 Token 生成机制，[llm-0018](llm-0018-kv-cache-prefill-decode.md) 拆解了自回归 Prefill/Decode 两阶段的 KV Cache 访存特性，[llm-0006](llm-0006-speculative-decoding.md) 讨论了基于无损拒绝采样的投机解码加速，[llm-0012](llm-0012-decoding-sampling-beam.md) 与 [llm-0031](llm-0031-constrained-decoding-fsm-pda-xgrammar.md) 则覆盖了采样分布变换与形式文法约束。本题聚焦**非自回归的离散掩码扩散语言模型范式：连续时间 ELBO 中的 $1/t$ 掩码加权推导、BD3-LM 与 Fast-dLLM 的分块 KV 缓存机制，以及多 Token 并行解掩码下的条件独立性陷阱与工程解法**。

---

### 1. 吸收态离散扩散与 $1/t$ 加权变分下界（ELBO）推导

#### 为什么不能直接在离散 Token 空间加高斯噪声？
在图像生成（DDPM）中，像素是连续实数，前向过程可以直接叠加高斯噪声 $x_t = \sqrt{\bar{\alpha}_t} x_0 + \sqrt{1 - \bar{\alpha}_t}\epsilon$。然而自然语言由离散词表 $V$ 中的 Token ID 组成，ID 之间的数值大小没有任何几何语义。早期研究尝试将 Token 映射到连续 Embedding 空间加高斯噪声（如 Diffusion-LM），但面临高维空间舍入回离散词表（Rounding）误差大、似然下界松散、难以扩展到十亿级参数等局限。

**MDLM（Sahoo et al., NeurIPS 2024）** 与 **LLaDA（Nie et al., 2025）** 证明：在离散词表 $V$ 中引入一个专门的吸收态（Absorbing State）掩码符号 $\texttt{[MASK]} \notin V$，直接在离散状态空间定义**前向掩码吸收过程（Forward Masking Process）**，既避免了连续嵌入空间的投影损耗，又能导出极其简洁的变分下界。

#### 前向掩码过程与反向含参去噪
设干净文本序列为 $x_0 = (x_0^{(1)}, x_0^{(2)}, \dots, x_0^{(L)}) \in V^L$。在连续时间步 $t \in [0, 1]$ 下，前向过程对序列中的每个位置 $i \in \{1, \dots, L\}$ 独立以概率 $t$（线性掩码调度，工程实现常取 $p_{\text{mask}}(t) = (1 - \epsilon)t + \epsilon,\ \epsilon = 10^{-3}$）替换为 $\texttt{[MASK]}$，以概率 $1 - t$ 保持原 Token $x_0^{(i)}$ 不变：

$$q(x_t^{(i)} \mid x_0^{(i)}) = \begin{cases} 1 - t, & \text{if } x_t^{(i)} = x_0^{(i)} \\ t, & \text{if } x_t^{(i)} = \texttt{[MASK]} \end{cases}$$

当 $t = 0$ 时序列完全干净；当 $t = 1$ 时序列退化为全掩码序列 $(\texttt{[MASK]}, \dots, \texttt{[MASK]})$。

反向生成过程从 $t = 1$ 向 $t = 0$ 推进。对于任意 $0 \le s < t \le 1$，已知真实 $x_0$ 时的精确反向转移后验分布 $q(x_s^{(i)} \mid x_t^{(i)}, x_0)$ 满足：
- **若位置 $i$ 在时刻 $t$ 已经解掩码（$x_t^{(i)} \neq \texttt{[MASK]}$）**：吸收态逆过程不可逆转已揭示的字符，故 $x_s^{(i)} = x_t^{(i)}$（概率为 $1$）；
- **若位置 $i$ 在时刻 $t$ 仍为掩码（$x_t^{(i)} = \texttt{[MASK]}$）**：它在更早时刻 $s$ 有 $\frac{s}{t}$ 的概率继续保持为 $\texttt{[MASK]}$，有 $\frac{t - s}{t}$ 的概率恢复为真实 Token $x_0^{(i)}$。

由于推理时未知真实 $x_0$，我们训练一个移除了因果掩码的**双向 Transformer 掩码预测器（Mask Predictor）** $p_\theta(x_0^{(i)} \mid x_t)$，用模型预测分布替代后验中的真实 $x_0^{(i)}$。

#### 为什么训练损失必须除以掩码率 $t$？与 BERT MLM 有何本质区别？
根据连续时间离散扩散的 Rao-Blackwell 化变分推导（Sahoo et al., 2024; Nie et al., 2025），模型对干净序列负对数似然 $-\log p_\theta(x_0)$ 的变分上界（Negative ELBO）可严格化简为在 $t \sim \mathcal{U}[0, 1]$ 上的期望积分：

$$\mathcal{L}_{\text{NELBO}}(\theta) = \mathbb{E}_{t \sim \mathcal{U}(0, 1)} \mathbb{E}_{x_t \sim q(x_t \mid x_0)} \left[ \frac{1}{t} \sum_{i=1}^{L} \mathbf{1}\big[x_t^{(i)} = \texttt{[MASK]}\big] \cdot \left( -\log p_\theta\big(x_0^{(i)} \mid x_t\big) \right) \right] \ge -\log p_\theta(x_0)$$

在指令微调（SFT）阶段，对于提示词与回答拼接序列 $x_0 = [p_0 \parallel r_0]$，前向过程固定提示词区间 $p_0$ 不加噪，仅对长度为 $L_{\text{ans}}$ 的回答区间 $r_0$ 采样掩码并归一化：

$$\mathcal{L}_{\text{SFT}}(\theta) = \mathbb{E}_{t \sim \mathcal{U}(0, 1),\ r_t} \left[ \frac{1}{t \cdot L_{\text{ans}}} \sum_{i=1}^{L_{\text{ans}}} \mathbf{1}\big[r_t^{(i)} = \texttt{[MASK]}\big] \left( -\log p_\theta\big(r_0^{(i)} \mid p_0, r_t\big) \right) \right]$$

| 维度 | 自回归语言模型（AR LLM，如 Llama / GPT） | 经典掩码语言模型（BERT MLM） | 掩码扩散语言模型（MDLM / LLaDA） |
| --- | --- | --- | --- |
| **注意力机制** | 单向因果掩码（Causal Attention，$i$ 仅看 $\le i$） | 双向全注意力（Bidirectional Attention） | 双向全注意力（或块间因果 + 块内双向） |
| **掩码率设定** | 无掩码，固定左到右链式分解 | **固定常数 $p_{\text{mask}} = 15\%$** | **连续随机采样 $t \sim \mathcal{U}(0, 1]$**（覆盖 $0\% \sim 100\%$） |
| **损失函数性质** | 精确对数似然 $\sum_i \log p_\theta(x^{(i)} \mid x^{(<i)})$ | 仅局部去噪伪似然，**不构成合法生成分布** | 带 $1/t$ 加权的积分，是真实对数似然的**严格 ELBO** |
| **生成与规划能力** | 严格从左到右，每次前向生成 1 个 Token；存在“逆向诅咒” | 无法从全 `[MASK]` 从头生成连贯长文本 | 支持从全 `[MASK]` 多步并行去噪、任意位置填充（Infilling）与逆序推理 |

**核心数学直觉**：为什么 BERT 不能从全 `[MASK]` 生成文本，而 LLaDA 可以？因为 BERT 只见过 $15\%$ 被掩码的句子，从未见过 $t \to 1$（近乎全掩码）的分布，也从未见过 $t \to 0$（仅剩一两个词待修补）的分布；同时，在 $t$ 很小时，序列中只有极少数（约 $t \cdot L$ 个）Token 被掩码，如果不乘上权重因子 $\frac{1}{t}$，小 $t$ 样本对梯度的贡献会被大 $t$ 样本淹没，$\frac{1}{t}$ 恰好抵消了期望掩码个数 $t \cdot L$ 中的 $t$，保证了全时间轴上梯度尺度的均衡与 ELBO 积分的无偏性。

---

### 2. 为什么纯扩散模型难以复用 KV Cache？Block Diffusion 与 Fast-dLLM 架构拆解

#### 纯双向扩散的三大推理痛点
如 [llm-0018](llm-0018-kv-cache-prefill-decode.md) 所述，自回归模型在 Decode 阶段之所以每次只需计算最新 1 个 Token 的 $Q, K, V$，根本原因在于**因果掩码保证了历史位置 $j < t$ 的隐藏状态绝对不会受未来新生成 Token 的影响**。然而在纯全序列掩码扩散模型（如原版 LLaDA）中：
1. **KV Cache 彻底失效**：由于采用双向全注意力，第 $k$ 步在句尾解掩码了 2 个 Token 后，句首 Prompt 以及所有已解掩码 Token 在每一层的注意力输出都会因为“看到了新揭示的未来词”而发生改变。因此在 $S$ 步去噪循环中，每一步都必须对完整序列长度 $L_{\text{prompt}} + L_{\text{gen}}$ 重新做一次全量 Prefill 级前向计算，单次生成复杂度高达 $\mathcal{O}(S \cdot (L_{\text{prompt}} + L_{\text{gen}})^2)$！
2. **预分配固定长度 $L_{\text{gen}}$ 与 `<EOS>` 长度坍缩**：纯扩散在推理启动前必须预先在显存中铺满固定数量 $L_{\text{gen}}$ 的 $\texttt{[MASK]}$。又因为在 SFT 训练时较短回答的末尾被填充了大量 `<EOS>`，模型在长序列生成早期极易在后半段高置信度地预测出 `<EOS>`，导致回答过早截断（LLaDA 甚至需要提供 `logits_eos_inf` 或 `confidence_eos_eot_inf` 开关来强行压制 `<EOS>` 置信度）。

为彻底解决上述瓶颈，工业界演化出两条核心技术路线：**训练期块级插值（BD3-LMs）**与**推理期近似块缓存（Fast-dLLM）**。

```text
方案 A: Block Diffusion (BD3-LMs, 训练+推理原生支持)
┌─────────────────┬─────────────────┬─────────────────────────┐
│  Block 0 (已定)  │  Block 1 (已定)  │  Block 2 (当前去噪块)    │ ──► 按需追加 Block 3...
│   KV 已冻结缓存   │   KV 已冻结缓存   │ [The] [MASK] [on] [MASK]│     (原生支持可变长生成)
└────────┬────────┴────────┬────────┴────────────▲────────────┘
         └─────────────────┴─────────────────────┘
        块间因果注意力 (Block-Causal) + 块内双向注意力 (Block-Diagonal)

方案 B: Fast-dLLM DualCache (免训练加速全序列双向扩散模型)
┌─────────────────────────┬──────────────────────┬─────────────────────────┐
│  Prefix [0 : s]         │ Current Block [s : e]│ Future Suffix [e : L]   │
│  Prompt + 已完成历史块    │ 正在迭代去噪的当前块   │ 全部仍为 [MASK] 的未来块  │
│  ★ Prefix KV 缓存复用    │ ★ 每步仅送入这 B 个词 │ ★ Suffix KV 缓存复用     │
└─────────────────────────┴──────────────────────┴─────────────────────────┘
  * 每进入新块时做 1 次全长前向刷新全局 KV Cache；块内后续步仅对长度 B 的当前块做前向并原地替换 [s:e] 缓存
```

#### 路线一：Block Diffusion（BD3-LMs，Arriola et al., ICLR 2025 Oral）
BD3-LMs 将长度为 $L$ 的序列划分为 $K = L / B$ 个大小为 $B$ 的块（Block）$\mathbf{x} = (x^{1}, x^{2}, \dots, x^{K})$，在**块间采用自回归链式分解**，在**块内采用离散掩码扩散**：

$$\log p_\theta(\mathbf{x}) = \sum_{b=1}^{K} \log p_\theta\big(x^{b} \mid x^{<b}\big)$$

- **推理端收益**：当第 $b$ 个块完成所有去噪步后，它的 Token 完全确定且不再受后续块 $b' > b$ 影响，因此其 KV Cache 可以像自回归模型一样永久冻结保存；同时无需预先指定总生成长度，只需每次追加一个大小为 $B$ 的 `[MASK]` 块，直到块内生成 `<EOS>` 即可自然停止。当 $B=1$ 时退化为纯自回归模型；当 $B=L$ 时退化为全序列扩散模型。
- **训练端一次前向的高效复合掩码**：如果在训练时对每个块分别采样噪声步并单独前向，计算开销将放大 $K$ 倍。BD3-LMs 将加噪序列 $\mathbf{x}_t$ 与干净序列 $\mathbf{x}_0$ 拼接为长度为 $2L$ 的序列 $[\mathbf{x}_t \parallel \mathbf{x}_0]$，通过由三部分组成的块稀疏注意力掩码（`block_diff_mask`，原生支持 PyTorch `FlexAttention`）在单次前向中完成所有块的训练：
  1. **块对角掩码 $M_{\text{BD}}$（Block-Diagonal）**：同一块内的加噪 Token $\mathbf{x}_t^{b}$ 之间（以及同一块内的干净 Token $\mathbf{x}_0^{b}$ 之间）允许双向互看；
  2. **偏移块因果掩码 $M_{\text{OBC}}$（Offset Block-Causal）**：第 $b$ 块的加噪 Token $\mathbf{x}_t^{b}$ 可以跨序列关注严格更早块 $b' < b$ 的**干净 Token $\mathbf{x}_0^{b'}$**，但绝不能关注同块或未来块的干净 Token $\mathbf{x}_0^{\ge b}$（防止标签泄漏）；
  3. **块因果掩码 $M_{\text{BC}}$（Block-Causal）**：干净序列 $\mathbf{x}_0^{b}$ 仅关注同块及更早块的干净 Token $\mathbf{x}_0^{\le b}$，用于构建无噪条件上下文表示。

#### 路线二：Fast-dLLM 的免训练双缓存（DualCache，Wu et al., 2025）
对于已经用全序列双向注意力训练好的开源模型（如 LLaDA-8B、Dream-7B），没有块因果掩码，能否在不重新训练的前提下启用 KV Cache？

Fast-dLLM 发现：在半自回归分块解码（按块从左到右依次去噪）时，当模型正在迭代去噪第 $b$ 个块（区间 $[s, e)$，长度 $B$）的连续几个时间步内，**位于 $s$ 之前的已确定前缀（Prompt + 已完成块）和位于 $e$ 之后的未来块（全部仍是完全相同的 `[MASK]` Token）在输入层根本没有发生变化**，且相邻去噪步之间它们的隐藏层 KV 特征余弦相似度高达 $0.99$ 以上！
- **PrefixCache**：在进入第 $b$ 块的第 $0$ 步时做一次全长前向并缓存前缀 $[0, s)$ 的 KV；块内后续去噪步只把 $[s, L)$ 作为 Query 送入模型，省去长 Prompt 的重复计算。
- **DualCache（前缀 + 后缀双缓存）**：更进一步，在块首步（Step 0）执行一次全长前向初始化完整序列 $[0, L)$ 的 KV Cache；在该块后续的去噪迭代（Step $1 \dots S_{\text{block}}-1$）中，**同时冻结前缀 $[0, s)$ 与未来全掩码后缀 $[e, L)$ 的 KV Cache**，每次仅将长度为 $B$ 的当前块 `x[:, s:e]` 送入 Transformer，并通过 `replace_position` 掩码原地更新缓存中 `[s:e]` 槽位的 K/V。这使块内每步前向的 Query 长度从 $L_{\text{prompt}} + L_{\text{gen}}$ 骤降至常数 $B$（如 $B=32$），配合并行解码在 LLaDA / Dream 上实测获得最高 **27.6 倍**的吞吐加速而精度几乎无损。

---

### 3. 并行解掩码的条件独立性陷阱与置信度感知调度

#### 为什么一次解掩码太多 Token 会导致“高置信度乱码”？
反向去噪的加速比直接取决于**每次前向传播平均提交（Unmask）的 Token 数量**。如果在长度为 $L_{\text{gen}} = 128$ 的生成中每步只解掩码 1 个 Token，需要 128 次前向（NFE = 128），毫无步数优势；但如果为了追求速度，在单步内同时对 $k$ 个掩码位置独立采样并锁定，就会遭遇经典的**条件独立性破坏（Conditional Independence Breakdown / Curse of Parallel Decoding）**。

原因在于：掩码预测器在单次前向中输出的是每个位置 $i$ 关于当前掩码上下文 $x_t$ 的**边际条件分布（Marginal Distribution）** $p_\theta(x_0^{(i)} \mid x_t)$，而不是多个未知位置之间的**联合分布（Joint Distribution）**：

$$\prod_{i \in \mathcal{M}_{\text{transfer}}} p_\theta\big(x_0^{(i)} \mid x_t\big) \neq p_\theta\big(\{x_0^{(i)}\}_{i \in \mathcal{M}_{\text{transfer}}} \mid x_t\big)$$

**直观反例**：假设当前句尾有两个相邻掩码 `"Please head to the [MASK]_1 [MASK]_2"`，训练语料中 `"new car"` 和 `"old house"` 出现频率相当。
- 在位置 1，模型预测 `p("new") = 0.51, p("old") = 0.49`，最高置信度词是 `"new"`；
- 在位置 2，模型预测 `p("house") = 0.51, p("car") = 0.49`，最高置信度词是 `"house"`。
如果贪心同时解掩码这两个位置，就会拼出语义错乱或语料中根本不存在的组合（更典型的是生成 `"high card"` 与 `"credit score"` 交叉拼成 `"high score"` / `"credit card"` 错位，或代码中的变量名首尾不一致）。

#### 三大工程缓解机制
1. **低置信度重掩码（Low-Confidence Remasking，LLaDA）**：
   在第 $t \to s$ 步预测出所有掩码位置的最优候选 $\hat{x}_0^{(i)} = \arg\max_v p_\theta(v \mid x_t^{(i)})$ 及其预测置信度 $c^{(i)} = p_\theta(\hat{x}_0^{(i)} \mid x_t)$ 后，不按随机位置保留，而是按线性调度计算出当前步应转移的配额 $k_t = \lfloor M_t / \text{steps} \rfloor$，**仅锁定置信度排名前 $k_t$ 的位置**，将其余所有低置信度位置重新置回 $\texttt{[MASK]}$ 留待下一轮在更丰富的上下文下重算。
2. **置信度阈值并行解码（Confidence-Aware Parallel Decoding，Fast-dLLM）**：
   固定每步转移 $k_t$ 个 Token 过于僵化——当遇到确定性极高的固定搭配（如 `import numpy as np`）时可以一次解掩码十几个词；当遇到多分支歧义点（如上述名词短语）时则只能先确定一个词以打破对称性。
   Fast-dLLM（Wu et al., 2025, Theorem 1）证明：**当各位置的最大边缘预测概率满足 $c^{(i)} = \max_v p_\theta(v \mid x_t^{(i)}) > 1 - \epsilon$ 且足够接近 $1$ 时，高维联合分布退化为近似单点分布，此时独立并行贪心解码与串行条件解码之间的总变差距离（Total Variation Distance）有紧上界并保证给出完全一致的解**。据此设计动态阈值准则（对应 `v1/llada/generate.py` 中的 `get_transfer_index`）：

   $$\mathcal{I}_{\text{transfer}} = \Big\{ i \in \mathcal{M}_t \;\Big|\; c^{(i)} \ge \tau \Big\} \;\cup\; \Big\{ \arg\max_{i \in \mathcal{M}_t} c^{(i)} \Big\}$$

   即：每步自动解掩码所有置信度大于等于阈值 $\tau$（通常取 $\tau = 0.90$）的掩码位置；若所有掩码位置置信度均低于 $\tau$，则强制保底解掩码置信度最高的 **1 个**位置，确保去噪循环严格收敛不死锁。此外，Fast-dLLM 还提供了动态因子策略（Factor-Based Strategy）：将排序后的第 $n$ 个候选阈值设为 $\tau_n = 1 - \frac{f}{n+1}$，自动根据拟并行提交的 Token 数量 $n$ 收紧置信度要求。
3. **混合架构：扩散模型作并行草稿器 + 自回归模型精确验证（Draft with Diffusion, Verify with AR）**：
   这是 2025–2026 年最具生产价值的落地范式（如 TiDAR、Fast-dLLM v2、以及已合入 vLLM / SGLang / llama.cpp 的 **DFlash / DFlash 2** 块扩散草稿器）。与传统投机解码（[llm-0006](llm-0006-speculative-decoding.md)）中 Draft 模型仍需逐个串行猜 $\gamma$ 个草稿 Token 不同，轻量级块扩散 Drafter 在 **1~2 次前向传播内并行吐出一整块（如 8~16 个）草稿 Token**，随后交由主自回归 Target 模型在单次前向中并行计算精确条件概率并执行拒绝采样验证。该架构既吃到了扩散并行吐词的低延迟红利，又在数学上 $100\%$ 保持了自回归主力模型原本的输出分布与长程推理质量。

---

### 4. 可运行的标准库实现：ELBO $1/t$ 加权、BD3-LM 复合掩码与 DualCache 置信度并行解码

以下 Python 3 标准库代码（零第三方依赖）完整实现并验证了：（1）MDLM / LLaDA 的 $1/p_{\text{mask}}$ 重要度加权损失在不同噪声率 $t$ 下的尺度无偏性；（2）BD3-LMs 拼接序列 $[\mathbf{x}_t \parallel \mathbf{x}_0]$ 的三合一块注意力掩码构建与防标签泄漏校验；（3）Fast-dLLM 置信度阈值并行解码（含保底规则）及 `Naive`、`PrefixCache`、`DualCache` 三种模式的前向步数（NFE）与注意力访存开销对比：

```python
from typing import Dict, List, Set, Tuple
import math


def compute_mdlm_loss_terms(
    log_probs: List[float], mask_flags: List[bool], t: float, eps: float = 1e-3
) -> Tuple[float, float]:
    """
    验证 LLaDA / MDLM 掩码扩散训练目标:
    p_mask = (1 - eps) * t + eps
    仅对被掩码位置计算交叉熵并除以 p_mask，再对序列总长 L 求均值。
    返回: (重要度加权 ELBO 损失, 未除 p_mask 的朴素平均损失)
    """
    assert 0.0 < t <= 1.0 and len(log_probs) == len(mask_flags)
    p_mask = (1.0 - eps) * t + eps
    L = len(log_probs)
    weighted_sum = 0.0
    unweighted_sum = 0.0
    for log_p, is_masked in zip(log_probs, mask_flags):
        if is_masked:
            ce = -log_p
            weighted_sum += ce / p_mask
            unweighted_sum += ce
    return weighted_sum / L, unweighted_sum / L


def build_bd3lm_attention_mask(seq_len: int, block_size: int) -> List[List[int]]:
    """
    复现 BD3-LM (Arriola et al., ICLR 2025) 训练拼接序列 [x_t || x_0] (总长 2*seq_len) 的复合掩码:
    前 seq_len 个位置为加噪序列 x_t (flag=0)，后 seq_len 个位置为干净序列 x_0 (flag=1):
    1. M_BD (Block-Diagonal): 同块且同属 x_t 或同属 x_0
    2. M_OBC (Offset Block-Causal): x_t 的块 b_q 可以关注严格更早块 (b_kv < b_q) 的干净 x_0
    3. M_BC (Block-Causal): x_0 的块 b_q 可以关注同块及更早块 (b_kv <= b_q) 的干净 x_0
    """
    assert seq_len % block_size == 0
    total = 2 * seq_len
    mask = [[0] * total for _ in range(total)]
    for q in range(total):
        x0_q = 1 if q >= seq_len else 0
        blk_q = (q - seq_len) // block_size if x0_q else q // block_size
        for kv in range(total):
            x0_kv = 1 if kv >= seq_len else 0
            blk_kv = (kv - seq_len) // block_size if x0_kv else kv // block_size
            m_bd = (blk_q == blk_kv) and (x0_q == x0_kv)
            m_obc = (blk_q > blk_kv) and (x0_q == 0) and (x0_kv == 1)
            m_bc = (blk_q >= blk_kv) and (x0_q == 1) and (x0_kv == 1)
            if m_bd or m_obc or m_bc:
                mask[q][kv] = 1
    return mask


def simulate_confidence_parallel_decoding(
    step_confidences: List[List[float]],
    prompt_len: int,
    gen_len: int,
    block_size: int,
    threshold: float,
) -> Dict[str, int]:
    """
    对比三种解码策略的总前向步数 (NFE) 与近似 Attention Token 访存开销 (正比于 Q_len * KV_len):
    1. 朴素全序列单步去噪 (Naive Full-Sequence, 无 KV Cache): 每步解掩码 1 个 token，每次前向重算全长 L_p + L_g
    2. 块级置信度并行 + Prefix Cache: 块内对 confidence >= threshold (保底每步最高置信度 1 个) 并行解掩码，
       每块首步重算前缀，后续步仅以 [current_block :] 作为 Q
    3. 块级置信度并行 + DualCache (前缀 + 未来掩码块双缓存): 每块首步刷新全局 KV Cache (1 次全长前向)，
       块内后续迭代仅对当前块 (长度 B) 做前向并原地替换 KV Cache 中对应块区间 [s:e]
    """
    assert gen_len % block_size == 0
    num_blocks = gen_len // block_size
    total_len = prompt_len + gen_len

    # 1. Naive Full-Sequence (1 token/step, full bidirectional attention without cache)
    naive_nfe = gen_len
    naive_attn_ops = gen_len * (total_len * total_len)

    # 2 & 3. Simulate Block-wise Confidence-Threshold Parallel Unmasking
    prefix_nfe = 0
    prefix_attn_ops = 0
    dual_nfe = 0
    dual_attn_ops = 0

    for b in range(num_blocks):
        s = prompt_len + b * block_size
        e = s + block_size
        masked_positions: Set[int] = set(range(block_size))
        step_idx = 0

        while masked_positions:
            conf_row = step_confidences[b * 10 + step_idx]
            # 找出当前仍处于 [MASK] 状态的位置中置信度 >= threshold 的集合，且强制保底最高置信度位置
            best_pos = max(masked_positions, key=lambda pos: conf_row[pos])
            to_unmask = {
                pos for pos in masked_positions if conf_row[pos] >= threshold
            } | {best_pos}
            masked_positions -= to_unmask

            if step_idx == 0:
                # 块首步：刷新全局 KV Cache
                prefix_nfe += 1
                prefix_attn_ops += total_len * total_len
                dual_nfe += 1
                dual_attn_ops += total_len * total_len
            else:
                # Prefix Cache 仅缓存 [:s]，当前步需输入 [s:] (长度 total_len - s)
                rem_len = total_len - s
                prefix_nfe += 1
                prefix_attn_ops += rem_len * total_len
                # DualCache 同时缓存 [:s] 与 [e:]，当前步仅输入当前块 [s:e] (长度 block_size)
                dual_nfe += 1
                dual_attn_ops += block_size * total_len

            step_idx += 1

    return {
        "naive_nfe": naive_nfe,
        "parallel_nfe": dual_nfe,
        "naive_attn_ops": naive_attn_ops,
        "prefix_cache_attn_ops": prefix_attn_ops,
        "dual_cache_attn_ops": dual_attn_ops,
    }


# --- 1. 验证 MDLM / LLaDA 的 1/p_mask 重要度加权损失 ---
# 设序列长 L=4，真实每位置交叉熵均为 -log_p = 2.0；对比 t=0.25 (1个mask) 与 t=1.0 (4个mask)
w_loss_low_t, raw_low_t = compute_mdlm_loss_terms(
    log_probs=[-2.0, -2.0, -2.0, -2.0],
    mask_flags=[True, False, False, False],
    t=0.25,
    eps=0.0,
)
w_loss_high_t, raw_high_t = compute_mdlm_loss_terms(
    log_probs=[-2.0, -2.0, -2.0, -2.0],
    mask_flags=[True, True, True, True],
    t=1.0,
    eps=0.0,
)
# 当被掩码比例恰好等于 t 时，乘上 1/t 使不同噪声水平下的单步期望损失保持尺度一致 (均为 2.0)
assert math.isclose(w_loss_low_t, 2.0) and math.isclose(w_loss_high_t, 2.0)
assert raw_low_t == 0.5 and raw_high_t == 2.0

# --- 2. 验证 BD3-LM 复合注意力掩码性质 (seq_len=4, block_size=2) ---
bd3_mask = build_bd3lm_attention_mask(seq_len=4, block_size=2)
# x_t 的块 0 (索引 0,1) 可双向互看，但绝不能偷看干净 x_0 的块 0 (索引 4,5) -> 防止信息泄漏
assert bd3_mask[0][1] == 1 and bd3_mask[1][0] == 1
assert bd3_mask[0][4] == 0 and bd3_mask[0][5] == 0
# x_t 的块 1 (索引 2,3) 可以通过 M_OBC 关注干净 x_0 的块 0 (索引 4,5)，但不能看干净块 1 (索引 6,7)
assert bd3_mask[2][4] == 1 and bd3_mask[2][5] == 1
assert bd3_mask[2][6] == 0 and bd3_mask[2][7] == 0

# --- 3. 验证置信度并行解码与 DualCache 的步数/访存压缩 ---
# 设 prompt_len=64, gen_len=16, block_size=4 (共 4 个块)，阈值 threshold=0.90
mock_confidences: Dict[int, List[float]] = {}
for blk in range(4):
    # 第 0 步：位置 0, 2 置信度超 0.90 并行解掩码 (2 个 token)
    mock_confidences[blk * 10 + 0] = [0.96, 0.72, 0.93, 0.65]
    # 第 1 步：剩余位置 1, 3 置信度均低于 0.90，触发保底机制仅解掩码最高置信度的位置 1 (1 个 token)
    mock_confidences[blk * 10 + 1] = [0.99, 0.88, 0.99, 0.79]
    # 第 2 步：最后位置 3 置信度 0.95 解掩码 (1 个 token)，当前块完成（仅用 3 步生成 4 个 token）
    mock_confidences[blk * 10 + 2] = [0.99, 0.99, 0.99, 0.95]

stats = simulate_confidence_parallel_decoding(
    step_confidences=[mock_confidences.get(i, [0.99] * 4) for i in range(40)],
    prompt_len=64,
    gen_len=16,
    block_size=4,
    threshold=0.90,
)
assert stats["naive_nfe"] == 16 and stats["parallel_nfe"] == 12
assert (
    stats["dual_cache_attn_ops"]
    < stats["prefix_cache_attn_ops"]
    < stats["naive_attn_ops"]
)

print(
    f"MDLM Weighted Loss (t=0.25 vs t=1.0): {w_loss_low_t:.2f} vs {w_loss_high_t:.2f} "
    f"(Unweighted: {raw_low_t:.2f} vs {raw_high_t:.2f})"
)
print(
    f"BD3-LM Mask Leakage Check -> x_t_blk0->x_0_blk0: {bd3_mask[0][4]}, "
    f"x_t_blk1->x_0_blk0 (M_OBC): {bd3_mask[2][4]}, x_t_blk1->x_0_blk1: {bd3_mask[2][6]}"
)
print(
    f"Decoding NFE: Naive={stats['naive_nfe']} -> Confidence-Parallel={stats['parallel_nfe']} "
    f"| Attention Ops: Naive={stats['naive_attn_ops']}, "
    f"PrefixCache={stats['prefix_cache_attn_ops']}, DualCache={stats['dual_cache_attn_ops']}"
)
print("Masked diffusion ELBO weighting, BD3-LM mask, and DualCache checks passed")
```

实际执行输出：

```text
MDLM Weighted Loss (t=0.25 vs t=1.0): 2.00 vs 2.00 (Unweighted: 0.50 vs 2.00)
BD3-LM Mask Leakage Check -> x_t_blk0->x_0_blk0: 0, x_t_blk1->x_0_blk0 (M_OBC): 1, x_t_blk1->x_0_blk1: 0
Decoding NFE: Naive=16 -> Confidence-Parallel=12 | Attention Ops: Naive=102400, PrefixCache=32000, DualCache=28160
Masked diffusion ELBO weighting, BD3-LM mask, and DualCache checks passed
```

---

## 延伸 / 追问

**追问 1：为什么掩码扩散语言模型（如 LLaDA）能够天然克服自回归模型的“逆向诅咒（Reversal Curse）”并在多区域代码补全（Infilling）中表现出色？**
自回归模型的训练与推理严格锁定在单向链式条件概率 $\prod_{i=1}^L p_\theta(x^{(i)} \mid x^{(<i)})$ 上——模型在训练时学到了由前缀“杜甫的诗句‘星垂平野阔’下一句是‘月湧大江流’”正向预测梯度，但从未在参数中直接建立从后缀预测前缀的反向条件通路（Berglund et al., 2023）。而在掩码扩散模型中，前向过程对任意子集位置随机施加 $\texttt{[MASK]}$，无论是前半句被掩码还是后半句被掩码，甚至是代码文件中分散在函数签名、Docstring 和调用处的 5 个不连续位置同时被置为 $\texttt{[MASK]}$，双向注意力都能在同一去噪步内同时利用左侧与右侧已知上下文协同恢复所有掩码槽位。因此在逆序古诗补全、数独全局规划与跨区域代码同步重构（Multi-Region Edit）任务中，掩码扩散具有天然的归纳偏置优势。

**追问 2：为什么在离散掩码扩散采样中使用 Gumbel-Max 采样时，低精度浮点数（FP16 / BF16）会导致生成质量显著崩塌（LLaDA 源码中为何强制转为 `torch.float64`）？**
如 LLaDA 官方仓库 `generate.py` 的 `add_gumbel_noise` 实现及 Zheng et al. (2024, *arXiv:2409.02908*) 揭示：在离散扩散模型中，采样类别分布常采用 Gumbel-Max 技巧 $\arg\max_v \big(\exp(z_v) / (-\log u_v)^T\big)$（其中 $u_v \sim \mathcal{U}(0, 1)$）。在 BF16（仅 7 位尾数）或 FP16 下，均匀随机数 $u_v$ 与对数指数运算极易发生截断下溢或数值碰撞，这虽然在表面评测上会人为降低生成文本的生成困惑度（Generative Perplexity，因为截断误差变相削弱了尾部随机性，等效于隐式降低了温度），但实际上严重扭曲了真实的类别分布并造成高频词重复与语义退化。因此在采样器核函数中，将 Logits 与 Gumbel 噪声提升至 `float64`（双精度）计算，是几乎零显存开销却能修复离散扩散采样失真的关键工程细节。

**追问 3：如果要对掩码扩散语言模型做强化学习后训练（如 GRPO），为什么不能直接套用自回归模型的逐 Token 概率连乘公式？**
在自回归模型的 PPO / GRPO 中，一条采样轨迹 $o$ 的策略对数概率可以直接通过一次前向传播精确分解为 $\log \pi_\theta(o \mid q) = \sum_{t=1}^{|o|} \log \pi_\theta(o_t \mid q, o_{<t})$。但在掩码扩散模型中：（1）模型并没有精确的边际对数似然 $\log \pi_\theta(o \mid q)$，只有关于随机掩码步 $t$ 和随机掩码模式 $o_t$ 的期望变分下界（ELBO）；（2）一条反向去噪轨迹包含 $S$ 个中间掩码状态 $(o_{t_S}, \dots, o_{t_0})$，若对全部 $S$ 步保存激活图做反向传播，显存会爆炸 $S$ 倍。因此针对扩散 LLM 的强化学习（如 d1 框架中的 `diffu-GRPO`，Zhao et al., 2025）必须在反向去噪采样得到完整回答 $o_0$ 后，通过在随机采样的时间步 $t$ 上对 $o_0$ 施加随机掩码，用单步（或少量采样步）的条件解掩码对数概率近似策略比率 $\frac{\pi_\theta(o_0 \mid q, o_t)}{\pi_{\text{old}}(o_0 \mid q, o_t)}$，从而在 $\mathcal{O}(1)$ 级前向开销内完成策略梯度更新。

---

## 常见误区

- **误区一：“扩散语言模型因为可以并行生成 Token，所以在任何硬件和部署配置下都一定比自回归模型更快。”**
  事实：生成延迟取决于**“总去噪步数（NFE）$\times$ 单步前向计算量”**。如果不启用分块因果掩码（BD3-LMs）或近似 KV 缓存（Fast-dLLM DualCache），纯双向扩散模型每一步都必须对完整序列（含全部 Prompt）重算注意力，单步计算量是自回归 Decode 步（仅算 1 个 Query Token）的数百倍！只有在结合了块级 KV Cache 复用，且单步通过高置信度阈值平均并行提交多个 Token（满足“节省的步数比例 $>$ 块内多 Token 算力增幅”）时，扩散模型才能在端到端延迟上真正击败深度优化的 AR 引擎。
- **误区二：“为了让扩散模型吐词最快，可以把去噪步数 $S$ 压到极小（比如 1~2 步直接解掩码整段话），模型会自动协调各词之间的关系。”**
  事实：单次前向传播只能输出各掩码位置相互独立的**边际分布**。当同时解掩码的 Token 数量过多、步数过少时，多个位置之间缺乏中间去噪步的条件交互，极易违反语法一致性与局部搭配（即“条件独立性诅咒”）。扩散模型的速度与质量受控于置信度阈值 $\tau$ 或每步解掩码配额：遇到高熵的复杂逻辑推理时，模型置信度普遍偏低，必须退回每次只解掩码少数几个锚点 Token 的精细迭代模式。
- **误区三：“训练一个带随机掩码的 BERT 模型，推理时摆上一排 `[MASK]` 循环替换就能当扩散语言模型用。”**
  事实：经典 BERT 仅在固定 $15\%$ 掩码率下训练，既无法处理 $t=1.0$（$100\%$ 全掩码）的初始状态，也没有经过 $1/t$ 权重的连续时间变分下界校准。要构建真正的离散掩码扩散语言模型，必须在训练期令掩码率 $t \sim \mathcal{U}(0, 1]$ 覆盖从全掩码到零星掩码的完整谱系，并在损失函数中严格引入 $1/t$ 重要度权重。

---

## 参考

- 选题线索：[ombharatiya/ai-system-design-guide, 04-inference-optimization/08-diffusion-llms.md](https://github.com/ombharatiya/ai-system-design-guide/blob/ed955b27d94201b663a741284767a1136dc83e5e/04-inference-optimization/08-diffusion-llms.md) 与 [pubalisen/ai-ml-interview-deep-dives, llm-fundamentals/43-diffusion-language-models.md](https://github.com/pubalisen/ai-ml-interview-deep-dives/blob/05cbb4c7383de742c90ab5e811130f658a4269ef/llm-fundamentals/43-diffusion-language-models.md)。固定 commit，独立拓展改编。
- Sahoo et al., [Simple and Effective Masked Diffusion Language Models (MDLM)](https://arxiv.org/abs/2406.07524)，NeurIPS 2024：吸收态离散掩码扩散、Rao-Blackwell 化连续时间 ELBO 推导与混合 MLM 目标。
- Nie et al., [Large Language Diffusion Models (LLaDA)](https://arxiv.org/abs/2502.09992)，2025，§2–3 & Appendix B（官方仓库 [`ML-GSAI/LLaDA`, commit `91824937`](https://github.com/ML-GSAI/LLaDA/blob/9182493720ed723ef8031210d85959364e51cbe0/generate.py)）：从头预训练与 SFT 的 $1/t$ 加权掩码损失、低置信度重掩码（Low-Confidence Remasking）、半自回归块生成与双精度 Gumbel 采样。
- Arriola et al., [Block Diffusion: Interpolating Between Autoregressive and Diffusion Language Models (BD3-LMs)](https://arxiv.org/abs/2503.09573)，ICLR 2025 Oral（官方仓库 [`kuleshov-group/bd3lms`, commit `1c3e8f43`](https://github.com/kuleshov-group/bd3lms/blob/1c3e8f43d88dfbcee5ff2aa6932a9e74b31ae1d7/models/hf/modeling_bd3lm.py)）：块间自回归与块内离散扩散插值、支持 KV Cache 与可变长生成、训练期 $M_{\text{BD}} \cup M_{\text{OBC}} \cup M_{\text{BC}}$ 复合注意力掩码。
- Wu et al., [Fast-dLLM: Training-free Acceleration of Diffusion LLM by Enabling KV Cache and Parallel Decoding](https://arxiv.org/abs/2505.22618)，ICLR 2026（官方仓库 [`NVlabs/Fast-dLLM`, commit `a9b81e4c`](https://github.com/NVlabs/Fast-dLLM/blob/a9b81e4caa240c8cad4f7dc1889ff4852a0fca5b/v1/llada/generate.py)）：分块近似 PrefixCache / DualCache 双缓存复用机制与置信度阈值并行解码（Confidence-Aware Parallel Decoding）理论保证。

来源访问与示例核验日期：**2026-11-03**。仅执行标准库 MDLM $1/t$ 加权损失、BD3-LM 复合注意力掩码防泄漏校验及 DualCache 置信度并行解码步数与访存模拟验证，未运行 GPU 端到端模型推理基准测试。
