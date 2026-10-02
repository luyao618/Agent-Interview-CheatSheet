---
id: llm-0025
title: Continuous Batching 为什么能提高 LLM 服务吞吐，却不保证每个请求都更快？
category: llm
tags: [continuous-batching, serving, scheduling, chunked-prefill, latency]
difficulty: medium
role: engineer
contributor: 佚名
source: 公开 vLLM 面试题第 8 题扩展改编；Orca 论文与固定版本 vLLM 文档核实（见参考）
status: published
updated: 2026-10-02
answers:
  - author: GPT-6-Astra
    type: ai
    model: GPT-6-Astra
    answered: 2026-10-02
    updated: 2026-10-02
---

## 问题

一个 LLM 服务把请求凑成固定 batch，等整批生成完再处理下一批。长短输出混在一起时，短请求结束后出现空槽，新请求仍在排队。

Continuous Batching 如何改善这个问题？它和普通动态组批、chunked prefill、PagedAttention 有什么区别？为什么总吞吐提升时，部分请求的首 token 或后续 token 延迟仍可能变差？请设计可验证的调度示例和线上验收。

本题从公开 vLLM 面试资料第 8 题扩展改编，不是经核实的公司真题；不沿用来源中的固定加速倍数或“消除等待”的绝对表述。

## 答案 · GPT-6-Astra

> 🤖 AI 答案 · 模型：GPT-6-Astra · 回答 2026-10-02

**Continuous Batching 把请求准入和移出的机会下沉到生成迭代边界：完成的序列退出，有资源时接入等待中的请求，不必等待同批最长序列结束。** 它减少批次尾部空槽，但不是无限接单，也不保证所有请求的端到端延迟都下降。

[llm-0018](llm-0018-kv-cache-prefill-decode.md) 解释 KV Cache 状态，[llm-0016](llm-0016-quantization-local-memory-budget.md) 解释显存预算；本题聚焦**服务调度粒度与吞吐—延迟权衡**，不重复缓存大小推导。

### 1. 静态 batch、动态组批和迭代级调度

- **本题的静态 batch**：启动后一组成员固定，短请求完成也不补新请求，等剩余成员全部结束再开下一组。短请求结果可以先返回，不必人为等整批；真正的瓶颈是槽位不能补充。
- **普通动态组批**：常指执行前按队列长度或等待时间聚合请求。能改善凑批，但如果整个生成期间成员仍固定，就没有解决长短输出的尾部空槽问题。
- **Continuous Batching**：每次迭代后更新活动集合，后来的请求可以在老请求仍生成时加入。不同框架也称 iteration-level 或 in-flight batching；名称不能替代对实际行为的检查。

“补位”发生在调度边界，不是中断任意一个正在运行的 GPU kernel。接入新请求通常还要做 prefill，并为其 KV Cache 分配空间，不能把它当成零成本插入。

### 2. 三种优化分别改变什么？

| 技术 | 优化对象 | 不代表什么 |
| --- | --- | --- |
| Continuous Batching | 在迭代边界选择本轮服务哪些序列 | 不保证无限并发或零排队 |
| Chunked Prefill | 把长 prompt 的 prefill 拆为多个调度块，与 decode 交错或混合 | 不是截断 prompt，也不是把输入文本分词成 chunk 后丢失上下文 |
| PagedAttention / 分块 KV 管理 | KV Cache 的物理分配、寻址及共享，降低某些浪费 | 不是调度策略本身，也不消除每条独立上下文的 KV 数据 |

三者可配合，但不能把收益全归给一个开关。本文引用的 vLLM **v0.10.2 V1** 文档描述了优先安排 decode，再利用本轮剩余 token 预算安排 prefill、必要时切分的策略；这只是固定版本行为，不代表所有引擎都如此。

应分别理解最大活动序列数、本轮 token 预算与可用 KV 空间。decode 迭代通常为每条序列推进一个 token，而 prefill 可处理很多输入 token；“32 个请求”不等于“本轮只算 32 个 token”。投机解码等路径还可能一次推进多个输出 token。

### 3. 最小模拟：补位怎样减少空槽？

假设只有两个执行槽位，A/B 在第 0 轮到达，C 在第 1 轮到达；分别需要 1、4、1 个 decode 步。**所有请求 prefill 已完成，每轮恒定耗时一个单位，每个活动请求推进一步，内存无限制**。这是刻意简化的调度模型，不是 GPU benchmark。

静态策略的第一批是 A/B，A 完成后空槽保持空闲，C 要等 B 结束；连续策略下一轮即可用空槽处理 C。两种策略均在请求实际完成时交付结果，不把静态策略故意写成整批统一返回。

```python
requests = [("A", 0, 1), ("B", 0, 4), ("C", 1, 1)]


def simulate(continuous):
    pending = list(requests)
    active, done, trace = {}, {}, []
    capacity, tick = 2, 0
    while pending or active:
        if continuous or not active:
            while len(active) < capacity and pending and pending[0][1] <= tick:
                name, _, steps = pending.pop(0)
                active[name] = steps
        trace.append(tuple(active))
        for name in list(active):
            active[name] -= 1
            if active[name] == 0:
                done[name] = tick + 1
                del active[name]
        tick += 1
    return done, trace


static, static_trace = simulate(False)
continuous, continuous_trace = simulate(True)
assert static == {"A": 1, "B": 4, "C": 5}
assert continuous == {"A": 1, "C": 2, "B": 4}
assert static_trace == [("A", "B"), ("B",), ("B",), ("B",), ("C",)]
assert continuous_trace == [("A", "B"), ("B", "C"), ("B",), ("B",)]
# 两种策略做相同数量的 decode 步，收益来自调度而非漏算工作。
assert sum(map(len, static_trace)) == sum(map(len, continuous_trace)) == 6
for done in (static, continuous):
    assert set(done) == {name for name, _, _ in requests}
    assert all(done[name] >= arrival + steps for name, arrival, steps in requests)
print("static completion:", static)
print("continuous completion:", continuous)
print("iterations:", len(static_trace), "->", len(continuous_trace))
print("batching schedule checks passed")
```

实际执行输出：

```text
static completion: {'A': 1, 'B': 4, 'C': 5}
continuous completion: {'A': 1, 'C': 2, 'B': 4}
iterations: 5 -> 4
batching schedule checks passed
```

模拟中 A/B 的完成时间不变，C 提前，总迭代数减少。但真实 GPU 的每轮耗时随 batch、上下文长度、prefill 混入和内存访问变化；不能用这里的轮数比例预测真实加速比。

### 4. 为什么吞吐升了，用户反而觉得慢？

- **更大 batch 的单轮更慢**：同时服务更多请求可能提升总输出 token/s，但每个流的 token 间隔可能变长。
- **长 prefill 干扰 decode**：大量输入计算占据执行时间；分块可减轻长时间停顿，但太小的 prefill 预算也可能延后新请求首 token。
- **KV 空间不足**：更多活动序列和更长上下文带来内存压力，可能触发等待、抢占与重计算。文档里的参数建议不是跨硬件通用最优值。
- **负载超过容量**：提高利用率不等于队列稳定。应限制队列与准入、提供超时/取消及公平性，不能靠不断增大并发掩盖排队。

低延迟与高吞吐不是简单二选一，但必须用目标负载验证平衡点。解码优先的策略也需要检查长 prompt 请求是否长期得不到服务；不要只盯平均值。

### 5. 怎样做公平验收？

1. **固定条件**：同模型/精度、硬件、采样、输入输出长度分布与缓存策略。区分冷启动、预热、前缀缓存命中和正常运行，不能用不同工作量作加速对照。
2. **重放实际到达过程**：同时测稳定负载、突发和长短混合请求。仅固定并发的 closed-loop 测试可能隐藏积压；补充按外部到达率施压的 open-loop 测试并报告实际接受、完成与拒绝量。
3. **统一测量边界**：TTFT 可定义为客户端发出到首个输出 token；包含排队、prefill、网络等。定义 ITL 为相邻输出 token 的时间间隔；若使用 `(最后 token 时刻 - 首 token 时刻)/(输出数-1)` 作为请求级 TPOT，则单 token 输出不适用，不能填 0 混入均值。流式消息块不一定对应单个 token，必须注明代理指标。
4. **一起看质量与服务指标**：总输出 token/s、请求/s、TTFT/ITL/端到端延迟的分位数、失败/超时/抢占率、KV 使用与排队时间；请求级平均 TPOT 可能掩盖流中长停顿，需单独看 ITL 尾部。保持输出长度口径，不把提前截断当作速度提升。
5. **报告满足 SLO 的有效吞吐**：先定义哪些请求满足首 token 与流畅度等门槛，再统计有效完成量，而不是只报告 GPU 利用率最高的一点。按长短输入、租户和优先级分组，检查公平性。

## 延伸 / 追问

**追问 1：开启 continuous batching 就能删掉限流和背压吗？**

不能。调度改善利用率，不能让有限算力承受无限到达流量；它与服务入口的队列上限和准入控制是不同层的问题。

**追问 2：Chunked prefill 的块越小，所有延迟都越好吗？**

不是。较小块可能保护 decode 的迭代间隔，却增加长 prompt 完成 prefill 的轮次与调度开销，损害该请求 TTFT。要按输入分布和 SLO 联合调优。

**追问 3：只看平均输出 token/s 足以选配置吗？**

不足。均值可能掩盖长请求饥饿、短请求排队、流式停顿和失败；应同时比较分位延迟、错误率及 SLO 内有效吞吐。

## 常见误区

- **“Continuous Batching 就是执行前多等几毫秒凑 batch。”** 关键是生成迭代之间能改变成员。
- **“PagedAttention 与 continuous batching 是同一个算法。”** 一个管理缓存访问与布局，一个管理服务调度。
- **“有空槽，新请求就一定马上 decode。”** 还受 prefill、token 预算、KV 空间与策略限制。
- **“模拟少一轮等于 GPU 一定按同样比例提速。”** 模拟没有硬件计时，真实每轮成本不恒定。

## 参考

- 选题线索：[vLLM 公开面试题，第 8 题 What is Continuous Batching?](https://github.com/shizhengLi/vllm-learning/blob/2a991fd9241dee2bd0a9ae45fa37d85f70f80c88/docs/interview_questions.md#8-what-is-continuous-batching-what-are-its-advantages)。固定 commit，独立扩展改编，不采用来源中的泛化性能保证。
- Yu et al., [Orca: A Distributed Serving System for Transformer-Based Generative Models](https://www.usenix.org/system/files/osdi22-yu.pdf)，OSDI 2022，iteration-level scheduling：以生成迭代而非完整请求作为调度粒度。
- vLLM **v0.10.2**，[Optimization 文档](https://github.com/vllm-project/vllm/blob/v0.10.2/docs/configuration/optimization.md)，Preemption 与 Chunked Prefill 小节：V1 的调度预算、prefill/decode 权衡和内存压力。本文未运行 vLLM，也不将固定版本描述当所有版本默认行为。

来源访问与示例核验日期：**2026-10-02**。仅运行确定性调度模拟，没有运行真实模型或 GPU 性能测试。
