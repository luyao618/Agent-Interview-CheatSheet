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
updated: 2026-08-05
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-05
    updated: 2026-08-05
---

## 问题

如何设计既不破坏 KV Cache、又能避免重复工具调用的上下文压缩策略？压缩会改写历史从而让缓存前缀失效，而激进裁剪又会让 Agent 忘记「已经调过某工具」而重复调用——这两个目标怎么同时满足？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-05

**先看两个约束为什么打架。** KV Cache / prompt cache 只对**逐字未变的前缀**命中：改动第 k 个 token，第 k 位之后的缓存全部失效、要重新 prefill。压缩的本质是**改写中间历史**——一压，缓存前缀就断。另一头，如果为了省 token 把工具的 Observation 直接删掉，模型「看不见自己已经查过」，下一轮就**重复调用同一工具**，既费钱又可能触发副作用。所以策略要同时满足：**别动缓存前缀，别丢「已做过什么」的记账。**

**核心结构：把上下文切成"稳定前缀 + 可压缩尾部"，压缩只在缓存边界发生。**

```
[稳定前缀 · 逐字不变 · 命中缓存]
  system / 工具定义 / 目标约束
  ── state 块：已确认事实 · TODO · 教训
  ── tool-ledger：调用去重台账（见下）
[可压缩尾部 · append-only]
  最近 N 轮明细（原样追加，不回改）
        │  尾部累积到阈值时↓
        ▼ 一次性把最旧的整段折叠成摘要，
          并入「稳定前缀」→ 形成新的更长前缀
          （承受一次 miss，之后长期命中）
```

要点是**不要每轮改写历史**（每轮都 miss），而是**低频、成段**地压：只折叠已冻结的老段落，把摘要沉淀进前缀，新前缀再长期复用；近处明细一律**追加到末尾**，永不回插。

**避免重复工具调用，靠一份「幸存于压缩」的记账，而非保留原文：**

1. **tool-ledger（调用台账）**：结构化记录 `工具 + 参数指纹 + 结果摘要/引用 id`，放进稳定前缀里常驻。原始大 blob 落外部存储、用 id 回指；模型看得到「这个查询已做、结论是 X」，就不会重发。
2. **结果 memo 化**：按「工具名 + 参数哈希」对结果做幂等缓存；即便模型仍重复请求，也命中本地 memo、不真正触发外部副作用，返回同一结果。
3. **压缩保序**：折叠 Observation 明细时，台账条目**必须保留**——可以丢过程，不能丢「做过没、结果是啥」这一位信息。

**权衡：** 压得越频、越碎 → 缓存命中越差、prefill 越贵；压得越狠 → 信息/去重线索丢得越多。实践取中：**按缓存边界成批压**（对齐 prefix breakpoint），**保留决策相关状态与台账**，把「省 token」和「省 prefill」都拿到，而不是顾此失彼。

> **要点**
> - KV/prompt cache 只认逐字前缀：压缩改写历史→前缀失效→重 prefill
> - 切成「稳定前缀 + append-only 尾部」，低频成段压、只折叠冻结老段
> - 用常驻 tool-ledger（工具+参数指纹+结果引用）保「已做过」记账，防重复调用
> - 结果按参数哈希 memo 化，重复请求也不触发真实副作用

## 延伸 / 追问

**追问：什么时候触发压缩最合适？每轮压、还是按阈值批量压？**

优先**按缓存边界批量压**，别每轮压。每轮改写历史等于每轮制造一次 cache miss，把 KV 复用的收益全赔进去。合理触发有两条线：**按预算**——尾部累计 token 逼近窗口（如 ~70%）时压一次；**按结构**——一个子任务/阶段收尾时，把该阶段轨迹整段折叠成摘要。两者都保证「一次性折叠一大段、并入前缀后长期命中」，而非零敲碎打。工程上再对齐 provider 的 prompt-cache breakpoint：把摘要写在断点之前、让新前缀成为新的可缓存单元，随后多轮复用摊薄这次 miss 的成本。

## 参考

- Anthropic Docs，*Prompt Caching*：https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- Anthropic Engineering，*Effective Context Engineering for AI Agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
