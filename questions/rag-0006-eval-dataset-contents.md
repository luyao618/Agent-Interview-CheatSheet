---
id: rag-0006
title: 评测数据集一般包括哪些内容
category: rag
tags: [rag, evaluation, dataset, ground-truth, golden-set]
difficulty: easy
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

（RAG / 大模型）评测数据集一般包括哪些内容？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

核心结论：一条评测样本的本质是 **「输入 → 标注的正确依据 → 期望输出 → 评分口径」** 四件套；RAG 场景在「依据」上要额外把**应命中的文档/片段**标出来，才能把检索和生成分层归因。

**一条样本的典型字段**

```
{
  query:          用户问题 / 输入
  relevant_docs:  应命中的文档/片段标注(golden chunk + 来源)
  reference:      参考答案 / 期望输出(ground-truth)
  meta:           难度、类型、领域、是否可答
  judge:          评分方式与判分标准(rubric / 指标)
}
```

**1. 输入（query）**：真实或仿真的用户问题，是评测的触发点。

**2. 相关文档 / 片段标注（relevant_docs）**：RAG 特有且最关键——标出该 query 应命中的 golden chunk 及其来源 doc_id，用于算 recall@k、precision、nDCG，判「检索捞得准不准」。

**3. 参考答案（reference / ground-truth）**：期望输出，用于算 correctness / EM / F1，或作 LLM-as-a-Judge 的对照基准。也包含**负样本**（无答案/不可答），考察模型该拒答时是否拒答，防幻觉。

**4. 分层元数据（meta）**：难度（easy/hard）、问题类型（事实型 / 多跳 / 推理 / 摘要）、领域、语言等标签。分层是为了**分桶看指标**——不能只看一个总分，要能定位「多跳题崩了」还是「长文档崩了」。

**5. 评分口径（judge）**：每条样本绑定的判分方式与 rubric——精确匹配、指标公式，还是 Judge 模型按标准打分，保证可复现。

```
难度分层  ┌ easy  ┐
          ├ medium├─► 分桶统计，定位短板
类型分层  └ hard  ┘   (事实/多跳/摘要/拒答…)
```

**构建与维护**：来源上①线上真实 query 采样脱敏，②专家人工标注，③LLM 合成「问题+来源片段」再人工抽检纠偏。维护上要控制覆盖度与分布均衡、定期随业务更新、防训练集泄漏污染，并对标注做一致性校验。

一句话：评测集 = query + 标注依据（RAG 加 golden chunk）+ 参考答案（含负样本）+ 分层标签 + 评分口径，分层标注才能从「分数」追到「哪类、哪一层出了问题」。

## 延伸 / 追问

**追问：评测集和训练集在内容构成上有什么不同？**

目的不同决定构成不同。训练集追求**规模与多样性**，喂的是「输入→期望输出」的学习信号，可带噪声、可数据增强，越多越好。评测集追求**代表性、纯净与可复现**：规模可以小但分布要贴近真实线上、难度/类型要分层覆盖、标注要精准且做一致性校验，还必须显式带 golden 依据与评分口径。最关键的一条铁律是**两者严格隔离、零重叠**——评测样本一旦进过训练，指标就被数据泄漏污染、虚高失真。所以评测集通常单独冻结一个版本、长期不变，作为可回归对比的「金标准」。

## 参考

- RAGAS Docs，*Testset Generation（合成评测集 query + reference context）*：https://docs.ragas.io/en/stable/concepts/test_data_generation/
- Microsoft，*Evaluation of RAG / generative AI（ground truth 数据集构成）*：https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-generation-evaluation
- Google Research，*Natural Questions: a Benchmark for QA Research*（含 query / 标注答案 / 来源段落）：https://ai.google.com/research/NaturalQuestions
