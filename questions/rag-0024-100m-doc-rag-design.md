---
id: rag-0024
title: 如何设计一个 100M 文档规模的 RAG 系统
category: rag
tags: [rag, scalability, vector-db, sharding, ann]
difficulty: hard
role: engineer
contributor: 佚名
source: 淘天/阿里
status: published
updated: 2026-06-22
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-22
    updated: 2026-06-22
---

## 问题

如何设计一个 100M（亿级）文档规模的 RAG 系统？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

亿级文档下，RAG 的难点从"召得准"变成"在可控成本/延迟内召得准"。核心是**分布式向量库 + ANN 索引 + 分片 + 离线批量 embedding + 多级缓存**。

```
离线：文档源 → 分布式切分/embedding(批) → 写入分片向量库(N shard)
在线：query → 路由/广播到各 shard → 各自 ANN topK → 全局归并 → rerank → LLM
```

**1. 容量与分片（Sharding）**
1 亿 chunk × 768 维 float32 ≈ 300GB，单机放不下且 QPS 受限，必须**水平分片**。按文档 ID/租户/时间 hash 切成 N 个 shard，每 shard 独立建 ANN 索引；查询**scatter-gather**：广播到各 shard 取局部 topK，再全局归并。可加副本提升 QPS 与可用性。

**2. ANN 索引选型**
- **HNSW**：召回高、延迟低，但内存占用大、构建慢，适合内存够、写入不频繁的场景。
- **IVF-PQ**：倒排聚类 + 乘积量化压缩向量，内存省一个量级、可上亿规模，召回略降；适合海量+成本敏感。
- 大规模常用 **IVF + PQ + HNSW（如 IVF_HNSW）** 组合：粗筛桶 + 桶内图索引，平衡内存/召回/延迟。用 Milvus/Vespa/分布式 FAISS 落地。

**3. 离线批量 embedding**
亿级文档全量编码是大头：用 **Spark/Ray 批处理**并行调度 GPU embedding，按队列削峰；产出落对象存储再批量灌库。**增量更新**走 CDC/消息队列，只编码变更文档，避免全量重建。

**4. 缓存与成本/延迟权衡**
- **多级缓存**：query→结果缓存（热点问答）、embedding 缓存、rerank 缓存。
- **冷热分层**：热数据 HNSW 全内存，冷数据 IVF-PQ/磁盘（DiskANN），按访问频率迁移。
- **量化压缩**：PQ/SQ 压缩 + 标量量化降内存与成本。
- **延迟**：scatter-gather 受最慢 shard 拖累，需限 `nprobe`/`efSearch` 控制单 shard 耗时，必要时降级（少查 shard/跳过 rerank）。

**5. 检索质量**
分片不应损召回：**混合检索**（向量 + BM25 倒排）多路召回，元数据预过滤（租户/时间/权限）缩小范围，全局 rerank（cross-encoder）取最终 topK。

一句话：亿级 RAG = **分片打散容量 + ANN(IVF-PQ/HNSW) 控内存与延迟 + 批量/增量 embedding 摊平算力 + 多级缓存与冷热分层压成本**，用 scatter-gather + 混合召回 + 全局 rerank 守住质量。

## 延伸 / 追问

**追问：scatter-gather 下单个 shard 抖动拖慢整体，怎么办？**

这是分布式检索的长尾问题，整体延迟取决于最慢 shard。常用手段：① **副本 + hedged request**，同一 shard 发给多副本取先返回的；② **超时降级**，设单 shard 截止时间，超时则用已返回的子集结果（容忍轻微召回损失换稳定延迟）；③ **负载均衡**，分片均匀、避免热点 shard，热点租户单独扩副本；④ **限制每 shard 计算量**（`nprobe`/`efSearch`），用召回换确定性延迟；⑤ 监控 P99 而非均值，按尾延迟做容量规划。本质是在**召回率与尾延迟**间做工程取舍。

## 参考

- Milvus，*分布式向量数据库（架构与可扩展性）*：https://github.com/milvus-io/milvus
- Johnson et al., *Billion-scale similarity search with GPUs (FAISS)*, 2017：https://arxiv.org/abs/1702.08734
- Malkov & Yashunin, *Efficient and robust approximate nearest neighbor search using HNSW*, 2018：https://arxiv.org/abs/1603.09320
- Subramanya et al., *DiskANN: Fast Accurate Billion-point Nearest Neighbor Search on a Single Node*, 2019：https://papers.nips.cc/paper/2019/hash/09853c7fb1d3f8ee67a61b6bf4a7f8e6-Abstract.html
