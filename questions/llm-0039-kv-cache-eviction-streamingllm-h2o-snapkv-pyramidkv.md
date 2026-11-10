---
id: llm-0039
title: KV Cache 稀疏驱逐与结构化预算分配（StreamingLLM、H2O、SnapKV 与 PyramidKV）是如何通过注意力汇聚点保护、重要词元识别与层级金字塔预算突破长上下文内存瓶颈的？
category: llm
tags: [kv-cache-eviction, attention-sink, streamingllm, h2o, snapkv, pyramidkv]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开注意力机制与推理优化题库（WiA-Attention / KVCache-Factory）扩展改编；StreamingLLM（ICLR 2024）、H2O（NeurIPS 2023）、SnapKV（NeurIPS 2024）、PyramidKV（2024）及官方源码核实（见参考）
status: published
updated: 2026-11-11
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-11-11
    updated: 2026-11-11
---

## 问题

在长序列自回归推理与持续多轮流式对话中，全量键值缓存（Full KV Cache）的显存占用随序列长度 $T$ 呈 $O(T)$ 线性增长。当 $T$ 突破数万乃至百万 Token 时，KV Cache 不仅极易触发显存溢出（OOM），更会让自回归 Decode 阶段每步的 HBM 访存量线性膨胀。除了降低单元素位宽的 KV 量化外，另一条正交且无需修改模型权重的路线是**KV Cache 稀疏驱逐与压缩（KV Cache Eviction / Token Pruning）**：将缓存容量严格限制在固定预算 $B \ll T$ 内，动态丢弃冗余历史 Token。这一方向经历了从 **StreamingLLM（ICLR 2024）**、**H2O（NeurIPS 2023）** 到 **SnapKV（NeurIPS 2024）** 与 **PyramidKV（2024）** 的系统性演进。

请深入剖析以下三个核心问题：
1. **朴素滑动窗口崩塌机理与 StreamingLLM 的双核设计**：为什么当生成长度超出滑动窗口 $W$ 时，即便只从 KV Cache 中驱逐序列最开头的第 1 个 Token（`pos=0`），模型困惑度（Perplexity）也会立即发生数量级暴增？什么是 **Attention Sink（注意力汇聚点）**？为什么 StreamingLLM 在保留前 $S$ 个 Sink Token 与最近 $W$ 个窗口 Token 后，还必须对缓存内的 Key 与当前 Query 执行**缓存内相对位置重编码（In-Cache RoPE Position Shifting）**？
2. **从位置盲目驱逐到内容感知驱逐（H2O vs SnapKV）**：StreamingLLM 为什么无法完成跨窗口的长文档问答与大海捞针（Needle-in-a-Haystack）？**H2O（Heavy-Hitter Oracle）**是如何利用累积注意力识别重要词元（Heavy Hitters）的，它在长 Prompt 下存在什么**因果位置累积偏置（Causal Length Bias）**与 FlashAttention 兼容性瓶颈？**SnapKV** 又是如何通过**尾部观测窗口投票（Observation Window Voting）+ 一维局部池化聚类（1D Pooling Clustering）**在 Prefill 阶段一次性精确捕获完整的关键语义簇的？
3. **跨层信息漏斗与 GQA 分组粒度对齐（PyramidKV 机制与工程陷阱）**：为什么对 Transformer 所有层分配完全相同的 KV 预算（Uniform Allocation）是次优的？**PyramidKV** 是如何根据浅层注意力广泛弥散、深层注意力高度聚焦的“信息漏斗（Information Funnel）”规律计算每层金字塔预算的？在分组查询注意力（GQA）模型中，为什么在 `repeat_kv` 之后按每个 Query Head 独立选 Top-$K$ 会导致压缩后的 KV 显存意外膨胀 $G$ 倍？应如何在 KV Head 粒度下做组内分数归约（Group Score Reduction）？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-11-11

**KV Cache 稀疏驱逐的核心，是在固定显存预算 $B$ 下同时守住“Softmax 数值锚点”、“长程任务相关语义簇”与“跨层/跨头结构对齐”：（1）由于 Softmax 强制要求所有位置注意力权重之和恒等于 $1$（$\sum_j A_{t,j} = 1$），当当前 Token 无需关注任何历史上下文时，自回归模型在预训练中自发学会将多余注意力倾倒在序列最开头的 $1\sim 4$ 个固定可见 Token（Attention Sinks）上以实现“近似零值空转”；朴素滑动窗口一旦驱逐首词，分母高幅值指数项 $\exp(z_0)$ 消失会导致冗余概率失控回流至局部窗口并引发级联特征坍缩；StreamingLLM 通过永久钉住前 $S=4$ 个 Sink Token 配合长度 $W$ 的滑动窗口，并在施加 RoPE 前将保留的 KV 重映射为缓存内连续相对下标 $[0, 1, \dots, S+W-1]$，以 $O(S+W)$ 恒定显存实现无限流式生成；（2）为克服 StreamingLLM 丢弃中间历史导致的“长程失忆”，H2O 维护前缀累积注意力 $\sum_{i=1}^t A_{i,j}$ 动态保留 Heavy Hitters，但全矩阵累加不仅面临早期 Token 被重复计分 $(L-j)$ 次的因果偏置，且难以直接融合进不落盘 $L \times L$ 注意力矩阵的 FlashAttention；SnapKV 则仅利用 Prompt 末尾长度为 $W_{\text{obs}}$（如 $32\sim 64$）的指令观测窗口计算局部注意力矩阵 $\mathbf{A}_{[-W_{\text{obs}}:, :-W_{\text{obs}}]}$，并在选 Top-$K$ 前沿序列维施加核大小 $k=5/7$ 的 1D 平均/最大池化，防止只抽走孤立锚点词而截断相邻关键数字或实体；（3）PyramidKV 进一步顺应 Transformer 浅层广泛聚合全局上下文、深层高度收敛至少数汇聚点的信息漏斗特性，按等差金字塔调度将更多预算倾斜给浅层、大幅削减深层预算；而在 GQA 架构中，必须在 `repeat_kv` 展开前（或临时展开算分后）将同一 KV 组内 $G$ 个 Query Head 的注意力得分按 `mean`/`max`/`sum` 归约为单份 `[B, n_kv_heads, L]` 评分再执行 gather，否则每个 Query Head 选出互异的 Token 集合将迫使缓存退化回 $n_q$ 份，彻底抵消 GQA 的 $G$ 倍显存收益。**

在展开数学推导与源码级拆解之前，建议先关联本库内已有的相关题目建立完整知识坐标系：关于 KV Cache 的基础内存增长公式以及 Prefill（算力受限）与 Decode（访存带宽受限）的算术强度差异，请参阅 [llm-0018](llm-0018-kv-cache-prefill-decode.md)；关于从单元素位宽维度将 KV Cache 压缩至 2-bit 的 KIVI 与 KVQuant 机制（可与本题的 Token 驱逐正交叠加），请参阅 [llm-0038](llm-0038-kv-cache-quantization-kivi-kvquant.md)；关于从注意力架构源头通过低秩联合压缩削减 KV 维度的 MLA 机制，请参阅 [llm-0034](llm-0034-mla-multi-head-latent-attention-rope-absorption.md)；关于 Agent 工程层面的轨迹上下文压缩策略，请参阅 [agent-0043](agent-0043-kv-cache-friendly-context-compression.md)；关于长上下文窗口与外部 RAG 检索的适用边界对比，请参阅 [rag-0016](rag-0016-long-context-vs-rag.md)。

---

### 1. 为什么删掉第 1 个 Token 模型就会崩？StreamingLLM 的 Attention Sink 与缓存内位置重映射

#### （1）Attention Sink 的 Softmax 归一化数学本质与滑动窗口崩塌推导
设第 $t$ 步解码的查询向量为 $\mathbf{q}_t \in \mathbb{R}^d$，历史键值向量为 $\{(\mathbf{k}_j, \mathbf{v}_j)\}_{j=0}^t$，注意力 logit 为 $z_{t,j} = \frac{\mathbf{q}_t \mathbf{k}_j^\top}{\sqrt{d}}$。标准 Softmax 注意力输出为：

$$\mathbf{o}_t = \sum_{j=0}^t A_{t,j} \mathbf{v}_j, \quad A_{t,j} = \frac{\exp(z_{t,j})}{\sum_{m=0}^t \exp(z_{t,m})} \quad \implies \quad \sum_{j=0}^t A_{t,j} \equiv 1$$

**StreamingLLM**（Xiao et al., ICLR 2024）通过逐层统计 Llama-2、MPT、Falcon 与 Pythia 的注意力分布，揭示了一个反直觉现象：在除第 0、1 层外的几乎所有中深层注意力头中，**序列最开头的 $1\sim 4$ 个初始 Token（即便只是毫无语义的起始符 `<s>` 或换行符）恒定吸收了高达 $40\%\sim 80\%$ 的注意力权重**。其根本成因在于：
1. **Softmax 缺乏“零输出（No-Op）”逃生通道**：在多头注意力的数十个头中，许多注意力头在特定时间步 $t$ 并没有匹配到任何有价值的历史特征（即对所有 $j \in [1, t]$，内积 $z_{t,j}$ 都很小且彼此接近）。然而，Softmax 在数学上强制所有权重的总和必须等于 $1$。
2. **因果掩码下的全局可见性与低范数 Value 垃圾桶**：由于训练期采用下三角因果掩码（Causal Mask），序列最开头的极少数 Token（$j \in \{0, \dots, S-1\}$）是**唯一对后续所有位置 $t \ge S$ 均 100% 可见的全局公共锚点**。因此，模型在预训练中自发演化出一种隐式机制：将初始 Token 的 Key 投影出在特定方向上的极大正偏置（使得 $z_{t,0} \gg z_{t,j}$），同时将其 Value 向量 $\mathbf{v}_0$ 演化为极小范数或近似正交于下游输出投影 $\mathbf{W}_O$ 的零均值偏置。这样，当某个头无需提取信息时，只需令 $\exp(z_{t,0})$ 主导 Softmax 分母，即可让 $A_{t,0} \to 1, \, A_{t, j>0} \to 0$，等效于让该注意力头安全“空转”。
3. **驱逐首词后的分母坍缩与级联失真**：
   假设原始全量缓存（或含 Sink 缓存）的分母为 $Z_{\text{sink}} = \sum_{s=0}^{S-1} \exp(z_{t,s})$，近期滑动窗口 $\mathcal{W} = \{t-W+1, \dots, t\}$ 的分母为 $Z_{\text{win}} = \sum_{j \in \mathcal{W}} \exp(z_{t,j})$。当该注意力头处于“空转”状态时，$Z_{\text{sink}} \gg Z_{\text{win}}$（例如 $Z_{\text{sink}} / Z_{\text{win}} \approx 9$），此时滑动窗口内任意普通 Token $j \in \mathcal{W}$ 分到的权重仅为：
   $$A_{t,j}^{\text{with-sink}} = \frac{\exp(z_{t,j})}{Z_{\text{sink}} + Z_{\text{win}}} \approx 0.1 \times \frac{\exp(z_{t,j})}{Z_{\text{win}}}$$
   一旦朴素滑动窗口在 $t = W$ 时将 $j=0, \dots, S-1$ 驱逐出缓存，$Z_{\text{sink}}$ 瞬间归零！原本仅占 $10\%$ 的窗口内各无关 Token 权重被迫暴涨 $\frac{Z_{\text{sink}} + Z_{\text{win}}}{Z_{\text{win}}} \approx 10\times$：
   $$A_{t,j}^{\text{naive-window}} = \frac{\exp(z_{t,j})}{Z_{\text{win}}} = \left(1 + \frac{Z_{\text{sink}}}{Z_{\text{win}}}\right) A_{t,j}^{\text{with-sink}}$$
   大量不相关的历史 Value 向量 $\mathbf{v}_j$ 被强行按高权重混入残差流，经过层归一化与数十层放大后，输出分布彻底崩坏为乱码。

#### （2）为什么必须执行缓存内相对位置重编码（In-Cache RoPE Position Shifting）？
许多候选人以为 StreamingLLM 只需在标准 KV Cache 上切片保留 `[0:S]` 与 `[T-W:T]` 即可。**事实上，如果直接复用旋转后的历史 Key 缓存，只要生成步数 $t$ 超过预训练上下文长度 $L_{\text{train}}$（如 Llama-2 的 $4096$），模型依然会崩溃！**

结合官方源码 `mit-han-lab/streaming-llm`（`streaming_llm/kv_cache.py::StartRecentKVCache` 与 `streaming_llm/pos_shift/modify_llama.py`），StreamingLLM 采用了**Pre-RoPE 缓存 + 缓存内连续位置重映射**架构：
- **问题根源**：如果在把 Key 存入缓存前就已经按全局绝对位置 $t$ 乘上了旋转位置编码 $\mathbf{R}_{\Theta, t}$，那么在第 $t = 10000$ 步时，保留的 Sink Token 处于位置 $[0, 1, 2, 3]$，而近期窗口 Token 处于位置 $[8980, \dots, 9999]$。此时：
  1. 当前 Query（位置 $10000$）与 Sink Token（位置 $0$）之间的相对位置距离高达 $\Delta = 10000 \gg L_{\text{train}}$，远超 RoPE 训练时见过的相位差分布；
  2. 位置 $3$ 与位置 $8980$ 之间出现了长达 $8976$ 个位置的巨大断层（Position Gap），破坏了注意力头对连续局部几何相位的假设。
- **源码级解法（`llama_pos_shift_attention_forward`）**：
  1. **缓存未旋转的 Key（Pre-RoPE Caching）**：在拼接与驱逐 `past_key_value` 之前，**不对 `key_states` 施加 RoPE**，确保 `StartRecentKVCache` 中存储的永远是不带位置相位的原始线性投影向量 $\mathbf{k}^{\text{pre}}$；
  2. **按缓存物理槽位重赋连续位置 ID**：设驱逐裁剪后当前缓存内的总 Token 数为 $C = \min(t, S + W)$（其中槽位 $0 \dots S-1$ 为 Sink，槽位 $S \dots C-1$ 为滑动窗口）。在每步计算注意力前，动态生成连续的缓存内位置索引 `key_position_ids = torch.arange(kv_seq_len)`（即 $[0, 1, \dots, C-1]$）对整个缓存的 Key 施加 RoPE，并将当前步的 Query 位置设为 $C-1$（或追加前的 $C$）：
     $$\tilde{\mathbf{k}}_idx = \mathbf{R}_{\Theta, \, idx} \, \mathbf{k}_{\text{global}(idx)}^{\text{pre}} \quad (idx \in \{0, 1, \dots, C-1\}), \quad \tilde{\mathbf{q}}_t = \mathbf{R}_{\Theta, \, C-1} \, \mathbf{q}_t^{\text{pre}}$$
  如此一来，无论对话持续到第 $10^5$ 步还是第 $10^7$ 步，模型看到的相對位置差永远严格被钳制在 $[0, S+W-1] \subset [0, L_{\text{train}}]$ 的训练分布甜点区内！

> **生产改进提示（Pre-trained Dedicated Sink Token）**：StreamingLLM 论文还证明，虽然免训练版通常需要 $S=4$ 个初始 Token 才能稳定充当汇聚点，但如果在预训练阶段就在所有语料最开头显式拼接 **1 个专用的可学习占位符（Learnable Sink Token `<sink>`）**，那么推理时仅需 $S=1$ 个 Token 就能完美吸收全部冗余注意力。这也是后来 OpenAI `gpt-oss` 等现代架构引入每头可学习标量偏置（Learnable Softmax Sink Bias，即在 Softmax 分母中直接加上 $\exp(b_h)$ 虚拟 Sink 项）的理论源头。

---

### 2. 从位置盲目保留到语义重要性保留：H2O 与 SnapKV 的机制博弈

StreamingLLM 的致命局限在于：**它实现的是“无限流式生成（Infinite Streaming Generation）”，而非“无限长上下文理解（Infinite Context Understanding）”**。一旦某个包含关键事实的 Token（如第 $500$ 步提到的密码或合同条款）滑出长度为 $W$ 的近期窗口，它就会被无情丢弃，模型彻底丧失长距离召回能力。为了在固定预算 $B$ 下保住长距离关键信息，**H2O** 与 **SnapKV** 分别代表了“全序列累积贪心驱逐”与“尾部观测窗口聚类投票”两代范式。

#### （1）H2O（Heavy-Hitter Oracle）：累积注意力评分与两大工程瓶颈
**H2O**（Zhang et al., NeurIPS 2023）观察到：训练良好的 LLM 注意力矩阵具有高度的稀疏性与幂律分布（Power-Law Distribution）——除局部近邻外，超过 $90\%$ 的长程注意力权重都集中投射在极少数关键语义词（如核心实体、动词、句首锚点，称为 **Heavy Hitters, $\text{H}_2$**）上。
- **评分与驱逐公式**：
  在官方源码 `FMInference/H2O`（`h2o_hf/utils_hh/modify_llama.py::LlamaAttention_heavy_hitter`）中，缓存预算 $B = B_{\text{heavy}} + B_{\text{recent}}$ 被一分为二：永远保留最近的 $B_{\text{recent}}$ 个局部 Token，而对更早的历史候选集 $j \in \{0, \dots, t - B_{\text{recent}} - 1\}$，维护从第 $0$ 步到当前第 $t$ 步的**累积注意力得分（Cumulative Attention Score）**：
  $$s_j^{\text{H2O}}(t) = \sum_{i=j}^t A_{i, j}$$
  每当缓存超出预算 $B$ 时，保留 $s_j^{\text{H2O}}(t)$ 排名前 $B_{\text{heavy}}$ 的历史 Token（天然包含了得分极高的 Attention Sinks），驱逐其余低分 Token。
- **H2O 在超长 Prompt 下的两大硬伤**：
  1. **因果长度偏置（Causal Length Bias / Position Bias）**：由于下三角因果掩码的限制，位置 $j=0$ 的 Token 参与了全部 $L$ 行注意力的累加（求和项数为 $L$），而位置 $j = 0.8 L$ 的后期 Token 仅参与了 $0.2 L$ 行累加！即使某个出现在文档中后段的“关键针（Needle）”在被提问时极其重要，在长文档前缀阅读阶段它尚未被高频关注，且累加次数先天处于劣势，极易在 Prefill 阶段被早期刷满存在感的普通高频词挤出 Top-$B_{\text{heavy}}$。
  2. **与 FlashAttention 的内存墙冲突**：标准 FlashAttention 通过在线 Softmax 分块归约避免了在 HBM 中实例化 $O(L^2)$ 的完整注意力矩阵 $\mathbf{A} \in \mathbb{R}^{L \times L}$。而原始 H2O 为了计算全局列和 $\sum_{i=1}^L A_{i,j}$，要么被迫回退到实例化完整 $L \times L$ 矩阵（在 $L=128\text{K}$ 时直接 OOM），要么需要执行两遍扫描并修改底层 CUDA 归约算子。

#### （2）SnapKV：“LLM 早已知道你在找什么”——尾部观测窗口投票 + 1D 池化聚类
**SnapKV**（Li et al., NeurIPS 2024）洞察到一个关键规律：在长文档问答、大海捞针或代码补全中，用户的**核心查询意图通常集中在 Prompt 最末尾的一小段 Token**（且即便指令在开头，末尾 Token 的注意力模式也已高度对齐后续解码阶段的生成需求）。因此，根本不需要计算昂贵且带有位置偏置的全矩阵 $L \times L$ 注意力！

结合官方源码 `FasterDecoding/SnapKV` 与 `Zefan-Cai/KVCache-Factory`（`pyramidkv/pyramidkv_utils.py::SnapKVCluster.update_kv`），SnapKV 在 Prefill 结束时执行一次性四步流水线：

```text
SnapKV Prefill 阶段一次性无损压缩流水线 (设总长 L, 观测窗口 W_obs = 64, 目标总容量 B = 320, 池化核 k = 5):

[前缀候选区 Prefix Candidates: 0 ... L - W_obs - 1]  |  [尾部观测窗口 Observation Window: L - W_obs ... L - 1]
                        ▲                                                      │
                        └────── Step 1: 仅用最后 W_obs 个 Query 与全量 Key 计算局部注意力 ──┘
                                attn_weights = softmax(Q[:, :, -W_obs:, :] @ K^T / sqrt(d))  # 形状仅 [B, H, W_obs, L] !

Step 2 (窗口投票求和):
  将 W_obs 个观测 Token 对前缀候选区 [0 : L - W_obs] 的注意力权重沿 Query 维求和:
  vote_scores[b, h, j] = sum_{i = L - W_obs}^{L - 1} A[b, h, i, j],   j in [0, L - W_obs - 1]

Step 3 (1D 局部池化聚类 — 保护完整语义短语!):
  对 vote_scores 施加 1D 平均池化或最大池化 (stride=1, padding=k // 2, 保持长度不变):
  pooled_scores = avg_pool1d(vote_scores, kernel_size=k, padding=k // 2, stride=1)

Step 4 (Top-K 收集与窗口拼接):
  indices = topk(pooled_scores, k = B - W_obs)          # 选出得分最高的 B - W_obs 个前缀位置
  K_compressed = cat([gather(K_prefix, indices), K_obs_window], dim=2)   # 最终长度恒为 B!
  V_compressed = cat([gather(V_prefix, indices), V_obs_window], dim=2)
```

- **为什么 Step 3 的 `avg_pool1d` / `max_pool1d` 是大海捞针不丢词的灵魂？**
  在真实自然语言中，一个关键事实通常由连续的多个 Token 共同构成（例如 `"The secret passcode is 7392"` 包含 6 个 Token）。然而，注意力头在检索时往往只会在其中的**1 个核心锚点词**（如 `"passcode"` 或 `"is"`）上打出极高的尖峰注意力，而紧挨着它的具体数值 `"7392"` 在当前步的注意力得分可能并不突出，只等生成到下一词时才通过局部偏移被读取。
  如果像 H2O 那样直接对原始单点得分取 `topk`，模型只会把孤立的 `"passcode"` 选入缓存，而把紧邻的 `"7392"` 删掉，导致回答时看得到锚点却读不出答案！SnapKV 通过一维卷积池化：
  $$\tilde{s}_j = \frac{1}{k} \sum_{u = -\lfloor k/2 \rfloor}^{\lfloor k/2 \rfloor} s_{j+u}^{\text{vote}}$$
  将核心尖峰 Token 的高分平滑扩散给左右相邻的 $\lfloor k/2 \rfloor$ 个邻居，从而把**整个连续的语义短语簇（Cluster）连根拔起、完整保留进 KV Cache**！
- **复杂度对比**：SnapKV 仅需额外计算形状为 $[W_{\text{obs}}, L]$（如 $64 \times 128\text{K}$）的极窄切片注意力，空间与计算复杂度均为 $O(W_{\text{obs}} \cdot L) = O(L)$，因此主干 Prefill 可以 100% 跑在原生高速 FlashAttention-2 上！

---

### 3. PyramidKV 层级金字塔预算与 GQA 缓存粒度陷阱

#### （1）PyramidKV：顺应跨层“信息漏斗”的等差金字塔预算调度
无论是 H2O 还是 SnapKV，默认都采用**跨层均匀预算（Uniform Allocation）**，即给第 $0$ 层到第 $M-1$ 层分配完全相同的缓存容量 $B$。**PyramidKV**（Cai et al., 2024）通过分析各层注意力熵（Attention Entropy）指出，Transformer 在处理长上下文时遵循明显的**信息漏斗（Information Funnel）**结构：
- **底层（Shallow Layers，$l \to 0$）**：注意力分布极其平坦、接近均匀分布，模型正在跨全文广泛扫描并混合局部词法特征，此时如果强行裁剪到极小预算，会造成不可逆的底层信息丢失；
- **中层（Middle Layers）**：开始在段落与句子内部形成局部语义聚类；
- **深层（Deep Layers，$l \to M-1$）**：信息已被高度浓缩到极少数核心 Token 与 Attention Sink 上，前几十个高分 Token 就占据了 $98\%$ 以上的注意力质量，保留大量长尾 Token 纯属浪费显存。

因此，在总显存预算不变的前提下，PyramidKV 将预算从深层抽调给浅层，构建**下宽上窄的金字塔预算调度**。在官方源码 `Zefan-Cai/KVCache-Factory`（`pyramidkv/pyramidkv_utils.py::PyramidKVCluster.update_kv`）中，给定目标平均总容量 `max_capacity_prompt`（记为 $B_{\text{avg}}$）、尾部观测窗口 `window_size`（记为 $W$）、形状超参数 $\beta$（默认 $\beta = 20$）与总层数 $M$（`num_hidden_layers`），各层前缀保留容量 $b_l^{\text{prefix}}$ 的精确计算公式为：

$$\begin{aligned}
b_{\text{base}} &= B_{\text{avg}} - W \\
b_{\min} &= \left\lfloor \frac{b_{\text{base}}}{\beta} \right\rfloor, \qquad b_{\max} = 2 \, b_{\text{base}} - b_{\min} \\
\text{steps} &= \left\lfloor \frac{b_{\max} - b_{\min}}{M - 1} \right\rfloor, \qquad b_l^{\text{prefix}} = b_{\max} - l \cdot \text{steps} \quad (l \in \{0, 1, \dots, M-1\})
\end{aligned}$$

（注：当提示词较短使得 $b_{\max} \ge L - W$ 时，源码会将上界钳制为 $b_{\max} = L - W$ 并对称重算 $b_{\min} = 2 b_{\text{base}} - b_{\max}$）。由于 $b_{\min} + b_{\max} = 2 b_{\text{base}}$，所有层的平均前缀容量 $\frac{1}{M}\sum_{l=0}^{M-1} b_l^{\text{prefix}} \approx b_{\text{base}}$，**在不增加任何额外总显存的条件下，显著提升了极低预算（如仅保留 $64\sim 128$ Tokens）下的长文档召回率**。

#### （2）工程高危陷阱：GQA 模型下的 `repeat_kv` 粒度膨胀与组内归约
在 Llama-3-8B（$n_q = 32$ 个 Query Heads，$n_{kv} = 8$ 个 KV Heads，组大小 $G = n_q / n_{kv} = 4$）等采用分组查询注意力（GQA）的现代模型中，落地 H2O / SnapKV / PyramidKV 时存在一个极具隐蔽性的工程陷阱（详见 `KVCache-Factory` Issue #49 与官方审计报告 `docs/gqa_cache_layout.md`）：
- **错误做法（`query_head` 粒度：先 `repeat_kv` 再压缩）**：
  早期许多开源实现照搬 Hugging Face `LlamaAttention` 的写法，在进入 `kv_cluster.update_kv` 之前，先调用了 `key_states = repeat_kv(key_states, G)` 将 KV 从 $8$ 个头复制展开成了 $32$ 个头，然后对 $32$ 个 Query Head 各自独立执行 `attn_cache.topk(B)` 与 `gather`。
  由于同一组内的 $4$ 个 Query Head 关注的历史 Token 位置并不完全相同，gather 出来的 $32$ 个头拥有各自独立的 Token 子集，再也无法折叠回 $8$ 个 KV Head！结果存入 `past_key_value` 的张量形状变成了 `[bsz, 32, B, head_dim]` 而非 `[bsz, 8, B, head_dim]`——**无意中把压缩后的 KV Cache 显存撑大了整整 $G = 4$ 倍，彻底抵消了 GQA 架构的核心收益！**
- **正确做法（`kv_head` 粒度：临时展开算分 + 组内归约 `_reduce_group_scores` + 未展开 gather）**：
  如 `pyramidkv_utils.py` 中的 `_grouped_window_attn_cache` 与 `_reduce_group_scores` 所示，正确的工程管线必须遵循：
  1. 传入 `update_kv` 的 `key_states` 与 `value_states` 保持未复制的原生形状 `[bsz, n_kv_heads, L, head_dim]`；
  2. 仅在计算观测窗口注意力矩阵时，临时生成局部变量 `key_rep = repeat_kv(key_states, groups)` 与 `query_states` 相乘并求得每个 Query Head 的投票分 $\mathbf{s}^{\text{q}} \in \mathbb{R}^{B_{\text{batch}} \times n_q \times (L - W)}$；
  3. **在池化与 `topk` 之前，将同一 KV 组内 $G$ 个 Query Head 的分数重塑为 `[bsz, n_kv_heads, G, L - W]` 并沿组维度执行归约（Group Reduction）**：
     $$s_{h_{kv}, j}^{\text{kv}} = \operatorname{ Agg }_{g=0}^{G-1} \left( s_{h_{kv} \cdot G + g, \, j}^{\text{q}} \right), \quad \operatorname{Agg} \in \{\text{mean}, \, \text{max}, \, \text{sum}\}$$
  4. 对归约后的 `[bsz, n_kv_heads, L - W]` 执行 1D 池化与 `topk`，直接从未展开的 `key_states`（$8$ 个头）上 `gather` 出被选中的 Token，使缓存严格保持 `[bsz, n_kv_heads, B, head_dim]` 的紧凑布局！

| 对比维度 | StreamingLLM（ICLR 2024） | H2O（NeurIPS 2023） | SnapKV（NeurIPS 2024） | PyramidKV（2024） |
| :--- | :--- | :--- | :--- | :--- |
| **保留结构组成** | 前 $S$ 个 Sink + 最近 $W$ 个窗口 | 累积高分 Heavy Hitters + 最近 $W$ 个窗口 | 尾部观测窗投票聚类前缀 + 最近 $W_{\text{obs}}$ 个窗口 | 与 SnapKV 相同，但**跨层预算呈金字塔递减** |
| **重要性评分信号** | 纯位置规则（无需计算注意力分数） | 全序列因果累积注意力 $\sum_{i=j}^t A_{i,j}$ | 末尾观测窗口局部注意力 $\sum_{i=L-W}^L A_{i,j}$ + **1D 池化** | 同 SnapKV（支持结合余弦相似度 Pivot/Weighted Merge） |
| **Prefill 额外开销与 FA2 兼容性** | $O(1)$ 零开销，完全兼容（需修改 RoPE 位置传入） | 原始需 $O(L^2)$ 全矩阵列和，存在因果长度偏置，破坏原生 FA2 | **仅需计算 $[W_{\text{obs}}, L]$ 极窄尾窗，主干 100% 兼容 FlashAttention-2** | 与 SnapKV 相同，$O(W_{\text{obs}} \cdot L)$ 极低开销 |
| **长文档大海捞针（NIAH）表现** | **极差**（针一旦滑出窗口 $W$ 即彻底丢失） | 中等（早期高频词易挤占名额，且单点选词易割裂多词短语） | **极强**（尾窗精准定位提问目标，1D 池化完整保留短语簇） | **在极小预算（如 $B=64/128$）下比均匀分配的 SnapKV 进一步提升** |
| **核心适用场景** | 无需回忆早期细节的**无限多轮流式对话 / 实时语音伴侣** | 中短 Prompt、长 Decode 持续动态演化的生成任务 | **长文档 QA、代码库分析、RAG 检索长上下文 Prefill 压缩** | **显存极度受限下的超长上下文 Prefill 与 Decode 加速** |

---

### 4. Python 3 标准库实现：StreamingLLM 位置重编码、H2O vs SnapKV 池化捕获与 PyramidKV / GQA 仿真

下面的零依赖 Python 3 标准库代码从底层复现并验证了：
1. **StreamingLLM 的 Attention Sink 保持与缓存内 RoPE 位置重映射（`StartRecentKVCache` + `pos_shift`）**：证明相对位置重编码如何将最大旋转距离恒定钳制在缓存容量 $C$ 内；
2. **H2O vs SnapKV（无池化 vs 1D 池化）在大海捞针短语上的对决**：在含 3-Token 关键短语（`[5]="passcode", [6]="is", [7]="7392"`）的因果注意力矩阵上，复现为什么 H2O 与无池化投票会因早期 Sink 霸榜和单点尖峰而漏掉密码值 `[7]`，而 SnapKV 的 1D 池化能将核心峰值扩散至邻居，完整保住 `[5, 6, 7]`；
3. **PyramidKV 跨层等差金字塔预算调度（`PyramidKVCluster`）**：验证浅层高预算、深层低预算分配与总预算守恒；
4. **GQA 模型下的 `kv_head` 组内归约 vs `query_head` 独立选择**：验证组内均值聚合如何在达成跨头共识的同时消除 $G$ 倍显存膨胀。

```python
import math
from typing import Dict, List, Tuple


def apply_rope_1d(vec: List[float], pos: int, base: float = 10000.0) -> List[float]:
    """对偶数维向量施加二维旋转位置编码 RoPE"""
    d = len(vec)
    out = [0.0] * d
    for i in range(0, d, 2):
        theta = 1.0 / (base ** (i / d))
        ang = pos * theta
        c, s = math.cos(ang), math.sin(ang)
        out[i] = vec[i] * c - vec[i + 1] * s
        out[i + 1] = vec[i] * s + vec[i + 1] * c
    return out


def softmax(logits: List[float]) -> List[float]:
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    s = sum(exps)
    return [e / s for e in exps]


def avg_pool_1d_same(scores: List[float], kernel_size: int = 3) -> List[float]:
    """对齐 FasterDecoding/SnapKV: F.avg_pool1d(..., kernel_size=k, padding=k//2, stride=1)"""
    pad = kernel_size // 2
    padded = [0.0] * pad + scores + [0.0] * pad
    n = len(scores)
    return [sum(padded[i : i + kernel_size]) / kernel_size for i in range(n)]


def simulate_streaming_llm(
    K_unrotated: List[List[float]],
    q_unrotated: List[float],
    start_size: int = 2,
    recent_size: int = 4,
    use_in_cache_pos_shift: bool = True,
) -> Dict[str, object]:
    """
    严格对齐 mit-han-lab/streaming-llm (StartRecentKVCache + modify_llama.py):
    - 保留前 start_size 个 Attention Sink 与最后 recent_size 个滑动窗口 Token
    - use_in_cache_pos_shift=True 时: Key 按缓存内连续下标 [0..C-1] 旋转, Query 按 C 旋转
    - use_in_cache_pos_shift=False 时: 使用原始绝对全局位置旋转 (当 t >> L_train 时超出训练分布)
    """
    seq_len = len(K_unrotated)
    cache_size = start_size + recent_size
    assert seq_len > cache_size

    kept_global_indices = list(range(start_size)) + list(range(seq_len - recent_size, seq_len))
    d = len(q_unrotated)

    if use_in_cache_pos_shift:
        k_positions = list(range(cache_size))
        q_pos = cache_size
    else:
        k_positions = kept_global_indices
        q_pos = seq_len

    q_rot = apply_rope_1d(q_unrotated, q_pos)
    k_rots = [
        apply_rope_1d(K_unrotated[g_idx], pos)
        for g_idx, pos in zip(kept_global_indices, k_positions)
    ]
    logits = [
        sum(q_rot[c] * k_vec[c] for c in range(d)) / math.sqrt(d) for k_vec in k_rots
    ]
    weights = softmax(logits)
    sink_mass = sum(weights[:start_size])
    return {
        "kept_global_indices": kept_global_indices,
        "k_positions": k_positions,
        "q_pos": q_pos,
        "max_relative_distance": q_pos - min(k_positions),
        "sink_mass": sink_mass,
        "weights": weights,
    }


def compare_h2o_vs_snapkv_selection(
    attn_matrix: List[List[float]],
    window_size: int = 3,
    max_capacity_prompt: int = 6,
    kernel_size: int = 3,
) -> Dict[str, object]:
    """
    对比同一注意力矩阵 A [L, L] 下:
    1. H2O (FMInference/H2O): 全序列累积注意力 sum_{i=0}^{L-1} A[i, j]
    2. SnapKV 无池化投票: 仅用尾部观测窗口 sum_{i=L-W}^{L-1} A[i, j]
    3. SnapKV 完整管线 (FasterDecoding/SnapKV): 尾部观测窗口投票 + 1D 池化聚类
    """
    L = len(attn_matrix)
    prefix_len = L - window_size
    prefix_budget = max_capacity_prompt - window_size

    # 1. H2O 全序列因果累积得分
    h2o_scores = [
        sum(attn_matrix[q_idx][k_idx] for q_idx in range(L))
        for k_idx in range(prefix_len)
    ]
    h2o_top_prefix = sorted(
        sorted(range(prefix_len), key=lambda idx: h2o_scores[idx], reverse=True)[:prefix_budget]
    )

    # 2. SnapKV 尾部观测窗口原始投票 vs 1D 池化后得分
    snapkv_raw_votes = [
        sum(attn_matrix[q_idx][k_idx] for q_idx in range(L - window_size, L))
        for k_idx in range(prefix_len)
    ]
    snapkv_unpooled_top = sorted(
        sorted(range(prefix_len), key=lambda idx: snapkv_raw_votes[idx], reverse=True)[:prefix_budget]
    )
    snapkv_pooled = avg_pool_1d_same(snapkv_raw_votes, kernel_size=kernel_size)
    snapkv_top_prefix = sorted(
        sorted(range(prefix_len), key=lambda idx: snapkv_pooled[idx], reverse=True)[:prefix_budget]
    )

    return {
        "h2o_scores": h2o_scores,
        "h2o_top_prefix": h2o_top_prefix,
        "snapkv_raw_votes": snapkv_raw_votes,
        "snapkv_unpooled_top": snapkv_unpooled_top,
        "snapkv_pooled": snapkv_pooled,
        "snapkv_top_prefix": snapkv_top_prefix,
    }


def compute_pyramidkv_layer_schedule(
    num_hidden_layers: int = 8,
    max_capacity_prompt: int = 64,
    window_size: int = 16,
    beta: int = 4,
    q_len: int = 512,
) -> List[int]:
    """
    严格对齐 Zefan-Cai/KVCache-Factory (pyramidkv_utils.py::PyramidKVCluster.update_kv):
      min_num = (max_capacity_prompt - window_size) // beta
      max_num = (max_capacity_prompt - window_size) * 2 - min_num
      steps   = (max_num - min_num) // (num_hidden_layers - 1)
      layer_prefix_budget(l) = max_num - l * steps
    """
    base_prefix = max_capacity_prompt - window_size
    min_num = base_prefix // beta
    max_num = base_prefix * 2 - min_num
    if max_num >= q_len - window_size:
        max_num = q_len - window_size
        min_num = base_prefix * 2 - max_num
    steps = (max_num - min_num) // (num_hidden_layers - 1)
    return [max_num - layer_idx * steps for layer_idx in range(num_hidden_layers)]


def gqa_group_reduced_selection(
    group_query_scores: List[List[float]],
    budget: int = 2,
    agg_mode: str = "mean",
) -> Tuple[List[List[int]], List[int]]:
    """
    对齐 Zefan-Cai/KVCache-Factory (_reduce_group_scores + _select_topk_kv):
    对比 query_head 粒度 (每个 Query Head 各自选 Top-K, 破坏 GQA 共享导致显存膨胀 G 倍)
    与 kv_head 粒度 (先对组内 G 个 Query Head 的分数按 mean/max/sum 聚合, 再统一选 1 份 Top-K)。
    """
    G = len(group_query_scores)
    prefix_len = len(group_query_scores[0])

    per_qhead_indices = [
        sorted(sorted(range(prefix_len), key=lambda j: group_query_scores[g][j], reverse=True)[:budget])
        for g in range(G)
    ]

    reduced_scores = []
    for j in range(prefix_len):
        col = [group_query_scores[g][j] for g in range(G)]
        if agg_mode == "mean":
            reduced_scores.append(sum(col) / G)
        elif agg_mode == "max":
            reduced_scores.append(max(col))
        elif agg_mode == "sum":
            reduced_scores.append(sum(col))
        else:
            raise ValueError(f"Unsupported agg_mode: {agg_mode}")

    kv_head_indices = sorted(
        sorted(range(prefix_len), key=lambda j: reduced_scores[j], reverse=True)[:budget]
    )
    return per_qhead_indices, kv_head_indices


# --- 1. 验证 StreamingLLM Sink 保留与 In-Cache RoPE 位置重映射 ---
seq_len_sim = 12
K_stream = [
    [3.2, 0.1, 2.8, -0.2] if t < 2 else [0.4 * math.cos(t * 0.5), 0.3 * math.sin(t * 0.5), -0.2, 0.25]
    for t in range(seq_len_sim)
]
q_cur = [0.5, 0.1, 0.4, -0.1]

res_shifted = simulate_streaming_llm(K_stream, q_cur, start_size=2, recent_size=4, use_in_cache_pos_shift=True)
res_unshifted = simulate_streaming_llm(K_stream, q_cur, start_size=2, recent_size=4, use_in_cache_pos_shift=False)

assert res_shifted["kept_global_indices"] == [0, 1, 8, 9, 10, 11]
assert res_shifted["k_positions"] == [0, 1, 2, 3, 4, 5] and res_shifted["q_pos"] == 6
assert res_shifted["max_relative_distance"] == 6
assert res_unshifted["max_relative_distance"] == 12
assert res_shifted["sink_mass"] > 0.40

# --- 2. 验证 H2O (因果长度偏置割裂短语) vs SnapKV (尾部窗口投票 + 1D 池化捕获完整针短语) ---
# 构造 L=12 的下三角因果注意力矩阵:
#   - 位置 0, 1: Attention Sinks (每步吸收固定背景注意力)
#   - 位置 5, 6, 7: 埋藏在上下文中段的 3-Token 关键实体短语 ("Needle": [5]="passcode", [6]="is", [7]="7392")
#   - 位置 9, 10, 11: 尾部的 Question 观测窗口 (W=3), 强烈触发对核心锚点 j=6 的检索
L_sim = 12
W_sim = 3
A_sim = [[0.0] * L_sim for _ in range(L_sim)]
for i in range(L_sim):
    for j in range(i + 1):
        if i >= L_sim - W_sim:
            # 尾部问题窗口 (i=9,10,11): 强烈关注核心针锚点 j=6 (0.56) 与紧邻上下文 j=5,7 (0.06)
            if j == 6:
                A_sim[i][j] = 0.56
            elif j in (5, 7):
                A_sim[i][j] = 0.06
            elif j in (0, 1):
                A_sim[i][j] = 0.09
            else:
                A_sim[i][j] = 0.14 / max(1, i - 3)
        else:
            # 前缀阅读阶段 (i<9): 注意力集中在句首 Sink (j=0,1) 与早期段落首词 (j=2)
            if j in (0, 1):
                A_sim[i][j] = 0.36 if i > 0 else 1.0
            elif j == 2:
                A_sim[i][j] = 0.20
            else:
                A_sim[i][j] = 0.08 / max(1, i - 1)
    row_s = sum(A_sim[i][: i + 1])
    for j in range(i + 1):
        A_sim[i][j] /= row_s

evict_cmp = compare_h2o_vs_snapkv_selection(A_sim, window_size=3, max_capacity_prompt=6, kernel_size=3)
# H2O 选出前缀 Top-3: 被累计 12 次的 Sink [0, 1] 挤占名额, 仅保住孤立词 [6], 丢失密码值 [7]!
assert evict_cmp["h2o_top_prefix"] == [0, 1, 6]
# 若 SnapKV 不做 1D 池化: 同样只选出 [0, 1, 6], 丢失紧邻的 [5] 和 [7]!
assert evict_cmp["snapkv_unpooled_top"] == [0, 1, 6]
# SnapKV 经 1D 池化后: 核心峰值 j=6 将高分扩散给相邻词 j=5, 7, 完整保住整个 3-Token Needle 短语 [5, 6, 7]!
assert evict_cmp["snapkv_top_prefix"] == [5, 6, 7]

# --- 3. 验证 PyramidKV 金字塔预算分配 ---
pyr_budgets = compute_pyramidkv_layer_schedule(
    num_hidden_layers=8, max_capacity_prompt=64, window_size=16, beta=4, q_len=512
)
uniform_prefix_budget = 64 - 16  # 48
assert pyr_budgets == [84, 74, 64, 54, 44, 34, 24, 14]
assert pyr_budgets[0] == 6.0 * pyr_budgets[-1]  # 浅层 0 预算 (84) 是深层 7 预算 (14) 的 6 倍

# --- 4. 验证 GQA 组内归约 (kv_head vs query_head 粒度) ---
gqa_scores = [
    [0.45, 0.05, 0.35, 0.05, 0.05, 0.05],  # Q-head 0 关注 pos 0, 2
    [0.42, 0.38, 0.05, 0.05, 0.05, 0.05],  # Q-head 1 关注 pos 0, 1
    [0.40, 0.05, 0.05, 0.36, 0.09, 0.05],  # Q-head 2 关注 pos 0, 3
    [0.08, 0.05, 0.05, 0.44, 0.33, 0.05],  # Q-head 3 关注 pos 3, 4
]
qhead_sets, kvhead_set = gqa_group_reduced_selection(gqa_scores, budget=2, agg_mode="mean")
assert len({tuple(s) for s in qhead_sets}) == 4
assert kvhead_set == [0, 3]

print(
    f"1. StreamingLLM: kept_global={res_shifted['kept_global_indices']} -> "
    f"in_cache_pos={res_shifted['k_positions']}, q_pos={res_shifted['q_pos']} "
    f"(max_dist={res_shifted['max_relative_distance']} vs unshifted={res_unshifted['max_relative_distance']})"
)
print(
    f"2. Eviction Prefix Top-3: H2O={evict_cmp['h2o_top_prefix']} vs "
    f"SnapKV_unpooled={evict_cmp['snapkv_unpooled_top']} vs "
    f"SnapKV_pooled={evict_cmp['snapkv_top_prefix']} (preserves full needle [5,6,7])"
)
print(
    f"3. PyramidKV 8-Layer Prefix Schedule: {pyr_budgets} "
    f"(mean={sum(pyr_budgets)/len(pyr_budgets):.1f} vs uniform={uniform_prefix_budget})"
)
print(
    f"4. GQA KV-Head Reduction (G=4): per_query_head={qhead_sets} -> "
    f"kv_head_consensus={kvhead_set} (4x memory reduction)"
)
print("All StreamingLLM, H2O, SnapKV, and PyramidKV eviction assertions passed!")
```

实际运行输出：

```text
1. StreamingLLM: kept_global=[0, 1, 8, 9, 10, 11] -> in_cache_pos=[0, 1, 2, 3, 4, 5], q_pos=6 (max_dist=6 vs unshifted=12)
2. Eviction Prefix Top-3: H2O=[0, 1, 6] vs SnapKV_unpooled=[0, 1, 6] vs SnapKV_pooled=[5, 6, 7] (preserves full needle [5,6,7])
3. PyramidKV 8-Layer Prefix Schedule: [84, 74, 64, 54, 44, 34, 24, 14] (mean=49.0 vs uniform=48)
4. GQA KV-Head Reduction (G=4): per_query_head=[[0, 2], [0, 1], [0, 3], [3, 4]] -> kv_head_consensus=[0, 3] (4x memory reduction)
All StreamingLLM, H2O, SnapKV, and PyramidKV eviction assertions passed!
```

---

## 延伸 / 追问

**追问 1：在多轮长对话（Multi-turn Conversation）或先给长文档、随后用户连续追问不同细节的场景下，直接把被 SnapKV / H2O 驱逐掉的 KV 永久物理删除会带来什么致命问题？工程上（如 Quest / ArkVale / ShadowKV）是如何把“永久驱逐（Permanent Eviction）”改造为“动态选择性召回（Query-Aware Page Selection）”的？**
1. **永久删除在多轮问答中的致命盲区**：
   SnapKV 在第 1 轮 Prefill 结束时，是根据**第 1 轮的问题（如“总结第三章的财务数据”）**作为尾部观测窗口来筛选前缀 KV 的。如果此时把第一章、第二章未命中的 KV 物理删除，当用户在第 2 轮突然追问“第一章提到的法务免责条款是什么？”时，相关 Token 早在第 1 轮结束时就被永久销毁了，模型必然发生失忆或幻觉！
2. **从“物理删除”到“全量驻留/卸载 + 页级动态稀疏选择（Quest）”**：
   为支持任意多轮切换关注焦点，**Quest（Query-Aware Sparsity, Tang et al., ICML 2024）** 与 **ShadowKV** 提出了**不物理删除历史 KV，但每步解码只按需加载 Top-$K$ 物理页（Pages）**的架构：
   - 将 KV Cache 按固定页大小（如 `page_size = 16` Tokens）切块，并为每一页维护两个极轻量的元数据向量：通道逐元素最大值 $\mathbf{k}_{\max}^{(p)} = \max_{t \in p} \mathbf{k}_t \in \mathbb{R}^d$ 与最小值 $\mathbf{k}_{\min}^{(p)} = \min_{t \in p} \mathbf{k}_t \in \mathbb{R}^d$（仅占原页大小的 $2 / 16 = 12.5\%$）；
   - 在每步 Decode 生成新查询 $\mathbf{q}_t$ 时，利用坐标符号匹配快速估算 $\mathbf{q}_t$ 在每个页面 $p$ 内可能取得的最大注意力上界分数：
     $$\hat{s}_p(\mathbf{q}_t) = \sum_{c=1}^d \max\!\left(q_{t,c} \cdot k_{\max, c}^{(p)}, \; q_{t,c} \cdot k_{\min, c}^{(p)}\right)$$
   - 仅将 $\hat{s}_p(\mathbf{q}_t)$ 排名前 $K$ 的页面从 HBM（或 CPU 内存）读入 SRAM 计算真实注意力。这样既在 Decode 阶段享受了与 KV 驱逐完全相同的 HBM 带宽加速，又在多轮对话中 100% 保留了随时找回任意历史段落的能力。

**追问 2：PyramidKV 为不同层分配了不同大小的 KV 预算，而 AdaKV（Feng et al., 2024）和 HeadKV 进一步在同一层内部为不同的注意力头（Attention Heads）分配了非均匀预算。这样做在 GPU 底层算子层面会引发什么张量形状难题？该如何高效实现？**
1. **不规则张量（Ragged Tensor）导致的 Batch 矩阵乘失效**：
   在标准 Transformer 或同层等预算的 SnapKV / PyramidKV 中，同一层所有注意力头保留的 Token 数量完全相同（皆为 $b_l$），因此缓存可以直接存为规整的四维张量 `[bsz, num_kv_heads, b_l, head_dim]`，直接调用标准批处理 SDPA。
   然而，同一层内不同注意力头的功能高度分化：少数“检索头（Retrieval Heads）”需要较大的缓存预算来跨越长距离捞取事实，而大量“局部语法头（Local/Induction Heads）”只需极小的窗口预算。当 **AdaKV** 在单层总预算 $\sum_{h=1}^H b_{l,h} = H \cdot b_l$ 下按各头注意力质量动态分配预算时，不同头保留的长度 $b_{l,1} \neq b_{l,2} \neq \dots \neq b_{l,H}$ 变得参差不齐，无法再拼成标准四维矩形张量（若用 Padding 补齐到 $\max_h b_{l,h}$，则完全丧失了节省显存和带宽的意义）。
2. **基于扁平化存储与 `flash_attn_varlen_func` 的零填充解法**：
   如 `KVCache-Factory` 中的 `DynamicCacheSplitHeadFlatten` 与 `AdaKVCluster.update_kv` 所示，工程上将同一层所有头的 KV 沿着头与序列维度展平拼接为一个紧凑的二维张量 `flat_kv`（形状为 `[\sum_h b_{l,h}, head_dim]`），并维护前缀和偏移数组 `cu_seqlens_k = [0, b_{l,1}, b_{l,1}+b_{l,2}, ...]`（长度为 $H+1$）与 `cu_seqlens_q = [0, 1, 2, ..., H]`。在 Decode 阶段，将“$H$ 个不同长度的注意力头”伪装成“Batch 大小为 $H$ 的变长序列（Varlen Sequences）”，直接调用 FlashAttention-2 原生的 `flash_attn_varlen_func` 内核即可在零 Padding 浪费下一次性完成并行计算！

**追问 3：除了直接把低分 Token 从缓存中丢弃（Hard Eviction），有没有办法把被驱逐 Token 的信息“吸收合并”到保留下来的 Token 中（如 CAM / LOOK-M / KVMerger）？合并时需要遵守什么数学约束？**
有！如 `KVCache-Factory`（`pyramidkv_utils.py::merge_kv`）实现的 **Pivot Merge（LOOK-M）** 与 **Weighted Merge**：
1. 在选出保留集 $\mathcal{I}_{\text{keep}}$ 与待驱逐集 $\mathcal{I}_{\text{drop}}$ 后，计算每个待驱逐键向量 $\mathbf{k}_u \in \mathcal{I}_{\text{drop}}$ 与所有保留键向量 $\mathbf{k}_v \in \mathcal{I}_{\text{keep}}$ 之间的余弦相似度：
   $$v^*(u) = \arg\max_{v \in \mathcal{I}_{\text{keep}}} \frac{\mathbf{k}_u \cdot \mathbf{k}_v}{\|\mathbf{k}_u\|_2 \|\mathbf{k}_v\|_2}, \quad \text{sim}_u = \max_{v \in \mathcal{I}_{\text{keep}}} \cos(\mathbf{k}_u, \mathbf{k}_v)$$
2. 利用 `scatter_add_` 将每个待驱逐 Token $(u)$ 按相似度权重 $w_u = \frac{\text{sim}_u + 1}{2}$ 归并到与其最相似的保留锚点 $v^*(u)$ 上：
   $$\tilde{\mathbf{k}}_v = \frac{\mathbf{k}_v + \sum_{u: v^*(u)=v} w_u \mathbf{k}_u}{1 + \sum_{u: v^*(u)=v} w_u}, \qquad \tilde{\mathbf{v}}_v = \frac{\mathbf{v}_v + \sum_{u: v^*(u)=v} w_u \mathbf{v}_u}{1 + \sum_{u: v^*(u)=v} w_u}$$
3. **关键约束**：合并只能在**已经施加了 RoPE 之后（Post-RoPE）**的同空间向量上进行，或者仅合并语义高度冗余的同段落相邻词；同时，最近观测窗口 $\mathcal{W}_{\text{recent}}$ 与句首 Attention Sink 严禁被异常远距离噪声污染，从而在极低预算下兼顾精确召回与全局摘要感知。

---

## 常见误区

- **误区一：“StreamingLLM 既然能让 Llama-2 处理长达 400 万 Token 的文本流且不崩，说明它可以用来对一整本百万字小说做全文细节问答（长上下文理解）。”**
  事实：**“无限流式推理（Infinite Streaming）”完全不等于“无限长上下文记忆（Infinite Context Understanding）”！** StreamingLLM 的物理缓存大小恒定为 $S + W$（例如 $4 + 4092 = 4096$）。它之所以在 400 万 Token 上困惑度不崩，是因为保留的 4 个 Sink Token 稳住了 Softmax 分母，且语言建模的局部困惑度主要由最近的 $W$ 个词决定。但任何在 $t - W$ 之前滑出窗口的事实细节都已经从显存中被彻底抹除，模型绝对无法回答窗口之外的历史细节。若需跨全文检索事实，必须使用 SnapKV / PyramidKV、Quest 动态选页或外部 RAG。
- **误区二：“在实现 StreamingLLM 时，只需在标准 Hugging Face `past_key_values`（已乘过 RoPE）上切片保留前 4 个和后 $W$ 个 Token 就能无限生成。”**
  事实：**如果在 RoPE 旋转之后再做缓存切片（Post-RoPE Eviction），一旦生成总步数 $t$ 超过模型预训练最大长度 $L_{\text{train}}$，输出依然会彻底乱码！** 因为此时缓存中 Sink Token 的旋转角停留在位置 $0\sim 3$，而新生成 Token 的旋转角已经增长到 $t > L_{\text{train}}$，两者内积中的相对旋转角 $(t - 0)\theta$ 远远超出了模型训练期见过的相位范围。正确实现必须在旋转前（Pre-RoPE）缓存 Key，并在每步注意力计算时按缓存内连续槽位 $[0, 1, \dots, S+W-1]$ 动态重赋 RoPE 位置。
- **误区三：“在 GQA 模型（如 Llama-3）上接入 SnapKV 或 H2O 时，直接对 `repeat_kv` 展开后的 32 个注意力头分别求 Top-$K$ 裁剪，就能按压缩比例降低显存。”**
  事实：**在 `repeat_kv` 之后按每个 Query Head 独立裁剪，会让压缩后的 KV Cache 显存无端暴涨 $G = n_q / n_{kv}$ 倍（在 Llama-3-8B 上暴涨 4 倍）！** 比如原本 8 个 KV Head 存 2048 个 Token 占用的空间，如果在展开成 32 个 Query Head 后各自独立选出 512 个不同的 Token，由于 32 个头的索引集合互不相同，缓存只能以 32 个头的形式存储（$32 \times 512 = 8 \times 2048$），导致“压缩 4 倍后显存竟然一分钱没省”！必须在 `topk` 之前对同一组内 $G$ 个 Query Head 的注意力得分做组内归约（`mean` / `max` / `sum`），在 `kv_head` 粒度上选出唯一共识索引集。

---

## 参考

- 选题线索：[wxqnl/WiA--What-is-Attention (`Attention/StreamingLLM.md`)](https://github.com/wxqnl/WiA--What-is-Attention/blob/e3ce79fbc81df4a105176ba2ac1cf8b775eaae7a/Attention/StreamingLLM.md)（固定 commit `e3ce79f`）与 [Jackie2049/perpetual-learning (`notebook/fundamentals/attention-sink-streamingllm-deep-dive.md`)](https://github.com/Jackie2049/perpetual-learning/blob/d723604718016521bb016607ba05858edabdc8fe/notebook/fundamentals/attention-sink-streamingllm-deep-dive.md)（固定 commit `d723604`），独立重构并扩展源码级对比。
- Xiao et al., [Efficient Streaming Language Models with Attention Sinks (StreamingLLM)](https://arxiv.org/abs/2309.17453)，ICLR 2024，及官方源码 [mit-han-lab/streaming-llm (`streaming_llm/kv_cache.py` & `streaming_llm/pos_shift/modify_llama.py`)](https://github.com/mit-han-lab/streaming-llm/blob/2e5042606d69933d88fbf909bd77907456b9b4dd/streaming_llm/pos_shift/modify_llama.py)（固定 commit `2e50426`）：Attention Sink 成因、Pre-RoPE `StartRecentKVCache` 与缓存内相对位置重编码实现。
- Zhang et al., [H2O: Heavy-Hitter Oracle for Efficient Generative Inference of Large Language Models](https://arxiv.org/abs/2306.14048)，NeurIPS 2023，及官方源码 [FMInference/H2O (`h2o_hf/utils_hh/modify_llama.py`)](https://github.com/FMInference/H2O/blob/ac75c2a8a9e76832b2a4139b9363373b56336bfb/h2o_hf/utils_hh/modify_llama.py)（固定 commit `ac75c2a`）：累积注意力评分与 Heavy-Hitter + Recent 双预算驱逐状态机。
- Li et al., [SnapKV: LLM Knows What You Are Looking for Before Generation](https://arxiv.org/abs/2404.14469)，NeurIPS 2024，及官方源码 [FasterDecoding/SnapKV](https://github.com/FasterDecoding/SnapKV/tree/e216ddc84c5bd210378cbdbbba12ba02102aa640)（固定 commit `e216ddc`）：尾部观测窗口投票与 1D 池化聚类保护机制。
- Cai et al., [PyramidKV: Dynamic KV Cache Compression based on Pyramidal Information Funneling](https://arxiv.org/abs/2406.02069)，2024，及官方统一评测与实现库 [Zefan-Cai/KVCache-Factory (`pyramidkv/pyramidkv_utils.py` & `docs/gqa_cache_layout.md`)](https://github.com/Zefan-Cai/KVCache-Factory/blob/68cd9551a63fedf362ddb0edb008badd04c24996/pyramidkv/pyramidkv_utils.py)（固定 commit `68cd955`）：跨层等差金字塔预算公式、GQA `kv_head` 组内分数归约（`_reduce_group_scores`）与相似度加权合并（`merge_kv`）。
- Tang et al., [Quest: Query-Aware Sparsity for Efficient Long-Context LLM Inference](https://arxiv.org/abs/2406.10774)，ICML 2024：多轮问答下保留全量 KV 并通过页面极值包围盒动态选择 Top-$K$ 页面的对比方案。

来源访问与示例核验日期：**2026-11-11**。仅执行标准库下 StreamingLLM 缓存内 RoPE 重映射、H2O 与 SnapKV 池化选词对比、PyramidKV 金字塔预算及 GQA 组内归约数值验证，未运行多卡长上下文基准压测。
