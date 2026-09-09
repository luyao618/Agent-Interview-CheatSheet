# 📚 AI 面试题库 · 目录

> 按**分类 + 序号**排列，点击题目标题即可跳转到对应题解。

**题目总数：122** ｜ 索引来源：[`index.json`](index.json)

## 按能力路径浏览

> 题目按技术分类归档；能力路径用于 Developer 与 PM 的跨分类学习，不改变既有题目 ID 或链接。

| 层级 | 能力 | 说明 |
| :---: | :--- | :--- |
| **L0** | **AI-native 基础判断** | 判断 AI 适用边界、任务价值与人与系统的责任边界。 |
| **L1** | **模型与知识基础** | 理解模型能力、Prompt/Context、模型选择、推理与成本边界。 |
| **L2** | **AI 应用构建** | 构建 Agent、RAG、Tool Calling/MCP、Memory、Workflow 与人工接管。 |
| **L3** | **生产化与治理** | 覆盖 Evaluation、Observability、Reliability、Security、Privacy 与 Cost。 |
| **L4** | **产品交付与业务闭环** | 完成需求发现、优先级、体验设计、指标、实验、合规与落地。 |

### Developer 路径（入口 → 目标）

| 层级 | 能力 | 入口 | 目标 |
| :---: | :--- | :--- | :--- |
| **L0** | AI-native 基础判断 | [Agent vs workflow](questions/agent-0008-agent-vs-workflow.md) | [为什么不能只调大模型 API](questions/agent-0035-why-not-just-call-llm-api.md) |
| **L1** | 模型与知识基础 | [Prompt vs context engineering](questions/agent-0019-prompt-vs-context-engineering.md) | [工具调用与 JSON 输出](questions/agent-0021-structured-json-output.md) |
| **L2** | AI 应用构建 | [RAG pipeline 全流程](questions/rag-0023-rag-pipeline-full-flow.md) | [Skill / token 优化](questions/agent-0001-skill-token-optimization.md) |
| **L3** | 生产化与治理 | [AI 应用监控](questions/engineering-0006-ai-app-monitoring.md) | [人手动接管与权限边界](questions/agent-0042-human-handoff-when-user-unavailable.md) |

### PM 路径（入口 → 目标）

| 层级 | 能力 | 入口 | 目标 |
| :---: | :--- | :--- | :--- |
| **L0** | AI 场景判断 | [AI 场景优先级](questions/product-0001-ai-scenario-prioritization.md) | [AI 需求拆解](questions/product-0002-ai-prd-requirements.md) |
| **L1** | 模型与知识基础 | [模型选型与能力边界](questions/llm-0002-open-source-vs-closed-source-models.md) | [Prompt / Context engineering](questions/agent-0019-prompt-vs-context-engineering.md) |
| **L2** | AI 应用构建 | [RAG pipeline 全流程](questions/rag-0023-rag-pipeline-full-flow.md) | [Function Calling 工具链](questions/agent-0004-function-calling-design.md) |
| **L3** | 生产化与治理 | [AI 产品指标](questions/product-0003-ai-product-metrics.md) | [失败恢复体验](questions/product-0004-ai-ux-failure-recovery.md) |
| **L4** | 产品交付与业务闭环 | [上线评测闭环](questions/product-0006-ai-product-iteration-loop.md) | [AI 需求拆解](questions/product-0002-ai-prd-requirements.md) |

**共同入口**：[`agent-0008`](questions/agent-0008-agent-vs-workflow.md) / [`agent-0035`](questions/agent-0035-why-not-just-call-llm-api.md) / [`agent-0019`](questions/agent-0019-prompt-vs-context-engineering.md) / [`product-0001`](questions/product-0001-ai-scenario-prioritization.md) / [`product-0003`](questions/product-0003-ai-product-metrics.md)，用来建立 AI 适用边界和业务落地的共同起点。

**Agent 内容映射**：[`agent-0008`](questions/agent-0008-agent-vs-workflow.md)、[`agent-0035`](questions/agent-0035-why-not-just-call-llm-api.md)、[`agent-0019`](questions/agent-0019-prompt-vs-context-engineering.md)、[`agent-0021`](questions/agent-0021-structured-json-output.md) 作为 L0/L1/L2 的串联入口；[`agent-0042`](questions/agent-0042-human-handoff-when-user-unavailable.md)、[`agent-0051`](questions/agent-0051-agent-virtual-identity-vs-user-identity.md)、[`agent-0054`](questions/agent-0054-self-improving-agent-trust-root-boundary.md) 聚焦 L3 与权责边界治理。

## 分类总览

| 分类 | 数量 | 快速跳转 |
| :--- | :---: | :--- |
| 🧠 大模型基础与原理 | 6 | [查看 ↓](#-大模型基础与原理) |
| 🤖 Agent 架构与编排 | 54 | [查看 ↓](#-agent-架构与编排) |
| 🔍 检索增强生成 | 41 | [查看 ↓](#-检索增强生成) |
| ⚙️ 工程化、部署、性能、成本 | 15 | [查看 ↓](#-工程化部署性能成本) |
| 📦 AI 产品与落地 | 6 | [查看 ↓](#-ai-产品与落地) |

---

## 🧠 大模型基础与原理

<sub>分类 ID：`llm` ｜ 共 6 题</sub>

| # | 题目 | 难度 |
| :---: | :--- | :---: |
| 1 | [什么是 LoRA 微调，LoRA 的核心思想是什么](questions/llm-0001-lora-fine-tuning.md) | 🟡 进阶 |
| 2 | [你怎么看开源模型和闭源模型？开源模型有哪些优势？](questions/llm-0002-open-source-vs-closed-source-models.md) | 🟢 入门 |
| 3 | [Chat Template 中 reasoning_content 应该保留、剥离还是压缩？](questions/llm-0003-chat-template-reasoning-content-retention.md) | 🔴 困难 |
| 4 | [多轮 Agent 后训练中，最终成败如何归因到中间工具调用决策？](questions/llm-0004-agent-rl-credit-assignment.md) | 🔴 困难 |
| 5 | [Agent 训练中如何判断 SFT 已经足够，应该切换到 RL？](questions/llm-0005-agent-training-sft-to-rl-switch.md) | 🔴 困难 |
| 6 | [什么是 Speculative Decoding？它如何在不改变输出分布的前提下加速 LLM 推理？](questions/llm-0006-speculative-decoding.md) | 🔴 困难 |

<div align="right"><a href="#-ai-面试题库--目录">↑ 返回顶部</a></div>

## 🤖 Agent 架构与编排

<sub>分类 ID：`agent` ｜ 共 54 题</sub>

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
| 33 | [Agent 工程师需要具备哪些技能和能力](questions/agent-0033-agent-engineer-skills.md) | 🟡 进阶 |
| 34 | [两个 Skill 内容不同但 description 相似导致 Agent 加载错 Skill，怎么解决](questions/agent-0034-skill-description-collision.md) | 🟡 进阶 |
| 35 | [LLM 应用开发为什么不能仅调用大模型 API，会遇到哪些问题](questions/agent-0035-why-not-just-call-llm-api.md) | 🟡 进阶 |
| 36 | [你怎么理解最近比较火的 loop 工程和 graph 工程](questions/agent-0036-loop-vs-graph-engineering.md) | 🟡 进阶 |
| 37 | [如何做一个多人对话的 Agent：识别每个人的发言并编排回复](questions/agent-0037-multi-user-conversation-orchestration.md) | 🟡 进阶 |
| 38 | [Agent 节省 Token 成本，有哪些思路和方法](questions/agent-0038-reduce-agent-token-cost.md) | 🟡 进阶 |
| 39 | [ReAct 轨迹变长后，如何在不丢关键状态的前提下降低上下文成本](questions/agent-0039-react-trajectory-context-cost.md) | 🔴 困难 |
| 40 | [当“模型即 Agent”越来越强，Harness 工程为什么仍然重要](questions/agent-0040-model-as-agent-harness-engineering.md) | 🟡 进阶 |
| 41 | [如何为 Agent 工具调用设计动态风险评估，而不是只按工具名分级](questions/agent-0041-dynamic-tool-risk-assessment.md) | 🔴 困难 |
| 42 | [Agent 需要人工接管但用户不在线或指令模糊时，系统该怎么设计](questions/agent-0042-human-handoff-when-user-unavailable.md) | 🟡 进阶 |
| 43 | [如何设计既不破坏 KV Cache、又能避免重复工具调用的上下文压缩策略](questions/agent-0043-kv-cache-friendly-context-compression.md) | 🔴 困难 |
| 44 | [Agent 状态栏如何设计，才能增强轨迹管理而不引入新的错误来源？](questions/agent-0044-agent-status-bar-design.md) | 🟡 进阶 |
| 45 | [多人长期维护系统提示词时，如何防止 Prompt 熵增？](questions/agent-0045-system-prompt-entropy-control.md) | 🟡 进阶 |
| 46 | [Skills 渐进式披露依赖模型“知道自己不知道”，这个元认知问题怎么解决](questions/agent-0046-skill-progressive-disclosure-metacognition.md) | 🔴 困难 |
| 47 | [频繁变化的工具集如何布局上下文，才能最大化 Prompt Cache 命中率](questions/agent-0047-tool-context-layout-for-prompt-cache.md) | 🔴 困难 |
| 48 | [用户记忆出现冲突时，Agent 应该覆盖、合并还是追问？](questions/agent-0048-user-memory-conflict-resolution.md) | 🟡 进阶 |
| 49 | [MCP 未来要支持流式输出、双向通信和有状态会话，该怎么扩展？](questions/agent-0049-mcp-streaming-bidirectional-stateful-sessions.md) | 🔴 困难 |
| 50 | [MCP 生态里多个工具功能重叠时，Agent 如何选择正确工具？](questions/agent-0050-overlapping-mcp-tool-selection.md) | 🟡 进阶 |
| 51 | [Agent 对外办事时，应使用虚拟身份还是用户本人身份？](questions/agent-0051-agent-virtual-identity-vs-user-identity.md) | 🔴 困难 |
| 52 | [异步事件堆积时，如何把工具结果、用户消息和系统提醒组织给模型？](questions/agent-0052-async-event-presentation-to-model.md) | 🟡 进阶 |
| 53 | [Agent 自举生成新 Agent 时，如何防止能力退化和错误累积？](questions/agent-0053-agent-bootstrapping-degradation-control.md) | 🔴 困难 |
| 54 | [Agent 能自我更新工具和验证器时，如何隔离不能被它修改的信任根？](questions/agent-0054-self-improving-agent-trust-root-boundary.md) | 🔴 困难 |

<div align="right"><a href="#-ai-面试题库--目录">↑ 返回顶部</a></div>

## 🔍 检索增强生成

<sub>分类 ID：`rag` ｜ 共 41 题</sub>

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
| 38 | [上下文感知检索会放大原文错误时，如何在检索阶段加入信息质量信号](questions/rag-0038-contextual-retrieval-information-quality.md) | 🔴 困难 |
| 39 | [多模态图表转文字后丢失空间关系，RAG 应如何保留视觉结构](questions/rag-0039-multimodal-rag-spatial-structure.md) | 🟡 进阶 |
| 40 | [RAPTOR 和 GraphRAG 分别适合回答什么类型的问题？](questions/rag-0040-raptor-vs-graphrag-query-types.md) | 🟡 进阶 |
| 41 | [文件系统式知识库相比向量数据库 RAG，有哪些优势和边界？](questions/rag-0041-filesystem-knowledge-base-vs-vector-rag.md) | 🟡 进阶 |

<div align="right"><a href="#-ai-面试题库--目录">↑ 返回顶部</a></div>

## ⚙️ 工程化、部署、性能、成本

<sub>分类 ID：`engineering` ｜ 共 15 题</sub>

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
| 9 | [异步 Agent 的事件队列优先级，应该由规则还是 LLM 判断？](questions/engineering-0009-async-agent-event-priority.md) | 🟡 进阶 |
| 10 | [“执行后自动验证”除了写代码跑测试，还能应用在哪些 Agent 工具场景？](questions/engineering-0010-execute-verify-feedback-loop.md) | 🟡 进阶 |
| 11 | [Agent 生成代码并执行时，如何在沙盒安全与能力开放之间取平衡？](questions/engineering-0011-agent-code-execution-sandbox-tradeoff.md) | 🔴 困难 |
| 12 | [Artifact 模式下让浏览器或数据库执行 Agent 生成代码，安全边界怎么设计？](questions/engineering-0012-artifact-generated-code-safety.md) | 🔴 困难 |
| 13 | [LLM-as-a-Judge 有系统性偏差时，如何发现和校准？](questions/engineering-0013-llm-as-judge-bias-calibration.md) | 🟡 进阶 |
| 14 | [Benchmark 数据公开后会被训练污染，如何设计抗泄漏的 Agent 评估？](questions/engineering-0014-agent-benchmark-leakage-resistant-evaluation.md) | 🔴 困难 |
| 15 | [用 LLM 模拟用户评估 Agent 时，如何验证模拟用户本身可靠？](questions/engineering-0015-llm-user-simulator-quality.md) | 🟡 进阶 |

<div align="right"><a href="#-ai-面试题库--目录">↑ 返回顶部</a></div>

## 📦 AI 产品与落地

<sub>分类 ID：`product` ｜ 共 6 题</sub>

| # | 题目 | 难度 |
| :---: | :--- | :---: |
| 1 | [如何判断一个业务场景是否适合引入 AI？](questions/product-0001-ai-scenario-prioritization.md) | 🟡 进阶 |
| 2 | [AI 产品的 PRD 需求应该如何拆解？](questions/product-0002-ai-prd-requirements.md) | 🟡 进阶 |
| 3 | [AI 产品如何设计质量、成本和业务指标？](questions/product-0003-ai-product-metrics.md) | 🟡 进阶 |
| 4 | [AI 产品如何设计不确定性与失败体验？](questions/product-0004-ai-ux-failure-recovery.md) | 🟡 进阶 |
| 5 | [AI 产品如何设计人工介入和风险分级？](questions/product-0005-human-in-the-loop-risk.md) | 🔴 困难 |
| 6 | [AI 产品上线后如何建立评测与迭代闭环？](questions/product-0006-ai-product-iteration-loop.md) | 🔴 困难 |

<div align="right"><a href="#-ai-面试题库--目录">↑ 返回顶部</a></div>

---

<sub>本目录由 `scripts/gen_index.py` 从 `index.json` 自动生成；新增题目后请重跑该脚本以保持同步。</sub>
