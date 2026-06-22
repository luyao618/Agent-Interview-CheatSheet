---
id: engineering-0005
title: 滑动窗口和令牌桶相比有什么区别？
category: engineering
tags: [engineering, rate-limiting, sliding-window, token-bucket, burst]
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

滑动窗口和令牌桶相比有什么区别？（限流选型：两者在突发处理、限流语义与适用场景上的差异）

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

两者都能限住「平均速率」，**根本区别在限流语义**：令牌桶限的是**速率**且**允许突发**，滑动窗口限的是**计数**且**不放大突发**。

**令牌桶（速率 + 突发）。** 桶按 `rate` 匀速补令牌、存量上限 `capacity`；空闲期攒下的令牌能让流量一次性冲过去，瞬时可达 `capacity`，平均仍受 `rate` 约束。它**主动留出突发余量**，吃得下正常的瞬时尖峰。

**滑动窗口（计数 + 平滑）。** 统计「现在往前 T 秒」的真实请求数，到 N 就拒。窗口随当前时刻连续右移，**不存突发额度**——你攒不下配额，只能按「过去 T 秒最多 N 次」被精确卡住，天然适配硬性次数配额。

```
令牌桶：空闲攒令牌 → 峰值一次放 capacity 个（突发）
  ▁▁▁▁▁████   ← 瞬时可超 rate，均值≤rate

滑动窗口：任意时刻回看 T 秒，计数≤N（无突发放大）
  │←—— T ——→│  超过 N 立即拒
```

**关键差异点。**

| 维度 | 令牌桶 | 滑动窗口 |
| --- | --- | --- |
| 限流对象 | 速率（个/秒） | 计数（T 秒内次数） |
| 突发 | **允许**（攒令牌） | **不允许**（无额度积累） |
| 状态 | 令牌数 + 时间戳（2 个值） | ZSET 日志 O(QPS×T)，或分桶计数 |
| 语义 | 「控平均速率、容忍尖峰」 | 「每 T 秒最多 N 次、绝不超发」 |
| 典型场景 | API 网关、LLM 调用平滑 | 第三方调用额度、支付/敏感接口 |

**怎么选。**
- 要**控平均速率又想容忍正常尖峰**（网关扛突发、空闲期不浪费）→ 令牌桶。
- 要**精确次数配额、绝不超发**（对外 API 每分钟 X 次、计费配额）→ 滑动窗口。
- 内存敏感、状态极轻 → 令牌桶（两个数）；要可审计每条请求 → 滑动窗口 ZSET。

实务常**组合**：网关层用令牌桶平滑流量、扛突发，业务层用滑动窗口卡死精确配额。一句话——**要吞突发选令牌桶，要精确计数选滑动窗口**。

## 延伸 / 追问

**追问：令牌桶能不能也做到「精确每分钟 N 次」？**

不能精确等价。令牌桶把 `capacity` 设为 1 个窗口的配额、`rate=N/T`，近似实现了均速 N/T，但它**仍允许把攒下的令牌一次突发**——某一秒可能放过接近 `capacity` 个，而滑动窗口在任意 T 秒回看都严格 ≤N。所以「绝不在任何 T 秒窗口超发」这种硬配额语义，令牌桶给不了，只有滑动窗口（按真实计数）能保证。反过来，若需求只是「长期均速可控、短时尖峰可接受」，令牌桶用两个整数就够，比滑动窗口存日志省得多。

## 参考

- Stripe Engineering，*Scaling your API with rate limiters*（token bucket vs 各类限流器）：https://stripe.com/blog/rate-limiters
- Cloudflare Blog，*How we built rate limiting capable of scaling to millions of domains*（滑动窗口计数）：https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
