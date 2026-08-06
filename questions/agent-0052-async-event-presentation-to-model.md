---
id: agent-0052
title: 异步事件堆积时，如何把工具结果、用户消息和系统提醒组织给模型？
category: agent
tags: [async-agent, event-queue, context-engineering, summarization, state-management]
difficulty: medium
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 4 章
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

异步 Agent 运行时，工具结果、用户新消息、系统提醒（超时、审批、护栏告警等）会并发到达并在一轮之间堆积。如何把这些异构事件组织进上下文喂给模型，才能让它抓住重点、正确决策，而不是只盯着最后一个事件？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-06

**核心矛盾：** 事件是「并发、异构、会堆积」的，模型上下文却是「线性、有限、有近因偏置」的。原始事件流按到达顺序糊上去，模型只会盯末尾那条、漏掉更重要的早到事件。

**硬约束：别重排 transcript，只额外生成一份 digest。** 组织事件 ≠ 改真实 message history——底层 protocol transcript 的 role、时间因果、以及每个 `tool_result` 回接对应 `tool_use`（`tool_use_id`）的关联都必须原样保留，否则破坏协议正确性与 KV cache。真正做排序/分组/摘要/高亮的，是在其之上**额外生成的一块有界 pending-events digest**：把本轮堆积的待处理事件整理成「重点在前」的只读简报，放在决策点附近。下面四步都作用于 digest，而非 transcript。

**1. 排序：语义优先。** digest 内按「决策相关度」排：系统策略/审批护栏 > 用户新指令 > 关键工具结果 > 普通结果 > 状态通知；同级再按时间。务必区分 **system policy**（真正的高权限指令）与 **runtime system event**（超时、审批请求等运行时通知）——后者只是高优先的待办，不能靠套个 `SYSTEM` 标题就伪装成更高的 instruction authority。

**2. 分组：同类聚合。** digest 内把同类事件聚在一起便于整体判断（下例是额外生成的 digest，非重排后的对话）：

```
┌ PENDING DIGEST（本轮待处理·只读简报）──┐
│ [策略/护栏] ⚠ 审批待批：删库操作        │
│ [运行时]    ⚠ tool_call#7 超时(已重试1) │
│ [用户新输入] 先别删，先导出一份备份      │
│ [工具结果]  ✔ search×3 命中12 ✖ db 超时 │
└ STATUS：目标X | 步4/6 | 预算18/50 ──────┘
```

**3. 压缩：摘要 + 去重，控 token。**
- **去重/合并**：重复检索、心跳/进度事件折叠成一条带计数（`search×3`），只留代表性载荷。
- **摘要**：长结果（大 JSON、日志）摘要留结论，原文存外部记忆给引用句柄。
- **有界**：每类只留最近 N 条并截断，旧的滚动进摘要。

**4. 提级：关键事件显式高亮。** 别指望模型在长列表里自己发现重点：用显式标记（`⚠`）、置于末尾、并在状态栏点名未决事项，把「有高优先事件在等你」变成绕不开的信号。用户新指令尤其要提级——它可能推翻正在执行的计划。

**一句话：** 底层 transcript 保持原序与 `tool_use`↔`tool_result` 关联不动，另起一份有界 digest 做**语义排序、分组、摘要、提级**，交给模型的是「重点在前、结构清晰、长度有界」的简报，而非按时间糊上来的流水。

## 延伸 / 追问

**追问：用户在工具执行中途发来新消息，是立刻打断当前动作，还是等这一步跑完再一起给模型？**

看该动作的**工具契约**，而非简单二分。给每个工具标注 `cancelable` / `idempotent` / `transactional` 三个属性，据此决策：① **只读或可回滚**（检索、读文件、事务型写）——软打断：在工具支持的 **safe point** 发出取消，让它到达一致点后，下一轮把「用户新指令 + 已完成部分的结果」一起提级喂给模型重规划。② **有副作用且非事务型**（外部转账、发邮件、第三方 API）——外部系统往往无法保证原子性，取消后仍可能 **outcome unknown**（请求已发但响应未回）。所以不是「必须原子」，而是把执行状态显式记为 `running / committed / rolled_back / unknown`；遇到 `unknown` 先做 **reconciliation**（查询对账/幂等键重放确认）确定真实结果，再连同用户新指令交给模型，避免拿半执行的脏状态去重规划。工程上：新消息先入队打断点，在**轮边界**统一注入而非硬中断执行线程；紧急停止（用户喊「停」）走独立高优先信号通道，触发 safe-point 取消与护栏。核心是把「响应及时」和「状态一致」分开——调度可抢占，但副作用动作的收尾必须由契约驱动、以对账兜底。

## 参考

- Anthropic Engineering，*Effective context engineering for AI agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic Engineering，*Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
