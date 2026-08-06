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

RAPTOR（递归聚类 + 树形层次摘要）和 GraphRAG（实体关系图 + 社区摘要）都想解决"朴素 RAG 答不了全局/结构性问题"的痛点。二者分别适合回答什么类型的问题？如何按查询类型选型？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-06

**先看两者的索引结构，问题类型是从结构长出来的。** RAPTOR 把 chunk **递归聚类 + 逐层摘要**，建成一棵"叶子=原文细节、越往上越抽象"的**摘要树**；检索时可跨层取，既够到细节又够到主题概括。GraphRAG 先抽**实体-关系三元组**建知识图，再对图做**社区划分 + 社区摘要**；检索时沿实体的边多跳游走，或读社区摘要。**一个擅长"主题层次的归纳"，一个擅长"实体之间的关系推理"。**

```
RAPTOR：主题聚类树               GraphRAG：实体关系图
        ▲摘要(全局主题)              (社区摘要)
      ／  ＼                        ●──关系──●──关系──●
   摘要    摘要 (子主题)              │        │        │
  ／＼    ／＼                        ●────────●        ●
叶 叶   叶 叶 (原文细节)         多跳：A→B→C 的连接
```

**各自的擅长题型：**

| 查询类型 | 更适合 | 为什么 |
| --- | --- | --- |
| 全局总结 / "这批文档讲了啥" | RAPTOR | 高层摘要节点天然是主题归纳 |
| 局部事实 / 单点问答 | RAPTOR（叶层）| 直接命中细节 chunk，无需建图开销 |
| 主题式跨文档归纳 | RAPTOR | 聚类把同主题内容拢到一棵子树 |
| 多跳关系 / "A 和 C 通过谁关联" | GraphRAG | 沿边游走是它的原生能力 |
| 实体为中心的聚合 | GraphRAG | "某人涉及的所有事件/关系"一跳可达 |
| 关系型全局（跨实体的宏观结构）| GraphRAG（社区摘要）| 社区摘要覆盖实体簇的整体图景 |

**一句话选型：** 问题是**"主题/内容层面的概括与细节"**→RAPTOR；问题是**"实体之间怎么连、多跳推理、以实体为中心聚合"**→GraphRAG。RAPTOR 便宜、对非结构化叙述型语料友好；GraphRAG 建图贵、但对关系密集、需要多跳的知识型语料不可替代。二者不互斥——可并存做**混合检索**，按 query 意图路由，甚至把 GraphRAG 的社区摘要也喂给树，取长补短。

## 延伸 / 追问

**追问：给定一个新语料和一批真实 query，怎么快速判断该上 RAPTOR、GraphRAG，还是都不上？**

先看**语料**再看**query 分布**，别一上来就建重索引。三步：① **query 画像**——统计真实问题里"全局总结/主题归纳"多，还是"谁和谁什么关系/多跳"多；前者偏 RAPTOR，后者偏 GraphRAG。若绝大多数是单点事实问答，**朴素 RAG + rerank 往往就够**，别为少数长尾上重索引。② **语料结构**——实体密集、关系明确（人物、事件、组织、引用网络）才值得抽图建 GraphRAG；纯叙述型长文档（报告、书籍）用 RAPTOR 的主题树更划算。③ **成本/时效权衡**——GraphRAG 抽三元组 + 社区摘要的离线构建与更新成本高，语料频繁变更时维护贵；RAPTOR 重建也不便宜但更轻。落地建议：先用朴素 RAG 跑基线、用真实 query 做评测，只有当"全局/关系型问题"确实占比高且基线答不好时，再按上面的画像针对性引入 RAPTOR 或 GraphRAG，而非默认全都上。

## 参考

- Sarthi et al., *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval*, 2024：https://arxiv.org/abs/2401.18059
- Edge et al., *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*, 2024：https://arxiv.org/abs/2404.16130
- Microsoft Research, *GraphRAG*：https://microsoft.github.io/graphrag/
