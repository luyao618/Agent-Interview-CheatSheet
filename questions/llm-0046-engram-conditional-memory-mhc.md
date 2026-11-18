---
id: llm-0046
title: 条件记忆（DeepSeek Engram）与流形约束超连接（mHC）是如何通过确定性多头哈希查表、U 型稀疏容量分配与 Birkhoff 双随机流形投影重塑大模型稀疏与残差拓扑的？
category: llm
tags: [engram, conditional-memory, mhc, hyper-connections, moe, sinkhorn-knopp]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开大模型架构与推理系统指南（ForceInjection/AI-fundamentals 与 linkedin/Liger-Kernel）扩展改编；DeepSeek Engram 与 mHC 官方论文及源码核实（见参考）
status: published
updated: 2026-11-19
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-11-19
    updated: 2026-11-19
---

## 问题

在迈向万亿参数与超长上下文的基座大模型演进中，微观计算块（Attention 与 MoE）与宏观层间拓扑（Residual Connection）同时面临结构性瓶颈：
- **在稀疏容量维度**，以混合专家（MoE）为代表的**条件计算（Conditional Computation）**通过动态路由激活稀疏参数来处理组合推理，但标准 Transformer 缺乏原生的**静态知识查表（Knowledge Lookup）**原语。为了识别一个常见的多词元命名实体（如“Diana, Princess of Wales”）或固定搭配，模型被迫消耗浅层多轮自注意力与 FFN 去逐层拼装局部静态特征——这本质上是在运行时用昂贵的动态算力重建一张静态查表，不仅浪费了可用于高阶推理的序列有效深度（Effective Depth），而且 MoE 的专家路由依赖运行时隐状态 $\mathbf{h}_t$，导致庞大的专家参数必须驻留在昂贵的 GPU HBM 中。
- **在宏观残差拓扑维度**，近年提出的**超连接（Hyper-Connections, HC）**将单流残差宽度从 $C$ 扩展为 $n \times C$（如 $n=4$ 条并行残差流）并引入可学习的流间混合矩阵 $\mathcal{H}_l^{\text{res}} \in \mathbb{R}^{n \times n}$，在不增加算子 FLOPs 的前提下显著提升了表征容量。然而，无约束的 $\mathcal{H}_l^{\text{res}}$ 在跨多层连乘 $\prod_{i=1}^{L-l} \mathcal{H}_{L-i}^{\text{res}}$ 时彻底破坏了 ResNet 的恒等映射（Identity Mapping）守恒律，在 27B 规模预训练中导致前向信号与反向梯度增益暴涨至 $3000\times$ 进而引发训练崩溃，同时使残差流的 HBM 内存读写（I/O）与流水线并行通信膨胀了约 $n$ 倍。

为攻克上述两大难题，DeepSeek 先后提出了**条件记忆模块 Engram（Conditional Memory via Scalable Lookup，`arXiv:2601.07372`）**与**流形约束超连接 mHC（Manifold-Constrained Hyper-Connections，`arXiv:2512.24880`，并被 DeepSeek-V4 与 GLM-5.3-Flash 等模型采用）**。请深入剖析以下三个核心问题：

1. **Engram 条件记忆的四阶段检索-融合机制与多分支（mHC）协同架构**：Engram 是如何通过**分词器规范化压缩（Tokenizer Compression）**与**多头乘法-XOR 素数哈希（Multi-Head Multiplicative-XOR Hashing）**，从 $N$-gram 后缀中以 $\mathcal{O}(1)$ 复杂度确定性检索静态记忆向量 $\mathbf{e}_t$ 的？面对哈希碰撞与一词多义噪声，**上下文感知门控（Context-aware Gating）**是如何将当前隐状态作为动态 Query、检索记忆作为 Key/Value 进行语义对齐调制并结合深度因果短卷积（ShortConv）的？当接入 $M=4$ 分支的 mHC 骨干网时，为什么要采用“共享单张稀疏表与 $\mathbf{W}_V$、拆分 $M$ 个分支专属 $\mathbf{W}_K^{(m)}$”的非对称参数共享设计？
2. **MoE 与 Engram 的 U 型稀疏分配定律（Sparsity Allocation Law）与训推解耦系统工程**：在固定总参数量 $P_{\text{tot}}$ 与固定单 Token 激活参数量 $P_{\text{act}}$（即严格 Iso-Parameter 与 Iso-FLOPs）约束下，将非激活稀疏参数预算 $P_{\text{sparse}} = P_{\text{tot}} - P_{\text{act}}$ 按比例 $\rho$ 分配给 MoE 路由专家、$1-\rho$ 分配给 Engram 静态记忆槽位时，为什么验证集 Loss 会呈现显著的 **U 型缩放曲线**且最优区间稳定在 $\rho \approx 75\% \sim 80\%$？为什么通过 LogitLens 与 CKA 表征对齐分析发现 Engram 等效于“加深了网络有效深度”并大幅提升了长上下文检索（如 RULER Multi-Query NIAH 从 $84.2 \to 97.0$）？在推理部署（如纳米级/生产级 vLLM 与 SGLang）中，确定性寻址是如何支撑 100B+ 参数记忆表卸载至主机内存（Host DRAM / LPDDR），以及异步预取重叠（Prefetch-and-Overlap）与 Linux 2 MiB 巨页折叠（`MADV_COLLAPSE`）、`shared` vs `per_rank` 布局之间存在怎样的工程权衡？
3. **流形约束超连接（mHC）的 Birkhoff 多面体投影、Sinkhorn-Knopp 迭代与基础设施优化**：为什么无约束超连接（HC）的复合映射 $\prod \mathcal{H}^{\text{res}}$ 会破坏特征均值守恒并引发千倍增益爆炸？mHC 是如何通过 **Sinkhorn-Knopp 算法**将 $\mathcal{H}_l^{\text{res}}$ 熵投影到由双随机矩阵（Doubly Stochastic Matrices）构成的 **Birkhoff 多面体流形 $\mathcal{M}^{\text{res}}$** 上，从而同时保证谱范数非扩张（$\|\mathcal{H}_l^{\text{res}}\|_2 \le 1$）、跨层乘法闭包性与几何凸组合混合的？针对 $n$ 倍宽残差流带来的“内存墙（Memory Wall）”，mHC 是如何通过把除以 RMSNorm 范数移至矩阵乘之后的重排序融合内核、块级选择性重计算最优步长 $L_r^* \approx \sqrt{\frac{nL}{n+2}}$ 以及 DualPipe 高优计算流通信重叠，将 $n=4$ 时的训练额外耗时压低至仅 $6.7\%$ 的？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-11-19

**DeepSeek Engram（条件记忆）与 mHC（流形约束超连接）分别从“稀疏容量的第二正交轴”与“多流残差拓扑的流形守恒律”重塑了现代基座大模型架构：（1）在稀疏建模轴上，Engram 将语言建模解耦为需要动态深层计算的“组合推理（交由 MoE）”与局部刻板的“静态知识检索（交由 Engram）”，先通过 NFKC/小写/空白折叠分词器压缩将 128K 词表冗余削减 $23.43\%$，再对每个 $N$-gram 阶（如 $2,3$-gram）采用 $K=8$ 个互异素数模数的乘法-XOR 哈希头实现 $\mathcal{O}(1)$ 确定性查表，随后以当前隐状态 $\mathbf{h}_t^{(m)}$ 为 Query、记忆投影为 Key/Value 计算 RMSNorm 缩放点积门控 $\alpha_t^{(m)} \in (0,1)$ 与膨胀因果卷积（ShortConv），并在 $M=4$ 的 mHC 多分支上共享 $\mathbf{W}_V$、独立设置 $\mathbf{W}_K^{(m)}$ 以融合成单次 FP8 GEMM；（2）在容量缩放与系统工程上，固定 $P_{\text{tot}}$ 与 $P_{\text{act}}$ 时，纯 MoE（$\rho=100\%$）因缺乏专用记忆被迫用浅层注意力与 FFN 重建静态实体，而分配 $20\% \sim 25\%$ 稀疏预算给 Engram（$\rho \approx 75\% \sim 80\%$）达到 U 型 Loss 谷底，使 Engram-27B 的第 5 层在 CKA 上对齐 MoE-27B 的第 12 层，且因索引仅依赖输入 Token IDs（完全独立于运行时隐状态），100B+ 记忆表可卸载至主机 DRAM 并通过层前确定性预取或 2 MiB 巨页映射突破 GPU HBM 容量墙；（3）在宏观残差拓扑上，mHC 针对 HC 跨层连乘 $\prod \mathcal{H}^{\text{res}}$ 导致的 $3000\times$ 信号爆炸，对 $\mathcal{H}^{\text{pre}}, \mathcal{H}^{\text{post}}$ 施加 Sigmoid 非负约束以消除正负抵消，并通过 $t_{\max}=20$ 轮 Sinkhorn-Knopp 交替行列归一化将 $\mathcal{H}_l^{\text{res}}$ 投影至 Birkhoff 双随机流形（行列和皆为 $1$），凭谱范数上界 $1$ 与矩阵乘法闭包性将 27B 模型的跨层复合增益严格锚定在 $\le 1.6$，再配合算子融合（将残差合并读开销从 $(3n+1)C$ 降至 $(n+1)C$）与按块长 $L_r^* \approx \sqrt{\frac{nL}{n+2}}$ 选择性重计算，在 $n=4$ 时仅付 $6.7\%$ 训练时间代价即全面超越基线。**

在深入拆解数学推导与源码前，建议结合题库内已有相关题目建立完整的大模型体系结构认知：关于子词分词器（BPE）与词表Token预算的底层机制，请参阅 [llm-0007](llm-0007-tokenization-bpe-budget.md)；关于自注意力机制与因果掩码建模，请参阅 [llm-0010](llm-0010-causal-attention-architecture.md)；关于预训练 Scaling Law 与参数量、算力预算的权衡，请参阅 [llm-0011](llm-0011-scaling-data-emergence.md)；关于量化部署中的显存核算及为什么 MoE 激活参数量不能直接当作显存需求，请参阅 [llm-0016](llm-0016-quantization-local-memory-budget.md)；关于多头潜在注意力（MLA）与矩阵吸收，请参阅 [llm-0034](llm-0034-mla-multi-head-latent-attention-rope-absorption.md)；关于原生稀疏注意力（NSA）与 MoBA 的长上下文加速，请参阅 [llm-0045](llm-0045-native-sparse-attention-nsa-moba.md)。

---

### 1. 为什么 MoE 与超连接（HC）需要“条件记忆”与“流形约束”？

在 DeepSeek 的两篇核心架构论文（Cheng et al., `arXiv:2601.07372` 与 Xie et al., `arXiv:2512.24880`）中，作者分别指出了当前主流稀疏架构与残差拓扑的根本性失配：

| 架构维度 | 传统主流范式（Pure MoE / 无约束 Hyper-Connections） | 理论与系统层面的结构性瓶颈 | DeepSeek 破局设计（Engram 条件记忆 + mHC 流形约束超连接） |
| :--- | :--- | :--- | :--- |
| **稀疏容量轴（Computation vs. Memory）** | **纯 MoE（条件计算）**：全部稀疏参数皆为动态路由专家 FFN | 缺乏原生知识查表原语；模型被迫消耗前 $1 \sim 6$ 层 Attention + FFN 去逐层拼装静态多词元实体（如“Princess of Wales”），挤占深层推理与全局长上下文注意力容量 | **双轴混合稀疏（MoE + Engram）**：将 $20\% \sim 25\%$ 稀疏参数重分配给 $\mathcal{O}(1)$ 静态 $N$-gram 记忆表，释放浅层算力，等效加深网络推理深度 |
| **参数寻址与硬件驻留（HBM vs. Host DRAM）** | **动态隐状态寻址**：MoE 第 $\ell$ 层专家路由依赖当前层运行时隐状态 $\mathbf{h}_t^{(\ell)}$ | 必须在进入第 $\ell$ 层时才能算出激活哪些专家；面对高并发随机请求，所有路由专家参数必须常驻昂贵的 GPU HBM | **确定性 Token ID 寻址**：Engram 的哈希槽位索引仅依赖输入序列 $X=(x_1,\dots,x_T)$，在进入第 1 层前即 $100\%$ 确定，支持卸载至百 GB 级主机内存（LPDDR/DRAM）并异步预取 |
| **跨层残差信号传播（Signal Conservation）** | **无约束超连接（HC）**：$n$ 条残差流通过无约束矩阵 $\mathcal{H}_l^{\text{res}} \in \mathbb{R}^{n \times n}$ 线性混合 | 跨层连乘 $\prod_{i=1}^{L-l} \mathcal{H}_{L-i}^{\text{res}}$ 破坏恒等映射均值守恒；27B 模型在 12k 步附近复合增益（Amax Gain Magnitude）飙升至 $3000\times$，引发 Loss 尖峰与梯度爆炸 | **Birkhoff 流形双随机约束（mHC）**：用 Sinkhorn-Knopp 迭代将 $\mathcal{H}_l^{\text{res}}$ 投影为行列和均为 $1$ 的双随机矩阵，满足谱范数 $\le 1$ 与乘法闭包，复合增益严格受控于 $\le 1.6$ |
| **宽残差流内存墙（Memory I/O & Pipeline）** | **未融合多流读写**：将残差流拓宽 $n$ 倍后逐算子读写并全量保存中间激活 | 单层残差维护读取量从 $2C$ 暴增至 $(5n+1)C + n^2 + 2n$，且激活显存与流水线跨 Stage 通信开销均膨胀 $n$ 倍 | **重排序融合内核 + $L_r^*$ 块重计算 + DualPipe 重叠**：将残差合并读开销从 $(3n+1)C$ 砍至 $(n+1)C$，并以最优步长 $L_r^* \approx \sqrt{\frac{nL}{n+2}}$ 丢弃重算，训练额外耗时仅 $6.7\%$ |

---

### 2. DeepSeek Engram：确定性多头哈希查表、上下文门控与多分支融合

如官方论文第 2 节与参考实现 `deepseek-ai/Engram/engram_demo_v1.py` 所示，Engram 模块仅被有选择地插入特定 Transformer 层（例如 Engram-27B 插入在 30 层中的第 $2$ 层与第 $15$ 层），在进入该层的 Attention 与 MoE 之前执行“检索（Retrieval）$\to$ 门控融合（Fusion）$\to$ 残差相加”。

#### （1）分词器规范化压缩（Tokenizer Compression）
标准子词分词器（如 128K 词表的 BPE）为了保证文本无损还原，会给带前导空格、大小写或重音符号差异的同一概念分配完全不同的 Token ID（例如 `"Apple"`、`"␣apple"`、`"APPLE"`）。若直接在原始 Token ID 上构造 $N$-gram，记忆表容量会被表面词形碎片严重稀释。
- Engram 预计算了一个满射规范化映射 $\mathcal{P}: V \to V'$（对应 `engram_demo_v1.py` 第 60–121 行的 `CompressedTokenizer`）：对每个原始 Token 解码文本依次执行 `NFKC -> NFD -> StripAccents -> Lowercase -> 空白折叠 -> Strip`（并用专用哨兵符 `\uE000` 保留纯空格 Token），将语义等价的原始 ID 坍缩到同一个规范 ID $x'_t = \mathcal{P}(x_t)$。
- 在 DeepSeek 128K（$129,280$）分词器上，该无损规范化直接实现了 **$23.43\%$ 的有效词表压缩率**（例如将 $163$ 种空白符变体合并为 $1$ 个规范空格，将 $54$ 种 `'A'/'␣a'/'á'` 变体合并为 $1$ 个规范 `'a'`），大幅提升了 $N$-gram 的碰撞密度与样本命中率。

#### （2）多头乘法-XOR 素数哈希（Multi-Head Multiplicative-XOR Hashing）
直接为所有 $N$-gram 组合建表需要 $|V'|^N$ 级天文空间。Engram 对每个 $N$-gram 阶 $n \in \{2, \dots, N\}$（默认 $N=3$，即同时提取 2-gram 与 3-gram 后缀 $g_{t,n} = (x'_{t-n+1}, \dots, x'_t)$）配置 $K$ 个独立的哈希头（默认 $K=8$），通过确定性函数 $\varphi_{n,k}$ 将后缀映射到大小为**互异素数 $M_{n,k}$** 的嵌入分片表 $\mathbf{E}_{n,k} \in \mathbb{R}^{M_{n,k} \times d_{\text{head}}}$（其中 $d_{\text{head}} = \frac{d_{\text{mem}}}{(N-1)K}$），再拼接全部 $(N-1)K$ 个头的向量得到 $\mathbf{e}_t \in \mathbb{R}^{d_{\text{mem}}}$（论文公式 1–2）：

$$z_{t,n,k} \triangleq \varphi_{n,k}(g_{t,n}), \qquad \mathbf{e}_{t,n,k} = \mathbf{E}_{n,k}[z_{t,n,k}], \qquad \mathbf{e}_t \triangleq \mathop{\Big\|}_{n=2}^{N} \mathop{\Big\|}_{k=1}^{K} \mathbf{e}_{t,n,k}$$

对照 `engram_demo_v1.py` 第 188–325 行（`NgramHashMapping` 与 `MultiHeadEmbedding`）及 SGLang 生产实现（`srt/layers/engram.py`），其底层工程细节极为严密：
1. **防溢出的层专属随机奇数乘数**：对于第 $\ell$ 个 Engram 层，以确定性种子 `seed + 10007 * layer_id` 生成 $N$ 个随机奇数乘数 $\mathbf{m}^{(\ell)} = 2\mathbf{r} + 1$，其中随机数上界受 `half_bound = (int64_max // |V'|) // 2` 严格约束，从数学上杜绝 `token_id * multiplier` 发生 64 位有符号整数溢出；
2. **逐阶乘法-XOR 折叠与互异素数取模**：对于位置 $t$ 的 $n$-gram，先计算无进位异或混合值 $\text{mix}_{t,n} = (x'_t \cdot m_0) \oplus (x'_{t-1} \cdot m_1) \oplus \dots \oplus (x'_{t-n+1} \cdot m_{n-1})$（序列左边界不足时填充映射后的 `pad_id`），随后第 $k$ 个头对专属素数 $M_{n,k}$（从基准槽位数出发，通过素性测试顺序搜寻全局不重复素数）取模：$z_{t,n,k} = \text{mix}_{t,n} \bmod M_{n,k}$；
3. **单表扁平偏移合并（Offset-Shifted Single Table）**：为了避免在 GPU 或主机内存上发起 $(N-1)K = 16$ 次零散的小表查表，实现中将同层全部 $(N-1)K$ 个素数分片表拼成一张总行数为 $\sum_{n,k} M_{n,k}$ 的大表，预先计算前缀和偏移量 $\text{offsets}$，查表时直接通过 `shifted_ids = input_ids + self.offsets` 一次性完成索引！

#### （3）上下文感知签名门控（Context-aware Gating）、ShortConv 与多分支融合
静态检索出的 $\mathbf{e}_t$ 缺乏当前语境感知，且不可避免地混有哈希碰撞或一词多义（Polysemy）噪声。Engram 引入了受注意力启发的上下文感知门控（论文公式 3–6 与源码第 365–378 行）：
- **单流基本形式**：将已聚合前序全局上下文的当前隐状态 $\mathbf{h}_t \in \mathbb{R}^d$ 作为动态 Query，将静态记忆 $\mathbf{e}_t$ 投影为 Key（$\mathbf{k}_t = \mathbf{W}_K \mathbf{e}_t$）与 Value（$\mathbf{v}_t = \mathbf{W}_V \mathbf{e}_t$）。为保证梯度稳定，先对 Query 与 Key 分别施加 `RMSNorm` 再计算缩放内积标量门控 $\alpha_t \in (0, 1)$（源码中在缩放点积后还加入了保持符号的平方根非线性 $\operatorname{sign}(u)\sqrt{\max(|u|, 10^{-6})}$ 以软化极端内积并增强门控灵敏度）：
  $$\alpha_t = \sigma\!\left( \mathcal{S}\!\left(\frac{\operatorname{RMSNorm}(\mathbf{h}_t)^\top \operatorname{RMSNorm}(\mathbf{W}_K \mathbf{e}_t)}{\sqrt{d}}\right) \right), \qquad \tilde{\mathbf{v}}_t = \alpha_t \cdot (\mathbf{W}_V \mathbf{e}_t)$$
  若检索到的 $\mathbf{e}_t$ 因哈希碰撞与当前上下文 $\mathbf{h}_t$ 语义冲突，内积为负，$\alpha_t \to 0$ 自动抑制噪声；若命中“Alexander the Great”等固定模式，则 $\alpha_t \to 1$ 强激活记忆。
- **接入 $M=4$ 多分支（mHC）的参数共享与单次 FP8 GEMM 融合（论文公式 6）**：
  当骨干网采用 $M=4$ 条残差流的 mHC 架构时，若为每个分支复制整套记忆表会造成 $4$ 倍内存浪费；若所有分支完全共享门控又会丧失多流表征多样性。Engram 采用**“一表一 Value、多分支独立 Key”**的精妙折中：全层共享同一张稀疏嵌入表与同一个 $\mathbf{W}_V \in \mathbb{R}^{d \times d_{\text{mem}}}$，但为第 $m \in \{1,\dots,M\}$ 条分支配备专属的 $\mathbf{W}_K^{(m)} \in \mathbb{R}^{d \times d_{\text{mem}}}$：
  $$\alpha_t^{(m)} = \sigma\!\left(\frac{\operatorname{RMSNorm}(\mathbf{h}_t^{(m)})^\top \operatorname{RMSNorm}(\mathbf{W}_K^{(m)} \mathbf{e}_t)}{\sqrt{d}}\right), \qquad \mathbf{u}_t^{(m)} = \alpha_t^{(m)} \cdot (\mathbf{W}_V \mathbf{e}_t)$$
  在推理与训练底层（如 SGLang 的 `ReplicatedLinear`），$1$ 个 $\mathbf{W}_V$ 与 $M=4$ 个 $\mathbf{W}_K^{(m)}$ 被纵向拼接为单个矩阵 $\mathbf{W}_{KV} \in \mathbb{R}^{(M+1)d \times d_{\text{mem}}}$，只需**单次稠密 FP8 矩阵乘**即可同时算出所有分支的 Key 与共享 Value！
- **膨胀深度因果短卷积（ShortConv，论文公式 5）**：
  对门控调制后的多分支序列 $\tilde{\mathbf{V}} \in \mathbb{R}^{T \times M \times d}$ 逐分支做 `RMSNorm` 后，送入核大小 $w=4$、膨胀率等于最大 $N$-gram 阶 $\delta = N = 3$、分组数等于总通道数 $M \cdot d$ 的一维深度因果卷积（Depthwise Causal Conv1D，零初始化权重以在训练起点严格保持恒等映射），经 SiLU 激活后残差叠加回主干：
  $$\mathbf{Y} = \operatorname{SiLU}\!\left(\operatorname{Conv1D}_{w=4, \delta=N}\!\left(\operatorname{RMSNorm}(\tilde{\mathbf{V}})\right)\right) + \tilde{\mathbf{V}}, \qquad \mathbf{H}^{(\ell)} \leftarrow \mathbf{H}^{(\ell)} + \mathbf{Y}$$

---

### 3. U 型稀疏分配定律、有效深度机制与 LPDDR 主机卸载工程

#### （1）MoE 与 Engram 的 U 型稀疏容量分配定律（Sparsity Allocation Law）
在固定总参数量 $P_{\text{tot}}$ 与每 Token 激活参数量 $P_{\text{act}}$（即单步 FLOPs 恒定）下，定义非激活稀疏参数预算为 $P_{\text{sparse}} \triangleq P_{\text{tot}} - P_{\text{act}}$，令 $\rho \in [0, 1]$ 表示分给 MoE 路由专家的稀疏预算占比（论文公式 7）：

$$P_{\text{MoE}}^{(\text{sparse})} = \rho \, P_{\text{sparse}}, \qquad P_{\text{Engram}} = (1 - \rho) \, P_{\text{sparse}}$$

- 在 $C = 2 \times 10^{20}$ FLOPs（$P_{\text{tot}} \approx 5.7\text{B}, P_{\text{act}} = 568\text{M}$）与 $C = 6 \times 10^{20}$ FLOPs（$P_{\text{tot}} \approx 9.9\text{B}, P_{\text{act}} = 993\text{M}$）两个算力档位的受控扫描中，验证集 Loss 随 $\rho$ 呈现显著的 **U 型曲线**：
  - **纯 MoE 端（$\rho \to 100\%$）次优**：缺乏静态记忆原语，模型被迫将宝贵的动态专家与浅层深度浪费在死记硬背局部静态搭配上；
  - **纯 Engram 端（$\rho \to 0\%$）次优**：砍掉过多路由专家导致条件计算能力坍塌，因为静态查表无法替代需要动态上下文组合的逻辑推理；
  - **黄金分配甜点（$\rho \approx 75\% \sim 80\%$）**：将约 **$20\% \sim 25\%$ 的稀疏参数预算从 MoE 路由专家转移给 Engram**（如在 Engram-27B 中，将路由专家从 $72$ 个减至 $55$ 个，腾出 $5.7\text{B}$ 参数构建 Engram 记忆表，保持总参数 $26.7\text{B}$、激活参数 $3.8\text{B}$ 完全不变，此时 $\rho = 74.3\%$），不仅知识问答暴涨（MMLU $+3.0$、CMMLU $+4.0$），通用推理与代码数学提升更加惊人（BBH $+5.0$、ARC-Challenge $+3.7$、HumanEval $+3.0$、MATH $+2.4$）。
- **为什么加静态查表反而大幅提升了推理与长上下文能力？**
  1. **释放浅层局部重构负担，等效增加网络推理深度**：通过 LogitLens 逐层 KL 散度与 CKA（Centered Kernel Alignment，论文公式 8–9）表征相似度分析发现，Engram-27B 在**第 $5$ 层**形成的实体表征，已与 MoE-27B 基线在**第 $12$ 层**的表征高度对齐（$a_j > j$ 显著上移），相当于为复杂推理白白多省出了 $6 \sim 7$ 层有效计算深度；
  2. **解放注意力头专注全局上下文**：将局部 $N$-gram 依赖卸载给 $\mathcal{O}(1)$ 查表后，Attention 头不再被局部词组粘连占用。在严格对齐预训练 Loss（Iso-Loss，46k 步 vs MoE 50k 步）的 $32\text{K}$ 长上下文扩展评测中，Engram-27B 在 RULER 多查询大海捞针（Multi-Query NIAH）上从 **$84.2$ 跃升至 $97.0$**，多跳变量追踪（VT）从 **$77.0$ 跃升至 $87.2$**！

#### （2）从论文“异步预取重叠”到 SGLang 生产级“LPDDR 主机内存巨页查表”的工程权衡
由于 Engram 的哈希槽位索引仅取决于输入 Token 序列 $X$，在进入模型第 $1$ 层前即可全部算出，这从根源上打破了 MoE 专家参数必须驻留 GPU HBM 的限制：
1. **插入层位置（Layer Placement）的建模-系统联合折中**：
   - 若像传统输入嵌入扩展（如 OverEncoding / SCONE）那样放在第 $0$ 层（输入层），则一方面因没有经过任何 Attention 层导致隐状态 $\mathbf{h}_t$ 缺乏全局上下文，门控 $\alpha_t$ 退化为噪声；另一方面第 $0$ 层没有任何前置计算时间窗口来掩盖 PCIe 主机内存查表延迟；
   - 反之，若放得太深（如第 $12$ 层以后），模型浅层已经耗费算力完成了局部特征拼装，错失了减负时机；
   - 因此 Engram 选择在第 $2$ 层（仅经 $1$ 轮 Attention 即可获得高质量上下文 Query，同时利用第 $1$ 个 Transformer Block 的密集计算窗口掩盖 PCIe 传输）与第 $15$ 层分两级注入。在 H800 上将 **100B 参数**的 Engram 表完全卸载至主机 DRAM 时，端到端推理吞吐量折损至多仅 **$2.8\%$**（8B 基座从 $6,315 \to 6,140\text{ tok/s}$）。
2. **SGLang 生产级落地（如 DeepSeek-V4.1-Flash 的 196B 主机内存表）的三大硬核手术**：
   - **裸指针统一 Gather 内核与双布局权衡**：`engram_gather.py` 接收裸内存地址，无缝支持设备 HBM 表、Pinned 主机内存表及 Grace-Blackwell ATS 映射；并提供 `shared`（基于 `memfd_create + MAP_SHARED`，同机 TP 各卡共享单份主存映射、查表**零集合通信**，但要求共享 PID Namespace）与 `per_rank`（`MAP_PRIVATE` 每卡仅存分片行，查表后经一次 `all_reduce` 求和重组，换取独享巨页折叠能力）两种布局；
   - **2 MiB 巨页折叠（HugePage Collapse）生死线**：上百 GB 的主机表若走标准 4 KiB 页，每次随机查表都会触发 CPU/IOMMU TLB Miss，导致查表变慢约 **10 倍**！工程实现中通过 `memfd_create` 配合 `madvise(MADV_HUGEPAGE)`、`cudaHostRegister` 锁页，并在加载前调用 `posix_fadvise(DONTNEED)` 清空旧页缓存，加载后通过 `libc.madvise(MADV_COLLAPSE=25)`（Linux $\ge 6.1$）同步折叠为 2 MiB 巨页，最后解析 `/proc/self/smaps` 强校验巨页覆盖率 $\ge 98\%$；
   - **跨平台逐位确定性（Bit-Identical Hashing）**：由于 CPU/ROCm 路径与 GPU Triton 路径共享同一张预训练权重表，分词器规范化词表大小、奇数乘数生成与素数序列构成强耦合全局不变量——**一旦更换或微调 Tokenizer 词表，整张百亿级 Engram 记忆表将全部失效**。

---

### 4. 流形约束超连接（mHC）：Birkhoff 双随机投影与内存墙优化

#### （1）为什么无约束超连接（HC）必然引发跨层信号爆炸？
在超连接（HC，Zhu et al., 2024）中，第 $l$ 层的输入被拓宽为 $n$ 条并行残差流矩阵 $\mathbf{x}_l \in \mathbb{R}^{n \times C}$（通常 $n=4$）。单层传播由残差混合矩阵 $\mathcal{H}_l^{\text{res}} \in \mathbb{R}^{n \times n}$、流读取向量 $\mathcal{H}_l^{\text{pre}} \in \mathbb{R}^{1 \times n}$ 与流写回向量 $\mathcal{H}_l^{\text{post}} \in \mathbb{R}^{1 \times n}$ 控制（mHC 论文公式 3–4）：

$$\mathbf{x}_{l+1} = \mathcal{H}_l^{\text{res}} \mathbf{x}_l + \mathcal{H}_l^{\text{post}\,\top} \mathcal{F}\!\left(\mathcal{H}_l^{\text{pre}} \mathbf{x}_l, \mathcal{W}_l\right)$$

将其沿深度从浅层 $l$ 递归展开至深层 $L$：

$$\mathbf{x}_L = \underbrace{\left(\prod_{i=1}^{L-l} \mathcal{H}_{L-i}^{\text{res}}\right)}_{\text{跨层复合残差映射 } \mathbf{P}_{l \to L}} \mathbf{x}_l + \sum_{i=l}^{L-1} \left(\prod_{j=1}^{L-1-i} \mathcal{H}_{L-j}^{\text{res}}\right) \mathcal{H}_i^{\text{post}\,\top} \mathcal{F}\!\left(\mathcal{H}_i^{\text{pre}} \mathbf{x}_i, \mathcal{W}_i\right)$$

- 在标准 ResNet（$n=1, \mathcal{H}_l^{\text{res}} = 1$）中，$\mathbf{P}_{l \to L} \equiv 1$ 严格保持恒等映射；
- 而在原始 HC 中，$\mathcal{H}_l^{\text{res}} = \alpha_l^{\text{res}} \tanh(\theta_l^{\text{res}} \tilde{\mathbf{x}}_l^\top) + \mathbf{b}_l^{\text{res}}$ 是**无约束实矩阵**。当连乘 $L-l$ 层（如 30 个 Block 展开为 60 个 Attention/FFN 子层）时，只要单层最大奇异值略大于 $1$ 或存在正负元素相长干涉，复合矩阵 $\mathbf{P}_{l \to L}$ 的前向最大绝对行和（Forward Signal Gain）与反向最大绝对列和（Backward Gradient Gain，统称 **Amax Gain Magnitude**）就会呈指数级发散——在 DeepSeek 27B 实验中直接冲上 **$3000\times$**，导致第 12k 步梯度范数崩盘！

#### （2）mHC 的流形投影：Birkhoff 多面体与 Sinkhorn-Knopp 算法
为了在保留 $n$ 条残差流跨流信息交换能力的同时恢复恒等映射的信号守恒律，mHC（Xie et al., `arXiv:2512.24880` 公式 6–9）将 $\mathcal{H}_l^{\text{res}}$ 投影到由**双随机矩阵（Doubly Stochastic Matrices）**构成的流形——即 **Birkhoff 多面体 $\mathcal{M}^{\text{res}}$**：

$$\mathcal{P}_{\mathcal{M}^{\text{res}}}\!\left(\mathcal{H}_l^{\text{res}}\right) \coloneq \left\{ \mathbf{H} \in \mathbb{R}^{n \times n} \;\middle|\; \mathbf{H}\mathbf{1}_n = \mathbf{1}_n, \;\; \mathbf{1}_n^\top \mathbf{H} = \mathbf{1}_n^\top, \;\; \mathbf{H} \ge 0 \right\}$$

具体参数化与投影步骤如下（给定展平隐状态 $\vec{\mathbf{x}}_l = \operatorname{vec}(\mathbf{x}_l) \in \mathbb{R}^{1 \times nC}$ 及 $\vec{\mathbf{x}}'_l = \operatorname{RMSNorm}(\vec{\mathbf{x}}_l)$）：
1. **动态与静态混合参数化（公式 7）**：
   $$\tilde{\mathcal{H}}_l^{\text{pre}} = \alpha_l^{\text{pre}}(\vec{\mathbf{x}}'_l \varphi_l^{\text{pre}}) + \mathbf{b}_l^{\text{pre}}, \quad \tilde{\mathcal{H}}_l^{\text{post}} = \alpha_l^{\text{post}}(\vec{\mathbf{x}}'_l \varphi_l^{\text{post}}) + \mathbf{b}_l^{\text{post}}, \quad \tilde{\mathcal{H}}_l^{\text{res}} = \alpha_l^{\text{res}}\operatorname{mat}(\vec{\mathbf{x}}'_l \varphi_l^{\text{res}}) + \mathbf{b}_l^{\text{res}}$$
2. **输入/输出映射非负约束与 Sinkhorn-Knopp 迭代投影（公式 8–9）**：
   $$\mathcal{H}_l^{\text{pre}} = \sigma\!\left(\tilde{\mathcal{H}}_l^{\text{pre}}\right) \in (0,1)^{1 \times n}, \qquad \mathcal{H}_l^{\text{post}} = 2\sigma\!\left(\tilde{\mathcal{H}}_l^{\text{post}}\right) \in (0,2)^{1 \times n}$$
   $$\mathbf{M}^{(0)} = \exp\!\left(\tilde{\mathcal{H}}_l^{\text{res}}\right), \qquad \mathbf{M}^{(t)} = \mathcal{T}_r\!\left(\mathcal{T}_c\!\left(\mathbf{M}^{(t-1)}\right)\right) \;\;\text{for } t = 1, \dots, t_{\max} \;\; (t_{\max}=20)$$
   其中 $\mathcal{T}_c(\mathbf{M})_{i,j} = \frac{\mathbf{M}_{i,j}}{\sum_{k=1}^n \mathbf{M}_{k,j}}$ 为列归一化，$\mathcal{T}_r(\mathbf{M})_{i,j} = \frac{\mathbf{M}_{i,j}}{\sum_{k=1}^n \mathbf{M}_{i,k}}$ 为行归一化。

为什么投影到 Birkhoff 流形能根治深层训练不稳定性？
- **性质 1（前向均值守恒与反向梯度守恒）**：因为每行之和为 $1$ 且非负，$\mathcal{H}_l^{\text{res}} \mathbf{x}_l$ 是 $n$ 条残差流的**凸组合（Convex Combination）**；同时因为每列之和为 $1$，所有流的特征均值在传播中严格守恒：$\frac{1}{n}\mathbf{1}_n^\top (\mathcal{H}_l^{\text{res}} \mathbf{x}_l) = \frac{1}{n}\mathbf{1}_n^\top \mathbf{x}_l$；
- **性质 2（谱范数有界非扩张）**：由 Perron-Frobenius 定理与 Gershgorin 圆盘定理，任何双随机矩阵的谱范数满足 $\|\mathcal{H}_l^{\text{res}}\|_2 \le 1$，从数学上杜绝了单层信号膨胀；
- **性质 3（跨层矩阵乘法闭包性，Compositional Closure）**：两个双随机矩阵的乘积依然严格是双随机矩阵！因此无论网络加深到多少层，跨层复合映射 $\prod_{i=1}^{L-l} \mathcal{H}_{L-i}^{\text{res}}$ 永远留在 Birkhoff 多面体内（在 $t_{\max}=20$ 有限步近似下，27B 模型全网 60 层复合增益峰值从 HC 的 $3000$ 骤降至 $\le 1.6$，降低了三个数量级）；
- **性质 4（Birkhoff-von Neumann 几何解释）**：Birkhoff 多面体是所有 $n \times n$ 置换矩阵（Permutation Matrices）的凸包，意味着 $\mathcal{H}_l^{\text{res}}$ 等效于对多条残差流做可导的软置换与单调信息混合。

#### （3）mHC 突破“内存墙”的三项系统级协同设计
1. **重排序 RMSNorm 与算子融合（Kernel Fusion，论文公式 10–19 & Table 2）**：
   - 在计算动态系数时，对高维向量 $\vec{\mathbf{x}}_l \in \mathbb{R}^{1 \times nC}$ 先做 `RMSNorm` 再乘以投影矩阵 $\varphi_l \in \mathbb{R}^{nC \times (n^2+2n)}$ 会导致对 $\vec{\mathbf{x}}_l$ 的冗余遍历。mHC 利用线性齐次性，先在单次融合内核中同时算出未归一化矩阵乘 $\vec{\mathbf{x}}_l \varphi_l$ 与范数标量 $r = \|\vec{\mathbf{x}}_l\|_2 / \sqrt{nC}$，随后在极小的系数张量 $[1, n^2+2n]$ 上除以 $r$；
   - 在应用残差更新 $\mathcal{F}_{\text{post,res}} \coloneq \mathcal{H}_l^{\text{res}} \mathbf{x}_l + \mathcal{H}_l^{\text{post}\,\top} \mathcal{F}(\cdot)$ 时，通过 TileLang 融合内核将每 Token 的 HBM **读取元素量从 $(3n+1)C$ 降至 $(n+1)C$**（当 $n=4$ 时从 $13C$ 降至 $5C$，削减 $2.6\times$），**写入元素量从 $3nC$ 降至 $nC$**（削减 $3.0\times$）；同时将 $t_{\max}=20$ 轮 Sinkhorn-Knopp 迭代完全锁在片上寄存器中执行，反向传播时在片上即时重算迭代轨迹而不写回 HBM。
2. **块级选择性重计算与最优步长公式 $L_r^*$（Selective Recomputing，论文公式 20）**：
   - 为消除 $n$ 流中间激活的显存膨胀，mHC 在前向传播后丢弃连续 $L_r$ 层内的轻量 mHC 映射激活，仅保留重计算块的起始输入 $\mathbf{x}_{l_0}$（占 $nC$）以及昂贵主干算子 $\mathcal{F}(\mathcal{H}_l^{\text{pre}}\mathbf{x}_l, \mathcal{W}_l)$ 的输出（占 $C$）。反向传播时，在不重跑重型 Attention/MoE 算子 $\mathcal{F}$ 的前提下，仅重跑廉价的 mHC 系数与融合内核；
   - 给定总层数 $L$，常驻块首激活显存与当前活跃块的瞬态重算显存之和为：
     $$\text{Mem}(L_r) = nC \times \left\lceil \frac{L}{L_r} \right\rceil + (n+2)C \times L_r \implies L_r^* = \arg\min_{L_r} \text{Mem}(L_r) \approx \sqrt{\frac{nL}{n+2}}$$
     例如当 $n=4, L=30$ 时，理论最优块长 $L_r^* \approx \sqrt{\frac{120}{6}} = \sqrt{20} \approx 4.47$（整数最优解 $L_r^* = 5$），且在流水线并行中恰好与单个 Pipeline Stage 的层数对齐，无需跨 Stage 重算。
3. **DualPipe 流水线通信与计算重叠（Section 4.3.3）**：
   针对 $n$ 流残差在 Pipeline Stage 边界造成的 $n$ 倍激活通信量，mHC 扩展了 DeepSeek-V3 的 DualPipe 调度器：将 FFN 层的 $\mathcal{F}_{\text{post,res}}$ 融合内核放入专用高优先级计算流（High-Priority Stream）以避免阻塞通信流，并在重叠的 Attention 层禁用长驻（Persistent）内核以支持抢占调度。

```
DeepSeek Engram (条件记忆) + mHC (流形约束超连接, M=n=4) 协同单层数据流：

  输入 Token IDs: X = (x_1, ..., x_T)                 n=4 条并行残差流: x_l in R^{n x C}
                 │                                                   │
  [层循环开始前: 100% 确定性寻址]                                    ▼
  1. CompressedTokenizer: x'_t = P(x_t) (-23.43%)     ┌─── [若当前层 l in Engram_Layers (如 l=2, 15)] ───┐
  2. 多头乘法-XOR 素数哈希 (n=2..3, K=8 头):          │  1. 从 HBM 或 Host DRAM (2MiB HugePage) 取出 e_t │
     z_{t,n,k} = (XOR_i x'_{t-i} * m_i) mod M_{n,k}   │  2. 单次 FP8 GEMM 算出共享 v_t 与 4 路专属 k_t^m │
  3. 异步预取 / 2MiB 巨页查表 -> 拼接静态记忆 e_t ────┼─►3. 逐流 RMSNorm + Signed-Sqrt Sigmoid 门控 a_t^m│
                                                      │  4. 膨胀因果 ShortConv (w=4, d=3) -> 残差加回 x_l │
                                                      └──────────────────────────────────────────────────┘
                                                                     │
                                                                     ▼
                                                      ┌─── [mHC 流形约束超连接包裹 Attention / MoE] ─────┐
                                                      │  1. 融合投影算出系数, 除以延迟归约范数 r          │
                                                      │  2. H_pre = sigmoid(.),  H_post = 2*sigmoid(.)   │
                                                      │  3. H_res = Sinkhorn-Knopp_20(exp(.)) (Birkhoff) │
                                                      │  4. F_pre:  h_in = H_pre * x_l  (n x C -> 1 x C) │
                                                      │  5. 执行主干算子: y = Attn(h_in) 或 MoE(h_in)    │
                                                      │  6. F_post,res 融合写回 (读从 13C 降至 5C):      │
                                                      │     x_{l+1} = H_res * x_l + H_post^T * y         │
                                                      └──────────────────────────────────────────────────┘
```

---

### 5. Python 3 标准库可运行仿真：Engram 确定性素数哈希、门控与 mHC Birkhoff 投影

下面的自包含脚本仅使用 Python 3 标准库（`math`、`typing`），忠实复现并验证了：
1. **Engram 分词器规范化压缩与多头乘法-XOR 素数哈希偏移寻址**（对应 `engram_demo_v1.py` 的 `CompressedTokenizer`、`NgramHashMapping` 与 `MultiHeadEmbedding`）；
2. **Engram 上下文感知签名门控（RMSNorm + Signed-Sqrt + Sigmoid）**在语义对齐与哈希碰撞/矛盾语境下的滤波对比；
3. **mHC 的 Sinkhorn-Knopp 迭代投影（$t_{\max}=20$）**在 10 层复合连乘下的增益守恒（$\text{Amax Gain} = 1.0$）与无约束 HC 的指数级信号爆炸对比；
4. **mHC 算子融合前后的 HBM 读写压缩比与公式 (20) 最优重计算块长 $L_r^*$ 求解**。

```python
import math
from typing import Dict, List, Tuple


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    d = 3
    while d * d <= n:
        if n % d == 0:
            return False
        d += 2
    return True


def find_next_distinct_primes(base_size: int, num_heads: int, seen: set) -> List[int]:
    """复现 Engram 源码 calculate_vocab_size_across_layers：为每个哈希头分配严格递增且不重复的素数模数"""
    primes = []
    candidate = base_size
    while len(primes) < num_heads:
        if is_prime(candidate) and candidate not in seen:
            seen.add(candidate)
            primes.append(candidate)
        candidate += 1
    return primes


def compress_tokenizer_demo(raw_vocab: Dict[int, str]) -> Tuple[Dict[int, int], int]:
    """复现 CompressedTokenizer：归一化大小写与前导空白，将语义等价 Token 坍缩为规范 ID"""
    canonical_to_new: Dict[str, int] = {}
    old_to_new: Dict[int, int] = {}
    for tid, token_str in raw_vocab.items():
        norm_key = " ".join(token_str.strip().lower().split())
        if not norm_key:
            norm_key = " "
        if norm_key not in canonical_to_new:
            canonical_to_new[norm_key] = len(canonical_to_new)
        old_to_new[tid] = canonical_to_new[norm_key]
    return old_to_new, len(canonical_to_new)


def engram_multi_head_xor_hash(
    canonical_ids: List[int],
    max_ngram: int,
    odd_multipliers: List[int],
    prime_moduli_per_ngram: List[List[int]],
    pad_id: int = 0,
) -> Tuple[List[List[int]], List[int]]:
    """
    复现 _get_ngram_hashes 与 MultiHeadEmbedding 偏移寻址：
    对每个位置 t 与 n in [2..N] 计算奇数乘法-XOR 混合哈希，并映射为单张扁平 Embedding 表的全局行号。
    """
    seq_len = len(canonical_ids)
    flat_prime_sizes = [p for n_primes in prime_moduli_per_ngram for p in n_primes]
    offsets = [0]
    for p in flat_prime_sizes[:-1]:
        offsets.append(offsets[-1] + p)

    global_indices_per_pos: List[List[int]] = []
    for t in range(seq_len):
        pos_indices: List[int] = []
        head_cursor = 0
        for n in range(2, max_ngram + 1):
            mix = 0
            for k in range(n):
                tok = canonical_ids[t - k] if t - k >= 0 else pad_id
                term = tok * odd_multipliers[k]
                mix = term if k == 0 else (mix ^ term)
            for mod_p in prime_moduli_per_ngram[n - 2]:
                local_slot = mix % mod_p
                pos_indices.append(offsets[head_cursor] + local_slot)
                head_cursor += 1
        global_indices_per_pos.append(pos_indices)
    return global_indices_per_pos, offsets


def rms_norm(vec: List[float], eps: float = 1e-6) -> List[float]:
    ms = sum(x * x for x in vec) / len(vec)
    inv_rms = 1.0 / math.sqrt(ms + eps)
    return [x * inv_rms for x in vec]


def engram_branch_signed_sqrt_gate(
    query_branch: List[float], key_branch: List[float]
) -> float:
    """
    复现 engram_demo_v1.py 第 368-373 行上下文门控：
    RMSNorm -> Scaled Dot-Product -> Signed-Sqrt -> Sigmoid
    """
    d = len(query_branch)
    nq = rms_norm(query_branch)
    nk = rms_norm(key_branch)
    dot = sum(q * k for q, k in zip(nq, nk)) / math.sqrt(d)
    signed_sqrt = math.sqrt(max(abs(dot), 1e-6)) * (1.0 if dot >= 0 else -1.0)
    return round(1.0 / (1.0 + math.exp(-signed_sqrt)), 4)


def sinkhorn_knopp_birkhoff(
    logits: List[List[float]], t_max: int = 20
) -> List[List[float]]:
    """
    复现 mHC 论文公式 (8)-(9)：通过指数化与 t_max=20 轮交替行列归一化投影至 Birkhoff 双随机流形
    """
    n = len(logits)
    mat = [[math.exp(logits[i][j]) for j in range(n)] for i in range(n)]
    for _ in range(t_max):
        # 列归一化 T_c
        for j in range(n):
            col_sum = sum(mat[i][j] for i in range(n))
            for i in range(n):
                mat[i][j] /= col_sum
        # 行归一化 T_r
        for i in range(n):
            row_sum = sum(mat[i][j] for j in range(n))
            for j in range(n):
                mat[i][j] /= row_sum
    return mat


def mat_mul(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    n = len(a)
    return [
        [sum(a[i][k] * b[k][j] for k in range(n)) for j in range(n)]
        for i in range(n)
    ]


def amax_gain_magnitude(mat: List[List[float]]) -> Tuple[float, float]:
    """计算 mHC 论文 Section 3.1 的前向最大行和增益与反向最大列和增益"""
    n = len(mat)
    max_row_sum = max(sum(abs(mat[i][j]) for j in range(n)) for i in range(n))
    max_col_sum = max(sum(abs(mat[i][j]) for i in range(n)) for j in range(n))
    return round(max_row_sum, 4), round(max_col_sum, 4)


def verify_mhc_io_and_recompute_budget(
    n_streams: int, dim_c: int, total_layers: int
) -> Dict[str, object]:
    """验证 mHC 论文 Table 2 算子融合前后访存量与公式 (20) 最优重计算块大小 L_r*"""
    unfused_read = (3 * n_streams + 1) * dim_c
    fused_read = (n_streams + 1) * dim_c
    unfused_write = 3 * n_streams * dim_c
    fused_write = n_streams * dim_c

    best_lr = min(
        range(1, total_layers + 1),
        key=lambda lr: n_streams * math.ceil(total_layers / lr) + (n_streams + 2) * lr,
    )
    analytic_lr = round(math.sqrt(n_streams * total_layers / (n_streams + 2)), 2)
    return {
        "read_reduction_ratio": round(unfused_read / fused_read, 2),
        "write_reduction_ratio": round(unfused_write / fused_write, 2),
        "best_integer_lr": best_lr,
        "analytic_lr": analytic_lr,
    }


# --- 1. 验证 Tokenizer 压缩与多头素数 XOR 哈希寻址 ---
demo_vocab = {
    0: "<pad>",
    1: "Apple",
    2: " apple",
    3: "APPLE",
    4: "Pie",
    5: " pie",
}
lut, compressed_size = compress_tokenizer_demo(demo_vocab)
assert compressed_size == 3  # 6 个原始 Token 坍缩为 3 个规范概念 (<pad>, apple, pie)
assert lut[1] == lut[2] == lut[3]

seen_primes: set = set()
primes_2gram = find_next_distinct_primes(base_size=100, num_heads=2, seen=seen_primes)
primes_3gram = find_next_distinct_primes(base_size=100, num_heads=2, seen=seen_primes)
assert primes_2gram == [101, 103]
assert primes_3gram == [107, 109]

# 两个表面 Token ID 不同但规范化等价的序列：["Apple", "Pie"] vs [" apple", " pie"]
seq_a = [lut[1], lut[4]]
seq_b = [lut[2], lut[5]]
hashes_a, table_offsets = engram_multi_head_xor_hash(
    seq_a, max_ngram=3, odd_multipliers=[3, 7, 11],
    prime_moduli_per_ngram=[primes_2gram, primes_3gram], pad_id=lut[0]
)
hashes_b, _ = engram_multi_head_xor_hash(
    seq_b, max_ngram=3, odd_multipliers=[3, 7, 11],
    prime_moduli_per_ngram=[primes_2gram, primes_3gram], pad_id=lut[0]
)
assert hashes_a == hashes_b
assert table_offsets == [0, 101, 204, 311]

# --- 2. 验证上下文感知门控：语义对齐激活 vs 碰撞/矛盾噪声抑制 ---
mem_key = [1.2, -0.9, 1.5, -1.1]
q_aligned = [1.1, -0.8, 1.4, -1.0]      # 与检索记忆高度对齐的上下文隐状态
q_conflict = [-1.1, 0.8, -1.4, 1.0]     # 发生哈希碰撞或语境矛盾时的隐状态
gate_aligned = engram_branch_signed_sqrt_gate(q_aligned, mem_key)
gate_conflict = engram_branch_signed_sqrt_gate(q_conflict, mem_key)
assert gate_aligned > 0.80 and gate_conflict < 0.20
assert round(gate_aligned + gate_conflict, 4) == 1.0

# --- 3. 验证 mHC Birkhoff 双随机投影的复合闭包性与增益守恒 vs 无约束 HC 爆炸 ---
raw_h = [
    [0.8, 0.3, -0.2, 0.4],
    [0.1, 0.9, 0.5, -0.1],
    [-0.3, 0.2, 1.1, 0.3],
    [0.4, -0.1, 0.2, 0.7],
]
hc_comp = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
for _ in range(10):
    hc_comp = mat_mul(hc_comp, raw_h)
hc_fwd_gain, hc_bwd_gain = amax_gain_magnitude(hc_comp)

mhc_single = sinkhorn_knopp_birkhoff(raw_h, t_max=20)
mhc_comp = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
for _ in range(10):
    mhc_comp = mat_mul(mhc_comp, mhc_single)
mhc_fwd_gain, mhc_bwd_gain = amax_gain_magnitude(mhc_comp)

assert hc_fwd_gain > 20.0 and hc_bwd_gain > 20.0
assert mhc_fwd_gain == 1.0 and mhc_bwd_gain == 1.0

# --- 4. 验证 mHC 融合内核 I/O 削减比与重计算最优块长 L_r* (n=4, L=30) ---
mhc_sys = verify_mhc_io_and_recompute_budget(n_streams=4, dim_c=2560, total_layers=30)
assert mhc_sys["read_reduction_ratio"] == 2.6
assert mhc_sys["write_reduction_ratio"] == 3.0
assert mhc_sys["best_integer_lr"] == 5

print(
    f"1. Engram Hash: raw_vocab=6 -> canonical={compressed_size}, "
    f"offsets={table_offsets}, pos1_slots={hashes_a[1]}"
)
print(
    f"2. Context Gate: aligned_alpha={gate_aligned} vs "
    f"collision_alpha={gate_conflict}"
)
print(
    f"3. 10-Layer Gain (n=4): unconstrained_HC=({hc_fwd_gain}, {hc_bwd_gain}) "
    f"vs mHC_Birkhoff=({mhc_fwd_gain}, {mhc_bwd_gain})"
)
print(
    f"4. mHC System (n=4, L=30): read_saved={mhc_sys['read_reduction_ratio']}x, "
    f"write_saved={mhc_sys['write_reduction_ratio']}x, "
    f"optimal_Lr*={mhc_sys['best_integer_lr']} (analytic={mhc_sys['analytic_lr']})"
)
print("All Engram Conditional Memory & mHC assertions passed!")
```

实际运行输出：

```text
1. Engram Hash: raw_vocab=6 -> canonical=3, offsets=[0, 101, 204, 311], pos1_slots=[1, 102, 205, 312]
2. Context Gate: aligned_alpha=0.8044 vs collision_alpha=0.1956
3. 10-Layer Gain (n=4): unconstrained_HC=(26.9389, 38.3726) vs mHC_Birkhoff=(1.0, 1.0)
4. mHC System (n=4, L=30): read_saved=2.6x, write_saved=3.0x, optimal_Lr*=5 (analytic=4.47)
All Engram Conditional Memory & mHC assertions passed!
```

---

## 延伸 / 追问

**追问 1：在预训练优化器配置上，为什么 Engram-27B 的主干网络（Attention / MoE / mHC）采用 Muon 优化器，而稀疏 Engram 嵌入表却必须单独使用 Adam 优化器、将学习率放大 $5\times$ 且设权重衰减（Weight Decay）为 $0$？同时为什么 ShortConv 卷积核必须初始化为全零（Zero-Init）？**
1. **稠密矩阵参数与极度稀疏查表梯度的几何性质截然不同**：
   - 主干网络中的线性投影与 MoE 专家权重是稠密二维矩阵，每个训练 Batch 都能收到密集梯度，使用基于 Newton-Schulz 正交化动量的 **Muon 优化器**（配合 `weight_decay=0.1`）能高效约束矩阵谱范数并加速特征学习；
   - 反之，Engram 记忆表拥有数百万至数亿行槽位（如 Engram-27B 的 `engram_vocab_size=2,262,400`），遵循自然语言 $N$-gram 的 **Zipf 幂律分布**——绝大部分长尾槽位在成百上千个 Step 中才被命中激活一次！如果对 Engram 嵌入表施加非零的 decoupled weight decay（$\lambda > 0$），未被当前 Batch 命中的长尾记忆槽位会在每一步无条件向零指数衰减，导致好不容易记住的低频知识被彻底抹除；同时，由于单槽位更新频率极低，必须借助 **Adam 的逐坐标自适应二阶动量（Per-coordinate Second Moment）** 并将学习率放大 $5\times$，才能让稀疏槽位与主干网络保持同步收敛速度。
2. **ShortConv 全零初始化（Conv Zero-Init）保护训练早期信号流**：
   在公式 (5) $\mathbf{Y} = \operatorname{SiLU}(\operatorname{Conv1D}(\operatorname{RMSNorm}(\tilde{\mathbf{V}}))) + \tilde{\mathbf{V}}$ 中，将卷积核权重初始化为全 $0$，使得训练第 $0$ 步时卷积分支输出严格为 $0$，即 $\mathbf{Y} = \tilde{\mathbf{V}}$，避免随机初始化的跨位置膨胀卷积在训练初期向多分支残差流注入高频伪影。

**追问 2：如果在推理阶段直接把训练好的 Engram-27B 模型的 Engram 记忆输出强制置零（Post-hoc Suppression Ablation），不同下游任务会出现怎样的分化？这揭示了 Transformer 内部怎样的知识存储分工？**
1. **事实性知识崩塌 vs 阅读理解高度鲁棒的“双峰极化”**：
   根据 Engram 论文 Section 6.3（Figure 6）的敏感度压力测试，当在推理期强行关断 Engram 模块（令 $\mathbf{Y} = \mathbf{0}$）而保持 MoE 主干不变时：
   - **闭卷事实问答（Factual Knowledge）灾难性崩塌**：TriviaQA 仅保留了原始性能的 **$29\%$**（总体事实类仅剩 $29\% \sim 44\%$），证明参数化事实关联与命名实体记忆已被高度卸载并存储在 Engram 静态哈希表中；
   - **上下文阅读理解（Reading Comprehension）几乎无损**：C3 保留了 **$93\%$** 的原始性能（总体阅读理解保留 $81\% \sim 93\%$），证明基于当前给定文章的动态信息提取与跨句整合完全由主干网络的 Attention 与 MoE 承担。
2. **对知识编辑与存储分层（LPDDR + NVMe SSD）的启示**：
   这种清晰的职能正交性不仅验证了“条件记忆管静态事实、条件计算管动态推理”的设计初衷，而且结合 $N$-gram 访问的 Zipf 分布，使得在系统层面可以将 Top $1\% \sim 5\%$ 的高频热点槽位缓存在 GPU HBM 或 Host DRAM 中，而将占容量大头的罕见长尾事实槽位下沉至大容量 NVMe SSD，构建多级存储层次（Multi-Level Cache Hierarchy）。

**追问 3：在 mHC 中，既然目标是保证跨层残差矩阵 $\mathcal{H}_l^{\text{res}}$ 的谱范数不大于 $1$ 以防止信号爆炸，为什么不直接使用正交矩阵投影（Orthogonal Matrix Projection，如 Cayley 变换或 Householder 反射）或直接对矩阵做行 Softmax（Row-stochastic），而一定要使用 Sinkhorn-Knopp 投影为双随机矩阵（Doubly Stochastic）？**
1. **为什么单向行 Softmax（Row-Stochastic，$\mathcal{H}\mathbf{1}=\mathbf{1}$ 但 $\mathbf{1}^\top\mathcal{H} \ne \mathbf{1}^\top$）不够？**
   若只约束每行之和为 $1$（仅做一次行 Softmax），虽然能限制前向传播的最大行和增益为 $1$，但**列和完全不受约束**（例如所有行都把权重 $1$ 集中投给第 $0$ 条残差流，导致第 $0$ 列之和变成 $n=4$，其余列之和为 $0$）。这不仅会导致多条残差流在几层之内迅速坍缩为单一流（喪失多流多样性），还会使反向传播的列和梯度增益（$\|\mathcal{H}^\top\|_\infty$）在跨层连乘时指数级爆炸！
2. **为什么正交矩阵（Orthogonal Matrix，$\mathbf{Q}^\top \mathbf{Q} = \mathbf{I}$）不如 Birkhoff 双随机矩阵？**
   正交矩阵虽然满足谱范数恒为 $1$，但其包含大量正负号交替的元素，在残差流线性组合时会引发严重的**正负信号相消干涉（Signal Cancellation）**，且无法保证各残差流特征均值守恒；而双随机矩阵同时满足非负性（$\mathbf{H} \ge 0$）、行和为 $1$（前向凸组合保界）与列和为 $1$（反向梯度保界与全局均值守恒），是兼顾多流单调特征融合与双向数值稳定的理想流形。

---

## 常见误区

- **误区一：“Engram 模块就是把传统的 $N$-gram Embedding 直接加在模型第 0 层（词表输入 Embedding 层）上，或者直接按哈希头取平均，跟早期的 FastText / OverEncoding 没有本质区别。”**
  事实：**无论把 $N$-gram 放在第 0 层还是简单取平均，都会损失绝大部分架构收益！** 首先，若放在第 0 层，一方面输入的原始 Token 尚未经过任何自注意力聚合全局语境，无法构造上下文感知门控 $\alpha_t$ 来过滤哈希碰撞与一词多义噪声；另一方面第 0 层没有任何前置计算层来掩盖从主机内存（Host DRAM）走 PCIe 预取嵌入向量的通信延迟。其次，论文 Section 3.2 与 6.2 的消融实验证明，去除上下文感知门控、去除多分支专属 Key 投影或去除 Tokenizer 规范化压缩，都会导致验证集 Loss 大幅恶化。
- **误区二：“既然 MoE 也是稀疏激活参数，那 MoE 的非激活专家参数也能像 Engram 记忆表一样直接卸载到 CPU 主机内存（LPDDR）里，并在模型 forward 之前提前预取到 GPU。”**
  事实：**MoE 的路由依赖运行时动态隐状态，无法在层循环开始前确定性预取！** 在第 $\ell$ 层 MoE 中，Token 究竟激活哪几个专家，必须等第 $1 \dots \ell-1$ 层以及第 $\ell$ 层 Attention 全部算完、拿到当前隐状态 $\mathbf{h}_t^{(\ell)}$ 后才能由 Router 算出，且在大 Batch 下几乎所有专家都会被某个 Token 触发，强行走 PCIe 会使 GPU 完全卡死在带宽瓶颈上。唯有像 Engram 这样**寻址索引 $100\%$ 仅依赖输入 Token IDs** 的条件记忆模块，才能在进入第 1 层前一次性算完所有层的查表索引并异步预取。
- **误区三：“在实现 mHC 的动态映射计算 $\vec{\mathbf{x}}'_l = \operatorname{RMSNorm}(\vec{\mathbf{x}}_l)$ 与 $\tilde{\mathcal{H}}_l = \alpha_l (\vec{\mathbf{x}}'_l \varphi_l) + \mathbf{b}_l$ 时，必须先在 HBM 中算出归一化后的高维向量 $\vec{\mathbf{x}}'_l \in \mathbb{R}^{1 \times nC}$，再调用矩阵乘算子乘以 $\varphi_l$。”**
  事实：**先对 $nC$ 维宽向量做逐元素除以范数写回 HBM、再读出来做矩阵乘，会引发严重的带宽浪费！** mHC 论文 Section 4.3.1（公式 14–16）指出，由于 RMSNorm 的缩放因子 $\gamma$ 可以预先吸收进投影矩阵 $\varphi_l$，而除以标量范数 $r = \|\vec{\mathbf{x}}_l\|_2 / \sqrt{nC}$ 是线性运算，完全可以在单次遍历 $\vec{\mathbf{x}}_l$ 的融合内核中同时算出矩阵乘结果 $\vec{\mathbf{x}}_l \varphi_l \in \mathbb{R}^{1 \times (n^2+2n)}$ 与范数 $r$，最后在仅有 $n^2+2n = 24$ 个元素的极小系数向量上执行除以 $r$，在数学严格等价的前提下大幅降低了高维显存扫描开销。

---

## 参考

- 选题线索：[ForceInjection/AI-fundamentals (`09_inference_system/engram/01-engram-deep-dive.md`)](https://github.com/ForceInjection/AI-fundamentals/blob/bdc74235f15f6dae5a507f4e651352e6851f904f/09_inference_system/engram/01-engram-deep-dive.md)（固定 commit `bdc7423`）与 [linkedin/Liger-Kernel (`docs/Low-Level-APIs.md`)](https://github.com/linkedin/Liger-Kernel/blob/673ab11ad4807ecfdfeb9b43a0fa1d491db49d42/docs/Low-Level-APIs.md)（固定 commit `673ab11`），独立推导数学机制并扩展源码级对比。
- Cheng et al. (DeepSeek-AI & PKU), [Conditional Memory via Scalable Lookup: A New Axis of Sparsity for Large Language Models](https://arxiv.org/abs/2601.07372)，2026，及官方参考实现 [deepseek-ai/Engram (`engram_demo_v1.py`)](https://github.com/deepseek-ai/Engram/blob/fb7f84a21f91223715394a33a1dc24bbfb7f788e/engram_demo_v1.py)（固定 commit `fb7f84a`）：分词器规范化压缩、多头乘法-XOR 素数哈希、上下文感知门控、多分支参数共享、U 型稀疏容量分配定律及 100B 主机内存卸载实验。
- Xie et al. (DeepSeek-AI), [mHC: Manifold-Constrained Hyper-Connections](https://arxiv.org/abs/2512.24880)，2025：超连接跨层复合映射数值失稳分析、Birkhoff 双随机流形约束、Sinkhorn-Knopp 迭代投影、RMSNorm 重排序融合内核与公式 (20) 选择性重计算最优块长推导。
- Zhu et al., [Hyper-Connections](https://arxiv.org/abs/2409.19606)，ICLR 2025，及 Sinkhorn & Knopp (1967), *Concerning nonnegative matrices and doubly stochastic matrices*：多流残差拓扑与双随机矩阵交替归一化理论基础。

来源访问与示例核验日期：**2026-11-19**。仅执行标准库下分词器规范化压缩、多头乘法-XOR 素数哈希偏移寻址、上下文签名门控、Sinkhorn-Knopp 双随机投影复合增益守恒及 mHC 访存/重计算预算的数值验证，未运行 27B/100B 大模型预训练与多机 H800 PCIe/DualPipe 硬件基准评测。
