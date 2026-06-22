---
id: agent-0015
title: Agent 如何避免无限循环调用工具
category: agent
tags: [agent, loop-prevention, stop-condition, budget, guardrails]
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

Agent 如何避免无限循环调用工具？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

死循环的根因：Agent 控制流由模型自主决定，一旦模型反复选择同一动作、或始终判断「还没完成」，循环就停不下来——既烧 token 又卡住任务。防御不能只靠模型自觉，必须在**循环框架层**加硬约束，分四道防线：

```
      每一轮 Act 前后都过一遍闸门
  ┌──────────────────────────────────────────┐
  │ ① 预算闸：步数++ / token / 耗时 超限? ──► 停 │
  │ ② 去重闸：本轮动作指纹 ∈ 历史? ──────► 拦/停 │
  │ ③ 停止闸：目标达成 or 终止信号? ─────► 正常停 │
  │ ④ 兜底闸：工具连续报错 / 卡死? ──────► 降级 │
  └──────────────────────────────────────────┘
```

**1. 预算 / 上限（硬性兜底，必做）**
给每次运行设三类配额：最大步数（max_steps，如 ≤ 15）、最大 token / 成本、最大墙钟时间（timeout）。任一触顶立即跳出循环，返回「已尽力」的部分结果而非空转。这是最后一道、也是最可靠的一道防线——其它机制都失效时它仍能保命。

**2. 重复动作检测 / 状态去重**
对每个 `(tool_name, 规范化参数)` 计算指纹，记入历史集合。若模型再次产出相同指纹：可直接复用上次结果（缓存）、拒绝并把「你已调用过且结果为 X」回灌提示其换路，或累计 N 次重复即判定卡死退出。进一步可检测**循环模式**（A→B→A→B 振荡）和「连续 K 步无新信息增益」，提前掐断。

**3. 明确的停止条件**
让模型有清晰的「完成」出口：约定显式终止动作（如 `finish`/`final_answer`），prompt 里写清完成标准与「拿到答案应立即收尾」；必要时让模型先产出计划再执行，按计划核对进度，避免无目标地反复试探。

**4. 超时与失败兜底**
单个工具调用要有超时和重试上限（如重试 ≤ 2 次，指数退避），避免在一个卡死/常错的工具上空转。连续失败应升级处理：换工具、降级返回、或转人工（human-in-the-loop），而不是无限重试同一个报错。

**工程小结**：循环必须是「带刹车」的——`while not done and within_budget`。**步数/预算上限是必须项**，去重与停止条件提升体验与效率，超时兜底防单点卡死。同时把每轮动作轨迹打点（可观测），既便于调试，也是触发上述闸门的数据来源。

## 延伸 / 追问

**追问：max_steps 触顶了，应该直接报错还是返回部分结果？**

优先**优雅降级**而非硬失败。触顶时不要抛异常丢弃全部进度，而是让模型基于已有的观测与中间结果做一次「收尾总结」，返回当前最佳答案并显式标注「因达到步数上限、结论可能不完整」。同时记录触顶事件与完整轨迹，用于排查是任务本身偏难、上限设太小，还是模型陷入了无效循环。如果是面向用户的实时场景，可在接近上限时提示「仍在处理」或转人工兜底；如果是离线批处理，则落日志告警，便于事后调上限或优化 prompt / 工具设计。核心原则：**上限是安全网，不是任务的正常终点**——频繁触顶说明任务拆解或工具链有问题，要回头优化，而非一味调大阈值。

## 参考

- Anthropic Engineering，*Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
- LangGraph Docs，*Recursion limit / GraphRecursionError*：https://langchain-ai.github.io/langgraph/how-tos/recursion-limit/
- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, 2022：https://arxiv.org/abs/2210.03629
