---
id: rag-0043
title: 向量检索的距离度量和 FLAT、IVF、HNSW 索引怎样选择，如何验证 Recall 与延迟取舍？
category: rag
tags: [vector-search, ann, faiss, distance-metrics, benchmarking]
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

向量检索的距离度量和 FLAT、IVF、HNSW 索引怎样选择，如何验证 Recall 与延迟取舍？请在同一数据集上建立 FLAT 精确基线，再扫描一个 ANN 查询参数，说明分数方向、构建和资源口径。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**先确定向量空间和度量，再用精确搜索定义近邻真值，最后测量 ANN 为速度付出了多少近邻损失。** 索引只负责寻找给定空间里的邻居，不负责判断这些邻居是否真的能回答业务问题。

表示与模型选择见 [rag-0010](rag-0010-dense-vs-sparse-vectors.md)、[rag-0026](rag-0026-embedding-model-selection.md)，人工相关性评测见 [rag-0027](rag-0027-evaluate-retrieval-quality.md)，端到端延迟见 [rag-0029](rag-0029-reduce-rag-latency.md)。本题的增量是距离排序、ANN 参数与精确基线实验。

### 1. L2、IP 和 COSINE 不可混用排序方向

对非零向量 q、x：

- L2：`||q-x||₂`，越小越近。**Faiss 的 METRIC_L2 返回平方 L2**，即 `Σ(qᵢ-xᵢ)²`；与开方后的 L2 排序相同，但分数及阈值不是同一个量。
- IP：`q·x`，越大越优；数据库向量的模长也会影响结果，它不天然等于余弦相似度。
- COSINE：`q·x / (||q||₂ ||x||₂)`，越大越相似。若接口返回的是 `1-cos` 这样的 cosine distance，则越小越近，必须看具体定义。

以下是独立设计、实际经 Faiss FLAT 验证的小例。query 为 `(1,0)`，数值按数学值或六位小数展示：

| ID / 向量 | 平方 L2，升序 | IP，降序 | COSINE，降序 |
| --- | ---: | ---: | ---: |
| A = (3,1) | 5 | 3 | 0.948683 |
| B = (1,1) | 1 | 1 | 0.707107 |
| C = (0.9,0.1) | 0.02 | 0.9 | 0.993884 |

三种排序分别是 **C→B→A、A→B→C、C→A→B**。数据库中模长更大的 A 能在 IP 排第一，但余弦更偏向方向接近 query 的 C；不应把“大分数”一概解释为同样的相似程度。

若查询和库向量都归一化成单位向量，则 `IP = COSINE`，且 `平方 L2 = 2 - 2×IP`，因此三者有等价的近邻排序。只归一化 query 不会消除库向量模长对 IP 的影响；只对库向量归一化可保持固定非零 query 的余弦排名，但若还要数值等于 cosine、使用上述 L2 公式，就须两侧都归一化。零向量的 cosine 无定义，NaN/Inf 或不可稳定归一化的输入应拒绝或按明确策略处理。

是否归一化要服从 Embedding 的训练与使用契约：若模型以模长表达检索信号，擅自归一化会改变目标。建库与查询还要使用配套模型、预处理、维度及度量；同维度不表示处于同一向量空间。不同模型即便都输出 [-1,1] 的余弦分数，也不能直接比较原始数值或共用未经校准的阈值，应在有标注的同一任务集上比较质量。

### 2. 索引选择是候选范围、资源和更新成本的取舍

| 索引 | 怎样检索 | 主要参数与代价 |
| --- | --- | --- |
| FLAT | 对全部合格向量计算目标度量，再取 Top-k | 无聚类/图训练；搜索计算约 O(Nd)，批处理可充分利用向量化。小库、低查询量或需要精确基线时很合理 |
| IVF_FLAT | 先把库向量分配到聚类倒排列表，查询只扫描部分列表，列表内用原始向量精确打分 | `nlist` 是构建时列表数；`nprobe` 是查询时探测列表数。需训练粗量化器并存 ID/列表/质心；少探测会漏掉其他列表里的近邻 |
| HNSW | 在多层近邻图上由稀疏上层导航，再在底层扩展候选 | `M` 影响连接数与图内存；`efConstruction` 影响建图搜索宽度及构建成本；`efSearch`（有些接口叫 `ef`）控制查询探索宽度。提高查询宽度通常提高 Recall，也增加工作量 |

IVF 的 `nprobe` 不是返回条数 k；HNSW 的 `efSearch` 也不是保证实际访问了恰好多少个点。建图参数与查询参数作用不同，不能指望只增大 efSearch 修复任意劣质图。HNSW 不依赖 IVF 那样的聚类训练，但仍需建图；插入顺序、随机种子、并行构建与更新/删除实现都会影响成本和结果，不宜承诺最坏情况搜索必为 O(log N)。

参数必须结合数据规模和分布选择。`nlist` 太小会让列表过长，太大则需要更多代表性训练样本，增加粗检索及维护成本；数据漂移后可能需要重训/重建。只改 nprobe 通常不用重建。HNSW 的 M、efConstruction 在构建时决定图的结构/质量，查询时扫 efSearch；需要同时满足目标 k、Recall 和时延约束，不能跨库照抄默认值。

未压缩 float32 向量的载荷下限约为 `4Nd` 字节。FLAT 还可能有 ID 映射等开销；IVF_FLAT 保留原向量，并增加倒排 ID、质心和元数据，并不会因为“少搜了”就大幅压缩存储。HNSW 通常还需约 O(NM) 的边及层级信息。训练临时数组、原始数据副本、查询缓冲、allocator 和并发都会增加实际内存。

IVF_PQ 等压缩变体另有量化误差，不能把 IVF_FLAT 的结论直接套过去。**只有本题这种无压缩、无额外扫描截断、覆盖全部列表的 IVF_FLAT，nprobe=nlist 才能与精确基线对齐**（仍需处理并列和浮点边界）；PQ 即使扫描全部列表也不自动消除压缩误差。过滤后的可见候选集也要与基线相同。

### 3. 近邻 Recall 的真值来自同一度量下的 FLAT

令 Gᵢ 是 FLAT 对第 i 条 query 返回的精确 Top-k ID 集合，Aᵢ 是 ANN 返回的 ID 集合，本题定义：

```text
ANN Recall@k = (1 / Q) × Σᵢ |Aᵢ ∩ Gᵢ| / k
```

这里每条 query 的 k 都是 10，分母是 `Q×k`。ANN 的重复 ID 不能重复计数，未填满时的 `-1` 不能算命中，不能通过缩小分母掩盖缺失。若精确第 k 名有并列，先约定稳定 ID tie-break 或可接受的并列集合；浮点实现差异也应核对。本次数据已检查第 k 与 k+1 分数严格分开。

这衡量的是**复现精确近邻的能力**，不是 [业务相关性 Recall](rag-0027-evaluate-retrieval-quality.md)。精确找到了错误语义空间里的邻居，ANN Recall 仍可能为 1。带权限/类别过滤时，应在同一合法子集建真值；候选数不足 k 时预先约定实际 kᵢ 并单独报告，空集指标记为不适用，不能填“100%”。

### 4. 固定版本的 FLAT 与 IVF nprobe 实跑

**数据是合成向量，搜索和计时是真实运行。** 没有调用 Embedding 模型，也没有语义标签。使用 NumPy PCG64/default_rng 种子 20260915，生成 10000 条 64 维标准正态库向量，再生成独立的 200 条 query；统一转 float32 并单位归一化。查询不加入库，也不参与聚类训练。Top-k=10；FLAT 和 IVF 使用完全相同的数据、预处理与 IP 度量，以此实现 COSINE 检索。

固定 `faiss-cpu==1.12.0`、`numpy==2.2.6`、Python 3.11.8。IVF_FLAT 的 nlist=64，聚类 seed=20260915、niter=10、nredo=1、spherical=True，训练使用全部 10000 条库向量，`max_codes=0`；建好同一个索引后仅扫描 nprobe=1/2/4/8/16/32/64，没有反复改数据或重建索引来挑最好结果。

本次环境：**Apple M5 Max，macOS 26.6.2 arm64，Faiss OPTIMIZE NEON**。Faiss 报告 1 线程，OMP/OpenBLAS/Accelerate 的线程环境变量在本测量进程中设为 1。每个配置先预热 2 次，再测 9 个批次，每批一起查询 200 条，取批次耗时中位数除以 200。这个数是**摊销 ms/query，不是逐请求延迟或 p95/p99**；不含数据生成、归一化、Embedding、网络、过滤、建库和序列化。配置按表中顺序测量，主机负载与缓存状态可能带来波动。

运行下列独立代码会输出环境、数据指纹、构建时间、序列化大小、距离小例及扫描结果。代码中的 8 条 query 另用 float64 逐项点积验证 FLAT，全部 query 还核对单位向量下 L2/IP 的排序与分数关系；这里用 `einsum(..., optimize=False)` 避免将独立参考交回 BLAS 路径。依赖安装可用 `python -m pip install faiss-cpu==1.12.0 numpy==2.2.6`（建议放在独立虚拟环境）。

```python
import os
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[name] = "1"  # 只约束本测量进程；必须在加载数值库前设置。

import hashlib
import json
import platform
import subprocess
from time import perf_counter_ns

import faiss
import numpy as np

def unit(vectors):
    x = np.array(vectors, dtype="float32", order="C", copy=True)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError("finite matrix required")
    norms = np.linalg.norm(x, axis=1)
    if np.any(norms == 0) or not np.isfinite(norms).all():
        raise ValueError("finite nonzero norms required")
    faiss.normalize_L2(x)
    return x

def recall_at_k(found, exact):
    if found.shape != exact.shape or exact.ndim != 2 or 0 in exact.shape:
        raise ValueError("same nonempty (queries, k) shapes required")
    if any(len(set(row)) != len(row) or np.any(row < 0) for row in exact):
        raise ValueError("ground truth needs k distinct valid IDs")
    overlap = sum(len(set(row[row >= 0]) & set(truth)) for row, truth in zip(found, exact))
    return overlap / exact.size  # -1不算命中，重复ID不重复计数，分母不缩小。

def metric_example():
    q = np.array([[1, 0]], dtype="float32")
    x = np.array([[3, 1], [1, 1], [.9, .1]], dtype="float32")
    result = {}
    for metric, database, query, index in (
        ("L2_squared", x, q, faiss.IndexFlatL2(2)),
        ("IP", x, q, faiss.IndexFlatIP(2)),
        ("COSINE", unit(x), unit(q), faiss.IndexFlatIP(2)),
    ):
        index.add(database)
        scores, ids = index.search(query, 3)
        result[metric] = {"order": ["ABC"[i] for i in ids[0]], "scores": scores[0].tolist()}
    return result

def timed_search(index, queries, k):
    for _ in range(2):
        index.search(queries, k)
    times = []
    for _ in range(9):
        start = perf_counter_ns()
        distances, ids = index.search(queries, k)
        times.append((perf_counter_ns() - start) / 1e6 / len(queries))
    return distances, ids, {"median_ms_per_query": float(np.median(times)),
                           "min_ms_per_query": min(times), "max_ms_per_query": max(times)}

def benchmark():
    assert faiss.__version__ == "1.12.0" and np.__version__ == "2.2.6"
    faiss.omp_set_num_threads(1)
    seed, n, d, nq, k, nlist = 20260915, 10000, 64, 200, 10, 64
    rng = np.random.default_rng(seed)
    xb = unit(rng.standard_normal((n, d)))
    xq = unit(rng.standard_normal((nq, d)))  # 独立抽样；不加入建库或聚类训练。
    flat = faiss.IndexFlatIP(d)
    start = perf_counter_ns(); flat.add(xb)
    flat_add_ms = (perf_counter_ns() - start) / 1e6
    exact_scores, exact = flat.search(xq, k + 1)
    assert np.all(exact_scores[:, k-1] > exact_scores[:, k])  # 本数据Top-k边界无并列。
    exact = exact[:, :k]
    # 独立float64暴力点积核对前8条查询的精确基线。
    reference_scores = np.einsum("qd,nd->qn", xq[:8].astype("float64"),
                                xb.astype("float64"), optimize=False)
    assert np.isfinite(reference_scores).all()
    reference = np.argsort(-reference_scores, axis=1)[:, :k]
    assert np.array_equal(exact[:8], reference)
    flat_l2 = faiss.IndexFlatL2(d); flat_l2.add(xb)
    l2_scores, l2_ids = flat_l2.search(xq, k)
    assert np.array_equal(l2_ids, exact)
    assert np.allclose(l2_scores, 2 - 2*exact_scores[:, :k], atol=2e-6)
    del flat_l2

    ivf = faiss.IndexIVFFlat(faiss.IndexFlatIP(d), d, nlist, faiss.METRIC_INNER_PRODUCT)
    ivf.cp.seed, ivf.cp.niter, ivf.cp.nredo, ivf.cp.spherical = seed, 10, 1, True
    ivf.max_codes = 0  # 不额外截断扫描；此处没有PQ压缩。
    start = perf_counter_ns(); ivf.train(xb)
    train_ms = (perf_counter_ns() - start) / 1e6
    start = perf_counter_ns(); ivf.add(xb)
    ivf_add_ms = (perf_counter_ns() - start) / 1e6
    _, ids, latency = timed_search(flat, xq, k)
    rows = [{"index": "FLAT", "nprobe": None, "recall": recall_at_k(ids, exact), **latency}]
    for nprobe in (1, 2, 4, 8, 16, 32, 64):
        ivf.nprobe = nprobe
        _, ids, latency = timed_search(ivf, xq, k)
        rows.append({"index": "IVF_FLAT", "nprobe": nprobe,
                     "recall": recall_at_k(ids, exact), **latency})
    assert rows[-1]["recall"] == 1.0
    return {
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
            "cpu": (subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
                    if platform.system() == "Darwin" else platform.processor() or platform.machine()),
            "faiss": faiss.__version__, "numpy": np.__version__, "faiss_threads": faiss.omp_get_max_threads(),
            "compile_options": faiss.get_compile_options()},
        "data": {"seed": seed, "n": n, "d": d, "nq": nq, "k": k, "nlist": nlist,
            "sha256": hashlib.sha256(xb.tobytes() + xq.tobytes()).hexdigest()},
        "build_ms": {"FLAT_add": flat_add_ms, "IVF_train": train_ms, "IVF_add": ivf_add_ms},
        "bytes": {"database_float32": xb.nbytes, "FLAT_serialized": len(faiss.serialize_index(flat)),
                  "IVF_FLAT_serialized": len(faiss.serialize_index(ivf))},
        "metric_example": metric_example(), "rows": rows,
    }

if __name__ == "__main__":
    print(json.dumps(benchmark(), ensure_ascii=False, indent=2))
```

**2026-09-15 实测记录**如下；重跑时间会变化，不能把这些小数当作性能回归阈值。数据 SHA-256（归一化后的库数组与 query 数组顺序拼接）为 `cc88a0706627654b21195defc568408727b150392be021c97753ee062cf1ea8f`。

| 索引 | nprobe | ANN Recall@10 | 摊销中位 ms/query | 9 批次摊销 min–max ms/query |
| --- | ---: | ---: | ---: | --- |
| FLAT | — | 1.0000 | 0.005059 | 0.004979–0.005124 |
| IVF_FLAT | 1 | 0.1100 | 0.001105 | 0.000974–0.001342 |
| IVF_FLAT | 2 | 0.1850 | 0.001626 | 0.001610–0.001676 |
| IVF_FLAT | 4 | 0.2890 | 0.003047 | 0.002900–0.003217 |
| IVF_FLAT | 8 | 0.4540 | 0.005527 | 0.005306–0.005771 |
| IVF_FLAT | 16 | 0.6475 | 0.009759 | 0.009677–0.009875 |
| IVF_FLAT | 32 | 0.8695 | 0.018817 | 0.018596–0.019608 |
| IVF_FLAT | 64 | 1.0000 | 0.036940 | 0.036460–0.037578 |

本次 FLAT 加载库向量为 **0.144 ms**；IVF 聚类训练 **5.886 ms**，添加库向量 **0.937 ms**。这是单次操作计时，不包含数据预处理，也未统计多次重建的方差。nprobe 扫描复用同一个已建索引，因此各扫描点没有新的构建成本。

库数组载荷为 **2,560,000 bytes**。`serialize_index` 的结果分别为 FLAT **2,560,045 bytes**、IVF_FLAT **2,657,035 bytes**，约 2.441 / 2.534 MiB（1 MiB=2²⁰ bytes）；同一个 IVF 索引的 nprobe 不改变向量/倒排载荷。这些是**序列化大小，不是进程 RSS 或训练峰值内存**。本实验未测这些内存指标，不能拿文件大小直接承诺部署容量。

此数据和批量口径下，nprobe 增大确实减少近邻遗漏，却增加搜索工作量；若示范要求 Recall@10≥0.95，扫描表里只有 nprobe=64 满足，而 FLAT 已同时给出精确结果和更低的摊销时间，因此本例会先选 FLAT。这个 0.95 只是读表条件，不是通用业务门槛。不能据此断言 IVF 总比 FLAT 慢：更大的库、不同聚类分布、维度、过滤比例、硬件、批量与并发可能改变结果。本题没有实跑 HNSW，关于其性能只给机制和选型依据，不捏造对照数字。

### 5. 怎样把实验迁移到真实业务

冻结真实库快照与 query 集，记录模型/预处理/metric/归一化/过滤、索引版本、数据与构建随机种子。先用开发查询扫描候选参数，选择后再用独立保留查询验收，不能在同一批查询上反复调参却声称泛化已验证。

在目标硬件上分别测构建训练/添加耗时、峰值 RSS/常驻内存、索引存储、冷/热搜索、目标 batch/并发下 p50/p95/p99、吞吐和更新开销。扫描查询参数时固定其他变量；若建图随机性或数据漂移明显，还要多次构建并报告波动。ANN Recall、业务相关性及端到端答案质量分开评测，选择满足质量与资源限制的配置，而非只挑最低延迟或最高原始相似分。

## 延伸 / 追问

**追问 1：ANN Recall 已达 1，为什么用户仍搜不到想要的内容？**

因为它只证明与同一向量空间中的精确结果一致。语义表示、query 预处理、切块、过滤或标注覆盖仍可能有问题；用人工相关性和任务成功率定位，不继续盲目加 nprobe。

**追问 2：把 nprobe 调到 nlist，IVF 就一定等于 FLAT 吗？**

本例 IVF_FLAT、原向量、无 max_codes 截断、同度量和候选集时能对齐；压缩索引或其他截断仍可能丢精度。即使精度一致，倒排访问与粗检索开销也可能让它更慢。

**追问 3：HNSW Recall 低，直接增大 M 还是 efSearch？**

先在固定图上扫 efSearch 看查询探索是否不足；M/efConstruction 属于构建侧，需要结合重建成本与内存重新评估。若精确基线本身业务质量差，调图参数不能修复表示问题。

## 常见误区

- **“所有分数都越大越相似。”** L2/平方 L2 通常升序，IP/COSINE 通常降序；cosine distance 要按接口定义判断。
- **“两个模型都给 0.8，因此相关性一样。”** 分数不跨模型直接可比，同一模型换预处理/归一化也可能改变分布。
- **“ANN Recall 就是业务相关性 Recall。”** 前者对齐精确向量近邻，后者对齐标注相关内容。
- **“ANN 一定比暴力检索快且省内存。”** 小库或高 Recall 要求下可能不划算；IVF_FLAT 不压缩原向量，图索引还增加结构内存。
- **“序列化只有几 MiB，进程也只需这些内存。”** 原始数组副本、索引对象、训练工作区和并发缓冲都在文件之外。

## 参考

- 课程线索：洛小山《AI 产品从入门到精通》learn-ai，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/vector-db-1.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vector-db-1.html)、[slides/vector-db-2.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vector-db-2.html)、[slides/vector-db-3.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/vector-db-3.html)。只作选题线索；正文、向量和实验代码独立设计，未搬运 AGPL 课件内容。
- Meta Faiss，[MetricType and distances](https://github.com/facebookresearch/faiss/wiki/MetricType-and-distances)：平方 L2、最大内积与单位归一化的余弦映射；固定 v1.12.0 源码 [faiss/MetricType.h](https://github.com/facebookresearch/faiss/blob/e8234e563f1ecef5f036e83c3cfee366d3f1fbca/faiss/MetricType.h#L23) 明确两种度量的定义。
- Meta Faiss，v1.12.0（commit `e8234e563f1ecef5f036e83c3cfee366d3f1fbca`）：[faiss/IndexIVF.h](https://github.com/facebookresearch/faiss/blob/e8234e563f1ecef5f036e83c3cfee366d3f1fbca/faiss/IndexIVF.h#L71) 的 nprobe/max_codes 与倒排列表；[faiss/IndexIVFFlat.h](https://github.com/facebookresearch/faiss/blob/e8234e563f1ecef5f036e83c3cfee366d3f1fbca/faiss/IndexIVFFlat.h) 的原始向量存储；[faiss/impl/HNSW.h](https://github.com/facebookresearch/faiss/blob/e8234e563f1ecef5f036e83c3cfee366d3f1fbca/faiss/impl/HNSW.h#L135) 的 efConstruction/efSearch 及图结构。

来源核实与测量日期均为 **2026-09-15**。Faiss 源码用于解释此版本接口；本文不声称上述参数名称、默认值或实测结果适用于所有向量数据库。
