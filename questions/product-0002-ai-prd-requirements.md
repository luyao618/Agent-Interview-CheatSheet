---
id: product-0002
title: AI 产品的 PRD 需求应该如何拆解？
category: product
tags: [ai-product, prd, requirements, workflow]
difficulty: medium
role: pm
contributor: 佚名
status: published
updated: 2026-09-09
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-09-09
    updated: 2026-09-09
---

## 问题

AI 产品的 PRD 与确定性软件产品有什么不同？应该如何拆解需求？

## 答案 · Claude-Opus-4.8

先写清用户任务和成功定义，再拆成输入、模型能力、工具或知识依赖、输出、失败处理和人工接管。PRD 不应只描述“模型要回答得好”，而应明确允许的行为边界、拒答条件、证据要求、延迟与成本预算，以及不可接受的错误。

需求拆解应包含正常路径、边界样本和对抗样本，并为每一层指定可观测信号。先用固定评测集验证能力，再用小流量 pilot 验证真实使用价值，避免把模型波动隐藏在模糊的功能验收里。

## 延伸 / 追问

- 哪些需求应由规则或 workflow 实现，而不是交给 LLM？
- 如何把“回答质量”写成可测试的验收条件？
