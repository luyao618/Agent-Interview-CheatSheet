---
id: rag-0018
title: 搭建 RAG 系统时，长文本的 chunking 策略如何设计，如何防止上下文截断
category: rag
tags: [rag, chunking, overlap, structure-aware, parent-child]
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

搭建 RAG 系统时，长文本的 chunking 策略如何设计，如何防止上下文截断？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

核心结论：防截断的本质是**别在语义中间硬切，且让被切散的上下文可恢复**。设计上用「结构感知切分定边界 + overlap 缝合边界 + 父子回溯补全上下文」三层兜住，而不是简单按定长 token 一刀切。

**截断从哪来**

定长滑窗按字符/token 切，会把一句话、一个表格行、一段代码函数从中间斩断：召回到的 chunk 语义不完整，下游 LLM 拿到半句话只能猜，回答就失真。这是「内容截断」；另一种是 chunk 拼进 prompt 后超出上下文窗口被尾部丢弃的「窗口截断」。两者都要防。

**三层设计**

1. **结构感知切分（定好边界）**：优先按文档自带边界切——Markdown 标题层级、HTML 标签、段落、句子、代码函数/类。用 RecursiveCharacterTextSplitter 这类「按分隔符优先级递归回退」的切法，先试大边界（段落）放不下再退句子，尽量让每个 chunk 是一个完整语义单元，从源头减少硬截断。

2. **overlap 缝合边界**：相邻 chunk 留 10–20% 重叠（约 20–50 token），把边界句两侧都覆盖到，避免「答案正好跨在切点上」而两块都不完整。代价是冗余与索引膨胀，按需权衡。

3. **父子 / 多粒度回溯（补全上下文）**：small-to-big——小块（句/小段）用于精确召回，命中后顺 parent_id 回溯父块（整节/整页）补全上下文再喂给 LLM。既保召回精度，又保证进 prompt 的是完整段落而非被切碎的片段。

```
长文档
  ├─ 结构感知：按 标题/段落/句子 切 → chunk=完整语义单元
  ├─ overlap：[..A 末句][A 末句 B 首句..]  缝合切点
  └─ 父子：  子块(精确召回) ──命中──▶ 回溯父块(补全上下文)
```

**配套防窗口截断**

- chunk 大小匹配嵌入模型上限与下游上下文预算，太大稀释相关性、太小丢上下文；
- 检索后控制 top-k 与总 token，必要时 rerank 取精、压缩或摘要，确保拼进 prompt 不溢出被尾部丢弃；
- chunk 存 doc_id/标题路径/位置等 metadata，便于回溯与溯源。

一句话：结构感知切分立边界、overlap 缝边界、父子回溯补上下文，三者叠加才能既防内容硬截断、又防窗口溢出截断。

## 延伸 / 追问

**追问：父子回溯会不会把父块拉得太大，反而撑爆上下文？**

会，所以要控粒度并设上限。常见做法：父块按「一个小节 / 一页」这类有界单元定义，而非整篇文档；回溯时只取命中子块对应的那一个父块，不是把整条链全展开。若多个子块命中同一父块，做去重合并只补一次。仍超预算时，对父块再做一次轻量压缩或摘要后入 prompt，或退而取「子块 + 前后各一句」的小窗口补全，而非整父块。本质是「按需补全、有界回溯」——补到语义完整即可，不是补得越多越好。

## 参考

- LangChain Docs，*Text Splitters（RecursiveCharacterTextSplitter / chunk_overlap）*：https://python.langchain.com/docs/concepts/text_splitters/
- LlamaIndex Docs，*Parent Document / Small-to-Big Retrieval*：https://docs.llamaindex.ai/en/stable/examples/retrievers/auto_merging_retriever/
- Pinecone Learn，*Chunking Strategies for LLM Applications*：https://www.pinecone.io/learn/chunking-strategies/
