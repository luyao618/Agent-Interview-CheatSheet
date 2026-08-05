---
id: agent-0043
title: 如何设计既不破坏 KV Cache、又能避免重复工具调用的上下文压缩策略
category: agent
tags: [context-compression, kv-cache, tool-use, memory, prompt-caching]
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

如何设计既不破坏 KV Cache、又能避免重复工具调用的上下文压缩策略？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-06

**两个目标天然打架。** KV Cache 要求前缀**逐字不变**——一旦改动前面的内容，命中点之后的缓存全部失效、要重新 prefill；而「压缩」本能地想去**改写历史**。「避免重复调用」又要求把「谁调过什么、拿到什么」这份事实**完好留住**，这与压缩想丢弃细节相冲突。解法是把上下文切成三段，各自服从不同纪律。

```
┌──────────── 上下文窗口 ────────────┐
│ [固定前缀]  system·工具定义·目标·few-shot   ← 逐字不变，长期命中缓存
│ [稳定状态]  已确认事实 · TODO · 工具调用台账 ← 决策必需，只在折叠点整段更新
│ [动态尾部]  最近 1~2 轮明细 + 新消息        ← 一律 append，绝不回插改写
└────────────────────────────────────┘
```

**1. 只追加，不回插（护缓存的铁律）。** 新内容永远拼到末尾，前缀原样不动，缓存自然持续命中。压缩不是在旧消息里「就地删改」——那会击穿缓存——而是**在边界处折叠**：把一段稳定旧轨迹整体替换成一段摘要，只在这一处付一次 miss，随后这段摘要成为新的稳定前缀，继续被缓存。所以要**在粗粒度边界（一个子任务/阶段结束）低频折叠**，而不是每轮微调。

**2. 工具调用台账（防重复的关键）。** 维护一个 `(工具名 + 归一化入参) → 结果引用/摘要` 的键值台账，常驻「稳定状态」块。发起调用前先查台账：命中就直接复用结果，不再真调。即使把原始 Observation 压掉了，「search(x) 已调过、结果在 #id」这个事实仍在台账里，模型不会因为「看不见历史」而重复调用。

**3. 可检索轨迹索引（保信息完整）。** 冗长的原始返回落到外部存储，按 `id` 编号；上下文里只留提取后的字段 + 引用，需要时按 id 回取（rehydrate）。这样窗口小、又没真正丢信息。

**权衡本质：** 缓存命中偏爱「不可变、少折叠」，信息完整偏爱「多留细节」。破局点是**按价值分层**——决策相关的事实与台账（小而关键）常驻，原始 blob（大而边际低）外置可检索。用「固定前缀 + 常驻台账 + append 尾部」，把二者从对立变成正交。

## 延伸 / 追问

**追问：折叠摘要发生时缓存那一段必然失效，如何把这次「缓存重置」的代价降到最低？**

三个工程手法：① **低频 + 对齐边界**——不要按 token 每满就折叠，而是攒到一个阶段结束再一次性折叠，让 miss 稀疏发生，且折叠点落在语义边界上，摘要质量也更高。② **分层缓存断点**——把「固定前缀」和「稳定状态」放在不同的缓存段：折叠只更新稳定状态段，最前面的 system/工具定义段仍逐字不变、继续命中，miss 只波及被折叠之后的部分，而非整条前缀。③ **折叠即再稳定**——折叠后立刻把新摘要冻结成不可变前缀，后续轮次重新累积命中，把一次性 prefill 成本摊薄到之后多轮。校验上，折叠后要核对台账里的关键 `id`/数值未被摘要改写，高风险动作保留可回溯的原始轨迹引用，避免「压缩顺手改错事实」。

## 参考

- Anthropic Engineering, *Effective Context Engineering for AI Agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic Docs, *Prompt Caching*：https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, 2022：https://arxiv.org/abs/2210.03629
