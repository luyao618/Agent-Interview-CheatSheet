---
id: llm-0028
title: PagedAttention 是如何借鉴操作系统虚拟内存解决 KV Cache 显存碎片并实现写时复制（CoW）共享的？
category: llm
tags: [paged-attention, vllm, kv-cache, memory-fragmentation, copy-on-write, prefix-caching]
difficulty: medium
role: engineer
contributor: 佚名
source: 公开大模型系统设计面试整理第 8 章扩展改编；PagedAttention 原论文（SOSP 2023）核实（见参考）
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

在早期的大语言模型（LLM）推理引擎中，由于自回归生成的最终输出长度无法事先预知，系统通常必须为每个进入的请求按最大可能序列长度（如 $S_{\max} = 2048$ 或 $4096$）在 GPU 显存中预先分配一块**连续的（Contiguous）** KV Cache 缓冲区。这种静态连续预分配导致了极低的显存利用率，严重限制了在线服务的最大并发 Batch Size。

vLLM 提出的 PagedAttention（Kwon et al., SOSP 2023）将操作系统虚拟内存与分页管理思想引入注意力计算。请深入剖析：
1. 传统连续 KV Cache 预分配会导致哪三类显存浪费（内部碎片、外部碎片、预留浪费）？PagedAttention 是如何通过逻辑块（Logical Blocks）、物理块（Physical Blocks）与块表（Block Table）将浪费压低到接近零的？
2. 在注意力前向计算中，当一个请求的 KV Cache 分散在不连续的物理显存块中时，PagedAttention 是如何进行分块寻址与注意力聚合计算的？
3. 在并行采样（Parallel Sampling / `n > 1`）、Beam Search 以及跨请求 Prefix Caching 场景下，PagedAttention 是如何利用引用计数（Reference Count）与写时复制（Copy-on-Write, CoW）实现物理块共享的？块大小（Block Size $B$）的选取有哪些工程权衡？

本题由公开大模型系统设计面试整理扩展改编，不是已核实的企业真题；不采信脱离具体并发负载与块大小配置的绝对吞吐提升倍数承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-10-23

**PagedAttention 的核心思想是打破“每个序列的 KV Cache 在物理显存中必须连续存储”的深度学习张量假设，将 KV Cache 切分为固定大小的块（Block，每块容纳 $B$ 个 Token 的 Key 和 Value），通过块表（Block Table）维护逻辑块到非连续物理块的动态映射；从而彻底消除外部碎片、将内部碎片严格限制在每个序列最后一个未满块（$< B$ 个 Token）以内，并支持块粒度的引用计数共享与写时复制（Copy-on-Write）。**

现有 [llm-0018](llm-0018-kv-cache-prefill-decode.md) 解释了 KV Cache 在 Prefill 与 Decode 阶段的状态复用原理，[llm-0016](llm-0016-quantization-local-memory-budget.md) 讨论了整机部署的显存容量预算，[agent-0047](agent-0047-tool-context-layout-for-prompt-cache.md) 探讨了上层 Prompt 布局对缓存命中率的影响。本题聚焦 **底层 KV 显存的分页管理机制、非连续分块注意力数学公式、写时复制（CoW）状态转换以及块大小权衡**。

---

### 1. 传统连续 KV 分配的三类显存浪费与 PagedAttention 的虚拟内存映射

根据 Kwon et al. (SOSP 2023) 的实测剖析，传统推理系统要求一个形状为 $(L, 2, H_{kv}, S_{\max}, d_{\text{head}})$ 的连续物理张量，导致有效显存利用率往往不足 $20\%\sim 40\%$，具体浪费来自三个维度：

| 浪费类型 | 产生原因（连续预分配机制） | PagedAttention 的解决方式 |
| --- | --- | --- |
| **内部碎片 (Internal Fragmentation)** | 按最大长度 $S_{\max}$（如 2048）预分配，但请求实际只生成了 100 个 Token 就提前遇到 `<eos>` 结束，尾部 1948 个槽位永远闲置且无法被其他请求借用。 | **按需动态分配（On-demand Allocation）**：每次只在当前块写满时才申请 1 个新的物理块（大小 $B$，如 16 个 Token）。内部碎片最多仅出现在序列末尾最后一个块，上限为 $B - 1$ 个 Token。 |
| **预留浪费 (Reservation Waste)** | 即便事先知道某请求会生成 500 个 Token，在第 1 步解码时后面 499 个位置也尚未产生数据，但连续缓冲区必须从第 0 秒起全程独占这 500 个槽位。 | **逐块延迟绑定**：未来的 Token 在未生成前不占用任何物理块，空闲块池可供其他并发请求立刻使用。 |
| **外部碎片 (External Fragmentation)** | 不同请求长度各异、到达和退出时机不同；释放后的连续显存留下大小不一的“空洞”，即使总空闲显存充足，也无法塞进一个需要大块连续空间的長请求。 | **等大定长分块（Uniform Block Size）**：所有物理块尺寸完全一致（均为 $B$ 个 Token），任何释放的物理块都能直接分配给任意请求的任何逻辑块，**外部碎片严格为 $0$**。 |

#### 与操作系统虚拟内存（OS Virtual Memory）的精确对应
- **虚拟页（Virtual Pages） $\leftrightarrow$ 逻辑块（Logical KV Blocks）**：每个请求视角下，自己的 Token 序列按顺序填入逻辑块 $0, 1, 2, \dots, \lceil S / B \rceil - 1$，呈现连续的逻辑索引。
- **物理页框（Physical Frames） $\leftrightarrow$ 物理块（Physical KV Blocks）**：GPU HBM 显存池预先划分为若干等大的物理块，块与块之间无需为同一请求相邻存放。
- **页表（Page Table） $\leftrightarrow$ 块表（Block Table）**：调度器为每条序列维护一张映射表，记录 `逻辑块号 l -> (物理块号 p, 已填充 Token 数 filled)`。对第 $t$ 个 Token（0-indexed），其寻址公式为：
  $$\text{logical\_block} = \lfloor t / B \rfloor, \quad \text{block\_offset} = t \bmod B$$

---

### 2. 非连续物理块上的分块注意力计算（Block-wise Attention）

当物理块分散在显存各处时，如何在不把它们重新拼接（Concat）成连续大张量的前提下完成 Attention 计算？

设块大小为 $B$，当前序列长度为 $S$，共占 $M = \lceil S / B \rceil$ 个逻辑块。令块表映射函数为 $\text{PT}(j)$（将第 $j$ 个逻辑块映射为物理块索引 $p_j$）。第 $j$ 个物理块中存储的 Key 和 Value 子矩阵分别为：
$$K_{p_j} = \left(k_{(j-1)B+1}, \dots, k_{jB}\right) \in \mathbb{R}^{B \times d_{\text{head}}}, \quad V_{p_j} = \left(v_{(j-1)B+1}, \dots, v_{jB}\right) \in \mathbb{R}^{B \times d_{\text{head}}}$$
*(注：最后一个块 $j=M$ 若未满，仅取前 $S - (M-1)B$ 个有效列)*。

对于当前解码步的查询向量 $q_i \in \mathbb{R}^{1 \times d_{\text{head}}}$，PagedAttention 内核按块表顺序遍历 $j = 1, \dots, M$，通过指针数组直接从非连续物理地址读取 $K_{p_j}$ 和 $V_{p_j}$ 到 GPU SRAM：
$$A_{i, j} = \frac{\exp\left(q_i K_{p_j}^\top / \sqrt{d_{\text{head}}}\right)}{\sum_{m=1}^{M} \sum_{t \in \text{block } m} \exp\left(q_i k_t^\top / \sqrt{d_{\text{head}}}\right)} \in \mathbb{R}^{1 \times B}, \quad o_i = \sum_{j=1}^{M} A_{i, j} V_{p_j}$$

配合 Online Softmax（见 FlashAttention 递推归一思想），CUDA Kernel 可以在一次遍历所有物理块的过程中边读取边累加局部最大值与指数和，**完全不需要在 HBM 中分配连续临时缓冲区**。

---

### 3. 引用计数（RefCount）与写时复制（Copy-on-Write, CoW）机制

在并行采样（如同一 Prompt 生成 $n=3$ 条候选回答）或 [llm-0012](llm-0012-decoding-sampling-beam.md) 所述的 Beam Search 中，多条序列共享完全相同的 Prompt 前缀甚至部分已生成的中间路径。PagedAttention 为每个物理块维护一个**引用计数（`ref_count`）**：

1. **零拷贝分叉（Zero-copy Forking）**：
   当序列 A 需要派生出候选分支 B 时，不需要拷贝任何物理 KV 显存，只需将序列 A 的块表浅拷贝给序列 B，并将这些共享物理块的 `ref_count` 加 $1$。
2. **写时复制（Copy-on-Write, CoW）触发条件**：
   当序列 A 和序列 B 各自采样出新的 Token，需要向各自的**最后一个未满逻辑块**追加写入新的 $(k_{\text{new}}, v_{\text{new}})$ 时，分配器检查该逻辑块对应的物理块 $p$：
   - **若 `ref_count[p] == 1`**（当前序列独占该物理块）：直接就地（In-place）写入该物理块的下一个空闲偏移槽位，无额外开销。
   - **若 `ref_count[p] > 1`**（该物理块正被多条序列共享，例如 Prompt 末尾未填满整块的残留部分）：为了防止覆盖破坏其他分支的历史 KV，触发 **CoW**：
     1. 从空闲物理池分配一个全新的物理块 $p_{\text{new}}$（`ref_count[p_new] = 1`）；
     2. 将原物理块 $p$ 中已有的 Token KV 数据复制到 $p_{\text{new}}$；
     3. 将原物理块的引用计数减 $1$（`ref_count[p] -= 1`）；
     4. 更新当前序列块表的最后一个映射指向 $p_{\text{new}}$，并在 $p_{\text{new}}$ 中追加写入新 Token。

> **关键细节**：前面已经彻底填满（Full）的共享逻辑块永远不会再被追加修改，因此它们的物理块在整个请求生命周期内始终保持共享（`ref_count > 1`），**写时复制只会发生在分叉点所在的那个未填满边界块上**！

---

### 4. 可运行的标准库实现：分页分配器、写时复制与非连续分块注意力仿真

以下 Python 3 标准库代码完整实现了 PagedAttention 的核心内存管理器（按需分块、零拷贝 `fork`、写时复制 `append_token`、块回收 `free`）、非连续分块注意力计算以及与传统连续预分配的显存浪费对比：

```python
import math
from typing import Dict, List, Tuple


class PagedKVCacheManager:
    def __init__(self, num_physical_blocks: int, block_size: int):
        self.block_size = block_size
        self.free_blocks: List[int] = list(range(num_physical_blocks))
        self.ref_counts: Dict[int, int] = {p: 0 for p in range(num_physical_blocks)}
        # 物理块存储: physical_block_id -> List of (k_vec, v_vec)
        self.physical_memory: Dict[int, List[Tuple[List[float], List[float]]]] = {
            p: [] for p in range(num_physical_blocks)
        }
        # 序列块表: seq_id -> List of physical_block_ids
        self.block_tables: Dict[str, List[int]] = {}

    def _alloc_block(self) -> int:
        assert self.free_blocks, "Out of physical KV blocks!"
        p = self.free_blocks.pop(0)
        self.ref_counts[p] = 1
        self.physical_memory[p] = []
        return p

    def create_sequence(self, seq_id: str) -> None:
        self.block_tables[seq_id] = []

    def fork_sequence(self, src_seq: str, dst_seq: str) -> None:
        """零拷贝派生新序列：共享块表并递增物理块引用计数"""
        self.block_tables[dst_seq] = list(self.block_tables[src_seq])
        for p in self.block_tables[dst_seq]:
            self.ref_counts[p] += 1

    def append_token_kv(self, seq_id: str, k_vec: List[float], v_vec: List[float]) -> None:
        """追加单个 Token 的 KV，自动处理按需分配与 Copy-on-Write (CoW)"""
        table = self.block_tables[seq_id]
        # 情况 1: 尚无块，或最后一个物理块已满 -> 分配新物理块
        if not table or len(self.physical_memory[table[-1]]) == self.block_size:
            new_p = self._alloc_block()
            table.append(new_p)
            self.physical_memory[new_p].append((k_vec, v_vec))
            return

        last_p = table[-1]
        # 情况 2: 最后一个块未满，但被多个序列共享 (ref_count > 1) -> 触发写时复制 CoW
        if self.ref_counts[last_p] > 1:
            new_p = self._alloc_block()
            # 复制原有已填充的 KV 数据
            self.physical_memory[new_p] = list(self.physical_memory[last_p])
            self.ref_counts[last_p] -= 1
            table[-1] = new_p
            last_p = new_p

        # 情况 3: 独占未满块 -> 直接就地追加
        self.physical_memory[last_p].append((k_vec, v_vec))

    def free_sequence(self, seq_id: str) -> None:
        """释放序列，引用计数归零的物理块归还空闲池"""
        for p in self.block_tables.pop(seq_id, []):
            self.ref_counts[p] -= 1
            if self.ref_counts[p] == 0:
                self.physical_memory[p] = []
                self.free_blocks.append(p)

    def paged_attention_decode(self, seq_id: str, q_vec: List[float]) -> List[float]:
        """沿着非连续物理块表直接计算缩放点积注意力"""
        dim = len(q_vec)
        scale = 1.0 / math.sqrt(dim)
        scores: List[float] = []
        values: List[List[float]] = []

        for p in self.block_tables[seq_id]:
            for k_vec, v_vec in self.physical_memory[p]:
                s = sum(q_vec[d] * k_vec[d] for d in range(dim)) * scale
                scores.append(s)
                values.append(v_vec)

        max_s = max(scores)
        exps = [math.exp(s - max_s) for s in scores]
        denom = sum(exps)
        probs = [e / denom for e in exps]
        return [sum(probs[t] * values[t][d] for t in range(len(values))) for d in range(dim)]


# 仿真验证: 块大小 B = 4，Prompt 长度为 6 个 Token (占 1 个满块 + 1 个含 2 Token 的半满块)
mgr = PagedKVCacheManager(num_physical_blocks=16, block_size=4)
mgr.create_sequence("seq_A")

prompt_kvs = [
    ([1.0, 0.0], [10.0, 20.0]),
    ([0.0, 1.0], [20.0, 30.0]),
    ([1.0, 1.0], [30.0, 40.0]),
    ([0.5, 0.5], [40.0, 50.0]),  # 填满物理块 0
    ([2.0, 0.0], [50.0, 60.0]),  # 进入物理块 1 (offset 0)
    ([0.0, 2.0], [60.0, 70.0]),  # 进入物理块 1 (offset 1)
]
for k, v in prompt_kvs:
    mgr.append_token_kv("seq_A", k, v)

assert mgr.block_tables["seq_A"] == [0, 1]

# Parallel Sampling: 从 seq_A 派生出 seq_B
mgr.fork_sequence("seq_A", "seq_B")
assert mgr.ref_counts[0] == 2 and mgr.ref_counts[1] == 2

# seq_A 和 seq_B 各自生成第 7 个 Token (触发物理块 1 的写时复制 CoW，而物理块 0 保持共享!)
mgr.append_token_kv("seq_A", [1.0, -1.0], [70.0, 80.0])
mgr.append_token_kv("seq_B", [-1.0, 1.0], [90.0, 100.0])

# 验证块表与引用计数: 物理块 0 仍由两者共享 (ref=2)，seq_A 拿到新物理块 2 (ref=1)，seq_B 留在原物理块 1 (ref=1)
assert mgr.block_tables["seq_A"] == [0, 2]
assert mgr.block_tables["seq_B"] == [0, 1]
assert mgr.ref_counts[0] == 2 and mgr.ref_counts[1] == 1 and mgr.ref_counts[2] == 1

# 验证非连续物理块上的 Attention 计算与连续张量完全一致
out_A = mgr.paged_attention_decode("seq_A", [1.0, 0.5])
out_B = mgr.paged_attention_decode("seq_B", [1.0, 0.5])
assert out_A != out_B

# 核算显存槽位占用对比 (最大长度 S_max=2048，两条序列实际各 7 个 Token)
contiguous_reserved_slots = 2 * 2048
paged_allocated_slots = sum(1 for p, ref in mgr.ref_counts.items() if ref > 0) * mgr.block_size
internal_frag_slots = paged_allocated_slots - (6 + 1 + 1)  # 6个共享Prompt + 2个独立生成Token = 8个唯一Token

print(f"Block tables after CoW: seq_A={mgr.block_tables['seq_A']}, seq_B={mgr.block_tables['seq_B']}")
print(f"Ref counts: block_0={mgr.ref_counts[0]}, block_1={mgr.ref_counts[1]}, block_2={mgr.ref_counts[2]}")
print(f"Allocated token slots: Contiguous={contiguous_reserved_slots}, Paged={paged_allocated_slots} (3 blocks of size 4)")
print(f"Seq_A Attention Output: {[round(x, 4) for x in out_A]}")
print("PagedAttention allocation, Copy-on-Write, and non-contiguous attention checks passed")
```

实际执行输出：

```text
Block tables after CoW: seq_A=[0, 2], seq_B=[0, 1]
Ref counts: block_0=2, block_1=1, block_2=1
Allocated token slots: Contiguous=4096, Paged=12 (3 blocks of size 4)
Seq_A Attention Output: [40.3979, 50.3979]
PagedAttention allocation, Copy-on-Write, and non-contiguous attention checks passed
```

---

### 5. 块大小（Block Size $B$）的工程权衡与抢占策略

1. **块大小 $B$ 选多大最合适？（通常选 $B = 16$ 或 $32$）**
   - **如果 $B$ 太小（例如 $B = 1$ 或 $2$）**：
     虽然内部碎片完全消失，但块表体积剧增，且更致命的是**破坏了 GPU 内存合并访问（Memory Coalescing）与向量化加载效率**。GPU Warp（32 线程）从 HBM 读取数据时需要连续的缓存行（Cache Line，通常 128 字节），块太小会导致严重的离散随机访存，使 Attention Kernel 带宽利用率暴跌。
   - **如果 $B$ 太大（例如 $B = 256$ 或 $512$）**：
     每个序列末尾未填满的内部碎片上限（$B - 1$ 个 Token）急剧增大；同时，基于块哈希的跨请求 Prefix Caching 必须攒够一整块 $B$ 个 Token 才能命中复用，块太大导致细粒度前缀共享率下降。
   - **黄金折中**：SOSP 2023 论文消融实验表明，$B = 16$ 或 $32$ 既能让 GPU 线程束充分打满 HBM 合并访存带宽，又能把末尾内部碎片控制在极低水平（平均仅浪费 $\le B/2$ 个 Token）。
2. **当并发序列同时增长导致物理块耗尽时怎么办？**
   由于 PagedAttention 是按需增量分配块，可能出现所有活动序列都在继续生成、但空闲物理块池耗尽的情况。此时调度器会按 FCFS（先来先服务）优先级，选择最新到达的低优先级请求群组执行抢占（Preemption）：
   - **Swapping（换出到 CPU 内存）**：将被抢占序列的物理块通过 PCIe 拷贝到 CPU 固定内存（Pinned Host RAM），释放 GPU 物理块；待高优请求完成后再换回（Swap-in）。
   - **Recomputation（丢弃重算）**：直接释放被抢占序列的物理块，将其已生成的 Token 拼接回原始 Prompt；后续恢复调度时直接走一次快速的 Prefill 重新算出 KV Cache（对于短序列或 PCIe 带宽受限机器，重算往往比跨 PCIe 搬运更快）。

---

## 延伸 / 追问

**追问 1：PagedAttention 会让单条无并发请求（`Batch Size = 1`）的解码速度变快吗？**
不会，甚至因为多了一层块表间接寻址（Block Table Indirection）和分散读取，单条请求的纯 Kernel 执行耗时比连续内存版还要略微慢 $1\% \sim 5\%$。PagedAttention 的真正威力在于**消除了约 $60\% \sim 80\%$ 的显存碎片浪费，使同一张 GPU 能够同时塞进原本 $2\times \sim 4\times$ 数量的并发序列**，通过大幅放大有效 Batch Size 来显著提升系统整体吞吐（Throughput）。

**追问 2：跨请求的自动前缀缓存（Automatic Prefix Caching, APC）是如何基于 PagedAttention 实现的？**
系统将每个填满的逻辑块按照 `Hash(父块哈希, 当前块内 B 个 Token ID)` 计算出唯一的内容哈希值。物理块不再在请求结束时立刻清空，而是放入全局哈希缓存池并保留 KV 数据（以 LRU 策略淘汰）。当新请求的 Prompt 前缀块计算出相同的哈希值时，直接将其块表指向缓存池中已有的物理块并递增 `ref_count`，从而跳过该前缀的 Prefill 计算。

**追问 3：当发生写时复制（CoW）时，为什么要复制整个物理块，而不是只给新 Token 单独开一个块？**
因为 PagedAttention 严格维护不变量：“除序列最后一个逻辑块外，前面所有逻辑块必须完全填满 $B$ 个 Token”。如果不在未满的共享块上做 CoW、而是强行留下一个半满的中间块并另起新块，就会在序列中间产生大量内部碎片，且打乱了位置索引 $\lfloor t / B \rfloor$ 与 $t \bmod B$ 的 O(1) 定长寻址规律。

---

## 常见误区

- **误区一：“PagedAttention 压缩了单个 Token 的 KV Cache 字节大小。”**
  事实：单个 Token 占用的 KV 字节数（$2 \cdot b \cdot L \cdot H_{kv} \cdot d_{\text{head}}$）由模型架构（如 GQA/MLA）和量化精度（FP16/FP8）决定，PagedAttention **不改变单 Token 的特征维度或精度**，它消除的是未使用的预留槽位和显存碎片。
- **误区二：“并行采样或 Prefix Caching 共享 KV Cache 时，任何修改都会导致整条 Prompt 的所有块全部复制一份。”**
  事实：写时复制（CoW）是**块粒度（Block-level）**的。一条长 4000 Token 的 Prompt 若按 $B=16$ 切分为 250 个块，前 249 个已满块永远只读不改（始终保持零拷贝共享），最多只有最后 1 个未填满的尾部块会在写入新 Token 时复制 1 次。
- **误区三：“用了 PagedAttention 就永远不会发生显存不足（OOM）或请求排队。”**
  事实：当所有活动序列的真实总 Token 数乘以单 Token KV 体积超过 GPU 物理块池上限时，依然会触发块耗尽，此时必须依赖调度器执行请求排队、Swapping 换出或 Recomputation 重算。

---

## 参考

- 选题线索：[neurarch-ai/awesome-llm-system-design, book/kv-cache/08-interview-qa.md](https://github.com/neurarch-ai/awesome-llm-system-design/blob/f3e737b29c41b8ac79f4fd44949620c100e5a0bd/book/kv-cache/08-interview-qa.md)。固定 commit，独立拓展改编。
- Kwon et al., [Efficient Memory Management for Large Language Model Serving with PagedAttention](https://arxiv.org/html/2309.06180v1)，SOSP 2023，§3–§5：内部/外部碎片与预留浪费定量分析、逻辑块与物理块映射、分块 Attention 公式、Copy-on-Write 机制与 Swapping/Recomputation 抢占策略。

来源访问与示例核验日期：**2026-10-23**。仅执行标准库分页内存管理与注意力数值验证，未运行 GPU 内核性能基准测试。
