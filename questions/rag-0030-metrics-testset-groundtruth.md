---
id: rag-0030
title: 评价指标、测试集、ground truth 如何定义
category: rag
tags: [rag, evaluation, metrics, test-set, ground-truth]
difficulty: medium
role: engineer
contributor: 佚名
source: XTransfer
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

评价指标、测试集、ground truth 如何定义？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

核心结论：这三者是「**目标 → 数据 → 标准**」一条链——**指标**回答「成功长什么样」，**测试集**是「拿来量的样本」，**ground truth** 是「量的那把尺子」。难点不在选指标，而在**把口径定清楚、把标注做一致**，否则指标再漂亮也不可信。

```
评测目标 ──► 指标(怎么量) ──► 测试集(量什么) ──► ground truth(对照基准)
  分层归因      检索/生成分开     覆盖真实分布       标注口径 + 一致性
```

**1. 评价指标（怎么量）——先分层，再选可归因的指标**

RAG 必须把检索和生成拆开，否则指标一动分不清是谁的锅：

- **检索层**：Recall@k / Hit Rate（漏没漏）、Precision@k / MRR / nDCG@k（排没排在前面）。
- **生成层**：忠实度 faithfulness（有没有依据召回片段、是否幻觉）、答案相关性、正确性（对照参考答案）。
- **端到端**：任务成功率 / 人工或 LLM-judge 打分，配延迟、成本等工程指标。

定义指标时**先明确决策用途**（上线门槛？AB 对比？）再选，并固定 `k`、阈值、聚合方式（按 query 平均还是按 token），口径写进文档。

**2. 测试集（量什么）——代表性 + 分层 + 防泄漏**

- **来源**：优先真实线上 query（采样脱敏），而非全靠人造，保证分布贴近生产。
- **分层覆盖**：按难度、问题类型（事实/多跳/对比）、领域、**可答 vs 不可答**分桶，每桶留足样本，便于切片归因。
- **规模**：起步几十~几百条精标，比上千条糙标更有用；持续把线上 badcase 回流进集。
- **防泄漏**：评测集不得进训练/调 prompt 的迭代数据，避免「背答案」。

**3. Ground truth（对照基准）——标注口径与一致性是命门**

一条样本的 ground truth 通常含：**应命中的文档/片段**（golden chunk，给检索层）+ **参考答案**（给生成层）。关键不是「标了」，而是「标得准且一致」：

- **写标注规范（rubric）**：什么算「相关」、部分相关怎么算、开放题按要点给分还是整体，先用例子把边界钉死。
- **多人标 + 测一致性**：用 Cohen's κ / 一致率衡量标注员间分歧，低了就回去改规范，而不是硬合。
- **仲裁机制**：分歧样本由资深标注/专家裁决，沉淀成新规范条目。
- **承认主观**：开放生成题没有唯一答案，用「可接受答案集合 + 要点 rubric」代替单一字符串匹配，必要时上 LLM-judge 但要先校准它与人工的一致性。

一句话：**指标定方向、测试集保代表性、ground truth 靠口径与一致性立信**——三者对齐，评测结论才敢用来做决策。

## 延伸 / 追问

**追问：开放式生成、没有唯一标准答案的题，ground truth 怎么落地？**

放弃「唯一字符串」，改用三种可操作形态：① **要点式 rubric**——把参考答案拆成必须命中的关键点（覆盖率/扣分项），按要点计分，容忍措辞差异；② **可接受答案集合**——枚举多个等价正确表述，配语义相似度（而非精确匹配）判定；③ **成对偏好**——不打绝对分，只判 A/B 哪个更好，做模型/版本相对比较，标注更稳。再叠 **LLM-as-judge** 提效，但必须先用一批人工标注**校准** judge（测它与人工的一致性、检查位置/长度偏置），并定期抽样人工复核，防止「裁判自己飘了」。最终 ground truth 不是一次定死的静态答案，而是**规范 + 样例 + 仲裁记录**共同构成、随 badcase 持续演进的活资产。

## 参考

- Ragas Docs，*Metrics（faithfulness / answer relevancy / context recall）*：https://docs.ragas.io/en/stable/concepts/metrics/
- LlamaIndex Docs，*Evaluation*：https://docs.llamaindex.ai/en/stable/module_guides/evaluating/
- Anthropic Docs，*Create strong empirical evaluations*：https://docs.anthropic.com/en/docs/test-and-evaluate/develop-tests
