---
id: agent-0002
title: 一个完整的 Agent 智能体架构一般包括哪些部分
category: agent
tags: [agent, architecture, planning, memory, tool-use, orchestration, guardrails, safety]
difficulty: medium
role: engineer
contributor: 佚名
source: 未知
status: published
updated: 2026-06-20
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-20
    updated: 2026-06-20
---

## 问题

一个完整的 Agent 智能体架构一般包括哪些部分？请说明各部分的职责及协作关系。

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-06-20

一个完整的 Agent 通常可拆为「大脑—感知/记忆—行动—调度」四类能力，核心由 LLM 驱动，围绕它扩展规划、记忆与工具：

```
                 ┌─────────────────────────────────────────┐
                 │  Guardrails / Safety / Observability      │  ← 横切
                 │  (权限边界·校验·注入防护·审批·审计监控)     │
                 ├─────────────────────────────────────────┤
   输入/目标 ──▶ │            Orchestration                  │ ◀── 反馈/观测
                 │        (控制循环 / 编排调度)               │
                 └───────────────────┬─────────────────────┘
        ┌────────────┬───────────────┼───────────┬────────────┐
        ▼            ▼               ▼            ▼            ▼
  ┌─────────┐  ┌─────────┐    ┌─────────┐  ┌─────────┐  ┌─────────┐
  │ LLM 内核 │  │ Planning │    │ Memory  │  │  Tools  │  │ Action  │
  │ (推理)   │  │ (规划)   │    │ (记忆)  │  │ (工具)  │  │ (执行)  │
  └─────────┘  └─────────┘    └─────────┘  └─────────┘  └─────────┘
```

1. **LLM 内核（Reasoning Core）。** 智能体的大脑，负责理解意图、推理、决定下一步动作。Profile / System Prompt 在此定义角色、目标与行为约束。

2. **规划（Planning）。** 把大目标拆成可执行子任务并决定顺序。常见手段：任务分解、ReAct（推理-行动交替）、Plan-and-Execute、以及通过自我反思（Reflection）根据结果修正计划。

3. **记忆（Memory）。** 短期记忆即上下文窗口，保存当前对话与中间状态；长期记忆借助向量库/外部存储，跨会话检索历史经验与知识（常与 RAG 结合）。记忆决定 Agent 能否"记住"和"积累"。

4. **工具调用（Tool Use）。** 通过函数调用/工具接口连接外部世界——搜索、代码执行、数据库、API、MCP 等，突破模型自身知识与能力边界，需配工具描述与结果解析。

5. **行动与执行（Action / Execution）。** 把模型决策落地为真实操作，并把执行结果（Observation）回灌给内核，形成"感知—决策—行动—反馈"闭环。

6. **编排与控制循环（Orchestration）。** 调度中枢：管理循环终止条件、错误重试、状态流转；多智能体场景下负责角色分工与消息路由（Supervisor / 协作网络）。

7. **护栏与可观测性（Guardrails / Safety / Observability，横切全局）。** 风险控制层，贯穿工具调用与执行：工具 allowlist 与权限边界、输入参数与输出校验、prompt injection 防护、敏感数据策略、高风险动作的 human approval、sandbox 执行与失败 rollback，以及全链路审计日志与监控。它不是某一模块的局部细节，而是约束所有动作的横切关注点。

一句话：**内核负责"想"、Planning 负责"怎么做"、Memory 负责"记得住"、Tools/Action 负责"做得到"、Orchestration 把它们组织成闭环，而 Guardrails/可观测性横切其上，保证整个闭环安全、可控、可追溯。**

## 延伸 / 追问

**追问：单 Agent 与多 Agent（Multi-Agent）架构如何取舍？**

单 Agent 结构简单、上下文集中、调试容易，适合目标明确、工具集有限的任务；但任务过宽时易出现上下文膨胀与"角色混乱"。多 Agent 把职责拆给多个专精角色（如规划者/执行者/审查者），通过 Supervisor 或协作网络编排，优点是分工清晰、可并行、单体上下文更短，适合复杂、跨领域、需多视角校验的工作流；代价是编排与通信复杂度上升、token 成本更高、易因消息传递失真而出错。取舍原则：先用单 Agent 把任务跑通，当出现"一个 prompt 装不下的职责"或需要独立校验/并行时，再拆成多 Agent，并为每个角色保持窄而清晰的边界。

## 参考

- Lilian Weng，*LLM Powered Autonomous Agents*（Planning / Memory / Tool Use 三支柱）：https://lilianweng.github.io/posts/2023-06-23-agent/
- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, 2022
- Anthropic Engineering，*Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
