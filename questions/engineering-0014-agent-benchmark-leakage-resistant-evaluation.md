---
id: engineering-0014
title: Benchmark 数据公开后会被训练污染，如何设计抗泄漏的 Agent 评估？
category: engineering
tags: [evaluation, benchmark, data-leakage, dynamic-tasks, testset]
difficulty: hard
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 6、7 章
status: published
updated: 2026-08-12
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-12
    updated: 2026-08-12
---

## 问题

公开 benchmark 一旦发布，题目和答案很快会被抓进训练语料，导致模型「见过考卷」、分数虚高。如何设计一套抗泄漏（leakage-resistant）的 Agent 评估体系？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-12

核心认知：**公开静态题库是一次性消耗品**。抗泄漏不是把题藏得更好，而是**让「记住答案」这条捷径失效**——把评估从「对答案」变成「在新实例上完成任务」。

**先分清三种污染**

- **直接污染**：题干 + 参考答案原文进了预训练语料。
- **间接污染**：题目没进，但题解博客、GitHub 提交、论文附录进了。
- **过拟合泄漏**：数据没泄，但反复在同一测试集上调参刷榜，测试集事实上变成了训练集。

**四层抗泄漏设计**

1. **程序化生成（首选）**：不写死题目，写**任务模板 + 参数采样器**，同一模板生成近乎无限实例（换实体、数值、约束、干扰项），配**程序化 verifier**（跑单测、查终态）判分，不依赖可被泄漏的参考答案。
2. **私有 holdout + 评测即服务**：公开小 dev set 供迭代，test set 不公开；只收模型不收答案，限提交频次并记录历史，抑制刷榜。
3. **时间滚动（live benchmark）**：只用**晚于训练截止日**产生的任务（新 issue、新事件、新版 API），定期换血，**降低**污染风险。但不是免疫：post-training、推理期 retrieval、「公开到评测」的延迟都可能重新引入污染，需叠加私有评测与结构性 held-out。
4. **交互式环境**：Agent 能力体现在**轨迹**上（多步决策、工具调用、错误恢复）。放进有状态沙箱，随机化种子、工具 schema 与初始状态。但浅层重命名可能只增加无关难度，随机化须落在**任务结构**上才算真 held-out。

```
静态题库                抗泄漏评估
固定题干 ──抓取──► 记忆   模板+随机种子 ──► 实例 N（每次不同）
参考答案      ↑ 分数虚高   程序化 verifier ──► 执行/终态判分
                          私有 holdout   ──► 只收模型不收答案
                          时间滚动       ──► 晚于 cutoff
```

**污染审计**

以下都是**诊断 proxy**，只提高或降低置信度，单独一条都不能归因：

- **金丝雀串（canary GUID）**：埋唯一字符串，看模型能否补全。**仅当** canary 从未在别处公开、探针无 retrieval / 上下文注入、植入链路受控时，补全才算训练暴露的强证据；否则可能只是检索。
- **扰动 Δ**：语义等价改写后重测，`原题分 − 扰动分` 为正是**记忆信号**，但也可能来自变体难度不等与 distribution shift——须配 matched control（在**已知未泄漏**的同源题上跑同一套扰动，比两组 Δ）。
- **时间切分对照**：按 cutoff 前后切分，「前」显著更高是**信号**，但受时间漂移、两侧难度不齐、cutoff 本身不确定（口径模糊、post-training 更晚）影响，须难度配平后再比。
- **记忆探针**：看模型能否逐字续写原文与格式噪声（编号、错别字）。
- **发布纪律**：加密打包、禁爬标记、License 声明、报告附污染自查。

**报分方式也要改**：单一 Accuracy 会掩盖污染，应同时报 `public vs private`、`原题 vs 扰动`、`cutoff 前 vs 后` 三组差值，每条都**重复采样并报置信区间**——差值是**诊断 proxy**，多路同向也只是提高置信度，不是证明。

一句话：**用「生成 + 验证 + 私有 + 滚动 + 交互」让答案不可记忆，再用带 control 的审计持续监测——拿到的是信号，不是判决。**

## 延伸 / 追问

**追问：拿不到模型训练数据时，怎么判断某个 benchmark 已经被污染？**

只能做**黑盒推断**——结论是「污染的可能性有多高」，不是「是否污染」。三类证据交叉验证：① **记忆探针**：给题干前半段看模型能否逐字续写后半段、选项顺序甚至数据集特有的格式噪声（原始编号、错别字）；逐字复现是较强信号，但需先排除推理期 retrieval。② **扰动对照**：构造语义等价变体，原题准确率高于变体提示记忆红利——必须同时在**已知未泄漏**的同源题上跑同一套扰动作 matched control，否则分不清是记忆还是变体更难。③ **时间断点**：按创建时间切分画准确率曲线，cutoff 处的台阶是信号，但要先做难度配平，并考虑 cutoff 口径模糊与 post-training 更晚的可能。④ **困惑度侧写**：若可拿 logprob，比该数据集与同分布新样本的 perplexity，异常偏低提示见过。每条都要多次采样并报置信区间；单一证据都可能被「题目本来就简单」或分布差异解释，**只有多路证据同向且各自配了 control，才够支撑一个带不确定性的判断**。

## 参考

- Sainz et al., *NLP Evaluation in trouble: On the Need to Measure LLM Data Contamination for each Benchmark*, 2023：https://arxiv.org/abs/2310.18018
- Zhu et al., *DyVal: Dynamic Evaluation of Large Language Models for Reasoning Tasks*, 2023：https://arxiv.org/abs/2309.17167
- White et al., *LiveBench: A Challenging, Contamination-Limited LLM Benchmark*, 2024：https://arxiv.org/abs/2406.19314
- Jain et al., *LiveCodeBench: Holistic and Contamination Free Evaluation of Large Language Models for Code*, 2024：https://arxiv.org/abs/2403.07974
- Yao et al., *τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains*, 2024：https://arxiv.org/abs/2406.12045
