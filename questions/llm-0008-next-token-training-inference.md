---
id: llm-0008
title: 自回归模型怎样逐 Token 生成回答，训练、推理和对话内学习分别改变了什么？
category: llm
tags: [autoregressive, next-token, training, inference, in-context-learning]
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

自回归模型怎样逐 Token 生成回答，训练、推理和对话内学习分别改变了什么？请用三步续写追踪输入、概率分布和新增 Token，并说明为什么“参数不变”不能直接推出“没有学习效果、没有记忆或没有推理能力”。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**自回归生成是在已有前缀上预测下一个 token，再把选中的 token 加回前缀；普通推理通常保持模型参数不变，但上下文和中间计算状态一直在变。** 训练改变可训练参数，对话内学习改变本次条件输入，产品的长期记忆则由额外的存储与读取机制提供。判断系统“学到了什么”，要先指出变化发生在哪一层。

### 1. 一次生成循环做了什么

给定输入 token 序列 `x`、参数 `θ` 和生成序列 `y₁…yₘ`，自回归分解为：

```text
pθ(y₁…yₘ | x) = ∏ₜ₌₁ᵐ pθ(yₜ | x, y₁…yₜ₋₁)
```

各项是无量纲的条件概率。若最后一个 `y` 包含结束标记，这个乘积也包含“在这里结束”的概率。分解本身不意味着系统必须一直选概率最大的 token，也不保证高概率文本就是真实答案。

典型 decoder-only 模型的一轮循环如下：

1. **准备前缀**：将消息经 tokenizer 和模型匹配的 chat template 编成 ID。Token 不一定是一个字或一个词，参见 [llm-0007：Token/BPE 与预算](llm-0007-tokenization-bpe-budget.md)。
2. **前向计算**：以当前前缀为条件，取得末位置对下一 token 的整张词表打分，即 logits。对 logits 做 softmax 可得到基础条件分布；logits 本身不是概率，数值不需要处于 `[0,1]` 或总和为 1。
3. **选择 token**：greedy 取最大分数；随机采样则从选定的分布抽样。温度 `T>0` 可通过 `softmax(logits/T)` 改变分布，top-k/top-p 等处理还会限制候选并重新归一化。基础模型分布与最终采样分布应分开记录；greedy 可以直接比较分数，无需真的计算 softmax。
4. **追加并检查停止**：将新增 ID 接到前缀，若生成结束标记、达到输出长度上限或触发服务端/应用的停止条件就结束，否则计算下一步。EOS 表示模型生成了结束标记；长度上限可能把尚未完成的答案截断，两者不能混为一谈。

通常先处理整个输入做 **prefill**，再逐步 **decode**；KV Cache 可以复用前缀计算，避免每步重算所有旧 token，但新 token 的选择仍依赖已选前缀。这里描述基本循环，加速实现可能一次验证多个候选，参见 [llm-0006：Speculative Decoding](llm-0006-speculative-decoding.md)，不能把“每次 forward 永远只产出一个 token”当作所有实现的约束。

一手实现可核对 **Transformers v4.57.1**：`generation/utils.py::_sample` 取 `outputs.logits[:, -1, :]`，处理分数后走 `multinomial` 或 `argmax`，再追加 `input_ids` 并调用 stopping criteria。`stopping_criteria.py` 分别实现 EOS 和长度条件。具体固定版本与位置见参考；本题没有运行这套真实模型推理代码。

### 2. 三步续写：概率是示意输入，代码输出是真实复现

设玩具输入前缀为 `[天空]`，**完整词表仅有 `天空、是、蓝色、灰色、<EOS>` 五个标签**，输入与输出使用同一词表。这是自编的教学状态表，不是任何真实模型的 tokenizer 切分或 logits 测量；`蓝色` 在此被人为定义为一个 token。三个前缀的条件分布如下，其他路径不在本演示范围内：

| 步骤 | 本步输入前缀 | `天空` | `是` | `蓝色` | `灰色` | `<EOS>` | greedy 新增 token |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `[天空]` | 0.05 | 0.60 | 0.15 | 0.10 | 0.10 | `是` |
| 2 | `[天空, 是]` | 0.05 | 0.05 | 0.70 | 0.15 | 0.05 | `蓝色` |
| 3 | `[天空, 是, 蓝色]` | 0.05 | 0.05 | 0.05 | 0.05 | 0.80 | `<EOS>`，停止 |

每行总和为 1，第三步也算一次新增 token，只是 EOS 不展示为普通文本。**分布不同源于条件前缀不同，没有在三步之间修改参数或概率表。** 示例将 `log(p)` 构造成 logits，再以 `T=1` 做稳定 softmax，采用 greedy，不启用随机采样或 top-k/top-p。

将以下代码保存为 `three_step.py`，运行 `python3 three_step.py`，仅依赖 Python 标准库：

```python
from math import exp, isclose, log, prod

# 人工设定的完整玩具词表与条件分布，不是任何真实模型的测量值。
VOCAB = ("天空", "是", "蓝色", "灰色", "<EOS>")
TABLE = {
    ("天空",): (0.05, 0.60, 0.15, 0.10, 0.10),
    ("天空", "是"): (0.05, 0.05, 0.70, 0.15, 0.05),
    ("天空", "是", "蓝色"): (0.05, 0.05, 0.05, 0.05, 0.80),
}

def generate(max_new_tokens):
    context, trace, chosen_probs = ("天空",), [], []
    reason = "length"
    for _ in range(max_new_tokens):
        row = TABLE[context]
        assert all(p > 0 for p in row) and isclose(sum(row), 1.0)
        logits = [log(p) for p in row]  # 构造 logits；T=1，无 top-k/top-p。
        weights = [exp(z - max(logits)) for z in logits]
        probs = [w / sum(weights) for w in weights]
        assert all(isclose(p, q) for p, q in zip(probs, row))
        token_id = max(range(len(VOCAB)), key=lambda i: probs[i])
        token = VOCAB[token_id]  # greedy；不会随机抽样。
        trace.append((context, probs, token))
        chosen_probs.append(probs[token_id])
        context += (token,)
        if token == "<EOS>":
            reason = "eos"
            break
    visible = "".join(t for t in context if t != "<EOS>")
    return trace, visible, reason, prod(chosen_probs)

trace, visible, reason, joint = generate(3)
for step, (context, probs, token) in enumerate(trace, 1):
    distribution = ", ".join(f"{t}:{p:.2f}" for t, p in zip(VOCAB, probs))
    print(f"{step} input=[{'|'.join(context)}] p=[{distribution}] add={token}")
print(f"stop={reason} visible={visible} joint={joint:.4f}")
assert [row[2] for row in trace] == ["是", "蓝色", "<EOS>"]
assert reason == "eos" and isclose(joint, 0.60 * 0.70 * 0.80)
limited, _, stop, _ = generate(2)
assert len(limited) == 2 and stop == "length"
assert all(row[2] != "<EOS>" for row in limited)
print("limit-check: max_new_tokens=2, added=2, reason=length")
```

**真实运行输出：2026-09-15，macOS arm64，Python 3.11.8。** 这里只验证人工示例的计算与循环行为，没有下载预训练模型、训练权重或调用模型 API：

```text
1 input=[天空] p=[天空:0.05, 是:0.60, 蓝色:0.15, 灰色:0.10, <EOS>:0.10] add=是
2 input=[天空|是] p=[天空:0.05, 是:0.05, 蓝色:0.70, 灰色:0.15, <EOS>:0.05] add=蓝色
3 input=[天空|是|蓝色] p=[天空:0.05, 是:0.05, 蓝色:0.05, 灰色:0.05, <EOS>:0.80] add=<EOS>
stop=eos visible=天空是蓝色 joint=0.3360
limit-check: max_new_tokens=2, added=2, reason=length
```

在**给定条件分布**下，序列 `是、蓝色、<EOS>` 的概率为 `0.60×0.70×0.80=0.336`，不是答案正确率，也不是 greedy 策略重复运行时的随机频率；本代码的选择是确定的。长度限制改为 2 时，可见文本同样是“天空是蓝色”，却没有生成 EOS，说明仅看显示出来的文字不能判断停止原因。

### 3. 训练、推理、对话内学习分别改变什么

| 过程 | 发生变化的对象 | 持续性与边界 |
| --- | --- | --- |
| 训练：预训练、微调等 | 梯度和优化器更新指定的可训练参数 `θ`，或 adapter 参数 | 更新后的 checkpoint 可用于后续请求；训练不是模型一生只能做一次，也不保证逐条精确记住数据 |
| 普通推理 inference | 前缀、激活、KV Cache、采样状态与输出；通常不更新参数 | 状态服务于当前计算，是否保留或复用由运行时决定；生成新内容不要求现场做梯度更新 |
| 对话内学习 / in-context learning | 将说明、例子、纠正等放入上下文，使固定模型的条件分布改变 | 可以表现为学会本轮的新映射或规则；不是参数微调，移除相关条件后不保证还能复现该行为 |
| 产品外部记忆 | 数据库中的偏好、事实、摘要等，以及后续检索并注入的内容 | 可跨会话存在，但必须有相应写入、授权与读取流程；它不自动等同于权重更新 |

对常见的 causal LM 预训练，训练目标可写为 `L(θ) = -Σ_t log pθ(x_t | x_<t)`，其中 `x_<t` 表示位置 `t` 之前的真实前缀；更直观的写法是 `-Σ log pθ(真实下一 token | 真实已有前缀)`。通过反向传播求梯度，再由优化器更新参数。训练常用 **teacher forcing**：用真实前文预测真实下一 token，而不是每个位置都先自由生成一个预测结果再拿去充当下一个训练输入。

在因果掩码保证不能偷看后续 token 的前提下，Transformer 可以在一次训练前向中并行计算多个位置的 next-token loss；普通自由生成时，后续前缀尚未确定，所以仍要依次选择。这是训练与生成的计算差异，不是“训练时看到了答案”。SFT 还可能只对部分位置计 loss，RL 的目标也不必是这条交叉熵公式；不能把所有训练方式概括成同一种目标。即使基础权重冻结，[LoRA 训练](llm-0001-lora-fine-tuning.md)仍会更新 adapter 的可训练参数。

在实际实现中，这个区别可见于固定版本 Transformers：`ForCausalLMLoss` 对齐下一位置的 labels 并算交叉熵，`Trainer` 执行 backward 和 optimizer step；普通 `generate()` 入口使用 `torch.no_grad()`。这说明这些路径如何实现，并不证明任何带“推理”名字的系统都绝不更新参数：若系统显式加入在线训练或 test-time adaptation，就需要另外说明更新了什么及如何隔离。

**普通推理不更新权重，不等于产品没有外部记忆，也不等于模型没有推理能力。** “inference”是运行已训练模型的过程，“reasoning”是完成推导、规划等任务的能力；是否具备后者要用任务结果和评测判断，不能由“底层预测 next token”直接否定。聊天数据若被另一个管线用于后续训练，也不等于每条消息都会立刻修改当前服务模型。外部记忆的设计见 [agent-0020：记忆类型与上下文](agent-0020-memory-types-context-overflow.md)。

### 4. 两类常见取舍

| 选择 | 适用条件 | 代价 / 不适用场景 |
| --- | --- | --- |
| Greedy 解码 | 希望减少输出随机性，适合做固定配置的对照实验 | 只做局部最大选择，不保证全局最高概率或正确性；追求候选多样性的创意任务可能不合适 |
| 随机采样 | 希望生成多个候选，如探索不同表达或解法 | 带来方差和更多评测成本；严格事实任务不能仅靠提高温度改善，仍需事实校验或约束 |
| 上下文示范 / 纠正 | 少量规则、临时任务，需快速验证或撤回 | 不需要训练但占输入预算，对示例与上下文保留敏感；不能据此承诺跨会话永久学会 |
| 参数微调 | 有代表性训练数据，需在大量请求中稳定改变行为 | 需要训练、版本管理和回归评测；仅记住一个易变偏好时通常不如外部记忆直接，也不保证事实永远更新及时 |

解码策略控制“怎样从当前分布取输出”，上下文与训练控制“分布因何改变”，两组选择是不同的维度。冻结参数也不保证服务调用逐字可复现；采样、模型版本、计算实现等都可能带来差异。

## 延伸 / 追问

**追问一：我在对话中定义“红灯输出 A，绿灯输出 B”，模型随后正确处理绿灯，是不是训练发生了？**

只能说明它能依据当前说明完成任务。没有 backward/optimizer 更新证据，不能据此认定微调；这是上下文条件化或 in-context learning。可移除规则并换成没有外部记忆注入的新请求做对照，但行为对照仍不能替代参数版本和训练日志的核查。

**追问二：同样输入却生成不同答案，是不是模型偷偷学习了？**

先核对模型版本、完整消息和工具/记忆注入、采样参数及运行环境。随机采样在参数不变时也会产生不同输出；反过来，greedy 输出相同也不能证明参数从未更新。若调查训练变更，应核对 checkpoint 或 adapter 版本及更新管线。

**追问三：为什么训练 loss 很低，生成时还是会在前几步出错后越走越偏？**

teacher forcing 的条件前缀来自真实数据，自由生成会把自己的选择接回去；一旦进入不同于训练数据的前缀，误差可能累积。要补自由生成的端到端评测和失败样例，并区分模型、上下文、解码与停止条件问题，不能仅凭低 loss 宣称任务已经解决。

## 常见误区

- **“不更新权重，所以模型没有推理能力，产品也没有记忆。”** 参数、计算状态、外部存储和任务能力是不同问题，应分别核查。
- **“每次一定选择概率最大的词。”** Token 不等于词；greedy 和随机采样的选择规则不同，局部最大也不保证整段最优。
- **“对话里学会一个规则，就是永久改写了模型。”** ICL 改变条件输入；跨会话表现还可能来自外部记忆、系统提示或模型版本变化。
- **“得到一段完整文字就代表模型正常结束。”** 同样的可见文本可能来自 EOS 或长度截断，需查看真实停止原因。

## 参考

本题独立组织答案与玩具实验，learn-ai 仅作学习线索，未移植其 AGPL 正文、代码或图片；不采用课件中固定训练成本、硬件规模或“生成机制排除推理能力”等泛化判断。

- 洛小山，《AI 产品从入门到精通》learn-ai，固定版本 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/1-2-base.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/1-2-base.html)、[slides/train-vs-infer.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/train-vs-infer.html)、[slides/zero-q-ai-learning.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/zero-q-ai-learning.html)。
- Brown et al., *Language Models are Few-Shot Learners*, NeurIPS 2020：[论文主页与摘要](https://papers.nips.cc/paper/2020/hash/1457c0d6bfcb4967418bfb8ac142f64a-Abstract.html)，明确 few-shot 实验通过文本指定任务与示范，不做 gradient update 或 fine-tuning；访问日期 2026-09-15。
- Hugging Face，**Transformers v4.57.1**，固定 commit `8cb5963cc22174954e7dca2c0a3320b7dc2f4edc`：[causal language modeling 文档 L27](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/docs/source/en/tasks/language_modeling.md#L27)；[`generation/utils.py::_sample` L2686](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/generation/utils.py#L2686)，核心选择与追加在 L2800–2842；[`generate` 的 no_grad 入口 L2233](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/generation/utils.py#L2233)。
- 同一 Transformers commit：[`stopping_criteria.py::MaxLengthCriteria` L59](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/generation/stopping_criteria.py#L59)、[`EosTokenCriteria` L452](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/generation/stopping_criteria.py#L452)；本题玩具循环另以 `max_new_tokens` 计新增 token，勿与包含输入的 `max_length` 混用。
- 同一 Transformers commit：[`loss/loss_utils.py::ForCausalLMLoss` L45](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/loss/loss_utils.py#L45)；[`trainer.py` optimizer step L2740](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/trainer.py#L2740)、[backward L4071](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/trainer.py#L4071)，用于核对训练更新与普通生成路径的区别。
