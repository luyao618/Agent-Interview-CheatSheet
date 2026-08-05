---
id: agent-0039
title: ReAct 轨迹变长后，如何在不丢关键状态的前提下降低上下文成本
category: agent
tags: [react, context-engineering, trajectory, compaction, kv-cache]
difficulty: hard
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 1、2 章
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

ReAct 轨迹变长后，如何在不丢关键状态的前提下降低上下文成本？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-05

**先看成本从哪来。** ReAct 每轮把全部 `Thought → Action → Observation` 拼回 prompt 再喂给模型，第 n 轮输入 ≈ 前 n-1 轮之和，累计 input 随轮数呈 **O(n²) 二次增长**；其中工具原始返回（Observation）往往是最大头。所以降本的靶心是：**只保留「下一步决策真正需要的状态」，把冗长的历史过程压掉**，而不是无脑截断。

```
朴素 ReAct：每轮重发全历史        分层后：state 固定 + 历史压缩
轮1 ▏                            [固定] system/工具/目标/约束
轮2 ▏▏                           [state] 已确认事实·TODO·教训   ← 不丢
轮3 ▏▏▏         O(n²)            [摘要] 旧轮 Thought 要点+结果
轮4 ▏▏▏▏  ← 二次膨胀              [原文] 仅最近 1~2 轮明细       ← 近似 O(n)
```

**五个手段，从「保状态」到「省算力」：**

1. **关键状态外置（不丢的核心）**：把目标、约束、已确认事实、待办、踩过的坑写进一个显式 `state / scratchpad` 块，放窗口固定位置。历史轨迹可裁剪，但这块永远在——这是「不丢关键状态」的关键。
2. **历史分级压缩**：区分「结论」与「过程」。旧轮只留 Thought 要点 + 关键结果，原始 Observation 摘要或丢弃；用**滚动摘要（rolling summary）**把 N 轮前的轨迹归并成一段，近 1~2 轮保留明细。
3. **Observation 瘦身**：工具返回只回灌提取后的字段，大 blob 落外部存储，用 id / 引用回指，需要时再按需取回，避免整篇 dump 进上下文。
4. **子 Agent 隔离**：探索性、长的子任务交给 sub-agent，在它自己的窗口里跑完，**只把结论回传**主轨迹；主 Agent 不被子任务的中间步骤污染，天然限制了膨胀。
5. **KV-Cache 友好布局**：稳定内容（system、工具定义、目标、few-shot）放最前且**逐字不变**，变动内容一律**追加到末尾**；不要在前缀里插改，否则缓存整体失效。前缀命中可省下这部分的 prefill 算力并享受缓存折扣。

一句话：**用「固定的 state 块 + 分级压缩的历史」替换「全量重发」**，把二次增长压回近似线性，同时保证决策所需状态零丢失。

## 延伸 / 追问

**追问：摘要压缩会丢信息，怎么判断哪些状态"必须保留"、什么时候触发压缩？**

用「决策相关性」而非「新鲜度」来判断保留：凡是影响后续动作选择的——**目标与验收标准、硬约束、已确认结论、未完成 TODO、失败教训与不可重试项**——进 state 块常驻；纯过程性内容（中间检索原文、可复现的工具调用细节）才是压缩对象。触发时机常用两条线：**按预算**（累计 token 达窗口的 ~70% 触发一次 compaction），或**按结构**（一个子任务/阶段结束时归并该阶段轨迹）。工程上再加两道保险：压缩后校验 state 里的关键 id / 数值未被摘要改写；对高风险动作保留可回溯的原始轨迹引用，便于回放和纠错。

## 参考

- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, 2022：https://arxiv.org/abs/2210.03629
- Anthropic Engineering, *Effective Context Engineering for AI Agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic Docs, *Prompt Caching*：https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
