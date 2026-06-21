---
id: rag-0014
title: 生成阶段如何在 Prompt 中设定边界条件，防止没检索到内容时模型产生幻觉
category: rag
tags: [rag, hallucination, prompt-engineering, grounding, refusal]
difficulty: medium
role: engineer
contributor: 佚名
source: 字节跳动
status: published
updated: 2026-06-21
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-21
    updated: 2026-06-21
---

## 问题

生成阶段如何在 Prompt 中设定边界条件，防止没检索到内容时模型产生幻觉？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

核心思想：在 Prompt 里把模型从「无所不知的答主」**降权为「只读给定材料的阅读理解器」**——只允许依据检索片段作答，材料不支持就明确说「不知道」，并强制引用来源。幻觉往往不是模型「错」，而是我们没给它**拒答的许可与边界**。

**四条边界约束（写进 system / instruction）**

1. **闭卷约束（grounding）**：只能基于 `<context>` 内的内容回答，禁止使用模型自身先验知识补全。
2. **拒答出口（refusal）**：context 为空或不足以支撑答案时，必须输出固定话术，如「根据现有资料无法回答」，不得编造。
3. **强制引用（citation）**：每个结论后标注来源 chunk id（如 `[doc3]`），无法标注的句子即视为无依据，应删除。
4. **不外推（no extrapolation）**：不猜测、不脑补、不把「相关」当「等同」；材料只答了一部分就只答这一部分。

```
检索结果
   │
   ├─ 命中且充分 ─► 依据 context 作答 + 标注 [来源]
   │
   ├─ 命中但不足 ─► 答可答的部分 + 显式声明「其余资料未覆盖」
   │
   └─ 空 / 不相关 ─► 触发拒答话术，不编造
```

**Prompt 骨架示例**

```
你是只读资料的问答助手。严格遵守：
- 只依据 <context> 作答，禁止使用资料外的知识。
- 每个结论须标注来源，如 [1][2]。
- 若 <context> 为空或不足以回答，只回复：
  "根据现有资料无法回答该问题。"
<context>
{检索到的片段，逐条带编号}
</context>
问题：{query}
```

**为什么有效**：固定拒答话术给了模型一条「安全退出路径」，让「我不知道」成为合法且低成本的选项；强制引用把每句话绑定到可核验的 chunk，无据之言无处藏身；闭卷约束切断了它调用参数化记忆去「填空」的冲动。

**配套（Prompt 之外）**：检索侧用相似度阈值过滤，低于阈值直接判定「无命中」，根本不把弱相关片段塞进 context；生成后做一道引用校验 / NLI 事实核查，剔除无来源支撑的句子。Prompt 约束是第一道闸，检索阈值与后置校验是第二、三道，三者叠加才稳。

一句话：**闭卷 + 给拒答出口 + 强制引用 + 检索阈值兜底**，把「没检索到也硬答」改造成「没依据就承认不知道」。

## 延伸 / 追问

**追问：只靠 Prompt 写「不知道就拒答」，模型仍然会硬答，怎么办？**

光靠 Prompt 是软约束，必有漏网。要分层加固：① **检索侧硬门槛**——设相似度/重排分阈值，top-1 低于阈值直接走「无命中」分支，连 context 都不给，模型自然无可外推；② **后置事实校验**——用 NLI 或「逐句找支撑 chunk」校验，凡无来源支撑的句子直接删除或触发兜底回复；③ **少样本示范**——在 Prompt 里给一个「context 为空 → 输出拒答话术」的范例，比纯指令更有效；④ **评测闭环**——构造「答案不在库内」的负样本集，用拒答率 / 幻觉率量化，反向调阈值与措辞。一句话：Prompt 立规矩，检索阈值与后置校验来强制执行。

## 参考

- OpenAI Help，*Retrieval-Augmented Generation and hallucination 最佳实践*：https://platform.openai.com/docs/guides/retrieval-augmented-generation
- Anthropic Docs，*Reduce hallucinations（grounding / allow "I don't know"）*：https://docs.anthropic.com/en/docs/build-with-claude/reduce-hallucinations
- Gao et al., *Retrieval-Augmented Generation for Large Language Models: A Survey*, 2023：https://arxiv.org/abs/2312.10997
