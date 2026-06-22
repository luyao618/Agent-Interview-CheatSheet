---
id: engineering-0003
title: 讲一下分布式令牌桶限流
category: engineering
tags: [engineering, rate-limiting, token-bucket, redis, distributed]
difficulty: medium
role: engineer
contributor: 佚名
source: 快手
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

讲一下分布式令牌桶限流。

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

**原理。** 令牌桶（Token Bucket）维护一个容量为 `capacity` 的桶，按固定速率 `rate`（个/秒）匀速放令牌；请求到来时取走一个（或 N 个）令牌，取到放行、取不到限流。桶的存量上限是 `capacity`，因此它**允许突发**：攒下的令牌能让短时流量一次性冲过去，平均速率仍被 `rate` 约束——这正是它优于「漏桶」的地方（漏桶恒速流出，压不住突发也利用不了空闲）。

```
       rate 个/秒
  令牌 ─────────▶ ┌──────────┐ 桶(≤capacity)
                  │ ●●●●●○○○ │
  请求取令牌 ◀──── └──────────┘
   有→放行 / 无→拒绝(或排队)
```

**为什么要"分布式"。** 单机版把桶放在进程内存里即可，但多实例部署时每台各算各的，N 台机器实际放过 `N×rate`，全局限速失效。需要把桶的状态（当前令牌数、上次补桶时间）**集中存储**，典型用 Redis 做共享存储。

**核心难点：原子性。** "补桶 + 取令牌"是读-改-写复合操作，并发下必须原子，否则会超发。直接用多条命令有竞态，**标准做法是 Redis + Lua 脚本**：脚本在 Redis 单线程里原子执行，一次完成「按时间差补令牌→判断够不够→扣减→回写」。惰性补桶（lazy refill）是关键技巧——不开后台定时器，每次请求时按 `min(capacity, tokens + (now - last) × rate)` 现算应补的量，省去定时任务。

```lua
-- KEYS[1]=bucket  ARGV: rate, capacity, now, requested
local b = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(b[1]) or capacity
local last   = tonumber(b[2]) or now
tokens = math.min(capacity, tokens + (now - last) * rate)  -- 惰性补桶
local ok = tokens >= requested
if ok then tokens = tokens - requested end
redis.call('HMSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', KEYS[1], ttl)        -- 冷 key 自动回收
return ok and 1 or 0
```

**突发处理。** `capacity > rate` 即留出突发余量：空闲时把桶蓄满，峰值来时一次放行至多 `capacity` 个，再回落到匀速。调大 `capacity` 容忍更大突发，调小则更平滑。

**集群一致性与时钟问题（高频追问点）。**
- **时间基准要统一**：`now` 必须取 **Redis 服务端时间**（`redis.call('TIME')`），不要用各应用机器的本地时钟——客户端时钟漂移会让补桶量算错，导致多放或少放。
- **单点 Redis 是性能与一致性的平衡点**：单实例天然串行、状态唯一，最简单可靠；要高可用上 Cluster，则同一个限流 key 落在同一分片即可，不要把一个桶拆到多节点。
- **故障降级**：Redis 不可用时按业务定策略——「fail-open」放行保可用性，或「fail-closed」拒绝保护后端，需显式选择。

**一句话。** 分布式令牌桶 = 令牌桶算法 + Redis 共享状态 + Lua 原子「惰性补桶/取令牌」+ 服务端统一时钟；它在限住全局平均速率的同时还能吃下突发，是 API 网关、LLM 调用配额等场景的主力限流器。

## 延伸 / 追问

**追问：和滑动窗口、漏桶比，分别什么场景用？**

三者定位不同。**漏桶**出口恒速，强制平滑、不放突发，适合需要保护下游"绝对匀速"的场景（如写入限速），但利用率低。**令牌桶**允许攒令牌后突发，平均速率受控，适合大多数 API/配额限流——既挡住持续高压，又不误杀正常的瞬时尖峰。**滑动窗口**精确统计"过去 T 秒内的请求数"，按真实计数限流、无突发放大，适合"每分钟最多 X 次"这类**计数语义**强的配额；代价是要存时间戳/分桶计数，内存与计算开销比令牌桶大。实务中常**组合**：网关层用令牌桶平滑+扛突发，业务层用滑动窗口卡精确配额。选型口诀：要吞突发选令牌桶，要绝对平滑选漏桶，要精确计数选滑动窗口。

## 参考

- Redis Docs，*How to implement rate limiting*：https://redis.io/learn/howtos/ratelimiting
- Stripe Engineering，*Scaling your API with rate limiters*（token bucket 实战）：https://stripe.com/blog/rate-limiters
- Redis Docs，*EVAL / Lua scripting*（原子脚本）：https://redis.io/docs/latest/commands/eval/
