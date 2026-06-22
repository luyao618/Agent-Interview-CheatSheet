---
id: rag-0023
title: RAG pipeline 的完整流程是什么
category: rag
tags: [rag, pipeline, ingestion, retrieval, generation]
difficulty: easy
role: engineer
contributor: 佚名
source: 淘天/阿里
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

RAG pipeline 的完整流程是什么？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

RAG 分**离线建库（Indexing）**与**在线问答（Query）**两条链路，串起来是一条端到端流水线：

```
离线 Indexing：
  文档加载 → 清洗/切分 → embedding → 写入向量库(+元数据/BM25)

在线 Query：
  用户问题 → 改写/embedding → 检索召回 → rerank 精排
            → 拼接 prompt(query+context) → LLM 生成 → 引用/评测
```

**离线：构建知识库**

1. **加载（Load）**：从 PDF / 网页 / DB / 代码等多源抽取文本，统一格式，保留标题、来源、时间等元数据。
2. **切分（Chunk）**：按结构 / 定长 + overlap 切成块，块大小匹配 embedding 上限与下游上下文预算。
3. **向量化（Embedding）**：用 embedding 模型把每个 chunk 编码成向量。
4. **索引（Index）**：向量写入向量库（FAISS / Milvus 等），常并存 BM25 倒排与元数据字段，支持混合检索与过滤；上游更新走增量索引。

**在线：检索增强生成**

5. **查询处理**：对用户问题做改写 / 扩展 / 多轮指代消解，再 embedding；可先判断**是否需要检索**。
6. **召回（Retrieval）**：向量近邻 + 关键词多路召回 topN 候选，可按元数据过滤。
7. **精排（Rerank）**：用 cross-encoder reranker 对候选重排，取 topK 宁少勿滥，降低噪声稀释。
8. **拼接 Prompt**：把 query + 检索片段（带出处）填入模板，约束「只依据给定上下文作答、无依据则拒答」。
9. **生成（Generation）**：LLM 基于上下文生成答案，并**标注引用来源**便于溯源。
10. **评测 / 反馈**：检索层看 recall@k / nDCG，答案层看忠实度（faithfulness）、相关性、引用正确率；线上 badcase 回流持续迭代。

一句话：RAG = **离线「加载→切分→embedding→索引」建库 + 在线「检索→rerank→拼接→生成→引用评测」问答**，核心是用外部检索把模型答案锚定到可溯源的证据上。

## 延伸 / 追问

**追问：这条流程里，哪几步最影响最终效果？**

经验上**检索质量是上限、生成是下限**。排序看：① 切分与 embedding——切坏了 / 编码区分度差，后面再好也召不回正确证据，这是最常见 badcase 根因；② 召回 + rerank——决定正确片段是否进入并排在 topK，混合召回 + reranker 提升明显；③ prompt 约束——决定模型是否「只依据上下文、敢拒答」，直接影响幻觉率；④ 生成模型本身反而不是瓶颈。优化顺序应**先建检索评测集定位是「检索没召到」还是「召到了没用好」**，再针对性调切分 / reranker / prompt，而非一上来换大模型。

## 参考

- LangChain Docs，*RAG / Retrieval*：https://python.langchain.com/docs/concepts/rag/
- LlamaIndex Docs，*High-Level Concepts（Indexing & Querying Stages）*：https://docs.llamaindex.ai/en/stable/getting_started/concepts/
- Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, 2020：https://arxiv.org/abs/2005.11401
