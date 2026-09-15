---
id: llm-0012
title: Greedy、Temperature、Top-k、Top-p 与 Beam Search 怎样改变解码，如何按任务选择？
category: llm
tags: [decoding, sampling, temperature, top-p, beam-search]
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

Greedy、Temperature、Top-k、Top-p 与 Beam Search 怎样改变解码，如何按任务选择？请用小概率分布说明截断、归一化和组合顺序，并比较客服与创作任务的取舍及确定性边界。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**Greedy 每步选一个最高分 token，Temperature 改变分布尖锐程度，Top-k/Top-p 限制采样候选，Beam Search 则同时保留多个序列前缀继续搜索。** 前几项主要决定“本步怎样选”，Beam 还比较“整条路径怎样评分”；它们不更新模型权重，也不能把模型没有掌握的事实补进去。自回归循环见 [llm-0008](llm-0008-next-token-training-inference.md)。

### 1. 分布变换和候选截断

设本步 logits 为 `z_i`，基础概率为 `p_i=softmax(z)_i`。对 `T>0`：

```text
q_i(T) = exp(z_i / T) / Σ_j exp(z_j / T)
       = p_i^(1/T) / Σ_j p_j^(1/T)    （对正概率项）
```

温度缩放 logits，不能简单地把概率除以 T 后就当作新分布。低温通常使分布更尖，高温更平；正温度缩放本身保留 logits 的排序，因此不改变一个无并列的 argmax。已被置为 `-∞` 的候选不会因为调高温度重新出现。

| 策略 | 具体操作 | 关键边界 |
| --- | --- | --- |
| Greedy | 每步取分数最大的 token，通常可直接对 logits 做 argmax | 局部最优不保证整段最高概率，更不保证事实正确；并列时还需实现决定如何选 |
| Temperature | 用 `z/T` 改变 softmax 分布，随后再采样 | `T=1` 不变；`T=0` 不能直接代入除法。服务的零温约定与库参数契约需要分清 |
| Top-k | 保留分数最高的一组候选，其他分数置 `-∞`，在剩余候选上归一化后采样 | 候选数量主要由 k 控制；边界并列和最少保留数量可能使实际保留数不同于 k |
| Top-p / nucleus | 按概率从高到低累加，保留达到阈值 p 的高概率候选前缀，再归一化采样 | 候选数量随分布变化；p 是累计概率阈值，不是“保留词表的 p%”或单项概率下限 |

有限正温度趋近 0 时，概率质量集中到最高分候选；若最高分并列，也不自动决定其中唯一一个。**Temperature=0 不保证事实正确或跨环境逐字复现。** 在本题固定的 Transformers 4.57.1 中，`TemperatureLogitsWarper(0.0)` 直接报错；普通 greedy 使用 `num_beams=1, do_sample=False`，不应通过除以零实现。

### 2. 手算截断，并检查组合顺序

假设完整词表只有 A–E 五个标签，人工设定本步概率为 `[0.5, 0.25, 0.125, 0.0625, 0.0625]`，总和为 1；这是数学输入，不是实际模型输出。

- **Top-k=2**：留下 A、B，原概率质量合计 `0.75`；重新归一化为 `[2/3, 1/3, 0, 0, 0]`。
- **Top-p=0.76**：A+B 的累计质量为 `0.75`，还没达到阈值，所以须加入 C，累计 `0.875`；新分布为 `[4/7, 2/7, 1/7, 0, 0]`。不能丢掉跨越阈值所需的 C。
- **T=0.5**：先平方各项再归一化，得到 `[64,16,4,1,1]/86`；这是温度变换，与选择固定数量的候选不同。

组合时每一步都作用于**当前**分布。对这组输入，`T=0.5 → k=2` 后 A/B 为 `0.8/0.2`，再做 `p=0.76` 只留下 A；若先做 `T=0.5 → p=0.76`，此时 A 的质量约为 `0.744186`，必须保留 B，之后再用 k=2 仍是 `0.8/0.2`。两种顺序输出不同。

本题固定源码中，普通采样路径 `do_sample=True, num_beams=1` 按 **Temperature → Top-k → Top-p** 构造这些处理器；其他惩罚、约束或自定义处理器还可能先改变分数。不要把该顺序当作所有 API 的统一约定。`do_sample=False` 时，这一组采样 warper 不会按同样方式生效，设置参数也不代表已经在采样。

### 3. 真实运行：固定版本 warper 与人工 Beam 树

运行环境：**2026-09-15，macOS arm64，Python 3.11.8，PyTorch 2.9.0，Transformers 4.57.1**。分布计算使用 CPU `float64`，显示时保留六位小数；没有加载预训练模型或执行随机抽样。

```sh
python -m pip install torch==2.9.0 transformers==4.57.1
```

把以下代码保存为 `decoding_demo.py`，执行 `python decoding_demo.py`。前半段调用真实的 Transformers warper；后半段是另一个独立的自编概率树，只演示等长序列搜索，不是调用完整的 Hugging Face Beam 生成流程。

```python
from fractions import Fraction as F
from importlib.metadata import version
import torch
from transformers import TemperatureLogitsWarper, TopKLogitsWarper, TopPLogitsWarper

assert version("transformers") == "4.57.1"
assert version("torch").split("+")[0] == "2.9.0"
# 人工A–E分布；CPU float64，不加载模型，也不实际抽样。
probs = torch.tensor([[0.5, 0.25, 0.125, 0.0625, 0.0625]], dtype=torch.float64)
logits = probs.log()
input_ids = torch.zeros((1, 1), dtype=torch.long)  # 此处的warper不读取这个占位前缀。

def distribution(*processors):
    scores = logits.clone()
    for processor in processors:
        scores = processor(input_ids, scores)
    result = scores.softmax(dim=-1)[0]
    assert torch.isfinite(result).all() and abs(result.sum().item() - 1) < 1e-12
    return result

t = TemperatureLogitsWarper(0.5)
k = TopKLogitsWarper(2)
p = TopPLogitsWarper(0.76)
cases = (("base", ()), ("T=0.5", (t,)), ("k=2", (k,)),
         ("p=0.76", (p,)), ("T,k,p", (t, k, p)), ("T,p,k", (t, p, k)))
for label, processors in cases:
    values = distribution(*processors)
    print(label + ": [" + ", ".join(f"{v:.6f}" for v in values.tolist()) + "]")
assert not torch.allclose(distribution(t, k, p), distribution(t, p, k))
assert torch.allclose(distribution(TemperatureLogitsWarper(1.0)), probs[0])
assert torch.allclose(distribution(TopKLogitsWarper(99)), probs[0])
assert torch.allclose(distribution(TopPLogitsWarper(1.0)), probs[0])
assert torch.count_nonzero(distribution(TopPLogitsWarper(0.0))).item() == 1
ties = torch.tensor([[0.0, 0.0, -1.0]], dtype=torch.float64)
kept = torch.isfinite(TopKLogitsWarper(1)(input_ids, ties)).sum().item()
assert kept == 2  # 本版本按第k分数阈值过滤，边界并列可能多留。
uniform = torch.zeros((1, 8), dtype=torch.float64)
assert torch.isfinite(TopPLogitsWarper(0.5)(input_ids, uniform)).sum().item() == 4
try:
    TemperatureLogitsWarper(0.0)
except ValueError:
    pass
else:
    raise AssertionError("T=0应走独立的greedy策略，不是除以零")
print("boundaries: T=1/k>=V/p=1 unchanged; p=0 keeps 1; top-k tie keeps 2; T=0 rejected")

# 另一个人工概率树：固定两步、无EOS/长度惩罚；不是HF完整Beam实现。
tree = {
    (): {"A": F(3, 5), "B": F(2, 5)},
    ("A",): {"x": F(51, 100), "y": F(49, 100)},
    ("B",): {"x": F(9, 10), "y": F(1, 10)},
}
assert all(sum(branch.values()) == 1 for branch in tree.values())

def beam(width):
    paths = [((), F(1))]
    for _ in range(2):
        candidates = [(prefix + (token,), score * probability)
                      for prefix, score in paths for token, probability in tree[prefix].items()]
        paths = sorted(candidates, key=lambda item: (-item[1], item[0]))[:width]
    return paths[0]

for label, width in (("greedy", 1), ("beam=2", 2)):
    path, score = beam(width)
    print(f"{label}: {' '.join(path)}, sequence_probability={float(score):.3f}")
assert beam(1) == (("A", "x"), F(153, 500))
assert beam(2) == (("B", "x"), F(9, 25))
```

实际 stdout：

```text
base: [0.500000, 0.250000, 0.125000, 0.062500, 0.062500]
T=0.5: [0.744186, 0.186047, 0.046512, 0.011628, 0.011628]
k=2: [0.666667, 0.333333, 0.000000, 0.000000, 0.000000]
p=0.76: [0.571429, 0.285714, 0.142857, 0.000000, 0.000000]
T,k,p: [1.000000, 0.000000, 0.000000, 0.000000, 0.000000]
T,p,k: [0.800000, 0.200000, 0.000000, 0.000000, 0.000000]
boundaries: T=1/k>=V/p=1 unchanged; p=0 keeps 1; top-k tie keeps 2; T=0 rejected
greedy: A x, sequence_probability=0.306
beam=2: B x, sequence_probability=0.360
```

这些概率均无量纲，只描述人工输入上的分布和序列概率。边界也要按调用层级理解：本版本 `TopPLogitsWarper(0.0)` 允许且默认至少保留一个候选，`TopKLogitsWarper(0)` 则非法；但 `generate(top_k=0)` 在此版本表示不构造 Top-k 处理器。Top-k 采用第 k 个分数作为阈值，因此并列时可能保留多于 k 个；Top-p 的临界累计量还受浮点计算、排序和最少保留数量影响。Beam sampling 的最少保留规则也可能不同，不能把这里的默认单 beam 结论推广到所有路径。

最少保留规则不负责修复无效输入：若先前约束已把全部 logits 置为 `-∞`，仍然没有合法分布，应用应检查并处理，不能把产生的 NaN 继续用于采样。

### 4. Beam 搜索的是序列，不是“思考深度”

普通确定性 Beam Search 保留 b 条高分前缀，将每条前缀的下一 token 候选展开，再按累计分筛回有限条路径。基础分数常是 `Σ_t log p(y_t | prefix)`，等价于比较联合概率的乘积；真实实现还要处理 EOS、长度惩罚/归一化和提前停止，最终排序不一定等于裸概率大小。

上面的独立概率树只比较**固定长度两步**，未列出的分支视为概率 0，不处理 EOS 或长度惩罚。Greedy 先选 A 的 `0.6`，再选 x 的 `0.51`，得到 `0.306`；宽度 2 保留 B 分支，发现 `0.4×0.9=0.36` 的 B x 更高。它是这个小树的最高概率路径，**不是正确率 36%**。有限宽度在更大搜索树上仍可能提前剪掉最终最优路径，不能承诺全局最优。

**Beam 不等同深度推理。** 它按序列评分保留分支，不自动核实事实、调用验证器或检查逻辑正确性。更宽的 beam 增加候选和状态维护开销，却未必提高任务质量；开放式文本还可能变得平淡、重复。Holtzman 等人的研究支持在其开放式生成实验中考虑 nucleus sampling，但不意味着 Beam 对翻译等所有任务都无用。

在 Transformers 中，普通确定性 Beam 一般使用 `num_beams>1, do_sample=False`；采样与 Beam 也可以组合，此时需要另外核对具体策略。beam 宽度 b 与 Top-k 的 k 是不同概念。投机解码研究的是怎样加速并保持目标解码分布，见 [llm-0006](llm-0006-speculative-decoding.md)，不能与修改分布的采样参数混为一谈。

### 5. 客服与创作应怎样选

| 任务 | 合理起点 | 代价与不适用场景 |
| --- | --- | --- |
| 事实型客服、字段抽取 | 用 greedy 或经过验证的低温采样建立基线，配合资料引用、输出校验及不确定时的回退 | 随机性较小不等于正确；若最高分本来是错误答案，低温会稳定选错。不能把温度当事实校验器 |
| 文案、头脑风暴 | 在固定测试集上逐项调整温度或 Top-p，比较多样性、可用率和筛选成本 | 多样性提高也会增加跑题和筛选工作；涉及事实仍需核对，不宜把“更发散”当作唯一质量指标 |
| 有明确目标的翻译等序列任务 | 可比较 greedy 与有限宽度 Beam，校准长度与任务评分 | 会增加候选计算及状态开销；开放式创作不应只因联合概率更高就默认 Beam 更优 |

表中是评测起点，不是所有模型通用的推荐参数表。先固定模型版本、原生模板、上下文、输出预算和任务指标，每次只改一个主要因素，再检查组合；业务最终比较事实正确率、格式通过率、用户可用率、延迟及总调用成本。不能从 beam 宽度直接推导 API 账单。

确定性也有层次：在完全固定的 logits、排序与算术规则下，greedy 是确定的选择；真实系统的模型版本、提示内容、浮点误差、并行内核或并列处理都可能改变结果。随机种子帮助复现实验，但 PyTorch 官方明确不保证跨版本、平台或 CPU/GPU 逐字一致。记录 seed、版本和执行设置很有用，却不能承诺“Temperature=0 永远同一句话”。

## 延伸 / 追问

**追问一：同时调低 Temperature 和 Top-p，是否一定更安全？**

两者都可能收缩候选，但它们筛的是分数，不识别事实或权限。叠加后甚至只剩一个错误候选；先检查作用顺序和最后分布，再用事实/安全用例验证，不应把随机性下降当成安全证明。

**追问二：为什么 Top-p 在同一设置下，有时保留两个 token，有时保留几十个？**

它按当前累计概率质量决定集合大小。尖锐分布很快达到阈值，平坦分布需要更多候选；温度及之前的过滤也会改变累计质量。若需要固定候选上限可研究 Top-k，但必须考虑并列和具体实现。

**追问三：Beam 越宽、累计概率越高，为什么答案可能更差？**

搜索分数与事实正确性、创造力或用户偏好不完全一致，长度处理也会改变排名。有限搜索可能更好地优化了一个不合适的目标；应依据任务评测选择策略，而不是把高概率或多分支等同更深的推理。

## 常见误区

- **“Temperature=0 保证正确且任何环境都能逐字复现。”** 它既不是事实验证器，也不能消除系统版本和数值实现差异。
- **“Beam Search 就是推理模型先想多条思路再选答案。”** Beam 是序列搜索算法，本身没有逻辑或事实验证机制。
- **“Top-p=0.9 就是保留前90%的词表。”** 它限制累计概率质量，候选个数随当前分布变化。
- **“Top-k/Top-p/温度的顺序无所谓，或设置参数就一定生效。”** 组合通常不交换，且采样/greedy/Beam 路径的参数行为不同。

## 参考

内容、人工分布与两步概率树独立编写，learn-ai 仅作学习线索，未移植其 AGPL 正文、代码或图片。没有真实模型生成、事实正确率、跨环境确定性或性能账单实验；数值只验证所示解码操作。

- 洛小山，《AI 产品从入门到精通》learn-ai，固定版本 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/1-2-mitigation-temp.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/1-2-mitigation-temp.html)、[slides/algo-9.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/algo-9.html)、[slides/algo-10.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/algo-10.html)。
- Hugging Face，**Transformers v4.57.1**，固定 commit `8cb5963cc22174954e7dca2c0a3320b7dc2f4edc`：[`generation/logits_process.py::TemperatureLogitsWarper` L231](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/generation/logits_process.py#L231)、[`TopPLogitsWarper` L464](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/generation/logits_process.py#L464)、[`TopKLogitsWarper` L531](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/generation/logits_process.py#L531)：变换、过滤、边界与最少保留规则。
- 同一 Transformers commit：[`generation/utils.py` L1249](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/generation/utils.py#L1249) 的采样处理器顺序；[`_beam_search` L3111](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/generation/utils.py#L3111) 及其辅助函数：累计 log 概率、长度处理和停止机制。
- Holtzman et al., *The Curious Case of Neural Text Degeneration*, ICLR 2020，固定 [arXiv:1904.09751v2](https://arxiv.org/abs/1904.09751v2)：开放式文本生成与 nucleus sampling 的一手研究；访问日期 2026-09-15。
- PyTorch **v2.9.0**，固定 commit `0fabc3ba44823f257e70ce397d989c8de5e362c1`：[Reproducibility 文档源码](https://github.com/pytorch/pytorch/blob/0fabc3ba44823f257e70ce397d989c8de5e362c1/docs/source/notes/randomness.rst)，跨版本、平台与设备的复现限制；访问日期 2026-09-15。
