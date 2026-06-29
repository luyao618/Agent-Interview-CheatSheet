---
id: agent-0029
title: Agent 设计里，你觉得最重要的部分是什么
category: agent
tags: [agent, context-engineering, architecture, reliability, design]
difficulty: medium
role: engineer
contributor: 佚名
source: 未知
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

Agent 设计里，你觉得最重要的部分是什么？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-29

这是一道考察「设计判断力」的开放题——没有唯一答案，关键是给出一个有取舍、能自圆其说的主轴。我的回答：**上下文工程（Context Engineering）是 Agent 设计的第一性问题**。

**为什么是它，而不是模型 / 工具 / 框架？**

Agent 的每一步本质都是一次 LLM 调用，模型的行为完全由那一刻「窗口里有什么」决定。模型选型、工具集、记忆、规划，最终都要落到「在正确的时刻，把正确且足量的信息喂进上下文」——这件事做不好，再强的模型也会跑偏。所以上下文不是众多模块之一，而是**所有模块汇聚、并决定单步质量的瓶颈**。

```
   目标 / 历史 ─┐
   工具描述   ─┤
   检索结果   ─┼──▶ 上下文工程 ──▶ LLM 单步 ──▶ 动作
   记忆 / 状态 ─┤    （选什么·放多少·     ↑
   约束 / 规则 ─┘     怎么排·何时压缩）   反馈回灌
```

**好的上下文工程要解决三件事：**

1. **相关性**：只放当前这一步真正需要的信息，把无关内容挡在窗口外（注意力会被噪声稀释，关键信息易被「淹没」）。
2. **预算**：窗口和 token 都有成本，要对历史做摘要 / 裁剪 / 分页，而不是无脑全塞——长上下文还会显著降低指令遵循度。
3. **结构**：用稳定的版式（系统约束、工具、当前任务分区呈现），让模型每一步都「站在确定的地基上」决策。

**这如何统领其他设计？** 记忆系统是「上下文的持久层」，工具设计是「上下文里可用动作的表达」，多 Agent 拆分本质是「给每个角色更短更干净的上下文」，可靠性（防幻觉、防绕圈）也大多源于上下文的噪声与缺失。它们都在为「这一步窗口里放什么」服务。

**一句话**：模型决定能力上限，**上下文工程决定这份能力在每一步能否真正兑现**——所以面试里我会把它作为 Agent 设计的核心抓手，再据此展开记忆、工具与编排。

> **要点**
> - 主轴选「上下文工程」，并说明它是单步质量的瓶颈
> - 相关性 / 预算 / 结构三个落点
> - 解释它如何统领记忆、工具、多 Agent 与可靠性

## 延伸 / 追问

**追问：把「上下文工程」当核心听起来有点虚，落到工程上有哪些具体抓手？**

可以拆成四个可动手的层面：① **检索与筛选**——按当前步动态拼上下文，用 RAG / 工具结果过滤 + rerank，只注入 top-k 相关片段，而非全量历史；② **压缩与记忆**——超窗时对历史做滚动摘要，把长期事实写入外部记忆（向量库 / KV），下次按需召回，参见 [agent-0023 超长上下文怎么处理？记忆模块怎么设计](agent-0023-long-context-memory-module.md)；③ **结构化版式**——固定分区（system 约束 / 工具 / 任务 / 草稿区），用分隔符和稳定顺序提升指令遵循度；④ **可观测**——埋点「上下文占用率、关键信息命中率、工具选择错误率」，把上下文质量变成可量化、可调优的指标。这四点合起来，就是把「虚」的理念变成能迭代的工程闭环。

## 参考

- Anthropic, *Building Effective Agents*, 2024：https://www.anthropic.com/research/building-effective-agents
- Anthropic, *Effective context engineering for AI agents*, 2025：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- LangChain, *Context Engineering*：https://blog.langchain.com/context-engineering-for-agents/
