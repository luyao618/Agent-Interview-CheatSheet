---
id: rag-0027
title: 如何评估 RAG 检索质量
category: rag
tags: [rag, retrieval-evaluation, recall, ndcg, mrr]
difficulty: medium
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

如何评估 RAG 的**检索质量**？常用哪些指标？评测集怎么构建？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

只评检索层（生成质量另算）。检索质量回答两件事：**该命中的片段捞没捞到（召回）、相关的排没排在前面（排序）**。所以指标分两组：

```
query ─► 检索 ─► topK 候选
            ├─ 召回得失 → Recall@k / Hit Rate@k
            └─ 排序质量 → Precision@k / MRR / nDCG@k
```

**指标语义与选型**

| 指标 | 衡量 | 关注 |
| --- | --- | --- |
| Recall@k | 应命中片段有多少进 topK | 漏没漏 |
| Hit Rate@k | topK 内是否命中任一相关片段 | 捞没捞到（命中即 1） |
| Precision@k | topK 中真相关的占比 | 脏不脏 |
| MRR | 首个相关片段排名的倒数均值 | 首条靠不靠前 |
| nDCG@k | 带位置折扣的排序质量 | 相关的排没排前面 |

- 只需「上下文够不够全」→ 看 **Recall@k / Hit Rate@k**；
- 关心「reranker 后排序好不好」→ 看 **MRR / nDCG@k**；
- topK 进 prompt 有 token 预算、怕噪声 → 加 **Precision@k**。
- k 要贴合线上真实截断（如送 5 条就评 @5），别拿 @20 自我安慰。**nDCG 在多相关、分等级时最全面**；二元相关时 MRR/Hit Rate 更直观。

**评测集构建（这是关键，指标只是尺子）**

1. **query 取真实分布**：从线上日志采样真实问句，覆盖高频、长尾、多意图，别只用自己编的顺口问题。
2. **标注 ground-truth chunk**：对每条 query 标出「应被召回」的片段 id（golden set）。来源：人工标注、已有 QA 对回链、或大模型辅助标注 + 人工抽检。
3. **规模与平衡**：先 100–300 条起步覆盖主要类型，难/易、单跳/多跳分层，避免被简单样本拉高均值。
4. **固定与版本化**：评测集冻结、纳入版本管理，换 embedding / chunk / reranker 时同集对比，才能归因。

**落地方法**：把上面打包成离线回归集，对 (embedding 模型、chunk 策略、topK、是否 rerank) 做网格对比，取 Recall@k、nDCG@k 的拐点配置；用 Ragas / TruLens 等可自动算 context recall / precision。线上再用点击、引用率、人工满意度做代理验证，离线指标涨而线上不涨要回查评测集是否失真。

## 延伸 / 追问

**追问：没有人工标注的 ground-truth，怎么快速搭一版可用的检索评测？**

两条捷径。① **反向构造**：拿已有文档片段，让大模型基于该片段生成一个「只有它能回答」的问题，(问题→源片段) 天然就是 query-标签对，几小时能造几百条，再人工抽检剔除泛化/跨片段的脏样本。② **弱信号代理**：用线上点击/采纳、用户是否追问、答案是否引用了召回片段做近似标签，规模大但有噪声，适合趋势监控而非精确归因。务实做法是两者结合——LLM 造集做离线回归找配置拐点，线上弱信号做长期守门；切记 LLM 生成的问题偏「片段内可答」，会高估真实长尾召回，关键版本仍需小规模人工标注校准。

## 参考

- Ragas Docs，*Context Recall / Context Precision*：https://docs.ragas.io/en/stable/concepts/metrics/
- Pinecone Learn，*Evaluation Measures in Information Retrieval*（Recall/MRR/nDCG）：https://www.pinecone.io/learn/offline-evaluation/
- TruLens Docs，*The RAG Triad*：https://www.trulens.org/getting_started/core_concepts/rag_triad/
