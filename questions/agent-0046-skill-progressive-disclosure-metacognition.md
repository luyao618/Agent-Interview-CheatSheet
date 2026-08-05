---
id: agent-0046
title: Skills 渐进式披露依赖模型"知道自己不知道"，这个元认知问题怎么解决？
category: agent
tags: [skills, progressive-disclosure, routing, metacognition, tool-discovery]
difficulty: hard
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 2、4 章
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

Skills 的渐进式披露（progressive disclosure）——先只给模型看简短的 skill 描述，模型判断相关才加载完整内容——依赖模型"知道自己不知道"、并主动去触发正确的 skill。可模型经常意识不到某个 skill 与当前任务相关、或高估自己已会而不去加载。这个元认知问题怎么解决？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-06

**先定位问题。** 渐进式披露的软肋在**触发环节**：模型要先从一句 skill 描述里认出「这事我需要它」。失败有两类——**该触发没触发**（没意识到相关，或高估自己会做而硬答，产出幻觉）；**触发错/滥触发**（描述含糊、语义撞车，见 agent-0034）。指望模型完美自省不现实，工程解法是**别把触发全押在模型的元认知上，而是从"描述质量 + 外部路由 + 强制检索 + 反馈校准"四路降低漏触发**。

```
任务 ──► [外部 Router 预筛] ──► 候选 skills 注入描述层
             │(检索/分类，不靠模型自省)      │
             ▼                              ▼
      强制检索护栏 ◄──── 模型判断是否加载 ──► 命中→加载完整 skill
      (高风险/未知领域              │
       先查再答)                    ▼
                           evaluator 事后校验：该用没用？→ 回灌
```

**四个手段：**

1. **写好触发面（description engineering）。** skill 描述里显式写**触发条件、典型任务例、关键词**，而不只是功能简介——把「什么时候该用我」讲清，直接降低模型的识别门槛。这是最便宜也最有效的一环。

2. **外部 Router 辅助，不靠模型自省。** 用一层轻量路由（关键词/embedding 检索、分类器，或小模型）根据任务**预筛相关 skills**，主动把候选描述推到模型面前。把「发现相关性」从模型的内省搬到确定性检索，漏触发大降。

3. **强制检索护栏。** 对高风险或明显超出常识的领域，设**先检索/先查 skill 再作答**的硬规则，不允许模型「凭记忆」直接答——用流程约束兜住「高估自己会」的元认知盲区。

4. **探针 + evaluator 闭环。** 事后用 evaluator（或规则）判「这题本该用某 skill 却没用」，把漏触发案例回灌：补触发例、调 router 阈值、加强制规则。用数据持续校准，而非一次性调好。

**一句话：不追求模型完美自知，而是把触发从"自省"降级为"可工程化"**——描述讲清触发条件、外部 router 主动召回、高风险强制检索、evaluator 反馈校准，四层叠加把「不知道自己不知道」的风险压到可接受。

## 延伸 / 追问

**追问：外部 Router 主动召回 skills，会不会把不相关的也塞进来，反而稀释上下文、诱发误用？**

会，所以 router 要在**召回率与精确率间调平衡**，且分层控制。做法：① router 只注入**精简描述**（渐进式披露的第一层），不直接灌完整 skill，误召回的代价只是几行描述、成本低；真正加载重内容仍由模型二次确认。② 给召回打分并**设阈值 + top-k 上限**，宁可少而准，避免一次塞十几个 skill 淹没注意力。③ 对语义易撞车的 skill 做**描述去重与边界澄清**（同 agent-0034），从源头减少误召回。④ 用 evaluator 同时监控两类错误——漏触发调高召回、误用调高精确率，双向回归阈值。本质是把「相关性判断」做成可度量、可调参的检索问题，而不是一次拍死的开关。

## 参考

- Anthropic Engineering, *Equipping agents for the real world with Agent Skills*：https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Anthropic Engineering, *Effective Context Engineering for AI Agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
