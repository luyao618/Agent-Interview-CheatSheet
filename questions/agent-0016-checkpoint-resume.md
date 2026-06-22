---
id: agent-0016
title: Agent 如何实现 checkpoint / resume
category: agent
tags: [agent, checkpoint, resume, state-persistence, durability]
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

Agent 如何实现 checkpoint / resume？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

核心思路：把 Agent 的「运行进度」做成**可序列化的状态机**——每跑完一步就把状态落盘成 checkpoint，崩溃/中断后从最近的 checkpoint 加载、重放未完成的步骤继续跑。关键是**状态完整**、**写入可靠**、**重放幂等**三件事。

**1. 要存什么——序列化完整状态**

恢复后能无缝接续的前提是状态没漏。一份 checkpoint 至少含：

- **对话/上下文**：messages、system prompt、已注入的检索结果。
- **计划与进度**：任务树/待办、当前第几步、已完成子目标。
- **记忆**：短期 scratchpad，以及长期记忆的引用（向量库 id，不必拷贝正文）。
- **工具调用轨迹**：每步 `(tool, 参数, 结果)`，用于重建现场、避免重复执行。
- **游标/外部副作用记录**：已处理到哪、已发出哪些写操作（配幂等键）。

```
  Step N 执行完
      │
      ▼
  快照 state = {messages, plan, step_idx,
               memory_ref, tool_history, cursor}
      │ 原子写 (temp→fsync→rename)
      ▼
  ┌─────────────┐   crash    ┌──────────────┐
  │ checkpoint  │ ─────────► │  load 最近点  │
  │  store(版本) │            │  重放未完步骤 │
  └─────────────┘            └──────────────┘
```

**2. 怎么存——持久化要可靠**

- **存储**：DB / KV / 对象存储；状态机框架（如 LangGraph）用 checkpointer 持久化每个节点后的状态。
- **原子写**：写临时文件再 rename，或事务提交，避免半截脏快照。
- **时机**：每步后或每个关键节点后写；附 `run_id + step` 版本号，支持回看/回滚。
- **粒度权衡**：写太频伤吞吐，太疏丢进度——按步长或耗时阈值折中。

**3. 怎么恢复——断点重放要幂等**

恢复 = 读最近 checkpoint → 还原内存态 → 从 `step_idx` 续跑。难点是**副作用重放**：进程可能在「执行了工具但没存结果」处崩溃，重放会重复执行。对策：

- **幂等键**：写操作带去重 id，重复请求被服务端忽略。
- **先记意图再执行**（write-ahead）：恢复时检查该步是否已落结果，已完成就跳过。
- 把工具尽量设计成可重入/查询型，外部不可逆动作（付款、发消息）单独加去重与确认。

**一句话**：checkpoint = 把 Agent 变成「每步存档的状态机」；resume = 「读档 + 幂等重放」。状态全、写可靠、重放幂等，三者齐了才能真正断点续跑。

## 延伸 / 追问

**追问：多步任务跑到一半崩了，怎么保证恢复后不把已执行的工具重复执行一遍？**

根因是「执行」与「记录结果」非原子，崩在两者之间就会重放重做。两条主线兜底：① **幂等**——给每个有副作用的工具调用生成稳定去重键（如 `run_id + step + 参数哈希`），服务端/中间件按键去重，重复请求直接返回首次结果；② **WAL 式两段记录**——执行前先持久化「即将调用 X」，执行后再写「结果 = Y」。恢复时按轨迹逐步核对：已有结果的步跳过、只记了意图没结果的步，要么查询外部系统的真实状态再决定补做，要么对可重入工具安全重试。对付款、发邮件这类不可逆动作，额外加业务幂等表或确认回执。原则：**宁可多查一次状态，也不盲目重放**。

## 参考

- LangGraph Docs，*Persistence / Checkpointer*：https://langchain-ai.github.io/langgraph/concepts/persistence/
- Temporal Docs，*Workflow Replay & Determinism*：https://docs.temporal.io/workflows
- Anthropic Engineering，*Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
