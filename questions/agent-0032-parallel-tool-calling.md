---
id: agent-0032
title: 怎么做并行 Tool Calling，既提升吞吐又保证一致性和可回放性
category: agent
tags: [agent, tool-use, parallel, concurrency, idempotency, replay]
difficulty: hard
role: engineer
contributor: 佚名
source: 未知
status: published
updated: 2026-06-29
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-29
    updated: 2026-06-29
---

## 问题

你怎么做并行 Tool Calling，既提升吞吐，又保证一致性和可回放性？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-29

并行 Tool Calling 的核心矛盾是：**吞吐想并发，一致性想串行，可回放想确定性**。三条主线要分别治理，不能用一把锁解决。

### 一、吞吐：把「能并发的」识别出来再放手

现代模型一轮可以一次性吐出多个 `tool_call`。真正决定能不能并发的是**依赖关系**，不是模型：

- **构建 DAG**：以「B 的入参是否引用 A 的输出」建依赖边。无边的工具进同一批并发执行，有边的拓扑排序分层跑。
- **并发执行**：同层用 `asyncio.gather` / 线程池并发，受 `Semaphore` 限流（控住下游 QPS 与连接数），按工具维度配超时与重试。
- **只读优先**：检索、查询类只读工具天然可并发；写操作单独识别（见下）。

```
模型一轮输出: [search(x), search(y), book(id=?)]
   ├─ search(x) ─┐  (无依赖, 并发)
   ├─ search(y) ─┤
   └─ book(id) ──┘  依赖 search 结果 → 下一层串行
```

### 二、一致性：区分读/写，写操作单独收口

并发的杀手是**并发写**。策略是分级：

1. **读写分离**：只读工具放开并发；写工具（下单、扣款、改库存）**默认串行**或加锁，绝不和同实体的其他写并发。
2. **幂等键**：每个写调用带稳定 `idempotency_key`（由 `run_id + tool_call_id` 派生）。重试 / 重放命中同键直接返回首次结果，避免重复下单（幂等与分布式事务细节见 [engineering-0002](engineering-0002-idempotency-distributed-transaction.md)）。
3. **同实体加锁**：对同一业务实体的并发写用分布式锁串行化（[engineering-0001](engineering-0001-redis-distributed-lock-failover.md)）。
4. **快照隔离**：同批并发里若读、写并存，读工具应基于**一致性快照 / 版本号（MVCC）**取数，并对本 run 的写保证 read-your-writes，避免读到并发写的中间态；强一致场景则把读排到写之后。
5. **结果回灌确定**：并发完成后，**按模型给出的 tool_call 顺序**（而非完成顺序）拼回上下文，保证下一轮模型看到的消息序列稳定。

### 三、可回放：每一步都落确定性日志

可回放 = 给定相同输入与相同工具返回，能重跑出相同轨迹。

- **Event Log**：每个 tool_call 落 `{call_id, name, args, result, ts}`。回放时**短路真实 I/O**，直接喂日志里的 result——这样回放不依赖外部系统当前状态，也能复现历史 bug。
- **固定随机源**：温度、随机 seed、并发完成顺序都不能进入状态；状态只由「有序的 tool 结果序列」决定。
- **Checkpoint**：长任务按轮次存档，崩溃后从最近 checkpoint 续跑（[agent-0016](agent-0016-checkpoint-resume.md)），续跑命中幂等键不会重复副作用。

**一句话收口**：用 DAG 拿到吞吐，用读写分离 + 幂等键 + 锁守住一致性，用有序事件日志 + 短路 I/O 换来可回放。三者解耦，各管一段。

## 延伸 / 追问

**追问：并发执行时其中一个工具失败了，整批怎么处理？**

不要「一损俱损」。按工具语义分档处理：

- **只读工具失败**：局部降级。把失败的那个 tool 结果标成 `error: <原因>` 照常回灌给模型，让模型自己决定是重试、换工具还是绕过——其余成功结果照用，不阻塞整批。
- **写工具失败**：看是否已产生副作用。带幂等键的可安全重试（重放命中同键不会重复执行）；不确定是否已落库的，走「查询确认 + 幂等补偿」而不是盲目重试。
- **同批存在依赖**：上游失败则下游依赖项直接跳过并标 `skipped`，不要用脏数据去调下游。
- **统一收口**：每个失败都进 Event Log（含错误码、是否重试、最终态），既给模型可读的错误信号，也保证回放时这次失败本身是可复现的。

关键是**失败要变成模型上下文里一条确定的、结构化的结果**，而不是抛异常炸掉整轮——这样吞吐、一致性、可回放三条线都不被单点失败破坏。

## 参考

- Anthropic，*Building effective agents*（工具编排与并行）：https://www.anthropic.com/engineering/building-effective-agents
- Anthropic，*Claude tool use（parallel tool use）*：https://docs.claude.com/en/docs/build-with-claude/tool-use
- OpenAI，*Function calling — parallel tool calls*：https://platform.openai.com/docs/guides/function-calling
