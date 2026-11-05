---
id: llm-0033
title: 超长上下文序列并行（Sequence Parallelism）中，Ring Attention 与 DeepSpeed-Ulysses 是如何切分注意力计算的，为什么需要 Zigzag 负载均衡与 2D 混合并行（USP）？
category: llm
tags: [sequence-parallelism, ring-attention, deepspeed-ulysses, context-parallelism, flash-attention, long-context]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开 AI 系统设计指南与面试题库扩展改编；Ring Attention、Striped/Zigzag Attention、DeepSpeed-Ulysses、USP 原论文及官方源码核实（见参考）
status: published
updated: 2026-11-05
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-11-05
    updated: 2026-11-05
---

## 问题

当大语言模型（LLM）的训练或预填充（Prefill）上下文长度从 $8\text{K}$ 扩展到 $128\text{K} \sim 1\text{M}$ Token 时，即便使用 FlashAttention 消除了 $O(L^2)$ 的显存占用，单卡仍会被随序列长度 $L$ 线性增长的激活值（Activations）和 KV 状态撑爆；同时，传统的张量并行（Tensor Parallelism, TP）受限于注意力头数与高频 All-Reduce 通信，无法独立横向扩展到数十张 GPU。为此，工业界引入了专门沿序列维度 $L$ 切分的**序列并行 / 上下文并行（Sequence Parallelism / Context Parallelism）**，其中以 **Ring Attention** 和 **DeepSpeed-Ulysses** 最具代表性。

请深入剖析以下三个核心问题：
1. **Ring Attention** 与 **DeepSpeed-Ulysses** 分别在哪个维度上切分注意力计算？Ring Attention 是如何利用环状点对点（P2P）通信与在线对数配分函数（Log-Sum-Exp, LSE）递推实现精确全局 Softmax 的？
2. 在自回归因果掩码（Causal Mask）下，为什么朴素连续分块的 Ring Attention 会出现严重的**计算空泡与负载失衡**（部分 GPU 算力利用率不足一半）？**Zigzag Ring Attention**（对称折返分块）与 **Striped Attention** 是如何将各卡计算量严格拉平的？
3. DeepSpeed-Ulysses 为什么会受到 **GQA/MQA 注意力头数上限** 的硬约束？在跨多机多卡（节点内高带宽 NVLink + 节点间低带宽 RoCE/IB）集群上，**USP（Unified Sequence Parallelism）2D 混合序列并行**是如何结合两者优势突破通信与头数瓶颈的？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-11-05

**Ring Attention 与 DeepSpeed-Ulysses 代表了超长序列并行的两种正交切分范式：Ring Attention 始终保持序列维度分片（每卡持有 $L/N$ 个 Token 的全部注意力头），通过 $N-1$ 步环状 P2P 传递 $K, V$ 分块，并借由在线 Log-Sum-Exp（LSE）递推精确合并跨卡注意力输出，其并行度不受注意力头数限制，但因果掩码下连续分块会导致高达 $(2N-1):1$ 的各卡负载失衡，必须依赖 Zigzag 对称分块（每卡持有首尾对称的 $b_r$ 与 $b_{2N-1-r}$ 两个子块）消除计算空泡；DeepSpeed-Ulysses 则在注意力前通过 `All-to-All` 集合通信将“序列分片、全头完整”重排为“全序列完整、注意力头分片（每卡 $H/N$ 个头）”，单次通信量比 Ring Attention 低 $4\times$ 以上且天然无因果负载不均，但并行度被 GQA 的 KV 头数 $H_{kv}$ 死死卡住。工程落地上，多机集群普遍采用 USP（2D 混合序列并行）：在节点内 NVLink 高带宽域内跑 Ulysses 切分注意力头，在跨节点 RoCE/IB 网络上跑 Zigzag Ring Attention 切分序列块。**

在展开数学推导与通信账本前，建议结合仓内相关题目建立完整知识坐标系：关于因果注意力掩码、GQA/MQA 头分组结构与 RoPE 位置编码的底层机制，请参阅 [llm-0010](llm-0010-causal-attention-architecture.md)；关于预填充（Prefill）计算受限与解码（Decode）显存带宽受限及 KV Cache 显存公式，请参阅 [llm-0018](llm-0018-kv-cache-prefill-decode.md)；关于分布式训练/推理的显存预算拆解，请参阅 [llm-0016](llm-0016-quantization-local-memory-budget.md)。

---

### 1. Ring Attention 与 DeepSpeed-Ulysses 的切分范式及在线 LSE 递推

设输入序列长度为 $L$，隐藏层维度为 $d = H_q \cdot d_h$（$H_q$ 为 Query 头数，$H_{kv}$ 为 KV 头数，$d_h$ 为单头维度），序列并行组共有 $N$ 张 GPU，每张 GPU 初始均持有长度为 $C = L/N$ 的本地序列分片 $X_r \in \mathbb{R}^{C \times d}$（$r \in \{0, 1, \dots, N-1\}$）。

#### （1）两种切分范式的核心对比

| 对比维度 | Megatron-SP（传统序列并行） | Ring Attention（环状注意力） | DeepSpeed-Ulysses（全对全头切分） | USP（2D 混合序列并行） |
| :--- | :--- | :--- | :--- | :--- |
| **Attention 期间张量切分** | 仅 LayerNorm / Dropout 切序列；Attention 靠 TP 切头，**序列不切分** | **保持序列分片** $(C, H, d_h)$，全部头驻留本地 | `All-to-All` 转置为**全序列、头分片** $(L, H/N, d_h)$ | 2D 网格 $(N_u \times N_r)$：序列长 $L/N_r$，头数 $H/N_u$ |
| **核心通信原语** | `All-Gather` + `Reduce-Scatter` | 环状异步 P2P `Send/Recv` $(K_j, V_j)$ | 前后各 1 次 `All-to-All`（共 2 次，反向 4 次） | 节点内 `All-to-All` + 节点间 P2P Ring |
| **前向单卡通信量（MHA，$H_q=H_{kv}$）** | $2 L d$（随 TP 组广播全序列） | $2 \frac{N-1}{N} L d \approx 2 L d$（传递 $K, V$） | $4 \frac{N-1}{N} \frac{L d}{N} \approx \frac{4 L d}{N}$（随 $N$ 增大反而下降） | 节点间仅 $\frac{2(N_r-1)Ld}{N_r N_u}$，跨机流量锐减 $N_u$ 倍 |
| **最大并行度上限** | $N \le H_{kv}$ | **无头数限制**（仅受最小分块长度 $C$ 限制） | **$N \le H_{kv}$**（超出会迫使 KV 头跨卡冗余复制） | **$N \le H_{kv} \times (L / C_{\min})$**，彻底解耦头数限制 |
| **因果掩码负载均衡** | 天然均衡 | **连续分块严重失衡**，需配合 Zigzag / Striped | 天然均衡（每卡独立算完整序列的 $H/N$ 个头） | 依靠内层 Zigzag Ring 保持严格均衡 |

#### （2）Ring Attention 的在线 Log-Sum-Exp（LSE）无溢出合并公式

在 Ring Attention 中，第 $r$ 张卡固定持有本地 Query 块 $Q_r \in \mathbb{R}^{C \times d_h}$。在 $N$ 个时间步中，各卡一边计算当前持有的 $(K_j, V_j)$ 分块对 $Q_r$ 的局部注意力，一边通过非阻塞 P2P 通信向下一张卡 `(r + 1) % N` 发送当前 $(K_j, V_j)$，并从上一张卡 `(r - 1) % N` 接收下一块。

只要单块计算时间 $T_{\text{comp}}(C^2 d) \ge T_{\text{comm}}(2 C d)$，即分块长度满足：

$$C = \frac{L}{N} \ge \frac{\text{显卡算力 (FLOPS)}}{\text{互联带宽 (Bytes/s)}} \times \text{数据类型字节数}$$

通信耗时会完全隐藏在 FlashAttention 计算背后。

为了在不保存全序列注意力矩阵的前提下精确合并第 $j$ 个分块的局部输出 $\tilde{O}^{(j)} \in \mathbb{R}^{C \times d_h}$ 与局部对数配分函数（Log-Sum-Exp）：

$$l^{(j)} = \operatorname{LSE}\left(\frac{Q_r K_j^\top}{\sqrt{d_h}}\right) = m^{(j)} + \log \sum_{t=1}^{C} \exp\left(S_{r,j}[:, t] - m^{(j)}\right)$$

主干工业实现（如 `zhuzilin/ring-flash-attention`）不分别维护 $(m, \sum \exp)$ 两个状态，而是仅维护累积输出 $O$ 与累积对数配分函数 $l$，利用 Sigmoid 函数 $\sigma(x) = \frac{1}{1 + e^{-x}}$ 与 $\operatorname{logsigmoid}(x) = -\log(1 + e^{-x})$ 执行无指数溢出的增量更新：

$$l_{\text{new}} = \log\left(e^{l} + e^{l^{(j)}}\right) = l - \operatorname{logsigmoid}\left(l - l^{(j)}\right)$$

$$O_{\text{new}} = \frac{e^{l} O + e^{l^{(j)}} \tilde{O}^{(j)}}{e^{l} + e^{l^{(j)}}} = O - \sigma\left(l^{(j)} - l\right) \odot \left(O - \tilde{O}^{(j)}\right)$$

这一递推式在数学上与单卡全序列 Softmax 完全等价（浮点误差在 $10^{-16}$ 量级），且全程只需驻留大小为 $O(C \times d)$ 的状态张量。

---

### 2. 因果掩码下的计算空泡与 Zigzag / Striped 负载均衡

在自回归训练与 Prefill 阶段，注意力矩阵受下三角因果掩码（$p_k \le p_q$）约束，全局有一半的元素被掩码跳过。如果直接按连续区间将序列切分为 $N$ 个块 $b_0, b_1, \dots, b_{N-1}$（Rank $r$ 持有 $b_r$），会导致灾难性的**木桶效应**：

```text
朴素连续分块 (N=4, 每块长度 C=L/4):
           K_b0   K_b1   K_b2   K_b3
Rank 0(b0) [ ◢ ]  [ 0 ]  [ 0 ]  [ 0 ]   --> 仅算 1 个下三角块 (有效工作量 0.5 C^2)
Rank 1(b1) [ █ ]  [ ◢ ]  [ 0 ]  [ 0 ]   --> 算 1 个满块 + 1 个三角块 (1.5 C^2)
Rank 2(b2) [ █ ]  [ █ ]  [ ◢ ]  [ 0 ]   --> 算 2 个满块 + 1 个三角块 (2.5 C^2)
Rank 3(b3) [ █ ]  [ █ ]  [ █ ]  [ ◢ ]   --> 算 3 个满块 + 1 个三角块 (3.5 C^2)
(注: █ 表示无掩码满块计算 C^2, ◢ 表示因果下三角块 C^2/2, 0 表示全掩码空泡)
```

可以看到：
- 在第 $s \in \{1, \dots, N-1\}$ 步环状迭代中，所有满足 $j > r$ 的 $(Q_r, K_j)$ 分块对完全落在上三角掩码区，无需任何计算（计算空泡）。
- Rank $N-1$ 的总有效计算量是 $(N - 0.5) C^2$，而 Rank $0$ 只有 $0.5 C^2$，**最大与最小负载比高达 $(2N-1):1$**！由于每一步环状通信都需要全体 GPU 同步，所有显卡每一轮都必须干等最慢的 Rank $N-1$ 算完，整个集群在 Attention 层的理论最高算力利用率被锁死在 $\frac{N+1}{2N} \approx 50\%$。

#### （1）Zigzag Ring Attention（对称折返分块）

为了彻底消灭空泡，**Zigzag Ring Attention** 将序列均匀切分为 **$2N$ 个子块** $b_0, b_1, \dots, b_{2N-1}$（每个子块长度为 $c = \frac{L}{2N}$），并按**首尾中心对称**规则分配给各张显卡：

$$\text{Rank } r \text{ 持有子块对：}\left(b_r,\; b_{2N - 1 - r}\right), \quad r \in \{0, 1, \dots, N-1\}$$

例如当 $N=4$ 时（共 $8$ 个子块 $b_0 \dots b_7$）：
- Rank 0 持有 $(b_0, b_7)$，Rank 1 持有 $(b_1, b_6)$，Rank 2 持有 $(b_2, b_5)$，Rank 3 持有 $(b_3, b_4)$。

在 $N$ 步环状迭代的第 $s$ 步中，Rank $r$ 接收到来自 Rank $j = (r - s) \bmod N$ 的 KV 子块对 $(K_{j,0}, K_{j,1}) = (b_j, b_{2N-1-j})$，其位置关系严格分为三种对称情形：
1. **当 $s = 0$（即 $j = r$，本地步）**：本地 Query $(b_r, b_{2N-1-r})$ 与本地 KV $(b_r, b_{2N-1-r})$ 的下标完全对齐，直接调用一次因果掩码 FlashAttention（内部包含 $b_r \times b_r$、$b_{2N-1-r} \times b_{2N-1-r}$ 两个三角块，以及 $b_{2N-1-r} \times b_r$ 一个完整块，有效计算面积为 $2 c^2 + c \text{ 项对角线}$）。
2. **当 $1 \le s \le r$（即 $j < r$）**：此时 Rank $r$ 的两个 Query 子块索引满足 $r > j$ 且 $2N - 1 - r > j$，但 $r < 2N - 1 - j$。因此，**全部本地 Query $(b_r, b_{2N-1-r})$ 的位置都严格大于前半个 KV 子块 $b_j$**，而与后半个 KV 子块 $b_{2N-1-j}$ 完全无交集。故让全部本地 Query（长度 $2c$）与 $K_{j,0}$（长度 $c$）做一次**无掩码全注意力（`causal=False`）**，有效计算面积恒为 $2 c^2$。
3. **当 $s > r$（即 $j > r$）**：此时 Rank $r$ 的前半个 Query $b_r$ 位置小于 $(b_j, b_{2N-1-j})$，全被掩码；而**后半个 Query $b_{2N-1-r}$ 的位置严格大于全部两个 KV 子块 $(b_j, b_{2N-1-j})$**（因为 $2N-1-r > 2N-1-j > j$）。故仅取后半个 Query $Q_{r,1}$（长度 $c$）与完整 KV 对（长度 $2c$）做一次**无掩码全注意力（`causal=False`）**，有效计算面积同样恒为 $2 c^2$！

**结论**：在每一步 $s$ 中，**每一张显卡的计算面积都严格相等**（本地步均为 $2c^2$，其余 $N-1$ 个外环步也均为 $2c^2$，且全部走满块 `causal=False` 高效无分支内核），各卡负载比恒为 **$1.00\times$**！

#### （2）Striped Attention 与 Zigzag 的工程取舍
- **Striped Attention（条纹切分）**：将第 $i$ 个 Token 分配给 Rank $(i \bmod N)$（即步长为 $N$ 的交错采样）。虽然也能在统计上拉平因果负载，但在变长序列拼接（Varlen / Sample Packing）场景下会打碎连续内存布局，且当子块粒度为 1 时无法直接利用 FlashAttention 的连续分块访存优势。
- **Zigzag Ring Attention**：每个子块 $b_r$ 内部依然是长度为 $\frac{L}{2N}$ 的连续 Token 区间，只需在 DataLoader 喂入模型前（以及 Position IDs / RoPE 索引处）按 $[b_r, b_{2N-1-r}]$ 重排即可直接复用原版 FlashAttention 内核，因此成为 Megatron-LM Context Parallelism 与 `ring-flash-attention` 的工业界默认方案。

---

### 3. DeepSpeed-Ulysses 的 GQA 头数瓶颈与 USP 2D 混合序列并行

#### （1）为什么 DeepSpeed-Ulysses 受制于 $N \le H_{kv}$？
DeepSpeed-Ulysses 的核心思想是：在进入 FlashAttention 前，对分片的 $Q, K, V \in \mathbb{R}^{(L/N) \times H \times d_h}$ 执行一次跨 $N$ 卡的 `All-to-All` 集合通信，将其重排为 $\mathbb{R}^{L \times (H/N) \times d_h}$；算完本地完整序列的 $H/N$ 个注意力头后，再通过一次 `All-to-All` 还原为 $\mathbb{R}^{(L/N) \times H \times d_h}$。

- **通信优势**：单卡前向只需发送/接收 $Q, K, V, O$ 四个张量，总通信量为 $4 \frac{N-1}{N} \frac{L d}{N} \approx \frac{4 L d}{N}$，比 Ring Attention 的 $2 L d$ 小了整整 **$N/2$ 倍**。
- **GQA/MQA 硬上限**：现代主流大模型普遍采用分组查询注意力（GQA，例如 Llama-3-8B/70B 的 KV 头数仅为 $H_{kv} = 8$，Qwen2.5-7B 甚至只有 $H_{kv} = 4$）。当序列并行度 $N > H_{kv}$（例如用 $N = 64$ 张卡训 $1\text{M}$ 长文本）时，$H_{kv} = 8$ 个 KV 头根本不够分给 $64$ 张卡！此时若强行使用纯 Ulysses，必须在 `All-to-All` 阶段将每个 KV 头冗余复制 $N / H_{kv} = 8$ 份，导致 KV 通信量与显存开销随并行度线性反弹。

#### （2）USP（Unified Sequence Parallelism）2D 混合拓扑
**USP（arXiv:2405.07719，开源库 `feifeibear/long-context-attention` 及 NVIDIA TransformerEngine `AttnFuncWithCPAndKVP2P`）** 将 $N$ 张 GPU 组织为 $N_{\text{ulysses}} \times N_{\text{ring}}$ 的二维正交进程组：

1. **内层（节点内 NVLink 域，规模 $N_u \le H_{kv}$）**：例如单机 8 卡 H100/A800 内部设置 $N_u = 8$，正好匹配 $H_{kv} = 8$，利用高达 $400 \sim 900\text{ GB/s}$ 的 NVLink 全互联带宽执行 `All-to-All` 头切分。此时每张卡只需负责 $H_q / N_u$ 个 Query 头和 $H_{kv} / N_u = 1$ 个 KV 头，序列维度在节点内汇聚为 $L / N_r$。
2. **外层（跨节点 RoCE / InfiniBand 域，规模 $N_r = N / N_u$）**：在跨机网络上组成长度为 $N_r$ 的环，按 **Zigzag Ring Attention** 传递经过内层 Ulysses 切头后的 $K, V$ 子块。由于每张卡在环上传输的 KV 仅包含 $H_{kv} / N_u$ 个头（隐藏维度缩小了 $N_u$ 倍），**跨机 P2P 通信流量直接锐减为纯 Ring Attention 的 $\frac{1}{N_u}$**，轻松被计算完全掩盖！

---

### 4. Python 3 标准库实现：在线 LSE 递推、Zigzag 负载均衡与 USP 通信账本核验

下面的零依赖 Python 3 标准库代码完整复现了：
1. `ring-flash-attention` 的 `sigmoid / logsigmoid` 在线 LSE 增量合并算子；
2. 朴素连续分块 Ring Attention 与 Zigzag Ring Attention 在 $N=4$ 卡因果掩码下的逐卡有效交互对统计及与单卡全序列真值的数值等价性校验；
3. 64 卡集群（$L=128\text{K}, H_{kv}=8$）下纯 Ring Attention 与 USP $(8 \times 8)$ 跨节点通信流量的定量对比。

```python
import math
from typing import Dict, List, Tuple


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def logsigmoid(x: float) -> float:
    # log(1 / (1 + exp(-x))) = -log(1 + exp(-x))
    return -math.log1p(math.exp(-x)) if x >= 0 else x - math.log1p(math.exp(x))


def flash_block_forward(
    q_rows: List[List[float]],
    q_pos: List[int],
    k_rows: List[List[float]],
    k_pos: List[int],
    v_rows: List[List[float]],
    scale: float,
    causal: bool,
) -> Tuple[List[List[float]], List[float], int]:
    """
    计算单个分块 (Q_sub, K_sub, V_sub) 的局部注意力输出 block_out 与对数配分函数 block_lse (log-sum-exp)，
    并统计有效 (未掩码) 的 (q, k) 交互对数量。
    """
    d = len(q_rows[0])
    block_out: List[List[float]] = []
    block_lse: List[float] = []
    valid_pairs = 0

    for qi, p_q in zip(q_rows, q_pos):
        scores: List[float] = []
        valid_vs: List[List[float]] = []
        for kj, vj, p_k in zip(k_rows, v_rows, k_pos):
            if causal and p_k > p_q:
                continue
            valid_pairs += 1
            dot = sum(qi[idx] * kj[idx] for idx in range(d)) * scale
            scores.append(dot)
            valid_vs.append(vj)

        assert len(scores) > 0, "Block invoked with all positions masked"
        m = max(scores)
        exps = [math.exp(s - m) for s in scores]
        denom = sum(exps)
        lse_val = m + math.log(denom)
        out_row = [
            sum(exps[t] * valid_vs[t][idx] for t in range(len(scores))) / denom
            for idx in range(d)
        ]
        block_out.append(out_row)
        block_lse.append(lse_val)

    return block_out, block_lse, valid_pairs


def update_out_and_lse(
    out: List[List[float]],
    lse: List[float],
    block_out: List[List[float]],
    block_lse: List[float],
    row_indices: List[int],
) -> None:
    """
    复现 ring-flash-attention (zhuzilin) 的无溢出增量合并公式:
    out_new = out - sigmoid(block_lse - lse) * (out - block_out)
    lse_new = lse - logsigmoid(lse - block_lse)
    """
    d = len(block_out[0])
    for local_i, target_i in enumerate(row_indices):
        if math.isinf(lse[target_i]):
            out[target_i] = list(block_out[local_i])
            lse[target_i] = block_lse[local_i]
        else:
            w = sigmoid(block_lse[local_i] - lse[target_i])
            out[target_i] = [
                out[target_i][idx] - w * (out[target_i][idx] - block_out[local_i][idx])
                for idx in range(d)
            ]
            lse[target_i] = lse[target_i] - logsigmoid(lse[target_i] - block_lse[local_i])


def simulate_naive_vs_zigzag_ring(
    Q: List[List[float]], K: List[List[float]], V: List[List[float]], num_gpus: int
) -> Dict[str, object]:
    seq_len = len(Q)
    d = len(Q[0])
    scale = 1.0 / math.sqrt(d)
    positions = list(range(seq_len))

    # 1. 单卡全量因果注意力参考真值
    ref_out, ref_lse, total_valid = flash_block_forward(
        Q, positions, K, positions, V, scale, causal=True
    )

    # 2. 朴素连续分块 Ring Attention: Rank r 持有连续块 [r*C : (r+1)*C]
    chunk_size = seq_len // num_gpus
    naive_rank_loads = [0] * num_gpus
    for step in range(num_gpus):
        for r in range(num_gpus):
            kv_r = (r - step) % num_gpus
            if kv_r <= r:  # 仅当 KV 块索引 <= Q 块索引时才存在非空因果交互
                q_pos = positions[r * chunk_size : (r + 1) * chunk_size]
                k_pos = positions[kv_r * chunk_size : (kv_r + 1) * chunk_size]
                _, _, pairs = flash_block_forward(
                    Q[r * chunk_size : (r + 1) * chunk_size],
                    q_pos,
                    K[kv_r * chunk_size : (kv_r + 1) * chunk_size],
                    k_pos,
                    V[kv_r * chunk_size : (kv_r + 1) * chunk_size],
                    scale,
                    causal=(step == 0),
                )
                naive_rank_loads[r] += pairs

    # 3. Zigzag Ring Attention: 切分为 2*N 个子块，Rank r 持有对称块 (b_r, b_{2N-1-r})
    sub_len = seq_len // (2 * num_gpus)
    zigzag_rank_loads = [0] * num_gpus
    zigzag_out = [[0.0] * d for _ in range(seq_len)]

    for r in range(num_gpus):
        idx0 = list(range(r * sub_len, (r + 1) * sub_len))
        idx1 = list(range((2 * num_gpus - 1 - r) * sub_len, (2 * num_gpus - r) * sub_len))
        q_idx = idx0 + idx1
        q_local = [Q[i] for i in q_idx]
        q1_local = [Q[i] for i in idx1]

        out_r = [[0.0] * d for _ in range(len(q_idx))]
        lse_r = [-math.inf] * len(q_idx)

        for step in range(num_gpus):
            kv_r = (r - step) % num_gpus
            kv_idx0 = list(range(kv_r * sub_len, (kv_r + 1) * sub_len))
            kv_idx1 = list(range((2 * num_gpus - 1 - kv_r) * sub_len, (2 * num_gpus - kv_r) * sub_len))
            kv_idx = kv_idx0 + kv_idx1

            if step == 0:
                # 全部 (q0, q1) 对本地 (k0, k1) 做因果注意力
                b_out, b_lse, pairs = flash_block_forward(
                    q_local, q_idx, [K[i] for i in kv_idx], kv_idx, [V[i] for i in kv_idx], scale, causal=True
                )
                update_out_and_lse(out_r, lse_r, b_out, b_lse, list(range(len(q_idx))))
            elif step <= r:
                # kv_r < r: (q0, q1) 的位置均严格大于 k0，故全部 q_local 对 k0 做无掩码全注意力
                b_out, b_lse, pairs = flash_block_forward(
                    q_local, q_idx, [K[i] for i in kv_idx0], kv_idx0, [V[i] for i in kv_idx0], scale, causal=False
                )
                update_out_and_lse(out_r, lse_r, b_out, b_lse, list(range(len(q_idx))))
            else:
                # kv_r > r: 仅后半块 q1 的位置严格大于 (k0, k1)，故仅 q1 对完整 (k0, k1) 做无掩码全注意力
                b_out, b_lse, pairs = flash_block_forward(
                    q1_local, idx1, [K[i] for i in kv_idx], kv_idx, [V[i] for i in kv_idx], scale, causal=False
                )
                update_out_and_lse(out_r, lse_r, b_out, b_lse, list(range(sub_len, 2 * sub_len)))

            zigzag_rank_loads[r] += pairs

        for local_i, global_i in enumerate(q_idx):
            zigzag_out[global_i] = out_r[local_i]

    max_err = max(
        abs(ref_out[i][j] - zigzag_out[i][j])
        for i in range(seq_len)
        for j in range(d)
    )
    return {
        "total_valid": total_valid,
        "naive_loads": naive_rank_loads,
        "zigzag_loads": zigzag_rank_loads,
        "max_err": max_err,
    }


# 构造长度为 L=16、维度 d=4、GPU 数 N=4 的测试序列
Q_test = [[math.sin(i * 0.7 + j * 0.3) for j in range(4)] for i in range(16)]
K_test = [[math.cos(i * 0.5 - j * 0.2) for j in range(4)] for i in range(16)]
V_test = [[(i + 1) * 0.1 + j * 0.05 for j in range(4)] for i in range(16)]

stats = simulate_naive_vs_zigzag_ring(Q_test, K_test, V_test, num_gpus=4)

# 1. 验证朴素连续分块存在严重负载不均，而 Zigzag 各卡负载完全相等!
assert stats["naive_loads"] == [10, 26, 42, 58]
assert stats["zigzag_loads"] == [34, 34, 34, 34]
assert sum(stats["zigzag_loads"]) == stats["total_valid"] == 136
assert stats["max_err"] < 1e-12

# 2. 验证 2D 混合序列并行 (USP) 通信量与 GQA 头数约束:
# 设总卡数 N=64, 序列长 L=131072, d=4096, GQA KV 头数 H_kv=8, bf16 (2 Bytes)
L, d, N, H_kv, b_bytes = 131072, 4096, 64, 8, 2
# 纯 Ulysses 要求 N <= H_kv，在 N=64 > H_kv=8 时不满足免复制切分条件;
# USP 取 N_ulysses=8 (节点内 NVLink) x N_ring=8 (跨节点 RoCE)
N_u, N_r = 8, 8
assert N_u <= H_kv and N_u * N_r == N
pure_ring_comm_mb = 2 * (N - 1) * (L // N) * d * b_bytes / (1024 * 1024)
usp_inter_node_ring_mb = 2 * (N_r - 1) * (L // N) * (d // N_u) * b_bytes / (1024 * 1024)
assert usp_inter_node_ring_mb < pure_ring_comm_mb / 60

print(f"Naive Ring valid (q,k) pairs per GPU:  {stats['naive_loads']} (max/min={58/10:.2f}x)")
print(f"Zigzag Ring valid (q,k) pairs per GPU: {stats['zigzag_loads']} (max/min=1.00x)")
print(f"Zigzag vs Single-GPU Reference max abs error: {stats['max_err']:.2e}")
print(f"Inter-node P2P KV volume per GPU: Pure Ring(N=64)={pure_ring_comm_mb:.1f} MiB vs USP(8x8)={usp_inter_node_ring_mb:.1f} MiB")
print("Ring Attention online LSE merge, Zigzag load balance, and USP checks passed")
```

```text
Naive Ring valid (q,k) pairs per GPU:  [10, 26, 42, 58] (max/min=5.80x)
Zigzag Ring valid (q,k) pairs per GPU: [34, 34, 34, 34] (max/min=1.00x)
Zigzag vs Single-GPU Reference max abs error: 2.22e-16
Inter-node P2P KV volume per GPU: Pure Ring(N=64)=2016.0 MiB vs USP(8x8)=28.0 MiB
Ring Attention online LSE merge, Zigzag load balance, and USP checks passed
```

---

## 延伸 / 追问

**追问 1：在多文档拼接（Sample Packing / Varlen）训练中，一条长序列内部包含多个互不可见的短文档，Zigzag Ring Attention 为什么会再次出现负载失衡？Llama-3 技术报告是如何解决的？**
Zigzag Ring Attention 之所以能在单条长文档上严格拉平负载，是因为假设整条序列是一个完整的 $L \times L$ 下三角掩码。当启用 Sample Packing（`flash_attn_varlen_func`）将多条长短不一的文档拼接成一条 $128\text{K}$ 序列时，注意力掩码变成了**主对角线上若干个大小不一的分块下三角矩阵（Block-Diagonal Causal Mask）**。此时首尾对称位置 $b_r$ 和 $b_{2N-1-r}$ 往往属于完全不同的文档，彼此之间根本没有跨文档注意力交互（全为 0），导致 Zigzag 的负载对称性被破坏。
Llama-3 与工业界解决方案：
1. **按文档粒度动态做 Zigzag 切分（Per-Document Zigzag Sharding）**：不按全局序列一刀切，而是将每一条独立文档各自切分为 $2N$ 个对称子块分发到 $N$ 张卡上（`ring-flash-attention` 中的 `zigzag_ring_flash_attn_varlen_func`），保证每个文档内部在各卡上的三角计算面积依然严格相等。
2. **All-Gather KV Context Parallelism（`llama3_flash_attn_varlen_func`）**：Llama-3 预训练中针对中等规模 CP 组采用了更简洁的策略——每层 Attention 前先按文档掩码需求执行一次异步 `All-Gather` 收集相关 $K, V$，本地直接跑单次 `flash_attn_varlen_func`，反向传播再对 `dK, dV` 执行 `Reduce-Scatter`。这避免了 $N$ 次 Kernel Launch 开销与复杂的 `cu_seqlens` 重映射，在短文档密集拼接时算子效率反而更高。

**追问 2：Ring Attention 的反向传播（Backward Pass）需要额外保存和传输什么张量？为什么反向传播的通信量是前向的 2 倍？**
在前向传播结束时，每张卡本地只保存了本地分片的输入 $Q_r, K_r, V_r$、最终合并后的输出 $O_r \in \mathbb{R}^{C \times d_h}$ 以及**全局对数配分函数 $l_r \in \mathbb{R}^{C \times 1}$**（绝不保存中间各步的注意力矩阵 $P_{r,j}$）。
在反向传播时，为了利用 FlashAttention Backward 重计算局部概率 $P_{r,j} = \exp(Q_r K_j^\top / \sqrt{d_h} - l_r)$ 并求得 $\text{d}Q_r, \text{d}K_j, \text{d}V_j$：
1. 不仅需要像前向一样沿着环传递 $(K_j, V_j)$ 分块，以便每张卡重算 $P_{r,j}$ 并累加本地的 $\text{d}Q_r$；
2. 同时，因为第 $r$ 张卡算出的梯度贡献 $\text{d}K_j^{(r)}, \text{d}V_j^{(r)}$ 属于第 $j$ 张卡的参数路径，还必须在环上**同步传递并累加梯度分块 $(\text{d}K_j, \text{d}V_j)$**。
因此，反向传播每一步环状 P2P 需要同时发送 $(K_j, V_j, \text{d}K_j, \text{d}V_j)$ 四个张量，单步通信量是前向传播（仅发送 $K_j, V_j$）的 **2 倍**。

**追问 3：在启用 Zigzag Ring Attention 时，旋转位置编码（RoPE）和 DataLoader 需要做怎样的特殊配合？**
因为 Zigzag 将原本连续的序列 $[b_0, b_1, \dots, b_{2N-1}]$ 打乱重组，使 Rank $r$ 持有了非连续的 $[b_r, b_{2N-1-r}]$：
1. **无通信本地切片**：绝不能在模型每一层都对激活值做跨卡 Shuffle，而是在 **DataLoader 输入层**直接为 Rank $r$ 切片喂入 `input_ids` 和 `labels` 的 $[b_r, b_{2N-1-r}]$ 部分。
2. **RoPE Position IDs 绑定**：由于 Embedding、MLP 和 RMSNorm 都是逐 Token 独立（Token-wise）运算，Token 顺序不影响结果；但在计算 RoPE（旋转位置编码）时，必须传入与 $[b_r, b_{2N-1-r}]$ 真实全局位置严格对应的 `position_ids`（即 $[r c \dots (r+1)c-1] \cup [(2N-1-r)c \dots (2N-r)c-1]$ 的余弦/正弦表），否则后半块 $b_{2N-1-r}$ 的相对位置距离会错乱。

---

## 常见误区

- **误区一：“Megatron-LM 传统的 Sequence Parallelism（SP）已经能把超长上下文的 Attention 切到多卡上了。”**
  事实：Megatron 早期提出的传统 SP（Korthikanti et al., 2022）**只在 LayerNorm、Dropout 和残差连接处沿序列维度切分激活值**；一进入 Self-Attention 和 MLP 层，它就通过 `All-Gather` 把全长序列拼回来了，Attention 内部依然依赖 Tensor Parallelism（TP）切头。只有 Ring Attention、DeepSpeed-Ulysses 和 Megatron Context Parallelism（CP）才真正把 Attention 内部的序列长度 $L$ 切分到了多卡上。
- **误区二：“Ring Attention 既然没有头数限制，在单机 8 卡 NVLink 内也应该无脑用 Ring Attention 代替 DeepSpeed-Ulysses。”**
  事实：Ring Attention 每层需要拆成 $N$ 次小分块 FlashAttention Kernel Launch，不仅增加了内核启动开销、降低了 GPU Tensor Core 饱和度，而且前向通信量（$\approx 2Ld$）在 $N=8$ 时是 Ulysses（$\approx 4Ld/8 = 0.5Ld$）的 **4 倍**。在 $N \le H_{kv}$ 且具备高带宽全互联（如单机 8 卡 NVLink）时，DeepSpeed-Ulysses 的单次全序列大 Kernel + 低通信量吞吐显著优于纯 Ring Attention。
- **误区三：“只要把序列分成 $N$ 块做 Ring Attention，因果掩码下通过跳过上三角空块就能把总训练时间缩短一半。”**
  事实：跳过上三角空块只能省掉 Rank $0, 1, \dots, N-2$ 的计算，但 **Rank $N-1$ 在每一步都必须实打实计算完整的非空块**（没有任何一块是全掩码）。因为环状通信每一步都是同步栅栏（Barrier），前 $N-1$ 张卡跳过了计算也只能原地空转等待 Rank $N-1$，如果不改用 Zigzag 或 Striped 分块，端到端耗时一秒都不会减少。

---

## 参考

- 选题线索：[Infrasys-AI/AIInfra, 05Infer/04LongInfer/02RingAttention.md](https://github.com/Infrasys-AI/AIInfra/blob/b97c0385ba07a62a717d82a0e7aed2927f12fc35/05Infer/04LongInfer/02RingAttention.md)（固定 commit `b97c0385`）与 [zhuzilin/ring-flash-attention Issue #2](https://github.com/zhuzilin/ring-flash-attention/issues/2) 及官方实现 [zigzag_ring_flash_attn.py](https://github.com/zhuzilin/ring-flash-attention/blob/786677930bce4f6022166899c88ce2c00c814ee2/ring_flash_attn/zigzag_ring_flash_attn.py)（固定 commit `78667793`）。
- Liu et al., [Ring Attention with Blockwise Transformers for Near-Infinite Context](https://arxiv.org/abs/2310.01889)，ICLR 2024：分块环状注意力与通信计算重叠条件。
- Brandon et al., [Striped Attention: Faster Ring Attention for Causal Transformers](https://arxiv.org/abs/2311.09431)，2023：因果掩码下连续分块的负载失衡与交错/对称分块优化。
- Jacobs et al., [DeepSpeed Ulysses: System Optimizations for Enabling Training of Extreme Long Sequence Transformer Models](https://arxiv.org/abs/2309.14509)，2023：基于 All-to-All 的注意力头切分与通信复杂度分析。
- Fang & Zhao, [USP: A Unified Sequence Parallelism Approach for Long Context Generative AI](https://arxiv.org/abs/2405.07719)，2024（开源实现 [feifeibear/long-context-attention](https://github.com/feifeibear/long-context-attention/tree/a5f8f600d435ced180a97c91c68e87ff3cfb8f89) commit `a5f8f600`）：Ulysses + Ring 2D 混合序列并行架构。

来源访问与示例核验日期：**2026-11-05**。仅执行标准库在线 LSE 递推、Zigzag 因果负载均衡与 USP 通信账本数值验证，未运行多机 GPU 集群训练压测。
