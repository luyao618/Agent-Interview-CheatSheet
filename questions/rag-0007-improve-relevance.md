---
id: rag-0007
title: 如果要提升检索相关度，你会怎么做
category: rag
tags: [rag, relevance, hybrid-search, rerank, query-rewrite]
difficulty: medium
role: engineer
contributor: 佚名
source: 快手
status: published
updated: 2026-06-21
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-21
    updated: 2026-06-21
---

## 问题

如果要提升（RAG 检索的）相关度，你会怎么做？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

核心思路：先用评测**定位瓶颈在召回还是排序**，再沿检索链路逐段下手——别一上来就堆 reranker。相关度是「召得回 + 排得准」两层问题。

```
Query ─► 改写/扩展 ─► 召回(向量+BM25 hybrid) ─► 融合 ─► Rerank ─► topK
  │          │              │                          │
 意图      多路召回      metadata过滤              精排截断
```

**1. Query 侧（召回前）**

- **改写 / 扩展**：口语化、指代、多意图的 query 先用 LLM 改写、补全、拆成多个子查询（multi-query）；HyDE 用「假设答案」去检索，缓解 query 与文档表述不对齐。
- **意图与过滤**：抽取实体 / 时间 / 类目转成 **metadata 过滤**，先把范围缩小再做语义匹配，能显著降噪。

**2. 召回侧（提召回率）**

- **Hybrid 混合检索**：向量（语义）+ BM25（关键词、术语 / ID / 专有名词），用 RRF 或加权融合。单走向量常漏精确词，混合是性价比最高的一招。
- **embedding 调优**：换更强 / 领域匹配的模型，必要时用业务正负样本微调；中文注意分词与归一化。
- **chunk 调优**：相关度差常源于切分——配 overlap、上父子 / small-to-big，避免命中片段上下文不全。

**3. 排序侧（提精度）**

- **Rerank 精排**：用 cross-encoder 对召回 topN 重排，把真正相关的顶上来，再截 topK。这是提升「排得准」最直接的杠杆。
- **召回放大 + 精排收窄**：召回 topN 适当放大（如 50→100）给精排更多候选，再由 reranker 截到 3–5 条喂 LLM。

**4. 数据与反馈闭环**

- **清洗与元数据**：去重、补标题 / 摘要 / 关键词，提升可被检索性。
- **负反馈**：收集点击 / 点踩 / 人工标注，做难负例挖掘，反哺 embedding 微调与阈值调参，形成迭代飞轮。

**落地顺序（按 ROI）**：① 建评测集量化 recall@k / nDCG → ② 上 hybrid + metadata 过滤 → ③ 加 reranker → ④ query 改写 / 扩展 → ⑤ chunk 与 embedding 调优 → ⑥ 负反馈微调。一句话：**先量化、再混合召回、后精排，最后靠反馈闭环持续逼近。**

## 延伸 / 追问

**追问：相关度上去了，但答案质量没改善，可能卡在哪？**

检索相关 ≠ 生成正确，常见三处断点：① **召回内容对但被截断 / 排在 LLM 注意力盲区**——topK 太大、关键片段落在中间（lost-in-the-middle），应收窄 topK 并把高分片段前置；② **上下文有了但 prompt 没约束**——未要求「依据检索内容作答、无依据则说不知道」，模型放飞自我产生幻觉；③ **相关但不充分**——单跳检索答不了多跳 / 对比类问题，需要 query 分解或多轮检索。排查法：固定一批 query，分别看「检索片段是否含答案」与「给定正确片段模型是否答对」，把检索错和生成错拆开定位。

## 参考

- Anthropic，*Contextual Retrieval*（hybrid + 上下文增强）：https://www.anthropic.com/news/contextual-retrieval
- Pinecone Learn，*Rerankers and Two-Stage Retrieval*：https://www.pinecone.io/learn/series/rag/rerankers/
- Gao et al., *Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE)*, 2022：https://arxiv.org/abs/2212.10496
- LlamaIndex Docs，*Query Transformations / Hybrid Retrieval*：https://docs.llamaindex.ai/en/stable/optimizing/advanced_retrieval/advanced_retrieval/
