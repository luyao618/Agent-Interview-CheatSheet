---
id: rag-0031
title: GraphRAG 系统整体流程是怎样的？从用户提问到最终生成答案，哪些模块是你独立负责的？
category: rag
tags: [rag, graphrag, knowledge-graph, community-detection, retrieval]
difficulty: hard
role: engineer
contributor: 佚名
source: 百度
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

GraphRAG 系统整体流程是怎样的？从用户提问到最终生成答案，哪些模块是你独立负责的？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

GraphRAG 把「扁平向量检索」换成「图谱 + 社区摘要」，同样分**离线建图**与**在线问答**两条链路：

```
离线建图(Indexing)：
  文档 → 切分 → LLM 抽取(实体/关系) → 去重对齐 → 知识图谱
       → 社区检测(Leiden) → 各社区 LLM 摘要 → 图/向量/摘要索引

在线问答(Query)：
  问题 →┬ Local：定位实体→邻域子图+相关chunk→生成
        └ Global：遍历社区摘要→map 各自作答→reduce 汇总
```

**离线：构图与摘要**

1. **切分**：文档切成 chunk（与传统 RAG 相同）。
2. **图谱抽取**：对每个 chunk 用 LLM 抽取实体、关系、属性（带描述），这是与传统 RAG 最大的差异——不再只存向量，而是结构化三元组。
3. **对齐去重**：跨 chunk 合并同名实体、消歧、聚合描述，构成全局知识图谱。
4. **社区检测**：用 Leiden 等算法把图按连通密度切成层次化社区（话题簇）。
5. **社区摘要**：对每个社区 LLM 生成一段摘要，描述该主题的核心实体与脉络。
6. **建索引**：实体/关系/摘要分别做 embedding 入库，备 local 与 global 检索。

**在线：两种检索模式**

- **Local Search（局部）**：问具体实体时，先匹配相关实体，再沿图扩展邻接实体、关系与原文 chunk，组装上下文生成——擅长「某某是什么/与谁有关」。
- **Global Search（全局）**：问宏观主题时（如「全文核心矛盾」），走 **map-reduce**：各社区摘要并行作答（map），再汇总成最终答案（reduce）——擅长传统 RAG 难做的全局归纳。

**与传统 RAG 的模块差异**：多了「实体关系抽取→建图→社区检测→社区摘要」四个离线模块，检索从「向量 topK」升级为「图遍历 + 社区 map-reduce」。

**我独立负责的模块**：离线侧的抽取 prompt 设计、实体对齐去重、社区摘要流水线；在线侧的 local/global 路由与子图/摘要的上下文组装。

一句话：GraphRAG = **离线「抽取→建图→社区摘要」+ 在线「图检索 local + 社区 map-reduce global」**，用结构补齐扁平 RAG 的全局推理短板。

## 延伸 / 追问

**追问：什么场景该上 GraphRAG，什么场景传统 RAG 就够？**

看问题类型与成本。**需要跨文档、多跳、全局归纳**的场景（「梳理全书人物关系」「总结整个仓库的架构演进」）才值得 GraphRAG——它的强项是 global 推理；而**事实型、单点查证**类问题（「某 API 的默认超时是多少」）传统向量 RAG 又快又准，没必要建图。代价上 GraphRAG 离线要对每个 chunk 跑 LLM 抽取 + 社区摘要，**建库成本与延迟高出一两个数量级**，图也需随文档增量维护。实务做法是**混合**：默认走传统 RAG，识别到宏观/多跳意图再路由到 global search，兼顾成本与覆盖。

## 参考

- Microsoft Research，*From Local to Global: A Graph RAG Approach to Query-Focused Summarization*, 2024：https://arxiv.org/abs/2404.16130
- Microsoft GraphRAG 官方文档：https://microsoft.github.io/graphrag/
- Traag et al., *From Louvain to Leiden: guaranteeing well-connected communities*, 2019：https://arxiv.org/abs/1810.08473
