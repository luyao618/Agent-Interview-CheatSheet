---
id: engineering-0004
title: 滑动窗口算法是怎么实现的？
category: engineering
tags: [engineering, rate-limiting, sliding-window, redis, algorithm]
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

滑动窗口算法是怎么实现的？（限流场景：如何精确限制「过去 T 秒内最多 N 次请求」）

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

滑动窗口要解决固定窗口的**临界突发**问题：固定窗口在 `[0,60s)`、`[60s,120s)` 各算各的，若请求集中在 59s 和 61s，相邻两个 1s 内可放过 `2N` 次。滑动窗口让窗口随当前时刻连续右移，永远统计「**现在往前 T 秒**」的真实请求量。主流有两种实现。

**实现一：滑动日志（Sliding Log）—— Redis ZSET。** 精确但重。每个限流 key 一个有序集合，member 是请求 ID、score 是时间戳；每次请求先剔除过期成员、再数窗口内还剩多少。

```lua
-- KEYS[1]=key  ARGV: now(ms), window(ms), limit, member
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window) -- 清掉窗口外的旧请求
local cnt = redis.call('ZCARD', KEYS[1])
if cnt < limit then
  redis.call('ZADD', KEYS[1], now, ARGV[4])              -- 记录本次请求
  redis.call('PEXPIRE', KEYS[1], window)                 -- 冷 key 自动回收
  return 1                                                -- 放行
end
return 0                                                  -- 限流
```

优点：精度 100%，能精确到每一次请求。缺点：**内存随 QPS×窗口线性增长**——每秒 1 万次、窗口 60s 就要存 60 万个时间戳，热点 key 很贵。

**实现二：分桶计数（Sliding Window Counter）—— 近似但省内存。** 把窗口切成若干小桶（如 60s 切成 60 个 1s 桶），每桶只存一个**计数**而非每条日志；统计时累加落在窗口内的桶。再细一点的工业近似法是「两桶加权」：只保留当前窗口和上一窗口两个计数，按当前时刻在窗口里的进度对上一窗口做线性加权：

```
estimated = curr_count + prev_count × (1 - elapsed_in_curr / window)
```

```
  上一窗口            当前窗口
┌──────────┐      ┌──────────┐
│ prev=80  │      │ curr=30  │   滑动窗口 │←—— T ——→│
└──────────┘      └────┬─────┘            ▼
        权重 (1-elapsed/T)=0.25      30 + 80×0.25 = 50
```

内存从「O(QPS×T)」降到「O(桶数)」甚至两个整数，代价是假设流量在窗口内均匀分布、有约 0.x% 的估算误差。

**精度 / 内存权衡（高频追问）。**
- **ZSET 滑动日志**：精确、可审计每条请求，但内存/网络开销大，适合限额小、要求严格的场景（如支付、敏感接口）。
- **分桶计数**：内存恒定、性能高，桶越细越准、越粗越省，适合高 QPS 网关；两桶加权是「省到极致」的近似。
- **原子性**同样靠 **Redis + Lua**：剔除过期 + 计数 + 写入必须一次原子完成，否则并发下会超发；时间统一取**服务端时间**避免客户端时钟漂移。

**一句话。** 滑动窗口 = 随当前时刻连续移动的统计窗口；要精确用 ZSET 存请求日志，要省内存用分桶（乃至两桶加权）计数，本质是在「精度」和「内存/性能」之间挑一个落点。

## 延伸 / 追问

**追问：滑动窗口和令牌桶到底差在哪，怎么选？**

差在**语义**：滑动窗口是**计数限流**——精确统计「过去 T 秒内放过几次」，不放大突发，天然适配「每分钟最多 X 次」这类硬配额（如第三方 API 调用额度）。令牌桶是**速率限流**——允许把空闲期攒下的令牌一次性突发掉，平均速率受控但瞬时可超 `rate`，适合要平滑流量又想吃下正常尖峰的网关。选型：要「精确次数配额、绝不超发」选滑动窗口；要「控平均速率又容忍突发」选令牌桶。实务常组合——网关层令牌桶扛突发，业务层滑动窗口卡死配额。

## 参考

- Cloudflare Blog，*How we built rate limiting capable of scaling to millions of domains*（两桶加权近似）：https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
- Redis Docs，*Sorted Sets*（ZSET 滑动日志）：https://redis.io/docs/latest/develop/data-types/sorted-sets/
- Redis Docs，*EVAL / Lua scripting*（原子脚本）：https://redis.io/docs/latest/commands/eval/
