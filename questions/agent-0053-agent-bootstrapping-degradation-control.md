---
id: agent-0053
title: Agent 自举生成新 Agent 时，如何防止能力退化和错误累积？
category: agent
tags: [agent-bootstrap, self-improvement, evaluation, governance, safety]
difficulty: hard
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 5、8 章
status: published
updated: 2026-08-10
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-10
    updated: 2026-08-10
---

## 问题

当一个 Agent 能够生成、配置甚至评判新的子 Agent（自举 / bootstrapping）时，多代传承后容易出现能力退化与错误累积。请说明这种代际退化的根因，以及工程上如何通过模板、评测门禁、人工审核、版本回滚和信任根隔离来抑制它。

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-10

**核心风险：把「自我复制」误当「自我改进」。** Agent 造 Agent 是一条**无外部真值的反馈闭环**：G_n 用自己的输出与判断去生成并评判 G_{n+1}，父代的模板缺陷、prompt 偏置、工具误选被子代继承并放大，而评测又由同源模型打分——如同 model collapse，误差单调累积、分布方差收窄（多样性塌缩），最终在一个**漂移的代理目标**上自嗨，而非真实任务。

关键是切断「自证」，给闭环钉一个**外部信任根**。

```
        ┌──── 不可变信任根（人类控制）────┐
        │ 黄金模板 · 固定评测集 · 安全策略 │
        └───────────┬─────────────────────┘
                    │ 约束 / 门禁 / 签发（只读）
   ┌── G_n ──生成──► 候选 G_{n+1} ──┐
   │                                │
   │   ┌── 外部评测门禁 + 人工审核 ──┘
   │   │  过 → 版本化晋升(canary)
   │   │  不过 → 丢弃 / 回滚父代
   └───┴─ 真实任务反馈（带真值）回灌
```

**五道防线：**

1. **信任根隔离**：黄金模板、评测真值、安全护栏放在生成器**改不到**的地方；子代只填槽位，不能重写 harness / 安全层；生成器不得给自己签发。
2. **模板化生成**：从已审定脚手架派生而非自由发挥，收窄搜索空间、限制可变面，把不确定性关进已知边界。
3. **评测门禁**：晋升前必须过**固定、外部、版本化**的基准，并与父代做回归对比（不许倒退）；用**留出集**防止 Goodhart / 过拟合评测。
4. **人工审核**：新能力、高风险动作、跨信任边界的变更须 human-in-the-loop 签核，不能全自动放行。
5. **版本化 + 回滚**：每代不可变、留血缘（provenance）；灰度上线、异常即回滚，绝不原地改写在跑的 Agent。

**防漂移：** 让**真实、带真值的任务反馈**持续进入闭环，别只喂自生成数据；保留多样性、监控关键指标的代际曲线，连续退化即熔断。

一句话：自举可以扩规模，但**真值、评测、安全**这三样必须锚在生成循环之外、由人类把关——**能造 Agent 的 Agent，绝不能同时是给自己发证的那个**。

## 延伸 / 追问

**追问：怎么早期发现「悄悄退化」——指标没崩但能力在退？**

盯趋势而非单点。① **代际基线回归**：每代固定评测集必须 ≥ 父代，用留出集算 regression，任一核心维度下滑即拦。② **分布 / 多样性监控**：跟踪输出多样性、工具调用分布、答案长度熵——model collapse 的先兆是方差收窄、模式趋同，比准确率更早暴露。③ **真值锚定探针**：混入一组人工标注的 canary 任务，其通过率是不可被生成器优化的硬指标。④ **血缘审计**：沿 provenance 回放，定位退化从哪一代、哪个模板 / prompt 变更引入。⑤ **人审抽样**：对晋升样本做定期盲审，防止评测被 Goodhart 蚀空。一句话：把「代际曲线 + 留出真值 + 多样性熵」做成看板，退化是趋势问题，要用趋势指标抓。

## 参考

- Shumailov et al., *The Curse of Recursion: Training on Generated Data Makes Models Forget*, 2023：https://arxiv.org/abs/2305.17493
- Shumailov et al., *AI models collapse when trained on recursively generated data*, Nature 2024：https://www.nature.com/articles/s41586-024-07566-y
- Anthropic Engineering, *Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
