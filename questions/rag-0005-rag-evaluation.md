---
id: rag-0005
title: RAG 系统如何评测
category: rag
tags: [rag, evaluation, retrieval-metrics, generation-metrics, ragas]
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

RAG 系统如何评测？从哪些维度衡量检索与生成的质量，常用哪些指标与框架？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

核心结论：RAG 评测要**分层**——把「检索对不对」和「答得好不好」拆开看，再叠一层端到端的整体评测，否则指标一动你根本不知道是检索丢了还是生成飘了。

**两层 + 一层整体**

```
query ─► 检索层 ──► 召回片段 ──► 生成层 ──► 答案
          │                       │
      retrieval metrics      generation metrics
          └────────── end-to-end ──────────┘
```

**1. 检索层（retrieval）**——衡量「该命中的片段有没有被捞上来、排得够不够前」：

- **Recall@k**：应命中片段有多少进了 topK，关注「漏没漏」。
- **Precision@k / Context Precision**：召回里有多少真相关，关注「脏不脏」。
- **MRR / Hit Rate**：第一个相关片段的排名，关注「准不准」。
- **nDCG@k**：带位置折扣的排序质量，对「相关的排前面」最敏感。

需要一套带标注的评测集（query → 应命中片段 / golden chunk）。

**2. 生成层（generation）**——在「给定召回上下文」的前提下衡量答案质量：

- **Faithfulness / 忠实度**：答案是否**只由上下文支撑**，有没有编造，直接对应幻觉。
- **Answer Relevance**：答案是否切题、回应了 query。
- **Context Utilization**：召回的关键信息有没有被用上。
- 有标准答案时再加 **correctness / EM / F1**。

**3. 端到端**：用户视角的整体正确率、有用性，常配人工评分或线上 A/B（点击、采纳、追问率）。

**评测方法**

- **分段评测（component-wise）**：检索层、生成层各自独立打分，便于**定位瓶颈**——recall 低就修检索（chunk、embedding、rerank），faithfulness 低就修 prompt 或上下文质量。
- **端到端评测**：固定 pipeline 看最终答案，贴近真实体验但难归因。
- **LLM-as-a-Judge**：用强模型按 rubric 给 faithfulness / relevance 打分，省去人工标注；要注意校准与偏置，关键场景仍需人工抽检。

**常用框架**：**RAGAS**（faithfulness、answer/context relevance、context precision/recall 一套现成指标）、**TruLens**、**DeepEval**、**LlamaIndex / LangSmith** 自带的评测模块。

一句话：**检索层用 recall/precision/nDCG 看「捞得准不准」，生成层用 faithfulness/answer-relevance 看「答得实不实」，再叠端到端看用户价值**；分段定位瓶颈、端到端兜底体验，离线指标 + 线上反馈一起看才靠谱。

## 延伸 / 追问

**追问：没有标注好的 golden 数据集，怎么冷启动评测？**

两条路并行：① **合成评测集**——用 LLM 从文档里反向生成「问题 + 对应来源片段」，快速攒出一批 query→golden chunk，人工抽检纠偏即可上线，RAGAS 等都内置 testset 生成；② **无参考指标（reference-free）**——faithfulness、answer/context relevance 这类不需要标准答案，靠 LLM-as-a-Judge 对「答案 vs 上下文」「答案 vs 问题」打分就能跑，先把忠实度和相关性的回归基线立起来。再叠线上信号（采纳率、点踩、人工追问）持续回流，逐步把高价值 query 沉淀成真正的标注集。一句话：先合成 + 无参考指标冷启动，再用线上反馈滚出金标准。

## 参考

- RAGAS Docs，*Metrics（faithfulness / answer relevancy / context precision & recall）*：https://docs.ragas.io/en/stable/concepts/metrics/
- Es et al., *RAGAS: Automated Evaluation of Retrieval Augmented Generation*, 2023：https://arxiv.org/abs/2309.15217
- TruLens Docs，*The RAG Triad（context relevance / groundedness / answer relevance）*：https://www.trulens.org/getting_started/core_concepts/rag_triad/
