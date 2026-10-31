---
id: engineering-0045
title: 为什么大规模 LLM 推理集群要做 Prefill 与 Decode 分离部署（P/D Disaggregation），跨节点 KV Cache 传输预算与 KV-Aware 路由应如何设计？
category: engineering
tags: [pd-disaggregation, distserve, kv-cache-transfer, kv-aware-routing, goodput, chunked-prefill]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开 AI 系统设计指南与面试题库扩展改编；DistServe、Sarathi-Serve 原论文及 vLLM/SGLang/Dynamo 官方架构核实（见参考）
status: published
updated: 2026-10-30
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-10-30
    updated: 2026-10-30
---

## 问题

在生产级大模型推理集群（特别是承载数万 Token 上下文的多轮 Agent 与 RAG 流量）中，线上服务必须同时满足两项严苛的服务等级目标（SLO）：既要保证**首 Token 延迟（TTFT, Time-to-First-Token）**足够低，又要保证流式生成阶段的**每 Token 间隔延迟（TPOT / ITL, Time-Per-Output-Token / Inter-Token Latency）**平滑无卡顿。

然而，在传统的单池共置（Colocated Continuous Batching）架构中，突发到达的长 Prompt 预填充（Prefill）会频繁打断正在生成的解码（Decode）批次。为此，现代推理基础设施（如 DistServe、vLLM Disaggregated Serving、SGLang、NVIDIA Dynamo）普遍演进向 **Prefill 与 Decode 分离部署（P/D Disaggregation）** 与 **KV 感知路由（KV-Aware Routing）**。请深入剖析：
1. 为什么即便开启了分块预填充（Chunked Prefill / Sarathi-Serve），单实例共置架构在长上下文流量下仍然难以最大化**有效吞吐（Goodput，即同时满足 TTFT 与 TPOT SLO 的最大请求率）**？Prefill 与 Decode 在硬件算术强度（Arithmetic Intensity）、批大小扩展规律及最优模型并行策略（TP vs PP/EP）上有何本质冲突？
2. 当把 Prefill 池与 Decode 池物理拆开后，如何定量计算跨节点传输 KV Cache 的体积与网络延迟预算（以 Llama-3-70B BF16 在 $400\text{ Gbps}$ RDMA 下传输 $10\text{k}$ Token 为例）？为什么工程上必须引入**逐层流水线式 KV 传输（Layer-by-Layer Pipelined Transfer）**与**短请求条件旁路（Conditional Disaggregation Bypass）**？
3. 在多副本集群前端，**KV-Aware 路由器**是如何综合评估“前缀缓存命中量”与“副本队列负载”来替代传统轮询/粘性会话的？为什么共享前缀缓存在多租户环境下会构成**跨租户计时侧信道（Timing Side-Channel）**，应如何通过链式块哈希加盐（`cache_salt`）实现安全隔离？

本题由公开 AI 系统设计指南与面试题库扩展改编，不是已核实的企业真题；不采信脱离具体模型架构、互连带宽与 SLO 阈值的固定收益倍数。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-10-30

**Prefill 与 Decode 分离部署（P/D Disaggregation）的核心动机是“消除两类异构计算阶段的相互干扰，按各自硬件瓶颈独立寻优并行度与扩缩容比例，从而最大化集群的 SLO 有效吞吐（Goodput）”：Prefill 是强算力受限（Compute-Bound）的矩阵-矩阵乘法，而 Decode 是强显存带宽受限（Memory-Bandwidth-Bound）的矩阵-向量乘法；共置架构（即便开启 Chunked Prefill）不仅会在尾延迟上产生互相拖累，还迫使两个阶段被迫共享同一套次优的 GPU 配比与张量/流水线并行度。分离架构将长请求路由至高算力 Prefill 池完成首 Token 计算，再通过 RDMA/NVLink 逐层异步传输 KV Cache 至高并发 Decode 池持续生成，并对短未命中请求启用条件旁路（Conditional Bypass）直连 Decode 池以规避传输税；同时在网关层利用带租户盐值（`cache_salt`）的 KV-Aware 路由器权衡前缀命中率与队列排队代价，兼顾高缓存命中、低尾延迟与多租户安全隔离。**

现有 [llm-0018](llm-0018-kv-cache-prefill-decode.md) 阐述了 KV Cache 在 Prefill 与 Decode 阶段的基础缓存原理，[llm-0016](llm-0016-quantization-local-memory-budget.md) 介绍了单卡量化与模型权重显存估算，[engineering-0021](engineering-0021-llm-queue-backpressure.md) 讨论了队列背压控制。本题聚焦**集群级推理架构中的 P/D 解耦设计、Goodput 优化目标、跨节点 KV Cache 传输带宽数学核算、分层 KV 卸载（Tiered KV Offloading）以及多租户 KV-Aware 路由算法**。

---

### 1. 为什么 Chunked Prefill 仍不够？Prefill 与 Decode 的三大结构性冲突

在单池共置（Colocated）连续批处理引擎中，同一个 GPU 实例既要接纳新到达请求的 Prefill，又要推进存量请求的 Decode。Agrawal et al. (2024, *Sarathi-Serve*) 提出的 **分块预填充（Chunked Prefill）** 将一个长 Prompt（如 $32\text{k}$ Token）切分为若干小块（如每步最多拼入 $2,048$ 个 Prefill Token），并将存量 Decode 请求“捎带（Piggyback）”在同一个混合 Batch 中执行，从而缓解了动辄数秒的世代卡死（Generation Stall）。

然而，Zhong et al. (2024, *DistServe*, OSDI 2024) 与 Patel et al. (2024, *Splitwise*, ISCA 2024) 证明，当线上对 **TTFT（首字延迟）** 和 **TPOT（吐字间隔）** 同时设有严格 P95/P99 SLO 时，Chunked Prefill 仍存在三大无法在单池内消除的物理矛盾：

| 冲突维度 | Prefill 阶段（首 Token 生成） | Decode 阶段（自回归逐字生成） | 单池共置（含 Chunked Prefill）的固有代价 |
| --- | --- | --- | --- |
| **硬件瓶颈与算术强度** | **Compute-Bound（算力受限）**：数千输入 Token 并行计算，算术强度（FLOPs/Byte）轻松超过 GPU 屋脊线拐点（如 H100 的 $\sim 295\text{ FLOPs/Byte}$） | **Memory-Bandwidth-Bound（访存受限）**：每请求仅输入 1 个 Token，每生成一个词都要将整份模型权重与历史 KV 从 HBM 读入寄存器 | 混合 Batch 中，Prefill 块越大，Decode 步耗时越长（拉高 TPOT 抖动）；Prefill 块越小，长 Prompt 被迫拆成几十轮迭代且反复重读历史 KV（拉高 TTFT） |
| **最优批处理策略** | 单条或极小 Batch（$B=1\sim 2$）即可打满 Tensor Core，增大 Batch 只会线性增加排队与 TTFT | 必须凑出**大 Batch（$B=32\sim 256$）**分摊一次权重读取的 HBM 带宽开销，才能提升每秒吐字吞吐 | Prefill 渴望低并发快进快出，Decode 渴望高并发长驻驻留，同一实例无法同时处于两个工作点 |
| **最优模型并行与硬件配比** | 高算力负载在中等张量并行（TP）结合流水线并行（PP）下扩展良好；更偏爱高 FLOPs 芯片 | 极度依赖低延迟 All-Reduce 以压低单步 TPOT，或在大规模 MoE 下采用宽专家并行（EP）+ 窄注意力并行；更偏爱高 HBM 容量/带宽芯片 | 共置实例被迫为两个阶段绑定完全相同的 TP/PP 拓扑与相同的硬件型号，造成严重的资源过配（Over-Provisioning） |

因此，工业界将核心衡量指标从单纯的“峰值 Token 吞吐”转向 **有效吞吐（Goodput）**——即**在满足给定 $(SLO_{\text{TTFT}}, SLO_{\text{TPOT}})$ 约束（如 $>95\%$ 请求达标）前提下，每张 GPU 每秒能承载的最大有效请求数**。P/D 分离通过将集群拆分为独立的 **Prefill 实例池** 与 **Decode 实例池**（例如按业务读写比配成 $3\text{ Prefill} : 1\text{ Decode}$ 或相反），彻底切断了 Prefill 突发对 Decode TPOT 的干扰。

---

### 2. 跨节点 KV Cache 传输预算核算与流水线隐藏机制

当 Prefill 实例算完输入序列的最后一层并吐出第 1 个 Token 后，必须将该请求在所有 Transformer 层产生的 KV Cache 移交给选定的 Decode 实例。**如果不精心设计传输链路，KV 搬运耗时本身就会吃掉解耦带来的全部收益。**

```text
                       [ KV-Aware 网关路由器 (Endpoint Picker) ]
                        │ (1. 计算加盐前缀哈希, 评估未命中 Token 数与队列负载)
          ┌─────────────┴───────────────────────────────────────────┐
          ▼ (短未命中请求: uncached <= 512 tok)                      ▼ (长 Prompt 请求: uncached > 512 tok)
 [ 条件旁路 (Conditional Bypass) ]                         [ Prefill 实例池 (Compute-Optimized) ]
   跳过 Prefill 池与跨网传输，                                 逐层前向计算 Layer 1 .. Layer L
   直接由目标 Decode 节点原地完成 Prefill + Decode               │
          │                                                     │ (2. Layer-by-Layer 异步 RDMA/NVLink 推送:
          │                                                     │     算完第 l 层立即用 NIXL/Mooncake 传第 l 层 KV，
          │                                                     │     与第 l+1..L 层前向计算完全重叠)
          ▼                                                     ▼
                       [ Decode 实例池 (Memory-Bandwidth-Optimized) ]
                        接收完最后一层 KV 后立即无缝接管第 2..N 个 Token 的低抖动生成
```

#### 定量核算：传一个 $10\text{k}$ Token 的请求到底要移多少数据、花多少毫秒？
对于任意采用标准多头或分组查询注意力（MHA / GQA）的模型，设层数为 $L$，KV 注意力头数为 $H_{\text{kv}}$，单头维度为 $d_h$，数值精度字节数为 $b$（BF16/FP16 取 $b=2$，FP8 取 $b=1$），则**每个 Token 的 KV Cache 字节数**为：

$$\text{Bytes}_{\text{KV/tok}} = 2 \times L \times H_{\text{kv}} \times d_h \times b$$

以主流开源大模型 **Llama-3.1/3.3-70B（BF16）** 为例：$L = 80$，$H_{\text{kv}} = 8$，$d_h = 128$，$b = 2$：
1. **单 Token KV 体积**：$\text{Bytes}_{\text{KV/tok}} = 2 \times 80 \times 8 \times 128 \times 2 = 327,680\text{ Bytes} = \mathbf{320\text{ KiB/token}}$；
2. **$10,240$（$10\text{k}$）Token Prompt 的总 KV 体积**：$10,240 \times 320\text{ KiB} = 3,276,800\text{ KiB} = \mathbf{3.125\text{ GiB}}$（约 $3.36\text{ GB}$）；
3. **在 $400\text{ Gbps}$（理论峰值 $50\text{ GB/s}$，按 $85\%$ 实际有效带宽即 $42.5\text{ GB/s}$ 计）RDMA 网卡下的阻塞传输耗时**：
   $$T_{\text{transfer}} = \frac{3.125 \times 1024^3\text{ Bytes}}{42.5 \times 10^9\text{ Bytes/s}} \approx \mathbf{78.95\text{ ms}}$$
   而在没有高速 RDMA、仅有 $25\text{ Gbps}$ 普通以太网的环境下，传输同样 $3.125\text{ GiB}$ 需要超过 **$1.2\text{ s}$**，此时跨机 P/D 分离会彻底劣化！

#### 三大工程加速与防退化机制
1. **逐层异步流水线传输（Layer-by-Layer Pipelined KV Transfer）**：
   Prefill 节点绝不等到全部 $L=80$ 层都算完才开始发网络包。当 GPU 刚算完第 $l$ 层的 Attention 并将 $K^{(l)}, V^{(l)}$ 写入显存页时，底层通信库（如 NIXL、Mooncake、MSCCL++）立即通过 GPUDirect RDMA 在独立 CUDA Stream 上将第 $l$ 层的 KV 异步推送给 Decode 节点，而 GPU 同时继续计算第 $l+1$ 层。这样，**前 $L-1$ 层的网络传输耗时被完全隐藏在 Prefill 前向计算内部**，只有最后一层（仅占总体积的 $1/80 \approx 40\text{ MiB}$，耗时 $<1\text{ ms}$）暴露在关键路径上。
2. **短请求条件解耦旁路（Conditional Disaggregation Bypass）**：
   对于只有两三百个未缓存 Token 的短请求（如简短日常对话，或多轮 Agent 中前 $20\text{k}$ Token 已全部命中 Decode 节点本地前缀缓存、仅新增 $150\text{ Token}$ 工具结果的续跑轮次），跨池握手与元数据调度开销反而大于原地计算。因此，现代编排层（如 NVIDIA Dynamo）设置了动态阈值：当请求的**未缓存 Prefill Token 数 $\le \tau_{\text{bypass}}$** 且目标 Decode 节点算力有余量时，**直接旁路 Prefill 池**，将请求发给 Decode 节点原地完成。
3. **紧凑注意力架构（MLA / FP8 KV / 混合线性注意力）对 P/D 传输的天然加成**：
   千万不要用同一套 `320 KiB/token` 公式生搬硬套所有模型！采用 **多头潜在注意力（MLA，如 DeepSeek-V2/V3/R1）**、**FP8/FP4 KV 量化** 或 **滑动窗口 + 线性注意力混合架构（如 Qwen3-Next / MiMo 等）** 的模型，其单 Token 需传输的全局 KV 状态可缩小至数十分之一甚至百字节级，使得跨节点 P/D 分离在普通高速网络上也极度轻快。

---

### 3. KV-Aware 路由、分层卸载与可运行标准库实现

在多副本推理集群中，如果网关仍使用传统的轮询（Round-Robin）或最小连接数负载均衡，同一多轮 Agent 会话的连续请求会被随机打散到不同副本，导致昂贵的系统提示词、工具 Schema 与长文档前缀在每台机器上重复计算。

#### KV-Aware 路由代价函数与多租户侧信道防护
现代推理网关（如 Kubernetes Gateway API Inference Extension `llm-d`、SGLang Router、Dynamo Router）通过维护前缀块哈希树（Radix Tree / Block Hash Table），为每个请求计算路由到候选副本 $w$ 的综合预测延迟代价：

$$\text{Cost}(w) = \frac{N_{\text{total}} - N_{\text{cached}}(w, \text{tenant})}{R_{\text{prefill}}} + \alpha \cdot Q_{\text{load}}(w)$$

其中 $N_{\text{cached}}(w, \text{tenant})$ 是副本 $w$ 上已缓存的连续前缀 Token 数（涵盖 GPU HBM 与通过 **SGLang HiCache / vLLM Tiered Offloading** 下沉到 Host Pinned DRAM 甚至 NVMe 磁盘的二级缓存），$R_{\text{prefill}}$ 为预填充速率，$Q_{\text{load}}(w)$ 为副本当前排队等待的 Token 负载。当持有完整缓存的副本 $w_0$ 发生严重排队拥塞时，路由器会自动权衡，将请求切向缓存部分命中但队列空闲的副本 $w_1$。

**安全红线——跨租户前缀缓存侧信道（Prefix Cache Timing Side-Channel）**：
如果多个租户共享同一个无隔离的前缀缓存池，攻击者可以构造包含目标机密文档或特定系统提示词前缀的请求，通过观测返回的首字延迟（TTFT 是 $80\text{ ms}$ 还是 $1,500\text{ ms}$）或 Usage 中的 `cached_tokens` 字段，精确探测其他租户是否刚刚访问过该敏感文本！因此，在计算前缀块哈希时，**必须在根块混入租户唯一盐值 `cache_salt`（即 $h_k = \operatorname{Hash}(\text{tenant\_id} \,\|\, h_{k-1} \,\|\, \text{tokens}_k)$）**，并在包括工具续跑（Tool Continuation）在内的所有 API 路径上强制执行。

#### 可运行的标准库实现：KV 传输预算核算、加盐链式前缀哈希与条件旁路路由

以下 Python 3 标准库代码完整实现了（1）GQA 模型的跨节点 KV Cache 传输体积与耗时计算，（2）带 `tenant_id` 盐值隔离的链式前缀块哈希，（3）综合缓存命中率与队列拥塞惩罚的 KV-Aware 路由决策，以及（4）短增量请求的条件解耦旁路（Conditional Bypass）：

```python
import hashlib
from dataclasses import dataclass, field
from typing import List, Set, Tuple


def compute_kv_bytes_per_token(
    num_layers: int,
    num_kv_heads: int,
    head_dim: int,
    bytes_per_elem: int = 2,
) -> int:
    """标准 MHA/GQA 模型单 Token 的 KV Cache 字节数: 2 (K+V) * L * H_kv * d_h * bytes"""
    return 2 * num_layers * num_kv_heads * head_dim * bytes_per_elem


def estimate_kv_transfer_ms(
    seq_len: int,
    kv_bytes_per_token: int,
    link_gbps: float,
    efficiency: float = 0.85,
) -> Tuple[float, float]:
    """
    计算跨节点传输 seq_len 个 Token 的 KV Cache 体积 (GiB) 与全量阻塞传输耗时 (ms)
    link_gbps: 物理链路带宽 (如 400 Gbps RDMA RoCEv2 / InfiniBand)
    """
    total_bytes = seq_len * kv_bytes_per_token
    total_gib = total_bytes / (1024 ** 3)
    effective_bytes_per_sec = (link_gbps * 1e9 / 8.0) * efficiency
    transfer_ms = (total_bytes / effective_bytes_per_sec) * 1000.0
    return round(total_gib, 4), round(transfer_ms, 2)


def salted_prefix_block_hash(tenant_id: str, token_block: Tuple[int, ...], parent_hash: str = "0") -> str:
    """
    带租户隔离盐值 (cache_salt) 的链式前缀块哈希:
    只有当 tenant_id、父块哈希与当前块 Token 完全一致时才产生相同哈希，杜绝跨租户缓存探测侧信道
    """
    payload = f"{tenant_id}|{parent_hash}|{token_block}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


@dataclass
class EngineWorker:
    worker_id: str
    queued_tokens: int
    cached_block_hashes: Set[str] = field(default_factory=set)


def select_worker_and_mode(
    tenant_id: str,
    prompt_blocks: List[Tuple[int, ...]],
    workers: List[EngineWorker],
    prefill_rate_tok_per_ms: float = 40.0,
    bypass_threshold_tokens: int = 512,
    load_penalty_ms_per_ktok: float = 35.0,
) -> Tuple[str, str, int, float]:
    """
    KV-Aware 路由与条件解耦旁路 (Conditional Disaggregation Bypass):
    1. 计算带 tenant_id 盐值的链式块哈希，统计各 Worker 连续命中的前缀 Token 数；
    2. 评估各 Worker 的预计等待与计算代价: Cost = uncached_tokens / prefill_rate + queue_penalty；
    3. 若未命中缓存的剩余 Prefill Token 数 <= bypass_threshold_tokens，直接旁路发往 Decode 池原地计算，
       避免为短增量请求付出跨池调度与 KV 传输开销。
    """
    block_hashes: List[str] = []
    parent = "0"
    for blk in prompt_blocks:
        h = salted_prefix_block_hash(tenant_id, blk, parent)
        block_hashes.append(h)
        parent = h

    total_tokens = sum(len(b) for b in prompt_blocks)
    best_worker = ""
    best_cost_ms = float("inf")
    best_uncached = total_tokens

    for w in workers:
        matched_tokens = 0
        for blk, h in zip(prompt_blocks, block_hashes):
            if h in w.cached_block_hashes:
                matched_tokens += len(blk)
            else:
                break
        uncached_tokens = total_tokens - matched_tokens
        compute_ms = uncached_tokens / prefill_rate_tok_per_ms
        queue_ms = (w.queued_tokens / 1000.0) * load_penalty_ms_per_ktok
        total_cost_ms = compute_ms + queue_ms
        if total_cost_ms < best_cost_ms:
            best_cost_ms = total_cost_ms
            best_worker = w.worker_id
            best_uncached = uncached_tokens

    mode = "DIRECT_DECODE_BYPASS" if best_uncached <= bypass_threshold_tokens else "DISAGGREGATED_PREFILL"
    return best_worker, mode, best_uncached, round(best_cost_ms, 2)


# --- 验证 1: Llama-3-70B (BF16, GQA 80层 8头 128维) 10,240 Tokens KV 传输核算 ---
kv_per_tok = compute_kv_bytes_per_token(num_layers=80, num_kv_heads=8, head_dim=128, bytes_per_elem=2)
assert kv_per_tok == 327680  # 320 KiB / token
gib_10k, ms_10k = estimate_kv_transfer_ms(seq_len=10240, kv_bytes_per_token=kv_per_tok, link_gbps=400.0, efficiency=0.85)
assert gib_10k == 3.125 and 75.0 <= ms_10k <= 80.0

# --- 验证 2: KV-Aware 路由综合权衡缓存命中与队列排队负载 ---
shared_sys_block = tuple(range(1, 2049))    # 2048 tokens 系统提示词
user_turn_block = tuple(range(2049, 4097))  # 2048 tokens 用户文档
h1 = salted_prefix_block_hash("tenant_A", shared_sys_block, "0")
h2 = salted_prefix_block_hash("tenant_A", user_turn_block, h1)

# Worker-0 虽缓存了全部 4096 tokens，但队列积压严重 (12,000 tokens)；Worker-1 缓存了前 2048 tokens 且队列空闲
w0 = EngineWorker("worker-0", queued_tokens=12000, cached_block_hashes={h1, h2})
w1 = EngineWorker("worker-1", queued_tokens=500, cached_block_hashes={h1})

chosen_w, mode_A, uncached_A, cost_A = select_worker_and_mode("tenant_A", [shared_sys_block, user_turn_block], [w0, w1])
assert chosen_w == "worker-1" and mode_A == "DISAGGREGATED_PREFILL" and uncached_A == 2048

# --- 验证 3: 跨租户 cache_salt 隔离防侧信道 + 短增量请求触发 Conditional Bypass ---
# Tenant_B 发送完全相同的 token 序列，但因 tenant_id 不同，无法命中 Tenant_A 的缓存块
_, _, uncached_B, _ = select_worker_and_mode("tenant_B", [shared_sys_block, user_turn_block], [w0, w1])
assert uncached_B == 4096

# 当 Worker-1 已缓存前 4096 tokens，本轮仅新增 128 tokens 工具结果追问时，触发短请求旁路直连 Decode
short_followup = tuple(range(4097, 4225))
w1.cached_block_hashes.add(h2)
_, mode_short, uncached_short, _ = select_worker_and_mode(
    "tenant_A", [shared_sys_block, user_turn_block, short_followup], [w0, w1]
)
assert uncached_short == 128 and mode_short == "DIRECT_DECODE_BYPASS"

print(f"70B BF16 KV/tok: {kv_per_tok // 1024} KiB; 10k prompt KV: {gib_10k} GiB, transfer @400Gbps: {ms_10k} ms")
print(f"KV-Aware Route (tenant_A): {chosen_w}, mode={mode_A}, uncached={uncached_A}, est_cost={cost_A} ms")
print(f"Cross-tenant (tenant_B) uncached tokens: {uncached_B}; Short follow-up mode: {mode_short}")
print("P/D disaggregation KV transfer, salted KV-aware routing, and bypass checks passed")
```

实际执行输出：

```text
70B BF16 KV/tok: 320 KiB; 10k prompt KV: 3.125 GiB, transfer @400Gbps: 78.95 ms
KV-Aware Route (tenant_A): worker-1, mode=DISAGGREGATED_PREFILL, uncached=2048, est_cost=68.7 ms
Cross-tenant (tenant_B) uncached tokens: 4096; Short follow-up mode: DIRECT_DECODE_BYPASS
P/D disaggregation KV transfer, salted KV-aware routing, and bypass checks passed
```

---

## 延伸 / 追问

**追问 1：如果 Prefill 池使用 `TP=4`（4 卡张量并行），而 Decode 池使用 `TP=8`（8 卡张量并行）以容纳更大的并发 KV Cache，两池之间的 KV Cache 传输会遇到什么张量布局问题？如何解决？**
在张量并行（TP）下，每一层的注意力头 $H_{\text{kv}}$ 是按列切分（Column-Parallel）散落在各个 TP Rank 上的。当 `TP_prefill = 4`（每张卡持有 $8 / 4 = 2$ 个 KV 头）向 `TP_decode = 8`（每张卡持有 $8 / 8 = 1$ 个 KV 头）传输时，源卡与目标卡的显存页布局（Page Layout）不再是一对一镜像，而是需要将每个 Prefill Rank 的 KV 切片拆开分别发往两个对应的 Decode Rank。
工程解决方案有两种：（1）**点对点子块直传（Sub-Block Peer-to-Peer Scatter）**：通信连接器（如 NIXL / Mooncake）将内存页索引精确到 `head` 或 `sub-group` 粒度，由每个 Prefill GPU 通过 RDMA Write 直接把对应头切片写入目标 Decode GPU 的物理页偏移；（2）**主机端规范化中转（Canonical Host Layout）**：如 vLLM 的多级卸载架构，先将 GPU 显存中的 KV 页异步汇聚到 Host Pinned DRAM 中与 TP 无关的规范化内存布局（Canonical Layout），再由任意不同 TP 拓扑的实例按需拉取。

**追问 2：当 Prefill 池的生产速度瞬间高于 Decode 池的消化速度（例如突发涌入大量长文本总结且输出也很长的请求）时，如果在 Prefill 节点显存里排队等待传输，会发生什么故障？如何设计跨池背压（Backpressure）？**
如果 Prefill 节点算完一个 $32\text{k}$ 请求（占约 $10\text{ GiB}$ KV 显存）后，Decode 池全满无法接收，这份已算好的 KV Cache 就会滞留在 Prefill 节点的 HBM 中。短短几个并发请求滞留就会把 Prefill 节点的显存彻底撑爆（死锁或 OOM），导致整个 Prefill 池瘫痪！
正确的跨池背压与流控契约是：
1. **先预留后拉取（Pre-Allocate & Pull Mode）或主机内存卸载缓冲**：在 Prefill 启动前（或刚完成时），协调器先向目标 Decode 节点申请锁定对应数量的物理 KV 页槽位；若 Decode 池显存水位超限，Prefill 节点算完后立即将 KV 异步卸载（Offload）到本机大容量的 Pinned Host DRAM 缓冲池中并释放 GPU HBM，等 Decode 空出槽位再从 DRAM 经 RDMA 拉取；
2. **网关级早期准入控制（Early Admission Control）**：结合 [engineering-0021](engineering-0021-llm-queue-backpressure.md)，当监测到 Decode 池 KV 利用率超过水位（如 $85\%$）或等待队列突破 `--max-num-queued-reqs` 时，直接在网关层挂起新 Prefill 分发或触发弹性扩容，绝不让未消化状态堆积在昂贵的 Prefill HBM 上。

**追问 3：在长连接流式输出（SSE / gRPC）中，网关层做故障转移（Failover）为什么必须区分“首 Token 到达前”和“首 Token 到达后”？**
因为一旦网关已经向客户端流式推出了哪怕 1 个 Token，这次 HTTP/SSE 响应的状态码就已经锁死为 `200 OK` 且部分正文字节已落入客户端解析器。如果此时后端 Decode 节点崩溃，网关若在底层悄悄重连另一个副本从头重算并继续往同一个流里灌数据，客户端就会收到一段**前半截与新开头拼接在一起的畸形重复文本**，甚至导致工具调用被触发两次（见 [engineering-0017](engineering-0017-model-routing-failover.md)）。
因此，生产级 AI 网关（如 Envoy AI Gateway）严守**首字分界线**：在首个 Token 产生之前（如触发 `streamIdleTimeout` 或预检返回 `503`），网关可对客户端完全透明地切换到备用副本或跨云供应商；一旦首个 Token 已经发出，后端断流必须立即显式终止流并向客户端上报流错误，由上层 Agent 循环根据已收到的完整记录与工具幂等键决定如何安全续跑。

---

## 常见误区

- **误区一：“任何规模的 LLM 服务只要上了 P/D 分离（Disaggregated Serving），吞吐和延迟就一定比单池共置（Colocated）好。”**
  事实：P/D 分离引入了额外的跨机网络传输、独立池容量碎片以及复杂的分布式故障域。如果业务流量主要是**短 Prompt（如几百 Token 的日常聊天）**、集群规模较小（只有几张卡），或者节点间没有高速 RDMA/NVLink 互连，那么单池开启 **Chunked Prefill + Prefix Caching** 不仅架构简单得多，端到端延迟反而更低。P/D 分离真正大放异彩的是**长上下文（如 Agent / RAG）、高并发且对 TTFT 与 TPOT 双重尾延迟有严苛 SLO 的中大型集群**。
- **误区二：“在做 KV-Aware 路由时，永远应该把请求强制发给前缀缓存命中率最高的那台机器（100% Sticky Routing）。”**
  事实：如果某个热门公共知识库或 Agent 模板的请求全部涌向已经缓存了该前缀的唯一一台机器 `Worker-0`，这台机器的排队延迟（Queueing Delay）会呈指数级飙升，远超在其他空闲机器上重新计算一次 Prefill 的耗时（即形成**缓存热点雪崩 Hot-Spot Stampede**）。因此 KV-Aware 路由必须将“省下的 Prefill 计算时间”与“目标机器的实时队列等待时间”放在同一个代价函数中动态权衡，必要时主动将流量溢出到次优机器实现缓存预热与分流。
- **误区三：“推算集群能跑多少并发长文本会话时，所有模型都可以套用 `2 * layers * kv_heads * head_dim * bytes` 这个标准公式。”**
  事实：该公式仅适用于标准 MHA/GQA 架构。现代旗舰模型普遍采用 **多头潜在注意力（MLA）**、**局部滑动窗口层 + 少量全局注意力层（Sliding-Window Hybrid）** 或 **线性注意力（Linear Attention / Gated DeltaNet）+ 稀疏注意力混合架构**，其每 Token 的 KV 显存占用可能比同参数量的标准 GQA 模型小一到两个数量级，且混合滑动窗口架构需要推理引擎具备专门的分支点状态缓存支持（如 SGLang 的 Sliding-Window-Aware Radix Cache）才能正确命中前缀缓存。

---

## 参考

- 选题线索：[ombharatiya/ai-system-design-guide, 04-inference-optimization/04-batching-strategies.md](https://github.com/ombharatiya/ai-system-design-guide/blob/ed955b27d94201b663a741284767a1136dc83e5e/04-inference-optimization/04-batching-strategies.md)、[02-kv-cache-and-context-caching.md](https://github.com/ombharatiya/ai-system-design-guide/blob/ed955b27d94201b663a741284767a1136dc83e5e/04-inference-optimization/02-kv-cache-and-context-caching.md) 与 [06-serving-infrastructure.md](https://github.com/ombharatiya/ai-system-design-guide/blob/ed955b27d94201b663a741284767a1136dc83e5e/04-inference-optimization/06-serving-infrastructure.md)。固定 commit `ed955b27`，独立拓展改编。
- Zhong et al., [DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving](https://arxiv.org/abs/2401.09670)，OSDI 2024：Prefill-Decode 干扰分析、Goodput 优化建模、异构并行策略解耦与带宽感知实例放置。
- Patel et al., [Splitwise: Efficient Generative LLM Inference Using Phase Splitting](https://arxiv.org/abs/2311.18677)，ISCA 2024：基于阶段算术强度差异的异构硬件池化与逐层流水线 KV 传输。
- Agrawal et al., [Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve](https://arxiv.org/abs/2403.02310)，OSDI 2024：分块预填充（Chunked Prefill）与无停顿捎带解码（Stall-Free Piggybacking）机制及边界。
- vLLM、SGLang 与 NVIDIA Dynamo 官方文档：Disaggregated Serving KV Connectors（NIXL / LMCache / Mooncake）、分层 KV 卸载（HiCache / Tiered KV Offloading）、跨租户 `cache_salt` 隔离与 KV-Aware 路由器设计。

来源访问与示例核验日期：**2026-10-30**。仅执行标准库 KV Cache 传输带宽核算、加盐前缀块哈希与 KV-Aware 路由旁路决策验证，未运行多节点 GPU RDMA 集群实测基准。
