---
id: rag-0010
title: 稠密向量和稀疏向量有什么区别？分别适合哪些搜索需求
category: rag
tags: [rag, dense-vector, sparse-vector, bm25, hybrid-search]
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

稠密向量和稀疏向量有什么区别？分别适合哪些搜索需求？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

核心区别在于**怎么表示一段文本**：稠密向量编码「语义」，稀疏向量编码「词项」。

**稠密向量（Dense）**：用 embedding 模型把文本压成一个几百~几千维的低维稠密向量，绝大多数维度为非零连续值，单维不可解释，但整体方向编码语义。相似度用余弦 / 内积，近义词、改写都能召回，使用 multilingual embedding 时还可跨语言召回。代表：BERT/BGE/OpenAI embedding + HNSW/IVF 近似最近邻（ANN）检索。

**稀疏向量（Sparse）**：维度对应词表（几万~几十万），向量里绝大多数是 0，只有出现的词非零，每一维含义明确（=某个 term 的权重）。本质是按词项精确匹配 + 词频加权。代表：BM25/TF-IDF（统计稀疏），以及 SPLADE/uniCOIL（学习式稀疏，能做有限词项扩展）；底层用倒排索引。

```
稠密  doc → [0.12, -0.83, 0.05, ...0.41]   维度低、全非零、编码语义
稀疏  doc → {  "向量":2.1, "稀疏":1.8, ... }  维度=词表、近乎全 0、对应词项

query "稠密向量" ──► 稠密: 命中"dense embedding"(语义近)
                  └► 稀疏: 命中含"稠密""向量"二词的文档(字面精确)
```

**各自适合的搜索需求**

| 维度 | 稠密 | 稀疏 |
| --- | --- | --- |
| 强项 | 语义 / 近义 / 模糊意图 | 关键词 / 专有名词 / 精确匹配 |
| 短板 | 精确 term、罕见词易漂移 | 同义改写召不回、零词重叠失效 |
| 典型场景 | 口语化问答、概念检索 | 代码/型号/ID、术语、法律条款 |
| 数据要求 | 需训练好的 embedding | 开箱即用、无需训练 |
| 索引 | 向量索引(HNSW/IVF) | 倒排索引 |

- 问「怎么提升睡眠质量」这类**语义模糊**的问法 → 稠密更稳；
- 查 `error code E1003`、药品名、人名这类**罕见精确 token** → 稀疏不会漂；稠密反而可能把生僻词糊掉。

**实践结论：用 Hybrid（混合检索）**。两路各召回 topK，再用 RRF 或加权融合分数，兼顾「语义覆盖」和「关键词精确」，通常优于任一单路；融合后再接 reranker（cross-encoder）做精排可进一步提升相关度。这也是当下 RAG 检索的主流配置。

## 延伸 / 追问

**追问：两路分数量纲不同，怎么融合？**

稠密的余弦分和 BM25 分不在同一量纲，直接相加不合理。两种主流做法：

1. **RRF（Reciprocal Rank Fusion）**：不看原始分，只看**排名**，每路按 `1/(k+rank)`（k 常取 60）打分再求和。免归一化、对异常分稳健，是默认首选。
2. **加权归一化**：先把每路分数 min-max 或 z-score 归一化到 [0,1]，再按权重 `α·dense + (1−α)·sparse` 相加，α 用验证集调。

工程上 RRF 简单稳定、无需调参，先上 RRF；若想精细控制语义/关键词的偏好，再换加权方案。融合后取 topN 交给 reranker 精排即可。

## 参考

- Pinecone Learn，*Sparse-Dense Hybrid Search*：https://www.pinecone.io/learn/hybrid-search-intro/
- Formal et al.，*SPLADE: Sparse Lexical and Expansion Model*：https://arxiv.org/abs/2107.05720
- Elastic Docs，*Reciprocal Rank Fusion (RRF)*：https://www.elastic.co/guide/en/elasticsearch/reference/current/rrf.html
