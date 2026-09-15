---
id: llm-0018
title: KV Cache 缓存的到底是什么，为什么能加速自回归推理，却会带来内存压力？
category: llm
tags: [kv-cache, prefill, decode, prefix-caching, inference]
difficulty: medium
role: engineer
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

KV Cache 缓存的到底是什么，为什么能加速自回归推理，却会带来内存压力？请手推追加一个 Token 时的复用与重算，说明请求内缓存、跨请求前缀复用和最终答案缓存的区别。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**KV Cache 保存每层 attention 已处理位置的 Key 和 Value，供后续位置继续读取。** 它省掉旧位置的重复前向计算，却没有省掉新位置对历史 K/V 的访问，也不是缓存“上次写好的答案”。本题聚焦缓存状态为何有效、怎样追加和何时不能复用；完整 Attention 矩阵与复杂度见 [llm-0010](llm-0010-causal-attention-architecture.md)，整机容量预算见 [llm-0016](llm-0016-quantization-local-memory-budget.md)。

### 1. 旧 K/V 为什么可以不重算

对标准 causal decoder，在权重、前缀输入、位置/掩码规则和数值配置一致、关闭 dropout 等推理条件下，位置 i 不会看见后面新追加的位置。这个性质可以逐层说明：第一层之前，旧 token 的输入表示不变；若某层旧位置的输入不变，该层只能读取原来已存在的左侧信息，加上逐位置的归一化、FFN 等运算，其旧位置输出也不变。因此下一层旧 K/V 同样保持有效。

**缓存是逐层、按上下文计算出来的状态，不是“某个词永远对应的一组 K/V”。** 高层 K/V 已包含前面层传播的上下文信息；即便后缀 token IDs 和位置都相同，只要更早的前缀不同，高层缓存也可能不同。双向 attention、改变位置规则或权重等情形不满足上述前提，不能直接套这个复用结论。

对已经处理 n 个位置的某一层，追加位置 n 时：

```text
从当前层的新位置表示计算 q_new、k_new、v_new
K_all = concat(K_past, k_new)      # 原来的 n 行值保持不变
V_all = concat(V_past, v_new)
a_new = softmax(q_new K_all^T / sqrt(d_k) + 当前位置的 mask)
y_new = a_new V_all
继续计算新位置的输出投影、残差/FFN和下一层
```

旧 Q 通常不需要留下给下一步使用，因为下一步只需要新的 query 来产生新位置的表示；旧位置的输出已经完成。旧注意力权重也不能当作新位置的权重复用：query 可能不同，可见 key 集合和 softmax 分母也发生变化。真正节省的是重做旧位置的投影和层间计算，不是让新 token 完全不用读取历史。普通 dense attention 的新 query 仍需遍历可见 K/V，端到端性能还受带宽、内核和调度影响。

### 2. 手推一次追加：缓存内容不变，注意力行要重算

设一个人工单层单头示例，`d_k=d_v=1`，给定投影后的张量，不涉及真实词表、位置编码或完整模型。已经缓存 A、B：`K_past=[0, ln2]`，`V_past=[10,20]`；原 B 的 query 为 1，其注意力权重为 `[1/3,2/3]`，输出 `50/3`。

现在追加 C，给定 `q_C=2`、`k_C=ln2`、`v_C=30`：

| 步骤 | 结果 |
| --- | --- |
| 复用旧值、追加新值 | `K_all=[0,ln2,ln2]`，`V_all=[10,20,30]` |
| 新 query 与全部 key 相乘，缩放因子为 1 | `scores=[0,ln4,ln4]` |
| 重新计算这一行 softmax | `exp(scores)=[1,4,4]`，`a_C=[1/9,4/9,4/9]` |
| 聚合 value | `y_C=(10+4×20+4×30)/9=70/3≈23.333333` |

没有重算 A/B 的 K/V，也没有重算 A/B 的最终输出；但 A/B 在 **C 这一行**的匹配分数和归一化权重都要重新计算。若沿用 B 的旧注意力行并给新列补零，会仍得到 `50/3`，不是正确的 C 输出。缓存的是可复用材料，而非上一个 query 的归一化结果。

### 3. Prefill、decode 与缓存长度的时序

Prefill 处理已知 prompt 的多个位置，在各层建立对应 K/V；最后一个 prompt 位置的 logits 可用于选择第一枚生成 token。**选中一个 token 并不意味着它的 K/V 已写入缓存**：通常要在下一次 forward 把它送入，经过每一层后才追加对应 K/V，再得到预测下一枚 token 的 logits。

例如 prompt 有 3 个 token：prefill 后 cache 长度为 3；若给定追加 token 13，decode forward 的输入长度为 1、可见缓存长度为 4，结束后 cache 长度才变为 4。新 token 仍要经过全部层及输出头，不只是算一个 K/V 投影。

手写循环必须让新位置编号、attention mask 和实际缓存内容一致。在本文 Transformers 实现中，`cache_position=[3]` 表示追加到已有三个位置之后；mask 需覆盖过去与当前位置。Padding、分块 prefill 或一次输入多枚新 token 时，还要按实现维护位置，不能简单把每次 forward 的局部下标都从 0 开始。

### 4. 用固定版本实现验证逐层复用

以下是**实际运行的缓存机制验证**：Python 3.11.8、PyTorch 2.9.0、Transformers 4.57.1，macOS arm64，CPU `float64`，eager attention、eval/inference mode，无 padding、滑窗或 offload。随机种子为 42，模型有两层、4 个 query heads、2 个 KV heads，每头维度 4。

模型由配置随机初始化，**没有下载预训练权重，也没有测试语言能力、吞吐或费用**。Token IDs 是给定的整数，13/17 并非模型采样结果。它与上面的标量手推是两个独立验证：手推展示重算内容，本实验验证带 RoPE 的逐层缓存路径、分支和位置边界。

```python
import copy
import torch
from transformers import LlamaConfig, LlamaForCausalLM

torch.manual_seed(42)
config = LlamaConfig(vocab_size=32, hidden_size=16, intermediate_size=32,
                     num_hidden_layers=2, num_attention_heads=4,
                     num_key_value_heads=2, max_position_embeddings=64,
                     attention_dropout=0.0)
config._attn_implementation = "eager"
model = LlamaForCausalLM(config).double().eval()  # 随机权重，无 from_pretrained。
prefix = torch.tensor([[1, 5, 9]])
next_id = torch.tensor([[13]])  # 给定的追加 token，不是模型采样结果。

def logical_bytes(cache):
    return sum(t.numel() * t.element_size()
               for layer in cache.layers for t in (layer.keys, layer.values))

with torch.inference_mode():
    prefill = model(prefix, use_cache=True)
    saved = copy.deepcopy(prefill.past_key_values)
    print("prefill:", saved.get_seq_length(), logical_bytes(saved))
    projected = {name: [] for name in ("q", "k", "v")}
    handles = []
    for layer in model.model.layers:
        for name in projected:
            projection = getattr(layer.self_attn, name + "_proj")
            handles.append(projection.register_forward_pre_hook(
                lambda module, args, name=name: projected[name].append(args[0].shape[-2])))
    step = model(next_id, past_key_values=prefill.past_key_values,
                 attention_mask=torch.ones(1, 4, dtype=torch.long),
                 cache_position=torch.tensor([3]), use_cache=True)
    for handle in handles:
        handle.remove()
    full = model(torch.cat((prefix, next_id), dim=1), use_cache=False)
    same_kv = all(torch.equal(getattr(old, name), getattr(new, name)[:, :, :3, :])
                  for old, new in zip(saved.layers, step.past_key_values.layers)
                  for name in ("keys", "values"))
    equal_logits = torch.allclose(step.logits[:, -1], full.logits[:, -1], atol=1e-12, rtol=1e-10)
    print("decode:", step.past_key_values.get_seq_length(), logical_bytes(step.past_key_values))
    print("new projection lengths:", projected)
    print("old KV unchanged:", same_kv)
    print("full vs cached logits:", equal_logits)
    assert same_kv and equal_logits
    assert all(lengths == [1, 1] for lengths in projected.values())

    # 同样的后两枚 token，改动第一枚 token 后检查逐层缓存。
    changed = model(torch.tensor([[2, 5, 9]]), use_cache=True).past_key_values
    equal_suffix = [torch.equal(old.keys[:, :, 1:, :], new.keys[:, :, 1:, :])
                    for old, new in zip(saved.layers, changed.layers)]
    print("same suffix keys, layers 0/1:", equal_suffix)
    assert equal_suffix == [True, False]

    # 两条分支分别复制前缀缓存；DynamicCache.update 会修改传入对象。
    other = torch.tensor([[17]])
    branch = model(other, past_key_values=copy.deepcopy(saved),
                   attention_mask=torch.ones(1, 4, dtype=torch.long),
                   cache_position=torch.tensor([3]), use_cache=True)
    branch_full = model(torch.cat((prefix, other), dim=1), use_cache=False)
    branch_ok = torch.allclose(branch.logits[:, -1], branch_full.logits[:, -1], atol=1e-12, rtol=1e-10)
    wrong = model(next_id, past_key_values=copy.deepcopy(saved),
                  attention_mask=torch.ones(1, 4, dtype=torch.long),
                  cache_position=torch.tensor([0]), use_cache=True)
    wrong_position = not torch.allclose(wrong.logits[:, -1], full.logits[:, -1], atol=1e-12, rtol=1e-10)
    print("independent branch matches:", branch_ok)
    print("wrong position differs:", wrong_position)
    assert branch_ok and wrong_position and saved.get_seq_length() == 3
```

**真实运行 stdout，2026-09-15。** prefill/decode 后两个数字分别为缓存序列长度、全部层 K/V 的逻辑数据 bytes：

```text
prefill: 3 768
decode: 4 1024
new projection lengths: {'q': [1, 1], 'k': [1, 1], 'v': [1, 1]}
old KV unchanged: True
full vs cached logits: True
same suffix keys, layers 0/1: [True, False]
independent branch matches: True
wrong position differs: True
```

Hook 确认追加时每层 Q/K/V 都只投影 1 个位置，旧 K/V 逐元素不变；增量与完整前向的末位置 logits 在给定容差内一致。修改第一枚 token 后，第一层相同后缀的 K 仍相同，第二层却不同，体现了高层状态对前文的依赖；不能把它解释成“第一层缓存总能随意拼接”。错误位置的对照产生不同 logits，说明 cache 长度正确也不足以证明复用正确。

源码中 Llama 在 RoPE 之后缓存 K，`DynamicLayer.update` 沿序列维连接新 K/V，并修改缓存对象。这里的 deepcopy 只是小规模实验的分支隔离方法；生产引擎可用共享不可变前缀块与写时复制。`torch.cat` 也可能搬运旧数据并分配新张量，**数据复制不等于重新计算旧 token 的表示**。

### 5. 内存按哪些维度增长

对各层相同、K/V 形状相同、未量化且不共享前缀的 full-attention cache，逻辑数值大小为 `M_KV = 2 × L × B × S × H_kv × d_head × bytes_per_element`；异长序列用 `Σ_i S_i` 替代 `B×S`。`L` 是层数，`H_kv` 是 KV heads 而非 query heads，`S` 是已缓存位置数，dtype 决定每元素字节数。

本实验 `L=2、B=1、H_kv=2、d_head=4、float64=8 bytes`：长度 3 时为 `2×2×1×3×2×4×8=768 bytes`，长度 4 时为 1024 bytes；每追加一个 token 增加 **256 bytes**。若仅按相同形状换成 FP16 的存储口径，每 token 为 64 bytes，但本文未用 FP16 运行这组数值比较。

这不含权重、Python 对象、临时激活、复制产生的瞬时峰值和 allocator 预留。Static cache 可提前分配最大长度；分块、前缀共享、KV 量化、滑窗或 MLA 又会改变存储方式，不能只读张量逻辑大小就当作设备总占用。相关分项与取舍引用 [llm-0016](llm-0016-quantization-local-memory-budget.md)，不在这里重复整机容量表。

### 6. 请求内、跨请求和最终答案缓存的边界

| 缓存 | 命中时复用什么 | 仍需做什么 / 适用限制 |
| --- | --- | --- |
| 请求内 KV Cache | 当前推理序列各层已处理位置的 K/V | 追加位置的全部前向、对旧 K/V 的 attention 读取及采样；常规实现保留状态，不是多轮 API 自动持久会话的保证 |
| 跨请求前缀缓存 | 另一请求中兼容的完整前缀状态或缓存块 | 查找、调度、处理未命中后缀/必要边界位置、继续 decode；缓存可能未驻留、已淘汰或不在可复用范围内 |
| 最终答案缓存 | 满足业务复用条件的已完成输出 | 判断业务 key、有效期与权限，防止把过期或不适用答案返回；有效命中时可能跳过生成，但这不是 K/V 复用 |

跨请求不能只按“意思相近”命中 K/V。需要核对实际 token 前缀或输入表示、模型/adapter、位置与掩码、数值/缓存布局，以及多模态内容和允许共享的范围。文本字节稳定只是帮助维持 token 前缀的一种做法，不能取代这些兼容条件。若从中间改写了前文，其后的状态一般需要重算，哪怕某段后缀文字没变。

vLLM v0.11.0 的前缀缓存设计用父块哈希、当前块 token IDs 和额外信息标识缓存块，额外信息包含 LoRA、多模态输入和隔离 salt；该版本只缓存完整块。这提供了“相同后缀不够”的工程实例，并不意味着所有服务有相同块大小、命中边界或策略。工具前缀怎样布局仍参考 [agent-0047](agent-0047-tool-context-layout-for-prompt-cache.md)，上下文折叠的取舍参考 [agent-0043](agent-0043-kv-cache-friendly-context-compression.md)。

**跨请求命中不自动意味着免费或零计算。** APC 主要省去共享前缀的 prefill，后续生成仍要计算；是否收费、如何计缓存读写与输出由服务规则决定。显式缓存标记也不构成永久命中的通用保证，驻留、淘汰、最小命中粒度和请求兼容性仍需检查。计费字段的基础口径见 [llm-0007](llm-0007-tokenization-bpe-budget.md)。

有无缓存是空间与重算的取舍：长自回归输出通常适合保存 KV；极短输出或只做一次前向时收益可能有限。动态缓存按需增长但可能有分配成本，静态缓存便于固定形状优化却预占容量；跨请求共享还需要生命周期管理。应测具体负载的峰值、prefill/decode 时间与命中量，而不是直接套“节省百分比”。

## 延伸 / 追问

**追问 1：为何不把上一轮 attention 权重也缓存起来，下一步直接乘 V？**

下一步 query 与可见 key 集合可能不同，旧权重的分母也不再适用。K/V 可作为材料复用，当前行的打分和归一化仍要重算；手推例中沿用旧行就会得到错误输出。

**追问 2：相同后缀能否拿另一条请求的 K/V 接过来？**

通常不能，高层 K/V 依赖更早前文。本实验改首 token 后第二层相同后缀的 K 就变了。应复用兼容的完整前缀，从分叉点重算后续状态，并隔离不同分支对可变缓存的追加。

**追问 3：模型权重没变、cache 长度也对，输出仍不同，先检查什么？**

检查实际前缀、cache_position/position_ids、RoPE、padding/mask、追加顺序及 dtype/内核配置；用完整前向作对照，区分可容忍的浮点差异和系统性状态错配。仅有“命中”日志不能证明缓存语义正确。

## 常见误区

- **“KV Cache 存的是最终答案或旧注意力矩阵。”** 它保存逐层 K/V，最终答案缓存是另一种业务复用机制。
- **“追加时只算新增 token，因此不再读历史。”** 新 query 仍要读取可见历史 K/V，不能把常规 decode 说成与上下文长度无关。
- **“跨请求缓存命中就免费、零计算，或显式标记就永远命中。”** 共享前缀之外的计算、缓存生命周期与服务计费规则依然存在。
- **“token 内容相同就能复用它的高层 K/V。”** 还需要完整前缀与计算环境兼容；K/V 不是静态词向量表。

## 参考

- 课程线索：洛小山《AI 产品从入门到精通》learn-ai，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`；[slides/8-2.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/8-2.html)、[slides/8-2b.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/8-2b.html)、[slides/ds-6.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/ds-6.html)、[slides/algo-2.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/algo-2.html)。正文和实验独立编写，不搬运 AGPL 素材；未采用课程固定省钱比例、保证命中或复杂度等同账单的判断。
- Hugging Face，[Transformers v4.57.1 Caching](https://huggingface.co/docs/transformers/v4.57.1/cache_explanation)：逐层 KV、cache_position 和缓存存储的一手说明。
- Transformers **v4.57.1**，固定 commit `8cb5963cc22174954e7dca2c0a3320b7dc2f4edc`：[LlamaAttention.forward，L235 起](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/models/llama/modeling_llama.py#L235)，投影、RoPE、cache update 与 attention；[DynamicLayer.update，L98 起](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/cache_utils.py#L98)，沿序列维追加。本文实际使用此版本运行随机初始化的小模型。
- vLLM **v0.11.0**，固定 commit `b8b302cde434df8c9289a2b465406b47ebab1c2d`：[Prefix caching design](https://github.com/vllm-project/vllm/blob/b8b302cde434df8c9289a2b465406b47ebab1c2d/docs/design/prefix_caching.md)、[APC features and limits](https://github.com/vllm-project/vllm/blob/b8b302cde434df8c9289a2b465406b47ebab1c2d/docs/features/automatic_prefix_caching.md)。用于前缀键和 prefill/decode 边界，不声称已运行 vLLM 服务。以上一手来源核实日期 **2026-09-15**。
