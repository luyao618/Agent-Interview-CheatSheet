---
id: rag-0025
title: RAG 中 Chunk size 如何选择
category: rag
tags: [rag, chunk-size, embedding, retrieval, tuning]
difficulty: medium
role: engineer
contributor: 佚名
source: 淘天/阿里
status: published
updated: 2026-06-22
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-22
    updated: 2026-06-22
---

## 问题

RAG 里 chunk size 如何选择？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

没有万能值，chunk size 是一个**带约束的调参问题**：先用三条硬/软约束圈定可行区间，再用检索评测在区间内搜出指标拐点。

**一、三条选择依据（倒推可行区间）**

```
   embedding 上限 ─┐
                   ├─►  可行 chunk size 区间  ─►  评测调参取拐点
   下游 token 预算 ─┤
                   │
   语料语义密度 ───┘
```

1. **嵌入模型上限（硬上界）**：embedding 模型有最大输入长度（如 512 token），超出会被静默截断，尾部信息丢失且向量被稀释。chunk 必须留在该上限内，并预留 overlap 余量。

2. **下游 LLM 的 token 预算（软上界）**：检索要 top-k 个 chunk 拼进 prompt，单 chunk 越大，k 路召回越快吃满上下文窗口、越贵、越易把关键信息淹没在长上下文中。用「窗口预算 ÷ 期望 k」反推单块上限。

3. **语料的语义密度（决定下界）**：一个 chunk 最好承载「一个完整语义单元」。FAQ/短问答信息密度高、答案自包含 → 小块（128–256）即可精确召回；论文/法律/手册逻辑跨度长 → 大块（512–1024）保上下文，并配父子结构（小块召回、回溯父块补全）。块太小会切碎语义、丢上下文；太大则稀释相关性、抬高成本。

**二、经验起点（再按评测校准）**

| 语料类型 | 起点 size | overlap |
| --- | --- | --- |
| FAQ / 短问答 | 128–256 | 10% |
| 通用文档 | 256–512 | 10–20% |
| 长逻辑文本（论文/法律） | 512–1024 + 父子 | 15–20% |

**三、评测调参方法（关键，不靠拍脑袋）**

1. 固定一套检索评测集：问题 → 应命中的 ground-truth 片段；
2. 对 `(size, overlap)` 做**网格搜索**，每组重建索引；
3. 用 **recall@k、nDCG@k、命中率**（必要时加端到端答案正确率）打分；
4. 取**指标拐点**而非最大块——继续增大 size 收益趋平甚至下滑时即停；
5. chunk 不是唯一变量：embedding 模型、是否加 reranker、metadata 过滤会和 size 交互，应一起评测，固定其余项再调 size。

一句话：**用 embedding 上限和下游预算卡住上界、用语料密度卡住下界，再用检索评测集在区间内搜指标拐点**，而不是套一个固定数字。

## 延伸 / 追问

**追问：上线后发现召回不准，怀疑是 chunk size，怎么快速定位？**

先分清是「切得不好」还是「size 不对」：抽一批 bad case，看命中 chunk 的内容——若答案被从中间切断、或一个 chunk 混了多主题，是**切分策略**问题（该上语义/结构切或加 overlap），未必要动 size；若 chunk 主题干净但仍漏召回，再考虑 size。定位方法：固定评测集，只调 size 跑 A/B，看 recall@k 是否随 size 变化显著——recall 对 size 敏感才说明 size 是瓶颈。还要排除混淆项：embedding 模型是否截断了长块、top-k 是否过小、是否缺 reranker。常见结论是「块偏大稀释了相关性」或「块偏小丢了上下文」，按方向小步调整并用评测验证，不要一次大改。

## 参考

- Pinecone Learn，*Chunking Strategies for LLM Applications*：https://www.pinecone.io/learn/chunking-strategies/
- LangChain Docs，*Text Splitters*（chunk_size / chunk_overlap）：https://python.langchain.com/docs/concepts/text_splitters/
- LlamaIndex Docs，*Evaluating the Ideal Chunk Size*：https://docs.llamaindex.ai/en/stable/optimizing/basic_strategies/basic_strategies/
