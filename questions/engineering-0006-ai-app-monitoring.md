---
id: engineering-0006
title: AI 应用项目里的监控怎么设计
category: engineering
tags: [engineering, observability, monitoring, llm-ops, tracing]
difficulty: medium
role: engineer
contributor: 佚名
source: 腾讯
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

AI 应用项目里的监控怎么设计？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

核心结论：AI 应用的监控 = **传统服务可观测性（延迟/错误/资源）+ LLM 特有维度（质量、幻觉、成本、token）**。差异在于输出是概率性的、无标准答案，所以不能只看「成功/失败」，必须把**全链路 tracing**、**质量评估**与**人审回流**做进监控闭环。

**四层指标体系**

```
        ┌─────────────────────────────────────────┐
用户 ──► │  AI 应用（RAG / Agent / 多步调用链）           │
        └───────┬───────────────────────────────────┘
                ▼   每次请求落一条 trace（trace_id 贯穿）
  ┌────────────────────────────────────────────────┐
  │ ① 链路 Tracing：检索→Prompt→LLM→工具→后处理 逐 span  │
  │ ② 质量指标：相关性 / 忠实度(幻觉) / 拒答率 / 格式合规   │
  │ ③ 性能&成本：延迟(首token/总)、token、$、QPS、错误率   │
  │ ④ 系统指标：CPU/GPU、显存、队列、依赖(向量库/API)健康  │
  └───────┬────────────────────────┬──────────────┘
          ▼                        ▼
     实时告警 (阈值/突变)      离线评估 + 人审回流 → 修 Prompt/数据
```

1. **链路 Tracing**——给每次请求一个 `trace_id`，把「检索 → 拼 Prompt → LLM 调用 → 工具/函数调用 → 后处理」拆成有父子关系的 span，记录每一步的输入、输出、耗时、token、命中的文档。这是 LLM 应用调试的地基：出问题时能定位是检索召回差、Prompt 拼错，还是模型本身幻觉。用 LangSmith / Langfuse / Phoenix / OpenTelemetry 落地。

2. **质量指标**——这是 AI 应用区别于普通服务的核心。
   - **相关性 / 忠实度（faithfulness）**：回答是否基于检索到的上下文，用于度量**幻觉**；
   - **答案相关性、检索 recall/precision**（RAG 场景，RAGAS 类指标）；
   - **拒答率、格式/JSON 合规率、护栏命中率**。
   质量多用 **LLM-as-a-Judge** 抽样在线打分 + 离线评测集回归，二者结合控成本。

3. **成本 / 延迟 / token**——按模型、按路由、按租户维度统计 **token 用量、$ 成本、P50/P95/P99 延迟（含首 token 延迟）、缓存命中率**。这是最容易失控、也最被业务关心的维度。

4. **异常告警**——对错误率、超时、成本突增、拒答率飙升、相关性掉点设阈值与同比/环比突变告警，接 Prometheus + Grafana / Alertmanager 或可观测平台。

**人审回流（闭环）**

线上抽样 + 用户负反馈（点踩、复制率低、重试）→ 进人工审核队列 → 标注好坏 → 回流为**评测集 / 微调数据 / Prompt 迭代依据**。监控不止于「看板报警」，而要把坏 case 沉淀成下一轮优化的输入，形成数据飞轮。

**落地建议**：trace 全量采样、质量指标抽样评估（控成本）、PII 脱敏后入库；先把 trace_id 串起来，再叠质量与成本看板。

一句话：**全链路 tracing 打底，质量与成本是 AI 应用的专属仪表盘，人审回流让监控闭环成长。**

## 延伸 / 追问

**追问：质量/幻觉这种没有标准答案的指标，线上怎么实时监控而不爆成本？**

分层抽样 + 代理信号。① **代理信号（便宜、可全量）**：用户负反馈（点踩、追问、重试、提前关闭）、拒答率、格式合规率、检索命中数、回答与上下文的 embedding 相似度——这些不调用大模型即可算，作为质量「体温计」实时盯。② **LLM-as-a-Judge（贵、抽样）**：对 1%~5% 流量异步打分忠实度/相关性，用小模型当裁判降本，结果落看板看趋势而非逐条卡。③ **离线评测集回归**：维护一套「问题→应命中片段/参考答案」的黄金集，每次改 Prompt/换模型/更新知识库前跑回归，防掉点。三者配合：代理信号触发告警 → 抽样 Judge 定位 → 离线集兜底验证，既实时又不烧钱。

## 参考

- Langfuse Docs，*LLM Observability & Tracing*：https://langfuse.com/docs
- LangSmith Docs，*Tracing & Evaluation*：https://docs.smith.langchain.com/
- RAGAS Docs，*Metrics（faithfulness / answer relevancy / context recall）*：https://docs.ragas.io/
- Arize Phoenix，*LLM Tracing & Evaluation*：https://docs.arize.com/phoenix
