---
id: llm-0014
title: 需求应通过 Prompt、RAG、微调还是预训练解决，如何用错误归因选择最小可行方案？
category: llm
tags: [prompt-engineering, rag, fine-tuning, pretraining, evaluation]
difficulty: medium
role: both
contributor: 佚名
source: 洛小山《AI 产品从入门到精通》learn-ai（固定版本见参考）
status: published
updated: 2026-09-15
answers:
  - author: GPT-6
    type: ai
    model: GPT-6
    answered: 2026-09-15
    updated: 2026-09-15
---

## 问题

需求应通过 Prompt、RAG、微调还是预训练解决，如何用错误归因选择最小可行方案？请分别针对最新退款政策、固定输出格式和领域术语，说明最小方案、升级条件及验证方法。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**先判断模型缺的是证据、任务约束，还是可迁移的领域能力，再选能通过验收的最小方案。** Prompt 调整当前输入；RAG 按请求取得外部证据；微调把训练样本中的规律迁移到参数；预训练学习更广泛的语言与领域分布。它们可以组合，不能只按“公司文档多不多”或“想不想拥有自己的模型”决策。

### 1. 四种方案改变什么

| 方案 | 改变的对象与适用条件 | 数据、成本及边界 |
| --- | --- | --- |
| Prompt / Few-shot | 改输入中的指令、上下文和示例；模型已有能力，只是目标、术语或格式没有说清楚 | 少量代表性示例即可做起点，但仍需测试集；每次携带内容占输入预算。单靠角色描述不能获得未提供的最新政策 |
| RAG | 在生成前取得与当前请求相关、可授权访问的证据，并把它送入上下文；适合更新频繁、需要逐条出处的知识 | 要有权威文档、版本和检索评测，不要求先造大量训练问答；有摄取、索引、检索、上下文和维护成本。漏召、旧文档、冲突及错误引用仍会造成错误 |
| 微调（本题主要指 SFT） | 用输入—期望输出样本更新模型或 adapter 参数，改善稳定的分类、抽取、表达和指令遵循行为 | 要有足够覆盖真实分布且标注一致的数据，付出清洗、标注、训练、回归和部署成本；可能减少长提示开销，也可能过拟合、遗忘或学错。不是可逐条更新、撤销并引用的事实数据库 |
| 预训练 / 继续预训练 | 从随机初始化学习基础能力，或在已有 checkpoint 上以语言建模目标继续适配领域分布；后者包括 domain-adaptive pretraining（DAPT） | 需要足够的高质量领域语料及训练评估能力；原始文本不等于指令样本。继续预训练后可能仍需 SFT 才能完成目标任务。从零训练还要论证现成底座不能满足的语言、架构或部署需求 |

这里的“Prompt 不训练参数”指普通推理时的文本提示；不包括 soft prompt / prompt tuning 等可训练方法。常见应用 RAG 可以冻结生成模型，但 **RAG 是架构选择，不是“绝不训练”的定义**：原始 RAG 论文就包含联合适配检索与生成的训练方案。训练与对话内学习边界见 [llm-0008](llm-0008-next-token-training-inference.md)，SFT 与对话形式的关系见 [llm-0009](llm-0009-base-chat-template-sft.md)。

**知识更新与行为迁移是两条轴，不是互斥标签。** 微调能学习事实和术语；问题是学习的可靠性、泛化、更新时效与可追溯性。Gekhman 等人的受控 closed-book QA 研究发现，新知识样本学得更慢，最终学会时还可能增加幻觉风险；这支持谨慎验证，不能推出“微调绝不学习知识”。相反，即便 RAG 提供了正确证据，模型仍可能误读规则或生成无依据内容。

### 2. 从错误样本出发，而不是固定走一遍技术阶梯

先把失败输出与业务真值放在一起，保存模型版本、提示、可见证据和输出，按以下顺序诊断：

1. **验收定义是否明确？** 区分字段格式、业务结论、引用和拒答；标注本身冲突时先修规则与数据。确定性资格判断可以交规则引擎，模型只做信息提取和解释。
2. **输入里有没有正确且适用的证据？** 在离线诊断中，把人工核准的证据替换进原上下文，保持模型和任务要求不变。若明显改善，优先修证据取得、版本过滤或上下文组织；这次人工供证不能计入线上 RAG 成绩。
3. **正确证据已经在场，错在格式还是业务语义？** 格式先尝试明确 schema、少量示例和受支持的约束输出；语义错误则检查规则歧义、示例覆盖、证据使用和底座能力。不能看到一条失败就认定“必须训练”。
4. **问题是否稳定、反复出现且有可用训练数据？** 在 Prompt 基线之外，试小规模 SFT 与合适底座的对照；若是广泛领域语言分布差异，再评估继续预训练。加数据是否有效要看独立测试的学习曲线，不是预设“几千条就够”。

因此，输出格式失败并不需要先搭 RAG，更新一条短政策也不必先造向量库：从受控政策源直接读取全文并放入 Prompt 就可能够用。文档规模、权限、版本或检索需求增长时再引入相应检索能力。已有流程细节见 [rag-0023](rag-0023-rag-pipeline-full-flow.md)；检索与生成的归因实验见 [rag-0033](rag-0033-retrieval-vs-generation-attribution.md)。

### 3. 三类需求的配套选择

以下全部是自编业务设定，不代表真实公司的退款政策或行业术语。日期、天数和版本号仅用于可复核案例。

| 需求与输入 | 错误归因及最小可行方案 | 升级条件与验证方法 |
| --- | --- | --- |
| **最新退款政策**：本例规定按申请日期选政策；P1 在 2026-01-01 至 2026-09-01 前允许未拆封且收货后不超过 7 天退款，P2 自 2026-09-01 起改为不超过 14 天。申请日 2026-09-15，已收货 10 天、未拆封 | 人工错误候选仍按 P1 拒退。先读取权威有效版本，把 P2 提供给模型或规则引擎；预期 `REFUND`、引用 `P2`。只取得失效 P1 时应补检索或转人工，不凭旧记忆拒退 | 多地区、商品或权限维度下无法直接取唯一政策时，建设带适用范围与版本控制的 RAG。分别量测有效证据召回、政策适用正确率、结论和引用正确率；测试生效日两侧、14/15 天、缺失证据和冲突文档 |
| **固定输出格式**：消费者只接受 `action` 和 `policy_id`；输入仍是上述退款 case | `结果：{...}` 属于协议问题。先声明字段与允许值、给合法示例；支持时采用 Structured Outputs / constrained decoding，并处理拒答、截断及业务校验。预期 `{"action":"REFUND","policy_id":"P2"}` | 若结构已稳定但分类映射、抽取或指令行为仍系统性失败，且有代表性输入—输出样本，可试 SFT。格式通过率与业务正确率分别计分；schema 合法的 `DENY/P1` 仍然是错的，不能据此宣称问题已解决 |
| **领域术语**：本例企业词表把售后部门 `RMA` 定义为“退货授权编号”，风控部门定义为“风险模型评估”；请求“解释 RMA”，部门可能缺失 | 通用展开可能套错语境。先传部门与小词表，必要时检索权威术语条目；售后上下文预期“退货授权编号”，风控预期“风险模型评估”。没有部门且存在歧义时先澄清 | 若词表充分但未见文本上的实体抽取或语义映射仍差，可试任务 SFT；若多种领域任务均因语言分布差异受限且有足够原始语料，再试 DAPT。留出文档/实体，测试缩写歧义、否定、罕见术语和通用任务回归，不能只复测训练词条 |

这些方案可以相加。例如 **SFT 学习“如何使用证据和输出字段”，RAG 提供“这次生效的政策”**，格式约束保证可解析，规则引擎判断退款资格。训练样本要覆盖证据不足和冲突时的行为；推理时仍要提供当前证据。把最新政策问答塞入 SFT 后移除检索，并不能保证下次政策变动自动生效。

“领域术语”也不直接等于“需要预训练”。少量确定的定义更适合词表或检索；专业长文本中的隐含关系可能需要任务示例或模型适配。Gururangan 等人在特定领域分类任务上观察到继续预训练收益，这提供了候选路径，不能保证任意现代聊天模型或任何领域推理任务都受益。LoRA 只是降低部分训练开销的方法，原理见 [llm-0001](llm-0001-lora-fine-tuning.md)，不改变上述选型标准。

### 4. 实际运行：验证真值与校验层的边界

下面用 Python 标准库验证三类案例。**输入政策、词表和候选字符串均为人工构造；没有调用模型、训练模型或实现检索系统。** `oracle` 是本例评测器的真值函数，`parse_shape` 只是本文两个字段的严格校验器，不是通用 JSON Schema 实现。它们的结果不能证明 Prompt、RAG 或微调的实际收益。

计算假设：生效区间左闭右开；`days` 是调用方已核实的非负整数天数；`unopened` 是已知布尔值。示例只处理表中简化政策，不含地区、品类、质量问题或其它例外。提供的政策记录已由业务人员核准；无有效版本或同时命中多个版本时转人工。词表查询使用已归一化的部门、术语字符串，不做模糊匹配。

```python
from datetime import date
import json

# 人工政策：生效区间左闭右开；None 表示没有结束日期。
POLICIES = [
    ("P1", date(2026, 1, 1), date(2026, 9, 1), 7),
    ("P2", date(2026, 9, 1), None, 14),
]

def oracle(as_of, days, unopened, policies=POLICIES):
    fallback = {"action": "ESCALATE", "policy_id": None}
    if (type(as_of) is not date or type(days) is not int
            or days < 0 or type(unopened) is not bool):
        return fallback
    active = [p for p in policies
              if p[1] <= as_of and (p[2] is None or as_of < p[2])]
    if len(active) != 1:
        return fallback
    pid, _, _, limit = active[0]
    action = "REFUND" if unopened and days <= limit else "DENY"
    return {"action": action, "policy_id": pid}

def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate key")
        obj[key] = value
    return obj

def reject_constant(value):
    raise ValueError(value)

def parse_shape(raw):
    try:
        obj = json.loads(raw, object_pairs_hook=unique_object,
                         parse_constant=reject_constant)
    except (ValueError, TypeError):
        return None
    if (type(obj) is not dict or set(obj) != {"action", "policy_id"}
            or obj["action"] not in ("REFUND", "DENY", "ESCALATE")
            or not (obj["policy_id"] is None or type(obj["policy_id"]) is str)):
        return None
    return obj

GLOSSARY = {("售后", "RMA"): "退货授权编号", ("风控", "RMA"): "风险模型评估"}

def term_lookup(team, term):
    return GLOSSARY.get((team, term), "CLARIFY")

today = date(2026, 9, 15)
gold = oracle(today, 10, True)
print("current:", gold)
print("stale_only:", oracle(today, 10, True, POLICIES[:1]))
samples = [
    ("extra_text", '结果：{"action":"REFUND","policy_id":"P2"}'),
    ("wrong_fact", '{"action":"DENY","policy_id":"P1"}'),
    ("correct", '{"action":"REFUND","policy_id":"P2"}'),
]
for name, raw in samples:
    parsed = parse_shape(raw)
    print(f"{name}: shape={parsed is not None}, fact={parsed == gold}")
print("terms:", term_lookup("售后", "RMA"), term_lookup("风控", "RMA"),
      term_lookup(None, "RMA"))
```

**真实运行 stdout：2026-09-15，macOS arm64，Python 3.11.8。**

```text
current: {'action': 'REFUND', 'policy_id': 'P2'}
stale_only: {'action': 'ESCALATE', 'policy_id': None}
extra_text: shape=False, fact=False
wrong_fact: shape=True, fact=False
correct: shape=True, fact=True
terms: 退货授权编号 风险模型评估 CLARIFY
```

`wrong_fact` 有正确的字段和类型，却使用了错误政策并给出错误结论。这里的 `fact` 只比较动作和政策编号，不评估自然语言解释是否忠实，也不验证原始政策是否真实；正式产品还需核验引用内容和业务输入。`stale_only` 是校验层拒绝过期证据的结果，不是声称模型会自行识别一切时效问题。格式机制及后端处理可继续读 [agent-0021](agent-0021-structured-json-output.md)。

### 5. 何时值得升级：质量和全生命周期成本一起比较

先建立按三类需求分层的独立测试集，真值由政策负责人或领域专家制定，测试答案不进入 prompt 示例或训练集。模型臂可以接收完成任务所需的政策和术语证据，**不能接收评测器给出的目标答案**。按文档、实体、用户和时间去重切分，尤其保留新政策生效后的测试与旧版本冲突案例。

对同一组请求配对比较：Prompt 基线、Prompt 加正确证据、线上检索证据、SFT 加相同证据；只有诊断支持时才增加 DAPT 臂。固定任务、测试集、输出协议、基础 checkpoint（可固定时）、采样设置和请求预算，并记录训练数据版本、检索快照、证据长度和失败处理。替换了模型家族或同时修改检索时，应报告为系统选型比较，不能把全部提升归因于微调。随机生成需预先约定重复次数及聚合规则。

至少分别报告业务正确率、格式通过率、证据/引用正确率、缺证据时的合理转人工率，以及每个完成请求的总费用、延迟分位数与人工处置量。超时、拒答、格式失败和重试都计入，避免只看成功解析的子集；转人工也不能拿来虚增“正确回答率”。各方法在开发集达到预先约定的质量门槛后，在未用于调参的测试集确认收益、置信区间和通用能力回归，再决定上线。

在同一评估周期与货币单位下，可用 `总成本 = 数据准备 + 索引/训练 + 验证/部署/维护 + 请求量 × 平均每请求运行成本` 比较候选。运行成本应覆盖检索、输入输出、重试和相关人工处理；更新频率决定索引或再训练开销。微调可能减少长提示，却增加训练与版本维护成本；RAG 增加查询链路，却可能降低知识更新代价。实际收费和缓存规则按所选服务核实，本题不采用课程中固定的报价或“多数需求”的比例作为结论。

数据量也不能跨方法直接比“条数”：RAG 看知识覆盖与可检索性，SFT 看输入—输出分布与标签一致性，DAPT 看去重后的领域文本覆盖和训练预算。用逐步扩大的开发训练集画学习曲线，确认边际收益；若标签冲突、覆盖不足或底座不合适，重复样本和更长训练未必有用。

## 延伸 / 追问

**追问 1：有 RAG 了，为什么还可能需要微调？**

正确证据进入上下文后，模型仍可能抽取错字段、忽略规则优先级或不会规范引用。可先改指令与示例，再用包含当前证据、期望输出和缺证据案例的 SFT 数据改善行为；必须与同证据下的基线对照。若检索没有召回适用政策，训练生成端通常不是第一修复点。

**追问 2：微调模型能背出新政策，为什么不能直接替代知识库？**

能背出一个训练事实不等于能可靠覆盖未见问法、撤销旧政策或证明出处。低更新频率、无需逐条溯源的封闭任务可以实测参数化方案，但要检查冲突、遗忘和更新成本；频繁变更且要求引用的事实更适合由受控外部源提供。两者仍可组合。

**追问 3：术语词表补齐后仍不懂领域文本，就应该从零预训练吗？**

先区分术语缺失、任务标注问题和广泛领域分布差异，比较合适底座、任务 SFT 和继续预训练。只有已有底座无法满足关键约束、数据与计算预算可支撑且有清楚验收时，才论证从零预训练；它不是 SFT 失败后的自动下一步。

## 常见误区

- **“微调只改风格，绝不学习知识。”** 微调会更新参数，也能学习事实；学习稳定性与维护代价需要验证。
- **“加了 RAG 必然消除幻觉。”** 检索可能过期或漏召，生成也可能曲解正确证据；引用存在不等于引用支持结论。
- **“必须依次完成 Prompt → RAG → 微调 → 预训练。”** 这是不同作用点，不是通用升级阶梯；错误归因决定该补哪一层。
- **“JSON 合法就算业务正确，领域术语多就必须训练。”** 前者混淆结构与语义，后者忽略词表、检索和任务特征；本题示例直接展示了两种边界。

## 参考

- 课程学习线索：洛小山《AI 产品从入门到精通》[learn-ai](https://github.com/itshen/learn-ai/tree/5a933d287dd5074cc1543cb849146f3261d47521)，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`；具体路径：[slides/zero-q-finetune-vs-rag.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/zero-q-finetune-vs-rag.html)、[slides/zero-q-train-or-prompt.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/zero-q-train-or-prompt.html)、[slides/1-2-sft.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/1-2-sft.html)、[slides/1-2-mitigation-rag.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/1-2-mitigation-rag.html)。本题独立组织论证、表格和代码，未搬运 AGPL 课件正文、代码或图片；课程中的价格、耗时和普遍效果未作为事实依据。
- OpenAI，[Model optimization](https://developers.openai.com/api/docs/guides/model-optimization)、[Supervised fine-tuning](https://developers.openai.com/api/docs/guides/supervised-fine-tuning)：eval 优先、提示与训练迭代及行为适配的一手文档。访问日期 **2026-09-15**；当日页面已说明其 fine-tuning 平台正在收尾且不向新用户开放，本文引用方法论，不承诺该平台当前账户可用性。
- OpenAI，[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)：支持的 schema、拒答/截断路径和结构正确仍可能含语义错误的边界；访问日期 **2026-09-15**。本文未调用该 API。
- Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, NeurIPS 2020，[arXiv:2005.11401v4](https://arxiv.org/abs/2005.11401v4)，参数与非参数记忆结合及原始训练方案；论文中的特定任务结果不是任何 RAG 应用的准确率保证。
- Gekhman et al., *Does Fine-Tuning LLMs on New Knowledge Encourage Hallucinations?*, 2024，[arXiv:2405.05904v1](https://arxiv.org/abs/2405.05904v1)，受控 closed-book QA 中新知识学习与幻觉风险；这里引用该固定版本，不外推为所有模型和训练配方的定律。
- Gururangan et al., *Don't Stop Pretraining: Adapt Language Models to Domains and Tasks*, ACL 2020，[正式论文 2020.acl-main.740](https://aclanthology.org/2020.acl-main.740/)，DAPT / TAPT 的一手依据，研究覆盖四个领域、八个分类任务。以上论文链接核实日期 **2026-09-15**。
