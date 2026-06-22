---
id: agent-0012
title: Agent 为什么容易 hallucination
category: agent
tags: [agent, hallucination, tool-use, grounding, error-propagation]
difficulty: medium
role: engineer
contributor: 佚名
source: 淘天/阿里
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

Agent 为什么容易 hallucination？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

核心结论：Agent 的幻觉不只是「模型瞎编」这一种。比起单轮问答，Agent 把 LLM 放进**多步循环 + 工具交互**里，于是单步的小偏差会被链式放大，且每一步都新增了出错面。Agent 特有的成因有四类：

**1. 多步误差累积（error propagation）**
单步正确率 0.95，连做 10 步整体只剩 ≈0.60。前一步的错误观测/错误结论被当成事实喂回下一轮，越走越偏，且模型倾向于**自圆其说**而非自我否定。

```
步骤:   1 ──► 2 ──► 3 ──► ... ──► N
正确率: .95  .90   .86         ↓ 链式衰减
        小错被当前提 → 后续推理在错误地基上继续盖楼
```

**2. 工具结果误用 / 臆造参数**
- **臆造调用**：工具缺失或 schema 不清时，模型凭空编出不存在的函数名、参数或 ID；
- **误读返回**：工具返回空/报错/格式异常，模型不核验就「脑补」一个合理答案；
- **过度自信**：把检索到的片段当全部事实，对没检索到的也敢断言。

**3. 缺乏 grounding 与校验**
没有把每一步的论断**锚定到可验证的外部证据**。模型的「先验记忆」与「当前工具事实」冲突时，常优先相信参数化记忆里的旧知识，而非现场观测。

**4. 长链路上下文漂移**
轨迹变长后，关键约束/中间结果被挤出窗口或被无关历史稀释，目标与事实双双漂移。

**缓解手段（对症下药）：**

| 成因 | 缓解 |
| --- | --- |
| 误差累积 | 限制步数/预算、关键步加 reflection 与自检、失败回滚重试 |
| 工具臆造 | 严格 schema + 参数校验、白名单约束、工具报错显式回灌让模型重试 |
| 缺 grounding | 强制「引用工具返回再作答」、结构化输出留证据字段、必要时二次核验 |
| 上下文漂移 | 压缩/摘要历史、固定保留目标与约束、必要信息写入外部记忆 |

一句话：Agent 幻觉 = 单步幻觉 × 多步放大 + 工具交互新增的出错面。可靠 Agent 不是更聪明，而是**每步都能验证、能停、能在出错时被发现并纠偏**。

## 延伸 / 追问

**追问：工程上怎么判断某一步是「真有依据」还是「模型脑补」？**

让证据可追溯、可机器校验。① **结构化输出**：要求模型作答时附带依据字段（引用了哪个工具返回、哪条检索片段、哪个 ID），没有证据就不能下结论；② **工具结果校验**：对返回值做 schema/类型/空值检查，异常时不静默吞掉，而是把错误显式回灌让模型重做，而非自行脑补；③ **一致性交叉验证**：高风险结论用第二条路径（换工具/换检索/再问一次）比对，不一致就降级或转人工；④ **断言与护栏**：对数值、ID、引用做后置校验（如引用必须真实存在于来源）。本质是把「模型说的」与「可验证的事实」分开，只有被证据支撑的那部分才允许进入下一步。

## 参考

- Ji et al., *Survey of Hallucination in Natural Language Generation*, 2022：https://arxiv.org/abs/2202.03629
- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, 2022：https://arxiv.org/abs/2210.03629
- Shinn et al., *Reflexion: Language Agents with Verbal Reinforcement Learning*, 2023：https://arxiv.org/abs/2303.11366
- Anthropic Engineering，*Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
