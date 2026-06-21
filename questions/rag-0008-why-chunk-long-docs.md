---
id: rag-0008
title: 向量化之前为什么要对长文档切片？不切片会怎样
category: rag
tags: [rag, chunking, embedding, context-window, retrieval]
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

在向量化之前，为什么要对长文档进行切片（chunking）？如果不切片会有什么后果？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-21

核心结论：切片是为了让「向量能表达、检索能命中、上下文塞得下」。一篇长文档若整体向量化，会同时撞上**编码上限**、**语义稀释**、**检索粒度**三堵墙。

**为什么要切片**

1. **绕开 embedding 长度上限**：嵌入模型有最大输入 token 数（常见 512、8K），超出会被截断，文末内容直接丢失，向量并不代表全文。

2. **避免语义稀释（dilution）**：embedding 把整段压成一个定长向量。一篇文档若混了多个主题，平均化后向量谁都不像，与具体 query 的相似度被拉平——「什么都沾一点，什么都不突出」。切成主题集中的小块，每个向量语义纯粹，匹配才准。

3. **匹配检索粒度与精度**：用户问题通常只对应文档某一小段。小块检索能精确定位到相关片段；整文召回则把大量无关内容一起带回。

4. **适配下游上下文窗口**：召回内容要拼进 prompt 喂给 LLM。块太大几条就撑爆 context window，还抬高 token 成本、引入「大海捞针」式注意力丢失。

**不切片的后果**

```
整篇文档 ──► 一个向量
  ├─ 超 embedding 上限 → 截断，尾部内容丢失
  ├─ 多主题平均 → 语义稀释，相似度被拉平
  ├─ 命中即整文 → 召回噪声大、定位差
  └─ 塞进 prompt → 超窗 / token 暴涨 / 注意力分散
```

- **召回噪声大**：相关的一句话被淹没在整篇里，精确片段反而排不上去。
- **定位差**：返回一整篇而非关键段落，LLM 还得自己再找一遍，易抓错重点。
- **超窗 / 高成本**：长块拼进上下文容易超长、被迫丢弃，token 费用和延迟同步上升。

一句话：切片让每个向量「主题单一、长度可控、粒度匹配」，是 embedding 能编码、检索能精确、生成塞得下的前提；不切片则三者皆失，召回又脏又粗还塞不进。

## 延伸 / 追问

**追问：那是不是切得越小越好？**

不是，块大小是个权衡。切太小：一句话被拆碎，单块语义不完整、缺上下文，模型拿到片段也答不全，且块数暴涨抬高索引与检索成本。切太大：又退回语义稀释和超窗问题。实践上按「embedding 上限、下游 LLM 上下文预算、语料主题密度」三者倒推，通用文档常取 256–512 token 起步，并叠加 10–20% overlap 缓冲边界切断。更进一步可用父子 / small-to-big 结构：小块负责精确召回，命中后回溯父块补全上下文，兼顾精度与完整性，避免在「太碎」和「太糊」之间二选一。

## 参考

- Pinecone Learn，*Chunking Strategies for LLM Applications*：https://www.pinecone.io/learn/chunking-strategies/
- LangChain Docs，*Text Splitters*：https://python.langchain.com/docs/concepts/text_splitters/
- Liu et al., *Lost in the Middle: How Language Models Use Long Contexts*, 2023：https://arxiv.org/abs/2307.03172
