---
id: rag-0036
title: RAG 你们怎么优化的：chunk size / overlap 怎么设，要不要加 rerank
category: rag
tags: [rag, optimization, chunk-size, overlap, rerank]
difficulty: medium
role: engineer
contributor: 佚名
source: 美团
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

RAG 你们怎么优化的？chunk size / overlap 怎么设？有没有加 rerank？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

这题考的不是某个魔法参数，而是**有没有一套「评测驱动」的优化方法论**。我会先亮结论：所有取值都从离线评测集倒推，而不是拍脑袋；rerank 基本是标配。

**先建评测闭环，再谈调参。** 没有评测集的调参都是玄学。我会先攒一套 50–200 条的 (query → 应命中 chunk) 标注集，盯两层指标：检索层用 recall@k、nDCG@k、MRR；生成层用 faithfulness（忠实度）、answer relevance。任何改动都跑这套集子看指标，取**指标拐点**而非单点最优。

```
评测驱动的优化环
  ┌─────────────────────────────────────────────┐
  │  改一个变量(size/overlap/rerank/hybrid)       │
  ▼                                              │
 跑评测集 ──► recall@k·nDCG (检索)              │
            └─► faithfulness (生成) ──► 看拐点 ──┘
```

**chunk size / overlap 怎么设。** 没有万能值，按「embedding 模型上限 + 下游 LLM 上下文预算 + 语料密度」三者倒推：

- **起点经验值**：通用文档 256–512 token；FAQ/短问答更小（128–256）；论文/法律等长逻辑文本更大（512–1024）并配父子结构。
- **overlap 基本必加**，缓冲边界把一句话/一个表格行切断，典型 **10–20%**（约 20–50 token）。过大→冗余召回、索引膨胀、成本上升；过小→边界信息丢失。
- **方法**：固定其它变量，对 (size, overlap) 做网格搜索，看 recall@k 拐点。有结构（Markdown/代码）就优先按结构切，最省力也最准。

**rerank：基本会加，性价比最高的一步。** 向量召回是「双塔」近似，召回快但排序粗；rerank 用 cross-encoder 让 query 和 doc 充分交互，精度显著更高。典型两段式：先向量/混合**粗召回 top-50~100**，再 rerank **精排到 top-3~5** 喂给 LLM。它直接拉高送进上下文的相关性，对最终答案质量增益往往比反复调 chunk 更大；代价是每 query 几十毫秒延迟，用召回数和精排数平衡即可。

```
query
  │
  ├─ 向量召回 ┐
  ├─ BM25     ┼─► 融合(RRF) top-100 ─► Rerank ─► top-5 ─► LLM
  └─ ...     ┘   (粗召回，要全)        (cross-encoder, 要准)
```

**hybrid 检索同样重要。** 纯向量对专有名词、ID、型号、低频词召回差，我会叠 **BM25/关键词**走稀疏路，再用 RRF 把两路结果融合——稠密管语义、稀疏管精确匹配，互补。

**完整优化清单（按性价比排序）：**

1. **数据/切分**：清洗噪声、按结构切、size/overlap 倒推；
2. **检索**：hybrid（向量 + BM25）+ metadata 过滤缩小范围；
3. **rerank**：粗召回放大 + cross-encoder 精排（增益最稳）；
4. **embedding 模型**：换更适配领域的模型，必要时微调；
5. **query 侧**：改写/扩写（HyDE、multi-query）提召回；
6. **生成侧**：prompt 加引用边界与「不知道就说不知道」防幻觉。

**一句话**：先搭评测闭环，再**一次只动一个变量**按指标调；chunk size/overlap 从经验值起步用网格搜索定，rerank 和 hybrid 几乎是标配——它们对最终质量的杠杆通常比死磕 chunk 参数更大。

## 延伸 / 追问

**追问：上了 rerank 延迟变高，怎么权衡？**

权衡点在「粗召回数 N」和「精排数 K」。延迟主要来自 rerank 要对 N 个候选逐个过 cross-encoder，N 越大越慢。优化手段：① 调小 N（如 100→50），用评测集确认 recall 没掉到拐点以下；② 选轻量 rerank 模型或蒸馏版，单次打分更快；③ 批量推理 + GPU，把 N 个候选并行打分；④ 加缓存，高频 query 直接命中；⑤ 真扛不住就退化为「只对向量 top-K 做 rerank」或按场景分级（高价值查询才精排）。核心还是评测驱动：画出 N–recall 和 N–延迟两条曲线，取「recall 已饱和、延迟可接受」的交点，而不是盲目堆大 N。

## 参考

- Pinecone Learn，*Rerankers and Two-Stage Retrieval*：https://www.pinecone.io/learn/series/rag/rerankers/
- LangChain Docs，*Text Splitters（chunk_size / chunk_overlap）*：https://python.langchain.com/docs/concepts/text_splitters/
- Ragas Docs，*RAG 评测指标（faithfulness / context recall）*：https://docs.ragas.io/en/stable/concepts/metrics/
