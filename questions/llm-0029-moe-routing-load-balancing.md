---
id: llm-0029
title: MoE（混合专家模型）是如何通过 Top-K 路由与负载均衡机制避免路由坍塌（Routing Collapse）的？
category: llm
tags: [moe, mixture-of-experts, load-balancing, auxiliary-loss, loss-free-balancing, expert-routing]
difficulty: medium
role: engineer
contributor: 佚名
source: 公开 AI 系统设计指南与面试整理扩展改编；Switch Transformer、DeepSeek 无辅助损失负载均衡论文与 Transformers 源码核实（见参考）
status: published
updated: 2026-10-23
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-10-23
    updated: 2026-10-23
---

## 问题

在现代前沿大语言模型（如 Mixtral 8x7B、DeepSeek-V2/V3、Qwen2.5-MoE 等）中，稀疏混合专家架构（Sparse Mixture-of-Experts, MoE）通过将标准 Transformer 的稠密前馈网络（FFN）替换为多个并行的专家子网络（Experts）与门控路由器（Router），实现了“总参数量大幅扩展而单 Token 激活计算量（FLOPs）保持恒定”。

然而，在训练 MoE 模型时，如果仅凭门控网络自由路由，极易发生**路由坍塌（Routing Collapse）**与严重的设备间负载失衡。请深入剖析：
1. MoE 层的 Top-$K$ 稀疏门控前向公式是怎样的？为什么不加约束的训练会不可避免地走向“赢家通吃”的路由坍塌？
2. 经典方案（如 GShard、Switch Transformer、Mixtral）是如何通过**负载均衡辅助损失（Auxiliary Load Balancing Loss）**约束专家负载的？为什么其中的离散比例项 $f_i$ 不能单独求导，必须与连续概率项 $P_i$ 相乘？
3. 为什么过强的辅助损失会损害语言模型主任务性能？DeepSeek 提出的**无辅助损失负载均衡（Auxiliary-Loss-Free Load Balancing）**是如何通过动态专家偏置 $b_i$ 消除干扰梯度，同时避免 Expert Choice 路由的未来信息泄漏（Future Token Leakage）的？

本题由公开 AI 系统设计指南与面试整理扩展改编，不是已核实的企业真题；不采信脱离具体拓扑与通信带宽的训练加速比绝对数值承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-10-23

**MoE 的核心挑战在于离散的 Top-$K$ 路由具有正反馈马太效应：早期偶然获得较大梯度的专家会更快降低主任务损失，进而吸引门控网络分配更高权重，最终导致少数专家过载、多数专家“饿死”。工业界主要通过两代机制解决该问题：第一代以 Switch Transformer 和 Mixtral 为代表，在损失函数中加入 $\mathcal{L}_{\text{aux}} = \alpha N \sum_{i=1}^N f_i P_i$（用连续可导的平均门控概率 $P_i$ 乘以离散的实际分配比例 $f_i$ 提供梯度信号）；第二代以 DeepSeek-V3 为代表，采用无辅助损失策略（Loss-Free Balancing），仅在选 Top-$K$ 集合时叠加动态更新的专家偏置 $s_{i,t} + b_i$，而在加权求和时保持原始门控分 $s_{i,t}$，从而在不引入任何干扰梯度的前提下实现精准负载均衡。**

现有 [llm-0016](llm-0016-quantization-local-memory-budget.md) 解释了部署 MoE 模型时为何全部专家权重都必须驻留显存而不能只按激活参数算预算，[llm-0010](llm-0010-causal-attention-architecture.md) 介绍了因果自注意力与未来 Token 掩码约束。本题聚焦 **MoE 稀疏路由数学原理、辅助损失梯度构造、无辅助损失偏置更新算法及专家容量（Expert Capacity）工程权衡**。

---

### 1. MoE Top-$K$ 稀疏路由公式与“路由坍塌”的成因

在 $N$ 个专家的 MoE 层中，设第 $t$ 个 Token 进入 FFN 前的隐状态为 $\mathbf{u}_t \in \mathbb{R}^d$，第 $i$ 个专家的门控质心向量为 $\mathbf{e}_i \in \mathbb{R}^d$。路由器首先计算每个专家的亲和度得分（Affinity Score）：
$$s_{i,t} = G(\mathbf{u}_t^\top \mathbf{e}_i)$$
其中非线性门控函数 $G(\cdot)$ 通常取 $\operatorname{Softmax}$（如 Switch Transformer、Mixtral）或 $\operatorname{Sigmoid}$（如 DeepSeek-V3）。随后，系统仅为当前 Token 激活得分最高的 $K$ 个专家（$K \ll N$，例如 $N=8, K=2$）：
$$g_{i,t} = \begin{cases} s_{i,t}, & \text{if } s_{i,t} \in \operatorname{TopK}(\{s_{j,t}\}_{j=1}^N, K) \\ 0, & \text{otherwise} \end{cases}$$
*(注：部分实现会对选出的 $K$ 个 $g_{i,t}$ 再次做归一化使 $\sum_i g_{i,t} = 1$)*。MoE 层的输出为：
$$\mathbf{h}_t = \mathbf{u}_t + \sum_{i=1}^N g_{i,t} \operatorname{FFN}_i(\mathbf{u}_t)$$

#### 为什么不加干预会发生路由坍塌（Routing Collapse）？
1. **Top-$K$ 截断导致未选中专家零梯度**：
   对于任意未被选入 $\operatorname{TopK}$ 的专家 $j$，其门控权重 $g_{j,t} = 0$。在反向传播时，$\frac{\partial \mathcal{L}_{\text{LM}}}{\partial \theta_{\text{FFN}_j}} = 0$。这意味着未选中的专家不仅没有学到新知识，其参数还停留在随机初始化状态。
2. **正反馈马太效应（Rich-get-Richer）**：
   训练初期，偶然被选中的少数专家（如 Expert 1）得到了充分梯度更新，其输出特征对降低语言模型交叉熵损失 $\mathcal{L}_{\text{LM}}$ 更有帮助。门控网络为了最小化 $\mathcal{L}_{\text{LM}}$，会进一步提高 $\mathbf{e}_1$ 的路由得分 $s_{1,t}$。如此循环数千步后，几乎 $100\%$ 的 Token 都会涌向这 $K$ 个专家，其余 $N-K$ 个专家永久“死亡”，MoE 退化为参数量缩水 $N/K$ 倍的普通稠密模型。
3. **分布式专家并行（Expert Parallelism, EP）木桶效应**：
   在多卡分布式训练/推理中，不同专家通常放置在不同 GPU 上。如果某张 GPU 上的专家接收了 $80\%$ 的 Token，而其他 GPU 闲置等待 All-to-All 通信同步，整个集群的吞吐将被最慢的那张过载卡彻底拖垮。

---

### 2. 经典方案：负载均衡辅助损失（Auxiliary Load Balancing Loss）

为了打破马太效应，Switch Transformer（Fedus et al., 2022）与 Mixtral（Hugging Face `modeling_mixtral.py` 的 `load_balancing_loss_func`）定义了批次级辅助损失。

设一个训练批次共包含 $T$ 个有效 Token，定义两个长度为 $N$ 的专家统计量：
1. **实际接收 Token 比例 $f_i$（离散统计量，不可导）**：
   $$f_i = \frac{1}{K \cdot T} \sum_{t=1}^{T} \mathbb{I}\left(\text{Token } t \text{ 选中了专家 } i\right)$$
   *(注：按此定义，每个 Token 选 $K$ 个专家，因此 $\sum_{i=1}^N f_i = 1$；在完美均匀分布下，每个专家的 $f_i = \frac{1}{N}$。原论文中也常写作乘上 $N$ 后的归一化形式 $\tilde{f}_i = N \cdot f_i$，此时均匀分布下 $\tilde{f}_i = 1$)*。
2. **平均门控路由概率 $P_i$（连续函数，可对路由器参数求导）**：
   $$P_i = \frac{1}{T} \sum_{t=1}^{T} s_{i,t}$$

负载均衡辅助损失定义为两者的点积并乘以专家总数 $N$ 与超参数系数 $\alpha$（通常取 $\alpha \in [10^{-3}, 10^{-2}]$）：
$$\mathcal{L}_{\text{aux}} = \alpha \cdot N \sum_{i=1}^{N} f_i \cdot P_i$$

#### 核心考点：为什么要设计成 $f_i \cdot P_i$ 的乘积形式？
- **为什么不能直接最小化 $\sum f_i^2$？**
  因为 $f_i$ 由阶跃指示函数 $\mathbb{I}(\cdot)$（依赖 `argmax` / `topk`）计算得出，对路由器权重 $\mathbf{e}_i$ 的导数处处为 $0$（或无定义），反向传播根本无法更新路由器。
- **为什么乘上 $P_i$ 就能工作，且在均匀分布时取得全局最小值？**
  在反向传播时，$f_i$ 被视为常数系数（Stop-gradient），梯度通过连续的 $P_i$ 流向门控网络：
  $$\frac{\partial \mathcal{L}_{\text{aux}}}{\partial s_{i,t}} = \frac{\alpha N}{T} f_i$$
  直观来看，**哪个专家当前实际分到的 Token 比例 $f_i$ 越大，它受到的正向惩罚梯度就越强**，优化器在执行梯度下降时就会更猛烈地压低该专家的门控概率 $s_{i,t}$！当所有专家负载均衡且门控概率均匀（即 $\forall i, f_i = \frac{1}{N}, P_i = \frac{1}{N}$）时，$N \sum_{i=1}^N \left(\frac{1}{N} \cdot \frac{1}{N}\right) = 1$ 达到理想均衡状态。

---

### 3. 前沿演进：无辅助损失负载均衡（Auxiliary-Loss-Free Load Balancing）

#### 传统辅助损失的“两难困境（Dilemma）”
在总损失 $\mathcal{L}_{\text{total}} = \mathcal{L}_{\text{LM}} + \mathcal{L}_{\text{aux}}$ 中，$\nabla \mathcal{L}_{\text{aux}}$ 本质上是一个**与语言建模主目标冲突的干扰梯度（Interference Gradient）**。如果某段代码语料天然就需要全部路由给“擅长写代码的专家”，强行拉平本批次分布的 $\nabla \mathcal{L}_{\text{aux}}$ 会强迫路由器把代码 Token 分给“擅长古诗的专家”。因此：
- $\alpha$ 设得太小 $\to$ 负载均衡失效，出现路由坍塌；
- $\alpha$ 设得太大 $\to$ 干扰梯度掩盖主任务梯度，模型困惑度（PPL）与下游能力显著退化。

#### DeepSeek 的 Loss-Free Balancing 机制（Wang et al., 2024）
为了彻底消除干扰梯度，DeepSeek 引入了一组**不参与梯度反向传播**的专家偏置向量 $\mathbf{b} = \{b_1, b_2, \dots, b_N\}$（初始化为 $0$）：

1. **偏置仅用于决定 Top-$K$ 集合，不掺入前向输出加权**：
   $$g_{i,t} = \begin{cases} s_{i,t}, & \text{if } (s_{i,t} + b_i) \in \operatorname{TopK}\left(\{s_{j,t} + b_j\}_{j=1}^N, K\right) \\ 0, & \text{otherwise} \end{cases}$$
   注意这里的精妙设计：判断谁进前 $K$ 名时看的是**偏置后得分 $s_{i,t} + b_i$**；但一旦选出前 $K$ 名，乘在专家输出 $\operatorname{FFN}_i(\mathbf{u}_t)$ 前面的权重依然是**纯粹的原始门控分 $s_{i,t}$**！因此门控网络接收到的梯度 $100\%$ 来自语言建模损失 $\mathcal{L}_{\text{LM}}$，没有任何辅助损失干扰。
2. **基于历史批次负载误差的符号反馈更新（Algorithm 1）**：
   在每个训练 Step 结束后，统计各专家实际分配到的 Token 数 $c_i$ 及所有专家的平均负载 $\bar{c} = \frac{K \cdot T}{N}$。计算负载偏差 $e_i = \bar{c} - c_i$，并以步长 $u$（如 $u = 0.001$）直接更新偏置：
   $$b_i \leftarrow b_i + u \cdot \operatorname{sign}(\bar{c} - c_i)$$
   - 若专家 $i$ 过载（$c_i > \bar{c}$），则 $e_i < 0$，$b_i$ 减小 $u$，下一批更难进入 Top-$K$；
   - 若专家 $i$ 欠载（$c_i < \bar{c}$），则 $e_i > 0$，$b_i$ 增加 $u$，下一批更容易被选中。

#### 三种主流负载均衡方案的全方位对比

| 负载均衡机制 | 代表模型 / 论文 | 专家负载均衡度 | 是否产生干扰梯度 | 是否泄漏未来 Token 信息 |
| --- | --- | --- | --- | --- |
| **辅助损失控制 (Auxiliary Loss)** | Switch Transformer, Mixtral | 取决于 $\alpha$ 强弱 | **有**（大 $\alpha$ 损害模型能力） | 无泄漏（Causal 安全） |
| **专家选择路由 (Expert Choice, EC)** | Zhou et al. (NeurIPS 2022) | 绝对完美均衡（定额挑选） | 无 | **严重泄漏**（破坏自回归因果律） |
| **无辅助损失偏置 (Loss-Free Balancing)** | DeepSeek-V3 (Wang et al., 2024) | 极高（动态闭环调节） | **无**（零辅助损失梯度） | 无泄漏（仅用历史批次更新 $b_i$） |

---

### 4. 可运行的标准库实现：路由坍塌、辅助损失与无损偏置负载均衡仿真

以下 Python 3 标准库代码对比了（1）无均衡约束下的严重负载倾斜、（2）Switch/Mixtral 辅助损失 `load_balancing_loss_func` 的精确计算、以及（3）DeepSeek 无辅助损失偏置更新算法如何在保持原始门控输出权重不变的同时将专家负载迅速拉平：

```python
import math
from typing import List, Tuple


def softmax(logits: List[float]) -> List[float]:
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    s = sum(exps)
    return [x / s for x in exps]


def topk_indices(scores: List[float], k: int) -> List[int]:
    return [idx for idx, _ in sorted(enumerate(scores), key=lambda x: (-x[1], x[0]))[:k]]


def compute_switch_aux_loss(
    gate_probs_batch: List[List[float]], top_k: int, alpha: float = 0.01
) -> Tuple[float, List[float], List[float]]:
    """对标 Hugging Face modeling_mixtral.py 的 load_balancing_loss_func"""
    num_tokens = len(gate_probs_batch)
    num_experts = len(gate_probs_batch[0])
    counts = [0] * num_experts
    prob_sums = [0.0] * num_experts

    for probs in gate_probs_batch:
        selected = topk_indices(probs, top_k)
        for idx in selected:
            counts[idx] += 1
        for i, p in enumerate(probs):
            prob_sums[i] += p

    # f_i: 每个专家在全批次 (num_tokens * top_k) 次选择中占的比例，总和为 1.0
    f = [c / (num_tokens * top_k) for c in counts]
    # P_i: 每个专家在全批次上的平均路由概率，总和为 1.0
    P = [ps / num_tokens for ps in prob_sums]

    # L_aux = alpha * N * sum(f_i * P_i)
    raw_dot = sum(f[i] * P[i] for i in range(num_experts))
    aux_loss = alpha * num_experts * raw_dot
    return aux_loss, f, P


def simulate_loss_free_balancing(
    raw_scores_batch: List[List[float]], top_k: int, steps: int = 40, update_rate: float = 0.005
) -> Tuple[List[int], List[int], List[float]]:
    """对标 DeepSeek Auxiliary-Loss-Free Load Balancing (Algorithm 1)"""
    num_tokens = len(raw_scores_batch)
    num_experts = len(raw_scores_batch[0])
    biases = [0.0] * num_experts
    avg_load = (num_tokens * top_k) / num_experts

    initial_counts: List[int] = []
    final_counts: List[int] = []

    for step in range(steps):
        counts = [0] * num_experts
        for scores in raw_scores_batch:
            # 路由选择使用带偏置分数: s_{i,t} + b_i
            biased_scores = [scores[i] + biases[i] for i in range(num_experts)]
            selected = topk_indices(biased_scores, top_k)
            for idx in selected:
                counts[idx] += 1
            # 关键验证: 实际加权专家输出的门控权重仍取自原始 scores[idx]，不加 biases[idx]
            active_weights = [scores[idx] for idx in selected]
            assert all(w == scores[idx] for w, idx in zip(active_weights, selected))

        if step == 0:
            initial_counts = list(counts)
        if step == steps - 1:
            final_counts = list(counts)

        # 按历史批次负载误差更新偏置: b_i <- b_i + u * sign(avg_load - c_i)
        for i in range(num_experts):
            err = avg_load - counts[i]
            sign = 1.0 if err > 0 else (-1.0 if err < 0 else 0.0)
            biases[i] = round(biases[i] + update_rate * sign, 6)

    return initial_counts, final_counts, biases


# 构造 16 个 Token 在 4 个专家上的傾斜门控分布 (Expert 0 明显占优，模拟路由坍塌前兆)
skewed_logits = [
    [1.8 - 0.1 * (t % 5), 0.9 - 0.08 * (t % 4), 0.3 + 0.09 * (t % 6), 0.1 + 0.11 * (t % 7)]
    for t in range(16)
]
skewed_probs = [softmax(l) for l in skewed_logits]

# 1. 计算倾斜状态 vs 理想均匀状态下的 Switch/Mixtral 辅助损失 (N=4, K=2, alpha=0.01)
skew_loss, skew_f, _ = compute_switch_aux_loss(skewed_probs, top_k=2, alpha=0.01)
uniform_probs = [[0.25, 0.25, 0.25, 0.25] for _ in range(16)]
# 均匀路由时手动构造轮转选择使每个专家恰好分到 8 次 (f_i = 0.25)
uniform_dot = 4 * sum(0.25 * 0.25 for _ in range(4)) * 0.01
assert skew_loss > uniform_dot, "Skewed routing must incur higher auxiliary loss than uniform!"

# 2. 运行 DeepSeek 无辅助损失偏置均衡 (N=4, K=2, 总分配次数=32, 理想平均负载=8)
init_c, final_c, learned_b = simulate_loss_free_balancing(
    skewed_probs, top_k=2, steps=40, update_rate=0.005
)

init_max_vio = (max(init_c) - 8.0) / 8.0
final_max_vio = (max(final_c) - 8.0) / 8.0
assert final_max_vio < init_max_vio and final_max_vio <= 0.125

print(f"Skewed Aux Loss: {skew_loss:.6f} vs Uniform Minimum: {uniform_dot:.6f}")
print(f"Initial token counts per expert (step 0): {init_c} (MaxVio={init_max_vio:.2f})")
print(f"Balanced token counts per expert (step 39): {final_c} (MaxVio={final_max_vio:.2f})")
print(f"Learned expert biases b_i: {learned_b}")
print("MoE auxiliary loss and auxiliary-loss-free balancing checks passed")
```

实际执行输出：

```text
Skewed Aux Loss: 0.013740 vs Uniform Minimum: 0.010000
Initial token counts per expert (step 0): [16, 14, 1, 1] (MaxVio=1.00)
Balanced token counts per expert (step 39): [8, 9, 7, 8] (MaxVio=0.12)
Learned expert biases b_i: [-0.175, 0.08, 0.135, 0.16]
MoE auxiliary loss and auxiliary-loss-free balancing checks passed
```

---

## 延伸 / 追问

**追问 1：为什么说“专家选择路由（Expert Choice, EC）”在自回归语言模型中会导致未来 Token 信息泄漏（Future Token Leakage）？**
- **Token-Choice（常规路由）**：每个 Token 独立在 $N$ 个专家里选 Top-$K$，第 $t$ 个 Token 去哪个专家只取决于 $\mathbf{u}_t$，严格遵守因果掩码（Causal Mask）。
- **Expert-Choice（Zhou et al., 2022）**：反过来让每个专家在当前句子的全部 $T$ 个 Token 中挑选得分最高的 $C$ 个 Token。虽然这能保证每个专家负载绝对等于 $C$，但第 $t$ 个 Token 能否被专家 $i$ 选中，取决于同一句话里排在它后面的未来 Token $t' > t$ 的得分高低！这打破了自回归生成的因果独立性（训练时能看到整句未来 Token 分布，推理逐字解码时却看不到），在 DeepSeek 论文附录 D 中被证明会造成严重的信息泄漏与推理退化。

**追问 2：什么是专家容量因子（Capacity Factor, CF）与 Token Dropping？为什么训练或编译静态图时需要它？**
在使用 XLA/TPU 或静态张量形状的分布式专家并行（EP）中，All-to-All 通信缓冲区必须在运行前确定静态形状。系统将每个专家单批次最多能处理的 Token 上限定为：
$$\text{Capacity} = \left\lceil \frac{T \cdot K}{N} \times \text{CF} \right\rceil$$
其中 $\text{CF} \ge 1.0$（常取 $1.25$）。如果某个专家实际被路由了超过 $\text{Capacity}$ 的 Token，多出来的溢出 Token 将被直接跳过 FFN 计算（仅通过残差连接 $\mathbf{h}_t = \mathbf{u}_t$ 透传到下一层），称为 **Token Dropping**。而在动态形状引擎（如 Megatron-LM Dropless MoE / vLLM）结合良好负载均衡时，可以做到不丢弃任何 Token（Dropless）。

**追问 3：除了辅助损失和偏置外，什么是 Router Z-Loss？它解决什么问题？**
ST-MoE（Zoph et al., 2022）发现门控网络的原始 Logits $z_{i,t} = \mathbf{u}_t^\top \mathbf{e}_i$ 在混合精度（BF16/FP16）训练中容易数值爆炸，导致 Softmax 指数溢出与训练崩溃。为此引入了 **Router Z-Loss**：
$$\mathcal{L}_z = \frac{1}{T} \sum_{t=1}^T \left( \log \sum_{i=1}^N \exp(z_{i,t}) \right)^2$$
它直接惩罚门控 Logits 的对数配分函数（Log-partition function）模长，在不改变专家相对排序的前提下把 Logits 幅度稳定在接近 $0$ 的安全区间，提升训练数值稳定性。

---

## 常见误区

- **误区一：“辅助损失 $\mathcal{L}_{\text{aux}} = \alpha N \sum f_i P_i$ 中的 $f_i$ 和 $P_i$ 是一回事，写两个只是为了平方惩罚。”**
  事实：$f_i$ 是经过离散 Top-$K$ 截断后的**真实硬分配比例**（不可导），而 $P_i$ 是未经截断的**平滑门控概率均值**（可导）。如果只写 $\sum P_i^2$，路由器可能会让所有专家的平均概率看起来接近，但在单个 Token 上依然产生极端偏置；只有用真实硬负载 $f_i$ 给可导概率 $P_i$ 加权，才能精确惩罚实际过载的专家。
- **误区二：“DeepSeek 的无辅助损失偏置 $b_i$ 既然加到了门控分上，也会改变专家输出的加权比例。”**
  事实：根据原论文公式 (3)，$b_i$ **只参与 `TopK` 集合的筛选比较**（决定哪些专家被激活）；一旦选出专家，乘在 $\operatorname{FFN}_i(\mathbf{u}_t)$ 上的门控系数仍然是未加偏置的原始得分 $s_{i,t}$。如果把 $b_i$ 也加进前向输出权重，就会破坏模型学习到的专家融合比例。
- **误区三：“训练好之后到了线上推理阶段，依然需要实时统计每个请求的负载去动态更新 $b_i$。”**
  事实：在推理阶段，模型参数与训练收敛后的偏置向量 $\mathbf{b}$ 通常是固定冻结的（或仅在离线根据目标域批量分布做静态微调），单次在线请求推理不会动态修改 $b_i$，从而保证自回归解码的确定性与并发一致性。

---

## 参考

- 选题线索：[ombharatiya/ai-system-design-guide, 01-foundations/01-llm-internals.md](https://github.com/ombharatiya/ai-system-design-guide/blob/ed955b27d94201b663a741284767a1136dc83e5e/01-foundations/01-llm-internals.md)。固定 commit，独立拓展改编。
- Fedus et al., [Switch Transformers: Scaling to Trillion Parameter Models with Simple and Efficient Sparsity](https://arxiv.org/abs/2101.03961)，JMLR 2022，Eq. 4–6：负载均衡辅助损失 $f_i \cdot P_i$ 与专家容量因子（Capacity Factor）。
- Wang et al., [Auxiliary-Loss-Free Load Balancing Strategy for Mixture-of-Experts](https://arxiv.org/html/2408.15664v1)，2024，§2–§3 & Algorithm 1：辅助损失与主任务梯度的冲突分析、动态专家偏置更新算法及 Expert Choice 未来信息泄漏证明。
- Hugging Face Transformers, [models/mixtral/modeling_mixtral.py (`v4.57.1`)](https://github.com/huggingface/transformers/blob/v4.57.1/src/transformers/models/mixtral/modeling_mixtral.py)：`load_balancing_loss_func` 官方源码实现。

来源访问与示例核验日期：**2026-10-23**。仅执行标准库路由分布与负载均衡算法数值验证，未运行多卡分布式 MoE 训练基准测试。
