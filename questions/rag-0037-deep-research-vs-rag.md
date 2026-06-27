---
id: rag-0037
title: Deep Research 是什么？还算不算 RAG
category: rag
tags: [deep-research, rag, agent, multi-step-retrieval, report-generation]
difficulty: medium
role: both
contributor: 佚名
status: published
updated: 2026-06-27
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-27
    updated: 2026-06-27
---

## 问题

Deep Research 是什么？它还算不算 RAG？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-27

一句话结论：**Deep Research 是一种「Agent 驱动的多轮检索 + 综合写作」工作流，它内含 RAG，但不等于 RAG**——把 RAG 从「一问一答的单跳检索」升级成了「自主规划、多源迭代、带验证和引用的研究报告」。

**Deep Research 是什么。** 它指 OpenAI / Google / Perplexity 等推出的一类产品形态：你给一个开放性问题（如「对比三家云厂商的向量数据库定价与性能」），系统不是检索一次就答，而是像研究员一样**自己拆解子问题 → 反复搜索 → 阅读多个来源 → 交叉验证 → 产出一篇带引用的长报告**，整个过程可能跑几分钟、调用几十上百次搜索与网页抓取。核心是「Agent + 检索 + 推理」三者的深度耦合。

**典型流程：**

```
用户问题
   │
   ▼
① 规划 Plan ── 把大问题拆成若干子问题/检索意图
   │
   ▼
② 检索循环 (多轮) ◄──────────┐
   ├─ search/browse 取来源     │ 信息不足/有矛盾
   ├─ 阅读 + 抽取关键事实       │ → 生成新查询继续
   └─ 反思: 够了吗? 有冲突吗? ──┘
   │ 充分
   ▼
③ 综合 Synthesize ── 归纳、消解冲突、组织结构
   │
   ▼
④ 带引用的研究报告 (可溯源)
```

**它和经典 RAG 的关系——为什么说「算，但不止」：**

| 维度 | 经典 RAG | Deep Research |
| --- | --- | --- |
| 检索轮次 | 单跳（一次召回） | 多跳、迭代，按需追加查询 |
| 控制流 | 固定 pipeline | Agent 自主规划 + 反思 |
| 信息源 | 通常单一向量库 | 网页/向量库/工具多源混合 |
| 输出 | 一段答案 | 结构化长报告 + 引用 |
| 验证 | 一般无 | 交叉验证、消解矛盾 |

可以把它理解为 **Agentic RAG 的一个落地形态**：检索增强这一底层范式没变（仍是「先取相关材料、再让模型基于材料生成、并给出出处」），但**外面套了一层 Agent 的规划-执行-反思循环**，把「检索」从一次性动作变成了一个可以自我驱动、自我纠错的子任务。所以面试时更准确的说法是：**Deep Research ⊃ RAG**——它必然用到 RAG 的检索-生成内核，但额外引入了任务分解、多轮 orchestration、来源批判与报告综合，这些是经典 RAG 不强调的。需要澄清的是，这里的「⊃ / 包含」是**产品与 workflow 层面包含了 retrieval-augmented generation 这一内核**，并非说所有 Deep Research 实现都等同于一条传统的 vector-store RAG pipeline——具体检索后端可以是网页搜索、API 工具或向量库，形态各异。

**一句话回答面试官：** Deep Research 不是要取代 RAG，而是 RAG 在「开放式、需要多源调研」场景下的自然演进——把单跳检索包进 Agent 的迭代循环里，换来更深的覆盖、可验证性和可溯源的长篇产出，代价是更高的延迟和 token 成本。

## 延伸 / 追问

**追问：既然 Deep Research 更强，是不是以后都该用它替代普通 RAG？**

不该一刀切，**按「问题的开放度」和「成本/延迟预算」选型**。Deep Research 的优势（多轮、跨源、可验证）是用代价换来的：单次任务往往要几分钟、几十到上百次检索调用，token 与费用是普通 RAG 的一两个数量级，还更难做到稳定低延迟。

适合 Deep Research 的：开放式、需要综合多个来源、答案没有现成单一出处的调研型任务（竞品分析、技术选型、文献综述、尽调）。

适合经典单跳 RAG 的：答案能在知识库里一次命中的事实型/客服型问答、对延迟敏感（要秒级响应）、高并发低成本的线上场景。

工程上的务实做法是**分层**：先用一次廉价的单跳 RAG 试答，命中且置信度高就直接返回；只有当问题被判定为「开放/复杂/信息不足」时，再升级到 Deep Research 的多轮 Agent 循环。这样兼顾了大多数请求的成本与少数复杂请求的深度。

## 参考

- OpenAI，*Introducing deep research*：https://openai.com/index/introducing-deep-research/
- Google Gemini，*Deep Research*：https://gemini.google/overview/deep-research/
- Anthropic，*Building effective agents*：https://www.anthropic.com/engineering/building-effective-agents
- Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, 2020：https://arxiv.org/abs/2005.11401
