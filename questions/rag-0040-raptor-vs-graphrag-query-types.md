---
id: rag-0040
title: RAPTOR 和 GraphRAG 分别适合回答什么类型的问题？
category: rag
tags: [rag, raptor, graphrag, hierarchical-index, graph-index]
difficulty: medium
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 3 章
status: published
updated: 2026-08-06
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-06
    updated: 2026-08-06
---

## 问题

RAPTOR 和 GraphRAG 分别适合回答什么类型的问题？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-06

核心结论：两者都是为「原始 chunk 检索答不好的问题」而生，但组织知识的**结构不同**——RAPTOR 建的是**树形层次摘要**，GraphRAG 建的是**实体关系图**。结构决定了各自擅长的查询类型。

**RAPTOR：递归聚类 + 摘要，自底向上建树**

把 chunk 聚类，对每簇生成摘要作为父节点，再对摘要递归聚类摘要，直到根。检索时可跨层命中：细节问题落到叶子，宏观问题命中高层摘要节点。

```
        [根：全文主旨摘要]
        /              \
   [簇摘要A]          [簇摘要B]      ← 高层：主题级归纳
    /    \            /    \
 chunk  chunk      chunk  chunk     ← 叶子：原始细节
```

擅长：
- **全局总结 / 主题归纳**：「这份报告整体讲了什么」「几篇文档的共同结论」——高层摘要节点直接命中。
- **需要不同抽象粒度**的问题：既要细节又要概览，跨层检索天然支持。
- **单文档或同质语料**内的分层理解。

**GraphRAG：抽实体与关系，建知识图 + 社区摘要**

用 LLM 从文本抽取实体、关系，构成图；再对图做社区聚类并为每个社区生成摘要。检索分两路：局部问题沿实体邻域游走，全局问题聚合社区摘要 map-reduce。

```
  (人物A)──合作──►(项目X)──依赖──►(技术Y)
     │                              ▲
     └────────投资──►(公司B)────────┘
```

擅长：
- **多跳关系推理**：「A 和 C 通过谁/什么产生联系」——沿边游走能串起 chunk 里分散、never co-occur 的事实。
- **跨文档的实体归纳**：把散落在多篇文档里对同一实体的描述聚合。
- **全局关系型总结**：「整个语料里有哪些主要阵营/主题」——社区摘要回答。

**选型对照**

| 查询类型 | 更适合 |
| --- | --- |
| 局部事实、单点检索 | 普通向量 RAG 即可 |
| 全局总结 / 主题归纳 | RAPTOR 或 GraphRAG 均可 |
| 多跳、跨实体关系推理 | **GraphRAG** |
| 多粒度、层次化理解 | **RAPTOR** |

一句话：**问「关系」用 GraphRAG，问「层次与总结」用 RAPTOR**；纯局部事实用朴素 RAG 就够，别为它上重型索引。生产中二者也可互补：RAPTOR 补全局上下文，GraphRAG 补关系链。

## 延伸 / 追问

**追问：既然 GraphRAG 也能做全局总结，为什么还要 RAPTOR？**

因为二者的「全局」来路不同，成本与失真点也不同。GraphRAG 的全局总结依赖**实体抽取 + 社区检测**，对「关系稀疏、实体不清晰」的语料（如叙事散文、连续论证）抽图噪声大、构建贵，且抽取会丢掉非实体型语义。RAPTOR 只做**聚类 + 摘要**，不假设文本里有清晰实体关系，对同质长文更稳、更省，天然保留原文语义粒度。反过来，多跳关系问题 RAPTOR 就吃力——它的树不编码实体间的边，跨节点关系无从游走，只能靠摘要「碰巧」提到。所以判据是**语料结构**：强实体关系（知识库、事件网络）→ GraphRAG；弱关系、重层次归纳（报告、论文、书）→ RAPTOR。

## 参考

- Sarthi et al., *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval*, 2024：https://arxiv.org/abs/2401.18059
- Edge et al., *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*, 2024：https://arxiv.org/abs/2404.16130
- Microsoft Research，*GraphRAG* 项目主页：https://microsoft.github.io/graphrag/
