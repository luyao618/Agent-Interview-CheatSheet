---
id: agent-0019
title: Prompt Engineering 和 Context Engineering 有什么区别
category: agent
tags: [agent, prompt-engineering, context-engineering, context-window, rag]
difficulty: medium
role: both
contributor: 佚名
source: 字节跳动
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

Prompt Engineering 和 Context Engineering 有什么区别？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

**一句话区分：** Prompt Engineering 是**「把一次指令写好」**——优化你直接写给模型的那段话；Context Engineering 是**「把进入上下文窗口的全部信息管理好」**——在每一轮里决定哪些记忆、检索片段、工具结果、历史该放进窗口、放多少、怎么排、何时裁。前者关心**措辞**，后者关心**信息的供给与组织**。

```
            ┌──────────────  Context Window (有限预算)  ──────────────┐
            │  System Prompt │ 工具定义 │ 历史/记忆 │ 检索片段 │ 工具结果 │ 本轮指令 │
            └────────┬───────────────────────────────────────┬─────────┘
                     │                                        │
  Prompt Eng. ──► 只打磨「本轮指令 / System Prompt」的措辞      │
                                                              │
  Context Eng. ──► 决定上面每一格「放什么、放多少、怎么排、何时裁」
                   (检索 / 记忆读写 / 压缩摘要 / 顺序 / 预算分配)
```

**维度对比：**

| 维度 | Prompt Engineering | Context Engineering |
| --- | --- | --- |
| 对象 | 单条指令、System Prompt 的文字 | 整个上下文窗口里的所有信息 |
| 关注点 | 措辞、角色、示例、输出格式 | 检索、记忆、裁剪、排序、token 预算 |
| 时态 | 偏静态（写一次） | 偏动态（每轮按状态重新组装） |
| 典型手段 | few-shot、CoT、角色设定、格式约束 | RAG、记忆读写、摘要压缩、上下文窗口管理、工具结果筛选 |
| 失败表现 | 模型「听不懂/答跑题」 | 信息缺失、被无关内容淹没、超窗截断 |

**为什么会从 Prompt 演进到 Context：** 单轮问答时，写好 prompt 基本就够了。但 Agent 是**多步循环**：每一步都会产生新的工具结果、观测和记忆，上下文是**不断累积**的。窗口预算有限，塞满了会触发截断、抬高成本、还会因无关内容稀释注意力（"lost in the middle"、context rot）。于是重点从「这句话怎么写」转向「**这一轮到底该把哪些信息喂给模型**」——这正是 Context Engineering 要解决的工程问题。

**核心包含的工作：**

1. **检索（Retrieval）** — RAG 把外部知识按相关性召回并注入，而非全量塞入。
2. **记忆（Memory）** — 短期对话状态、长期向量记忆的读写与召回。
3. **裁剪 / 压缩（Compaction）** — 摘要历史、丢弃过期工具结果、控制 token 预算。
4. **组织（Structuring）** — 信息的顺序、分隔、优先级，把最关键的放在模型最敏感的位置。
5. **工具结果治理** — 只保留有用的返回字段，避免一条冗长 JSON 吃掉半个窗口。

**关系而非对立：** Context Engineering 是 Prompt Engineering 的**超集**——Prompt 是其中「本轮指令措辞」这一格的优化，Context 关心的是**整个窗口在每一轮如何被装配**。一句话总结：**Prompt 决定「怎么问」，Context 决定「带着什么信息去问」**；做 Agent，后者往往是决定可靠性的关键。

## 延伸 / 追问

**追问：上下文越长越好吗？为什么还要主动裁剪？**

不是。长上下文有三重代价：① **成本与延迟**——token 量直接抬高费用与首字延迟；② **注意力稀释**——模型对长序列中段信息更易忽略（"lost in the middle"），无关内容会挤占对关键信息的注意力，即 context rot；③ **硬截断风险**——超窗会丢尾部信息甚至破坏结构。因此工程上要做**上下文预算管理**：只召回 top-k 相关片段、对历史滚动摘要、丢弃过期的工具输出、把最关键信息放在头尾。目标不是「装得多」，而是**在有限预算内让信噪比最高**——给模型恰好够用、且组织良好的信息，比给它一切都重要。具体「上下文工程要注意哪些点、有哪些反模式」可参见 [agent-0031 上下文工程有哪些需要注意的点](agent-0031-context-engineering-key-points.md)。

## 参考

- Anthropic Engineering，*Effective Context Engineering for AI Agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic Engineering，*Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
- Liu et al., *Lost in the Middle: How Language Models Use Long Contexts*, 2023：https://arxiv.org/abs/2307.03172
