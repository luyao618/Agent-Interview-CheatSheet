---
id: rag-0012
title: 为什么初筛召回后还要加 Rerank 模型？它能解决向量搜索的哪些局限
category: rag
tags: [rag, rerank, cross-encoder, recall-precision, retrieval]
difficulty: medium
role: engineer
contributor: 佚名
source: 字节跳动
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

为什么初筛召回后还要加 Rerank 模型？它能解决向量搜索的哪些局限？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

核心结论：这是典型的**两阶段检索（retrieve-then-rerank）**。向量初筛（bi-encoder）负责「**召回够、够快**」，但精度有限；rerank（cross-encoder）负责「**排得准**」，对小候选集做细粒度相关性重排。两者分工，用一点延迟换显著的精度提升。

**为什么向量初筛精度不够**

bi-encoder 把 query 和 doc **各自独立**编码成向量，离线就把全库 doc 算好、建 ANN 索引，线上只算一次 query 向量再做近邻搜索——这是它能在亿级库里毫秒级召回的根本原因。但代价是：query 与 doc 在编码时**从不交互**，相关性被压成一个固定维度向量的点积，必然有信息损失。由此带来三个典型局限：

1. **语义近似但不相关**：向量空间里「主题相近」就会高分，但「相近」≠「能回答这个问题」。如问「A 药的**副作用**」，介绍「A 药**适应症**」的片段向量很近却答非所问。
2. **细粒度匹配弱**：否定、限定、实体/数字、多跳条件等细节在单向量里被抹平。「2023 年营收」和「2022 年营收」常被判为高度相似。
3. **ANN 近似误差**：为了快，向量检索本身是**近似**最近邻，排序只看几何距离，不是真正的相关性判断。

**rerank 怎么补**

cross-encoder 把 `[query, doc]` **拼成一条**输入丢进 Transformer，让两者在每一层做 full attention 交互，直接输出一个相关性分数。能捕捉 bi-encoder 抹平的细节（否定、实体对齐、逻辑关系），判别精度高得多。代价是**慢**——每个候选都要过一次模型，无法离线预存，所以**只能对小集合用**。于是两阶段流水线水到渠成：

```
query
  │
  ▼
① bi-encoder 初筛（快, 召回向）
  全库 → ANN 近邻 → Top-N 候选 (N≈50~100)
  │   重召回，宁滥勿缺
  ▼
② cross-encoder 精排（慢, 精度向）
  对 N 条逐一 [query,doc] 交互打分 → 重排
  │   截断
  ▼
  Top-K 喂给 LLM (K≈3~5, 干净)
```

- **第一阶段重召回**：N 设大些（top-50/100），先保证答案片段「进了候选池」，漏召回后面无法挽回。
- **第二阶段重精度**：cross-encoder 把真正相关的顶上来，再按「固定上限 / 分数阈值 / 分差拐点」截断到小 K（详见 rag-0004），把干净的少量上下文交给 LLM，缓解 lost-in-the-middle 与噪声稀释（详见 rag-0011）。

**它解决的核心局限**，一句话：bi-encoder 用「独立编码 + 近似搜索」换了速度，丢了 query-doc 交互带来的精度；rerank 用「联合编码 + 全交互」把精度补回来，只在小候选集上付出可控的算力。两者是**速度与精度的分工**，不是相互替代。

## 延伸 / 追问

**追问：既然 cross-encoder 更准，为什么不直接用它检索，跳过向量召回？**

因为**算不动**。cross-encoder 必须把 query 和每个 doc 拼起来现算，无法像 bi-encoder 那样离线预存 doc 向量、建 ANN 索引。直接全库跑意味着每次查询要对**全部文档**各做一次前向，亿级库下延迟和成本完全不可接受。bi-encoder 反过来——doc 向量离线算好，线上只算一次 query 再做近邻搜索，复杂度从「全库」降到「近邻」。所以工程上让二者各司其职：bi-encoder 把候选从亿级砍到几十上百（快、保召回），cross-encoder 只在这小集合上精排（准、可控）。这正是「漏斗式」检索的价值——**用便宜模型缩小范围，用贵模型保证质量**，在召回率、精度、延迟、成本之间取平衡。

## 参考

- Pinecone Learn，*Rerankers and Two-Stage Retrieval*：https://www.pinecone.io/learn/series/rag/rerankers/
- Cohere Docs，*Rerank*（cross-encoder 精排）：https://docs.cohere.com/docs/reranking
- Sentence-Transformers Docs，*Cross-Encoders vs Bi-Encoders*：https://www.sbert.net/examples/applications/cross-encoder/README.html
- Nogueira & Cho，*Passage Re-ranking with BERT*, 2019：https://arxiv.org/abs/1901.04085
