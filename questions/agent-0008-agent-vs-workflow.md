---
id: agent-0008
title: Agent 与 Workflow automation 的区别是什么
category: agent
tags: [agent, workflow, autonomy, control-flow, orchestration]
difficulty: easy
role: both
contributor: 佚名
source: 淘天/阿里
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

Agent 与 Workflow automation 的区别是什么？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

**一句话区分：** 本质差别在**谁决定控制流**。Workflow 是**人预先编排好固定路径**，每一步走向都写死在代码/编排图里；Agent 是**模型在运行时动态决定下一步**——调哪个工具、是否重试、何时收尾，都由 LLM 根据中间结果自行判断。

**两种控制流对比：**

```
Workflow（路径预先写死）
  输入 ─► 步骤A ─► 步骤B ─► 判断 ─┬─► 步骤C ─► 输出
                                └─► 步骤D ─► 输出
        （分支也是人提前枚举好的 if/else）

Agent（路径运行时生成）
  目标 ─►┌─ LLM 决策下一步 ─► 调用工具 ─► 观测结果 ─┐
         └◄──────────── 回灌，模型再决定 ◄──────────┘
              循环直到模型判断"达成目标 / 该停了"
```

**关键差异维度：**

| 维度 | Workflow | Agent |
| --- | --- | --- |
| 控制流 | 人预先编排、固定 | 模型动态决定 |
| 路径 | 有限、可穷举 | 开放、运行时生成 |
| 灵活性 | 低，新场景要改编排 | 高，靠提示与工具适应 |
| 可预测/可控 | 强，易测试审计 | 弱，需护栏与停止条件 |
| 成本/延迟 | 低且稳定 | 较高（多轮 LLM 调用） |
| 失败模式 | 漏掉未编排的分支 | 死循环、跑偏、烧 token |

**各自适用场景：**

- **选 Workflow**：流程**清晰且稳定**、分支可穷举、对一致性/合规/延迟/成本敏感。如审批流、ETL、定时对账、固定的"检索→拼 prompt→生成"链路。能用确定性编排解决的，就不必上 Agent。
- **选 Agent**：任务**开放、步骤数和路径事先说不清**、依赖中间结果临场决策。如跨多工具的研究调查、自主排障、需要反复试探与回溯的复杂操作。

**工程现实——不是二选一：** 二者是连续光谱，最佳实践常是**混合**：用 Workflow 编排骨架保证可控与可观测，只在确实需要动态决策的环节嵌入 Agent；或反过来，让 Agent 在高风险步骤回落到固定流程并加人工审批。Anthropic 的建议也是**先用最简单的方案**，只有当固定编排扛不住任务的开放性时，才引入 Agent 的自主性——多花的灵活性要用可控性来还。一句话：**能编排就别让模型自由发挥，必须自由发挥时才用 Agent，并把边界、停止条件、兜底设计清楚。**

## 延伸 / 追问

**追问：既然 Agent 更灵活，为什么生产上还大量用 Workflow？**

因为**灵活性的代价是可控性**。Workflow 路径固定，所以**可测试、可审计、延迟与成本可预期**，出错也容易定位到具体步骤——这正是生产系统最看重的。Agent 每一步都让模型临场决策，带来三类风险：① 不确定性（同样输入可能走不同路径，难复现）；② 失控（死循环、跑偏、token 成本不可控）；③ 难审计（决策藏在模型推理里）。所以选型不是"谁更先进"，而是**任务是否真的需要运行时决策**：路径能穷举就用 Workflow，省钱省心又稳定；只有当任务足够开放、固定编排会漏掉大量分支时，Agent 的自主性才物有所值。务实做法是给 Agent 套上 Workflow 式护栏——限定可用工具、设最大步数与预算、关键动作加人工审批，把"自由度"压到任务真正需要的最小范围。

## 参考

- Anthropic Engineering，*Building Effective Agents*（Workflows vs Agents 的区分与取舍）：https://www.anthropic.com/engineering/building-effective-agents
- LangGraph Docs，*Workflows and Agents*：https://langchain-ai.github.io/langgraph/tutorials/workflows/
- OpenAI，*A Practical Guide to Building Agents*：https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
