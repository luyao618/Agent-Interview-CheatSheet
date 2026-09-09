---
id: product-0004
title: AI 产品如何设计不确定性与失败体验？
category: product
tags: [ai-product, ux, uncertainty, failure-recovery]
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

面对 AI 输出不确定、延迟较长或执行失败，产品体验应该如何设计？

## 答案 · Claude-Opus-4.8

把不确定性变成可理解、可恢复的状态：展示处理中和阶段性进展，区分模型推测、检索证据与已执行动作；在无法确认时明确说明限制，提供重试、修改输入、查看依据、撤销或转人工的路径。涉及外部副作用的操作必须在执行前确认，执行后提供结果与失败原因。

验收时覆盖正确、部分成功、超时、拒答、工具失败和用户中断六类路径，指标包括恢复成功率、重复提交率、误操作率和用户对结果可信度的反馈。

## 延伸 / 追问

- 什么信息应该展示给用户，什么信息只用于 tracing？
- 如何避免“看起来很聪明”但无法验证的 UI？
