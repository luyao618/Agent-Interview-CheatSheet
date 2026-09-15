---
id: llm-0009
title: Base 模型如何通过 Chat Template 与 SFT 变成对话模型，模板不匹配会怎样？
category: llm
tags: [chat-template, sft, instruction-tuning, special-tokens, serialization]
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

Base 模型如何通过 Chat Template 与 SFT 变成对话模型，模板不匹配会怎样？请展示同一组 messages 的正确序列化与错误模板对照，并区分模板格式、训练权重和角色权限的作用。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**Chat Template 规定消息怎样变成 token 序列，SFT 则通过训练，让模型在这种序列条件下更稳定地生成期望的 assistant 回答。** 模板改变输入结构，训练改变可训练参数；只给 Base 模型套上角色标记，不等于已经得到一个经过指令微调的 Chat 模型。Chat 模型依然可以用自回归 next-token 目标训练和生成，基本循环见 [llm-0008](llm-0008-next-token-training-inference.md)。

### 1. 从 Base 到 Chat：格式和训练怎样配合

Base 模型经过预训练，已经能续写文本，也可能在合适提示下续写对话。对话微调的目标是让它更稳定地遵循任务、识别角色和轮次，并生成符合要求的回应；不能把 Base 与 Chat 简化为“完全不会聊天”和“突然获得聊天架构”。

一条典型的训练与部署链路是：

1. **准备示范数据**：将指令、历史和期望回答组织为 messages，明确哪些内容属于 system、user、assistant，必要时还有工具消息。送入普通文本 causal LM 前仍要编码为 token 序列；messages 不是模型直接接收的宿主语言对象。
2. **使用匹配的 tokenizer/template 序列化**：由模板加入角色头、消息结束标记、换行等，得到文本或 token ID。Jinja 是宿主程序使用的模板语言，模型接收渲染后的 token 序列，不执行 Jinja。写一个特殊字符串也不会自动注册新的 token ID；增加 special tokens 时，还需处理 tokenizer、embedding/输出词表与训练的配套。
3. **构造监督目标并做 SFT**：使用高质量 assistant 示范作为目标，以 teacher forcing 计算 next-token loss，再反向传播更新模型或 adapter 参数。常见的 assistant-only 训练只监督 assistant 回答及相应结束标记；也有全序列监督等配置，必须明确自己的 loss mask，不能假设“应用了模板”就自动做好了标签。
4. **按同一格式部署**：输入使用与训练相容的角色结构、控制 token 和结束约定；发起一条新回复时，把前缀停在适当的 assistant 起点，再调用生成。模板、tokenizer、权重/adapter 和生成配置应作为一个经过验证的版本组合管理。

若监督位置集合为 `M`，可将 SFT 目标写成 `L(θ) = -Σ_{t∈M} log pθ(x_t | x_<t)`。模板影响 `x` 如何排列，loss mask 决定 `M`，优化器更新 `θ`；三者是不同工作。训练样本通常已经包含目标 assistant 回答，因此不需要在完整样本末尾再追加一个空的 assistant 开头。本题只复现序列化，没有运行 SFT，也没有测量训练后的收益。

**SFT 不只是改语气。** 示范可以教任务完成方式、输出格式、何时拒答、如何按约定调用工具等行为，前提是数据和训练目标包含这些要求；它也不保证事实必然正确或从此不会受干扰。Ouyang 等人的 InstructGPT 工作先用人工示范做 SFT，再进行偏好相关训练；不能把其整套方法的结果都归因于 SFT 单独一步。何时进一步采用 RL，参见 [llm-0005](llm-0005-agent-training-sft-to-rl-switch.md)。

### 2. Chat Template 要匹配哪些细节

| 细节 | 作用与常见错误 |
| --- | --- |
| 角色边界 | 区分每条消息的说话方与内容；把 system/user/assistant 正文简单拼接，会丢失训练格式中的结构 |
| assistant 起点 | 指示下一段生成从哪里开始；漏掉某些模型所需的头部，可能变成续写 user 或其他片段 |
| 消息结束与生成停止 | 消息结束标记界定历史轮次；模型新生成的结束 ID 可以触发停止，输入历史里已有这些 ID 并不意味着一开始就停止 |
| special tokens 与空白 | 控制字符串需要按目标 tokenizer 映射；换行、空格、BOS/EOS 都可能影响 token 序列，不能凭外观看起来相似就判为相容 |
| 模板版本与分支 | 同模型系列、同 Base 衍生的不同 Chat 模型也可能格式不同；工具、推理、多模态分支不能靠一份普通文本模板推断 |

`add_generation_prompt=True` 与“继续一条已有 assistant 前缀”不是同一个操作。在 Transformers 中，后者可以用 `continue_final_message=True` 表达，两者不能同时开启。是否需要 generation prompt、具体加什么，由模板决定，不是所有模型都统一追加 `assistant:`。历史 reasoning 内容的特殊约定见 [llm-0003](llm-0003-chat-template-reasoning-content-retention.md)。

模板不匹配常常**仍能成功渲染、编码并返回输出**，但输入已经偏离模型习惯的格式，可能表现为角色混淆、续写错误位置、格式失控或结束行为异常。需要结合完整渲染文本、token ID、生成配置及任务评测定位；“能调用成功”不是兼容性证明，也不能只根据一次差回答就认定模板一定错了。

### 3. 固定公开模板的真实序列化对照

使用 **Qwen/Qwen2.5-0.5B-Instruct** 的公开 tokenizer/template，固定 revision 为 `7ae557604adf67be50417f59c2c2f167def9a775`。仅加载 tokenizer 文件，不加载模型权重；messages 是自编输入，其中的历史 assistant 回答“2。”也是示例数据，并非本次调用模型生成。

运行环境与日期：**2026-09-15，macOS arm64，Python 3.11.8，Transformers 4.57.1，tokenizers 0.22.2，Jinja2 3.1.6，huggingface-hub 0.36.2**。先安装：

```sh
python -m pip install transformers==4.57.1 tokenizers==0.22.2 jinja2==3.1.6 huggingface-hub==0.36.2
```

将以下代码保存为 `template_compare.py`，执行 `python template_compare.py`。首次需要联网获取固定 revision 的 tokenizer 文件；不需要 PyTorch 或 GPU。

```python
from importlib.metadata import version
from transformers import AutoTokenizer

assert version("transformers") == "4.57.1"
MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
tokenizer = AutoTokenizer.from_pretrained(
    MODEL, revision=REVISION, trust_remote_code=False
)
messages = [
    {"role": "system", "content": "用中文简短回答。"},
    {"role": "user", "content": "1 + 1 等于多少？"},
    {"role": "assistant", "content": "2。"},
    {"role": "user", "content": "再加 1 呢？"},
]
# 故意错误：只保留正文，丢弃角色、消息边界和新 assistant 起点。
bad_template = "{% for m in messages %}{{ m['content'] + '\\n' }}{% endfor %}"
good = tokenizer.apply_chat_template(
    messages, tokenize=False, add_generation_prompt=True
)
bad = tokenizer.apply_chat_template(
    messages, chat_template=bad_template, tokenize=False,
    add_generation_prompt=True,
)
good_ids = tokenizer.apply_chat_template(
    messages, tokenize=True, add_generation_prompt=True
)
bad_ids = tokenizer(bad, add_special_tokens=False)["input_ids"]
assert good_ids == tokenizer(good, add_special_tokens=False)["input_ids"]
assert good.endswith("<|im_start|>assistant\n")
assert bad == "".join(m["content"] + "\n" for m in messages)
start_id = tokenizer.convert_tokens_to_ids("<|im_start|>")
end_id = tokenizer.convert_tokens_to_ids("<|im_end|>")
assert good_ids.count(start_id) == 5 and good_ids.count(end_id) == 4
assert start_id not in bad_ids and end_id not in bad_ids
assert good_ids != bad_ids
without_prompt = tokenizer.apply_chat_template(
    messages, tokenize=False, add_generation_prompt=False
)
assert good == without_prompt + "<|im_start|>assistant\n"
try:
    tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, continue_final_message=True
    )
except ValueError:
    pass
else:
    raise AssertionError("两种续写模式不应同时开启")
print("GOOD")
print(good)
print("BAD")
print(bad)
print(f"tokens: good={len(good_ids)}, bad={len(bad_ids)}")
print(f"special IDs: im_start={start_id}, im_end={end_id}")
print("boundary checks: OK")
```

实际 stdout 如下。`GOOD`、`BAD` 和统计行是程序打印的标签，不属于送给模型的输入；未安装模型计算后端时，库可能另向 stderr 输出仅 tokenizer 可用的提示。

```text
GOOD
<|im_start|>system
用中文简短回答。<|im_end|>
<|im_start|>user
1 + 1 等于多少？<|im_end|>
<|im_start|>assistant
2。<|im_end|>
<|im_start|>user
再加 1 呢？<|im_end|>
<|im_start|>assistant

BAD
用中文简短回答。
1 + 1 等于多少？
2。
再加 1 呢？

tokens: good=49, bad=26
special IDs: im_start=151644, im_end=151645
boundary checks: OK
```

正确结果保留四条消息的边界，并在末尾打开第五个消息头，等待生成新的 assistant 内容；错误模板忽略了 `add_generation_prompt` 参数，也没有输出任何角色标记。**49 与 26 的单位是本次 tokenizer 输出的 token 数，不是质量、费用或安全性测量。** 这个实验验证了格式与 ID 的不同，没有验证模型在错误模板下会具体回答什么，更没有测量准确率下降幅度。

已渲染的模板文本再编码时使用 `add_special_tokens=False`，避免对本已包含控制 token 的文本重复添加 BOS/EOS；更直接的路径是 `apply_chat_template(..., tokenize=True)`。本例原生模板未声明用于提取 assistant mask 的 `{% generation %}` 区块，因此不能将“渲染成功”视为“assistant-only SFT 的标签已经正确”；训练时还需验证自己的监督位置和结束 token。

### 4. 选择现成模型，还是自行设计模板并训练

| 方案 | 适用条件 | 代价与不适用场景 |
| --- | --- | --- |
| 使用现成 Instruct/Chat 权重及其匹配模板 | 通用问答、业务验证，希望尽快建立可靠基线 | 需遵守其角色、工具和模板约定；若必须采用完全不同的协议，不能只换模板文件就认定兼容 |
| 定义数据格式，对 Base 或已有模型做 SFT | 有代表性示范、训练资源与评测能力，确实需要改变任务行为或协议 | 要维护数据、loss mask、tokenizer/权重版本及回归评测；仅因显示层想换消息样式就重训通常不合适 |

更换模型时可以复用应用层 messages，但序列化应交给对应模型的模板；使用托管 API 时还要遵守服务商接受的消息契约，不能把本例 Qwen 控制字符串当作所有 API 的统一协议。API 路径叫“chat”“messages”还是“completions”，也不能证明内部使用哪套模板。

### 5. 角色标记为什么不是安全隔离

角色结构有助于模型学习谁在说话、应该如何遵循指令，**标记不是加密，也不是物理权限隔离**。在本例 tokenizer 中，`<|im_start|>` 是注册的控制 token，正文中出现同样字面量也可以编码成该 ID；这不等于攻击一定成功，却说明不能仅靠一个分隔符承诺安全。

应用应在可信代码中构造角色和消息，避免把不可信内容直接拼成高权限消息，并在工具执行层落实真实的鉴权与参数验证。模型输出“我是 system”不会赋予它数据库或文件权限；同样，SFT 学过角色边界也不证明它能抵抗所有 prompt injection。安全判断需要单独验证，不能由本题的序列化测试代替。

## 延伸 / 追问

**追问一：给 Base 模型增加同款 Chat Template，为什么可能看起来能回答，却仍不等于完成 SFT？**

Base 可能利用预训练中学到的对话模式或上下文示例进行续写；模板只提供条件序列，没有触发梯度更新。要判断是否训练过，应核对权重/adapter 版本和训练记录；单个流畅回答不能证明模型已具备稳定的指令遵循能力。

**追问二：换模型后仍能调用成功，但它开始续写用户消息，该查什么？**

先核对新权重对应的 tokenizer/template revision、实际渲染文本、assistant 起点、结束 ID 和是否重复添加 special tokens，再区分新建 assistant 回复与继续已有前缀。保存固定 messages 的渲染/ID 对照并做端到端评测；不能仅凭两边都接受同一份 messages JSON 就认为底层格式相同。

**追问三：用户正文写了角色控制标记，是否就真的变成 system 消息？**

宿主程序记录的角色与权限不会因此自动改变，但模型看到的 token 流可能受到影响。应按模型和服务接口的契约处理这类内容，并让外部执行权限始终由可信代码控制；不能把“role 字段仍为 user”或“模型受过 SFT”当成抵抗注入的完整保证。本题未测量这类攻击的成功率。

## 常见误区

- **“Chat Template 本身让 Base 权重学会了对话。”** 模板做序列化，SFT 更新可训练参数；二者作用不同。
- **“SFT 只是把话说得更客气。”** 它能训练任务行为与输出约定，效果取决于示范、目标和评测，也会有局限。
- **“角色 token 天然构成安全隔离。”** 它们是模型输入结构，不是密码学认证或不可跨越的权限边界。
- **“消息拼完不能有换行，能 tokenize 就说明模板正确。”** 本例真实模板明确包含换行；错误格式同样可以编码成功。

## 参考

答案及对照代码独立编写，learn-ai 仅作学习线索，未移植其 AGPL 正文、代码或图片。实验使用公开 tokenizer/template，不涉及模型权重训练，也不宣称完成了 Base 与 Chat 的效果对比。

- 洛小山，《AI 产品从入门到精通》learn-ai，固定版本 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/1-2-fake-chat.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/1-2-fake-chat.html)、[slides/1-2-sft.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/1-2-sft.html)、[slides/1-2-api.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/1-2-api.html)。
- Qwen Team，Qwen2.5-0.5B-Instruct，固定 revision `7ae557604adf67be50417f59c2c2f167def9a775`：[tokenizer_config.json](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/blob/7ae557604adf67be50417f59c2c2f167def9a775/tokenizer_config.json) 的 `chat_template`、`added_tokens_decoder`、`eos_token` 字段，实验的模板与 token ID 依据；访问日期 2026-09-15。
- Hugging Face，**Transformers v4.57.1**，固定 commit `8cb5963cc22174954e7dca2c0a3320b7dc2f4edc`：[Chat templates 文档](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/docs/source/en/chat_templating.md)，重点为格式差异、重复 special tokens、两种续写模式与 Model training 小节。
- 同一 Transformers commit：[`tokenization_utils_base.py::apply_chat_template` L1546](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/tokenization_utils_base.py#L1546)，续写模式校验与 `add_special_tokens=False` 编码在该函数内；[`utils/chat_template_utils.py::render_jinja_template` L466](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/utils/chat_template_utils.py#L466)，模板渲染与 assistant mask 提取使用不同分支。
- Ouyang et al., *Training language models to follow instructions with human feedback*, 2022：[arXiv:2203.02155v1](https://arxiv.org/abs/2203.02155v1)，人工示范 SFT 与后续 RLHF 的一手研究，本文不引用其效果数字作为 SFT 单独收益；访问日期 2026-09-15。
