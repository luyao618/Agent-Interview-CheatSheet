---
id: llm-0013
title: Few-shot、Chain-of-Thought、Self-Consistency 与 Think Tool 分别何时有用，怎样验证额外推理值得？
category: llm
tags: [few-shot, chain-of-thought, self-consistency, think-tool, evaluation]
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

Few-shot、Chain-of-Thought、Self-Consistency 与 Think Tool 分别何时有用，怎样验证额外推理值得？请用同一业务规则题比较直接回答、示例提示与多样本投票，明确真值、聚合规则和质量—成本对照。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**Few-shot 提供示范，CoT 帮助分解求解，Self-Consistency 聚合多个样本，Think Tool 在工具流程中提供一次整理信息的机会。** 它们改变上下文、推理过程或推理时的计算分配，不等于重新训练权重，也不能保证答案正确。是否值得，应由同一批任务上的真实质量提升、延迟和总成本决定，而不是解释长度或投票一致率。

### 1. 四种方法分别解决什么问题

| 方法 | 机制与适用条件 | 代价与不适用场景 |
| --- | --- | --- |
| Few-shot | 在上下文中给输入—输出示例，让模型识别格式、映射、规则例外；适合仅靠说明仍有歧义的任务 | 占输入预算，错误或偏斜示例会带偏结果；简单且已有可靠格式约束的任务不一定需要更多示例 |
| Chain-of-Thought（CoT） | 原论文用中间求解步骤示范引导复杂算术、规则组合等任务；工程中可用任务检查项或受支持的原生推理能力帮助分解 | 更长的生成和推理可能增加延迟，也可能放大错误前提；简单查表、精确计算应优先使用可靠代码或工具 |
| Self-Consistency | 从同一任务采样多个可能的求解结果，将可比较的最终答案归一化后聚合，降低单次偶然错误的影响 | 多次调用付出更多成本；同模型的系统性偏差可能反复出现，无法靠多数票修正共享的错误规则或缺失资料 |
| Think Tool | 在较长工具链中插入整理已知事实、缺失项和规则约束的步骤，再继续行动 | 工具本身不提供新事实，不替代验证器；会增加上下文、日志和调用开销，简单任务可能只是多绕一圈 |

Few-shot 是 in-context learning 的一种方式：示例改变条件输入，通常不更新参数，边界见 [llm-0008](llm-0008-next-token-training-inference.md)。CoT 论文中的公开求解示范，也不能等同于某个模型的私有隐藏推理。**不要把更长的解释当成更正确，也不要求展示模型隐藏推理。** 对产品输出可以要求结论、命中的规则编号、引用证据和缺失字段；这些是可核验的决策记录，不是索取完整内部思考轨迹。

Self-Consistency 的重点是多样性与聚合，而非把同一条结果复制多份。原论文结合 CoT 采样多个求解输出并选择一致答案；生产系统可以只聚合可见的最终答案，不需要提取隐藏推理。各次请求应避免看到其他候选答案，但**采样过程独立不等于错误统计上独立**：相同权重、提示或知识缺口仍会使样本一起犯错。

### 2. Think Tool 的作用与时效边界

Anthropic 2025-03-20 的官方文章讨论了在复杂工具调用中加入 `think` 步骤的做法：工具不查询外部信息、不改变业务数据库，而是让模型有一个整理当前情况的空间。它仍然可能把内容写入日志或对话上下文，所以不能叫作“任何状态都不变”或“零成本”。工具执行器的业务权限也不会因出现一个 think 步骤而自动更安全。

**该官方文章在 2025-12-15 增补说明：多数场景更推荐原生 extended thinking，而不是专用 think 工具。** 本题于 2026-09-15 核实了这项更新。因此，Think Tool 应被视为一种需要按当前模型能力验证的流程设计，不是普遍必装组件；也不能把旧版“原生思考在开头、Think Tool 在中途”的对比分界永久化。

若要评估它，可在收到关键工具结果之后增加一个简短检查点，只记录“已知事实、缺失字段、适用规则、下一动作是否可执行”。必须同时评估不加工具、原生推理和专用工具方案，统计工具说明与调用本身的 token、延迟和失败率。原文章的特定模型/基准收益不是所有业务的效果承诺；更完整的行动—反馈编排见 [agent-0025：ReAct](agent-0025-react-pattern-working-principle.md)。

### 3. 同一业务题，先定义独立真值

下面是自编的售后规则，不代表任何真实公司的政策。所有候选模型接收同一规则快照和目标输入，按顺序应用：

```text
R0：days必须为非负整数；custom/opened/defect必须为已知布尔值。
    任一输入无效或未知，返回ESCALATE。
R1：质量缺陷已确认（defect=true）且days<=30，优先返回EXCHANGE。
    这条对定制商品、已拆封商品同样适用。
R2：非定制、未拆封且days<=7，返回REFUND。
R3：其他情况返回DENY。

目标：custom=true, opened=true, days=20, defect=true。
要求：只输出action和命中的rule_ids；不要假定缺失事实。
```

**评测器真值为 `EXCHANGE`，命中 R1。** 这里由规则引擎按明示政策计算真值；正式业务还应独立核验政策和标注。目标答案不附加到待测 prompt 中，也不由多数票或模型自称的信心决定。如果真实业务规则已经能可靠形式化，应让确定性引擎判断资格，模型用于提取信息或解释结果，不必为了“多思考”而重复调用模型。

Few-shot 臂额外加入以下开发示例，目标 case 不在示例中：

| 示例输入（custom, opened, days, defect） | 示例输出 |
| --- | --- |
| false, false, 7, false | `REFUND`，R2 |
| true, true, 31, true | `DENY`，R3 |
| true, true, 10, true | `EXCHANGE`，R1 |

正式测试还要保留不同实体和未见组合，覆盖 7/8 天、30/31 天、缺失信息及规则优先级，避免只复测与示例几乎相同的题。若要提示任务分解，可以增加“检查输入完整性和规则优先级，只返回结论及依据编号”的要求；这不要求隐藏推理，也不能单凭可见说明判断内部过程是否忠实。

### 4. 对照设计与采样/聚合协议

主对照设三臂：A 直接使用共同规则与问题，调用一次；B 加上述示例，调用一次；C 使用与 B **同一提示**，独立调用五次再聚合。A/B/C 固定模型与版本、原生模板、规则/资料、输出 schema、单次输出预算和采样配置。比如选择支持相应设置的模型，在开发集上预先固定 `T=0.7、top_p=0.9`；这里只是示意实验配置，不是通用推荐值。

C 的五次请求使用不同随机流/seed（若支持），彼此不带入其他候选答案；不能缓存同一输出后复制五遍当成五次样本。为单独检验 CoT 或 Think Tool 的收益，应增设“一次调用加检查项/原生推理”和“同一工具流程加检查点”的消融臂，不能同时改变多种因素后把全部增益归给某一种方法。采样与确定性限制见 [llm-0012](llm-0012-decoding-sampling-beam.md)。

本例的聚合规则预先规定为：

1. 真实流水线先验证 JSON/schema，再从 `action` 字段提取合法动作；下面的代码只演示已提取字段的标签归一化，不替代完整解析器。
2. C 必须保留五个槽位，超时、拒绝或解析失败填 `None`。无效项不投票，但不能从分母和成本中删掉；也不按答案对错选择性补采样。
3. 某合法动作严格超过全部槽位的一半才选它；否则弃权并转人工/规则核验。严格多数门槛是本例的业务选择，**不是 Self-Consistency 唯一规定**；论文的答案聚合常用众数，还需要单独约定平票处理。
4. 聚合时不看真值、不根据解释长短加权。`3/5` 是样本的一致程度，不是“答案有60%概率正确”。动作正确性、规则依据正确性和关键违规应分别评分。

这里 C 演示的是多样本答案聚合端，不声称复现了论文全部 CoT 路径采样流程。没有相互独立的权威依据时，五个错误候选仍可能投出一个很稳定的错误结果。

### 5. 人工候选与成本算例：实际运行的是校验代码

**以下候选答案、token 数和单价全部为人工示意，没有调用或评测真实模型。** 假设 A 单次输入/输出为 `160/8 token`，B 为 `240/8 token`，C 的每次用量与 B 相同；输入费 `2`、输出费 `8` 美元/百万 token，无缓存或工具费。O 应理解为该服务全部计费输出，若包含 reasoning token 就已包含在 O 中，不能重复加；本例不声称这些假设用量就是上面 prompt 的实际长度。

成本按全部调用累计：`Σ(I×输入单价 + O×输出单价)/1,000,000`。将以下代码保存为 `reasoning_strategy_demo.py`，执行 `python3 reasoning_strategy_demo.py`，仅依赖标准库：

```python
from collections import Counter
from decimal import Decimal as D

def oracle(case):
    days = case.get("days")
    flags = [case.get(k) for k in ("custom", "opened", "defect")]
    if type(days) is not int or days < 0 or any(type(x) is not bool for x in flags):
        return "ESCALATE"  # R0：无效或未知输入。
    if case["defect"] and days <= 30:
        return "EXCHANGE"  # R1优先。
    if not case["custom"] and not case["opened"] and days <= 7:
        return "REFUND"    # R2。
    return "DENY"          # R3。

LEGAL = {"EXCHANGE", "REFUND", "DENY", "ESCALATE"}

def vote(samples):
    # 无效输出不投票，但仍计入预设K和成本；必须严格超过K/2。
    normalized = [s.strip().upper() if isinstance(s, str) else None for s in samples]
    counts = Counter(s for s in normalized if s in LEGAL)
    for action, count in counts.items():
        if count * 2 > len(samples):
            return action, count
    return None, 0  # 弃权交人工/规则核验，不偷看gold选赢家。

target = {"custom": True, "opened": True, "days": 20, "defect": True}
gold = oracle(target)
assert gold == "EXCHANGE"
# 以下输出与token数全部为人工示意；没有调用或测量真实模型。
arms = {
    "direct": (["DENY"], 160, 8),
    "few_shot": (["EXCHANGE"], 240, 8),
    "vote_5": (["EXCHANGE", "DENY", " exchange ", "EXCHANGE", None], 240, 8),
}
input_price, output_price = D("2"), D("8")  # 假设美元/百万token，无缓存/工具费。
costs = {}
print("gold=" + gold)
for name, (samples, input_each, output_each) in arms.items():
    assert len(samples) == (5 if name == "vote_5" else 1)
    action, votes = vote(samples)
    input_total = len(samples) * input_each
    output_total = len(samples) * output_each
    cost = (D(input_total) * input_price + D(output_total) * output_price) / D(1_000_000)
    costs[name] = cost
    print(f"{name}: action={action or 'ABSTAIN'} votes={votes}/{len(samples)} "
          f"correct={int(action == gold)} input={input_total} output={output_total} usd={cost:.6f}")
assert costs["vote_5"] == 5 * costs["few_shot"]
print(f"vote_5/few_shot cost ratio={costs['vote_5'] / costs['few_shot']:.1f}")
wrong, count = vote(["DENY", "DENY", "DENY", "EXCHANGE", None])
assert wrong == "DENY" and wrong != gold
print(f"wrong-majority: action={wrong} votes={count}/5 correct=0")
assert vote(["EXCHANGE", "DENY", None, None, None])[0] is None
assert vote(["EXCHANGE", "EXCHANGE", None, None, None])[0] is None
assert vote([])[0] is None
assert oracle({**target, "days": 30}) == "EXCHANGE"
assert oracle({**target, "days": 31}) == "DENY"
assert oracle({**target, "defect": None}) == "ESCALATE"
print("boundary checks: OK")
```

**真实运行 stdout（2026-09-15，macOS arm64，Python 3.11.8）**：

```text
gold=EXCHANGE
direct: action=DENY votes=1/1 correct=0 input=160 output=8 usd=0.000384
few_shot: action=EXCHANGE votes=1/1 correct=1 input=240 output=8 usd=0.000544
vote_5: action=EXCHANGE votes=3/5 correct=1 input=1200 output=40 usd=0.002720
vote_5/few_shot cost ratio=5.0
wrong-majority: action=DENY votes=3/5 correct=0
boundary checks: OK
```

这里 `correct` 仅是这个人工 case 的动作是否等于真值，不是模型准确率。B/C 的结论相同，C 的假设成本为 B 的五倍；反例又显示多数可以投错。它们只证明规则、聚合和算术按设计执行，不能证明 Few-shot 或 Self-Consistency 在生产环境有收益。

真实质量—成本评估应在保留测试集上按 case 配对，报告动作正确率、依据/引用正确率、关键违规率、弃权率和自动处理覆盖率，并用与独立业务单位匹配的区间估计。比较 `K=1/3/5` 等预定预算点及同预算基线，确认提升是否覆盖总 token、重试、工具调用、人工接管和 p95 延迟。并行五次能缩短部分墙钟等待，却不会自动省掉五次用量；缓存或不同计费档位可能改变成本比，需查真实 usage。

采用方案前先设质量底线与最小值得关注的提升。若增益不稳定、只改善解释长度，或额外成本超过目标，应保留更简单的基线；不要只展示被投票“救回”的例子，而遗漏被多数票改错或被弃权的任务。

## 延伸 / 追问

**追问一：五次都给同一个答案，是不是已经足够可信？**

不能。共同的错误规则、缺失事实、同一模型偏差或重复缓存输出都可能导致高度一致。先验证样本来源，再用独立真值和失败切片测量正确率；不要把一致率直接当作置信概率。

**追问二：Few-shot 加得越多是不是越好？**

不一定。示例要覆盖目标格式和重要边界，避免矛盾、冗余及测试泄漏；增加示例会占上下文和预算。用相同测试集比较少量代表性示例、更多示例及无示例基线，观察质量而不是输入长度。

**追问三：为什么不要求模型把所有推理都打印出来，方便验收？**

验收需要可验证的动作、规则和事实依据，不需要模型私有隐藏推理；更长的可见解释也可能包含错误或事后合理化。对本例用独立规则引擎和输入边界测试验收，比按解释是否流畅打分更直接。

**追问四：Think Tool 能把缺失的工具结果“想出来”吗？**

不能。它只能整理已有信息，缺失事实必须通过适当工具、用户补充或人工核验取得。当前模型若已有合适的原生推理能力，应先按官方接口和任务评测比较，不默认再套一个空工具。

## 常见误区

- **“解释越长越正确，所以应强制展示隐藏推理。”** 长度不是正确性或忠实性证明；应请求简短、可验证的结果依据。
- **“多数票能产生真值。”** 多数只反映这些样本的聚合结果，可能共享错误，且平票/弃权规则必须预先约定。
- **“Few-shot 就是在线微调，Think Tool 不做业务写入所以没有成本。”** 示例通常不更新权重；额外上下文、工具消息和生成仍有代价。
- **“单题从错变对，足以证明额外推理值得。”** 必须在配对测试集上比较质量、覆盖率、风险和总成本，本题人工样本不构成这种证据。

## 参考

答案、业务规则和人工候选独立编写，learn-ai 仅作学习线索，未移植其 AGPL 正文、代码或图片。本文没有要求或展示模型隐藏推理，也未把示意 token、报价或候选当作真实模型实验。

- 洛小山，《AI 产品从入门到精通》learn-ai，固定版本 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/6-1.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/6-1.html)、[slides/6-2.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/6-2.html)、[slides/10-6.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/10-6.html)。
- Brown et al., *Language Models are Few-Shot Learners*, NeurIPS 2020：[论文主页与摘要](https://papers.nips.cc/paper/2020/hash/1457c0d6bfcb4967418bfb8ac142f64a-Abstract.html)，few-shot 文本示例与不进行梯度更新的设置。
- Wei et al., *Chain of Thought Prompting Elicits Reasoning in Large Language Models*, 2022，固定 [arXiv:2201.11903v1](https://arxiv.org/abs/2201.11903v1)：CoT 示范与推理任务的实验，不作为所有模型/任务的效果保证。
- Wang et al., *Self-Consistency Improves Chain of Thought Reasoning in Language Models*, 2022，固定 [arXiv:2203.11171v1](https://arxiv.org/abs/2203.11171v1)：多样采样与一致答案聚合的一手研究。
- Anthropic, [The “think” tool: Enabling Claude to stop and think in complex tool use situations](https://www.anthropic.com/engineering/claude-think-tool)，发表于2025-03-20；特别核对页面顶部 **2025-12-15 Extended thinking update**。以上来源访问与核实日期均为2026-09-15；Think Tool 页面通过浏览器实际读取，本文不沿用课件中的固定收益数字。
