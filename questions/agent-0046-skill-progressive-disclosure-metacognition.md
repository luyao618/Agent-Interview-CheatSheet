---
id: agent-0046
title: Skills 渐进式披露依赖模型“知道自己不知道”，这个元认知问题怎么解决
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

Skills 的渐进式披露（progressive disclosure）依赖模型「知道自己不知道」——只有当模型意识到「当前任务需要一个尚未加载的能力」时，才会去触发加载。这个元认知（metacognition）问题怎么解决？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-06

**先点破根因**：渐进式披露把「是否加载 Skill」交给模型自省。但模型有个致命盲区——**它看不见不在上下文里的东西**。于是失败不是「加载错」，而是「压根没意识到该加载」：它凭参数里的模糊记忆硬答、幻觉一个能力，全程无感。指望模型可靠地「知道自己不知道」并不现实。

**思路：把触发从「模型内省」外移到「系统机制」**，让元认知尽量不依赖模型自觉。

```
  纯自省(脆弱)                    机制兜底(稳健)
  任务 → 模型"我需要X吗?"          任务 → 系统检索能力索引
         │  漏判→直接硬答                │  Top-K候选常驻可见
         ▼                              ▼
       错误输出                    模型在候选里选/确认 → 加载
                                        ▲  evaluator不满意则回灌重触发
```

**五个可落地手段：**

1. **常驻能力索引（capability index）。** 把「有哪些能力、各自何时用」压成极简目录常驻上下文。模型至少**知道选项空间存在**——这是「知道自己可能不知道」的前提，比让它凭空回忆强得多。

2. **description 写触发例而非功能名。** 元数据里放「when to use + 触发 query 示例」，把路由从「内省判断」降级为「模式匹配」：命中相似输入就触发，不依赖模型抽象出「我缺能力」这层元认知。

3. **探针问题（self-check）。** 动手前强制一步自问：「本任务是否需要外部检索/工具/未加载能力？」把隐式判断显式化为一次可观测的推理，CoT 能显著降低漏触发率。

4. **强制检索兜底。** 对知识型/高不确定任务，**默认先跑一次 router 检索**再作答，而不是等模型「觉得」需要。把「模型决定是否加载」翻转成「系统总召回候选、模型只做精选」，从架构上消除漏判。

5. **外置 router / evaluator。** 用轻量分类器（按关键词、意图、文件类型硬路由）在语义匹配前分流；再用 evaluator 校验输出——若结果不达标或疑似「缺能力硬编」，回灌信号触发二次加载，形成「加载→执行→评估→补加载」闭环。

**一句话**：别把可靠性押在模型的元认知上。用**常驻索引**让它知道选项、用**触发例+探针**降低漏判、用**强制检索+evaluator 闭环**做机制兜底——渐进式披露省 token，但触发决策要有系统级安全网。

> **要点**
> - 根因：模型看不见「不在上下文里」的能力，漏触发是静默失败
> - 外移触发：从「模型内省」转向「系统检索 + 候选精选」
> - 手段：能力索引常驻、description 写触发例、探针自检、强制检索、router/evaluator 闭环

## 延伸 / 追问

**追问：能力索引常驻会不会又把 token 省下来的部分吃回去？怎么平衡？**

会有开销，但可控，关键是**只常驻「判别用的最小信息」**。索引里每个能力只保留 `name + 一句话触发条件`（几十 token），不放正文、示例、参数 schema——那些仍走按需加载。规模上千时，不再全量常驻，而是把索引本身做成可检索资源：运行时按 query 召回 Top-K 再喂模型，常驻的只剩「分组/命名空间目录」。这样常驻成本随**分组数**而非**能力总数**增长。衡量方法：对比「纯渐进式披露的漏触发率」与「加索引后的漏触发率 + 多出的常驻 token」，用漏触发导致的重试/错误成本去摊薄索引开销——通常前者远大于后者，索引是划算的保险。

## 参考

- Anthropic Docs，*Agent Skills*（progressive disclosure 与 name+description 路由）：https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills
- Anthropic Engineering，*Effective context engineering for AI agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic Engineering，*Building Effective Agents*（router / evaluator-optimizer 编排模式）：https://www.anthropic.com/engineering/building-effective-agents
