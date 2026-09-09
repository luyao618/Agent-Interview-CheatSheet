---
id: product-0003
title: AI 产品如何设计质量、成本和业务指标？
category: product
tags: [ai-product, metrics, evaluation, cost]
difficulty: medium
role: both
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

如何为 AI 产品建立同时覆盖质量、成本和业务结果的指标体系？

## 答案 · Claude-Opus-4.8

指标分三层：模型/任务质量（正确性、完整性、引用准确率、工具选择成功率）、系统体验（延迟、可用性、失败率、人工接管率、每任务 token 与费用）和业务结果（完成率、转化、留存、节省时长或收入）。指标必须绑定具体任务和用户群，避免把点赞率当成唯一质量信号。

先建立带 ground truth 的离线评测集，再用线上分层实验验证业务指标。每次换模型、prompt 或检索策略，都同时检查质量、成本和风险门槛，防止单项优化造成整体退化。

## 延伸 / 追问

- LLM-as-a-Judge 的分数如何用人工样本校准？
- 业务指标提升但错误率上升时如何决策？
