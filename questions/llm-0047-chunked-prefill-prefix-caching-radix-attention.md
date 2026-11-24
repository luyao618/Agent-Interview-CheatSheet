---
id: llm-0047
title: 分块预填充（Chunked Prefill / Sarathi-Serve）与自动前缀缓存（vLLM APC vs SGLang RadixAttention）是如何通过统一 Token 预算调度、链式块哈希与基数树前缀复用消除推理停顿并降低首字延迟的？
category: llm
tags: [chunked-prefill, prefix-caching, radix-attention, sarathi-serve, vllm, sglang]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开大模型推理系统源码导读与精读笔记（halfrost/Halfrost-Field 与 XiaYiHann/AIInfraGuide-ia-lab）扩展改编；Sarathi-Serve、SGLang 论文及 vLLM V1 / SGLang 官方源码核实（见参考）
status: published
updated: 2026-11-25
answers:
  - author: gemini-4-carbon
    type: ai
    model: gemini-4-carbon
    answered: 2026-11-25
    updated: 2026-11-25
---

## 问题

在多轮 Agent 工具调用、长文档 RAG 与高并发在线推理服务中，单实例大模型推理引擎同时面临两类核心性能痛点：一是超长 Prompt 到达时，整段预填充（Prefill）占满 GPU 数百毫秒至数秒，造成同批在途解码请求出现严重的**生成停顿（Generation Stall，即 TBT/ITL 尾延迟尖峰）**以及流水线并行（PP）微批次气泡；二是大量请求共享相同的 System Prompt、Tool Schema 或多轮历史轨迹，反复重算前缀 KV Cache 导致首字延迟（TTFT）与算力成本居高不下。现代工业级推理引擎（如 **vLLM V1** 与 **SGLang**）普遍通过 **分块预填充（Chunked Prefill / Sarathi-Serve）** 与 **跨请求前缀缓存（Automatic Prefix Caching, APC / RadixAttention）** 协同破局。请深入剖析以下三个核心问题：

1. **算术强度错配、Chunked Prefill 与无停顿预算调度（Stall-Free Batching）**：为什么从 GPU Roofline 模型来看，纯 Decode 批次天然受限于显存带宽（Memory-Bound）而存在大量空闲算力？Sarathi-Serve（OSDI 2024）与 vLLM V1 调度器是如何废除显式的“Prefill 阶段 / Decode 阶段”切换，改用单一全局 Token 预算（`max_num_scheduled_tokens`）与双游标缺口模型实现无停顿混合调度的？分块预填充在重复读取历史块 KV Cache、矩阵乘 Tile Quantization 对齐以及流水线并行气泡消除上有哪些定量权衡？
2. **vLLM V1 链式块哈希（APC）与 SGLang 基数树（RadixAttention）的底层架构对决**：vLLM V1 的 Automatic Prefix Caching 是如何通过链式滚动哈希 $h_i = H(h_{i-1}, \text{tokens}_{iB:(i+1)B}, \text{extra\_keys})$ 绑定完整前缀、多模态块内偏移与跨租户 `cache_salt` 的？为什么在缓存 $100\%$ 命中时仍必须强制设置 `max_cache_hit_length = num_tokens - 1`（甚至引发完整末块重算）？对比之下，SGLang 的 **RadixAttention（压缩前缀树 `RadixCache`）** 是如何通过动态边分裂（`_split_node`）、祖先链引用锁（`lock_ref`）与小根堆叶子逐级淘汰管理多分支 Agent 搜索树的，二者在数据结构复杂度与淘汰零开销设计上有何本质差异？
3. **复杂模型架构与生产级安全/基准边界**：在包含非因果注意力层、滑动窗口注意力（SWA）/ Mamba 混合状态模型、EAGLE/MTP 投机解码或跨进程 KV 传输（P/D 分离）的生产环境中，前缀缓存与分块预填充必须施加哪些正确性门控（如 `drop_eagle_block`、单调不动点交集对齐、Canonical CBOR + `PYTHONHASHSEED`）与安全防侧信道措施？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-carbon

> 🤖 AI 答案 · 模型：gemini-4-carbon · 回答 2026-11-25

**分块预填充（Chunked Prefill）与自动前缀缓存（APC / RadixAttention）分别从“单步计算预算的时间削峰填谷”与“跨请求历史状态的零重算空间复用”重塑了现代推理引擎内核：（1）在迭代调度层，纯 Decode 批每次仅每序列推进 $1$ 个 Token，权重从 HBM 搬运的开销无法分摊（算术强度远低于 GPU 峰值脊点），导致大量 Tensor Core 算力闲置；Sarathi-Serve 与 vLLM V1 废除了全局 Prefill/Decode 模态标签，用统一游标缺口 $\Delta_r = \text{num\_tokens\_with\_spec} - \text{num\_computed\_tokens}$ 度量需求，每步设定刚性预算 $\tau$（`max_num_scheduled_tokens`，且强制 $\tau \ge \text{max\_num\_seqs}$ 保证活性），优先扣减 `RUNNING` 队列的在途 Decode/Chunk，再以 `min(need, rem_budget)` 切分 `WAITING` 长 Prompt 搭车执行，将秒级生成停顿压平为受控的微秒/毫秒级均匀步长并消除 PP 流水线气泡；（2）在前缀复用层，vLLM V1 采用退化 Merkle 链式块哈希 $h_i = H(h_{i-1}, \text{tokens}, \text{extra\_keys})$ 配合 `ref_cnt` 与 `_block_hash` 正交解耦的侵入式双端空闲队列（无哈希残块前插队首优先回收、有哈希块逆序后插队尾使链尾先于链头淘汰），实现 $O(1)$ 零扫描延迟驱逐，并通过 `max_cache_hit_length = num_tokens - 1` 保证至少 $1$ 个末尾位置前向产出下步采样 Logits；而 SGLang `RadixCache` 以页对齐压缩前缀树显式维护树状分支拓扑，借动态边分裂（`_split_node`）、沿父链递增 `lock_ref` 保护在途共享前缀、按时间戳小根堆自底向上裁剪 `lock_ref == 0` 叶子，天然契合 ToT/Agent 多分支树搜索；（3）在工程正确性边界上，引擎对非因果注意力强制关闭缓存与切块，对 Hybrid（Full + SWA/Mamba）模型通过单调递减不动点求各 KV Group 命中交集，对 EAGLE 投机解码回退末个命中块（`drop_eagle_block`）重算隐状态，并通过首块注入租户专属 `cache_salt` 阻断跨租户时序侧信道探测。**

在深入拆解调度方程与源码数据结构前，建议结合题库内已有题目串联上下游知识脉络：关于 Prefill 与 Decode 两阶段 KV Cache 的基础物理含义与内存压力，请参阅 [llm-0018](llm-0018-kv-cache-prefill-decode.md)；关于模型权重与 KV 显存容量的静态核算方法，请参阅 [llm-0016](llm-0016-quantization-local-memory-budget.md)；关于多 Token 预测（MTP）与 EAGLE 特征层自回归草稿头为何依赖最后一层隐状态，请参阅 [llm-0037](llm-0037-mtp-medusa-eagle-tree-speculative.md)；关于单序列超长上下文跨多卡切分的序列并行（Ring Attention / Ulysses），请参阅 [llm-0033](llm-0033-ring-attention-ulysses-sequence-parallelism.md)；关于 Agent 侧如何组织 ReAct 历史轨迹以降低上下文开销，请参阅 [agent-0039](agent-0039-react-trajectory-context-cost.md)；关于服务端队列积压失衡时的宏观背压机制，请参阅 [engineering-0021](engineering-0021-llm-queue-backpressure.md)。

---

### 1. 算术强度错配、Chunked Prefill 与 vLLM V1 统一预算调度

#### 1.1 Roofline 视角：为什么 Decode 批次可以“免费搭车” Prefill 块？

设单层线性投影权重矩阵参数量为 $W$（以 BF16 存储占 $2W$ 字节），当一次前向传播打包处理的总词元数为 $T_{\text{batch}}$ 时，矩阵乘（GEMM）的计算量为 $2 T_{\text{batch}} W$ FLOPs，从高带宽显存（HBM）读取权重的访存量约为 $2W$ 字节，其算术强度（Arithmetic Intensity）满足：

$$\mathcal{I}(T_{\text{batch}}) \approx \frac{2 T_{\text{batch}} W}{2W + \text{Act\_IO}} \approx T_{\text{batch}} \;\; (\text{FLOPs / Byte})$$

在现代 GPU 上（如 A100 BF16 算力 $312\text{ TFLOPs}$、HBM 带宽 $\sim 1.5\text{-}2.0\text{ TB/s}$，理论算力脊点 Ridge Point 约在 $156 \sim 200$ Token；H100 FP8/BF16 及高张量并行度 TP 下实测饱和拐点更推高至 $256 \sim 600$ Token）：
- **纯 Decode 迭代的算力饥饿**：即便并发跑 $B = 32$ 条 Decode 序列，总词元数也仅有 $T_{\text{batch}} = 32 \ll 200$，完全落在 **Memory-Bound（内存带宽受限）** 斜坡区——耗时主要由搬运整套模型权重的固定底噪（如 $\sim 12\text{ ms}$）决定，Tensor Core 大部分周期在空等数据；
- **整段 Prefill 插队的灾难（Generation Stall）**：传统 Prefill-Prioritizing 调度一旦看到空闲显存，就把一条 $4096$ 甚至 $32\text{K}$ Token 的新请求整段塞入一次迭代，导致单步耗时骤增数十倍（Sarathi-Serve 论文 Fig.9 实测朴素混合批相对纯 Decode 批使 TBT 暴涨最高达 $28.3\times$），打断所有正在流式输出的在线会话。
- **Piggybacking（搭车效应）**：只要将长 Prompt 切成小块，填满预算缺口 $\tau - B_{\text{decode}}$ 使其恰好逼近硬件 Roofline 拐点，就能在不显著推高单步耗时的前提下“白捡”原本闲置的线性层算力。

#### 1.2 vLLM V1 的双游标缺口模型与无相位（Phase-Agnostic）预算裁剪

对照 `vllm/v1/core/sched/scheduler.py` 源码，现代引擎彻底移除了 `is_prefill_stage` 之类的全局切换状态机。每个请求仅维护两个单调推进的游标：已算出 KV 的 `num_computed_tokens`（记为 $c_r$）与目标总长 `num_tokens_with_spec`（记为 $g_r = L_{\text{prompt}} + L_{\text{out}} + L_{\text{spec}}$）。四种推理行为在算术上坍缩为同一个缺口 $\Delta_r = g_r - c_r$：
- **Full Prefill**：$c_r = 0 \implies \Delta_r = L_{\text{prompt}}$；
- **Chunked Prefill**：上一轮只算完部分块，$0 < c_r < L_{\text{prompt}} \implies \Delta_r = L_{\text{prompt}} - c_r$；
- **Prefix Cache Hit**：准入前探测命中长度 $P$，直接快进 $c_r \leftarrow P \implies \Delta_r = L_{\text{prompt}} - P \ge 1$；
- **Standard / Speculative Decode**：$\Delta_r = 1$（或 $1 + k_{\text{draft}}$）。

每轮 `schedule()` 初始化共享标量预算 `token_budget` $= \tau$（`max_num_scheduled_tokens`），按严格的两阶段顺序扣减：
1. **Phase A（优先保障 `RUNNING`）**：按 FCFS 扫描已在途的 Decode 与未完结 Prefill Chunk，通过三级裁剪链确定本步分配量 $a_r = \min(\Delta_r, \text{long\_prefill\_token\_threshold}, \text{token\_budget})$；若 `allocate_slots` 因 KV 物理块耗尽返回 `None`，触发尾部受害者抢占（Preemption）并退还其本步已扣预算；
2. **Phase B（剩余预算准入 `WAITING`）**：先执行只读前缀缓存探测调高 $c_r$，再以**一行核心截断 `num_new_tokens = min(num_new_tokens, token_budget)`** 自然完成长 Prompt 切块！注意配置层强制校验活性不变量 **`max_num_batched_tokens >= max_num_seqs`**：若预算 $\tau$ 小于最大并发序列宽度，排在队尾的活跃序列将永远分不到哪怕 $1$ 个 Decode Token 而陷入死锁饥饿；同时在 Phase B 若 KV 块不足，调度器直接 `break` 退出等待循环，**绝不为了接纳新请求而抢占已在途的运行任务**。

#### 1.3 切块粒度权衡：KV 重复访存、Tile Quantization 与 PP 气泡消除

把长 $L$ 的 Prompt 均分为 $N = \lceil L / C \rceil$ 个块（每块长 $C$）并非越碎越好：
1. **历史块 KV 重复 HBM 读取开销**：计算第 $m$ 块（$m \in \{1, \dots, N\}$）与前序块的因果注意力时，第 $1$ 块的 KV 会被重读 $N-1$ 次，总额外 KV 读取字节数正比于 $\sum_{m=1}^{N-1} m C = \frac{N(N-1)}{2} C \approx \frac{L^2}{2C}$。但正如 Sarathi-Serve（`arXiv:2403.02310` §4.3 & Fig.14）实测所示，长序列线性层与 Prefill Attention 总体受算力主导，$C = 2048$ 时端到端 Prefill 耗时几乎零折损，$C = 512$ 时最多增加约 $25\%$，换取在途 Decode P99 TBT 严格受控；
2. **GPU 矩阵乘分块量化灾难（Tile-Quantization Effect）**：GPU Tensor Core 按固定 Tile（如 $64$、$128$ 或 $256$ 行）分派 Thread Block。若预算扣除在途 Decode 后切出的块长落在 **“差一点对齐”的尴尬值（如 $257$ vs $256$）**，多出的 $1$ 个 Token 会迫使硬件额外启动整整一轮几乎全空的 Tile 波次，论文实测仅多 $1$ 个 Token 就使单块耗时激增 **$32\%$**！工程调优必须让预算 $\tau$ 与常用块长对齐 $64/128/256$ 边界；
3. **跨节点流水线并行（PP）气泡消除**：在跨节点百吉比特以太网部署超大模型（如 Falcon-180B TP4-PP2）时，未切块前 $4\text{K}$ Prefill 微批次（$\sim 1150\text{ ms}$）与 Decode 微批次（$\sim 200\text{ ms}$）交错会产生高达 $950\text{ ms}$ 的流水线空转气泡；统一预算 $\tau$ 将所有微批次执行时间方差大幅抹平，使商品化网络上的 PP 吞吐容量显著释放。

---

### 2. 前缀缓存双雄：vLLM 链式块哈希（APC）vs SGLang 基数树（RadixAttention）

当多个请求共享前 $P$ 个前缀词元时，因果注意力（Causal Mask）保证了位置 $[0, P)$ 的隐状态与 KV 张量仅依赖前序输入，与位置 $[P, N)$ 的后缀完全无关。vLLM V1 与 SGLang 选择了两种截然不同的索引与内存生命周期哲学：

| 对比维度 | vLLM V1 Automatic Prefix Caching (APC) | SGLang RadixAttention (`RadixCache`) |
| :--- | :--- | :--- |
| **核心索引结构** | 扁平哈希表 `BlockHashToBlockMap`（键为链式块摘要 + 4B `group_id`） | 压缩前缀树（Radix Tree，边存储变长页对齐 `RadixKey` 与设备 KV 索引切片） |
| **匹配粒度与查找** | 严格按固定物理块长 $B$（如 $16$ Token）顺序查表，遇首次 Miss 立即 `break` | 树向下跳转 + 边内指数倍增搜索（Galloping + 二分）定位首个分歧点并按 `page_size` 向下对齐 |
| **动态分支拓扑处理** | 无需分裂节点；相同完整块自然算出相同链式哈希，未满块无法共享 | 遇部分边匹配自动触发 `_split_node` 原地裂边，并在 `checkpoint` 时用 `split_prompt` 切开输入与输出 |
| **活跃保护与淘汰机制** | `ref_cnt` 与 `_block_hash` 正交解耦；侵入式双向链表 `FreeKVCacheBlockQueue` 实现 **$O(1)$ 零扫描延迟淘汰** | 沿叶到根递增祖先 `lock_ref` 锁死在途前缀；缺内存时对 `lock_ref == 0` 叶子建小根堆 **$O(K \log |\mathcal{L}|)$ 级联裁剪** |
| **并发重复写入策略** | **不主动去重（No De-dup）**：单键碰撞原地升级为 `{block_id: block}` 字典，保证块表 Append-Only | 插入完成（`_insert_cache`）后主动比对已驻留前缀并调用 `free_segment` **立即回收重复分配的物理槽位** |

#### 2.1 vLLM V1 链式块哈希：密码学前缀承诺、`num_tokens - 1` 铁律与双端队列淘汰

对照 `vllm/v1/core/kv_cache_utils.py`、`kv_cache_manager.py` 与 `block_pool.py`：
1. **退化 Merkle 链式滚动哈希**：第 $i$ 个完整块（覆盖 $[iB, (i+1)B)$，尾部不足 $B$ 个 Token 的残块绝不计算哈希）的键由三元组递推生成：
   $$h_0 = H\big(\text{NONE\_HASH},\; \text{tokens}_{0:B},\; e_0\big), \qquad h_i = H\big(h_{i-1},\; \text{tokens}_{iB:(i+1)B},\; e_i\big)$$
   其中根种子 `NONE_HASH` 在未指定 `PYTHONHASHSEED` 时取 `os.urandom(32)` 防碰撞攻击；附加键 `extra_keys` $e_i$ 按固定顺序拼接 `(lora, mm, cache_salt, prompt_embeds)`——尤其是多模态输入必须编码 **`(mm_feature.identifier, offset - start_token_idx)`**（因为不同图片的视觉占位符 Token ID 完全相同，且同一张图在块内偏移不同会产出不同旋转位置编码 KV）。由于 $h_{i-1}$ 嵌套在原像内部，$h_i$ 构成了对整个前缀 $[0, (i+1)B)$ 的传递承诺，一旦第 $k$ 块未命中，后续块绝无命中可能，扫描可立即终止。
2. **为什么 $100\%$ 缓存命中时仍强制 `max_cache_hit_length = request.num_tokens - 1`？**
   若允许全部 $N$ 个 Prompt Token 直接命中缓存，首轮前向传播将调度 $0$ 个新 Token，模型根本无法在最后一个位置执行前向计算以产出用于采样第一个生成词的 **Next-Token Logits**！更微妙的块对齐次生效应在于：因为 `allocate_slots` 要求已计算长度按 `block_size` $B$ 整数倍对齐，当重复请求的 Prompt 长度**恰好是块大小的整数倍**（如 $N = 2B = 32, B = 16$）时，`max_length // B = (32 - 1) // 16 = 1`，会导致**整个最后一个完整块（16 个 Token）被迫重算**，而非仅重算最后 1 个 Token！这也是 vLLM 按 Token 统计的 `PrefixCacheStats` 命中率上限只能无限趋近 $100\%$ 却永不等于 $100\%$ 的源码根源（同时被抢占请求重入的自命中会被单独路由到 `preempted_hits` 桶，防止虚增真实跨请求命中率）。
3. **正交生命周期与双端 `FreeKVCacheBlockQueue` 的零成本 LRU**：
   物理块同时携带分配引用计数 `ref_cnt` 与缓存身份 `_block_hash`。当请求结束释放块列表时，`single_type_kv_cache_manager.py` 先将块按**逆序（`reversed`，即链尾在前、链头在后）**传入 `free_blocks`：
   - 当 `ref_cnt` 归零后，若 `block_hash is None`（未填满尾块，永远不可能被 APC 命中），调用 `prepend_n` 插到空闲队列**最前端**，下次分配最先覆写回收；
   - 若 `block_hash is not None`，调用 `append_n` 追加到空闲队列**最末端（MRU）**，块继续留在哈希表中处于 `ref_cnt == 0 ∧ _block_hash != None` 的“空闲但可命中”态；且由于逆序入队，**复用概率最低的序列尾部块自然排在序列头部块（如公共 System Prompt）之前被淘汰**；唯有当新分配真正 `popleft_n` 弹出该块时，才惰性触发 `_maybe_evict_cached_block` 抹除哈希并发送淘汰事件，全程 $O(1)$ 无任何后台扫描或时间戳堆开销。

#### 2.2 SGLang RadixAttention：动态裂边、指数倍增匹配与自底向上级联驱逐

对照 `sglang/srt/mem_cache/radix_cache.py` 源码，SGLang 面向复杂结构化程序（Few-Shot 分支、Self-Consistency 采样、多轮 Agent 树）将所有历史序列的输入**与生成输出**统一维护在一棵基数树中：
1. **无拷贝指数搜索（Exponential Search）与动态裂边（`_split_node`）**：树边存储变长词元序列 `RadixKey`。匹配时，`RadixKey.match_at` 不做逐词元 Python 循环，而是以 $1, 2, 4, 8, \dots$ 倍增窗口做底层数组切片比较，定位分歧窗口后再二分查找首个分歧词元；若分歧点落在某条树边内部（`0 < prefix_len < len(child.key)`），`_split_node` 立即创建中间父节点承接公共前缀切片并**继承子节点的 `lock_ref` 与优先级**，使共享拓扑按需生长；在 `checkpoint(..., split_prompt=True)` 时还会特意在 Prompt 末尾边界处预切一刀，允许后续内存紧张时只淘汰该轮生成的回答而保留宝贵的 Prompt 前缀。
2. **祖先锁链保护（`inc_lock_ref`）与小根堆叶子级联淘汰（`evict`）**：在途请求通过 `inc_lock_ref` 从挂载节点一路向根遍历递增全部祖先的 `lock_ref`，将这些节点的词元数从 `evictable_size_` 划入 `protected_size_`。当显存不足需回收 `num_tokens` 时，`evict()` 仅收集当前所有 `children` 为空且 `lock_ref == 0` 的可驱逐叶子建立最小堆（按 `last_access_time` 或策略优先级），每次弹出最旧叶子释放物理页；**一旦某叶子被删后其父节点变成了新的无锁孤叶（`len(parent.children) == 0 and parent.lock_ref == 0`），立即将该父节点动态推入同一个淘汰堆**，从而实现精确按 Token 需求量的自底向上剪枝，绝不误伤任何活跃分支正在依赖的公共树干。
---

### 3. 混合注意力/投机解码边界与生产级安全隔离

把分块预填充与前缀缓存推向现代异构基座与多租户生产环境时，源码中还埋设了五道极易在面试深水区被追问的正确性与安全闸门：

1. **非因果层（Non-Causal Attention）硬熔断与写入四重漏斗**：
   前缀缓存与分块预填充的数学基石都是位置 $i$ 的 KV 不依赖位置 $j > i$。对于 Encoder-Decoder 跨注意力或含双向注意力层的视觉/多模态混合模型，vLLM V1 在 `engine/core.py` 检测到 `non_causal=True` 时会**强制关闭 Prefix Caching**，在 `config/scheduler.py` 中对 Encoder-Decoder 强制令 `enable_chunked_prefill = False`。同时，写入缓存路径（`cache_blocks`）严格执行四重过滤：**排除未确认的投机草稿词元**（上限截断于 `request.num_tokens` 而非 `num_tokens_with_spec`，杜绝草稿被拒后遗留脏别名）、向下取整至完整块、跳过稀疏/滑动窗口产生的 `is_null` 空洞块、以及在远端 KV 异步拉取未落地前通过 `delay_cache_blocks` 延迟发布。
2. **Hybrid 混合架构（Full Attention + SWA / Mamba）的单调不动点交集与 Bigram 键**：
   当模型交错堆叠全注意力层与滑动窗口（SWA）或线性状态层（Mamba）时，不同层的有效驻留窗口不同——不能只从缓存恢复半套网络层！vLLM V1 引入带 4 字节大端 `group_id` 的复合键 `BlockHashWithGroupId`，并通过 `HybridKVCacheCoordinator` 执行**单调递减不动点迭代（Monotonic Decreasing Fixed-Point）**：全注意力组向下闭合只需探测一次，SWA/Mamba 组反复向更短公共边界修剪，直到所有 KV Group 对齐在同一个合法的 `scheduler_block_size` 交集游标上；而对于 EAGLE 投机解码，读取端启用 `drop_eagle_block` 主动回退弹出最后一个命中块以重算 Draft Head 所需的最后一层 Hidden States（SGLang `RadixKey` 则通过 `is_eagle -> is_bigram=True` 将单 Token 视图切换为相邻二元组 `(t[i], t[i+1])` 视图保证特征对齐）。
3. **跨进程确定性序列化（Canonical CBOR + `PYTHONHASHSEED`）与跨租户侧信道防御（`cache_salt`）**：
   - 在跨节点 KV 路由或二级存储卸载（Offloading）中，Python 默认 `pickle` 编码随版本波动且未设 `PYTHONHASHSEED` 时每个进程会用 `os.urandom(32)` 生成互异的 `NONE_HASH` 根，导致跨进程哈希完全失配；因此生产跨进程复现必须显式选用 `sha256_cbor` / `xxhash_cbor` 规范编码并固定 `PYTHONHASHSEED`；
   - **时序侧信道风险**：在公有云多租户共享池中，若攻击者构造候选敏感前缀探测 TTFT 是否骤降，即可通过缓存命中时延反推其他租户是否刚输入过该私有文档或提示词！vLLM 与 SGLang 均支持请求级 **`cache_salt`**：vLLM 将其注入第 $0$ 块（`start_token_idx == 0`）的 `extra_keys`，凭借哈希链雪崩效应低成本隔离整条前缀链；SGLang 则在 `RadixKey` 子节点字典键上前置 `(extra_key, cache_salt)` 命名空间元组，彻底阻断跨租户树节点共享。

```
统一预算调度 + 前缀缓存协同数据流（单步 Iteration）：

 新请求 (Prompt N toks, cache_salt)
   │  1. 链式块哈希 / RadixTree 探测 (上限 N-1, EAGLE 额外回退末块)
   ▼
 命中前缀 P toks (直接复用物理块, touch 摘出 FreeQueue / inc_lock_ref 锁祖先)
   │  2. 剩余待算缺口 need = N - P >= 1
   ▼
 共享标量预算 token_budget = max_num_scheduled_tokens (>= max_num_seqs)
   ├─► Phase A [RUNNING 优先]: 先扣减所有在途 Decode (各 1 tok) 与在途 Chunk (缺块则抢占队尾)
   └─► Phase B [WAITING 搭车]: take = min(need, rem_budget) ──► 切块混入同一轮 Forward Pass!
```

---

### 4. 可运行 Python 3 标准库仿真：无停顿分块调度、APC 哈希链与 RadixCache 裂边淘汰

下面的自包含脚本仅使用 Python 3 标准库（`hashlib`、`heapq`、`dataclasses`、`typing`），端到端复现并校验了：（1）整段抢占 Prefill 造成的近 $200\text{ ms}$ 生成停顿 vs 统一预算分块调度的 TBT 削峰；（2）vLLM V1 链式块哈希的 `cache_salt` 雪崩隔离、$100\%$ 重复请求因 `num_tokens - 1` 触发的完整末块重算，以及双端空闲队列“无哈希尾块最先回收、链头公共块最后淘汰”的精确序关系；（3）SGLang `RadixCache` 的动态裂边、运行锁保护与叶子级联淘汰：

```python
import hashlib
import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class SimRequest:
    req_id: str
    prompt_len: int
    max_out: int
    computed: int = 0
    generated: int = 0
    tbt_ms: List[float] = field(default_factory=list)
    last_emit_ms: Optional[float] = None

    @property
    def num_tokens(self) -> int:
        return self.prompt_len + self.generated


def step_latency_ms(total_tokens: int) -> float:
    """Roofline 分段耗时近似: <=256 token 受限于权重读取带宽 (~12ms), 超出后转入算力线性区"""
    return 12.0 + 0.01 * total_tokens if total_tokens <= 256 else 14.56 + 0.045 * (total_tokens - 256)


def measure_max_decode_tbt(enable_chunked: bool, token_budget: int) -> Tuple[float, List[int]]:
    """复现 Sarathi-Serve / vLLM V1 预算受限无停顿混合调度 vs 整段抢占 Prefill"""
    decodes = [
        SimRequest(f"dec_{i}", 512, 6, computed=512, generated=1, last_emit_ms=0.0)
        for i in range(8)
    ]
    running, waiting = list(decodes), [SimRequest("long_prefill", 4096, 2)]
    clock_ms, trace = 0.0, []

    while running or waiting:
        sched: Dict[str, int] = {}
        if not enable_chunked and waiting:
            req = waiting.pop(0)
            sched[req.req_id] = req.num_tokens - req.computed
            running.append(req)
        else:
            rem = token_budget
            for req in running:
                if rem <= 0:
                    break
                take = min(req.num_tokens - req.computed, rem)
                sched[req.req_id], rem = take, rem - take
            while waiting and rem > 0:
                req = waiting.pop(0)
                take = min(req.num_tokens - req.computed, rem)
                sched[req.req_id], rem = take, rem - take
                running.append(req)

        batch_toks = sum(sched.values())
        assert not enable_chunked or batch_toks <= token_budget
        trace.append(batch_toks)
        clock_ms += step_latency_ms(batch_toks)

        nxt = []
        for req in running:
            if req.req_id in sched:
                req.computed += sched[req.req_id]
                if req.computed == req.num_tokens:
                    if req.last_emit_ms is not None:
                        req.tbt_ms.append(clock_ms - req.last_emit_ms)
                    req.last_emit_ms = clock_ms
                    req.generated += 1
            if req.generated < req.max_out:
                nxt.append(req)
        running = nxt

    return max(g for r in decodes for g in r.tbt_ms), trace


NONE_HASH = hashlib.sha256(b"fixed-seed-vllm-v1").digest()


def hash_block_chain(tokens: List[int], block_size: int = 4, cache_salt: Optional[str] = None) -> List[bytes]:
    """复现 vLLM V1 链式块哈希: 仅处理完整块 H(parent_hash, block_tokens, extra_keys)"""
    hashes, parent = [], NONE_HASH
    for s in range(0, (len(tokens) // block_size) * block_size, block_size):
        extra = (f"salt:{cache_salt}",) if (s == 0 and cache_salt) else None
        parent = hashlib.sha256(repr((parent, tuple(tokens[s : s + block_size]), extra)).encode()).digest()
        hashes.append(parent)
    return hashes


def vllm_apc_hit_tokens(tokens: List[int], cached: set, block_size: int = 4, salt: Optional[str] = None) -> int:
    """复现 kv_cache_manager.py: max_cache_hit_length = num_tokens - 1，遇首次 miss 即断"""
    max_blocks = (len(tokens) - 1) // block_size
    hits = 0
    for h in hash_block_chain(tokens, block_size, salt)[:max_blocks]:
        if h not in cached:
            break
        hits += 1
    return hits * block_size


def vllm_free_queue_order(queue: List[Tuple[int, Optional[bytes]]], freed: List[Tuple[int, Optional[bytes]]]) -> List[int]:
    """复现 block_pool.py: 逆序归还 -> 无哈希尾块 prepend 队首优先回收, 带哈希块逆序 append 队尾"""
    no_hash = [(bid, h) for bid, h in reversed(freed) if h is None]
    with_hash = [(bid, h) for bid, h in reversed(freed) if h is not None]
    return [bid for bid, _ in (no_hash + queue + with_hash)]


class MiniRadixNode:
    def __init__(self, key: Tuple[int, ...], ts: float, parent: Optional["MiniRadixNode"] = None):
        self.key, self.ts, self.parent = key, ts, parent
        self.children: Dict[int, "MiniRadixNode"] = {}
        self.lock_ref = 0

    def __lt__(self, other: "MiniRadixNode") -> bool:
        return self.ts < other.ts


class MiniRadixCache:
    """复现 SGLang RadixCache: 动态边分裂 (_split_node)、祖先链 lock_ref 与小根堆叶子驱逐"""

    def __init__(self) -> None:
        self.root = MiniRadixNode((), 0.0)
        self.root.lock_ref, self.clock = 1, 0.0

    def insert_and_lock(self, seq: Tuple[int, ...]) -> Tuple[int, MiniRadixNode]:
        self.clock += 1.0
        node, rem, matched = self.root, seq, 0
        while rem and rem[0] in node.children:
            child = node.children[rem[0]]
            child.ts = self.clock
            c = 0
            while c < len(child.key) and c < len(rem) and child.key[c] == rem[c]:
                c += 1
            matched += c
            if c < len(child.key):
                mid = MiniRadixNode(child.key[:c], child.ts, parent=node)
                mid.lock_ref, child.key, child.parent = child.lock_ref, child.key[c:], mid
                mid.children[child.key[0]] = child
                node.children[mid.key[0]] = mid
                node, rem = mid, rem[c:]
                break
            node, rem = child, rem[c:]
        if rem:
            leaf = MiniRadixNode(rem, self.clock, parent=node)
            node.children[rem[0]] = leaf
            node = leaf
        cur = node
        while cur is not self.root:
            cur.lock_ref += 1
            cur = cur.parent
        return matched, node

    def unlock(self, node: MiniRadixNode) -> None:
        while node is not self.root:
            node.lock_ref -= 1
            node = node.parent

    def evict_tokens(self, target: int) -> List[Tuple[int, ...]]:
        leaves, stack = [], [self.root]
        while stack:
            cur = stack.pop()
            if cur is not self.root and not cur.children and cur.lock_ref == 0:
                leaves.append(cur)
            stack.extend(cur.children.values())
        heapq.heapify(leaves)
        evicted, reclaimed = [], 0
        while reclaimed < target and leaves:
            v = heapq.heappop(leaves)
            reclaimed += len(v.key)
            evicted.append(v.key)
            p = v.parent
            assert p is not None
            del p.children[v.key[0]]
            if p is not self.root and not p.children and p.lock_ref == 0:
                heapq.heappush(leaves, p)
        return evicted


tbt_raw, tr_raw = measure_max_decode_tbt(enable_chunked=False, token_budget=1024)
tbt_chk, tr_chk = measure_max_decode_tbt(enable_chunked=True, token_budget=1024)
assert tbt_raw > 195.0 and tbt_chk < 50.0 and max(tr_chk) == 1024

prompt_8 = [10, 11, 12, 13, 20, 21, 22, 23]  # 恰好 2 * block_size
chain_a = hash_block_chain(prompt_8, block_size=4, cache_salt="tenant-A")
chain_b = hash_block_chain(prompt_8, block_size=4, cache_salt="tenant-B")
assert chain_a[0] != chain_b[0] and chain_a[1] != chain_b[1]
hit_a = vllm_apc_hit_tokens(prompt_8, set(chain_a), block_size=4, salt="tenant-A")
hit_b = vllm_apc_hit_tokens(prompt_8, set(chain_a), block_size=4, salt="tenant-B")
assert hit_a == 4 and hit_b == 0  # max_hit=8-1=7 -> 7//4=1 块，第 2 块完整重算以产出 logits

evict_seq = vllm_free_queue_order([(99, b"old")], [(0, chain_a[0]), (1, chain_a[1]), (2, None)])
assert evict_seq == [2, 99, 1, 0]

radix = MiniRadixCache()
m1, n1 = radix.insert_and_lock((1, 2, 3, 4, 5, 6))
radix.unlock(n1)
m2, n2 = radix.insert_and_lock((1, 2, 3, 7, 8))
assert m1 == 0 and m2 == 3
evicted = radix.evict_tokens(target=5)
assert evicted == [(4, 5, 6)] and radix.root.children[1].lock_ref == 1

print(f"Max Decode TBT: unchunked={tbt_raw:.2f} ms (peak step={max(tr_raw)} toks) vs chunked={tbt_chk:.2f} ms (peak step={max(tr_chk)} toks)")
print(f"APC 8-token exact repeat (B=4): tenant-A hit={hit_a}/8 tokens (last full block recomputed), tenant-B hit={hit_b}/8")
print(f"APC FreeQueue eviction order (front->back): {evict_seq} (no-hash tail 2 first, shared head 0 last)")
print(f"RadixCache split & eviction: matched_prefix={m2}, evicted_unlocked_leaf={evicted}, shared_prefix_lock={radix.root.children[1].lock_ref}")
print("All Chunked Prefill, APC hash-chain/LRU, and RadixAttention checks passed.")
```

```text
Max Decode TBT: unchunked=199.45 ms (peak step=4096 toks) vs chunked=49.12 ms (peak step=1024 toks)
APC 8-token exact repeat (B=4): tenant-A hit=4/8 tokens (last full block recomputed), tenant-B hit=0/8
APC FreeQueue eviction order (front->back): [2, 99, 1, 0] (no-hash tail 2 first, shared head 0 last)
RadixCache split & eviction: matched_prefix=3, evicted_unlocked_leaf=[(4, 5, 6)], shared_prefix_lock=1
All Chunked Prefill, APC hash-chain/LRU, and RadixAttention checks passed.
```

---

## 延伸 / 追问

**追问 1：既然 Chunked Prefill 已经能消除生成停顿，为什么在超大规模生产集群（如万卡服务）中还要大费周章地做 Prefill-Decode 物理分离部署（P/D Disaggregation）？两者是互斥替代还是互补关系？**
1. **单实例内部资源耦合的天花板**：Chunked Prefill 非常适合无超高速 RDMA 互联的中小规模商品化 GPU 池（零跨机 KV 搬运开销），但它仍将两种硬件偏好截然相反的负载绑在同一组 GPU 与同一份并行度（TP/PP）上——混入过多 Prefill Token 仍会把单步耗时从纯内存带宽底噪（如 $12\text{ ms}$）推高到算力线性区（如 $45\text{ ms}$），无法同时逼近极致严苛的 ITL（如 $<15\text{ ms}$）与最大单卡吞吐；此外同池共享 HBM 也限制了 Decode 侧能开出的极限并发 Batch 大小。
2. **现代生产的黄金组合是“跨池 P/D 分离 + 池内 Chunked Prefill + 全局 Prefix Cache”**：在大规模集群中，Prefill 池用高算力配置专攻 TTFT，Decode 池用高显存带宽与大专家并行专攻 ITL；而 **Prefill 池内部依然默认开启 Chunked Prefill**（防止一条 $128\text{K}$ 超长请求饿死同池其他 $2\text{K}$ 短请求的 TTFT，并消除 PP 气泡），同时结合跨请求 APC / RadixCache 将已算好的前缀直接从本地 HBM 或主机 DRAM 命中，省去昂贵的重算与跨网传输。

**追问 2：做推理引擎压测（Benchmarking）时，为什么开启 Prefix Caching 后直接用固定 50 条真实业务 Prompt 循环打压 QPS，测出的容量上线后会瞬间崩盘？正确的压测方法是什么？**
1. **缓存污染导致的虚假百倍吞吐**：固定小样本集在第一轮预热后，后续几乎 $98\%$ 的 Prompt Token 全部命中缓存跳过前向计算，压测工具实际测到的只是“每条请求仅 Prefill 末尾 $1$ 个块 + Decode”的极限缓存吞吐，算力负载被人为低估数倍至十倍；一旦切换到真实长尾流量（缓存命中率跌回 $30\% \sim 60\%$），Prefill 排队会瞬间击穿 TTFT SLO 并打满显存。
2. **科学压测三原则**：一是在纯算力基线压测中为每条请求附加唯一随机前缀或独立 `cache_salt`（或每次压测前调用 `reset_prefix_cache`），测出**零命中下界（Worst-Case Capacity）**；二是从线上真实脱敏日志中按真实时间戳重放（Trace Replay），匹配真实的共享前缀拓扑、会话思考间隔（Think Time）与树状分支度；三是监控引擎暴露的**按 Token 加权净命中率（剔除 `preempted_hits` 自命中）**，确保压测命中率与线上稳态一致。

**追问 3：当物理块大小 `block_size`（或 SGLang 的 `page_size`）从 `1` 调大到 `16` 或 `64` 时，对 Prefix Cache 命中率、元数据开销与 FlashAttention 内核效率分别有什么正负影响？**
1. **调小粒度（如 `page_size = 1`）**：前缀匹配精度达到极致（任意词元位置分叉都不会浪费尾块，且 $100\%$ 重复请求只需重算最后 $1$ 个 Token 而非整块 $64$ 个 Token），但 Python/CPU 侧哈希链或基数树节点与块表索引膨胀数十倍，且非连续单 Token 页会导致底层 Paged FlashAttention / FlashInfer 内核发生严重的非合并显存访问（Uncoalesced HBM Access）与寻址开销。
2. **调大粒度（如 `block_size = 16 / 64` 或 MLA 架构下的 `64`）**：完美契合 GPU Tensor Core Tile 与缓存行突发读写（Burst Read），控制面哈希与页表开销极低；代价是未填满的尾部残块无法参与跨请求共享，且细碎动态内容若穿插在 Prompt 前部会提前打断整块哈希命中。因此工程上通常选 `16`（标准 GQA）或 `64`（DeepSeek MLA 等压缩 KV 架构），并在应用层遵守“静态指令与稳定工具定义严格前置、动态时间戳与检索片段后置”的上下文工程铁律。

---

## 常见误区

- **误区一：“Chunked Prefill 就是单纯把长 Prompt 切成几段依次算完，就算不设全局 Token 预算也能加速首字延迟（TTFT）。”**
  事实：**恰恰相反！** Sarathi-Serve 消融实验（Table 4）明确证明：如果脱离了统一预算无停顿调度（Stall-Free Batching），单独把单条请求的 Prefill 切碎反而会因为多次 Kernel 启动开销与历史块 KV 重复从 HBM 读取而使该请求自身的 **TTFT 变慢**。切块的真正价值是用极小的单请求 TTFT 代价（$C=2048$ 时近乎 $0\%$，$C=512$ 时 $\le 25\%$），换取同批数十个在途 Decode 请求彻底免遭秒级卡顿（消除 Generation Stall）并抹平 PP 流水线气泡。
- **误区二：“开启 Automatic Prefix Caching 后，只要发一条和上一条一模一样的 Prompt，引擎就能实现 100% 缓存命中、跳过全部 Prefill 直接吐字。”**
  事实：**前缀缓存命中长度严格受限于 `num_tokens - 1`！** 模型必须至少对最后 $1$ 个输入 Token 执行真实的前向传播才能算出预测首个生成词的 Logits；更关键的是，在块对齐分配器（如 vLLM V1 `block_size = 16`）下，若重复 Prompt 的长度恰好是 $16$ 的整数倍（如 $32$ 个 Token），`(32 - 1) // 16 = 1` 会导致**最后整整 $1$ 个完整块（$16$ 个 Token）全部重算**，监控面板上的按 Token 命中率最高只能贴近而永远不会达到 $100\%$。
- **误区三：“vLLM V1 的 LRU 前缀淘汰需要维护一个按访问时间戳排序的全局优先队列或后台定时清理协程，请求未命中缓存时也会带来不小的 CPU 损耗。”**
  事实：**vLLM V1 通过侵入式双向链表实现了 $O(1)$ 零扫描延迟淘汰！** 物理块的分配计数 `ref_cnt` 与缓存哈希 `_block_hash` 完全正交：释放时仅做常数时间的无哈希块队首前插（`prepend_n`）与带哈希块逆序队尾追加（`append_n`），命中时 `O(1)` 摘除（`touch`），而真正的哈希清理（`_maybe_evict_cached_block`）被推迟到物理槽位下次被弹出重分配的那一瞬间，没有任何时间戳堆维护或后台扫描开销。

---

## 参考

- 选题线索：[halfrost/Halfrost-Field (`05-scheduler-continuous-batching-chunked-prefill.md` & `07-automatic-prefix-caching.md`)](https://github.com/halfrost/Halfrost-Field/blob/87981b3283d7b5b2136ee230963bdfac833a1486/contents/LLM/vllm/05-scheduler-continuous-batching-chunked-prefill.md)（固定 commit `87981b3`）与 [XiaYiHann/AIInfraGuide-ia-lab (`docs/papers/sarathi-serve-notes.md`)](https://github.com/XiaYiHann/AIInfraGuide-ia-lab/blob/9fad77ebc0bfbd93799f919a3fbd0564094c9155/docs/papers/sarathi-serve-notes.md)（固定 commit `9fad77e`），结合原论文与引擎核心源码对照深化。
- Agrawal et al., [Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve](https://arxiv.org/abs/2403.02310)，USENIX OSDI 2024：Decode 内存带宽受限与 Prefill 算力受限的 Roofline 错配分析、Chunked-Prefills 与 Stall-Free Token Budget 调度、Tile-Quantization 对齐效应及 PP 气泡消除。
- Zheng et al., [SGLang: Efficient Execution of Structured Language Model Programs](https://arxiv.org/abs/2312.07104)，NeurIPS 2024，及官方源码 [sgl-project/sglang (`python/sglang/srt/mem_cache/radix_cache.py`)](https://github.com/sgl-project/sglang/blob/2d03ffcdf29584165f98781d0aececa6526f3835/python/sglang/srt/mem_cache/radix_cache.py)（固定 commit `2d03ffc`）：`RadixCache` 压缩前缀树、指数倍增分歧搜索、`_split_node` 动态裂边、`inc_lock_ref` 祖先锁与小根堆叶子级联淘汰。
- vLLM V1 官方源码 [vllm-project/vllm (`vllm/v1/core/sched/scheduler.py`, `kv_cache_utils.py`, `kv_cache_manager.py`, `block_pool.py`)](https://github.com/vllm-project/vllm/blob/38e4d7ac17878b8006a21af1e56cfcf6d4ecc316/vllm/v1/core/sched/scheduler.py)（固定 commit `38e4d7a`）：双游标缺口模型、链式块哈希 `H(parent, tokens, extra_keys)`、`max_cache_hit_length = num_tokens - 1` 边界、侵入式双端空闲队列与 `cache_salt` 隔离。

来源访问与示例核验日期：**2026-11-25**。仅执行标准库下统一预算无停顿分块调度、APC 链式块哈希与双端队列淘汰序、以及 `RadixCache` 动态裂边与锁保护叶子淘汰的确定性数值验证，未运行多卡 GPU 真实大模型推理吞吐压测。
