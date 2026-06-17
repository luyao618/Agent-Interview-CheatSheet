# AI-Interview-CheatSheet

> 面向 **AI / LLM / Agent 开发工程师** 与 **AI 产品经理** 的中文面试题库。
> 持续迭代、不断新增题目，中文先行、后补英文翻译。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#贡献指南)
[![Language](https://img.shields.io/badge/lang-中文%20%7C%20English(WIP)-blue.svg)](#路线图-roadmap)

---

## 项目简介

本项目收集并整理 **AI / LLM / Agent 方向**在面试中真实遇到的问题与答案，覆盖两类典型岗位：

- **工程师视角**：模型原理、训练与推理、Prompt 工程、RAG、Agent 架构、工程化与部署、性能与成本优化等。
- **产品经理视角**：AI 产品定义、需求拆解、评估指标、数据飞轮、合规与伦理、商业化与落地等。

题库的核心定位：

- **中文先行**：前期以中文 Q&A 为主，逐步补齐英文翻译。
- **持续迭代**：题目与答案不断更新、不断新增，是一个长期维护的活文档。
- **结构化**：每道题都带**分类**与**元数据**，便于后续**检索、筛选与静态站展示**。

> 长期目标：当题量与质量达到一定程度后，基于这些结构化数据用 **GitHub Pages** 构建一个可检索、可分类浏览的静态站点。

---

## 特性

- 🗂 **分类组织**：按方向（LLM / Agent / RAG / 工程化 / 产品 …）和子分类分目录存放，便于定位。
- 🔎 **检索能力**：每题带统一的元数据字段（标签 / 难度 / 方向 / 更新时间），可按字段过滤、搜索，并为后续站点检索打基础。
- 🏷 **题目元数据**：标准化的 frontmatter，记录 `id`、`category`、`tags`、`difficulty`、`role`、`updated` 等字段。
- 🌐 **中文优先、双语演进**：先沉淀中文内容，后续以 `*.en.md` 形式补充英文翻译，互不阻塞。
- 📈 **可持续增长**：统一的单题模板，方便批量录入、机器解析与自动生成索引。
- 🚀 **面向静态站**：数据结构从一开始就对齐 GitHub Pages 展示需求，避免后期返工。

---

## 目录结构

题库按「方向 / 分类」分目录存放，建议采用如下约定（随题量增长可细化）：

```
AI-Interview-CheatSheet/
├── README.md                  # 项目说明（本文件）
├── LICENSE
├── questions/                 # 题库主目录，所有 Q&A 存放于此
│   ├── llm/                   # 大模型基础与原理
│   │   ├── attention-mechanism.md
│   │   └── tokenization.md
│   ├── agent/                 # Agent 架构与编排
│   │   └── react-vs-plan-execute.md
│   ├── rag/                   # 检索增强生成
│   │   └── chunking-strategies.md
│   ├── engineering/           # 工程化、部署、性能、成本
│   │   └── inference-optimization.md
│   └── product/               # AI 产品经理方向
│       └── ai-product-metrics.md
├── assets/                    # 图片、图表等静态资源
└── docs/                      # 未来 GitHub Pages 站点的构建产物 / 配置
```

约定说明：

- **一题一文件**：每道题目独立成 `.md` 文件，文件名使用英文小写短横线命名（kebab-case），如 `attention-mechanism.md`，便于检索与 URL 友好。
- **目录即分类**：所在子目录代表其主分类（`category`），文件内 frontmatter 再补充更细粒度的 `tags`。
- **英文翻译**：英文版以同名 `*.en.md` 存放于同一目录，如 `attention-mechanism.en.md`。

---

## 单题格式约定

每道题是一个独立的 Markdown 文件，由 **YAML frontmatter（元数据）** + **正文（问题 / 答案）** 两部分组成。可直接复制下面的模板新增题目：

```markdown
---
id: llm-0001                      # 全局唯一 ID，建议 "方向-序号"
title: 简述 Transformer 中的自注意力机制     # 题目标题
category: llm                     # 主分类，与所在目录一致
tags: [transformer, attention, 原理]   # 细粒度标签，便于检索
difficulty: medium                # easy | medium | hard
role: engineer                    # engineer | pm | both
source: 字节跳动一面               # 可选，题目来源
updated: 2026-06-17               # 最近更新日期（YYYY-MM-DD）
status: published                 # draft | published
---

## 问题

简述 Transformer 中的自注意力（Self-Attention）机制，并说明为什么需要多头注意力。

## 答案

自注意力机制通过 Query、Key、Value 三组向量计算 token 之间的相关性……

> **要点**
> - Scaled Dot-Product Attention 的计算流程
> - 多头注意力如何捕捉不同子空间的特征
> - 复杂度与长序列的局限

## 延伸 / 追问

- 与传统 RNN / CNN 相比的优势？
- 如何缓解自注意力的 O(n²) 复杂度？

## 参考

- Vaswani et al., *Attention Is All You Need*, 2017
```

**元数据字段说明**

| 字段 | 必填 | 说明 |
| --- | :---: | --- |
| `id` | ✅ | 全局唯一标识，建议 `方向-序号`（如 `agent-0007`） |
| `title` | ✅ | 题目标题，用于索引与站点展示 |
| `category` | ✅ | 主分类，与所在目录保持一致 |
| `tags` | ✅ | 标签数组，支撑多维检索 |
| `difficulty` | ✅ | 难度：`easy` / `medium` / `hard` |
| `role` | ✅ | 适配岗位：`engineer` / `pm` / `both` |
| `source` | ⬜ | 题目来源（公司 / 渠道），可留空 |
| `updated` | ✅ | 最近更新日期，`YYYY-MM-DD` |
| `status` | ✅ | `draft`（草稿）/ `published`（已发布） |

> 统一的 frontmatter 是后续**自动生成索引、检索过滤、GitHub Pages 展示**的基础，请新增题目时务必填写完整。

---

## 路线图 (Roadmap)

- [x] **阶段一 · 中文题库**：搭建目录结构与单题模板，持续录入中文 Q&A。
- [ ] **阶段二 · 英文翻译**：为已发布题目补充 `*.en.md` 英文版本，形成双语题库。
- [ ] **阶段三 · 检索 / 分类完善**：基于元数据自动生成分类索引、标签云与全文检索。
- [ ] **阶段四 · GitHub Pages 静态站**：将结构化题库渲染为可检索、可分类浏览的静态站点对外展示。

---

## 贡献指南

欢迎一起完善这份题库！新增一条 Q&A 的流程：

1. **确定分类**：在 `questions/<方向>/` 下选择或新建合适的子目录。
2. **新建文件**：复制上文「单题格式约定」中的模板，文件名使用英文 kebab-case，如 `tool-calling-design.md`。
3. **填写元数据**：完整填写 frontmatter（尤其 `id` / `category` / `tags` / `difficulty` / `role` / `updated`），`id` 不要与已有题目冲突。
4. **撰写内容**：问题描述清晰，答案准确并尽量给出要点、追问与参考资料。
5. **提交 PR**：遵循下方命名与提交规范。

**命名规范**

- 文件名：英文小写 + 短横线（kebab-case），语义清晰，例如 `kv-cache-explained.md`。
- 题目 `id`：`方向-四位序号`，如 `rag-0003`、`pm-0012`。
- 英文版：同名加 `.en.md` 后缀，置于同一目录。

**提交（Commit / PR）规范**

- 提交信息建议遵循 [Conventional Commits](https://www.conventionalcommits.org/)：
  - `docs: add llm question about kv-cache`（新增题目）
  - `docs: fix answer in agent/react-vs-plan-execute`（修正内容）
  - `chore: restructure rag directory`（结构调整）
- 一个 PR 聚焦一类改动，便于 review。
- 提交前请自检：frontmatter 字段完整、`id` 唯一、Markdown 渲染正常。

---

## License

本项目基于 [MIT License](./LICENSE) 开源。
