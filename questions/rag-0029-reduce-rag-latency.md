---
id: rag-0029
title: 如何降低 RAG 的端到端延迟
category: rag
tags: [rag, latency, caching, ann, streaming]
difficulty: medium
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

如何降低 RAG 的端到端延迟（latency）？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

核心结论：RAG 延迟由「检索段 + 生成段」串联组成，**生成段（首 token + 解码）通常是大头**。优化要先按链路打点定位瓶颈，再分段下手，而不是无脑加缓存。

```
query → [embed] → [ANN 召回] → [rerank] → [拼 prompt] → [LLM 生成]
         ~10ms     ~10-50ms     ~50ms       -            占 60%+（TTFT + decode）
```

**1. 检索段优化**

- **ANN 索引调优**：HNSW 调小 `efSearch`、IVF 调小 `nprobe`，在 recall 与延迟间取折中；超大库用 IVF-PQ / 量化压缩内存、提升吞吐。
- **缩小检索域**：先用 metadata filter 圈定子集再做 ANN，候选更少更快。
- **并行召回**：多路（向量 + BM25 + 多 query）用并发而非串行执行，按最慢一路计时。
- **embedding 提速**：query 向量化用小而快的模型或本地部署，避免额外网络往返。

**2. rerank 取舍**

cross-encoder rerank 精度高但慢。可缩小 rerank 候选数（先粗排 top-50 再精排 top-5）、用更小的 rerank 模型，或对延迟敏感场景直接砍掉 rerank 用向量分数兜底。

**3. 生成段优化（收益最大）**

- **流式输出（streaming）**：边生成边返回，把感知延迟从「整段时间」降到「首 token 时间（TTFT）」，体验提升最直接。
- **控制 token 量**：精简 prompt、压缩/裁剪 context（少而准的 chunk），缩短输入；限制 `max_tokens`，输出越短解码越快。
- **模型与推理**：延迟敏感场景选更小/蒸馏模型；服务端用 KV-cache、PagedAttention、投机解码等提吞吐。

**4. 缓存（三层）**

- **query 缓存**：相同/语义相近问题直接返回历史答案（精确 + 语义缓存）。
- **embedding 缓存**：高频 query 向量结果缓存，省嵌入计算。
- **检索结果缓存**：热点 query 的 top-k 结果缓存，命中即跳过 ANN。

**5. 网络与架构**

embedding、向量库、LLM 三类服务**同区域部署**减少跨网往返；能并行的步骤并行，能预计算的离线算（如离线建库、离线 rerank 蒸馏）。

一句话：先打点定位（多数瓶颈在生成段 TTFT），再「检索调索引 + 砍冗余 rerank + 流式生成 + 三层缓存 + 同区域部署」组合下手。

## 延伸 / 追问

**追问：缓存命中率不高、又想快，优先做哪一步？**

优先上**流式输出**——它不依赖命中率，对任何 query 都能把感知延迟降到 TTFT，是性价比最高的一招。其次压缩 context、限制 `max_tokens` 缩短生成段。缓存适合「头部 query 集中、重复率高」的场景，长尾为主时命中率低、收益有限，且要解决语义缓存的相似度阈值与陈旧失效问题。ANN 调参属于在已知检索是瓶颈时才动，且要用评测集守住 recall 不被调崩。顺序：先打点 → 流式 → 减 token → 选模型 → 再视命中率决定是否加缓存。

## 参考

- Pinecone Learn，*Vector Search & ANN（HNSW / IVF 参数）*：https://www.pinecone.io/learn/series/faiss/vector-indexes/
- NVIDIA Developer Blog，*Mastering LLM Inference（KV-cache / TTFT）*：https://developer.nvidia.com/blog/mastering-llm-techniques-inference-optimization/
- LangChain Docs，*Streaming*：https://python.langchain.com/docs/concepts/streaming/
