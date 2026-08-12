---
id: llm-0005
title: Agent 训练中如何判断 SFT 已经足够，应该切换到 RL？
category: llm
tags: [sft, reinforcement-learning, post-training, agentic-model, evaluation]
difficulty: hard
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 7 章
status: published
updated: 2026-08-12
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-12
    updated: 2026-08-12
---

## 问题

训练 Agent 模型常用「先形后神」的范式：先用 SFT 把输出格式和工具调用协议固化下来，再上 RL 优化决策质量。实际操作中，如何判断 SFT 已经做够了、可以切换到 RL？有哪些可量化的指标？切早了和切晚了分别会出什么问题？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-12

**SFT 教「形」，RL 教「神」**：SFT 是行为克隆，把输出格式、工具调用协议、轨迹骨架灌进去；RL 优化决策质量——该调哪个工具、何时停、错了怎么回。顺序不能反的硬机制是：策略梯度只能放大**已被采样到**的行为，轨迹连解析都过不了、reward 全零时，GRPO 组内 advantage 恒零，梯度为零，训练只是烧钱。至于更强的说法「RL 带不来 base 之外的新能力」，**只是一条窄结论**：Yue et al. 观察到当前 RLVR 在数学/代码 benchmark 上多是把 base 已有行为集中化、pass@大k 未必超过 base；它未覆盖所有 RL 方法与 multi-turn tool Agent，别当定律。

```
SFT(形) ───── gate ─────► RL(神)
格式/协议/基础能力         决策取舍/纠错/收敛
── 均在 RL 实际采样温度下测，不看 greedy ──
 ① tool_call schema 合法率（示例起点 ~95%）
 ② 轨迹可跑完率（示例起点 ~90%，不死循环、会停）
 ③ 存在可优化的成功轨迹 ← RL 的燃料
    直接信号：组内 reward 有方差的 prompt 占比
    proxy：pass@k − pass@1 的 gap（coverage）
 ④ SFT 边际收益趋平，且熵尚未坍缩
    全组 reward 恒 0/恒 1 → 补数据，RL 救不了
```

**四个可测门槛**（百分比为**示例起点、非通用硬阈值**，需按任务复杂度、rollout 成本与 reward 稀疏度校准）

1. **格式与协议合格率**：必须在 RL 真实使用的采样温度下统计，greedy 好看没有意义。schema 合法率、工具名存在性、停止符正确率是硬门槛。
2. **端到端可执行率**：rollout 跑到终局的比例，决定 RL 的有效样本率。
3. **存在可优化的成功轨迹**——最关键。对 GRPO 这类组内取 baseline 的算法，**最直接的信号是「多少比例的 prompt 能在组内采出 reward 方差（至少一条成功 rollout）」**：全组同分则 advantage 恒零，对训练零贡献。`pass@k − pass@1` 只是 **coverage proxy**，便宜好算，但聚合会掩盖「哪些 prompt 有信号」。两者都低说明能力不在分布里，补数据 / RFT / 换 base 都比硬上 RL 划算。
4. **SFT 收益递减且未过拟合**：验证集不再涨、train/val 劈叉就停；同时盯熵——坍缩说明 SFT 灌过头了。

**两侧风险**

- **切太早**：奖励几乎全零，无梯度；少数偶然跑通的轨迹主导更新；模型转去刷易验证的格式分而非任务成功。
- **切太晚**：熵坍缩、多样性丧失，RL 没有探索空间，天花板反而更低；还容易死记轨迹，换套工具就崩。

**工程做法**：SFT 阶段就用 RL 的评测口径（同温度、同环境、同 reward 函数）逐 checkpoint 打点。切换点不是「几条曲线的交点」——四个指标量纲不同，未必有共同交点——而是**多约束 gate**：**取最早同时满足 ①协议合格率与可执行率达到本任务设定的约束、②已存在可优化的成功轨迹、③SFT 边际收益趋平 的 checkpoint**，多个满足时选熵更高的。切换后保留对 SFT 参考模型的 KL 约束，并持续监控格式合格率。

## 延伸 / 追问

**追问：如果 pass@k 也上不去，业务又必须提升效果，怎么办？**

别硬上 RL，按性价比走三步：① **拒绝采样自蒸馏（RFT / STaR）**——用现有模型或更强模型在训练集上大量采样，只保留结果正确且过程合法的轨迹回灌 SFT，把 pass@k 里的成功案例「压」进 pass@1，这是 SFT 与 RL 之间最划算的一档。② **降难度而不是降标准**——拆子任务、简化工具签名、补足 system prompt 与示例，先让 pass@k 起来再谈 RL；很多时候瓶颈在工具接口设计，不在模型。③ **课程化**：按难度分桶，先在有信号的桶上跑 RL，随策略变强逐步放开难桶，并清掉 reward 恒为 0 或恒为 1 的样本——它们对组基线没有任何贡献。三步之后 pass@k 仍然贴地，那就是 base model 容量或数据覆盖的问题，换模型比调 RL 更划算。

## 参考

- Ouyang et al., *Training language models to follow instructions with human feedback (InstructGPT)*, 2022：https://arxiv.org/abs/2203.02155
- DeepSeek-AI, *DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning*, 2025：https://arxiv.org/abs/2501.12948
- Yue et al., *Does Reinforcement Learning Really Incentivize Reasoning Capacity in LLMs Beyond the Base Model?*, 2025：https://arxiv.org/abs/2504.13837
- Zelikman et al., *STaR: Bootstrapping Reasoning With Reasoning*, 2022：https://arxiv.org/abs/2203.14465
- Yuan et al., *Scaling Relationship on Learning Mathematical Reasoning with Large Language Models (RFT)*, 2023：https://arxiv.org/abs/2308.01825
