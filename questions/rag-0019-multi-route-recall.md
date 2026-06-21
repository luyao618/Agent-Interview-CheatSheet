---
id: rag-0019
title: 如果遇到简单专有名词匹配问题，知识库多路召回架构如何设计
category: rag
tags: [rag, multi-route-recall, bm25, vector, fusion]
difficulty: medium
role: engineer
contributor: 佚名
source: 京东
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

如果遇到简单专有名词匹配问题，知识库多路召回架构如何设计？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

核心结论：专有名词（产品型号、缩写、人名、SKU）召不回，根因是**向量召回擅长语义、不擅长字面精确匹配**——`SKU-A100` 和 `SKU-A1000` 在向量空间里几乎一样近。解法是**多路并行召回 + 融合**：让精确/关键词路负责「专名命中」，向量路负责「语义泛化」，各取所长再合并。

**为什么单路不够**

- 纯向量：稀有词、型号、拼写敏感词会被「语义近似」淹没，精确度差。
- 纯关键词（BM25）：扛得住精确字面，但同义改写、口语化提问召不全。
- 专名既要求「一字不差」，又常被用户简写/别称，单路都有盲区。

**多路召回架构**

```
              用户 query
                 │
   ┌─────────────┼──────────────┐
   ▼             ▼              ▼
向量路        BM25/关键词路    精确/词典路
(语义召回)    (字面召回)      (专名→别名表/
   │             │            规则精确匹配)
   └─────────────┼──────────────┘
                 ▼
            RRF 融合排序
                 ▼
          rerank → top-k → LLM
```

1. **向量路**：embedding 近邻检索，保语义召回率。
2. **BM25/稀疏路**：倒排 + 词频，专名作为关键词能精确命中，对型号、缩写鲁棒。
3. **精确/词典路**：维护**专名别名表/同义词典**（`小米SU7=SU7=su7`），query 侧做实体识别与归一，命中走精确匹配或 metadata 过滤，直接锁定目标文档。

**融合（关键）**

各路结果用 **RRF（Reciprocal Rank Fusion）** 合并：`score=Σ 1/(k+rank)`，只依赖排名、无需各路分数同尺度，工程上最稳；也可加权让专名路在检出专名时权重更高。融合后再过 rerank 精排取 top-k。

**专名增强要点**

- 建索引时对专名**保留原文 + 不做激进分词**，避免 `A100` 被切碎。
- query 端做实体抽取 + 别名归一，专名路才能稳定触发。
- 别名表可人工维护或从日志/同义词挖掘增量补充。

一句话：向量保召回、BM25 保字面、词典/精确路保专名，三路并行用 RRF 融合再 rerank——专名走关键词/词典路提精确，语义走向量路提泛化，互补兜底。

## 延伸 / 追问

**追问：query 里既有专名又有语义意图，怎么避免某一路把结果带偏？**

靠「路由 + 融合权重」两层兜。先轻量判断 query 类型：识别到强专名（型号/SKU/缩写）就调高 BM25/词典路权重甚至加 metadata 过滤把范围锁死；偏开放语义提问就让向量路主导。融合阶段用 RRF 而非直接相加各路原始分，天然抗「某一路分数尺度异常」带偏；必要时按路设权重或对专名路命中做加权。最后统一 rerank 精排，用交叉编码器在合并候选集上重新打分，纠正单路偏置，确保既不漏专名、也不丢语义相关文档。

## 参考

- Pinecone Learn，*Hybrid Search（dense + sparse）*：https://www.pinecone.io/learn/hybrid-search-intro/
- Elastic Docs，*Reciprocal Rank Fusion (RRF)*：https://www.elastic.co/guide/en/elasticsearch/reference/current/rrf.html
- Weaviate Docs，*Hybrid Search & Fusion*：https://weaviate.io/developers/weaviate/search/hybrid
