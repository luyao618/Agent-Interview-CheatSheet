---
id: engineering-0001
title: 多 Agent 协作并发操作业务实体时，用 Redis 分布式锁如何避免主从切换导致锁丢失
category: engineering
tags: [engineering, redis, distributed-lock, redlock, concurrency]
difficulty: hard
role: engineer
contributor: 佚名
source: 京东
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

多 Agent 协作更新知识库版本、并发操作业务实体时，如果用 Redis 分布式锁，如何避免主从切换导致锁丢失？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

**问题根因。** 单点 Redis（主从架构）的复制是**异步**的：客户端 A 在 master 上 `SET key val NX PX` 拿到锁，master 还没把这条写同步给 replica 就宕机，哨兵把 replica 提升为新 master——新 master 上根本没有这把锁，客户端 B 又能拿到。于是 **A、B 同时持锁**，两个 Agent 并发写同一实体，互斥被破坏。

```
A 拿锁(master) ──┐ 异步复制未到达
                 ▼
            master 宕机 → replica 升主（无锁）
                 ▼
B 拿锁(新master) ──→ A、B 同时持锁 ✗
```

**对策一：Redlock 多节点。** 部署 N 个（典型 5 个）**相互独立**的 master，客户端依次向各节点加锁，在多数（N/2+1）节点上成功且总耗时小于锁有效期才算成功。少数节点宕机/切换不影响多数派，避免单点复制丢锁。代价：运维 N 套实例、时钟假设强、对 GC/网络停顿敏感，社区（Kleppmann）对其正确性有争议，不适合做强一致的唯一裁决。

**对策二：fencing token（关键兜底）。** 锁本身无法消除「持锁进程卡顿后锁已过期、却仍来写」的问题。让锁服务每次发放**单调递增的 token**，写入时把 token 带给被保护资源（DB/存储），资源端**拒绝比已见过的更小的 token**。即使旧持有者复活，其 token 较小会被拒，从根上保证互斥。这是 Redlock 论争中公认的正确性补丁。

**对策三：换强一致协调器。** 若业务对正确性零容忍，直接用基于 Raft/ZAB 的 **etcd / ZooKeeper**：写经多数派提交才返回，leader 切换不丢已确认的锁；配 lease + watch 实现自动续约与故障释放。代价是吞吐略低、延迟略高，但换来「不会双持」的强保证。

**工程权衡。**

| 方案 | 一致性 | 复杂度 | 适用 |
| --- | --- | --- | --- |
| 单点 Redis 锁 | 弱（会丢） | 低 | 容忍偶发并发的幂等场景 |
| Redlock | 中 | 中 | 可用性优先、能配 fencing |
| etcd/ZK | 强 | 中高 | 正确性优先的核心写 |

**一句话：** 锁只是「降低概率」，真正的正确性靠 **fencing token + 写端幂等/版本号校验**；要强一致就上 etcd/ZK，别让异步复制的 Redis 单独承担唯一裁决。

## 延伸 / 追问

**追问：拿到锁后业务执行超时、锁提前过期怎么办？**

两条线一起做。其一**自动续约（watchdog）**：持锁期间后台线程定期对锁续期（Redisson 默认看门狗每 1/3 过期时间续一次），只要进程存活锁就不会过期，进程崩了则到期自动释放。但续约不能解决进程「假死」（长 GC/STW）——它没死却停了，仍可能过期后被他人抢锁。其二**fencing + 写端校验兜底**：无论锁是否过期，写操作都带单调 token 或实体版本号（乐观锁 `WHERE version=?`），DB 拒绝过期请求。这样「续约保活、fencing 保正确」，避免只靠续约的侥幸。释放锁要用 Lua 脚本校验「锁的 value 是不是自己的 uuid」再删，防止误删他人锁。

## 参考

- Redis Docs，*Distributed Locks with Redis (Redlock)*：https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/
- Martin Kleppmann，*How to do distributed locking*（fencing token 论争）：https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html
- Redisson Wiki，*Distributed locks and synchronizers*（看门狗自动续约）：https://github.com/redisson/redisson/wiki/8.-distributed-locks-and-synchronizers
- etcd Docs，*Concurrency API (lock / lease)*：https://etcd.io/docs/latest/dev-guide/api_concurrency_reference_v3/
