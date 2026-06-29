---
id: agent-0031
title: 上下文工程有哪些需要注意的点
category: agent
tags: [agent, context-engineering, context-window, memory, compaction, rag]
difficulty: medium
role: engineer
contributor: 佚名
source: 腾讯
status: published
updated: 2026-06-29
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-29
    updated: 2026-06-29
---

## 问题

上下文工程有哪些需要注意的点？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-29

**一句话：** 上下文工程的核心是「在有限的窗口预算里，每一轮都装入**信噪比最高**的信息」。目标不是塞得多，而是**恰好够用且组织良好**。要注意的点可归为下面五类。

```
   ┌──────────── Context Window（有限预算）────────────┐
   │ System │ 工具定义 │ 历史/记忆 │ 检索片段 │ 工具结果 │ 本轮指令 │
   └───┬────────┬─────────┬──────────┬─────────┬────────┘
      稳定      精简       滚动摘要    top-k      裁字段    清晰
     (可缓存)  (按需载)   (防膨胀)   (防淹没)   (防爆窗)  (放头尾)
```

**1. 预算与膨胀控制（最关键）**
窗口是稀缺资源。Agent 多步循环会让工具结果、历史不断累积，必须主动管理 token 预算：对历史**滚动摘要（compaction）**、丢弃过期的工具输出、限制单次召回的片段数。否则会触发三重代价——成本/延迟上升、超窗硬截断、以及注意力被稀释。

**2. 信息组织与位置**
模型对长序列**中段信息更易忽略**（"lost in the middle"）。所以要把最关键的信息放在**头部或尾部**，用清晰的分隔符/标签区分各部分（系统指令、知识、工具结果、用户问题），并保持**结构稳定**——越靠前越稳定的内容越能命中 **prompt cache**，省钱省延迟。

**3. 检索的「准」而非「全」**
RAG 注入要按相关性 **top-k 召回**，宁缺毋滥。无关片段不只是浪费 token，更会主动干扰模型、制造幻觉。注意 chunk 粒度、rerank 排序、以及召回内容与问题的对齐。

**4. 记忆与状态的读写**
区分短期（对话状态）与长期（向量记忆）。要点：写入要去重、设过期/淘汰策略；读取要按需召回而非全量回放；避免把记忆当垃圾桶，越脏的记忆越拖累后续每一轮。

**5. 工具结果治理**
一条冗长 JSON 能吃掉半个窗口。只保留**有用字段**，对大返回做摘要或分页，错误信息保留可定位的关键部分即可。工具定义本身也要精简——工具过多会抬高选错工具的概率。

**几个常见反模式（要避免）：**

| 反模式 | 后果 | 对策 |
| --- | --- | --- |
| 「窗口越大越好，全塞进去」 | 注意力稀释、context rot、贵 | 按预算召回 + 压缩 |
| 历史只增不减 | 膨胀、超窗截断 | 滚动摘要 + 丢弃过期项 |
| 检索图省事召回 top-50 | 关键信息被噪声淹没 | 精召回 + rerank |
| 每轮重排系统提示 | 缓存失效、成本翻倍 | 稳定前缀，变动放后段 |
| 工具原始结果直接回填 | token 爆炸 | 裁字段 / 摘要 |

**一句话总结：** 上下文工程 = **预算管理 + 信息组织 + 精准供给**。把窗口当成需要精打细算的「黄金内存」，每一轮都问一句：「这条信息，真的值得占这个位置吗？」

## 延伸 / 追问

**追问：上下文「越长越好」吗？长上下文模型出来后，是不是就不用做上下文工程了？**

不是。即便窗口涨到百万 token，也不能免去上下文工程，原因有三：① **注意力与召回率**——长上下文中段信息更易被忽略，有效利用率随长度下降（context rot），塞满 ≠ 用好；② **成本与延迟**——token 量直接抬高费用和首字延迟，长上下文每一步都更贵更慢；③ **信噪比**——无关内容会主动干扰推理、诱发幻觉，多塞往往是负收益。长窗口降低的是「装不下」的硬约束，但「该装什么、怎么排、何时裁」这个工程问题依旧存在，甚至更重要——窗口越大，越需要纪律去管。实践上仍要：精准召回、滚动压缩、稳定前缀复用缓存。与「Prompt 与 Context Engineering 的区别」可对照阅读 [agent-0019](agent-0019-prompt-vs-context-engineering.md)。

## 参考

- Anthropic Engineering，*Effective Context Engineering for AI Agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Liu et al., *Lost in the Middle: How Language Models Use Long Contexts*, 2023：https://arxiv.org/abs/2307.03172
- Anthropic，*Prompt caching*：https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
