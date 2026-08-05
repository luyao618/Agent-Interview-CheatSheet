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

多人长期维护同一份系统提示词时，规则不断堆叠、相互矛盾、无人敢删，导致提示词膨胀、行为漂移——如何在工程上防止这种 "Prompt 熵增"？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-06

**什么是 Prompt 熵增。** 多人共同维护一份系统提示词时，每人为修一个 case 就往里加规则，只增不删；久而久之规则相互矛盾、语义重叠、无人敢动，提示词越来越长、行为越来越难预测——这就是熵增。根治思路只有一句：**把提示词当受治理的代码，而不是可随手涂改的文档。**

**治理闭环：**

```
改动提案 ─► 结构化 diff ─► lint 去重 ─► 评测回归 ─► owner review ─► 合并
   ▲                                                              │
   └────────────── 线上反馈（失败/投诉 → 新评测用例）◄──────────────┘
```

1. **结构化拆分**：把巨型提示词拆成有语义边界的模块（角色 / 约束 / 工具说明 / 输出格式 / 示例），每块单一职责、可独立引用与删除。散文式长段落是熵增温床。

2. **版本管理即代码**：提示词进 Git，走 PR + diff + review，禁止线上直接改；每次改动可追溯「谁、为什么、改了哪条」，可回滚。

3. **Lint 与去重**：CI 加静态检查——长度上限、冲突 / 重复规则检测、格式与禁用措辞。新规则先查是否已有等价条目，避免「第 3 条和第 27 条互相打架」。

4. **评测回归**：维护固定 golden cases，每次改提示词跑回归看指标是否倒退。没有评测，任何「微调」都是盲改；有了评测才敢删规则。

5. **Owner + 定期审查**：每个模块有 owner，定期做「反向 review」——问的不是加什么，而是「哪条能删」；加规则时标注来源 case 与失效条件，过期即清。

6. **可观测反馈闭环**：线上采集失败 / 兜底 / 投诉，定位到具体规则并回灌评测集，形成「线上问题 → 评测用例 → 提示词修订 → 回归验证」的闭环，而非头痛医头。

一句话：**结构化降复杂度、版本 + lint + 评测把住入口、owner 主动做减法、可观测反向驱动**——四层合力，熵增才能被持续对冲。

## 延伸 / 追问

**追问：小团队 / 早期项目，还没条件搭评测和 CI，最低成本能先做哪一两件？**

优先做两件几乎零成本的事。第一，**版本化 + 单一 owner**：把提示词从代码里抠出来放进 Git 单文件，任何改动走 PR、指定一人做最终 review——光是「不能绕过 review 直接改」就能挡住大半随手堆叠。第二，**每条规则写明来源与失效条件**（注释一行「为解决 X case 而加，X 不再出现即可删」），让后来者敢删而非只敢加。评测可以从「手动跑一组固定问答、肉眼比对」起步，攒够典型 case 再自动化。核心不是工具多重，而是先立「只增不删要先问一句」的反向纪律：每次加规则时强制自问「有没有旧规则该一起删」。

## 参考

- Anthropic Docs，*Prompt engineering overview*：https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview
- Anthropic Engineering，*Effective context engineering for AI agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
