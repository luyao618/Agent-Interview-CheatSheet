---
id: llm-0015
title: 知识蒸馏如何把教师模型能力迁移给学生，与量化、普通微调有何不同？
category: llm
tags: [knowledge-distillation, teacher-student, soft-targets, fine-tuning, evaluation]
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

知识蒸馏如何把教师模型能力迁移给学生，与量化、普通微调有何不同？请设计一个领域蒸馏训练与独立保留集评估流程，说明怎样发现能力损失和教师偏差的传递。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**知识蒸馏用教师模型产生的监督信号训练学生，让学生在目标任务上学到教师的输出规律。** 信号可以是类别或 token 的概率分布，也可以是教师生成并经过校验的答案。训练更新的是学生参数；教师通常固定。迁移的效果取决于教师在该领域的质量、数据覆盖、学生容量和训练方法，不是把一个模型的全部能力装进另一个模型。

蒸馏不是复制参数，学生也不必与教师架构相同。它经常用于训练更易部署的小模型，也能把多个教师的集成行为压到一个学生；“一定更小”不是监督关系的定义。学生可以从已有 checkpoint 开始训练，无须从随机参数重新学习语言。

### 1. 蒸馏、量化和普通微调不是同一维度

| 方法 | 改变什么 | 适用条件与代价 |
| --- | --- | --- |
| 知识蒸馏 | 将教师的分布、标签或生成序列作为学生训练目标；学生参数通过优化更新 | 教师在目标分布上有值得学习的行为，且学生可承载任务；增加教师推理、标签审核与训练开销，可能传递错误或丢失长尾能力 |
| 量化 | 用较低精度表示权重、激活等数值；通常不以复制教师行为为目标，也不必减少参数个数 | 想降低存储或利用低精度硬件时可考虑；有量化误差及算子支持限制，内存变小不等于任意硬件上都更快。PTQ 在训练后转换，QAT 则把量化影响纳入训练 |
| 普通监督微调（SFT） | 用输入—期望输出样本训练已有模型，监督通常来自人工或已验证任务数据 | 有稳定任务及代表性标注时可用；仍有标注、训练和回归成本，不一定涉及另一个模型 |

**蒸馏可以通过 SFT 实现。** 用教师回答组成数据集，再训练学生生成这些回答，就是一种生成数据蒸馏；它与“普通 SFT”的训练代码可能相同，区别主要在监督来源与质量控制。采用 LoRA 只是选择了参数更新方式，不自动构成蒸馏，见 [llm-0001](llm-0001-lora-fine-tuning.md)。量化与蒸馏也可以先后组合，但需要分别测量量化前后的质量与部署性能。

若瓶颈只是动态知识缺失，优先检查证据取得，而不是立即蒸馏，选型边界见 [llm-0014](llm-0014-prompt-rag-finetuning-choice.md)。若现有小模型已经满足质量要求，直接优化推理或量化可能比造教师数据更划算；开放范围广、教师本身不可靠或错误代价无法容忍时，蒸馏也可能不适合。

### 2. 两种常见监督路线

**软目标蒸馏**让学生匹配教师对多个候选的概率分配。例如教师认为三个路由类别的概率是某个非 one-hot 分布，除了首选标签，其他类别的相对概率也可能提供有用信号；这些概率反映模型行为，不是客观真值或可见的内部思考过程。

设教师和学生在同一输入上输出对齐的类别 logits，温度 `T > 0`，一条样本的常见损失写为：

```text
p^(T) = softmax(z_teacher / T)
q^(T) = softmax(z_student / T)
L = (1 - α) × CE(y, q^(1)) + α × T² × KL(p^(T) || q^(T))
KL(p || q) = Σ_i p_i × log(p_i / q_i)，0 ≤ α ≤ 1
```

`y` 是独立核验的硬标签，硬标签项在 `T=1` 计算；教师分布作为常量，梯度只更新学生。没有可靠硬标签时可只使用教师项，但失去了一条纠错来源。对固定教师分布，软交叉熵和此方向的 KL 只差教师熵，对学生的梯度相同；它们的数值不是同一个量。

Hinton 等人的原论文用提高温度暴露非首选类别间的关系，并用 `T²` 补偿软目标梯度随温度升高而缩小的尺度，尤其可从高温近似理解。**这不是不同温度下损失或梯度严格不变的保证。** 温度太高会让分布接近均匀，太低会接近硬标签；`T` 和 `α` 要在开发集上选择，不能把解码时的低温或高温效果直接当作蒸馏结论。

对自回归 LLM，逐 token KL 还需要说明：教师和学生看什么前缀、哪些目标位置参与 loss、padding 如何屏蔽，以及按 token 还是按序列平均。**同一个 token 下标必须代表同一个事件。** 不同 tokenizer 或词表不能直接逐下标算 KL；只有 API 返回少量 top-logprobs 时，也不能冒充已取得全词表分布，须处理剩余概率质量或改用其他路线。

**生成数据 / 序列级蒸馏**让教师生成答案，再把经过筛选的输入—答案对交给学生做监督训练。Kim 与 Rush 的序列蒸馏工作在机器翻译中用教师搜索得到的序列作为训练目标。这条路线不要求访问教师内部权重或全量 logits，也能在教师、学生 tokenizer 不同时，把教师文本重新用学生 tokenizer 编码。

只提供最终答案也可以蒸馏；不能要求“必须保留完整隐藏推理才有效”。任务需要时可使用可公开、可验证的解题示范、规则依据或工具结果，但它们不是取得模型隐藏推理的前提，也不保证解释越长越有效。相较完整软分布，单条生成序列丢失了部分候选信息，教师的搜索和采样偏好也会进入数据。

### 3. 领域训练流程：先保留评估数据，再生成监督

以**客服工单路由**为自编领域任务。输出只允许一个标签：`D` 表示物流查询，`R` 表示退款受理，`E` 表示转人工。规则优先级为：安全异常、身份未确认或诉求冲突先转人工；其他情况下，明确退款申请分到 R，仅查物流分到 D；信息不足也转人工。**R 只表示交给退款流程受理，不表示已经获得退款资格。** 规则足够确定时可直接实现业务路由；这里用它建立学生模型评估的独立真值。

1. **定义范围与基线。** 输入为脱敏工单、必要订单状态和规则版本，输出为 D/R/E。先检查教师、现有学生 checkpoint 和规则方案的错误；冻结拟使用的教师/学生版本、输入上下文和输出协议。记录数据与教师输出的使用授权。
2. **按来源分组后拆分。** 在教师标注之前，按原始订单、会话和近重复文本组划分 train、dev、test；同一工单的改写不能跨集合。dev 用于调参，test 独立保留；补充未见实体、后续时间段与安全异常等难例，避免随机逐句切分造成泄漏。
3. **只为训练输入构造训练监督。** 给教师提供相同业务规则，保存请求、证据、教师版本、采样设置及输出来源。校验合法标签、规则一致性和敏感样本，由业务人员抽查并修正。不能只保留教师最自信或最容易的样本，否则可能删掉本来就稀少的 E 类；教师与规则冲突时应核查，而不是把教师回答强行当真值。
4. **从同一学生底座训练对照组。** 比较人工监督 SFT、教师监督蒸馏、人工与教师混合监督；能取得对齐 logits 时再加入软目标方案。在同输入集合、相同上下文和可比训练预算下比较监督来源；额外合成数据的规模实验单独报告，不能把数据量增长全部归因于蒸馏损失。记录训练 token、epoch、loss 归约、优化器、随机种子及 checkpoint；只用 dev 选择配置和停止点。
5. **冻结配置后评估独立 test。** 由未依赖教师候选的业务标注生成 gold；教师可作为被测系统在 test 上作答，但其答案不进入训练或充当评分标准。对教师、原学生、人工 SFT 与蒸馏学生使用同样的输入和解码预算，分别统计任务准确率、各类召回/混淆、格式失败、E 类漏转人工以及真实延迟、内存和单请求总成本。无效输出或超时仍进入分母；E 类路由正确不代表人工处理已经成功。
6. **按质量约束决定交付。** 上线门槛先在业务/开发阶段约定，关键风险指标不能被平均准确率掩盖。对真实实验报告多次训练和按来源组配对评估的不确定性，并检查域外、长上下文与新规则回归。测试不通过就返回训练/dev 排查，反复据同一 test 调参会把它变成开发集；后续版本要保留新的独立验证。

这套流程不会证明学生完整继承教师。学生可能保留常见短问题的能力，却丢失罕见术语、多步规则或长上下文能力；也可能在特定领域依靠更合适的数据与人工纠错超过教师，因此教师成绩既不是普遍可达目标，也不是所有任务上不可超越的硬上限。SFT 与后续 RL 的选择是另一个问题，见 [llm-0005](llm-0005-agent-training-sft-to-rl-switch.md)。

### 4. 人工保留集：一致率不能替代正确率

下面八条输入分别视为不同来源组，**仅用于展示保留集评估规则，未被用来训练任何模型**。gold 按上述路由规则人工制定；“教师”“原学生”“蒸馏学生”三列都是人为指定的候选标签，不是训练或推理实测。真实实验不得把这些候选列提供给待测模型。

| ID / 输入 | gold | 教师候选 | 原学生候选 | 蒸馏学生候选 |
| --- | --- | --- | --- | --- |
| T01：订单信息齐全，只查询运输进度 | D | D | D | D |
| T02：身份已确认，明确申请退款，无安全异常 | R | R | D | R |
| T03：申请退款，同时报告电池冒烟 | E | R | E | R |
| T04：申请退款，但尚未确认订单归属 | E | E | E | E |
| T05：身份清楚，包裹未到，只询问进度 | D | D | R | D |
| T06：订单与身份清楚，仅请求办理退款 | R | R | R | R |
| T07：同一工单诉求相互矛盾，尚未澄清 | E | E | E | R |
| T08：身份清楚，物流问题已解决，现仅申请退款 | R | R | R | R |

这组人工数据特意包含“学生跟着教师在 T03 犯错”和“学生还会额外漏掉 T07”。它是反例设计，不是蒸馏必然退化的经验证据。

### 5. 实际运行的损失与评分算例

下面的 logits 是单条**人工训练样本**的设定，类别顺序为 D/R/E，硬标签 D；它与上表候选没有训练关系。计算使用自然对数，CE/KL 的口径为单样本、单位为 nat，混合项按给定权重缩放。`T=2`、`α=0.5` 仅供演示。评分函数接收已解析的标签字符串或 `None`，非法输出算错；没有 E 类时其召回返回 `None`，不伪造满分。

```python
import math

def log_probs(logits, temperature):
    if (not math.isfinite(temperature) or temperature <= 0 or not logits
            or not all(math.isfinite(z) for z in logits)):
        raise ValueError("finite logits and positive temperature required")
    scaled = [z / temperature for z in logits]
    if not all(math.isfinite(z) for z in scaled):
        raise ValueError("scaled logits overflow")
    top = max(scaled)
    shifted = [z - top for z in scaled]
    if not all(math.isfinite(z) for z in shifted):
        raise ValueError("logit range overflow")
    normalizer = math.log(sum(math.exp(z) for z in shifted))
    return [z - normalizer for z in shifted]

def kd_loss(teacher_logits, student_logits, gold_index, temperature, alpha):
    if (len(teacher_logits) != len(student_logits)
            or type(gold_index) is not int
            or not 0 <= gold_index < len(student_logits)
            or not 0 <= alpha <= 1):
        raise ValueError("aligned classes, valid gold and alpha required")
    teacher_logp = log_probs(teacher_logits, temperature)
    student_logp = log_probs(student_logits, temperature)
    kl = sum(math.exp(p) * (p - q) for p, q in zip(teacher_logp, student_logp))
    hard_ce = -log_probs(student_logits, 1.0)[gold_index]
    total = (1 - alpha) * hard_ce + alpha * temperature**2 * kl
    return kl, hard_ce, total

# 人工训练样本的三类 logits；与下方保留集候选无训练关系。
teacher_logits, student_logits = [2.0, 1.0, 0.0], [0.0, 1.0, 2.0]
for temperature in (1.0, 2.0):
    probs = [math.exp(x) for x in log_probs(teacher_logits, temperature)]
    print(f"teacher T={temperature:g}:", [round(x, 6) for x in probs])
kl, ce, loss = kd_loss(teacher_logits, student_logits, 0, 2.0, 0.5)
print(f"KL={kl:.6f}, hard_CE={ce:.6f}, mixed_loss={loss:.6f}")

LABELS = {"D", "R", "E"}

def score(pred, gold, teacher):
    if (not gold or len(pred) != len(gold) or len(teacher) != len(gold)
            or any(g not in LABELS for g in gold)):
        raise ValueError("nonempty aligned records and valid gold required")
    n = len(gold)
    correct = sum(p == g for p, g in zip(pred, gold)) / n
    agree = sum(p in LABELS and p == t for p, t in zip(pred, teacher)) / n
    critical = [p == "E" for p, g in zip(pred, gold) if g == "E"]
    recall = sum(critical) / len(critical) if critical else None
    return correct, agree, recall

# 固定人工候选，非模型推理结果；D=物流，R=退款受理，E=转人工。
gold = ["D", "R", "E", "E", "D", "R", "E", "R"]
teacher = ["D", "R", "R", "E", "D", "R", "E", "R"]
baseline = ["D", "D", "E", "E", "R", "R", "E", "R"]
student = ["D", "R", "R", "E", "D", "R", "R", "R"]
for name, pred in (("teacher", teacher), ("baseline", baseline), ("student", student)):
    accuracy, agreement, recall = score(pred, gold, teacher)
    print(f"{name}: accuracy={accuracy:.3f}, agreement={agreement:.3f}, E_recall={recall:.3f}")
```

**真实运行 stdout：2026-09-15，macOS arm64，Python 3.11.8。仅执行人工输入的数值计算，未训练或调用模型。**

```text
teacher T=1: [0.665241, 0.244728, 0.090031]
teacher T=2: [0.50648, 0.307196, 0.186324]
KL=0.320157, hard_CE=2.407606, mixed_loss=1.844116
teacher: accuracy=0.875, agreement=1.000, E_recall=0.667
baseline: accuracy=0.750, agreement=0.625, E_recall=1.000
student: accuracy=0.750, agreement=0.875, E_recall=0.333
```

教师自身一致率为 1，但准确率只有 `7/8`。人工学生候选与教师的一致率从 `5/8` 变成 `7/8`，准确率仍是 `6/8`，E 类召回却从 `3/3` 降为 `1/3`。若本任务预先规定“不可增加关键场景漏转人工”，这个候选不能通过，即使它更像教师；八条样本也不足以证明实际质量或统计显著性。损失计算同样没有证明真实模型收敛，更不能推出部署速度或费用改善。

### 6. 能力与偏差传递的取舍

教师错标、过度自信、不当拒答、身份模板或某些人群/表达方式的覆盖偏差，都可能进入学生监督；学生容量和优化误差还可能产生教师没有的新错误。**偏差传递是需要控制的风险，不是所有缺陷必然完整复制的定律。** 人工标签、规则校验、数据平衡和针对失败类别的补样可以降低风险，仍要在独立数据上测量。

只用教师给学生打分容易奖励相同错误；多个同源教师投票也不自动独立。应记录来源并用独立任务真值、可执行规则或校准后的人工评价检查，必要时报告错误相关性。教师的置信度、师生一致率和训练 loss 都不能替代业务正确率。

部署收益需包含全生命周期：教师生成与筛选、学生训练、回归评估、再训练和运行成本。目标硬件、批量、上下文长度及延迟分位数相同或明确可比后，才能讨论是否更快、更便宜；学生需要更多重试或频繁回退到教师时，节省可能被抵消。新政策与工具协议变化后也要重新验证，不把一次蒸馏当成持续更新机制。

## 延伸 / 追问

**追问 1：教师 API 没有 logits，还能蒸馏吗？**

可以用教师生成的可用答案形成监督数据，让学生做序列训练；质量检查和数据覆盖仍不可省。不同 tokenizer 时可重新编码文本。若要做逐 token 分布匹配，则需解决完整概率与语义对齐，不能把几个 top-logprobs 直接当全分布。

**追问 2：学生训练 loss 很低，而且与教师高度一致，为什么仍不敢上线？**

它可能只学会训练集或教师的系统性错误；教师在目标业务上也可能有缺陷。应看独立保留集、关键类别漏判、域外回归和部署指标，本题人工候选就是“一致率提高但转人工召回下降”的反例。

**追问 3：先量化还是先蒸馏？**

取决于瓶颈和预算。若原模型质量已够、主要受内存限制，可先验证量化；若需要更小学生承接特定能力，可先蒸馏，再单独检查量化增量损失。组合方案最终仍须在目标运行环境复测，不能直接相乘两个宣传中的收益。

## 常见误区

- **“蒸馏就是复制或截取教师参数，架构必须相同。”** 核心是教师监督学生训练；不同架构可通过对齐任务输出迁移，特征级蒸馏另需对齐设计。
- **“只给最终答案不算蒸馏，必须取得完整隐藏推理。”** 生成答案监督本身就是可行路线，是否加入公开中间示范由任务和验证决定。
- **“越蒸馏越可靠，学生自动拥有教师全部能力。”** 学生可能丢失能力、继承或新增错误；连续蒸馏还需检查覆盖和偏差，不能默认持续改进。
- **“量化不能涉及训练，SFT 与蒸馏互斥。”** QAT 涉及训练，生成数据蒸馏也常用 SFT；它们分别描述数值表示、监督来源和训练方法。

## 参考

- 课程学习线索：洛小山《AI 产品从入门到精通》[learn-ai](https://github.com/itshen/learn-ai/tree/5a933d287dd5074cc1543cb849146f3261d47521)，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`；具体路径：[slides/oss-5.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/oss-5.html)、[slides/oss-6.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/oss-6.html)、[slides/oss-7.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/oss-7.html)。本文独立组织题干、答案、表格和代码，未搬运 AGPL 课件正文、代码或图片；未采用课程通用成本倍数、模型评测数字和“必须完整推理”的判断。
- Hinton, Vinyals & Dean, *Distilling the Knowledge in a Neural Network*, 2015，[arXiv:1503.02531v1](https://arxiv.org/abs/1503.02531v1)，尤其 §2：软目标、同温度匹配、硬标签混合与 `T²` 补偿；原论文分类/语音实验不构成现代 LLM 的收益保证。
- Kim & Rush, *Sequence-Level Knowledge Distillation*, EMNLP 2016，[ACL Anthology D16-1139](https://aclanthology.org/D16-1139/)，§3 的 word-level 与 sequence-level 蒸馏；机器翻译中的教师生成序列是一手实例，不要求把其搜索策略当成所有任务的最优方案。
- Jacob et al., *Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference*, CVPR 2018，[正式论文与摘要](https://openaccess.thecvf.com/content_cvpr_2018/html/Jacob_Quantization_and_Training_CVPR_2018_paper.html)：量化表示及配套训练的一手依据；图像模型上的性能结果不能直接移用到 LLM 部署。以上一手链接核实日期 **2026-09-15**。
