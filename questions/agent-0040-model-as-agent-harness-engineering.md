---
id: agent-0040
title: 当"模型即 Agent"越来越强，Harness 工程为什么仍然重要
category: agent
tags: [harness, model-as-agent, orchestration, guardrails, observability]
difficulty: medium
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 1 章
status: published
updated: 2026-08-05
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-05
    updated: 2026-08-05
---

## 问题

当"模型即 Agent"越来越强，Harness 工程为什么仍然重要？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-05

**先划清边界。** "模型即 Agent"说的是：规划、反思、工具选择这些**认知能力**正从框架硬编码迁移进模型权重，模型自己就能决定"下一步做什么"。但一个能上线的 Agent = 模型的认知 + 一整套**它够不到的东西**——真实世界的状态、可执行的工具、不可逾越的护栏、可观测性、验证闭环、产品集成。这套东西就是 **Harness**（运行时骨架）。模型再强，也只是 Harness 里的推理内核，而不是 Harness 本身。

```
        ┌──────────────── Harness（工程负责） ────────────────┐
  用户 →│  输入编排 → [ 模型/认知内核 ] → 工具执行 → 验证/护栏  │→ 产品
        │      ↑ state/memory        ↓ 权限沙箱        ↓ 可观测  │
        └──────── 重试 · 审计 · 回放 · 评估回流 ──────────────┘
```

**Harness 负责六件模型天生做不到的事：**

1. **状态与记忆**：模型每次调用无状态，跨轮/跨会话的事实、进度、用户偏好必须由 Harness 外置存储并按需注入上下文。
2. **工具与副作用**：模型只能"说"要调用，真正连数据库、发请求、写文件、处理超时与失败重试的是 Harness——它把意图变成可执行、可回滚的动作。
3. **护栏与权限**：能力越强，越需要**约束边界**。权限校验、沙箱隔离、危险动作二次确认、预算/速率上限，这些安全属性必须在模型之外强制，不能寄望模型自觉。
4. **验证与闭环**：模型输出是概率性的。Harness 负责结构校验、执行结果核对、失败重试与纠偏，把"大概对"逼近"确定可用"。
5. **可观测性**：日志、trace、评估指标、回放——没有这层，线上问题无法定位，质量无法度量和回归。
6. **产品集成**：鉴权、多租户、UI/API 契约、合规审计——把一个 demo 变成产品的全部工程。

**模型进步后，框架价值如何迁移？** 认知类脚手架（硬编码的规划链、人工 ReAct 提示、繁琐的工具路由）确实在**贬值**——模型自己做得更好。但价值**没有消失，而是上移**：从"替模型思考"转向"给模型可靠的手脚和护栏"。框架越来越薄的是**认知编排层**，越来越厚的是**状态、安全、可观测、评估**这些工程层。

一句话：**模型负责"想得对"，Harness 负责"做得成、管得住、看得见"**；前者会被模型进步吃掉，后者是随能力增强而更重要的工程底座。

## 延伸 / 追问

**追问：既然认知脚手架在贬值，实践中如何判断某段框架逻辑该删还是该留？**

一条判据：**这段逻辑是在"替模型做决策"，还是在"给模型提供它够不到的能力/约束"？** 前者（人工规划树、写死的工具选择规则、模板化反思）随模型变强应主动删除，避免和模型的判断打架、拖慢迭代；后者（状态注入、权限沙箱、结果校验、trace、评估）应保留并加固。经验做法是**默认让模型自主，只在观测到确定性失败模式时才补一层薄护栏**，且这层护栏最好是可校验的硬约束（如 schema 校验、权限白名单），而非又一段引导模型怎么想的提示词——后者最容易在下一代模型上过时。

## 参考

- Anthropic Engineering, *Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
- Anthropic Engineering, *Effective Context Engineering for AI Agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
