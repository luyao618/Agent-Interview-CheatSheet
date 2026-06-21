---
id: rag-0020
title: 有医疗/法律等专业领域知识，要做智能助手，RAG 链路会怎么搭建
category: rag
tags: [rag, domain-specific, pipeline, evaluation, safety]
difficulty: hard
role: engineer
contributor: 佚名
source: 字节跳动/豆包
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

有医疗 / 法律等专业领域知识，要做智能助手，RAG 链路会怎么搭建？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

医疗 / 法律属于**高风险、强合规、低容错**场景，RAG 的设计重心不是「召回更多」，而是**准确、可溯源、敢拒答**。整条链路按下面五段搭建：

```
语料治理 → 领域索引 → 检索+rerank → 受约束生成 → 专家评测/反馈
  ↑权威分级  ↑专业embed   ↑混合召回    ↑强制引用      ↑可溯源闭环
```

**1. 领域语料治理（地基）**
- 只收**权威源**：诊疗指南、药典、法条 / 判例、SOP；标注**版本、生效日期、效力层级、地域**，过期 / 废止内容下架。
- 结构化切分：按条款 / 章节 / 适应症切，保留标题路径与元数据，**禁止跨条款混切**导致语义串台。

**2. 专业 embedding 与索引**
- 通用 embedding 对专业术语（药名、罪名、缩写）区分度差，需**领域微调或专业向量模型**，并维护术语 / 别名词典做 query 改写。
- 混合索引：向量（语义）+ BM25 / 关键词（精确命中术语、法条号），元数据字段（科室、法域、时间）支持过滤。

**3. 检索 + rerank**
- 多路召回后用**领域 reranker** 精排，按效力层级 / 时效加权；topK 宁少勿滥，避免噪声稀释。

**4. 受约束生成（合规核心）**
- **强引用约束**：答案每个结论必须挂可点击出处，不允许「无来源发挥」。
- **敢拒答**：检索置信度低 / 证据冲突 / 超出范围时，输出「无法确定，请咨询专业人士」，而非编造。
- **安全护栏**：免责声明、禁止开具体处方 / 法律定性，高风险走人工复核（human-in-the-loop）。

**5. 专家评测与闭环**
- 评测分两层：检索层看 recall@k / 命中率；答案层由**领域专家**评准确性、引用正确性、有害率，而非只看流畅度。
- 建领域评测集 + 线上 badcase 回流，持续迭代语料与 prompt。

一句话：专业领域 RAG = **权威语料 + 专业检索 + 强引用约束 + 敢拒答 + 专家评测**，宁可少答、不可错答。

## 延伸 / 追问

**追问：领域知识会更新（指南改版、法条修订），怎么保证答案不引用过期内容？**

核心是把「时效」做成一等公民：① 每个 chunk 带 `effective_date` / `expire_date` / `version` / `status(生效|废止)` 元数据，检索时**强制过滤掉已废止、未生效**的条款；② 同一主题多版本并存时，rerank 按生效时间加权，默认取**当前有效版本**，必要时让模型标注「截至 X 日期」；③ 增量索引：上游指南 / 法条更新触发 pipeline 重新切分入库并下架旧版，而非全量重建；④ 冲突兜底：检测到新旧版本结论冲突时，提示「条款近期有修订」并附两版出处交人工确认。要点是让时效性由**数据与检索过滤**保证，而不是指望模型记得哪条过期了。

## 参考

- Anthropic Docs，*Retrieval Augmented Generation / Citations*：https://docs.anthropic.com/en/docs/build-with-claude/citations
- LlamaIndex Docs，*Metadata Filtering & Node Postprocessors*：https://docs.llamaindex.ai/en/stable/module_guides/querying/node_postprocessors/
- LangChain Docs，*Self-querying / Metadata filters*：https://python.langchain.com/docs/how_to/self_query/
