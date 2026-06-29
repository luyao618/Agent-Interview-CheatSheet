# 📚 AI 面试题库 · 目录

> 按**分类 + 序号**排列，点击题目标题即可跳转到对应题解。

**题目总数：77** ｜ 索引来源：[`index.json`](index.json)

## 分类总览

| 分类 | 数量 | 快速跳转 |
| :--- | :---: | :--- |
| 🤖 Agent 架构与编排 | 32 | [查看 ↓](#-agent-架构与编排) |
| 🔍 检索增强生成 | 37 | [查看 ↓](#-检索增强生成) |
| ⚙️ 工程化、部署、性能、成本 | 8 | [查看 ↓](#-工程化部署性能成本) |

---

## 🤖 Agent 架构与编排

<sub>分类 ID：`agent` ｜ 共 32 题</sub>

| # | 题目 | 难度 |
| :---: | :--- | :---: |
| 1 | [如何设计 Skill 来降低 Token 消耗](questions/agent-0001-skill-token-optimization.md) | 🟡 进阶 |
| 2 | [一个完整的 Agent 智能体架构一般包括哪些部分](questions/agent-0002-agent-architecture-components.md) | 🟡 进阶 |
| 3 | [你对 Agent 了解多少，如何理解与定义 AI Agent](questions/agent-0003-define-ai-agent.md) | 🟢 入门 |
| 4 | [Function Calling 是怎么设计的](questions/agent-0004-function-calling-design.md) | 🟡 进阶 |
| 5 | [工具调用的安全控制是怎么实现的](questions/agent-0005-tool-calling-security.md) | 🟡 进阶 |
| 6 | [Agent 如何处理 token 限制并把短期/长期记忆注入提示词](questions/agent-0006-memory-token-limit-injection.md) | 🟡 进阶 |
| 7 | [LLM 用 MCP 调用内部系统接口的完整生命周期，大模型能直接调接口吗](questions/agent-0007-mcp-call-lifecycle.md) | 🟡 进阶 |
| 8 | [Agent 与 Workflow automation 的区别是什么](questions/agent-0008-agent-vs-workflow.md) | 🟢 入门 |
| 9 | [Agent 与 RPA 有什么差别](questions/agent-0009-agent-vs-rpa.md) | 🟢 入门 |
| 10 | [为什么 Agent 比普通 chatbot 更复杂](questions/agent-0010-agent-vs-chatbot-complexity.md) | 🟢 入门 |
| 11 | [Agent 的 long-term memory 与 short-term memory 如何设计](questions/agent-0011-long-short-term-memory.md) | 🟡 进阶 |
| 12 | [Agent 为什么容易 hallucination](questions/agent-0012-agent-hallucination-causes.md) | 🟡 进阶 |
| 13 | [如何让 Agent 自动拆分任务](questions/agent-0013-task-decomposition.md) | 🟡 进阶 |
| 14 | [如何设计 Agent 的 tool registry](questions/agent-0014-tool-registry-design.md) | 🟡 进阶 |
| 15 | [Agent 如何避免无限循环调用工具](questions/agent-0015-avoid-infinite-tool-loop.md) | 🟡 进阶 |
| 16 | [Agent 如何实现 checkpoint / resume](questions/agent-0016-checkpoint-resume.md) | 🟡 进阶 |
| 17 | [Prompt 注入攻击如何防御](questions/agent-0017-prompt-injection-defense.md) | 🟡 进阶 |
| 18 | [有哪些 RAG/Agent 评测维度](questions/agent-0018-rag-agent-eval-dimensions.md) | 🟡 进阶 |
| 19 | [Prompt Engineering 和 Context Engineering 有什么区别](questions/agent-0019-prompt-vs-context-engineering.md) | 🟡 进阶 |
| 20 | [Agent 的记忆类型有哪些？上下文超过模型最大长度怎么解决](questions/agent-0020-memory-types-context-overflow.md) | 🟡 进阶 |
| 21 | [如何确保 Agent 返回标准 JSON？如果模型输出多余说明文字，后端如何提取？](questions/agent-0021-structured-json-output.md) | 🟡 进阶 |
| 22 | [Prompt 和 MCP 为什么要抽象？换模型是否需要重调提示词？](questions/agent-0022-prompt-mcp-abstraction.md) | 🟡 进阶 |
| 23 | [超长上下文怎么处理？记忆模块怎么设计](questions/agent-0023-long-context-memory-module.md) | 🟡 进阶 |
| 24 | [MCP 和 Function Calling 的区别与优势是什么](questions/agent-0024-mcp-vs-function-calling.md) | 🟡 进阶 |
| 25 | [ReAct 模式的工作原理是什么](questions/agent-0025-react-pattern-working-principle.md) | 🟡 进阶 |
| 26 | [常见的 Multi-Agent 协作模式有哪些](questions/agent-0026-multi-agent-collaboration-patterns.md) | 🟡 进阶 |
| 27 | [单 Agent 遇瓶颈时，为什么需要 Multi-Agent](questions/agent-0027-why-multi-agent.md) | 🟡 进阶 |
| 28 | [如何设计 Agent 长期记忆的写回策略、衰减策略与冲突消解](questions/agent-0028-long-term-memory-writeback-decay-conflict.md) | 🔴 困难 |
| 29 | [Agent 设计里，你觉得最重要的部分是什么](questions/agent-0029-most-important-part-of-agent-design.md) | 🟡 进阶 |
| 30 | [MCP、A2A、普通 Function Calling 三者有什么本质区别？工程里怎么选？](questions/agent-0030-mcp-a2a-function-calling.md) | 🟡 进阶 |
| 31 | [上下文工程有哪些需要注意的点](questions/agent-0031-context-engineering-key-points.md) | 🟡 进阶 |
| 32 | [怎么做并行 Tool Calling，既提升吞吐又保证一致性和可回放性](questions/agent-0032-parallel-tool-calling.md) | 🔴 困难 |

<div align="right"><a href="#-ai-面试题库--目录">↑ 返回顶部</a></div>

## 🔍 检索增强生成

<sub>分类 ID：`rag` ｜ 共 37 题</sub>

| # | 题目 | 难度 |
| :---: | :--- | :---: |
| 1 | [RAG 里 Chunk 是怎么切的：固定、语义还是自适应](questions/rag-0001-chunking-strategies.md) | 🟡 进阶 |
| 2 | [为什么引入父子索引（Parent-Child Index）](questions/rag-0002-parent-child-index.md) | 🟡 进阶 |
| 3 | [为什么在检索阶段引入 BM25](questions/rag-0003-bm25-in-retrieval.md) | 🟡 进阶 |
| 4 | [Rerank 后的 topK 截断是怎么做的](questions/rag-0004-rerank-topk-truncation.md) | 🟡 进阶 |
| 5 | [RAG 系统如何评测](questions/rag-0005-rag-evaluation.md) | 🟡 进阶 |
| 6 | [评测数据集一般包括哪些内容](questions/rag-0006-eval-dataset-contents.md) | 🟢 入门 |
| 7 | [如果要提升检索相关度，你会怎么做](questions/rag-0007-improve-relevance.md) | 🟡 进阶 |
| 8 | [向量化之前为什么要对长文档切片？不切片会怎样](questions/rag-0008-why-chunk-long-docs.md) | 🟡 进阶 |
| 9 | [切片时设置重叠区域的作用是什么？比例通常怎么确定](questions/rag-0009-chunk-overlap-purpose.md) | 🟡 进阶 |
| 10 | [稠密向量和稀疏向量有什么区别？分别适合哪些搜索需求](questions/rag-0010-dense-vs-sparse-vectors.md) | 🟡 进阶 |
| 11 | [向量库检索的 Top-K 设置过大，会对生成质量产生哪些负面影响](questions/rag-0011-topk-too-large-impact.md) | 🟡 进阶 |
| 12 | [为什么初筛召回后还要加 Rerank 模型？它能解决向量搜索的哪些局限](questions/rag-0012-why-rerank-after-recall.md) | 🟡 进阶 |
| 13 | [文档发生局部更新时，如何通过增量索引避免全量重新向量化](questions/rag-0013-incremental-indexing.md) | 🟡 进阶 |
| 14 | [生成阶段如何在 Prompt 中设定边界条件，防止没检索到内容时模型产生幻觉](questions/rag-0014-prompt-boundary-anti-hallucination.md) | 🟡 进阶 |
| 15 | [HyDE 的原理是什么？处理模糊提问有什么优势](questions/rag-0015-hyde-principle.md) | 🟡 进阶 |
| 16 | [超长上下文模型出现后，传统 RAG 架构的必要性是否降低](questions/rag-0016-long-context-vs-rag.md) | 🟡 进阶 |
| 17 | [RAG 检索到针对同一故障的两份冲突手册，如何识别冲突并优先选时效性更高的信息](questions/rag-0017-conflicting-docs-resolution.md) | 🔴 困难 |
| 18 | [搭建 RAG 系统时，长文本的 chunking 策略如何设计，如何防止上下文截断](questions/rag-0018-chunking-anti-truncation.md) | 🟡 进阶 |
| 19 | [如果遇到简单专有名词匹配问题，知识库多路召回架构如何设计](questions/rag-0019-multi-route-recall.md) | 🟡 进阶 |
| 20 | [有医疗/法律等专业领域知识，要做智能助手，RAG 链路会怎么搭建](questions/rag-0020-domain-rag-pipeline.md) | 🔴 困难 |
| 21 | [Agentic RAG 项目的数据来源与质量保障怎么做](questions/rag-0021-agentic-rag-data-quality.md) | 🟡 进阶 |
| 22 | [搜索触发条件如何设计？如何优化检索质量](questions/rag-0022-search-trigger-and-quality.md) | 🟡 进阶 |
| 23 | [RAG pipeline 的完整流程是什么](questions/rag-0023-rag-pipeline-full-flow.md) | 🟢 入门 |
| 24 | [如何设计一个 100M 文档规模的 RAG 系统](questions/rag-0024-100m-doc-rag-design.md) | 🔴 困难 |
| 25 | [RAG 中 Chunk size 如何选择](questions/rag-0025-chunk-size-selection.md) | 🟡 进阶 |
| 26 | [Embedding model 如何选择](questions/rag-0026-embedding-model-selection.md) | 🟡 进阶 |
| 27 | [如何评估 RAG 检索质量](questions/rag-0027-evaluate-retrieval-quality.md) | 🟡 进阶 |
| 28 | [RAG 中 metadata filtering 的作用是什么](questions/rag-0028-metadata-filtering.md) | 🟡 进阶 |
| 29 | [如何降低 RAG 的端到端延迟](questions/rag-0029-reduce-rag-latency.md) | 🟡 进阶 |
| 30 | [评价指标、测试集、ground truth 如何定义](questions/rag-0030-metrics-testset-groundtruth.md) | 🟡 进阶 |
| 31 | [GraphRAG 系统整体流程是怎样的？从用户提问到最终生成答案，哪些模块是你独立负责的？](questions/rag-0031-graphrag-overall-flow.md) | 🔴 困难 |
| 32 | [GraphRAG 相比传统 RAG 的核心优势是什么？怎么保证召回准确率？](questions/rag-0032-graphrag-advantages.md) | 🟡 进阶 |
| 33 | [RAG 输出错误，怎么判断是检索错了还是生成错了？有做过归因实验吗？](questions/rag-0033-retrieval-vs-generation-attribution.md) | 🟡 进阶 |
| 34 | [Chunk 划分策略对 RAG 效果影响大吗？用过哪些优化方式](questions/rag-0034-chunk-strategy-impact.md) | 🟡 进阶 |
| 35 | [如果不用图数据库，能实现真正的 GraphRAG 吗？为什么？](questions/rag-0035-graphrag-without-graphdb.md) | 🔴 困难 |
| 36 | [RAG 你们怎么优化的：chunk size / overlap 怎么设，要不要加 rerank](questions/rag-0036-rag-optimization-practices.md) | 🟡 进阶 |
| 37 | [Deep Research 是什么？还算不算 RAG](questions/rag-0037-deep-research-vs-rag.md) | 🟡 进阶 |

<div align="right"><a href="#-ai-面试题库--目录">↑ 返回顶部</a></div>

## ⚙️ 工程化、部署、性能、成本

<sub>分类 ID：`engineering` ｜ 共 8 题</sub>

| # | 题目 | 难度 |
| :---: | :--- | :---: |
| 1 | [多 Agent 协作并发操作业务实体时，用 Redis 分布式锁如何避免主从切换导致锁丢失](questions/engineering-0001-redis-distributed-lock-failover.md) | 🔴 困难 |
| 2 | [专家级 Agent 主动操作底层命令或行为时，架构上如何保证指令幂等与分布式事务回滚](questions/engineering-0002-idempotency-distributed-transaction.md) | 🔴 困难 |
| 3 | [讲一下分布式令牌桶限流](questions/engineering-0003-distributed-token-bucket.md) | 🟡 进阶 |
| 4 | [滑动窗口算法是怎么实现的？](questions/engineering-0004-sliding-window-rate-limit.md) | 🟡 进阶 |
| 5 | [滑动窗口和令牌桶相比有什么区别？](questions/engineering-0005-sliding-window-vs-token-bucket.md) | 🟡 进阶 |
| 6 | [AI 应用项目里的监控怎么设计](questions/engineering-0006-ai-app-monitoring.md) | 🟡 进阶 |
| 7 | [字段提取任务里如何评估标注数据质量、合格标准与数据混合策略](questions/engineering-0007-annotation-quality-eval.md) | 🟡 进阶 |
| 8 | [双十一/双十二订单查询有上千万 QPS，从系统设计和大促筹备角度怎么支撑峰值流量](questions/engineering-0008-peak-qps-system-design.md) | 🔴 困难 |

<div align="right"><a href="#-ai-面试题库--目录">↑ 返回顶部</a></div>

---

<sub>本目录由 `scripts/gen_index.py` 从 `index.json` 自动生成；新增题目后请重跑该脚本以保持同步。</sub>
