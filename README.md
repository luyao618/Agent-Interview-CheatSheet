# Agent-Interview-CheatSheet

> 面向 **AI / LLM / Agent 开发工程师** 与 **AI 产品经理** 的面试题库。
> 每道题会用头部的大模型的回答作为default回答。
> 持续迭代、不断新增题目，欢迎补充。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#贡献指南)
[![Language](https://img.shields.io/badge/lang-中文%20%7C%20English(WIP)-blue.svg)](#路线图-roadmap)

---

## 项目简介

本项目收集并整理 **AI / LLM / Agent 方向**在面试中真实遇到的问题，包括但不限于：

- **工程师视角**：模型原理、训练与推理、Prompt 工程、RAG、Agent 架构、工程化与部署、性能与成本优化等。
- **产品经理视角**：AI 产品定义、需求拆解、评估指标、数据飞轮、合规与伦理、商业化与落地等。

对于每个问题会用头部大模型回答面试问题作为"Defualt Answer"。
每个问题一个markdown文件，包含元数据，目录包含所有问题方便检索。

> 📖 **题目目录**：[index.md](./index.md) —— 按分类 + 序号排列，点击即可跳转到对应题目。

> 未来目标：当题量与质量达到一定程度后，基于这些结构化数据用 **GitHub Pages** 构建一个可检索、可分类浏览的静态站点。

---

## 目录结构

所有题目 Markdown在 `questions/` 根目录下；分类与检索能力由仓库根目录的单一索引文件 `index.json` 承载，根目录 `index.md` 是面向用户的可点击目录页。

```
AI-Interview-CheatSheet/
├── README.md                  # 项目说明（本文件）
├── LICENSE
├── index.json                 # 检索索引 + category registry（唯一索引来源，仓库根目录）
├── index.md                   # 目录页：按分类 + 序号排列，点击跳转到对应题目
├── questions/                 # 题库主目录，所有 Q&A Markdown 存放于此
│   ├── llm-0001-attention-mechanism.md       # 中文题目
│   ├── llm-0001-attention-mechanism.en.md    # 对应英文翻译
│   ├── agent-0001-react-vs-plan-execute.md
│   └── rag-0001-chunking-strategies.md
├── assets/                    # 图片、图表等静态资源
└── docs/                      # 未来 GitHub Pages 站点的构建产物 / 配置
```

约定说明：

- **一题一文件、根目录平铺**：每道题目独立成 `.md` 文件，直接放在 `questions/` 根目录下。
- **文件命名**：`questions/<id>-<slug>.md`。`<id>` 为 `方向-四位序号`（如 `rag-0003`）；`<slug>` 使用英文小写短横线命名（lowercase ASCII kebab-case），语义清晰、URL 友好，如 `llm-0001-attention-mechanism.md`。
- **分类来自索引而非目录**：题目的主分类由 frontmatter 的 `category` 字段显式承载，并在根目录 `index.json` 中重复登记；`index.json` 的 `categories` 是分类的权威 registry（含中文 label 与排序），不靠文件夹路径表达 `category`。
- **归类原则**：**技术题一律按技术方向归类**（`llm` / `agent` / `rag` / `engineering`），即使 `role: pm` 也按技术方向归类，再用 `role` 字段标注视角（`engineer` / `pm` / `both`）；`product` 分类**只放纯产品方法论题**（如需求拆解、商业化、指标体系），避免与 `role: pm` 语义重叠。更细粒度先用 `tags`，暂不引入 `subcategory`。
- **语言区分**：语言由文件后缀区分——中文原文为 `questions/<id>-<slug>.md`，英文翻译为同 basename 加 `.en.md`，同样平铺在 `questions/` 根目录，如 `llm-0001-attention-mechanism.en.md`。

### 索引文件 `index.json`

`index.json`（位于仓库根目录）是题库的唯一检索索引与 category registry，必须是合法 JSON。分类 registry 预置五个固定分类：

```json
{
  "schema_version": 1,
  "categories": [
    {"id": "llm", "label": "大模型基础与原理", "sort": 10},
    {"id": "agent", "label": "Agent 架构与编排", "sort": 20},
    {"id": "rag", "label": "检索增强生成", "sort": 30},
    {"id": "engineering", "label": "工程化、部署、性能、成本", "sort": 40},
    {"id": "product", "label": "AI 产品经理方向", "sort": 50}
  ],
  "questions": []
}
```

每个 `questions[]` entry 的字段约定：

| 字段 | 必填 | 说明 |
| --- | :---: | --- |
| `id` | ✅ | 全局唯一 ID，`方向-四位序号`，与文件名前缀一致 |
| `title` | ✅ | 题目标题 |
| `file` | ✅ | 中文源文件名（root-level，如 `llm-0001-attention-mechanism.md`） |
| `language` | ✅ | 源文件语言，通常为 `zh` |
| `category` | ✅ | 主分类，须匹配 `id` 前缀与 `categories` 中某个 `id` |
| `category_label` | ✅ | 分类中文 label，与 `categories` 中对应项一致 |
| `tags` | ✅ | 标签数组 |
| `difficulty` | ✅ | `easy` / `medium` / `hard` |
| `role` | ✅ | `engineer` / `pm` / `both` |
| `status` | ✅ | `draft` / `published` |
| `contributor` | ✅ | 题目提供人，默认 `佚名` |
| `updated` | ✅ | 题目条目最后变更日期，`YYYY-MM-DD` |
| `answers_count` | ✅ | 答案条数 |
| `source` | ⬜ | 可选，题目来源（公司 / 渠道） |
| `translations` | ⬜ | 可选，翻译映射，如 `{"en": "llm-0001-attention-mechanism.en.md"}` |

> 索引**不复制**完整题干或答案正文——Markdown 文件始终是内容的 source of truth，`index.json` 只承载用于检索/分类/排序的元数据。
> 一致性约束：每个 root-level `questions/*.md` 都必须有对应的 index entry，且每个 index entry 的 `file` 都必须指向真实存在的 root-level 文件。

---

## 单题格式约定

每道题是一个独立的 Markdown 文件，由 **YAML frontmatter（元数据）** + **正文（问题 / 各条答案）** 两部分组成。

一道题可以挂**多条答案**：录入时**默认带一条 AI 答案**（`author` 署回答模型名），之后任何人都可以追加署名的人类答案或新的 AI 答案。每条答案的元数据（署名、类型、日期等）写在 frontmatter 的 `answers` 列表里，**答案正文**写在正文区对应的 `## 答案 · <author>` 小节中，二者通过 `author` 对应。

可直接复制下面的模板新增题目：

```markdown
---
id: llm-0001                      # 全局唯一 ID，"方向-四位序号"，与文件名前缀一致
title: 简述 Transformer 中的自注意力机制     # 题目标题
category: llm                     # 主分类，须匹配 id 前缀和 index.json 中的某个 category
tags: [transformer, attention, 原理]   # 细粒度标签，便于检索
difficulty: medium                # easy | medium | hard
role: engineer                    # engineer | pm | both
contributor: 佚名                 # 题目提供人，默认「佚名」
source: 字节跳动一面               # 可选，题目来源
status: published                 # draft | published
updated: 2026-06-17               # 题目条目最后变更日期（题干/元数据/任一答案，YYYY-MM-DD）
answers:                          # 多答案列表，至少一条
  - author: Claude-Opus-4.8       # 署名：AI 答案填模型名，人类答案填自取的名字
    type: ai                      # ai | human
    model: Claude-Opus-4.8        # 仅 AI 答案填，便于按模型检索/统计；人类答案省略
    answered: 2026-06-17          # 该答案的回答日期（YYYY-MM-DD）
    updated: 2026-06-17           # 该答案的更新日期（YYYY-MM-DD）
  - author: 老王
    type: human
    answered: 2026-06-18
    updated: 2026-06-18
---

## 问题

简述 Transformer 中的自注意力（Self-Attention）机制，并说明为什么需要多头注意力。

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-06-17

自注意力机制通过 Query、Key、Value 三组向量计算 token 之间的相关性……

> **要点**
> - Scaled Dot-Product Attention 的计算流程
> - 多头注意力如何捕捉不同子空间的特征
> - 复杂度与长序列的局限

## 答案 · 老王

> 🙋 人类答案 · 老王 · 回答 2026-06-18

面试时我会先讲清楚「为什么要 attention」，再展开计算细节……

## 延伸 / 追问

- 与传统 RNN / CNN 相比的优势？
- 如何缓解自注意力的 O(n²) 复杂度？

## 参考

- Vaswani et al., *Attention Is All You Need*, 2017
```

**元数据字段说明**

| 字段 | 必填 | 说明 |
| --- | :---: | --- |
| `id` | ✅ | 全局唯一标识，`方向-四位序号`（如 `agent-0007`），前缀与文件名/`category` 一致 |
| `title` | ✅ | 题目标题，用于索引与站点展示 |
| `category` | ✅ | 主分类，须匹配 `id` 前缀和 `index.json` 中的某个 category，**不再与所在目录绑定** |
| `tags` | ✅ | 标签数组，支撑多维检索 |
| `difficulty` | ✅ | 难度：`easy` / `medium` / `hard` |
| `role` | ✅ | 适配岗位：`engineer` / `pm` / `both` |
| `contributor` | ✅ | 题目**提供人**（谁录入/提供了这道题），默认 `佚名`；注意与答案的 `author` 区分 |
| `source` | ⬜ | 题目来源（公司 / 渠道），可留空 |
| `status` | ✅ | `draft`（草稿）/ `published`（已发布） |
| `updated` | ✅ | **题目条目**最后变更日期（题干、元数据或任一答案有改动即更新），`YYYY-MM-DD` |
| `answers` | ✅ | 答案列表，至少一条；每个元素的字段见下 |
| `answers[].author` | ✅ | 答案**署名**：AI 答案填回答模型名（如 `Claude-Opus-4.8`），人类答案填自取的名字 |
| `answers[].type` | ✅ | 答案类型：`ai` 或 `human` |
| `answers[].model` | 条件 | **仅 AI 答案填**，回答所用模型名；保留独立字段方便按模型检索/统计（人类答案省略） |
| `answers[].answered` | ✅ | 该条答案的回答日期，`YYYY-MM-DD` |
| `answers[].updated` | ✅ | 该条答案的更新日期，`YYYY-MM-DD` |

> **`updated` 的两个层级**：题目级 `updated` 是「整条题目最后一次变更」，用于站点排序与「最近更新」；每条答案的 `answers[].updated` 是「这条答案自身最后一次修订」。改动某条答案时，同时更新该答案的 `updated` 和题目级 `updated`。

> 统一的 frontmatter 是后续**维护索引、检索过滤、GitHub Pages 展示**的基础，请新增题目时务必填写完整，并在 `index.json` 中同步登记对应 entry。

---

## 路线图 (Roadmap)

- [x] **阶段一 · 中文题库**：搭建扁平目录结构与单题模板，持续录入中文 Q&A。
- [ ] **阶段二 · 英文翻译**：为已发布题目补充 `*.en.md` 英文版本，形成双语题库。
- [ ] **阶段三 · 检索 / 分类完善**：基于 `index.json` 与元数据完善分类索引、标签云与全文检索。
- [ ] **阶段四 · GitHub Pages 静态站**：将结构化题库渲染为可检索、可分类浏览的静态站点对外展示。

---

## 贡献指南

欢迎一起完善这份题库！新增一条 Q&A 的流程：

1. **确定分类**：选定题目的主分类（`llm` / `agent` / `rag` / `engineering` / `product` 之一，须是 `index.json` 中已登记的 category；技术题按技术方向归类，纯产品方法论题归 `product`）。
2. **新建文件**：复制上文「单题格式约定」中的模板，在 `questions/` 根目录下新建文件，文件名为 `<id>-<slug>.md`，`<slug>` 用英文 kebab-case，如 `agent-0007-tool-calling-design.md`。**不要创建分类子目录。**
3. **填写元数据**：完整填写 frontmatter（`id` / `category` / `tags` / `difficulty` / `role` / `contributor` / `status` / `updated` 以及 `answers` 列表），`id` 不要与已有题目冲突，且 `category` 须匹配 `id` 前缀与某个 index category；不填 `contributor` 时按 `佚名` 处理。
4. **撰写内容**：问题描述清晰；至少提供一条答案，**默认带一条署名模型名的 AI 答案**，每条答案在正文区写成 `## 答案 · <author>` 小节，并在 frontmatter `answers` 中补齐该答案的 `author` / `type` / `model` / `answered` / `updated`。
5. **新增/修订答案**：在 `answers` 列表追加或修改对应条目，更新该答案的 `updated`，并同步刷新题目级 `updated`。
6. **登记索引**：在 `index.json` 的 `questions` 数组中新增/更新对应 entry（字段见上文「索引文件」），确保 `file` 指向新建的 Markdown 文件。
7. **提交 PR**：遵循下方命名与提交规范。

**命名规范**

- 文件名：`questions/<id>-<slug>.md`，`<slug>` 用英文小写 + 短横线（kebab-case），语义清晰，例如 `llm-0002-kv-cache-explained.md`。
- 题目 `id`：`方向-四位序号`，前缀与文件名/`category` 一致，如 `rag-0003`、`product-0012`。
- 答案署名 `author`：AI 答案统一填回答模型名（如 `GPT-5.5`、`Claude-Opus-4.8`），人类答案填自取的名字。
- 英文版：同 basename 加 `.en.md` 后缀，同样平铺在 `questions/` 根目录，如 `llm-0002-kv-cache-explained.en.md`。

**提交（Commit / PR）规范**

- 提交信息建议遵循 [Conventional Commits](https://www.conventionalcommits.org/)：
  - `docs: add llm question about kv-cache`（新增题目）
  - `docs: fix answer in agent-0001-react-vs-plan-execute`（修正内容）
  - `chore: update index.json`（索引调整）
- 一个 PR 聚焦一类改动，便于 review。
- 提交前请自检：frontmatter 字段完整、`id` 唯一、`index.json` 已同步登记且能被 JSON parser 解析、Markdown 渲染正常。

---

## License

本项目基于 [MIT License](./LICENSE) 开源。
