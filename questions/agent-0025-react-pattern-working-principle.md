---
id: agent-0025
title: ReAct 模式的工作原理是什么
category: agent
tags: [agent, react, reasoning, tool-use, prompting]
difficulty: medium
role: engineer
contributor: 佚名
source: 未知
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

解释 ReAct 模式的工作原理。

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-27

核心结论：ReAct（Reasoning + Acting）让大模型把**「推理」与「行动」交织**在同一条轨迹上——不再「一次想完再做」，而是边想边做、用环境反馈纠正下一步。它是绝大多数现代 Agent 的执行内核。

**一、基本循环：Thought → Action → Observation**

每一轮模型产出三类内容，循环往复直到给出 Final Answer：

- **Thought（思考）**：用自然语言写出当前推理——「我还缺什么信息、下一步该做什么」。
- **Action（行动）**：选择一个工具并给出结构化参数，如 `search("ReAct 论文")`。
- **Observation（观测）**：执行工具后，把真实返回结果回填进上下文，作为下一轮推理的新证据。

```
       ┌──────────────────────────────┐
       ▼                              │
  Thought（推理：缺什么/下一步）        │
       │                              │
       ▼                              │
  Action（调用工具 + 参数）            │ 未完成则继续
       │                              │
       ▼                              │
  Observation（工具返回，回填上下文）── ┘
       │ 信息足够
       ▼
  Final Answer（停止）
```

**二、为什么有效**

1. **推理指导行动**：Thought 决定调哪个工具、传什么参数，避免盲目试探。
2. **行动校正推理**：Observation 注入外部真实信息，把模型「锚定」在事实上，显著降低幻觉——这是相比纯 Chain-of-Thought（只推理、不与环境交互）的关键优势。
3. **可解释、可干预**：思考链显式可读，便于调试、加护栏、做人审。

**三、工程落地要点**

- **提示词模板**：用固定的 `Thought/Action/Action Input/Observation` 格式（或 function-calling 的结构化等价物）约束输出，便于解析器稳定提取。
- **停止与预算**：设最大步数 / token 上限，避免在工具上无限绕圈。
- **错误处理**：工具报错时把错误信息作为 Observation 回填，让模型自我纠正而非崩溃。

一句话：ReAct = **让模型「想一步、做一步、看一步」，用环境反馈闭环地逼近答案**，是把 LLM 从「会说」变成「会做」的最小可行范式。

## 延伸 / 追问

**追问：ReAct 和 Function Calling、Chain-of-Thought 是什么关系？**

三者不冲突、常叠加。**Chain-of-Thought（CoT）** 只在模型内部展开推理、不与外部交互，适合纯逻辑/数学题；**ReAct** 在 CoT 基础上加了「行动—观测」环节，让推理能调用工具、吃到真实反馈，适合需要外部信息或副作用的任务。**Function Calling** 则是 ReAct 中「Action」一步的**工程实现方式**：早期 ReAct 靠文本模板让模型吐出 `Action: search[...]` 再正则解析，脆弱且易跑偏；现代模型原生支持 function calling，直接产出结构化 JSON 工具调用，由运行时执行并回填结果——本质仍是 Thought→Action→Observation 循环，只是 Action 的载体从「自由文本」升级为「受约束的结构化调用」，更稳、更易工程化。

## 参考

- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, 2022：https://arxiv.org/abs/2210.03629
- Wei et al., *Chain-of-Thought Prompting Elicits Reasoning in LLMs*, 2022：https://arxiv.org/abs/2201.11903
- LangChain Docs，*ReAct Agent*：https://python.langchain.com/docs/concepts/agents/
