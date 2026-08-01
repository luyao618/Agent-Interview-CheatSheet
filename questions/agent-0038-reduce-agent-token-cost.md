---
id: agent-0038
title: Agent 节省 Token 成本，有哪些思路和方法
category: agent
tags: [token-optimization, cost, prompt-caching, context-engineering, model-routing]
difficulty: medium
role: engineer
contributor: 佚名
source: 未知
status: published
updated: 2026-08-01
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-01
    updated: 2026-08-01
---

## 问题

Agent 要节省 Token 成本，有哪些思路和方法？请系统地说明。

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-01

核心公式：**Token 成本 = Σ(每次调用的 input + output) × 单价 × 调用次数**。降本就从「单次量、单价、次数」三个乘子同时下手，分五层。

**一、输入侧——只喂必要的上下文**

- 按需加载：Skill / 工具 / 文档走渐进式披露，元数据常驻、正文触发时才载入，别把全部知识塞进窗口。
- 历史压缩：滑动窗口 + 定期摘要，丢弃过期 turn，用结构化记忆代替原文回灌。
- 精准检索：RAG 先 rerank 再 top-k 截断，只注入高相关片段，配合元数据过滤。

**二、缓存侧——稳定前缀与重复请求缓存住**

- Prompt caching：系统提示、工具定义、稳定指令做成固定前缀命中缓存，重复输入按缓存价计费（可省约 90%）。
- 语义缓存：重复 / 近似 query 直接返回历史答案，省掉整次调用。

**三、模型侧——按难度选模型**

- 模型分级 / 路由：简单子任务用小模型（Haiku 级），难任务才上大模型；能蒸馏则蒸馏。

**四、流程侧——减少调用次数与循环**

- 收敛 ReAct 轮次：先规划再执行，可并行的 tool call 并行，设好终止条件避免空转 / 死循环。
- 用代码搬数据：确定性的解析 / 过滤 / 聚合交给工具，模型只读结果，不灌原始大文件。
- 子代理隔离：重检索 / 重读取委派给 subagent，主线程只收结论，防中间产物污染上下文。

**五、输出侧——控制生成量**

- 限制 `max_tokens`、要求结构化 / 精简输出，非必要不长篇 reasoning。

```
成本 = Σ(input + output) ×  单价  ×  次数
          ↑压缩/缓存        ↑选模型   ↑减循环
```

一句话：常驻内容压到最小、稳定前缀走缓存、按难度分模型、用工具和子代理替模型搬数据。

## 延伸 / 追问

**追问：这些手段哪些会牺牲效果（准确率 / 体验）？如何在降本与质量间取舍？**

Prompt caching、并行 tool call、用代码搬数据基本是**无损降本**，优先全量上。有损的主要是三类：

1. **历史压缩 / 摘要**——过度摘要会丢关键约束。做法：保留最近 N 轮原文 + 更早的摘要，关键事实（用户偏好、已确认决定）单独固定不摘。
2. **top-k 截断 / 小模型路由**——截太狠会漏召回，模型太小会降准。用离线评测集卡住质量下限，按任务难度分档路由，边界任务用大模型兜底或升级重试。
3. **限制输出长度**——需要推理的任务别硬砍，可用「先给结论、按需展开」。

工程上先按 ROI 排序：常驻层每个 token 都乘以全部请求，收益最大，优先优化；再用 A/B 对比降本前后的平均 token、延迟和质量指标，只保留质量不明显下降的优化。核心原则：**无损优化默认开启，有损优化必须配评测护栏与回退路径。**

## 参考

- Anthropic Docs，*Prompt caching*：https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- Anthropic Engineering，*Effective context engineering for AI agents*：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic，*Building Effective Agents*（编排、路由等模式）：https://www.anthropic.com/research/building-effective-agents
