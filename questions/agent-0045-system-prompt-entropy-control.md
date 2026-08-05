---
id: agent-0045
title: 多人长期维护系统提示词时，如何防止 Prompt 熵增？
category: agent
tags: [prompt-engineering, prompt-governance, system-prompt, testing, maintainability]
difficulty: medium
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 2 章
status: published
updated: 2026-08-06
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-06
    updated: 2026-08-06
---

## 问题

多人长期维护一个系统提示词（system prompt）时，如何防止 Prompt 熵增？也就是随着每个人「出问题就往里加一句」，提示词越滚越长、规则互相打架、没人敢删——该怎么治理？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-06

**先认清熵增机制。** 每次线上 bug 的最省事修法就是「往 prompt 里再加一句禁止/要求」，成本低、见效快，于是提示词单调膨胀：规则堆叠 → 相互矛盾 → 越长越稀释注意力、越没人敢动。本质是**缺少「删除/合并」的反向压力和「改动是否真有效」的度量**。治理不是写得更小心，而是把 prompt 当**代码**来工程化。

```
熵增闭环（要打破的）           治理闭环（要建立的）
出 bug → 加一句 → 变长 →       改动 → 评测回归 → 通过才合入
更矛盾 → 更没人敢删 ↺          ↑                      │
                              └──── owner review + 定期重构 ◄──┘
```

**五条落地手段：**

1. **结构化而非流水账。** 按「角色/目标 → 硬约束 → 工具与流程 → 输出格式 → 示例」分区，规则挂到明确小节，杜绝同一意图散落多处。新增先问「已有哪条覆盖」，能改不新增。

2. **版本化 + 评测回归（关键）。** prompt 进 git、走 PR、可 diff 可回滚；配一套**评测集**（golden cases + badcase 回归），任何改动必须跑评测，用数据证明「修了目标 case 且没劣化其他」，而不是凭感觉加。这是对抗熵增的核心反向压力——**没有量化收益的行就不该进**。

3. **lint 与去重。** 自动检查：超长、重复/冲突规则、含糊措辞、写死的临时补丁；CI 卡门槛。让「随手加一句」有摩擦。

4. **owner + review。** 指定 prompt owner，改动需 review；每条规则最好能追溯到「为什么加、对应哪个 case」，无主的裸规则优先清理。

5. **定期重构 + 反馈闭环。** 排期做 prompt 重构（合并同类、删死规则、把稳定约束下沉到代码护栏而非留在 prompt）；线上问题不止加规则，先看是否该进护栏/工具层。用观测数据驱动「删」，而不只是「加」。

**一句话：把 system prompt 当生产代码——结构化、进版本控制、以评测回归为准入门槛、lint 去重、有 owner review 并定期重构**，用「改动必须证明净收益」的工程闭环，替代「出事就加一句」的熵增本能。

## 延伸 / 追问

**追问：什么样的约束该留在 prompt 里，什么该「下沉」到代码护栏？**

判据是**能否被确定性执行、以及违背的代价**。凡是**可程序化校验的硬约束**——输出必须是合法 JSON、禁止调用某工具、金额上限、必须带某字段——应下沉到代码：用 schema 校验、工具权限白名单、后置校验器强制，而不是指望模型每次都读到并遵守那句话。prompt 只保留**需要模型理解与权衡的软性指导**：语气风格、优先级取舍、模糊情境下的判断倾向。这样既缩短 prompt、又把「安全/合规」这类不容试错的约束放到了必然生效的层。经验法则：**如果一条 prompt 规则「违反了会出事」，它就不该只活在 prompt 里**——prompt 是概率性的建议，代码护栏才是确定性的保证。

## 参考

- Anthropic Engineering, *Effective Context Engineering for AI Agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic Docs, *Prompt engineering overview*：https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview
