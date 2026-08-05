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

**先分清「谁的思考、什么时候」——这不是三选一，而是分层。** `reasoning_content` 是推理模型（DeepSeek-R1、QwQ、o1 系）在最终 `content` 之外单独产出的思考轨迹，长度常是答案的 3~10 倍。关键前提：R1/QwQ 的 **chat template 与官方 API 本身就把「历史轮」的 reasoning 剥掉**，只把 `content` 拼回下一轮——因为模型训练时没见过「上一轮的思考」，硬喂回去属于**分布外（OOD）**，既涨 token 又可能让它锚死在陈旧推理上。

```
┌──────────── 一次 ReAct 轮次 ────────────┐
│ 当前步思考  reason→act 交替，最终答案未出   ← 必须【保留】
├──────────────────────────────────────┤
│ 历史轮思考  已产出最终 content 的旧轮次     ← 原始轨迹【剥离】
│           但其承载决策的结论            ← 【压缩】进 content/状态块
└──────────────────────────────────────┘
```

**1. 保留（当前步内）。** 同一轮里模型靠自己的思考交替「推理—行动」，chat template 在本轮最终答案出来前必须留着当前思考，否则 ReAct 断链。这是刚需，不是可选项。

**2. 剥离（跨轮 / 跨任务）。** 旧轮的原始 reasoning 一律丢——对齐模型训练分布、省下最大头的 token、KV Cache 也不膨胀。这是推理模型多轮对话的**官方默认**做法。代价：模型「想清楚但没写进最终答案」的理由随之消失，可能重新推导甚至自相矛盾。

**3. 压缩（保住命脉）。** 剥离不等于「把想清楚的东西也扔了」：思考里那些后续步骤依赖的结论（选定的方案、排除的选项、推导出的关键事实）必须**提升进可见的 `content` 或状态块**，而不是随原始轨迹一起蒸发。代价是摘要有损、且多一步成本，须护住关键字段别压错。

**一句话落地：当前步保留，跨轮剥离原始轨迹，把承载决策的结论压缩进持久状态。** 这样既守住 chat template 的契约与成本，又不丢「为什么这么做」。

## 延伸 / 追问

**追问：如果为了 agent 调试或复用长链推理，一定要在历史里留部分思考，怎么降低信息损失又不踩 OOD？**

四条工程手法：① **双通道**——给模型看的 context 走「剥离 + 结论压缩」，给人 / 日志看的完整 trace 全量落外部存储、按轮次 id 可回取；调试需求用后者满足，别塞进模型输入。② **改写而非回灌**——真要复用某段长推理，不要把原始 `reasoning_content` 原样喂回（OOD），而是改写成普通 `content`（正式结论 / 中间引理形式），以模型训练见过的格式呈现。③ **护住命脉字段**——选定方案、被排除项及原因、推导出的数值 / 约束，校验后再写入；高风险决策保留可回溯的原始 trace 引用。④ **低频对齐边界**——压缩落在语义边界（一个子任务结束）低频做，别每轮摘要，省得反复付成本又累积失真。

## 参考

- DeepSeek API Docs, *Reasoning Model（多轮对话须剥离 reasoning_content）*：https://api-docs.deepseek.com/guides/reasoning_model
- Qwen Team, *QwQ / Qwen3 Thinking Mode*：https://qwenlm.github.io/blog/qwq-32b/
- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, 2022：https://arxiv.org/abs/2210.03629
