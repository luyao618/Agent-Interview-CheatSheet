---
id: agent-0013
title: 如何让 Agent 自动拆分任务
category: agent
tags: [agent, planning, task-decomposition, react, plan-execute]
difficulty: medium
role: engineer
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

如何让 Agent 自动拆分任务？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

核心结论：任务拆分不是「一次性把大任务切成小任务」，而是**拆解—编排—执行—重规划**的闭环。工程上有三种主流范式，按任务可预测性来选。

**三种拆分范式：**

1. **ReAct（边想边拆）**：不预先列全计划，每一步用「Thought→Action→Observation」决定下一动作。优点是依赖运行时反馈、灵活；缺点是缺全局视野、易绕路、链长易漂移。适合**步骤不确定、强依赖中间结果**的探索型任务。

2. **Plan-and-Execute（先规划后执行）**：Planner 先用 LLM 一次性产出有序子任务列表，Executor 逐个执行，全部完成后由 Replanner 检查是否达标、决定续拆或收尾。优点是全局规划、token 省、可控；缺点是计划可能脱离实际。适合**目标清晰、可提前编排**的任务。

3. **树状 / 分治规划**：把目标递归拆成子目标树，子目标再往下拆到「可由单个工具直接完成」的叶子（类似 HTN、Tree-of-Thought）。适合**层级深、可并行**的复杂任务。

```
              目标
               │  分解 (decompose)
        ┌──────┼──────┐
      子目标A  子目标B  子目标C
        │              │
     ┌──┴──┐        (依赖 A 完成)
   叶子   叶子  ── 可并行 ──►  叶子=单步可执行
```

**让拆分真正可用的四个关键：**

- **子目标编排**：每个子任务给清晰的输入/输出契约，便于串联与校验。
- **依赖管理**：把子任务建成 DAG，无依赖的并行、有依赖的按拓扑序串行，避免「下游用了还没产出的结果」。
- **重规划（replan）**：执行中子任务失败或观测与预期不符时，回到 Planner 局部重拆，而非硬推到底——这是长任务不崩的关键。
- **停止与预算**：限定最大深度/步数/token，设达成判据，防止无限拆解烧钱。

**落地要点：** 用结构化输出（JSON 子任务列表 + 依赖字段）约束 Planner，让拆分结果可被程序解析调度；叶子粒度对齐「一个工具一次能做完」；ReAct 给灵活、Plan-Execute 给可控，复杂场景常**混合**——先全局 Plan，子步内用 ReAct，遇阻则 Replan。一句话：好的拆分 = 会拆（分治）+ 会排（DAG 依赖）+ 会改（重规划）+ 会停（预算护栏）。

## 延伸 / 追问

**追问：Plan-and-Execute 和 ReAct 到底怎么选？能不能混用？**

按「任务可预测性」选。目标明确、步骤可提前列清楚（如「查 A、算 B、生成报告」）→ Plan-and-Execute，一次规划省 token 且可控、可审计；步骤高度依赖现场反馈、无法预知下一步（如调试、开放式检索）→ ReAct，逐步适应。实践中更常**混合**：顶层用 Plan-and-Execute 列出里程碑式子目标保证全局方向，单个子目标内部用 ReAct 灵活试探，子目标失败或现实偏离计划时触发 Replanner 局部重拆。这样既有全局视野又有局部弹性，是目前复杂 Agent（如 deep research、coding agent）的主流形态。

## 参考

- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, 2022：https://arxiv.org/abs/2210.03629
- Wang et al., *Plan-and-Solve Prompting*, 2023：https://arxiv.org/abs/2305.04091
- Yao et al., *Tree of Thoughts: Deliberate Problem Solving with LLMs*, 2023：https://arxiv.org/abs/2305.10601
- LangChain Docs，*Plan-and-Execute Agents*：https://blog.langchain.dev/planning-agents/
