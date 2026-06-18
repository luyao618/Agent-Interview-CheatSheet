---
id: rag-0001
title: RAG 里 Chunk 是怎么切的：固定、语义还是自适应
category: rag
tags: [rag, chunking, retrieval, embedding, semantic-chunking, overlap]
difficulty: medium
role: engineer
contributor: 佚名
source: 未知
status: published
updated: 2026-06-18
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-18
    updated: 2026-06-18
---

## 问题

RAG 里 Chunk 是怎么切的？固定、语义还是自适应？为什么？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-18

核心结论：没有「唯一正确」的切法。固定 / 语义 / 自适应是按**切分依据**递进的三类策略，工程上按数据结构化程度与精度要求来选，并普遍叠加 overlap 与父子结构。

**三类策略**

1. **固定切分（fixed-size）**：按字符 / token 定长滑窗切，配 overlap（如 512 token、重叠 50）。优点：实现简单、长度可控、对 embedding 与上下文窗口友好；缺点：会把完整语义（一句话、一个表格行）从中间切断。适合同质、无强结构的长文。

2. **语义切分（semantic）**：先按自然边界（句子 / 段落 / Markdown 标题 / 代码函数）切，再用相邻句向量相似度，在「语义跳变处」断开。优点：chunk 内主题集中、检索精度高；缺点：长度不均、需额外 embedding 计算、对噪声敏感。适合结构清晰、主题密度高的文档。

3. **自适应切分（adaptive）**：不预设固定规则，按内容动态决定边界与粒度——结合标题层级、token 预算、相似度阈值，甚至用 LLM 判断断点；常配合父子 / 多粒度（small-to-big、parent-child）：小块用于精确召回，命中后回溯父块补全上下文。优点：兼顾召回精度与上下文完整；缺点：实现与算力成本最高。

```
原始文档
  │
  ├─ 固定：  [===512===][overlap][===512===]   定长滑窗
  │
  ├─ 语义：  [句1 句2 │ 句3 句4]   在相似度跳变(sim↓)处断
  │
  └─ 自适应：父块 ──┬─ 子块a（精确召回）
                   └─ 子块b → 命中后回溯父块补上下文
```

**选型逻辑**

- **先看结构**：有清晰结构（Markdown / HTML / 代码）就优先按结构切，最省力也最准。
- **再看精度要求**：检索精度敏感 → 语义或自适应；快速上线 / 成本敏感 → 固定切分起步。
- **overlap 几乎必加**，缓冲边界切断（典型 10–20%）。
- **chunk 大小匹配下游**：太大稀释相关性、抬高 token 成本；太小丢失上下文。

一句话：固定切胜在简单可控，语义切胜在精度，自适应切胜在精度与上下文的平衡。生产里通常「按结构 + 固定上限 + overlap」打底，再对高价值语料上语义 / 父子切分。

## 延伸 / 追问

**追问：Chunk 大小和 overlap 具体怎么定？有经验值吗？**

没有万能值，按「嵌入模型上限、下游 LLM 上下文预算、语料密度」三者倒推。经验起点：通用文档 256–512 token、overlap 10–20%（约 20–50 token）；FAQ / 短问答可更小（128–256）；法律 / 论文等长逻辑文本可更大（512–1024）并配父子结构。调参方法：固定一套检索评测集（问题 → 应命中片段），用 recall@k、nDCG 对不同 (size, overlap) 做网格搜索，取指标拐点而非最大块。注意 overlap 过大 → 冗余召回、索引膨胀、成本上升；过小 → 边界信息丢失。最后别只调 chunk：检索质量还取决于 embedding 模型、是否加 reranker、metadata 过滤，应一起看。

## 参考

- LangChain Docs，*Text Splitters*（RecursiveCharacterTextSplitter / chunk_overlap）：https://python.langchain.com/docs/concepts/text_splitters/
- LlamaIndex Docs，*Node Parsers / SemanticSplitterNodeParser*：https://docs.llamaindex.ai/en/stable/module_guides/loading/node_parsers/
- Pinecone Learn，*Chunking Strategies for LLM Applications*：https://www.pinecone.io/learn/chunking-strategies/
- LlamaIndex Docs，*Parent Document / Small-to-Big Retrieval*（父子多粒度检索）：https://docs.llamaindex.ai/en/stable/examples/retrievers/auto_merging_retriever/
