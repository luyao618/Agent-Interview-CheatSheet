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

在长 ReAct 循环里，Chat Template 中上一轮的 `reasoning_content`（思考 token）应该保留、剥离还是压缩？三种策略各有什么利弊？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-06

**先分清 provider 契约，再谈分层——这不是三选一。** `reasoning_content` 是**字段约定**而非通用标准：DeepSeek-R1、Qwen 兼容 API 把思考轨迹单列到该字段；OpenAI o1 则**不返回原始 CoT**，只给隐藏/摘要版。以官方资料为准：DeepSeek API **不**把上一轮 `reasoning_content` 拼回下一轮；QwQ README 要求多轮 history 只留 final output、`apply_chat_template` 已实现该剥离。硬回灌历史思考会**偏离官方推荐 template 与输入分布、可能引发性能退化**（是「偏离分布」的经验论断，不是有直接证据的「训练没见过」）。

```
┌──────────── 按「轮是否已完成」分层 ────────────┐
│ 未完成 request 内  同一请求的 multi-step tool-use  ← 依 provider 契约【保留】
├──────────────────────────────────────────────┤
│ 已完成的对话轮    final output 已产出的旧 turn     ← 原始轨迹【剥离】
│                但其承载决策的结论              ← 【压缩】提取校验后写入状态
└──────────────────────────────────────────────┘
```

**1. 保留（同一 request、尚未收尾）。** request 内的 multi-step tool-use，reasoning 往往**必须留**：Qwen3 官方 template 保留 last query 之后的 reasoning，丢掉会损害 multi-step tool use。「保留」边界不是笼统「当前一句」，而是**跟随具体 model/provider 的 tool-call replay contract**，别按「一律丢」实现。

**2. 剥离（已完成的对话轮之间）。** user turn 结束、final output 已出，其原始 reasoning 按官方默认剥掉——对齐推荐 template、省 token、KV Cache 不膨胀。剥的是**已完成轮**，非同一 request 内仍在推进的 tool-use 链。代价：没写进 final output 的理由消失，可能重推甚至自相矛盾。

**3. 压缩（保住命脉）。** 剥离 ≠ 连结论一起扔：后续依赖的结论（选定方案、排除项及原因、关键约束）要**提取校验后写入可见 `content` 或状态块**，而非随轨迹蒸发。代价是摘要有损、须护住关键字段。

**落地：同一 request 未收尾时按 provider 契约保留，已完成轮剥离原始轨迹，把决策结论提取校验后写入持久状态。**

## 延伸 / 追问

**追问：如果为了 agent 调试或复用长链推理，一定要在历史里留部分思考，怎么降低信息损失又不偏离官方输入分布？**

四条工程手法：① **双通道**——给模型看的 context 走「按契约剥离 + 结论状态化」，给人 / 日志看的完整 trace 全量落外部存储、按轮次 id 可回取；调试需求用后者满足，别塞进模型输入。② **提取结论，而非复述 CoT**——不要把已完成轮的原始 `reasoning_content` 原样或近似回灌（偏离推荐 template / 输入分布），而是**从 trace 中提取决策结论与约束、校验后写入状态块**（正式结论形式），以官方 template 见过的格式呈现，不暗示复述隐藏思考。③ **护住命脉字段**——选定方案、被排除项及原因、推导出的数值 / 约束，校验后再写入；高风险决策保留可回溯的原始 trace 引用。④ **低频对齐边界**——压缩落在语义边界（一个子任务结束）低频做，别每轮摘要，省得反复付成本又累积失真。

## 参考

- DeepSeek API Docs, *Reasoning Model（多轮对话不把上一轮 reasoning_content 拼回）*：https://api-docs.deepseek.com/guides/reasoning_model
- Qwen Team, *QwQ Usage Guidelines（No Thinking Content in History；apply_chat_template）*：https://github.com/QwenLM/QwQ#usage-guidelines
- OpenAI, *Reasoning models（o1 不返回原始 CoT）*：https://platform.openai.com/docs/guides/reasoning
- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, 2022：https://arxiv.org/abs/2210.03629
