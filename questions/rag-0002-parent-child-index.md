---
id: rag-0002
title: 为什么引入父子索引（Parent-Child Index）
category: rag
tags: [rag, retrieval, parent-child-index, small-to-big, indexing]
difficulty: medium
role: engineer
contributor: 佚名
source: 快手 · AI Agent 开发一面
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

为什么引入父子索引（Parent-Child Index）？相对纯大块 / 纯小块切分，它在「召回精度」与「上下文完整性」之间是如何取舍的？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

核心结论：父子索引把「用什么去检索」和「拿什么去喂模型」解耦——**用小块（子）做向量检索保召回精度，命中后回溯大块（父）补上下文完整性**，从而绕开纯大块 / 纯小块都绕不开的矛盾。

**纯切分的两难**

- **纯大块**：上下文完整，但一个 chunk 混入多个主题，向量被「平均化」，query 与目标句的相似度被噪声稀释 → **召回精度差**，还浪费 token。
- **纯小块**：主题单一、向量干净、检索准，但命中的片段太短、缺前后文，模型「只见树木」 → **上下文不完整**，易答偏或编造。

精度要小、完整要大，单一粒度无法两头兼得。

**父子索引怎么做**

把文档先切成**父块**（段 / 小节，承载完整上下文），每个父块再切成若干**子块**（句 / 小段，语义单一）。**只把子块写入向量库**用于检索；每个子块带指针指向其父块。检索时用 query 匹配子块，命中后**不返回子块本身，而是回溯并返回对应父块**（small-to-big）喂给 LLM。

```
文档
 └─ 父块P1（完整上下文，存原文/不进向量库）
      ├─ 子块c1 ─┐
      ├─ 子块c2 ─┤  只有子块进向量库做检索
      └─ 子块c3 ─┘
                 │ query 命中 c2
                 ▼
        回溯指针 c2 → P1，返回父块 P1 给 LLM
```

**为什么两个指标同时改善**

- **召回精度**来自检索粒度小：向量描述单一语义，命中更准、排序更稳，规避大块的语义稀释。
- **上下文完整**来自喂给模型的粒度大：父块带足前后文，规避小块的信息缺失与答案割裂。
- 二者不再耦合在同一个 chunk 上——这正是父子结构相对单一粒度的根本价值。

**取舍与代价**

不是免费午餐：① 父块更大 → 单次喂入 token 与成本上升，需控制父块大小与召回数 k；② 多个子块可能回溯到同一父块，要**去重**避免重复上下文；③ 索引与回溯逻辑更复杂，要维护「子→父」映射。

一句话：父子索引 = 小块的检索精度 + 大块的上下文完整，代价是 token 成本与工程复杂度，适合精度与上下文都敏感的高价值语料。

## 延伸 / 追问

**追问：父子索引和 Sentence-Window、Auto-Merging 检索是一回事吗？**

同属「检索粒度 ≠ 喂入粒度」的 small-to-big 思路，但实现不同。**Sentence-Window**：以单句建索引，命中后按固定窗口向左右扩展 N 句，靠位置邻接补上下文，不需要预切父块，简单但「父」边界是滑窗、不贴合语义结构。**Parent-Child**：父子边界在切分时就按文档结构（段/小节）定好，回溯的是一个语义完整的父块，边界更自然。**Auto-Merging**：多层父子树，若同一父块下**足够多**子块同时被命中，就自动合并上提到父块，否则只返回子块——相当于按命中密度动态决定返回粒度，比固定回溯更省 token。选型：结构清晰用 Parent-Child，想按命中情况动态合并用 Auto-Merging，语料无明显结构用 Sentence-Window 兜底。

## 参考

- LlamaIndex Docs，*Parent Document / Auto-Merging Retriever*：https://docs.llamaindex.ai/en/stable/examples/retrievers/auto_merging_retriever/
- LangChain Docs，*ParentDocumentRetriever*：https://python.langchain.com/docs/how_to/parent_document_retriever/
- LlamaIndex Docs，*Metadata Replacement + Node Sentence Window*：https://docs.llamaindex.ai/en/stable/examples/node_postprocessor/MetadataReplacementDemo/
