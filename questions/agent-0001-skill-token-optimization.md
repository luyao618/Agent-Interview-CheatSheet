---
id: agent-0001
title: 如何设计 Skill 来降低 Token 消耗
category: agent
tags: [skill, token-optimization, context-engineering, progressive-disclosure, cost]
difficulty: medium
role: engineer
contributor: 佚名
source: 腾讯面试题
status: published
updated: 2026-06-18
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-18
    updated: 2026-06-18
---

## 问题

如何设计 Skill（Agent Skill）来降低 Token 消耗？请说明设计思路与关键手段。

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-18

核心思想：让 Skill 遵循「渐进式披露（progressive disclosure）」，把上下文按需分层加载，绝大多数 token 只在真正触发时才进入窗口。

三层加载模型：

```
① 元数据层   name + description（常驻，仅几十 token）
        │   匹配到任务才下沉 ↓
② 指令层     SKILL.md 正文（触发时加载，控制在数百行内）
        │   需要时才下沉 ↓
③ 资源层     引用的脚本/模板/文档（按路径显式读取）
```

设计要点：

1. **元数据精简且高判别度。** `description` 只写「做什么、何时用」，让路由阶段用极少 token 决定是否加载，避免无关 Skill 占窗口。
2. **SKILL.md 保持瘦身。** 正文只放决策流程与关键约定，把长示例、表格、API 细节拆到独立文件，用相对路径引用、按需 Read。
3. **用代码而非上下文搬运数据。** 确定性且体量大的处理（解析、过滤、格式化）交给脚本/工具执行，模型只读结果，不把原始大文件灌进 context。
4. **单一职责拆分。** 一个 Skill 只解决一类问题，触发面窄，避免「大而全」Skill 每次整体载入。
5. **子代理隔离上下文。** 把重读取/重检索的工作委派给 subagent，主线程只接收结论，防止中间产物污染主上下文。
6. **稳定指令走 prompt caching。** Skill 正文与系统约定是稳定前缀，命中缓存后复用，显著降低重复输入计费。

一句话：把「总是加载」的内容压到最小，把「可能用到」的内容做成可寻址、按需拉取的资源，并用工具/子代理替模型承担数据搬运。

## 延伸 / 追问

**追问：如何量化某个 Skill 的 token 开销并定位优化点？**

分三段统计：常驻元数据 token、单次触发加载的 SKILL.md token、按需资源 token。用 token 计数工具对每段离线计算，再结合调用日志看命中率（触发频次 × 单次加载量 = 该 Skill 的摊销成本）。优化优先级：常驻层 > 高频触发的指令层 > 低频资源层——常驻每个 token 都乘以全部请求数，收益最大；对高频 Skill 再做正文瘦身与缓存；低频大资源保持惰性加载即可。最后用 A/B（精简前后）对比平均输入 token 与延迟，验证收益。

## 参考

- Anthropic Docs，*Agent Skills*（progressive disclosure 加载机制）：https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills
- Anthropic Engineering，*Effective context engineering for AI agents*
- Anthropic Docs，*Prompt caching*：https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
