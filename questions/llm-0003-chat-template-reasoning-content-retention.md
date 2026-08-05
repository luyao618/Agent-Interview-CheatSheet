---
id: llm-0003
title: Chat Template 中 reasoning_content 应该保留、剥离还是压缩？
category: llm
tags: [chat-template, reasoning-content, context-window, inference, agent-loop]
difficulty: hard
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 2 章
status: published
updated: 2026-08-06
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-06
    updated: 2026-08-06
---

## 问题

在长 ReAct / 多轮 Agent 循环里，推理模型每轮都会产出一大段 `reasoning_content`（思考轨迹）。把它保留、剥离还是压缩进历史？三种策略各有什么利弊？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-06

**先定性：`reasoning_content` 是"一次性草稿纸"，不是持久状态。** 它由模型为**当前这一步**推理而生，往往是整段输出里最长的部分；多轮累积会二次膨胀上下文。关键要分清**两个时间尺度**：一次工具调用回合**之内** vs 回合**之间**——两者答案相反。

```
回合之内（thinking → tool_call → 结果回填 → 继续）
   └─ 必须保留：思考与紧随的 tool_use 绑定，
      剥掉会割裂"为什么调这个工具"，破坏本回合推理连续性
回合之间（上一轮已产出最终答案，进入新一轮）
   └─ 默认剥离：历史 reasoning 对下一轮决策无增量价值，
      多数推理模型的 chat template 本就不回灌旧思考
```

**三种策略的利弊：**

1. **保留（full retain）**。优点：推理连续、模型可承接上文思路，且在**同一工具回合内是必需的**。缺点：跨轮保留会让 token 爆炸、成本与延迟飙升；DeepSeek-R1、Claude 扩展思考等模型的官方约定恰恰是**跨轮不回传旧 `reasoning_content`**——硬留反而违反模板、可能劣化。

2. **剥离（strip）**。优点：省 token 最狠，契合推理模型"思考即用即弃"的设计，历史只留最终 `content`。缺点：丢掉"当初为何这么决定"的依据，遇到需要回溯的场景模型可能**重新推导**甚至反复；纯剥离不适合"决策理由后续还要用"的长任务。

3. **压缩 / 摘要（summarize）**。折中：丢弃冗长 CoT，只把**决策级结论**（选了哪条路、排除了什么、待办与约束）蒸馏进显式 state 块。优点：低成本保住决策相关信息。缺点：摘要有失真风险、且多一次调用开销。

**推荐组合：** 把 `reasoning_content` 当**易失草稿**——**回合内保留以维持连续性；回合结束即从历史剥离**（跟随模型 chat template 的既定行为），同时把该轮产生的**结论/待办/教训**外置进持久 state，而不是靠原始思考轨迹承载记忆。这样既守住模板约定与成本，又不丢"决策为什么这么做"。

## 延伸 / 追问

**追问：为什么很多推理模型明确要求跨轮"剥离"历史 `reasoning_content`，而不是让用户自己选？**

因为这既是**成本约束**也是**训练分布约束**。其一，思考轨迹通常是输出里最长的部分，跨轮累积会迅速吃满窗口、抬高 prefill 成本，收益却很低——下一轮真正需要的是上一轮的**结论**，不是它的推导过程。其二更关键：这类模型在**后训练时**看到的多轮格式里，历史 assistant 轮往往**只含最终答案、不含思考**；推理时若把大量旧 `reasoning_content` 回灌，等于喂给模型一个它训练时罕见的分布，可能干扰当前推理、甚至诱发风格漂移或降质。所以官方 chat template 直接在模板层剥离，是用"对齐训练分布"来保证稳定性，而非留给用户试错。例外仍是**同一工具回合内**：此时思考与 `tool_use` 属于未完成的一步，必须整体保留。

## 参考

- DeepSeek API Docs, *Reasoning Model (deepseek-reasoner) — 多轮对话中的 reasoning_content 处理*：https://api-docs.deepseek.com/guides/reasoning_model
- Anthropic Docs, *Extended thinking*（thinking blocks 与工具调用中的保留规则）：https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking
- Anthropic Engineering, *Effective Context Engineering for AI Agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
