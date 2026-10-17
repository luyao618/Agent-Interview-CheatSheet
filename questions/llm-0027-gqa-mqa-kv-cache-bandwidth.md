---
id: llm-0027
title: GQA（分组查询注意力）与 MQA 是如何缓解 KV Cache 显存与带宽瓶颈的，与标准 MHA 相比如何权衡？
category: llm
tags: [gqa, mqa, mha, kv-cache, attention, inference, uptraining]
difficulty: medium
role: engineer
contributor: 佚名
source: 公开大模型推理与架构高频面试题整理第 18 题扩展改编；GQA 原论文与 Transformers 官方源码核实（见参考）
status: published
updated: 2026-10-17
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-10-17
    updated: 2026-10-17
---

## 问题

在自回归大语言模型（LLM）的 Decode 阶段，每生成一个新 Token 都需要从高带宽显存（HBM）中读取所有历史位置的 Key 和 Value 缓存（KV Cache），这使得长上下文和高并发推理成为典型的访存受限（Memory-bandwidth Bound）过程。

为了缓解标准多头注意力（Multi-Head Attention, MHA）的 KV Cache 压力，业界演进出了多查询注意力（Multi-Query Attention, MQA）与分组查询注意力（Grouped-Query Attention, GQA，如 LLaMA-2 70B、LLaMA-3、Qwen2 等广泛采用）。请深入剖析：
1. MHA、MQA 与 GQA 在 Query、Key、Value 头数分配与投影参数矩阵维度上有何本质区别？它们对 KV Cache 显存占用与访存带宽的压缩比例如何计算？
2. 在前向计算中，当 $G$ 个 KV 头需要与 $H$ 个 Query 头做注意力内积时（$H$ 为 $G$ 的整数倍），底层是如何完成组内映射与广播对齐（如 `repeat_kv`）的？
3. 如何通过 Uptraining（继续预训练转换）将已有的 MHA 预训练模型低成本改造为 GQA/MQA 模型？在工程实践中如何权衡组数 $G$、张量并行（TP）切分与表达能力？

本题由公开大模型架构面试整理扩展改编，不是已核实的企业真题；不采信脱离具体上下文长度、Batch Size 与硬件带宽条件的绝对推理加速比承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-10-17

**GQA（Grouped-Query Attention）通过将 $H$ 个 Query 注意力头划分为 $G$ 个组（$1 < G < H$），并让同一组内的 $H/G$ 个 Query 头共享同一套 Key 和 Value 头，直接将 KV Cache 的显存容量与每步 Decode 的 HBM 访存带宽需求降低为标准 MHA 的 $G/H$（压缩 $H/G$ 倍），在几乎不损失模型生成质量的前提下获得了接近 MQA 的推理吞吐。**

现有 [llm-0010](llm-0010-causal-attention-architecture.md) 介绍了标准因果自注意力的计算机制，[llm-0016](llm-0016-quantization-local-memory-budget.md) 讨论了整机部署的显存预算，[llm-0018](llm-0018-kv-cache-prefill-decode.md) 解析了 KV Cache 在 Prefill 与 Decode 阶段的复用原理。本题聚焦 **MHA / MQA / GQA 的头数分组拓扑、KV 缓存与带宽定量推导、组内广播计算流以及 Uptraining 权重转换机制**。

---

### 1. MHA、MQA 与 GQA 的结构对比与 KV Cache 定量推导

设模型隐藏层维度为 $d_{\text{model}}$，Query 总头数为 $H$，每个头的维度为 $d_k = d_v = d_{\text{head}} = d_{\text{model}} / H$，层数为 $L$，批量大小为 $B$，当前上下文序列长度为 $S$，单个浮点数占 $b$ 字节（例如 FP16/BF16 下 $b=2$）。

三者在注意力投影层与缓存结构上的核心差异如下：

| 维度 | 标准多头注意力 (MHA) | 多查询注意力 (MQA) | 分组查询注意力 (GQA-$G$) |
| --- | --- | --- | --- |
| **Query 头数** | $H$ | $H$ | $H$ |
| **Key / Value 头数** | $H$（一对一独立） | $1$（全场全局共享） | $G$（分 $G$ 组，每组 $H/G$ 个 Q 头共享 1 个 KV 头） |
| **$W_Q$ 投影参数形状** | $d_{\text{model}} \times (H \cdot d_{\text{head}})$ | $d_{\text{model}} \times (H \cdot d_{\text{head}})$ | $d_{\text{model}} \times (H \cdot d_{\text{head}})$ |
| **$W_K, W_V$ 投影参数形状** | $d_{\text{model}} \times (H \cdot d_{\text{head}})$ | $d_{\text{model}} \times (1 \cdot d_{\text{head}})$ | $d_{\text{model}} \times (G \cdot d_{\text{head}})$ |
| **单 Token 跨全层 KV Cache 大小** | $2 \cdot b \cdot L \cdot H \cdot d_{\text{head}}$ | $2 \cdot b \cdot L \cdot 1 \cdot d_{\text{head}}$ | $2 \cdot b \cdot L \cdot G \cdot d_{\text{head}}$ |
| **相对 MHA 的 KV 缓存压缩比** | $1\times$（基准） | $H\times$（最大压缩） | $\frac{H}{G}\times$（可调折中） |
| **表达能力与训练稳定性** | 最高（多视角特征捕捉） | 明显退化，训练易出现不稳定性 | 接近 MHA，显著优于 MQA |

> **统一视角**：GQA 是注意力头共享机制的广义形式（Generalized Multi-Query Attention）——当 $G = H$ 时，GQA 退化为标准 **MHA**；当 $G = 1$ 时，GQA 退化为极端共享的 **MQA**。

#### 实例量化计算（以 70B 级模型参数为例）
假设 $L=80, H=64, d_{\text{head}}=128$，采用 BF16（$b=2$ 字节），序列长度 $S=32768$，Batch Size $B=16$：
- **标准 MHA（$G=64$）**：
  $$\text{KV Cache}_{\text{MHA}} = 2 \times 2 \times 80 \times 64 \times 128 \times 32768 \times 16 = 1,374,389,534,720 \text{ Bytes} = 1280 \text{ GiB}$$
- **GQA-8（$G=8$，每 8 个 Q 头共享 1 个 KV 头）**：
  $$\text{KV Cache}_{\text{GQA-8}} = \frac{1280 \text{ GiB}}{64 / 8} = 160 \text{ GiB}$$
- **MQA（$G=1$）**：
  $$\text{KV Cache}_{\text{MQA}} = \frac{1280 \text{ GiB}}{64} = 20 \text{ GiB}$$

可以看到，GQA-8 直接将 1280 GiB 的 KV Cache 砍到了 160 GiB（节省 87.5%），使原本需要十几张 80GB 显卡才能放下的长序列批次得以在单机 8 卡内驻留，且每生成一个新 Token 从 HBM 搬运 KV 的字节数也同步减少了 87.5%。

---

### 2. 前向计算的组内映射与 `repeat_kv` 实现细节

在 GQA 的前向传播中，输入隐状态 $X \in \mathbb{R}^{B \times S \times d_{\text{model}}}$ 经过线性投影后得到：
- $Q \in \mathbb{R}^{B \times H \times S \times d_{\text{head}}}$
- $K, V \in \mathbb{R}^{B \times G \times S \times d_{\text{head}}}$

设每组包含的 Query 头数为 $r = H / G$（即 `num_key_value_groups`）。对于第 $h \in \{0, 1, \dots, H-1\}$ 个 Query 头，它所对应的共享 Key/Value 头索引为：
$$g(h) = \left\lfloor \frac{h}{r} \right\rfloor = \text{h // (H // G)}$$

将该组内的单份 $K_{g(h)}, V_{g(h)}$ 与对应的 $Q_h$ 计算缩放点积注意力：
$$\text{head}_h = \text{ softmax}\left(\frac{Q_h K_{g(h)}^\top}{\sqrt{d_{\text{head}}}} + M\right) V_{g(h)}$$

#### 源码级张量对齐与 Kernel 优化
在 Hugging Face `transformers`（如 `modeling_llama.py` 的 `repeat_kv`）的朴素 PyTorch 实现中，为了让维度为 $(B, G, S, d_{\text{head}})$ 的 $K, V$ 能与 $(B, H, S, d_{\text{head}})$ 的 $Q$ 直接调用批量矩阵乘法（`torch.matmul`），会通过插入维度并 `expand` + `reshape` 将 $K, V$ 扩展为 $H$ 个头。

但**在生产级推理引擎（如 FlashAttention-2 / vLLM PagedAttention）的融合算子内部，绝不会在 HBM 中真正复制出 $H$ 份物理 KV 显存**，而是直接在 GPU SRAM 寄存器/共享内存层面通过索引偏移 `h // r` 让同一组内的多个 Query 头并发读取同一块 KV 缓存块，从而真正兑现 HBM 带宽的节省。

---

### 3. 从 MHA 到 GQA 的 Uptraining（继续预训练转换）

Ainslie et al. (EMNLP 2023) 指出，不需要从零开始预训练一个 GQA 模型，可以通过 **两步 Uptraining 方案** 将已有的开源 MHA 模型（如 T5、LLaMA-1）低成本转化为 GQA 模型：

1. **投影权重均值池化（Mean Pooling Checkpoint Conversion）**：
   对于原 MHA 模型的 $H$ 个 Key 投影矩阵 $\{W_K^{(0)}, W_K^{(1)}, \dots, W_K^{(H-1)}\}$ 和 Value 投影矩阵 $\{W_V^{(0)}, \dots, W_V^{(H-1)}\}$，按组长 $r = H / G$ 划分为 $G$ 组，对组内原有的投影矩阵直接求算术平均（Mean Pooling），作为新 GQA 第 $g$ 个 KV 头的初始权重：
   $$\widetilde{W}_K^{(g)} = \frac{1}{r} \sum_{j = g \cdot r}^{(g+1)r - 1} W_K^{(j)}, \quad \widetilde{W}_V^{(g)} = \frac{1}{r} \sum_{j = g \cdot r}^{(g+1)r - 1} W_V^{(j)}$$
   论文消融实验证明，**Mean Pooling 显著优于随机初始化（Random Initialization）或只挑选组内第一个头（First Head Selection）**，因为它最大程度保留了原多头预训练积累的特征空间信息。
2. **小比例继续预训练（Short Uptraining）**：
   使用转换后的权重，按照原预训练配方继续训练仅约 **$\alpha = 5\%$** 的原始预训练步数/算力，模型即可迅速适应组内共享 KV 的结构约束，恢复到接近原 MHA 的评测指标。

---

### 4. 可运行的标准库实现：GQA 组映射、Uptraining 均值池化与显存核算

以下代码使用纯 Python 3 标准库实现 MHA / MQA / GQA 的 KV Cache 容量核算、Uptraining 权重 Mean Pooling 转换，以及 GQA 分组注意力前向计算与 `repeat_kv` 等价性验证：

```python
import math
from typing import List, Tuple


def kv_cache_gib(
    batch_size: int,
    seq_len: int,
    num_layers: int,
    num_kv_heads: int,
    head_dim: int,
    bytes_per_elem: int = 2,
) -> float:
    """计算指定 KV 头数下的 KV Cache 总显存 (GiB)"""
    total_bytes = 2 * bytes_per_elem * num_layers * num_kv_heads * head_dim * seq_len * batch_size
    return total_bytes / (1024 ** 3)


def mean_pool_kv_heads(mha_heads: List[List[float]], num_groups: int) -> List[List[float]]:
    """
    模拟 GQA Uptraining 的 Checkpoint 转换：
    将 H 个头的参数向量 (H, D) 按组进行 Mean Pooling 聚合为 (G, D)
    """
    num_q_heads = len(mha_heads)
    assert num_q_heads % num_groups == 0, "Query 头数必须能被 G 整除"
    group_size = num_q_heads // num_groups
    dim = len(mha_heads[0])

    pooled: List[List[float]] = []
    for g in range(num_groups):
        group_slice = mha_heads[g * group_size : (g + 1) * group_size]
        mean_vec = [
            sum(group_slice[i][d] for i in range(group_size)) / group_size
            for d in range(dim)
        ]
        pooled.append(mean_vec)
    return pooled


def gqa_attention_single_step(
    q_heads: List[List[float]],
    k_cache: List[List[List[float]]],
    v_cache: List[List[List[float]]],
) -> Tuple[List[List[float]], List[List[float]]]:
    """
    单步 Decode 的 GQA 注意力计算 (直接通过 h // group_size 索引共享 KV，无物理复制)
    q_heads: (H, d_head)
    k_cache, v_cache: (G, seq_len, d_head)
    返回: (H, d_head) 输出向量列表, (H, seq_len) 注意力权重列表
    """
    num_q_heads = len(q_heads)
    num_kv_heads = len(k_cache)
    assert num_q_heads % num_kv_heads == 0
    group_size = num_q_heads // num_kv_heads
    head_dim = len(q_heads[0])
    scale = 1.0 / math.sqrt(head_dim)

    outputs: List[List[float]] = []
    attn_weights_all: List[List[float]] = []

    for h in range(num_q_heads):
        kv_idx = h // group_size  # 组内映射：决定当前 Q 头读取哪一个 KV 头
        q_vec = q_heads[h]
        k_seq = k_cache[kv_idx]
        v_seq = v_cache[kv_idx]

        # 计算缩放点积分数
        scores = [
            sum(q_vec[d] * k_token[d] for d in range(head_dim)) * scale
            for k_token in k_seq
        ]
        max_s = max(scores)
        exps = [math.exp(s - max_s) for s in scores]
        denom = sum(exps)
        probs = [e / denom for e in exps]
        attn_weights_all.append(probs)

        # 加权聚合 Value
        out_vec = [
            sum(probs[t] * v_seq[t][d] for t in range(len(v_seq)))
            for d in range(head_dim)
        ]
        outputs.append(out_vec)

    return outputs, attn_weights_all


# 1. 验证 70B 模型 (L=80, H=64, d_head=128, B=16, S=32768, BF16) 的 KV Cache 压缩
mha_mem = kv_cache_gib(16, 32768, 80, num_kv_heads=64, head_dim=128)
gqa8_mem = kv_cache_gib(16, 32768, 80, num_kv_heads=8, head_dim=128)
mqa_mem = kv_cache_gib(16, 32768, 80, num_kv_heads=1, head_dim=128)
assert mha_mem == 1280.0
assert gqa8_mem == 160.0
assert mqa_mem == 20.0

# 2. 验证 Uptraining Mean Pooling 转换 (H=4 -> G=2)
raw_k_heads = [
    [1.0, 2.0],
    [3.0, 4.0],
    [10.0, 20.0],
    [30.0, 40.0],
]
pooled_k = mean_pool_kv_heads(raw_k_heads, num_groups=2)
assert pooled_k == [[2.0, 3.0], [20.0, 30.0]]

# 3. 验证 GQA (H=4, G=2, S=2, d_head=2) 前向计算与 repeat_kv 展开完全等价
q_demo = [
    [1.0, 0.0],  # Group 0, Q0
    [0.0, 1.0],  # Group 0, Q1
    [1.0, 1.0],  # Group 1, Q2
    [2.0, -1.0], # Group 1, Q3
]
k_cache_gqa = [
    [[1.0, 0.0], [0.0, 1.0]],  # KV Head 0 (被 Q0, Q1 共享)
    [[0.5, 0.5], [1.5, -0.5]], # KV Head 1 (被 Q2, Q3 共享)
]
v_cache_gqa = [
    [[10.0, 20.0], [30.0, 40.0]],
    [[5.0, 15.0], [25.0, 35.0]],
]

out_direct, weights_direct = gqa_attention_single_step(q_demo, k_cache_gqa, v_cache_gqa)

# 构造显式 repeat_kv 后的等效 4 头缓存 (G=2 -> H=4)
k_repeated = [k_cache_gqa[0], k_cache_gqa[0], k_cache_gqa[1], k_cache_gqa[1]]
v_repeated = [v_cache_gqa[0], v_cache_gqa[0], v_cache_gqa[1], v_cache_gqa[1]]
out_repeated, _ = gqa_attention_single_step(q_demo, k_repeated, v_repeated)

for h in range(4):
    for d in range(2):
        assert math.isclose(out_direct[h][d], out_repeated[h][d], rel_tol=1e-12)

print(f"70B KV Cache (B=16, S=32K): MHA={mha_mem:.0f}GiB, GQA-8={gqa8_mem:.0f}GiB, MQA={mqa_mem:.0f}GiB")
print(f"Uptraining Mean-Pooled K heads: {pooled_k}")
print(f"GQA Head-0 output: {[round(x, 4) for x in out_direct[0]]}, Head-1 output: {[round(x, 4) for x in out_direct[1]]}")
print("GQA attention, repeat_kv equivalence, and uptraining checks passed")
```

实际执行输出：

```text
70B KV Cache (B=16, S=32K): MHA=1280GiB, GQA-8=160GiB, MQA=20GiB
Uptraining Mean-Pooled K heads: [[2.0, 3.0], [20.0, 30.0]]
GQA Head-0 output: [16.6048, 26.6048], Head-1 output: [23.3952, 33.3952]
GQA attention, repeat_kv equivalence, and uptraining checks passed
```

---

### 5. 工程落地的核心权衡与张量并行（TP）约束

1. **组数 $G$ 与张量并行度（Tensor Parallelism, TP）的整除关系**：
   在多卡张量并行推理中，注意力层是按头（Head Dimension）切分到不同 GPU 上的。
   - 若选择了 **GQA-$G$**，为了避免跨卡通信或重复存储，通常要求 **$G$ 能被 TP 度数整除**（例如 $G=8$ 恰好完美适配单机 8 卡 `TP=8`，每张 GPU 持有 $64/8=8$ 个 Query 头和 $8/8=1$ 个 KV 头）。
   - 如果采用 **MQA（$G=1$）** 跑在 `TP=8` 上，由于只有 1 个 KV 头无法继续切分，工程上必须在全部 8 张卡上**冗余复制（Replicate）同一份 KV Head**，此时单卡上的 KV Cache 占用与 `GQA-8` 在 `TP=8` 下完全一样，MQA 在多卡切分下反而失去了相对 `GQA-8` 的显存优势！这也是为什么 70B 级模型普遍选择 $G=8$ 而非 $G=1$ 的关键工程原因。
2. **为什么 GQA 主要加速 Decode 而对短序列 Prefill 加速不明显？**
   - **Prefill 阶段**是计算受限（Compute-bound）：尽管 GQA 减少了 $W_K, W_V$ 的线性投影计算量，但占大头的 $Q K^\top$ 与 $\text{Attn} \cdot V$ 仍然要对全部 $H$ 个 Query 头执行，总 FLOPs 几乎没有减少。
   - **Decode 阶段**是访存带宽受限（Memory-bandwidth-bound）：算术强度极低，耗时主要花在从 HBM 读取历史 KV Cache 上，因此 GQA 削减 KV Cache 体积能立竿见影地降低每步解码延迟并提升最大并发 Batch Size。

---

## 延伸 / 追问

**追问 1：同一组内的多个 Query 头既然共享完全相同的 Key 和 Value，它们的注意力输出会完全一样吗？**
不会。虽然组内共享同一份 $K_{g(h)}$ 和 $V_{g(h)}$，但每个 Query 头拥有**各自独立的投影矩阵 $W_Q^{(h)}$** 和不同的旋转位置编码作用结果，因此生成的查询向量 $Q_h$ 互不相同（如上文代码中 Head-0 与 Head-1 共享 KV Head 0，但因 $Q_0 \neq Q_1$，最终得到的注意力分布和输出向量完全不同）。不同 Query 头依然可以从同一份上下文表征中检索不同的语义侧面。

**追问 2：既然 GQA 减少了 $W_K$ 和 $W_V$ 的参数量，模型总参数量会大幅缩水吗？**
为了保持对比公平或维持模型容量，主流架构（如 LLaMA-2 70B）在把 MHA 改为 GQA 省下 $W_K, W_V$ 参数的同时，会**按比例调大前馈网络（FFN / SwiGLU）的中间层维度**（例如将 `intermediate_size` 扩大），把省下来的参数量补回到计算密集度更高的 MLP 层中，从而在总参数量不变的前提下进一步增强模型表达能力。

**追问 3：GQA 与 DeepSeek-V2/V3 提出的 MLA（Multi-head Latent Attention）在压缩 KV Cache 的思路上有何本质不同？**
- **GQA** 是**硬性的头间共享（Head-wise Sharing）**：直接砍掉独立的 KV 头数量，所有组内头強制看完全相同的低维物理向量。
- **MLA** 是**低秩潜在向量联合压缩（Low-rank Joint Compression）**：将所有头的 Key 和 Value 联合投影到一个低维潜在向量 $c_t^{KV}$ 中进行缓存（推理时仅存压缩后的潜变量与解耦的 RoPE key），在矩阵乘法时可将解压矩阵吸收到 $W_Q$ 和 $W_O$ 中，从而在比 GQA 缓存更小的前提下，保留每个注意力头各自独立的等效 Key/Value 特征。

---

## 常见误区

- **误区一：“PyTorch 代码里调用了 `repeat_kv` 把 KV 扩展成了 $H$ 个头，所以 GQA 实际上根本没省显存。”**
  事实：**KV Cache 持久化存储发生在 `repeat_kv` 之前**！缓存张量在解码步之间一直以 $(B, G, S, d_{\text{head}})$ 的紧凑形状常驻显存。即便使用朴素 `repeat_kv`，也只是在单层前向计算瞬间产生临时视图/张量，算完该层即释放；而在 FlashAttention / PagedAttention 等生产内核中，连这步临时展开都无需落盘 HBM。
- **误区二：“GQA 可以把长序列 Attention 的计算复杂度从 $O(S^2)$ 降到 $O(S)$。”**
  事实：GQA 没有改变自注意力机制对序列长度 $S$ 的二次方复杂度（Prefill 依然是 $O(H \cdot S^2 \cdot d_{\text{head}})$，Decode 每步依然是 $O(H \cdot S \cdot d_{\text{head}})$）。它降低的是 KV 存储与 HBM 内存读取带宽的常数因子 $G/H$。
- **误区三：“把预训练好的 MHA 模型转成 GQA，只需要直接挑每组的第 1 个 KV 头留下、其余丢弃即可上线使用。”**
  事实：直接丢弃头或仅做 Mean Pooling 而不经过继续训练，模型困惑度（PPL）会立即崩塌；必须配合小比例（约 5% 原始算力）的 Uptraining 让参数重新对齐分布。

---

## 参考

- 选题线索：[RiddleGo/agent-interview-300, 01-LLM基础/18-GQA-MQA.md](https://github.com/RiddleGo/agent-interview-300/blob/e29d19298e86f4a779064883e23b1a72bf6687fb/01-LLM%E5%9F%BA%E7%A1%80/18-GQA-MQA.md)。固定 commit，独立重构拓展。
- Ainslie et al., [GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints](https://arxiv.org/html/2305.13245v3)，EMNLP 2023，§2.1–§3.3：Uptraining 均值池化转换方案、5% 预训练恢复比例与 GQA-$G$ 分组消融实验。
- Shazeer, [Fast Transformer Decoding: One Write-Head is All You Need](https://arxiv.org/abs/1911.02150)，2019：Multi-Query Attention (MQA) 原始论文与自回归解码带宽瓶颈分析。
- Hugging Face Transformers 源码，[src/transformers/models/llama/modeling_llama.py](https://github.com/huggingface/transformers/blob/v4.57.1/src/transformers/models/llama/modeling_llama.py#L159-L169)：固定版本 tag `v4.57.1` 的 `repeat_kv` 组内广播对齐实现。

来源访问与示例核验日期：**2026-10-17**。仅执行标准库代数与数值仿真验证，未运行 GPU 吞吐基准测试。
