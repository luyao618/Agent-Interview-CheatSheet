---
id: agent-0003
title: 你对 Agent 了解多少，如何理解与定义 AI Agent
category: agent
tags: [agent, definition, autonomy, tool-use, planning, llm]
difficulty: easy
role: both
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

你对 Agent 了解多少？你是怎么理解与定义 AI Agent 的？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-20

**一句话定义：** AI Agent 是以大模型为决策核心、能在一个目标驱动下**自主地循环「感知—决策—行动」**、并借助工具与环境交互来推进任务的系统。它的本质区别不在于「会聊天」，而在于**模型自己决定下一步做什么、何时调用工具、何时结束**。

**核心运行循环：**

```
        ┌─────────────────────────────┐
        │            目标 / 任务            │
        └──────────────┬──────────────┘
                       ▼
   ┌──► 感知 Observe ──► 决策 Reason/Plan ──► 行动 Act ──┐
   │      (读取环境/           (LLM 推理         (调用工具/         │
   │       工具结果)           选择动作)         执行操作)         │
   └────────────── 反馈 Feedback ◄──────────────────────┘
                       │  达成目标 / 触发停止条件
                       ▼
                     输出结果
```

模型在每一轮根据当前观测决定动作，把工具返回结果作为新观测喂回下一轮，直到完成或满足停止条件——这就是 ReAct 式「推理+行动」交替的本质。

**四个关键组成部分：**

1. **大脑（LLM）** — 负责理解、规划与决策，是 Agent 的中枢。
2. **工具（Tools）** — 把模型的「想法」落到现实：检索、代码执行、API 调用、读写文件等，突破模型自身知识与能力边界。
3. **记忆（Memory）** — 短期记忆维持当前任务上下文，长期记忆（向量库/外部存储）跨会话沉淀经验。
4. **规划（Planning）** — 任务拆解、子目标编排、反思与重试，决定 Agent 能否处理多步复杂任务。

**与相邻概念的区分：**

| 形态 | 谁在控制流程 | 自主性 |
| --- | --- | --- |
| Chatbot | 人逐轮驱动 | 无 |
| 固定 Workflow | 人预先编排好路径 | 低（路径写死） |
| **Agent** | **模型动态决定路径** | **高** |

判别标准：**控制流是不是由模型动态决定**。如果每一步都是工程师写死的 if/else，那是 workflow；如果模型能根据中间结果自行选择调用哪个工具、是否重试、何时收尾，才算 Agent。

**我对它的整体理解：** Agent = **LLM（推理）+ 工具（行动）+ 记忆（状态）+ 循环（自主）**。它把语言模型从「一问一答的生成器」升级为「能在环境中持续行动以达成目标的执行体」。自主性是连续光谱而非开关：从 Copilot 式建议、到人审批关键步、再到端到端自治，工程实践中需要按风险在「自主程度」与「可控/可观测」之间取平衡——可靠的 Agent 往往不是最自由的，而是边界、停止条件与失败兜底设计得最清晰的。

## 延伸 / 追问

**追问：一个最小可用的 Agent，工程上至少要落地哪些东西？**

四件套缺一不可：① **决策循环**——驱动「调用模型 → 解析其要的动作 → 执行 → 把结果回灌」反复迭代；② **工具层**——给每个工具清晰的 name/description/参数 schema，让模型知道何时用、怎么用，并处理好工具报错；③ **停止条件**——目标达成、超出最大步数/预算、或触发护栏时必须能停，否则会死循环烧 token；④ **状态与可观测**——保留对话/动作轨迹，记录每一步的输入输出便于调试与回放。加分项：规划/反思（先列计划再执行、失败后自我修正）、长期记忆、以及对高风险动作加人工审批（human-in-the-loop）。一句话：先把「循环 + 工具 + 能停 + 可观测」跑通，再谈多步规划与多 Agent 协作。

## 参考

- Anthropic Engineering，*Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, 2022：https://arxiv.org/abs/2210.03629
- Anthropic Docs，*Agent Skills / Tool use*：https://docs.anthropic.com/en/docs/agents-and-tools
