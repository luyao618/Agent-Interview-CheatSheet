---
id: llm-0016
title: 部署量化模型时怎样估算内存与吞吐，为什么 MoE 的激活参数量不能直接当显存需求？
category: llm
tags: [quantization, memory-budget, kv-cache, moe, inference]
difficulty: medium
role: engineer
contributor: 佚名
source: 洛小山《AI 产品从入门到精通》learn-ai（固定版本见参考）
status: published
updated: 2026-09-15
answers:
  - author: GPT-6
    type: ai
    model: GPT-6
    answered: 2026-09-15
    updated: 2026-09-15
---

## 问题

部署量化模型时怎样估算内存与吞吐，为什么 MoE 的激活参数量不能直接当显存需求？请对同一模型计算 FP16/INT4 权重下限，再加入上下文、并发及运行时开销，说明估算的适用边界。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**先算需要驻留的数据，再算运行期间的峰值，最后在目标硬件上验证速度。** `参数量 × 位宽 / 8` 只是按指定编码保存权重数值的原始字节数下限；部署还需要量化元数据、KV Cache、临时张量和运行时内存。MoE 每个 token 只计算部分专家，不代表其他专家权重可以从内存预算中删除。

### 1. 位宽降低了什么，又没有降低什么

以均匀仿射量化为例，`q = clip(round(w / scale) + zero_point)`，重建值为 `w_hat = scale × (q - zero_point)`；对称量化可以不存独立 zero point。分组、舍入、裁剪和异常值处理会影响误差。4 bit 有 16 种编码，但 INT4、NF4 和不同混合精度格式并非同一种数值表示。

FP16/BF16 每个数占 2 bytes，4-bit 权重理想打包后平均占 0.5 bytes；**weight-only INT4 不等于激活、KV Cache 和全部计算都变成 INT4**。例如 W4A16 表示权重 4 bit、激活 16 bit，内核可能在计算过程中解码权重。量化误差可能改变输出，应在任务保留集上比较 FP16/BF16 与量化版本，不能仅凭权重误差或位宽承诺准确率。

量化和蒸馏的区别见 [llm-0015](llm-0015-knowledge-distillation-tradeoffs.md)；本题聚焦部署账本，不复写开闭源选型，相关讨论见 [llm-0002](llm-0002-open-source-vs-closed-source-models.md)。

### 2. 分项建立内存账本

| 项目 | 基本估算 | 需要核对的边界 |
| --- | --- | --- |
| 权重数值 | 对实际驻留的参数按位宽求和；统一位宽时为 `ceil(P × bits / 8)` bytes | 混合精度层、共享权重是否复用、分片与副本；文件大小也可能含容器头、对齐和其他数据 |
| 量化元数据 | 每个量化组的 scale、zero point、码本等，加上补齐或布局开销 | 分组通常按张量/行进行，应分别取整；不能总是对全模型参数除一次 group size。某些层保留高精度 |
| KV Cache | 按各层 K/V 的真实形状、dtype 和驻留 token 数计算 | GQA/MQA 的 KV head 数、生成长度、并发、beam、前缀共享、滑动窗口和缓存量化 |
| 激活与 workspace | prefill、decode、反量化和算子临时张量的阶段峰值 | Prefill 的临时峰值可能大于稳定 decode；attention 内核、分块和 graph capture 会改变占用 |
| 引擎与余量 | 运行上下文、allocator、内存池、调度/通信缓冲，以及预留空间 | allocated 与 reserved 口径不同，避免重复加同一内存池；系统/其他进程占用要从可用预算扣除 |

更准确的表达是 `M_peak = max_t [M_weights + M_KV(t) + M_workspace(t) + M_engine(t)]`，加载期间的转换或双份权重也要纳入峰值观察；预算再加明确的安全空间。各组件的最大值未必同时出现，简单求和可用于保守规划，但不能替代测量。纯推理通常不需要训练用梯度和优化器状态，也不要把训练显存公式直接搬过来。

磁盘 checkpoint、CPU RAM、独立 GPU 显存是不同账本。统一内存机器上 CPU/GPU 共享同一物理池，也不能把系统可用内存和 GPU 限额当两份容量相加；可用量、系统保留和运行时限制要按实际设备读取，不能固定假定所有机器都有某个可分配比例。

### 3. KV Cache 为什么会随上下文和并发增长

对普通 full-attention decoder、各层配置相同、K/V 维度相同且不共享前缀的情况：

```text
M_KV = 2 × L × H_kv × d_head × bytes_cache × Σ_i S_i
```

这里 `2` 代表 K 和 V，`L` 是层数，`H_kv` 是 KV heads 数，`d_head` 是每头维度，`S_i` 是第 i 条序列当时保留的 token 数。`S_i` 包含已处理的 prompt 和已缓存的生成 token；规划最大长度时应覆盖预计输出空间。各序列等长时 `Σ_i S_i = B × S`，`B` 指实际驻留缓存的序列数，不是排队请求总数。Beam 等解码方式还可能产生多份分支缓存。

GQA 中多组 query heads 共享 K/V，MQA 通常只有一组 K/V，所以不能直接用 query heads 代替 `H_kv`。KV Cache 保存的内容及 prefill/decode 边界见 [llm-0010](llm-0010-causal-attention-architecture.md)。降低权重位宽不会自动降低 `bytes_cache`；KV 量化需要单独的内核支持、元数据预算和质量验证。

这条公式给的是**逻辑缓存数值大小**。实际引擎可能按最大长度预分配，或按固定 token block 向上取整；前缀共享可减少物理副本，写时复制又会增加副本，allocator 还可能保留空闲池。PagedAttention 主要改善分配与共享，并不会让每条独立上下文的 K/V 信息凭空消失。滑动窗口、MLA、混合 attention 层或 K/V 不同形状要按实际缓存结构逐层求和，不能盲套此式。

### 4. 同一假想模型的 FP16 / INT4 算例

以下是**自编容量规划数据，不对应某个真实模型或显卡实测**：

- 模型恰有 `8,000,000,000` 个参数；同一组权重比较全 FP16 与全 INT4。INT4 使用人工设定的对称分组格式：每 128 个权重配一个 FP16 scale（2 bytes），无 zero point；最后一组补齐。主算例恰好整除，无额外对齐、码本、副本或高精度层。这不是某个 GGUF/GPTQ 格式的规格。
- `L=32`、`H_kv=8`、`d_head=128`，两种权重精度均用 FP16 KV Cache；full attention，无前缀共享、beam、offload 或多卡切分。只按已保留 token 数计算，无额外静态预分配。
- 可供这个推理进程规划的设备预算为 **16 GiB**。暂以 **1.5 GiB** 代表该场景的全部非权重/非 KV 运行时开销，另留 **1 GiB** 空间；二者都是人工预算假设，必须用加载与运行峰值替换，不能外推到任意上下文或 batch。
- 单位：`1 GB = 10^9 bytes`，`1 GiB = 2^30 bytes`；参数量中的 B 表示十亿，与并发符号 B 不同。

原始权重下限：FP16 为 `8e9 × 2 = 16e9 bytes = 16 GB ≈ 14.901161 GiB`；INT4 为 `8e9 × 0.5 = 4 GB ≈ 3.725290 GiB`。INT4 的 scale 为 `8e9 / 128 × 2 = 125,000,000 bytes`，故此示意格式的权重与 scale 合计 **4.125 GB ≈ 3.841706 GiB**。

每个缓存 token 占 `2 × 32 × 8 × 128 × 2 = 131,072 bytes = 128 KiB`，得到：

| 驻留序列数 B × 每序列缓存长度 S | KV（GiB） | FP16 总规划（GiB） | INT4 含 scale 总规划（GiB） |
| --- | ---: | ---: | ---: |
| 1 × 4096 | 0.5 | 17.901161 | 6.841706 |
| 4 × 4096 | 2 | 19.401161 | 8.341706 |
| 4 × 8192 | 4 | 21.401161 | 10.341706 |
| 8 × 16384 | 16 | 33.401161 | 22.341706 |

总规划均包含上述 1.5 GiB 运行时项和 1 GiB 余量。FP16 权重本身小于 16 GiB，第一行仍超预算；INT4 在前几行满足这个假设预算，最后一行仍不满足。**“满足规划”不是已经验证能加载或稳定运行**：若实际 prefill 峰值、量化布局或预分配大于假设，需要重算。也不能因为 INT4 权重数值缩小到四分之一，就把整进程内存也除以四。

### 5. MoE：总参数决定哪些权重要存，激活参数只描述部分计算

把一组简化 MoE 参数写成 `P_total = P_shared + E × P_expert`、`P_active = P_shared + k × P_expert`：`E` 是专家数，`k` 是每 token 选中的专家数，共享项包括 attention 等始终参与的权重。真实模型应按层及实际专家大小分别求和。

假设共享参数 2B、8 个各 1B 的专家、每 token 选 2 个，则总参数 10B，激活参数 4B。若所有专家驻留同一设备，**只算原始 INT4 权重也要 5 GB，而不是按激活量得到的 2 GB**，两者都还未加 scale 和缓存。不同 token 会选择不同专家；不能因为当前 token 没选中某个专家，就默认它不需要存储。

Expert parallel 或其他切分可以把权重分布到多卡，offload 可以把部分专家放到 CPU RAM；这改变的是每个设备的驻留位置和传输需求，不是把整个模型缩成激活参数量。每卡还可能有共享层副本、KV、路由与通信缓冲，不能简单把全模型预算除以卡数。

激活参数量有助于理解稀疏 FFN 的运算量，却不能直接推出“速度等于同参数稠密模型”。吞吐还取决于一批 token 触及多少专家、负载不均、路由与 all-to-all 通信、显存/互联带宽、内核效率和 attention 长度。MoE 的专家数也不是 KV Cache 的直接乘数：若专家位于 FFN，缓存仍由其 attention 结构决定。Mixtral 原论文提供了“每 token 选部分专家、不同 token 可选不同专家”的一手实例。

### 6. 吞吐只能先算约束，再做部署评测

Roofline 模型用计算能力和内存流量共同给出上界。对某一明确的执行步，在相同硬件层级与计数口径下，可写成 `t_step ≥ max(F_step / C_peak, Bytes_moved / BW_peak)`。这里的流量是穿过所讨论内存层级的实际数据量，不是 checkpoint 文件大小；缓存复用、batch 复用、反量化和多卡通信都会改变它。

一个**单请求 decode 的人工上界示例**：假定每生成一个 token 都从设备内存读一次完整稠密权重，INT4 连同 scale 一起读，带宽上限假设为 **200 GB/s**，忽略 KV 读取、计算、调度与其他开销。FP16 读权重至少 `16 GB / 200 GB/s = 80 ms`，仅此约束下最多 `12.5 token/s`；INT4 至少 `4.125 / 200 = 20.625 ms`，最多约 `48.485 token/s`。这是指定假设下的读权重时间下界和速度上界，**不是实测速度或保证的加速比**；不能把它用于有权重复用的 batch 或专家稀疏访问而不重算流量。

Prefill 可并行处理已知 prompt，常能提高矩阵计算利用率；小 batch decode 常受权重/KV 访问约束，长上下文 attention 或其他算子也可能成为瓶颈。提高并发可能增加整体 output token/s，却同时增加缓存、排队及单请求延迟。量化还可能受反量化或硬件内核限制，不能只看 GPU 理论算力或文件体积选型。

下面原样运行可复算容量与带宽示例。代码只进行整数/Fraction 算术，没有分配模型权重、加载量化内核或执行 GPU benchmark：

```python
from fractions import Fraction as F

GB, GiB = 10**9, 2**30

def nonnegative_int(value):
    if type(value) is not int or value < 0:
        raise ValueError("nonnegative integer required")

def ceil_div(n, d):
    nonnegative_int(n)
    if type(d) is not int or d <= 0:
        raise ValueError("positive divisor required")
    return (n + d - 1) // d

def packed_bytes(params, bits):
    if type(bits) is not int or bits <= 0:
        raise ValueError("positive bit width required")
    nonnegative_int(params)
    return ceil_div(params * bits, 8)

def grouped_int4_bytes(params, group=128, scale_bytes=2):
    nonnegative_int(scale_bytes)
    groups = ceil_div(params, group)
    # 此示意格式将最后一组补齐，再存每组一个 scale，无 zero point。
    return packed_bytes(groups * group, 4) + groups * scale_bytes

def kv_bytes(lengths, layers=32, kv_heads=8, head_dim=128, cache_bytes=2):
    for value in (layers, kv_heads, head_dim, cache_bytes):
        if type(value) is not int or value <= 0:
            raise ValueError("positive cache dimensions required")
    for length in lengths:
        nonnegative_int(length)
    return 2 * layers * kv_heads * head_dim * cache_bytes * sum(lengths)

params = 8_000_000_000
fp16 = packed_bytes(params, 16)
int4_min = packed_bytes(params, 4)
int4_stored = grouped_int4_bytes(params)
for name, size in (("FP16", fp16), ("INT4_raw", int4_min), ("INT4_with_scales", int4_stored)):
    print(f"{name}: bytes={size}, GB={size / GB:.3f}, GiB={size / GiB:.6f}")

# 人工预算：运行时项 1.5 GiB，另留 1 GiB 安全空间；并非实测。
runtime, headroom, capacity = 3 * GiB // 2, GiB, 16 * GiB
for batch, length in ((1, 4096), (4, 4096), (4, 8192), (8, 16384)):
    cache = kv_bytes([length] * batch)
    totals = [w + cache + runtime + headroom for w in (fp16, int4_stored)]
    flags = [total <= capacity for total in totals]
    print(f"B={batch}, S={length}: KV={cache / GiB:.3f} GiB, "
          f"FP16={totals[0] / GiB:.6f}, INT4={totals[1] / GiB:.6f}, within_plan={flags}")

# 单请求、每步读权重一次，假设带宽上限 200 GB/s，忽略其他耗时。
bandwidth = 200 * GB
for name, size in (("FP16", fp16), ("INT4_with_scales", int4_stored)):
    time_lower_bound = F(size, bandwidth)
    rate_upper_bound = 1 / time_lower_bound
    print(f"{name}: weight_read_ms>={float(time_lower_bound * 1000):.3f}, "
          f"tokens_per_s<={float(rate_upper_bound):.3f}")

# 另一假想 MoE：共享 2B，8 个各 1B 的专家，每 token 选 2 个。
total_params, active_params = 2 * GB + 8 * GB, 2 * GB + 2 * GB
print("MoE raw INT4 GB (total/active):",
      packed_bytes(total_params, 4) / GB, packed_bytes(active_params, 4) / GB)
```

**真实运行 stdout：2026-09-15，macOS arm64，Python 3.11.8。所有配置、带宽及余量均为示意假设。**

```text
FP16: bytes=16000000000, GB=16.000, GiB=14.901161
INT4_raw: bytes=4000000000, GB=4.000, GiB=3.725290
INT4_with_scales: bytes=4125000000, GB=4.125, GiB=3.841706
B=1, S=4096: KV=0.500 GiB, FP16=17.901161, INT4=6.841706, within_plan=[False, True]
B=4, S=4096: KV=2.000 GiB, FP16=19.401161, INT4=8.341706, within_plan=[False, True]
B=4, S=8192: KV=4.000 GiB, FP16=21.401161, INT4=10.341706, within_plan=[False, True]
B=8, S=16384: KV=16.000 GiB, FP16=33.401161, INT4=22.341706, within_plan=[False, False]
FP16: weight_read_ms>=80.000, tokens_per_s<=12.500
INT4_with_scales: weight_read_ms>=20.625, tokens_per_s<=48.485
MoE raw INT4 GB (total/active): 5.0 2.0
```

### 7. 从预算到上线，要补哪些实测

先固定 checkpoint、量化工具及格式版本、group size、敏感层精度、KV dtype、推理引擎/内核、设备和并行方式。读取实际张量清单与加载日志，区分权重驻留、缓存池和临时缓冲；观察加载、冷启动 prefill、长输出 decode、并发压力下的峰值，而不只看模型刚加载完的一次占用。

用同一输入/输出长度分布及任务保留集比较原精度、不同量化档位和必要的较小模型方案。记录质量、格式/工具调用正确率、OOM/失败率、TTFT、每输出 token 延迟（TPOT）、整体输出 token/s、请求延迟分位数，并注明并发、batch、排队、缓存命中和是否包含 prefill。硬件异步执行时要用正确的同步或事件计时，稳态吞吐与冷启动分开。

内存不够可以降低并发或上下文、采用受支持的 KV 量化、分片/offload，或换更小模型；这些方案分别付出容量、质量、通信、尾延迟或能力代价。仅受权重容量限制时 INT4 值得试；若关键质量回归无法接受，高一档精度或更小但较高精度的模型也是合理候选。没有跨模型、任务和硬件普适的“优先保尺寸”或“固定选 Q4”结论。

## 延伸 / 追问

**追问 1：4-bit 文件只有几 GB，为什么长对话仍会 OOM？**

权重量化没有自动压缩 KV；上下文和驻留序列增加后，KV 或 prefill 临时峰值可能占主导。检查 KV dtype、实际分配策略和峰值，再决定限长、限并发或使用受支持的缓存优化，不能再乘一个固定余量系数猜答案。

**追问 2：MoE 做了专家 offload，就能按激活参数规划 GPU 显存吗？**

需要按实际驻留与预取策略计算 GPU、CPU 和传输缓冲。激活参数只是某个 token 的计算子集，不等于引擎始终只保留这些权重；专家切换、batch 内专家集合以及传输重叠都会影响占用和吞吐。

**追问 3：并发翻倍，吞吐会翻倍吗？**

不会保证。权重复用和更大矩阵可能提高利用率，但 KV、队列、内核和通信也会增长。需要同时看整体吞吐、单请求延迟和内存峰值；满足显存预算只是实验的起点。

## 常见误区

- **“参数量乘固定精度系数就包含所有开销。”** 固定余量系数不是通用公式；模型结构、上下文、并发和引擎都影响预算。
- **“装得下就代表跑得快。”** 容量是存储约束，速度还受计算、带宽、内核、路由和通信限制。
- **“MoE 只需存激活参数，速度等于同激活量的稠密模型。”** 未激活专家仍需放在某处，稀疏计算也有调度和通信代价。
- **“INT4 会让 KV 与整个进程内存一起变为四分之一。”** 权重位宽与 KV dtype 分开；scale、保留高精度层和临时缓冲也不能省略。

## 参考

- 课程学习线索：洛小山《AI 产品从入门到精通》[learn-ai](https://github.com/itshen/learn-ai/tree/5a933d287dd5074cc1543cb849146f3261d47521)，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`；具体路径：[slides/oss-8.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/oss-8.html)、[slides/oss-9.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/oss-9.html)、[slides/zero-q-parameters.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/zero-q-parameters.html)。本文独立编写文字、表格与代码，未搬运 AGPL 素材；未将课程固定系数、硬件可用比例或工具偏好作为通用结论。
- Jacob et al., *Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference*, CVPR 2018，[正式论文](https://openaccess.thecvf.com/content_cvpr_2018/html/Jacob_Quantization_and_Training_CVPR_2018_paper.html)：量化表示及配套训练的一手依据；本文不移用其图像任务的性能收益。
- Ainslie et al., *GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints*, 2023，[arXiv:2305.13245v1](https://arxiv.org/abs/2305.13245v1)，§2 的 GQA/MQA 与 KV head 共享关系。
- Kwon et al., *Efficient Memory Management for Large Language Model Serving with PagedAttention*, 2023，[arXiv:2309.06180v1](https://arxiv.org/abs/2309.06180v1)：请求级 KV Cache、分块、共享和碎片管理；本文不承诺该论文的特定吞吐增益。
- Jiang et al., *Mixtral of Experts*, 2024，[arXiv:2401.04088v1](https://arxiv.org/abs/2401.04088v1)，§2 的专家路由与稀疏计算；本文 MoE 数字为另行构造的示例，不是 Mixtral 规格。
- Williams, Waterman & Patterson, *Roofline: An Insightful Visual Performance Model for Floating-Point Programs and Multicore Architectures*, [UCB/EECS-2008-134](https://www2.eecs.berkeley.edu/Pubs/TechRpts/2008/EECS-2008-134.html)，§3 的计算/带宽上界与内存流量口径。以上一手链接核实日期 **2026-09-15**。
