---
id: agent-0033
title: Agent 工程师需要具备哪些技能和能力
category: agent
tags: [agent, career, skills, engineering, context-engineering, evaluation]
difficulty: medium
role: engineer
contributor: 佚名
source: 未知
status: published
updated: 2026-07-02
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-07-02
    updated: 2026-07-02
---

## 问题

你认为 Agent 工程师需要具备哪些技能和能力？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-07-02

这是一道考察「岗位画像认知」的开放题，答法不是罗列名词，而是给出一个**分层的能力模型**并说清各层为何必要。Agent 工程师本质是「把不确定的 LLM 装进确定的工程系统」，因此能力可分为四层：

```
        ┌─────────────────────────────┐
  L4    │  产品判断 / 场景抽象 / 成本意识   │  ← 决定「做不做、怎么落地」
        ├─────────────────────────────┤
  L3    │  系统工程：编排·并发·容错·可观测   │  ← 决定「稳不稳、扩不扩得动」
        ├─────────────────────────────┤
  L2    │  Agent 核心：上下文·记忆·工具·评测 │  ← 决定「Agent 好不好用」
        ├─────────────────────────────┤
  L1    │  LLM 基本功：Prompt·采样·局限认知  │  ← 一切的地基
        └─────────────────────────────┘
```

**L1 · LLM 基本功。** 理解模型能力边界与失败模式：幻觉、指令遵循随上下文变长而衰减、采样参数（temperature / top-p）对稳定性的影响。知道「什么该交给模型、什么必须由代码兜底」。

**L2 · Agent 核心能力（差异化所在）。**
- **上下文工程**：在正确的时刻把正确且足量的信息喂进窗口——相关性筛选、预算裁剪、结构化版式，这是单步质量的瓶颈。
- **记忆与检索**：短期 / 长期记忆设计、RAG 召回与 rerank、超窗时的滚动摘要。
- **工具与协议**：Function Calling / MCP 的设计与安全边界、tool registry、防无限循环。
- **评测（最易被忽视）**：能把「Agent 好不好」变成可量化指标（任务成功率、工具选择准确率、轨迹回放），没有评测就没有迭代。

**L3 · 系统工程。** Agent 是长时、有状态、会调外部副作用的系统：需要并发与幂等、checkpoint / resume、超时重试与降级、全链路 tracing 与成本监控。这是把 demo 变成生产的关键。

**L4 · 产品与判断。** 能把模糊业务需求抽象成 Agent 能执行的任务边界，判断「该不该上 Agent、还是用 workflow / RPA 更划算」，并对延迟、token 成本、失败代价做权衡。

**一句话**：Agent 工程师 = **扎实的 LLM 认知（L1） + 上下文/记忆/工具/评测的核心内功（L2） + 生产级系统工程（L3） + 产品成本判断（L4）**；其中真正拉开差距的是 L2 的上下文工程与评测能力。

> **要点**
> - 用「四层能力模型」作答，而非平铺名词
> - L2 是差异化：上下文工程 + 记忆检索 + 工具协议 + **评测**
> - 强调评测与系统工程（幂等/可观测/成本）常被低估
> - 顶层是产品判断：该不该上 Agent、成本怎么权衡

## 延伸 / 追问

**追问：如果只能优先培养一项能力，你会选哪个？为什么？**

我会选 **评测（Evaluation）能力**。理由是：其余能力——上下文、记忆、工具、编排——本质都是「优化动作」，而优化的前提是有一把**可信的尺子**。没有评测，你无法判断改 prompt、换模型、加 rerank 到底是变好还是变坏，只能凭感觉调参，迭代退化成碰运气。

具体要会：① 构建贴近真实场景的评测集（含边界与对抗样本）；② 设计分层指标——端到端任务成功率、单步工具选择准确率、检索命中率、轨迹可回放；③ 用 LLM-as-judge 做规模化打分，同时用人工样本校准 judge 本身的偏差；④ 把评测接入 CI，让每次改动都能看到指标涨跌。一句话：**上下文工程决定单步上限，评测能力决定整个系统能不能持续变好**——所以在真实项目里我会最先把评测闭环搭起来，参见 [有哪些 RAG/Agent 评测维度](agent-0018-rag-agent-eval-dimensions.md)。

## 参考

- Anthropic, *Building Effective Agents*, 2024：https://www.anthropic.com/research/building-effective-agents
- Anthropic, *Effective context engineering for AI agents*, 2025：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- OpenAI, *A practical guide to building agents*, 2025：https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
