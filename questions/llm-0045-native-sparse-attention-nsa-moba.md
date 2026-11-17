---
id: llm-0045
title: 原生稀疏注意力（DeepSeek NSA）与块混合注意力（Moonshot MoBA）是如何通过层级块压缩选择、GQA 组内共享路由与 Online Softmax 合并实现可训练长上下文加速的？
category: llm
tags: [native-sparse-attention, moba, long-context, block-sparse-attention, flash-attention, gqa]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开注意力机制架构指南与长上下文工程题库（rohitg00/ai-engineering-from-scratch / fla-org/flash-linear-attention）扩展改编；DeepSeek NSA（ACL 2025 Best Paper / fla-org）与 Moonshot MoBA（Kimi / MoonshotAI）官方论文及源码核实（见参考）
status: published
updated: 2026-11-18
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-11-18
    updated: 2026-11-18
---

## 问题

在 $64\text{K} \sim 1\text{M}$ Tokens 的超长上下文预训练、思维链（Chain-of-Thought）强化学习与高并发推理中，标准自注意力（Full Softmax Attention）面临双重瓶颈：在 Compute-Bound 的训练与 Prefill 阶段，$\mathcal{O}(T^2)$ 的注意力计算占据了绝大部分算力开销；而在 Memory-Bound 的自回归 Decode 阶段，每生成一个 Token 都必须从高带宽显存（HBM）完整读取全部历史 KV Cache，导致在 $64\text{K}$ 上下文下注意力计算占到了端到端解码延迟的 $70\% \sim 80\%$。

早期的推理期稀疏方案（如 H2O、SnapKV、StreamingLLM、Quest）或离散检索方案（如 ClusterKV、HashAttention）在实际工业部署中暴露出两大根本性缺陷——**“高效推理幻觉（Illusion of Efficient Inference）”**与**“可训练稀疏神话（Myth of Trainable Sparsity）”**：一方面，基于预训练稠密模型在推理期强行剪枝会偏离原始优化轨迹并破坏检索头，且按单头或单 Token 离散抽样会导致非连续显存随机读取，在 GQA（Grouped-Query Attention）下因各头选中块的并集（Union）膨胀而丧失加速比；另一方面，`top-k` 离散采样与聚类不可导，阻断了端到端反向传播。

为彻底攻克上述难题，**DeepSeek 提出了原生稀疏注意力（NSA, Native Sparse Attention，ACL 2025 Best Paper）**，**Moonshot AI（Kimi）同期提出了块混合注意力（MoBA, Mixture of Block Attention）**。请深入剖析以下三个核心问题：

1. **DeepSeek NSA 的三分支层级建模、无辅助损失可导路由与 GQA 组内一致性**：NSA 是如何通过**压缩分支（Compression，$\tilde{K}_t^{\text{cmp}}$）**、**选择分支（Selection，$\tilde{K}_t^{\text{slc}}$）**与**滑动窗口分支（Sliding Window，$\tilde{K}_t^{\text{win}}$）**的门控加权协同，兼顾全局粗粒度扫描、局部细粒度检索与近期上下文建模的？为什么选择分支可以直接复用压缩分支的中间注意力分布 $\mathbf{p}_t^{\text{cmp}}$ 推导空间块重要性得分 $\mathbf{p}_t^{\text{slc}}$（含跨粒度重叠滑窗公式）而无需引入额外辅助损失（Auxiliary Loss）？为什么在 GQA/MQA 架构下必须将同一 GQA Group 内所有 Query 头的重要性分数聚合求和（${\mathbf{p}_t^{\text{slc}}}' = \sum_{h=1}^H \mathbf{p}_t^{\text{slc},(h)}$），并在算子内层循环采用 **Group-Centric（以 GQA 组为中心）**而非 FlashAttention 传统的按时间块加载策略？
2. **Moonshot MoBA 的 MoE 式无参块路由、因果性双重保障与 Online Softmax 跨分支无损合并**：MoBA 是如何遵循“更少先验结构（Less Structure）”原则，将长度为 $N$ 的上下文切分为大小为 $B$ 的块（视为 MoE 专家），并通过无额外参数的块均值池化内积 $s_i = \langle \mathbf{q}, \operatorname{mean\_pool}(\mathbf{K}[I_i]) \rangle$ 动态路由至 $\text{Top-}k$ 历史块的？为了严格维持自回归因果性，为什么 MoBA 必须禁止路由至未来块并**强制将当前块（Current Block）作为“共享专家（Shared Expert）”永远激活**？在底层高效实现（`moba_efficient.py`）中，当当前块因果自注意力（`causal=True`）与历史选中块变长注意力（`causal=False`）分别调用两次 `_flash_attn_varlen_forward` 后，是如何利用两路返回的 $\text{LSE}$（Log-Sum-Exp）统计量完成精确 Online Softmax 合并与反向传播的？
3. **原生可训练稀疏注意力（NSA / MoBA / DSA / MSA）的 2×2 演进象限与生产级工程权衡**：如何从**选择粒度（Block 块级 vs Token 词元级）**与**打分代理（Pooled Keys 池化键免蒸馏 vs Learned Indexer 独立索引器 KL 蒸馏）**两个正交维度统一解构 NSA、MoBA、DeepSeek-V3.2 DSA（Lightning Indexer）与 MiniMax MSA？为什么 NSA 必须使用独立的三套 KV 投影并单设滑动窗口分支以防止“局部捷径学习（Shortcut Learning）”，而 MoBA 则在 SFT 阶段采用尾部层切换回 Full Attention 的混合策略（Layer-wise Hybrid）并在 Decode 阶段回退至稠密注意力？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-11-18

**DeepSeek 原生稀疏注意力（NSA）与 Moonshot 块混合注意力（MoBA）通过将稀疏模式内生嵌入预训练计算图、并与现代 GPU Tensor Core 块级连续访存及 GQA 架构对齐，终结了传统稀疏注意力“只省理论 FLOPs 却不降实际延迟、只支持推理剪枝而不支持端到端训练”的困局：（1）在 DeepSeek NSA 中，每个查询词元 $\mathbf{q}_t$ 并行经过压缩（粗粒度块聚合 $\tilde{K}_t^{\text{cmp}}$）、选择（Top-$n$ 重要连续块原精度保留 $\tilde{K}_t^{\text{slc}}$）与滑动窗口（近期局部窗口 $\tilde{K}_t^{\text{win}}$）三条独立 KV 分支并由 Sigmoid 门控 $g_t^c \in [0,1]$ 加权融合；由于压缩分支本身直接参与最终输出并与语言模型交叉熵损失端到端可导，选择分支直接复用压缩分支的注意力概率 $\mathbf{p}_t^{\text{cmp}}$ 作为块重要性打分即可获得免费梯度（无需额外辅助损失），同时通过同 GQA 组内跨头求和 ${\mathbf{p}_t^{\text{slc}}}' = \sum_{h=1}^H \mathbf{p}_t^{\text{slc},(h)}$ 强制组内所有 Query 头共享同一套稀疏 KV 块索引 $\mathcal{I}_t$，配合 Triton 内核的 Group-Centric 调度将 HBM 访存量在 $64\text{K}$ Decode 下压缩至约 $1/11.6$；（2）Moonshot MoBA 则秉持零新增参数的极简主义，将每个历史 KV 块视为 MoE 专家，以块内 Key 均值池化内积 $s_i = \langle \mathbf{q}, \operatorname{mean\_pool}(\mathbf{K}[I_i]) \rangle$ 路由 Top-$(k-1)$ 历史块，同时将查询所在的“当前块”设为权重恒为 $\infty$ 的静态共享专家（内部施加三角因果掩码），最后将“当前块因果 FlashAttention”与“历史块非因果变长 FlashAttention”的两路局部输出 $\mathbf{O}^s, \mathbf{O}^m$ 通过自然对数空间 $\text{LSE}$（Log-Sum-Exp）缩放因子 $\exp(\text{LSE}_{\text{branch}} - \text{LSE}_{\text{mixed}})$ 精确归并为单一全局 Softmax；（3）在工业演进谱系上，NSA 与 MoBA 构成了“块粒度 + 池化键打分”的两翼，并进一步启发了引入独立可学习索引器与在线 KL 蒸馏的 DeepSeek-V3.2 DSA（词元粒度）与 MiniMax MSA（块粒度 Max-Pool）。**

在深入推导数学公式与算子源码前，建议结合题库内已有相关题目建立完整的长上下文注意力体系：关于标准因果自注意力（Causal Self-Attention）机制，请参阅 [llm-0010](llm-0010-causal-attention-architecture.md)；关于自回归推理中 KV Cache 的显存带宽瓶颈与 Prefill/Decode 算术强度分析，请参阅 [llm-0018](llm-0018-kv-cache-prefill-decode.md)；关于超长上下文在多卡间切分的序列并行（Ring Attention 与 DeepSpeed-Ulysses），请参阅 [llm-0033](llm-0033-ring-attention-ulysses-sequence-parallelism.md)；关于 DeepSeek 通过低秩潜在压缩与矩阵吸收削减 KV Cache 的 MLA 架构，请参阅 [llm-0034](llm-0034-mla-multi-head-latent-attention-rope-absorption.md)；关于推理期 KV Cache 稀疏驱逐算法（StreamingLLM、H2O、SnapKV 与 PyramidKV），请参阅 [llm-0039](llm-0039-kv-cache-eviction-streamingllm-h2o-snapkv-pyramidkv.md)；关于差分注意力（DIFF V1/V2）与门控注意力（Gated Attention）消除注意力沉没及离群值的机制，请参阅 [llm-0044](llm-0044-differential-transformer-gated-attention.md)。

---

### 1. 为什么传统稀疏注意力在现代 GPU 与预训练中会失效？

在 NSA（Yuan et al., ACL 2025 Best Paper, `arXiv:2502.11089`）第 2 节中，作者从硬件体系结构与优化动力学两个维度剖析了既有稀疏注意力方法的结构性缺陷：

| 痛点维度 | 传统稀疏注意力方案（H2O / Quest / ClusterKV / HashAttention 等） | 硬件与训练层面的真实瓶颈 | DeepSeek NSA 与 Moonshot MoBA 的破局设计 |
| :--- | :--- | :--- | :--- |
| **阶段局限性（Phase-Restricted）** | H2O / SnapKV 仅加速 Decode（Prefill 仍需全量算注意力图）；MInference 仅加速 Prefill | 在长文档摘要（Prefill 主导）或长思维链 CoT 推理（Decode 主导）中至少有一个阶段退化为 Full Attention | **全生命周期稀疏**：训练前向、训练反向、Prefill 与（NSA 的）Decode 全链路共享同一套块级稀疏算子 |
| **GQA / MQA 访存并集膨胀** | Quest 等按每个 Query 头独立挑选 Top-$k$ KV 块 | 在 GQA 中 $G = H_Q / H_{KV}$ 个查询头共享同一份 KV Cache；若各头独立选块，HBM 实际加载的 KV 块数是各头选中集合的**并集（Union）** $\big|\bigcup_{h=1}^G \mathcal{I}_t^{(h)}\big| \gg k$，计算省了但带宽没省 | **GQA 组内一致选块（NSA Eq. 10）**：对同一 GQA 组内所有 Query 头的块重要性分数求和后统一选出共享的 Top-$n$ 块 |
| **细粒度离散访存与 Tensor Core 失配** | HashAttention / MagicPIG 按单 Token 哈希或 LSH 抽样 | 在 HBM 中随机 gather 离散单 Token 会彻底破坏缓存行合并访存（Coalesced Memory Access），无法调用基于连续 Tile 的 FlashAttention Tensor Core 指令 | **空间连续块（Blockwise Contiguity）**：以 $32 \sim 4096$ 的连续 Token 块为最小路由与加载单元，完美契合 SRAM Tile 块矩阵乘 |
| **不可导算子与训推分布偏移** | 推理期对 Dense 预训练模型直接剪枝（Top $20\%$ 注意力仅覆盖约 $70\%$ 权重）；或训练期引入 $k$-means 聚类 / 辅助 Loss | 事后剪枝直接摧毁预训练形成的长程检索头（Retrieval Heads）；而独立打分网络依赖辅助 MSE Loss 训练，既增加算子开销又损害主任务收敛 | **原生可导代理打分**：直接用参与主任务输出计算的块压缩键（NSA）或块均值键（MoBA）内积打分，主损失梯度天然回传至 Key/Query 投影 |

---

### 2. DeepSeek NSA：三分支层级稀疏、跨粒度重要性推导与 Group-Centric 内核

#### （1）三分支并行重映射与门控聚合框架
给定位置 $t$ 的查询向量 $\mathbf{q}_t \in \mathbb{R}^{d_k}$ 及历史键值序列 $\mathbf{k}_{:t} \in \mathbb{R}^{d_k \times t}, \mathbf{v}_{:t} \in \mathbb{R}^{d_v \times t}$，NSA（论文公式 3–6 及官方仓库 `fla-org/native-sparse-attention` 中 `modeling_nsa.py`）通过三种不同的映射策略 $\mathcal{C} = \{\text{cmp}, \text{slc}, \text{win}\}$ 构造紧凑键值表示 $(\tilde{K}_t^c, \tilde{V}_t^c)$，每个分支独立执行 Softmax 注意力后，由输入特征经线性层加 Sigmoid 生成的门控标量 $g_t^c \in [0, 1]$ 加权求和（`g_cmp, g_slc, g_swa = self.g_proj(hidden_states).sigmoid().unbind(-1)`）：

$$\mathbf{o}_t^* = \sum_{c \in \{\text{cmp}, \text{slc}, \text{win}\}} g_t^c \cdot \operatorname{Attn}\!\left(\mathbf{q}_t, \tilde{K}_t^c, \tilde{V}_t^c\right), \qquad N_t = \sum_{c \in \mathcal{C}} \operatorname{size}\!\left[\tilde{K}_t^c\right] \ll t$$

三条分支各司其职，且为了防止跨分支梯度干扰与局部捷径学习（Shortcut Learning），论文明确为三条分支配备**独立的键值序列表示**：
1. **压缩分支（Token Compression, $\text{cmp}$）—— 捕获全局粗粒度高阶语义**：
   将历史键值按块长 $l$（如 $l=32$）、滑窗步长 $d$（如 $d=16$，通常取 $d < l$ 以利用块间重叠缓解边界信息割裂）切分为 $\left\lfloor \frac{t - l}{d} \right\rfloor$ 个块，通过带块内位置编码的可学习 MLP $\varphi$（或轻量均值池化）将每个块压缩为单个代表性 Token（论文公式 7）：
   $$\tilde{K}_t^{\text{cmp}} = f_K^{\text{cmp}}(\mathbf{k}_{:t}) = \left\{ \varphi\!\left(\mathbf{k}_{id+1 : id+l}\right) \;\middle|\; 0 \le i \le \left\lfloor \frac{t - l}{d} \right\rfloor - 1 \right\} \in \mathbb{R}^{d_k \times \left\lfloor \frac{t - l}{d} \right\rfloor}$$
2. **选择分支（Token Selection, $\text{slc}$）—— 按需召回细粒度关键上下文**：
   仅靠压缩块会丢失精确字面细节（如代码变量名、数字与密码）。选择分支按选择块粒度 $l'$（如 $l'=64$）挑选重要性排名最高的前 $n$ 个块（如 $n=16$，含固定激活的 $1$ 个首块与 $2$ 个局部块），将这些块内的原始未压缩键值拼接为 $\tilde{K}_t^{\text{slc}} \in \mathbb{R}^{d_k \times n l'}$。
3. **滑动窗口分支（Sliding Window, $\text{win}$）—— 隔离局部强相关性，防止捷径坍缩**：
   由于自然语言中近期相邻 Token 的局部相关性极易收敛并主导早期梯度，若将局部 Token 与远距离压缩/选择 Token 混在同一个 Softmax 中，模型会迅速走“只看局部窗口”的捷径（Shortcut），导致压缩与选择分支得不到有效训练。NSA 专门剥离出维护最近 $w$ 个 Token（如 $w=512$）的独立滑动窗口分支 $\tilde{K}_t^{\text{win}} = \mathbf{k}_{t-w:t}, \tilde{V}_t^{\text{win}} = \mathbf{v}_{t-w:t}$，使长程分支能够专注于学习全局检索模式。

#### （2）零开销块重要性推导公式与 GQA 组内一致性聚合
如何为选择分支的候选块打分？若像传统方法那样额外引入路由网络并用辅助 Loss 拟合注意力分布，不仅增加计算开销，还会拖累主模型精度。NSA 巧妙地利用了压缩分支在计算自身注意力时已经生成的中间 Softmax 概率分布（论文公式 8）：

$$\mathbf{p}_t^{\text{cmp}} = \operatorname{Softmax}\!\left(\frac{\mathbf{q}_t^\top \tilde{K}_t^{\text{cmp}}}{\sqrt{d_k}}\right) \in \mathbb{R}^{\left\lfloor \frac{t - l}{d} \right\rfloor}$$

- **为什么压缩分支的概率天然可学？** 因为压缩分支的输出 $\operatorname{Attn}(\mathbf{q}_t, \tilde{K}_t^{\text{cmp}}, \tilde{V}_t^{\text{cmp}}) = \tilde{V}_t^{\text{cmp}} \mathbf{p}_t^{\text{cmp}}$ 直接乘以 $g_t^{\text{cmp}}$ 进入最终输出 $\mathbf{o}_t^*$，语言建模损失的梯度会直接通过 $\mathbf{p}_t^{\text{cmp}}$ 回传给 $\mathbf{q}_t$ 和压缩算子 $\varphi(\mathbf{k})$，迫使 $\mathbf{p}_t^{\text{cmp}}$ 自动把高概率分配给真正对预测下一个词有用的历史块！
- **跨粒度重叠块映射公式（论文公式 9）**：
  - 当选择块与压缩块采用相同非重叠切分（即 $l' = l = d$）时，选择块重要性得分直接等于压缩块概率：$\mathbf{p}_t^{\text{slc}} = \mathbf{p}_t^{\text{cmp}}$；
  - 当压缩块带步长重叠且与选择块大小不同（满足整除关系 $d \mid l$ 且 $d \mid l'$，例如论文实验配置 $l=32, d=16, l'=64$，此时 $\frac{l'}{d}=4, \frac{l}{d}=2$）时，第 $j$ 个选择块（覆盖区间 $[j l', (j+1)l')$）与周围所有产生空间重叠的压缩块概率按二重求和映射（论文公式 9）：
    $$\mathbf{p}_t^{\text{slc}}[j] = \sum_{m=0}^{\frac{l'}{d} - 1} \sum_{n=0}^{\frac{l}{d} - 1} \mathbf{p}_t^{\text{cmp}}\!\left[\frac{l'}{d} j + m + n\right]$$
- **GQA 组内一致性选块（论文公式 10–12）**：
  在采用 GQA（设每组含 $H = H_Q / H_{KV}$ 个查询头，如 DeepSeek 27B 实验中 $H_Q=64, H_{KV}=4 \implies H=16$）的模型中，为了杜绝不同查询头各自拉取不同 KV 块造成的 HBM 读取并集膨胀，NSA 强制将同一 GQA Group 内全部 $H$ 个查询头的块重要性分数相加（对应 `naive.py` 第 205 行 `attn_select = attn_select.view(B, H, G, T, C).sum(2)`）：
  $${\mathbf{p}_t^{\text{slc}}}' = \sum_{h=1}^{H} \mathbf{p}_t^{\text{slc},(h)}, \qquad \mathcal{I}_t = \left\{ i \;\middle|\; \operatorname{rank}\!\left({\mathbf{p}_t^{\text{slc}}}'[i]\right) \le n \right\}, \qquad \tilde{K}_t^{\text{slc}} = \operatorname{Cat}\!\left[\left\{ \mathbf{k}_{i l' + 1 : (i+1) l'} \;\middle|\; i \in \mathcal{I}_t \right\}\right]$$

#### （3）硬件对齐的 Group-Centric Triton 内核与算术强度平衡
为什么选择分支不能直接照搬 FlashAttention-2 的“沿时间维加载连续 $B_q$ 个位置的单头 Query 到 SRAM”？
- 因为在序列维度上相邻的不同位置 $t$ 和 $t+1$，其动态选出的 Top-$n$ 历史块集合 $\mathcal{I}_t$ 与 $\mathcal{I}_{t+1}$ 往往互不相同（Disjoint），若外层按连续时间位置打包 Query，内层循环依然要为每个位置读取各自不同的 KV 块，SRAM 复用率极低。
- **NSA 的 Group-Centric 调度策略（论文 Section 3.4 & Figure 3）**：
  1. **Grid 外层循环遍历序列位置 $t$ 与 GQA 组索引 $g$**：每个 Triton 线程块（CTA）负责单个时间步 $t$ 上的**整个 GQA 查询头组** $\mathbf{Q}_{t, g} \in \mathbb{R}^{H \times d_k}$（例如 $H=16, d_k=192$），一次性将其驻留于片上 SRAM；
  2. **内层循环顺序拉取组内共享的稀疏 KV 块**：由于组内全部 $H$ 个查询头严格共享同一套块索引列表 $\mathcal{I}_{t,g}$（共 $n$ 个块，每个块长 $l'=64$），内层循环只需从 HBM 连续加载一次 $\mathbf{K}_{\text{tile}} \in \mathbb{R}^{B_k \times d_k}$ 与 $\mathbf{V}_{\text{tile}} \in \mathbb{R}^{B_k \times d_v}$，即可在 SRAM 内立即与全部 $H=16$ 个查询头执行矩阵乘（GEMM）！
  3. **解码期（Decode）HBM 访存量定量核算（论文 Table 4）**：
     对于缓存长度为 $s$ 的序列，单步 Decode 仅需从 HBM 读取最多 $\left\lfloor \frac{s-l}{d} \right\rfloor$ 个压缩 Token、$n l'$ 个选择 Token 以及 $w$ 个滑动窗口 Token：
     $$N_{\text{access}}(s) \approx \left\lfloor \frac{s - l}{d} \right\rfloor + n \cdot l' + w$$
     代入论文标准配置（$l=32, d=16, l'=64, n=16, w=512$）：当 $s = 65,536$（$64\text{K}$）时，压缩分支约读取 $4096$ 个 Token，选择分支读取 $16 \times 64 = 1024$ 个 Token，滑窗读取 $512$ 个 Token，总计仅需访问 $4096 + 1024 + 512 = 5632$ 个等效 Token，相比 Full Attention 的 $65,536$ 个 Token 实现了 **$65536 / 5632 \approx 11.6\times$ 的理论与实测解码加速**（训练前向与反向在 $64\text{K}$ 下亦分别取得 $9.0\times$ 与 $6.0\times$ 加速）。

```
DeepSeek NSA 三分支层级稀疏架构与 Group-Centric 内核数据流：

                 输入序列隐状态 X_t (位置 t, GQA Group g 含 H=16 个 Query 头)
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          ▼                            ▼                            ▼
  [分支 1: Token Compression]  [分支 2: Token Selection]    [分支 3: Sliding Window]
  按块长 l=32, 步长 d=16 聚合   复用 p_t^cmp 映射至 l'=64 块  截取最近 w=512 个局部 Token
  K_cmp, V_cmp (共 ~(s-l)/d)   GQA 组内 H 头求和取 Top-n=16   K_win, V_win (防止局部捷径)
          │                            │                            │
          ├───► p_t^cmp ───────────────┘ (零辅助 Loss 提供块重要性路由信号)
          ▼                            ▼                            ▼
     Attn_cmp(q_t)               Attn_slc(q_t)                Attn_win(q_t)
  (标准 FlashAttention)     (Group-Centric Triton 内核:     (标准因果滑窗内核)
                             SRAM 驻留 [H, d_k] Query 组,
                             HBM 连续拉取共享 I_t 块 Tile)
          │                            │                            │
          └──────────► × g_t^cmp   +   × g_t^slc   +   × g_t^win ◄──┘
                                       │
                                       ▼
                        最终注意力输出 o_t* (64K 仅读 5632 Tokens)
```

---

### 3. Moonshot MoBA：MoE 式块路由、因果双重保护与 Online Softmax LSE 合并

与 NSA 构造三套独立 KV 分支不同，Moonshot AI（Lu et al., `arXiv:2502.13189`）提出的 **MoBA（Mixture of Block Attention）** 追求**零新增参数**与**与预训练 Full Attention 模型无缝切换**的极简架构。

#### （1）MoE 式无参块路由与双重因果性约束（Causality Preservation）
设上下文总长度为 $N$，被均匀切分为 $n = N / B$ 个非重叠连续块，第 $i$ 个块（$i \in \{1, \dots, n\}$）覆盖的位置区间为 $I_i = [(i-1)B + 1, \, iB]$。MoBA 将每个历史 KV 块视为一个 MoE 专家，查询向量 $\mathbf{q} \in \mathbb{R}^{1 \times d}$（处于位置 $\operatorname{pos}(\mathbf{q})$，所属当前块编号为 $c = \lceil \operatorname{pos}(\mathbf{q}) / B \rceil$）仅对选中的块下标集合 $I = \bigcup_{g_i > 0} I_i$ 计算注意力（论文公式 2–6）：

$$\operatorname{MoBA}(\mathbf{q}, \mathbf{K}, \mathbf{V}) = \operatorname{Softmax}\!\left(\frac{\mathbf{q} \mathbf{K}[I]^\top}{\sqrt{d}}\right) \mathbf{V}[I]$$

为了在不引入任何额外可训练路由矩阵的前提下衡量查询 $\mathbf{q}$ 与第 $i$ 个块的亲和度，MoBA 直接计算 $\mathbf{q}$ 与该块内所有 Key 向量沿序列维度的**均值池化（Mean Pooling）**的内积，并施加两条严格的因果性规则（对照官方源码 `MoonshotAI/MoBA` 中 `moba/moba_naive.py` 第 46–65 行与 `moba/moba_efficient.py` 第 335–365 行）：

$$s_i = \begin{cases} -\infty, & \text{若 } i > c \quad \text{（规则 1：严禁路由至任何未来块）} \\ +\infty, & \text{若 } i = c \quad \text{（规则 2：强制激活当前块，类比 MoE 共享专家）} \\ \left\langle \mathbf{q}, \, \frac{1}{|I_i|} \sum_{t \in I_i} \mathbf{K}_t \right\rangle, & \text{若 } i < c \quad \text{（历史完整块：FP32 精度内积打分）} \end{cases}$$

$$g_i = \begin{cases} 1, & s_i \in \operatorname{Topk}\!\left(\{s_j \mid j \in [n]\}, \, k\right) \\ 0, & \text{otherwise} \end{cases}$$

- **为什么当前块（$i = c$）不能用 $\operatorname{mean\_pool}(\mathbf{K}[I_c])$ 打分，而必须强制设为 $+\infty$（必选）？**
  因为在一个长度为 $B$（如 $B=512$ 或 $4096$）的当前块内部，当查询位置 $\operatorname{pos}(\mathbf{q})$ 处于块中间时，整块均值 $\operatorname{mean\_pool}(\mathbf{K}[I_c])$ 包含了 $\operatorname{pos}(\mathbf{q})$ 之后的**未来 Token 的 Key 信息**！若用整块均值参与路由打分，就会发生严重的未来信息泄漏（Causal Leakage）；反之，若强制令每个查询必定路由到其所属的当前块（相当于在 $\text{Top-}k$ 配额中固定占掉 $1$ 个名额作為“共享专家”，仅在 $i < c$ 的历史块中动态挑选 $\text{Top-}(k-1)$ 个块），并在当前块内部施加下三角因果掩码（Causal Mask），就既从根源上杜绝了块均值泄漏，又天然保证了局部上下文的连续覆盖！

#### （2）双路变长 FlashAttention 拆分与 Online Softmax（LSE）精确合并推导
在 GPU 高性能实现（`moba/moba_efficient.py` 的 `MixedAttention` 类）中，对于位置处于块 $c$ 的查询 $\mathbf{q}$，它需要关注的键值由两部分异构集合组成：
1. **当前块内满足 $t \le \operatorname{pos}(\mathbf{q})$ 的前缀 Token（记为集合 $\mathcal{S}_{\text{self}}$）**：需要带**下三角因果掩码（`causal=True`）**的自注意力；
2. **动态选中的 $k-1$ 个完整历史块内的全部 Token（记为集合 $\mathcal{S}_{\text{moba}}$）**：因为历史块中的所有位置均严格早于当前块（$t < (c-1)B + 1 \le \operatorname{pos}(\mathbf{q})$），所以查询对这些历史块做注意力时**完全不需要因果掩码（`causal=False`）**！

MoBA 将这两部分拆成两次独立的 `_flash_attn_varlen_forward` 调用：
- 第一路对所有块执行块内对角线因果注意力（`causal=True`），返回局部归一化输出 $\mathbf{O}^{\text{self}} \in \mathbb{R}^d$ 与自然对数空间的 Log-Sum-Exp 统计量 $L^{\text{self}} = \ln \sum_{t \in \mathcal{S}_{\text{self}}} \exp\!\left(\frac{\mathbf{q} \mathbf{K}_t^\top}{\sqrt{d}}\right)$；
- 第二路将选中同一历史 KV 块的所有查询按 MoE 专家分组重排（`moba_q`），调用非因果变长 FlashAttention（`causal=False`），并需要注意**剔除没有任何 Query 选中的“零查询历史块专家（`zero_expert_count > 0`）”**以防止空序列在反向传播中产生 `NaN` 梯度，返回历史块聚合输出 $\mathbf{O}^{\text{moba}} \in \mathbb{R}^d$ 与其对应的 $L^{\text{moba}} = \ln \sum_{t \in \mathcal{S}_{\text{moba}}} \exp\!\left(\frac{\mathbf{q} \mathbf{K}_t^\top}{\sqrt{d}}\right)$。

如何将各自独立做过 Softmax 归一化的 $\mathbf{O}^{\text{self}}$ 与 $\mathbf{O}^{\text{moba}}$ 无损还原为在并集 $\mathcal{S}_{\text{self}} \cup \mathcal{S}_{\text{moba}}$ 上的全局精确 Softmax 输出 $\mathbf{O}$？根据 Online Softmax 恒等式（对应 `moba_efficient.py` 第 132–166 行）：

$$\begin{aligned}
m &= \max\!\left(L^{\text{self}}, \, L^{\text{moba}}\right) \\
L^{\text{mixed}} &= m + \ln\!\left( \exp\!\left(L^{\text{self}} - m\right) + \exp\!\left(L^{\text{moba}} - m\right) \right) = \ln\!\left( \sum_{t \in \mathcal{S}_{\text{self}} \cup \mathcal{S}_{\text{moba}}} \exp\!\left(\frac{\mathbf{q} \mathbf{K}_t^\top}{\sqrt{d}}\right) \right) \\
\mathbf{O} &= \exp\!\left(L^{\text{self}} - L^{\text{mixed}}\right) \cdot \mathbf{O}^{\text{self}} + \exp\!\left(L^{\text{moba}} - L^{\text{mixed}}\right) \cdot \mathbf{O}^{\text{moba}}
\end{aligned}$$

在反向传播（`MixedAttention.backward`，第 208–264 行）中，只需将前向合并得到的全局输出 $\mathbf{O}$ 与全局对数配分函数 $L^{\text{mixed}}$（即 `mixed_attn_vlse`）直接传回给两次 `_flash_attn_varlen_backward`，FlashAttention 内核即可在不存储完整注意力矩阵的情况下，直接算出关于 $\mathbf{Q}, \mathbf{K}, \mathbf{V}$ 的精确梯度！

---

### 4. 原生可训练稀疏注意力的 2×2 演进矩阵（NSA / MoBA / DSA / MSA）

结合工业界最新演进（DeepSeek-V3.2 的 **DSA** `arXiv:2512.02556`、GLM-5.2 的 **IndexShare** 以及 MiniMax 的 **MSA** `arXiv:2606.13392`），所有原生可训练稀疏注意力本质上都是在求解同一个核心矛盾：**如何用一个远低于 $\mathcal{O}(T^2)$ 的廉价代理（Proxy）为候选集合打分并取 $\text{Top-}k$，同时让打分器获得有效梯度**。按**选择粒度（Granularity）**与**打分代理（Scoring Proxy）**两个正交轴，四大主流架构构成如下完整的 $2 \times 2$ 矩阵：

| 架构方案 | 选择粒度 | 打分代理（Scoring Proxy） | 梯度获取与训练范式 | 自回归 Decode 行为 | 核心优势与工程边界 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DeepSeek NSA**<br>(`arXiv:2502.11089`) | **Block 块级**<br>（+ 压缩与滑窗） | **池化/压缩键复用**<br>（直接复用 $\mathbf{p}_t^{\text{cmp}}$） | **主损失直接回传**（免辅助 KL 损失，支持从零预训练） | **原生稀疏加速**<br>（GQA 组共享选块，$64\text{K}$ 提速 $11.6\times$） | 三分支信息无损，训推全链路加速；但引入三套 KV 与门控参数，需定制 Group-Centric 内核 |
| **Moonshot MoBA**<br>(`arXiv:2502.13189`) | **Block 块级**<br>（单路由分支） | **块均值池化键**<br>（$\langle \mathbf{q}, \bar{\mathbf{k}}_b \rangle$） | **主损失直接回传**（零新增参数，可与 Full Attention 动态互切） | **回退至稠密注意力**<br>（Prefill 用 MoBA，Decode 切回 Full） | 极简零参数，完美复用 `flash_attn_varlen`；但单步 Decode 无批量 Query 分摊路由，且 SFT 需尾部层混合 |
| **DeepSeek-V3.2 DSA**<br>(`arXiv:2512.02556`) | **Token 词元级**<br>（如选 $k=2048$） | **独立轻量索引器**<br>（FP8 Lightning Indexer） | **在线 KL 蒸馏对齐**<br>（以主注意力为 Teacher 蒸馏 Indexer） | **稀疏加速**<br>（配合 MLA 的单共享潜变量 MQA 模式） | Token 级挑选精度最高，支持将 Dense 预训练模型后训练改造为稀疏；GLM-5.2 通过每 $4$ 层共享一次索引（IndexShare）再砍 $2.9\times$ 索引开销 |
| **MiniMax MSA**<br>(`arXiv:2606.13392`) | **Block 块级**<br>（GQA 组共享） | **独立索引器 + 块内 Max-Pool**<br>（$S_{t,b}^g = \max_{i \in B_b} I_{t,i}^g$） | **从零预训练 + 在线 KL 蒸馏**<br>（含 Stop-Grad 与 Warm-up 稳定器） | **原生稀疏加速**<br>（保留未压缩 KV，块级连续读取） | 解决了均值池化键打分无法主动压低未选中长尾块的缺陷，兼顾块级连续访存与高稀疏率检索 |

---

### 5. Python 3 标准库可运行仿真：NSA 重叠块映射、GQA 共享访存与 MoBA LSE 合并

下面的自包含脚本仅使用 Python 3 标准库（`math`、`typing`），完整实现了：
1. **NSA 论文公式 (9) 跨粒度重叠块重要性推导**（验证 $l=32, d=16, l'=64$ 下压缩块概率向选择块的精确映射）；
2. **NSA 论文公式 (10) GQA 组内共享选块 vs 独立选块（如 Quest）的 HBM 访存并集对比**；
3. **MoBA 块均值路由（含当前块强制自路由与未来块掩码）及双路 FlashAttention LSE Online Softmax 合并等价性证明**；
4. **NSA 论文 Table 4 在 $64\text{K}$ 上下文下的 Decode 访存预算与理论加速比核算**。

```python
import math
from typing import Dict, List, Tuple


def dot_vec(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def softmax_with_lse(scores: List[float]) -> Tuple[List[float], float]:
    """返回概率分布以及自然对数空间的 Log-Sum-Exp (LSE)"""
    valid = [s for s in scores if s > -1e20]
    if not valid:
        return [0.0 for _ in scores], float("-inf")
    m = max(valid)
    exps = [math.exp(s - m) if s > -1e20 else 0.0 for s in scores]
    sum_exp = sum(exps)
    lse = m + math.log(sum_exp)
    probs = [e / sum_exp for e in exps]
    return probs, lse


def simulate_nsa_stride_to_selection_mapping(
    p_cmp: List[float], l_cmp: int, d_stride: int, l_slc: int
) -> List[float]:
    """验证 NSA 论文公式 (9)：从重叠压缩块概率 p_cmp 推导选择块重要性得分 p_slc"""
    assert l_cmp % d_stride == 0 and l_slc % d_stride == 0
    m_span = l_slc // d_stride
    n_span = l_cmp // d_stride
    num_slc_blocks = (len(p_cmp) - (n_span - 1)) // m_span
    p_slc = []
    for j in range(num_slc_blocks):
        score_j = 0.0
        for m in range(m_span):
            for n in range(n_span):
                idx = m_span * j + m + n
                if idx < len(p_cmp):
                    score_j += p_cmp[idx]
        p_slc.append(round(score_j, 4))
    return p_slc


def compare_gqa_kv_block_selection_memory(
    head_block_scores: List[List[float]], top_n: int, block_size: int
) -> Dict[str, object]:
    """对比按查询头独立选块（Independent）与 NSA GQA 组内共享选块（Group-Consistent）的 HBM 读取开销"""
    num_heads = len(head_block_scores)
    num_blocks = len(head_block_scores[0])

    # 1. 每个 Query 头独立取 Top-n，GQA 下需从 HBM 读取所有头选中块的并集 (Union)
    independent_union = set()
    for h in range(num_heads):
        ranked = sorted(
            range(num_blocks), key=lambda b: head_block_scores[h][b], reverse=True
        )
        independent_union.update(ranked[:top_n])

    # 2. NSA 公式 (10)：先对同 GQA Group 内所有头的重要性得分求和，再共享选出 Top-n
    group_sum_scores = [
        sum(head_block_scores[h][b] for h in range(num_heads))
        for b in range(num_blocks)
    ]
    shared_selected = sorted(
        range(num_blocks), key=lambda b: group_sum_scores[b], reverse=True
    )[:top_n]

    tokens_indep = len(independent_union) * block_size
    tokens_shared = len(shared_selected) * block_size
    return {
        "independent_blocks_loaded": len(independent_union),
        "shared_blocks_loaded": len(shared_selected),
        "independent_tokens": tokens_indep,
        "shared_tokens": tokens_shared,
        "memory_reduction_ratio": round(tokens_indep / tokens_shared, 2),
        "shared_selected_indices": sorted(shared_selected),
    }


def verify_moba_online_softmax_fusion(
    q: List[float],
    keys: List[List[float]],
    values: List[List[float]],
    query_pos: int,
    block_size: int,
    top_k: int,
) -> Dict[str, object]:
    """验证 MoBA 的块路由（含当前块强制自路由）及双路 FlashAttention LSE Online Softmax 合并等价性"""
    scale = len(q) ** -0.5
    num_blocks = math.ceil(len(keys) / block_size)
    current_blk = query_pos // block_size
    d_val = len(values[0])

    # 1. 计算各块 Mean-Pool Key 与门控亲和度（遵守因果掩码与当前块强制激活）
    gate_scores = []
    for b in range(num_blocks):
        b_start = b * block_size
        b_end = min(len(keys), (b + 1) * block_size)
        if b > current_blk:
            gate_scores.append(float("-inf"))  # 未来块严禁路由
        elif b == current_blk:
            gate_scores.append(float("inf"))   # 当前块强制路由 (Shared Expert)
        else:
            mean_k = [
                sum(keys[t][d] for t in range(b_start, b_end)) / (b_end - b_start)
                for d in range(len(q))
            ]
            gate_scores.append(dot_vec(q, mean_k))

    ranked_blocks = sorted(range(num_blocks), key=lambda b: gate_scores[b], reverse=True)
    selected_blocks = sorted(ranked_blocks[: min(top_k, current_blk + 1)])
    hist_blocks = [b for b in selected_blocks if b < current_blk]

    # 2. 路径 A：直接拼接所有选中块内的合法因果 Token 计算精确全局 Softmax
    all_indices = [
        t
        for b in selected_blocks
        for t in range(b * block_size, min(len(keys), (b + 1) * block_size))
        if t <= query_pos
    ]
    all_logits = [dot_vec(q, keys[t]) * scale for t in all_indices]
    all_probs, _ = softmax_with_lse(all_logits)
    out_exact = [
        round(
            sum(all_probs[idx] * values[all_indices[idx]][d] for idx in range(len(all_indices))),
            6,
        )
        for d in range(d_val)
    ]

    # 3. 路径 B：MoBA MixedAttention 双路独立计算 + Online Softmax LSE 合并
    cur_indices = [
        t
        for t in range(current_blk * block_size, min(len(keys), (current_blk + 1) * block_size))
        if t <= query_pos
    ]
    cur_probs, lse_self = softmax_with_lse([dot_vec(q, keys[t]) * scale for t in cur_indices])
    out_self = [
        sum(cur_probs[idx] * values[cur_indices[idx]][d] for idx in range(len(cur_indices)))
        for d in range(d_val)
    ]

    hist_indices = [
        t
        for b in hist_blocks
        for t in range(b * block_size, min(len(keys), (b + 1) * block_size))
    ]
    hist_probs, lse_moba = softmax_with_lse([dot_vec(q, keys[t]) * scale for t in hist_indices])
    out_moba = [
        sum(hist_probs[idx] * values[hist_indices[idx]][d] for idx in range(len(hist_indices)))
        for d in range(d_val)
    ]

    # Online Softmax LSE 精确归并（对应 moba_efficient.py MixedAttention.forward）
    max_lse = max(lse_self, lse_moba)
    lse_mixed = max_lse + math.log(
        math.exp(lse_self - max_lse) + math.exp(lse_moba - max_lse)
    )
    factor_self = math.exp(lse_self - lse_mixed)
    factor_moba = math.exp(lse_moba - lse_mixed)
    out_fused = [
        round(factor_self * out_self[d] + factor_moba * out_moba[d], 6)
        for d in range(d_val)
    ]
    out_naive_sum = [round(out_self[d] + out_moba[d], 6) for d in range(d_val)]

    return {
        "selected_blocks": selected_blocks,
        "factor_self": round(factor_self, 4),
        "factor_moba": round(factor_moba, 4),
        "out_exact": out_exact,
        "out_fused": out_fused,
        "out_naive_sum": out_naive_sum,
    }


def evaluate_nsa_decoding_memory_budget(
    seq_len: int, d_stride: int, l_slc: int, top_n: int, win_size: int
) -> Dict[str, float]:
    """核算 NSA 在自回归 Decode 阶段的等效读取 Token 数与加速比（对齐论文 Table 4）"""
    nsa_tokens = (seq_len // d_stride) + top_n * l_slc + win_size
    speedup = round(seq_len / nsa_tokens, 1)
    return {
        "seq_len": seq_len,
        "nsa_tokens": nsa_tokens,
        "expected_speedup": speedup,
    }


# --- 1. 验证 NSA 跨粒度重叠块重要性映射（公式 9：l=32, d=16, l'=64） ---
p_cmp_demo = [0.04, 0.08, 0.22, 0.28, 0.14, 0.09, 0.06, 0.05, 0.04]
p_slc_demo = simulate_nsa_stride_to_selection_mapping(
    p_cmp_demo, l_cmp=32, d_stride=16, l_slc=64
)
assert p_slc_demo == [1.34, 0.58]

# --- 2. 验证 GQA 组内共享选块 vs 独立选块的 HBM 访存差异 ---
gqa_scores_demo = [
    [0.42, 0.08, 0.31, 0.05, 0.04, 0.03, 0.04, 0.03],
    [0.38, 0.29, 0.09, 0.08, 0.05, 0.04, 0.04, 0.03],
    [0.35, 0.07, 0.11, 0.30, 0.06, 0.04, 0.04, 0.03],
    [0.40, 0.06, 0.08, 0.07, 0.28, 0.04, 0.04, 0.03],
]
gqa_mem_res = compare_gqa_kv_block_selection_memory(
    gqa_scores_demo, top_n=2, block_size=64
)
assert gqa_mem_res["independent_blocks_loaded"] == 5
assert gqa_mem_res["shared_blocks_loaded"] == 2
assert gqa_mem_res["memory_reduction_ratio"] == 2.5
assert gqa_mem_res["shared_selected_indices"] == [0, 2]

# --- 3. 验证 MoBA 块路由与 Online Softmax LSE 跨分支无损合并 ---
q_demo = [1.2, 0.8]
keys_demo = [
    [0.1, 0.2], [0.2, 0.1],    # Block 0 (低相关历史块)
    [1.5, 1.0], [1.2, 0.9],    # Block 1 (高相关历史块)
    [-0.5, 0.1], [-0.4, 0.2],  # Block 2 (无关历史块)
    [0.9, 1.1], [0.4, 0.3],    # Block 3 (当前块, query_pos=6 位于该块首位置)
]
vals_demo = [
    [1.0, 0.0], [1.2, 0.1],
    [5.0, 2.0], [4.0, 3.0],
    [0.0, 1.0], [0.1, 0.9],
    [2.0, 4.0], [9.0, 9.0],    # index=7 为未来 Token (t > query_pos=6)，被因果掩码屏蔽
]
moba_res = verify_moba_online_softmax_fusion(
    q_demo, keys_demo, vals_demo, query_pos=6, block_size=2, top_k=2
)
assert moba_res["selected_blocks"] == [1, 3]
assert moba_res["factor_self"] == 0.2685
assert moba_res["factor_moba"] == 0.7315
assert moba_res["out_fused"] == moba_res["out_exact"] == [3.885161, 2.846327]
assert moba_res["out_naive_sum"] == [6.57716, 6.42284]

# --- 4. 验证 NSA 64K 上下文 Decode 访存预算（论文 Table 4） ---
budget_64k = evaluate_nsa_decoding_memory_budget(
    seq_len=65536, d_stride=16, l_slc=64, top_n=16, win_size=512
)
assert budget_64k["nsa_tokens"] == 5632
assert budget_64k["expected_speedup"] == 11.6

print(
    f"1. NSA Stride Mapping (l=32, d=16 -> l'=64): p_slc={p_slc_demo}"
)
print(
    f"2. GQA KV Selection: indep_blocks={gqa_mem_res['independent_blocks_loaded']} "
    f"({gqa_mem_res['independent_tokens']} toks) vs shared_blocks={gqa_mem_res['shared_blocks_loaded']} "
    f"({gqa_mem_res['shared_tokens']} toks, {gqa_mem_res['memory_reduction_ratio']}x saved)"
)
print(
    f"3. MoBA LSE Fusion: blocks={moba_res['selected_blocks']}, "
    f"factors=({moba_res['factor_self']}, {moba_res['factor_moba']}), "
    f"fused={moba_res['out_fused']} == exact={moba_res['out_exact']}"
)
print(
    f"4. NSA 64K Decode Budget: full={budget_64k['seq_len']} -> "
    f"nsa={budget_64k['nsa_tokens']} toks ({budget_64k['expected_speedup']}x speedup)"
)
print("All Native Sparse Attention (NSA) and MoBA assertions passed!")
```

实际运行输出：

```text
1. NSA Stride Mapping (l=32, d=16 -> l'=64): p_slc=[1.34, 0.58]
2. GQA KV Selection: indep_blocks=5 (320 toks) vs shared_blocks=2 (128 toks, 2.5x saved)
3. MoBA LSE Fusion: blocks=[1, 3], factors=(0.2685, 0.7315), fused=[3.885161, 2.846327] == exact=[3.885161, 2.846327]
4. NSA 64K Decode Budget: full=65536 -> nsa=5632 toks (11.6x speedup)
All Native Sparse Attention (NSA) and MoBA assertions passed!
```

---

## 延伸 / 追问

**追问 1：为什么 Moonshot MoBA 在监督微调（SFT）阶段观察到纯稀疏模型的性能退化，并提出了“尾部若干层切回 Full Attention（Layer-wise Hybrid）”的训练方案？而在自回归 Decode 阶段，为什么 MoBA 选择直接回退到稠密 Full Attention？**
1. **SFT 阶段 Prompt Loss Masking 引发的稀疏梯度阻断（Sparse Gradient Challenge）**：
   在预训练阶段，序列中的每一个 Token 都计算 Next-Token Prediction 交叉熵损失，因此前文每个块都能获得密集的局部与跨块梯度监督；然而在 SFT（Supervised Fine-Tuning）阶段，长 Prompt 部分（如数万字的文档上下文）的 Loss 通常被掩码屏蔽（Loss Masking），**唯有末尾较短的 Response Tokens 产生非零损失梯度**。如果所有层都使用高稀疏率的 MoBA（例如在 $32\text{K} \sim 1\text{M}$ 上下文中仅路由 $4\% \sim 25\%$ 的历史块），仅靠末尾少量 Response Token 的稀疏路由连接很难将梯度充分传播回长文档的各个段落。MoBA 论文 Section 3.2 发现，利用 MoBA 零新增参数、与 Full Attention 完全同构的优势，**将模型最后 $3$ 层（共 $32$ 层中的第 $29 \sim 31$ 层）切换为 Full Attention**，其余前 $29$ 层保持 MoBA，即可让顶层聚合完整上下文梯度并显著压低 SFT Trailing Loss。
2. **Decode 阶段缺乏 Query 批量分摊（Prefill/Decode Asymmetry）**：
   MoBA 的高效内核依赖将“路由到同一个历史 KV 块专家的所有 Query Tokens”打包重排后做一次块级 GEMM（即 MoE 的 Expert Grouping 技巧）。在训练和 Prefill 阶段，整条长序列有数万个 Query Token 同时参与路由，每个历史 KV 块都能分到足够多的 Query 来跑满 Tensor Core；但在逐 Token 生成的 Decode 阶段，当前步只有 $1$ 个 Query Token，不仅无法在多个 Query 位置间分摊 KV 块读取，而且 MoBA 是按单个注意力头（Per-Head）独立路由的（未像 NSA 那样做 GQA 组内强制共享与专用 Decode 内核），因此在 Llama-8B-1M-MoBA 生产评测中，MoBA 仅用于加速最耗时的长序列 Prefill（在 $1\text{M}$ 长度下提速 $6.5\times$），而在生成阶段无缝切回 Full Attention。

**追问 2：从 DeepSeek NSA（块级池化打分）演进到 DeepSeek-V3.2 的 DSA（DeepSeek Sparse Attention）与 MiniMax MSA，为什么后两者放弃了“直接用块均值池化 Key 打分”，转而引入独立的轻量级学习索引器（Learned Indexer）与在线 KL 散度蒸馏？**
1. **均值池化打分（Mean-Pooled Key Proxy）的两大理论天花板**：
   - **块内特征平滑抵消**：当块大小 $B$ 较大时，块内数十个至数千个 Token 的 Key 向量取均值 $\bar{\mathbf{k}}_b = \frac{1}{B}\sum_{i \in B_b} \mathbf{k}_i$ 会把块内孤立的“单 Token 关键针（Needle）”淹没在背景词元的均值中；
   - **未选中尾部的零梯度盲区（Unselected Tail Problem）**：在 MoBA（以及仅靠选中块回传梯度的池化路由）中，未被 `top-k` 选中的历史块 $b \notin \mathcal{S}_t$ 完全不参与输出计算，因此其得不到“主动压低错误高分块”的负样本梯度监督。
2. **DSA（Token 级 Lightning Indexer）与 MSA（块级 Max-Pool Indexer）的突破**：
   - **DeepSeek-V3.2 DSA** 设计了一个极低开销的独立索引器（少量头、低秩、FP8 精度）：$I_{t,i} = \sum_{h=1}^{H_I} w_{t,h} \operatorname{ReLU}(\mathbf{q}_{t,h}^{I\,\top} \mathbf{k}_i^I)$，直接对每个候选 Token 打分并选出 Top-$k$（如 $k=2048$），配合 MLA 的单共享潜变量 MQA 模式克服了单 Token 读取的带宽开销；
   - **MiniMax MSA** 则将独立索引器的单 Token 打分在块内取最大值 $S_{t,b}^g = \max_{i \in B_b} I_{t,i}^g$（只要块内有 $1$ 个关键针 Token 得分高，整块即被召回，避免了均值稀释），并沿用 NSA 的 GQA 组内共享块选择骨架；
   - 由于独立索引器不直接乘入主注意力输出 $\mathbf{o}_t$，它无法从主任务交叉熵获得梯度，因此 DSA 与 MSA 均采用**在线 KL 散度蒸馏（Online KL Distillation）**：以主注意力分布为 Teacher、索引器得分为 Student，并通过对索引器输入施加 `stop-gradient`、预热期（Warm-up）稠密对齐以及强制保留局部块三项稳定器，防止辅助损失污染主干表征。

**追问 3：在 DeepSeek NSA 的预训练实验中，为什么稀疏模型在 GSM8K、DROP、AIME 24 以及多跳问答（HotpotQA / 2WikiMultihopQA）上的准确率不仅没有因为丢弃了 $90\%$ 以上的历史 Token 而下降，反而显著超越了同规模的 Full Attention 基线？**
1. **结构化消除长序列注意力噪声底噪（Attention Noise Filtering）**：
   正如 [llm-0044](llm-0044-differential-transformer-gated-attention.md) 所分析，标准 Full Softmax Attention 在面对 $32\text{K} \sim 64\text{K}$ 上下文时，成千上万个无关背景 Token 的非负指数项 $\exp(q^\top k / \sqrt{d}) > 0$ 会分走超过一半的概率质量，稀释关键推理前提。NSA 在预训练阶段就通过 Top-$n$ 块硬截断将占序列 $90\%$ 以上的无关背景块彻底排除在细粒度分支的 Softmax 分母之外，迫使注意力权重高度集中在最相关的 $n=16$ 个块上。
2. **端到端同步演化出专职检索与推理通路**：
   与推理期事后剪枝不同，NSA 从预训练第 $1$ 步起就让压缩分支、选择分支、滑窗分支与 FFN / MoE 专家协同适应，使模型学会将局部语法交由滑窗分支处理、将跨段落多跳实体桥接交由选择分支精确提取，从而在 LongBench 多跳推理（HPQ $+0.087$、2Wiki $+0.051$）与 $32\text{K}$ R1 蒸馏长思维链数学竞赛（AIME 24 在 $8\text{K}/16\text{K}$ 下分别取得 $+0.075$ 与 $+0.054$ 提升）上全面反超 Full Attention。

---

## 常见误区

- **误区一：“在 GQA 模型中实现块稀疏注意力时，让每个 Query 头各自挑选最相关的 Top-$k$ 个 KV 块，就能把解码期的显存带宽读取量降低到原来的 $k / N_{\text{blocks}}$。”**
  事实：**在 GQA/MQA 架构下，按每个 Query 头独立选块会引发严重的“HBM 访存并集膨胀”！** 因为同一个 GQA Group 内的 $G$ 个 Query 头（如 $G=8$ 或 $16$）在物理上共享同一份 KV Cache 头。如果这 $G$ 个查询头各自选出互不重叠的 $k$ 个块，GPU 在解码时为了完成该组的计算，必须把所有头选中块的**并集（最多达 $G \times k$ 个块）**全部从 HBM 搬运到 SRAM，导致实际省下的显存带宽微乎其微。这正是 DeepSeek NSA 必须在公式 (10) 中将同组所有头的块重要性得分求和、强制整个 GQA 组共享同一套 Top-$n$ 块索引 $\mathcal{I}_t$ 的根本原因。
- **误区二：“Moonshot MoBA 把当前块（Current Block）和选中的历史块（Historical Blocks）分成两次 FlashAttention 调用后，直接把两路返回的输出张量相加 `out = out_self + out_moba` 就能得到最终注意力输出。”**
  事实：**直接相加 `out_self + out_moba` 在数学上是完全错误的（会导致输出幅值翻倍且权重比例失真）！** 因为两次 FlashAttention 调用分别在各自的局部子集 $\mathcal{S}_{\text{self}}$ 和 $\mathcal{S}_{\text{moba}}$ 上独立做了归一化（各自内部权重和均为 $1$，合计权重和变成了 $2$）。正确做法必须读取 FlashAttention 内核额外返回的自然对数配分函数 $\text{LSE}$（`softmax_lse`），利用 Online Softmax 公式计算全局配分函数 $\text{LSE}_{\text{mixed}} = \ln(\exp(\text{LSE}_{\text{self}}) + \exp(\text{LSE}_{\text{moba}}))$，再分别乘以重缩放系数 $\exp(\text{LSE}_{\text{self}} - \text{LSE}_{\text{mixed}})$ 与 $\exp(\text{LSE}_{\text{moba}} - \text{LSE}_{\text{mixed}})$ 后求和。
- **误区三：“DeepSeek NSA 既然已经有了选中块的细粒度注意力（Selected Attention）和全局压缩注意力（Compressed Attention），再单独维护一个独立的滑动窗口分支（Sliding Window Attention）纯粹是算力冗余，直接把最近几个块固定加进选择分支里效果完全一样。”**
  事实：**将近期局部上下文直接混入选择分支会导致严重的“局部捷径学习（Shortcut Learning）”！** NSA 论文 Section 3.3.3 明确指出，在训练初期，局部相邻 Token 的统计规律极易拟合，若不将滑动窗口拆分为拥有独立 KV 投影的单独分支，注意力梯度会被近期局部 Token 迅速垄断，导致模型根本学不会利用压缩分支和选择分支去捕获远距离全局依赖。通过专用滑动窗口分支显式承接局部模式，才能解放压缩与选择分支去专攻长程语义检索。

---

## 参考

- 选题线索：[rohitg00/ai-engineering-from-scratch (`phases/10-llms-from-scratch/17-native-sparse-attention/docs/en.md`)](https://github.com/rohitg00/ai-engineering-from-scratch/blob/9a6608f11e6a9adc9649c0db1308267cbb8ef6bb/phases/10-llms-from-scratch/17-native-sparse-attention/docs/en.md)（固定 commit `9a6608f`）与 [fla-org/flash-linear-attention (`fla/ops/dsa/README.md`)](https://github.com/fla-org/flash-linear-attention/blob/cc4648a3b35c27c6bc6b3cfb0079a14d57bcbc5b/fla/ops/dsa/README.md)（固定 commit `cc4648a`），独立推导数学机制并扩展源码级对比。
- Yuan et al. (DeepSeek-AI & PKU & UW), [Native Sparse Attention: Hardware-Aligned and Natively Trainable Sparse Attention](https://arxiv.org/abs/2502.11089)，ACL 2025 Best Paper，及开源实现 [fla-org/native-sparse-attention (`native_sparse_attention/ops/naive.py` & `modeling_nsa.py`)](https://github.com/fla-org/native-sparse-attention/blob/bd67af59b90afa34b25f61d2922e612d10dba3bd/native_sparse_attention/ops/naive.py)（固定 commit `bd67af5`）：三分支层级架构、跨步长块重要性推导公式 (8)–(12)、GQA 组内共享选块与 Group-Centric Triton 内核设计。
- Lu et al. (Moonshot AI & Tsinghua & ZJU), [MoBA: Mixture of Block Attention for Long-Context LLMs](https://arxiv.org/abs/2502.13189)，2025，及官方源码 [MoonshotAI/MoBA (`moba/moba_naive.py` & `moba/moba_efficient.py`)](https://github.com/MoonshotAI/MoBA/blob/b5d58363311d3ca946f1ec444182727c15e338b5/moba/moba_efficient.py)（固定 commit `b5d5836`）：MoE 式块均值池化路由、当前块强制激活因果保护、`MixedAttention` 双路变长 FlashAttention 调用与 LSE Online Softmax 合并实现。
- DeepSeek-AI, [DeepSeek-V3.2: Pushing the Frontier of Open Large Language Models (DeepSeek Sparse Attention, DSA)](https://arxiv.org/abs/2512.02556)，及 MiniMax, [MiniMax Sparse Attention (MSA)](https://arxiv.org/abs/2606.13392)：可学习轻量索引器（Learned Indexer）、块内 Max-Pooling 与在线 KL 蒸馏对齐演进。

来源访问与示例核验日期：**2026-11-18**。仅执行标准库下 NSA 跨粒度重叠块重要性映射、GQA 组内共享选块访存核算、MoBA 双路 LSE Online Softmax 合并等价性及 $64\text{K}$ 解码预算的数值验证，未运行 27B/8B 大模型预训练与多卡 GPU Triton 内核基准评测。
