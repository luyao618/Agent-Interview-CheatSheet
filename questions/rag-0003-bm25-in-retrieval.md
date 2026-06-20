---
id: rag-0003
title: 为什么在检索阶段引入 BM25
category: rag
tags: [rag, bm25, sparse-retrieval, hybrid-search, keyword-matching]
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

为什么在检索阶段引入 BM25？它和稠密向量检索各自的短板是什么，为什么二者要做 hybrid？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

核心结论：BM25 是**稀疏 / 关键词检索**的代表，用来补稠密向量在**精确术语、长尾词、低频专名**上的召回短板；二者失败模式互补，所以生产里常做 hybrid。

**BM25 是什么**

经典的词频检索打分：在 TF-IDF 基础上加了**词频饱和**（一个词出现再多，贡献也趋于上限）和**文档长度归一化**（长文不因为词多而占便宜）。它基于**字面词匹配**，命中靠 query 与文档**共享同一个 token**。

**稠密向量的短板**

向量检索把文本压成语义向量，擅长「换一种说法也能召回」，但有结构性弱点：

- **精确术语 / 专名**：型号 `A100`、错误码 `ERR_503`、函数名、人名，语义空间里往往被近义概念稀释，反而召不回字面命中的那篇。
- **长尾 / 低频词**：训练语料里稀少的词，embedding 表达差。
- **域外漂移**：换领域后向量质量明显下降，而 BM25 不依赖训练、开箱即用、可解释。

BM25 恰好在这些点上稳：只要词对上就能召回，对精确匹配近乎「必中」。

**为什么 hybrid**

二者**失败模式正交**——向量丢字面、BM25 丢语义改写。融合双路召回能同时覆盖：

```
query
 ├─ BM25(稀疏) ──► 字面/术语/长尾命中 ─┐
 │                                     ├─► 融合(RRF/加权) ─► rerank ─► top-k
 └─ 向量(稠密) ─► 语义改写/近义命中 ───┘
```

融合常用 **RRF**（按各路排名倒数相加，免去分数量纲对齐）或加权求和，再接 reranker 精排。

一句话：向量保「语义召回」，BM25 保「字面召回」，hybrid 取并集把两类漏召都补上，是检索阶段低成本高收益的稳健做法。

## 延伸 / 追问

**追问：既然有了强大的向量检索，为什么不直接抛弃 BM25？**

因为向量并不能稳定覆盖 BM25 的强项。① **精确匹配刚需**：代码、ID、法条编号、SKU 这类 query，用户要的就是字面命中，向量的「近似」反而有害；② **零训练、可解释、便宜**：BM25 不需要 GPU 算 embedding，命中词一目了然，便于调试和冷启动；③ **鲁棒性**：换域、长尾、拼写罕见词时向量退化，BM25 仍稳定。代价是它不懂同义改写、对分词敏感、易被关键词堆砌干扰。所以主流不是二选一，而是「BM25 兜字面 + 向量补语义」的 hybrid，让两者各自扬长、互相兜底。

## 参考

- Robertson & Zaragoza, *The Probabilistic Relevance Framework: BM25 and Beyond*, 2009：https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf
- Elastic Docs, *Practical BM25*：https://www.elastic.co/blog/practical-bm25-part-2-the-bm25-algorithm-and-its-variables
- Cormack et al., *Reciprocal Rank Fusion (RRF)*, 2009：https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
- Pinecone Learn, *Hybrid Search*：https://www.pinecone.io/learn/hybrid-search-intro/
