---
id: rag-0039
title: 多模态图表转文字后丢失空间关系，RAG 应如何保留视觉结构
category: rag
tags: [multimodal-rag, vision, document-ai, layout, retrieval]
difficulty: medium
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 3、9 章
status: published
updated: 2026-08-06
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-06
    updated: 2026-08-06
---

## 问题

图表、表格、界面截图这类内容转成文字后，行列、对齐、层级等空间关系往往丢失，RAG 应如何保留这些视觉结构？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-06

核心结论：问题根源是「图 → 纯文本」这一步做了**有损压缩**——把二维的位置、对齐、层级拍平成一维字符串。要点是**别只存文字，把「结构」当作一等公民与文字一起入库**，分四层递进：

**1. 版面元数据（layout metadata）**
版面分析（PDF layout、LayoutLMv3 等）不仅取文字，还保留每个元素的 bbox 坐标、阅读顺序、字号与层级（标题 → 段 → 表 → 单元格）。把这些作为 chunk 的 metadata 存下，命中后可据坐标还原「谁在谁上面 / 左边」。

**2. 结构化抽取（而非线性化）**
表格转成保留行列的 HTML / Markdown / JSON，而不是空格拼接的文本；图表抽成 {坐标轴, 系列, 数值} 的结构数据 + 一句自然语言摘要。结构本身即可检索，能回答「第 3 行第 2 列」这类问题。

**3. 图索引（graph index）**
把元素建成图：节点 = 单元格 / 图例 / 坐标轴 / 标题，边 = 空间关系（相邻、包含、对齐）与从属关系。GraphRAG 式检索能沿边回答「这条曲线对应哪个图例」。

```
页面图像
  ├─ layout:  bbox + 阅读序 + 层级  → 存 metadata
  ├─ 结构化:  表→行列 JSON, 图→序列数据 + 摘要
  ├─ 图索引:  节点(元素) ── 边(空间/层级)
  └─ 多模态:  页面图像直接编码 (ColPali)
```

**4. 多模态 embedding 兜底**
用图文双塔 / ColPali 直接对页面图像分块编码，跳过 OCR 这一有损环节，让「视觉版式」本身参与召回。

**生成阶段**：召回后别只喂纯文本，把 layout-aware 文本 + 对应原图 patch 一起交给 VLM，模型才能读出空间关系。一句话——结构信息要在**入库、索引、检索、生成**四环全程携带，任一环拍平成纯文本都会丢。

## 延伸 / 追问

**追问：如果只能用现成的通用 embedding + 向量库，没有版面分析和 VLM，最低成本怎么减损？**

退而求其次三招：① 线性化时显式注入锚点——表格转 Markdown 保留 `|` 分隔与表头行，图表转「轴 / 系列 / 值」的键值文本，让行列关系以符号形式活在文本里，而非空格拼接；② chunk 不跨结构边界切——一张表、一个图例块作为不可分 chunk，并在文本前缀补一行标题 / 来源做上下文；③ 把可得的坐标 / 页码 / 序号写进 metadata 做过滤与重排。这样即便召回的是纯文本，行列与层级线索仍在，能覆盖大多数「第几行第几列」「对应哪个图例」的问题。真正的图像语义（配色、趋势形状）仍会丢，只能靠多模态模型补。

## 参考

- Microsoft，*Table Transformer (TATR)*，表格结构识别：https://github.com/microsoft/table-transformer
- Huang et al., *LayoutLMv3: Pre-training for Document AI*, 2022：https://arxiv.org/abs/2204.08387
- Faysse et al., *ColPali: Efficient Document Retrieval with Vision Language Models*, 2024：https://arxiv.org/abs/2407.01449
- Microsoft Research，*GraphRAG*：https://microsoft.github.io/graphrag/
