---
id: agent-0027
title: 单 Agent 遇瓶颈时，为什么需要 Multi-Agent
category: agent
tags: [agent, multi-agent, orchestration, context-engineering, collaboration]
difficulty: medium
role: engineer
contributor: 佚名
source: 未知
status: published
updated: 2026-06-28
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-28
    updated: 2026-06-28
---

## 问题

单 Agent 遇到瓶颈时，为什么需要 Multi-Agent？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-28

核心结论：Multi-Agent 不是为了「更高级」，而是单 Agent 在**上下文、能力、可靠性**三个维度撞到天花板时，用「分而治之」换取可扩展性。能用单 Agent 跑通就别拆——只有真出现下面这些瓶颈，才值得付出编排与通信的代价。

**一、单 Agent 的三类瓶颈**

1. **上下文膨胀（最常见）。** 任务一宽，工具描述、历史对话、检索结果就把窗口塞满，关键信息被「淹没」，模型注意力涣散、开始遗忘和幻觉。即便窗口够大，过长上下文也会显著降低指令遵循度，并推高每一步的 token 成本。
2. **角色 / 能力冲突。** 同一个 prompt 既要「发散创意」又要「严谨审查」，既要规划又要执行，目标互相打架；工具集过大时模型选错工具的概率也随之上升。
3. **缺乏独立校验。** 单 Agent 自己写、自己判，等于「自己批改自己的卷子」，没有外部视角，错误容易一路传递到最终输出。

**二、Multi-Agent 如何破局**

把一个「全能但过载」的 Agent，拆成多个**职责窄、上下文短**的专精角色，通过编排层协作：

```
                 ┌─────────────────┐
                 │   Supervisor    │  ← 拆解任务 / 路由 / 汇总
                 │   （编排中枢）   │
                 └────────┬────────┘
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
     ┌─────────┐     ┌─────────┐     ┌─────────┐
     │ Planner │ →   │Executor │ →   │Reviewer │
     │ 规划者  │     │ 执行者  │     │ 审查者  │
     └─────────┘     └─────────┘     └─────────┘
       窄上下文        窄上下文         独立校验
```

带来三个直接收益：

- **上下文隔离**：每个角色只看自己那一摊，窗口短、注意力集中、更省钱。
- **分工与并行**：互不依赖的子任务（如多源调研）可并发执行，缩短端到端时延。
- **独立校验**：执行与审查分属不同 Agent，形成「作者 / 评审」分离，能拦截单体看不见的错误。

**三、代价与判断标准**

Multi-Agent 不是免费的：编排复杂度、Agent 间消息传递失真、token 总量上升、调试更难。判断原则——**先用单 Agent 把任务跑通**，当出现「一个 prompt 装不下的职责」「需要并行加速」或「需要独立校验」时，再拆；并为每个角色保持**窄而清晰的边界**，否则只是把混乱从一个 Agent 搬到了多个 Agent。

一句话：Multi-Agent = 用**上下文隔离 + 专业分工 + 独立校验**，换单 Agent 在复杂任务上换不来的可扩展性与可靠性。

## 延伸 / 追问

**追问：怎么判断「现在该不该」从单 Agent 升级到 Multi-Agent？有没有可量化的信号？**

别凭感觉拆，看可观测信号。**该升级的信号**：① 单次任务的 prompt / 工具描述已占满大半上下文窗口，或常因超长而触发截断、遗忘；② 同一 Agent 被塞进互斥目标（既要创作又要审查），输出风格反复横跳；③ 工具数量多到模型频繁选错工具；④ 准确性靠「自己检查自己」上不去，需要独立第三方校验；⑤ 存在天然可并行的独立子任务，串行做端到端时延无法接受。**先别拆、优先单 Agent 的情况**：任务目标单一、工具集小、对时延不敏感——这时拆分只会徒增编排与 token 成本。落地建议：从单 Agent 起步并埋点（上下文占用率、工具选择错误率、自检通过率），命中上述阈值再拆，而非一上来就上多 Agent。具体拆成哪种拓扑、各模式怎么取舍，见 [agent-0026 常见的 Multi-Agent 协作模式有哪些](agent-0026-multi-agent-collaboration-patterns.md)。

## 参考

- Anthropic, *Building Effective Agents*, 2024：https://www.anthropic.com/research/building-effective-agents
- Anthropic, *How we built our multi-agent research system*, 2025：https://www.anthropic.com/engineering/multi-agent-research-system
- LangChain Docs, *Multi-agent*：https://docs.langchain.com/oss/python/langchain/multi-agent
