---
id: agent-0028
title: 两个 Skill 内容不同但 description 相似导致 Agent 加载错 Skill，怎么解决
category: agent
tags: [skill, tool-selection, routing, disambiguation, retrieval]
difficulty: medium
role: engineer
contributor: 佚名
source: 腾讯
status: published
updated: 2026-06-29
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-29
    updated: 2026-06-29
---

## 问题

如果两个 Skill 实际内容不一样，但是 description 很相似，导致 Agent 每次加载错 Skill，怎么解决？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-06-29

**本质**：Skill 的选择是一次「语义检索 / 分类」——模型只看常驻的 `name + description` 来路由。两个 description 在向量空间里几乎重叠，决策边界就被抹平，模型只能靠噪声乱选。修复的方向是**拉大可区分度**，而非加长描述。

```
相似 description：决策边界模糊        改写后：边界清晰
   skill A ──┐                       skill A ───────●
            ╳  ← 选错               (PDF→文本)
   skill B ──┘                       skill B ───────────●
                                     (扫描件 OCR)
```

**1. 重写 description，正交化（首选、成本最低）**
- 写**触发条件**而非功能名词：开头点明「**when to use / 何时用**」与「**何时不要用**」。
- 显式划界："Use for native/text PDFs; **NOT** for scanned images — use `ocr-extract` instead"，互相点名排斥。
- 去掉两者共有的高频词（如都写"处理文档"），保留各自独有的输入类型、前置条件、输出。一句话能区分就别堆三句。

**2. 收敛触发面**
- 合并：若两者本就高度重叠，合成一个 Skill，内部再按参数/分支走不同逻辑，从根上消除歧义。
- 拆层：把宽泛的"文档处理"做成一个 router/dispatcher 入口，子能力放到第二层按需加载（progressive disclosure），减少同层竞争项。

**3. 改进选择机制**
- Skill 多时，用**检索式**而非全量塞入：对 query 做 embedding 召回 Top-K，再让模型在少量候选里精选，降低混淆。
- 让模型**先输出选择理由**（"选 X 因为输入是扫描件"）再调用，思维链能显著降低误选率。
- 必要时加一道**轻量分类器/规则前置**（按文件后缀、MIME、关键词硬路由），不把全部判断压给语义匹配。

**4. 用评测兜底**
- 建一个「query → 期望 Skill」的小测试集，把易混对（confusion pair）作为回归用例；每次改 description 后量化误选率，**用数据驱动改写**而不是凭感觉。线上则对 Skill 命中做日志埋点，定期捞误选样本回灌测试集。

**优先级**：先 1（改写正交化）→ 不够再 3（检索+理由）→ 结构性重叠才上 2（合并/拆层），4 全程兜底。

> **要点**
> - 根因是 description 语义重叠 → 路由决策边界模糊
> - 首选改写：写"何时用/何时不用"并互相点名排斥
> - 机制层：检索 Top-K + 输出选择理由 + 规则硬路由
> - 用 confusion-pair 测试集量化误选率，闭环迭代

## 延伸 / 追问

**追问：Skill 数量到几百上千时，靠改 description 还够吗？**

不够，要从「全量比较」转向「检索 + 分层」。把每个 Skill 的 `name/description/示例 query` 建索引，运行时按用户 query 召回 Top-K（如 5~10）候选，只把这少量候选喂给模型精选——既省 token 又把混淆项从"全库"缩到"邻居"。再叠加命名空间/标签分组、必要时两级路由（先选域、再选具体 Skill）。description 改写解决的是**局部可分性**，检索分层解决的是**规模可扩展性**，两者正交、应同时用。

## 参考

- Anthropic, *Agent Skills* / *Claude Docs — Skills*（progressive disclosure、name+description 路由）
- Anthropic, *Writing effective tools for agents*（清晰描述与触发边界的写法）
- Model Context Protocol — Tools 规范（工具/能力的描述与选择）
