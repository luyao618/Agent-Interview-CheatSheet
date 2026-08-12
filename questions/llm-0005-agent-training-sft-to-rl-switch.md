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

Agent 后训练常走「先 SFT 再 RL」的路线。SFT 练到什么程度算够、该切 RL 了？有哪些可量化的指标？切早了、切晚了各会出什么问题？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-12

**分工先说清：SFT 教「形」，RL 教「神」。** SFT 是行为克隆——让模型学会 agent loop 的**格式与协议**（何时 thought、怎么发 tool_call、参数 schema 合不合法、拿到返回怎么接、什么时候停）。RL 优化的是**结果**——在能跑通的前提下把成功率往上顶。**RL 只能放大已有行为，不能凭空造出没见过的能力**：它从策略采样中选优，若某类正确行为采样概率≈0，就永远得不到正反馈。所以切换的判据不是「SFT loss 降够了」，而是**「模型已经能稳定产出可被评判的轨迹，且轨迹里有足够的成功样本可供强化」**。

```
SFT 阶段目标：格式/协议达标 ──► 切换判据 ──► RL 阶段目标：成功率
  ├ 格式合法率 ≥99%              ├ 无效轨迹占比够低（否则梯度全喂废样本）
  ├ 工具协议遵守（名/参数/停止）   ├ pass@k 显著高于 pass@1（有头部空间可挖）
  └ 验证集 loss 已平台期          └ 采样多样性未坍缩（entropy 未塌）
```

**该切的四类量化信号：**

1. **格式与协议达标（硬门槛）。** tool_call 可解析率、工具名有效率、参数 schema 校验通过率、能正常触发终止（不空转 / 不超步数）——这几项应 **≥99%**。达不到就继续 SFT：RL 阶段这类错误只会变成大量零奖励轨迹，白烧算力。

2. **pass@k 与 pass@1 的差距（最关键的正向信号）。** 若 **pass@1 低但 pass@k（k=8/16）显著高**，说明模型「偶尔能做对」——正确行为已在分布内，只是概率不够。**这正是 RL 最擅长的场景**：把已有的成功模式提概率。反之 pass@k 也贴地，说明能力缺口是根本性的，应继续补 SFT 数据或换基座，RL 救不了。

3. **SFT 收益已饱和。** 验证集 loss / 任务成功率进入平台期，加数据边际收益趋近于零；此时继续 SFT 只会加剧对演示数据的过拟合。

4. **采样多样性仍在。** RL 需要探索空间。若 SFT 过久导致输出高度确定（entropy 坍缩、k 条采样几乎同一条），RL 会**无从探索**——这是**切晚了**的典型症状。

**切早 vs 切晚的代价：**

| | 切早（SFT 不足） | 切晚（SFT 过度） |
| --- | --- | --- |
| 症状 | 轨迹大量格式错误、奖励几乎全 0 | 输出同质化、entropy 低、pass@k≈pass@1 |
| 后果 | 梯度信号稀疏且噪声大，训不动 | 探索不足，RL 提升有限，易过拟合演示分布 |
| 处理 | 回补 SFT 数据（尤其失败模式） | 提温度 / 加 entropy bonus / 减 SFT epoch 重来 |

**工程做法：** 不必非黑即白地一刀切——可以**用一个小规模 RL 探针试跑**（几百步），看奖励曲线是否抬头、无效轨迹比例是否可控，以此判断时机是否成熟，比拍脑袋定 epoch 数可靠得多。切换后仍要**保留少量 SFT 数据混训或加 KL 约束**，防止 RL 阶段把格式能力训崩（灾难性遗忘）。

**一句话：** **SFT 练到「格式几乎不出错、且 pass@k 明显高于 pass@1、同时输出没塌成一个模子」就该切 RL——前者保证轨迹可被评判，后者保证有东西可强化。**

## 延伸 / 追问

**追问：如果 pass@k 也很低（模型基本做不对），是不是就不该上 RL 了？**

基本是——此时**先补能力，而非补优化**。诊断顺序：① **看失败归因**：是格式错、工具用错、还是推理错？前两类补 SFT 数据最快；纯推理不足则要考虑换更强基座。② **降难度找信号**：把任务拆成子任务或用更简单的样本，若在易档上 pass@k 起来了，说明能力存在、只是任务太难，可用**课程学习**由易到难逐步放开 RL。③ **注入正样本**：用更强的模型（或人工）造成功轨迹做**拒绝采样微调（RFT / STaR）**，把正确行为先塞进分布，再上 RL 放大——这是最常见的破局手段。④ **改造奖励**：全零奖励下 RL 无梯度，可加可验证的中间信号（子目标达成、检索命中证据）把奖励变稠密。核心原则：**RL 是放大器不是发生器**——分布里没有的东西，先想办法把它放进去。

## 参考

- Ouyang et al., *Training language models to follow instructions with human feedback (InstructGPT)*, 2022：https://arxiv.org/abs/2203.02155
- Zelikman et al., *STaR: Bootstrapping Reasoning With Reasoning*, 2022：https://arxiv.org/abs/2203.14465
- Yuan et al., *Scaling Relationship on Learning Mathematical Reasoning with Large Language Models (RFT)*, 2023：https://arxiv.org/abs/2308.01825
- DeepSeek-AI, *DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning*, 2025：https://arxiv.org/abs/2501.12948
