---
id: llm-0007
title: Token、字符与词有什么区别，BPE 如何影响多语言产品的上下文和成本预算？
category: llm
tags: [tokenization, bpe, multilingual, context-window, cost]
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

Token、字符与词有什么区别，BPE 如何影响多语言产品的上下文和成本预算？请用指定 tokenizer 实测同一语义的中文、英文与代码，并说明估算与实际账单的边界。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**Token 是 tokenizer 输出序列中的单位，字符是文本表示的单位，词是语言学单位，三者没有固定换算比例。** 模型处理的是 token ID 序列；同一句话换了 tokenizer，序列长度就可能改变。多语言产品应按目标模型的编码规则测量真实内容，再分别做上下文容量预算和计费预算。

### 1. 从文本到 token ID

| 概念 | 含义 | 为什么不能直接换算 |
| --- | --- | --- |
| 字符 | 必须先约定口径：Unicode code point、用户看到的字素簇，或其他计数单位 | `é` 可以用一个 code point 表示，也可由 `e` 加组合重音表示；UTF-8 字节数又不同 |
| 词 | 有语言意义的单位，如英文单词或中文词语 | 中文不靠空格自然分词；一个英文单词也可能拆成多个 token |
| Token | 词表中某个条目在序列里的一次出现，编码为整数 ID | 可能是整词、子词、空格加词、标点，甚至一个字符的部分字节；不保证独立有语义 |

词表把可编码片段映射为 ID；**token 数数的是序列长度，不是不同 ID 的个数**。对 byte-level BPE，普通条目表示字节片段，完整序列的字节拼回后才解码为文本。单个 token 未必恰好落在 UTF-8 字符边界。这里讨论有效 Unicode 文本；不能把无损往返的结论推广到非法 surrogate 输入或任意截断的 token 序列。

### 2. BPE：训练时学合并，编码时用既定规则

以本题实测的 **tiktoken 0.12.0** 为例，主线是：

1. **训练阶段的概念模型**：先按预切分规则形成片段，再将片段表示为 UTF-8 字节。以 256 个单字节为基础，反复统计当前相邻符号对，合并频率最高的一对，并记录优先级，直到达到词表目标。合并后的符号还可以参与下一次合并。这是 byte-level BPE 的教学过程，不表示本题重新训练了官方词表。
2. **编码阶段**：加载固定词表、merge ranks 和预切分正则；在每个普通片段内，优先合并 rank 最小的可合并相邻对，直到不能合并，输出 ID。不会根据当前用户的一句话重新统计频率、更新词表。
3. **special tokens 另行处理**：结束标记、填空标记等是协议约定的保留 ID，不靠普通 BPE 频次自然产生。哪些标记受支持、是否自动添加、如何解释，取决于 tokenizer、chat template 和模型协议；仅对字符串调用 `encode()` 不等于构造了完整聊天请求。

可核对一手源码：`tiktoken/_educational.py` 的 `bpe_train` / `bpe_encode` 展示前两步；实际 Rust 编码入口 `src/lib.rs::encode_ordinary` 先正则切片，整片命中词表时直接返回 ID，否则进入 `byte_pair_encode` / `_byte_pair_merge`。词表文件、校验 hash 和正则在 `tiktoken_ext/openai_public.py`，见参考中的固定 commit。

**Trie 是数据结构，BPE 是切分算法，不能把所有 tokenizer 等同于 Trie 最长匹配。** 一个纯示意反例：初始符号为 `a,b,c`，先学到 `b+c→bc`，后学到 `a+b→ab`，没有 `abc`。对 `abc`，按合并优先级得到 `a | bc`；从左侧贪婪最长匹配会得到 `ab | c`。词表相同也不足以保证结果相同，还必须看算法、merge rank、预切分及 special-token 策略。

### 3. 多语言取舍：词表覆盖影响长度，长度不是总成本

训练语料的语言分布、词表大小、预切分与合并规则，会影响哪些文本片段能够合成一个 token。罕见字、专业术语、代码命名、空白与 Unicode 表示都可能改变计数。字节基础让有效文本即使没有整词条目也可编码，但不保证切分紧凑，也不表示模型理解了这个词。

| 产品方案 | 适用条件 | 代价与不适用场景 |
| --- | --- | --- |
| 保留用户原语言，用目标模型的 tokenizer 测量和限额 | 要保留原话、术语、引用或代码；通常作为基线 | 需要按语言和任务评测长度、质量、延迟；当前模型若对主要语言表现很差，仅放宽 token 限额不足以解决问题 |
| 先翻译成统一语言，再调用模型，必要时回译 | 可接受语义改写，且实测端到端质量、成本更合适的任务 | 多出翻译调用、延迟和语义损失；精确引文、合同措辞或代码标识符处理不适合仅为省 token 而翻译 |

若多个候选模型都满足任务质量，也可以对比它们在真实语料上的 tokenizer 压缩率；但应同时计算单价与生成量。**不能给现成模型随意换一个更省 token 的词表**：ID 必须与该模型训练时的 embedding 和输出词表对应。更大的词表也增加相关参数与计算开销，不能据 token 数断言模型一定更快、更便宜。

### 4. 可复现计数：同一任务的中文、英文与代码

共同语义为“返回两个数的和”：中文和英文描述该操作，Python 代码实现该操作；这不是把三种输入当成相同的任务完成度。为控制变量，代码仅考虑数值参数。所有字符串保持原样，不做归一化；代码含四个缩进空格和最后一个换行。

**真实运行口径：2026-09-15，macOS arm64，Python 3.11.8，tiktoken 0.12.0；分别指定 `cl100k_base` 和 `o200k_base`。** 只计算普通文本，不包含消息角色、chat template、工具 schema 或服务端开销。未调用模型 API，也未产生实际账单。首次加载 encoding 需要联网下载词表，库按固定 hash 校验。

在 Python 环境安装 `python -m pip install tiktoken==0.12.0`，将下列代码保存为 `token_counts.py`，执行 `python token_counts.py`：

```python
import tiktoken

assert tiktoken.__version__ == "0.12.0"
samples = {
    "zh": "返回两个数的和。",
    "en": "Return the sum of two numbers.",
    "code": "def add(a, b):\n    return a + b\n",
}
print("encoding label codepoints utf8_bytes tokens")
for name in ("cl100k_base", "o200k_base"):
    enc = tiktoken.get_encoding(name)
    for label, text in samples.items():
        ids = enc.encode(text)
        assert enc.decode(ids, errors="strict") == text
        print(name, label, len(text), len(text.encode("utf-8")), len(ids))

    # 边界验证：空串、special-token 策略、不同 Unicode 表示。
    assert enc.encode("") == []
    marker = "<|endoftext|>"
    try:
        enc.encode(marker)
    except ValueError:
        pass
    else:
        raise AssertionError("默认应拒绝此 special-token 字面量")
    assert len(enc.encode(marker, allowed_special={marker})) == 1
    assert len(enc.encode(marker, disallowed_special=())) == 7
    assert len(enc.encode("é")) == 1
    assert len(enc.encode("e\u0301")) == 2
    assert len(enc.encode("🙂")) == (2 if name == "cl100k_base" else 1)
print("boundary checks: OK")
```

实际输出（`codepoints` 为 Python `len(str)`，不是屏幕上看到的字符数）：

```text
encoding label codepoints utf8_bytes tokens
cl100k_base zh 8 24 7
cl100k_base en 30 30 7
cl100k_base code 32 32 12
o200k_base zh 8 24 6
o200k_base en 30 30 7
o200k_base code 32 32 12
boundary checks: OK
```

这个小样本中，中英文本在 `cl100k_base` 下相同，在 `o200k_base` 下中文反而更少；足以反驳“中文固定贵若干倍”，**不足以估计整个产品的平均比例**。代码虽实现同一操作，语法与空白也参与编码，不能按自然语言字数推算。两个 encoding 下代码长度相同也不意味着 token ID 相同。

special-token 检查中的两种设置含义不同：`allowed_special={marker}` 将它识别为保留 ID；`disallowed_special=()` 将它当普通文本编码，**不会删除它**。处理用户原文时按接口协议选择拒绝或普通文本编码，不应为了消除异常就允许所有保留标记。

### 5. 把计数用于上下文与费用预算

**容量预算按完整请求算。** 设 `I` 为组装后的输入 token 数，含系统指令、历史、检索内容、工具定义/结果及协议开销；`R` 为本次生成预留，`M` 为安全余量，`W` 为目标模型的上下文上限，单位都是 token：

```text
I + R + M ≤ W
R ≤ 该模型/接口的最大输出上限
```

若接口还有独立输入限制，也必须满足。对 OpenAI reasoning 接口，`R` 需覆盖 reasoning、可见文本及相应生成格式开销；不能只给最终回答留空间。上限、截断策略和计算规则须按具体模型 snapshot 核对。原始字符串的本地计数仅覆盖 `I` 的一部分；应使用服务商计数接口或模型匹配的完整 template 估算，再以实际 `usage` 校准，不能硬编码“每条消息固定加几个 token”通用于所有模型。

**费用预算按实际用量分类计价。以下简式仅适用于无独立 cache-write 费率的纯文本请求。** 设 `I_c` 是 `I` 中命中缓存读取的部分，`O` 为实际计费输出，单价 `p_in`、`p_cache`、`p_out` 的单位为美元 / 百万 token：

```text
费用（美元）= ((I - I_c) × p_in + I_c × p_cache + O × p_out) / 1,000,000
```

这里 `I_c` 是输入的子集，不能再加一次完整输入价；输出预留 `R` 用于限额和预算，不代表最终消耗了 `R`。OpenAI `usage.output_tokens` 已包含其中的 reasoning tokens，不能再把 `output_tokens_details.reasoning_tokens` 重复相加。多次调用逐次求和；工具费、图像/音频或其他计费项目另按合同规则核算，不套用本地文本计数。

**以下是无独立 cache-write 费率的预算算例，不是模型报价或实测账单（编写于 2026-09-15）**：假设 `I=5,000`、`I_c=3,000`、`O=1,000` token，三种单价分别为 `2`、`0.5`、`8` 美元 / 百万 token，则费用为 `(2,000×2 + 3,000×0.5 + 1,000×8)/1,000,000 = 0.0135` 美元。即便有缓存折扣，缓存内容仍占本次上下文容量；价格优惠不会把窗口变大。

**存在独立缓存写入用量及费率时，须分为普通输入、缓存读取、缓存写入三类。** 以 OpenAI 的 `usage` 口径为例，`I_c` 对应 `input_tokens_details.cached_tokens`，另设 `I_w` 对应 `input_tokens_details.cache_write_tokens`；两者是总输入 `I=input_tokens` 中互斥的部分，普通输入为 `I-I_c-I_w`，三类数量均应非负。设 `p_write` 为缓存写入的完整单价，单位同为美元 / 百万 token：

```text
费用（美元）= ((I - I_c - I_w) × p_in + I_c × p_cache + I_w × p_write + O × p_out) / 1,000,000
```

不能把 `I_w` 一概按普通输入价处理，也不能在已经为它收取普通输入价后，再叠加完整的 `p_write`。OpenAI 官方 Prompt caching 文档在 **2026-09-15 核实**时规定，GPT-5.6 及以后模型的缓存写入、读取费率分别为普通输入价的 **1.25 倍、0.1 倍**；其他模型、服务商或后续版本须核对自己的字段与费率，不能套用这两个倍数。

**分类计价算例（2026-09-15 验证，仅计算输入费）**：采用官方文档第二次请求的示例用量 `I=15,000`、`I_c=12,000`、`I_w=3,000` token，另假设普通输入单价为 `2` 美元 / 百万 token（不是模型报价）。按上述已核实比例，读取价为 `0.2`、写入价为 `2.5`，普通输入数量为 `0`。输入费为 `(0×2 + 12,000×0.2 + 3,000×2.5)/1,000,000 = 0.0099` 美元；误用简式会得到 `0.0084` 美元，少计 `0.0015` 美元。输出费仍需另加，示例用量也不代表本题实际调用过 API。

上线前按语言、代码比例和任务类型抽样，记录 token 分布、输出长度与失败率；容量关注长尾和最大值，费用预测结合调用量与真实单价。模型或 template 升级后重测。具体 Agent 降本手段参见 [agent-0038：Agent 节省 Token 成本](agent-0038-reduce-agent-token-cost.md)，本题聚焦这些优化之前的计量基础。

## 延伸 / 追问

**追问一：换模型后，同样的文本从 1,000 token 降到 700，是否就便宜 30%？**

不能直接下结论。先确认 tokenizer 与模型匹配，再比较普通输入/缓存读取/缓存写入/输出单价、输出量、翻译或重试调用以及任务质量；更少的输入 token 只改变成本公式中的一个量。重新计数后也要验证 template 开销和上下文余量，不能沿用旧模型的整数 ID。

**追问二：按 token 数截取中文，为什么有时末尾出现 `�`？**

byte-level token 的边界可能位于 UTF-8 字符内部，截断后默认宽容解码会插入替换字符。应在合法文本边界选择截断点，严格解码验证，再重新编码并确认仍符合预算；必要时继续缩短。不能把每个 token 分别解码为字符串再拼接；排查时可用 `decode_single_token_bytes` 看真实字节。

**追问三：本地只数出 2,000 token，API 却报告更大的输入量，是 tokenizer 一定错了吗？**

不一定。先核对实际发送的完整请求、模型/encoding 版本、历史消息、工具 schema、附件和 special-token/template 规则；本地文本计数与服务端完整输入可能本来就不是同一口径。输出账单也可能含不可见 reasoning 开销，应结合 `usage` 的分类字段定位差异。

## 常见误区

- **“一个汉字 / 单词固定等于若干 token。”** 不能把字数比例当常数；编码、文本分布、空白和 Unicode 表示都会影响结果。
- **“所有 tokenizer 都是 Trie 最长匹配。”** 数据结构不能代替算法定义；本题固定版本的 tiktoken 按预切分与 merge rank 工作。
- **“本地 `encode()` 的长度就是 API 账单。”** 它只测传入字符串；完整请求与输出还有协议、工具或 reasoning 等开销，结算应核对服务端用量及费率。
- **“BPE 学会了语义，新词会自动加入词表。”** 编码期通常使用固定词表；能用字节表示新词，与模型能否正确理解它是两回事。

## 参考

以下内容为独立组织的问答与自编实验；learn-ai 仅作为选题和学习线索，未移植其 AGPL 课件正文、代码或图片，也未沿用其示意价格或固定语言倍数。

- 洛小山，《AI 产品从入门到精通》learn-ai，固定版本 `5a933d287dd5074cc1543cb849146f3261d47521`，学习路径：[slides/1-2-vocab.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/1-2-vocab.html)、[slides/cost-2.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/cost-2.html)、[slides/ds-9.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/ds-9.html)、[slides/zero-q-token.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/zero-q-token.html)。
- OpenAI，**tiktoken 0.12.0**，固定 commit `97e49cbadd500b5cc9dbb51a486f0b42e6701bee`：[教学训练与编码 `tiktoken/_educational.py`，`bpe_encode` L83 / `bpe_train` L119](https://github.com/openai/tiktoken/blob/97e49cbadd500b5cc9dbb51a486f0b42e6701bee/tiktoken/_educational.py#L83)；[运行时 `src/lib.rs`，`_byte_pair_merge` L17](https://github.com/openai/tiktoken/blob/97e49cbadd500b5cc9dbb51a486f0b42e6701bee/src/lib.rs#L17)、[`encode_ordinary` L232](https://github.com/openai/tiktoken/blob/97e49cbadd500b5cc9dbb51a486f0b42e6701bee/src/lib.rs#L232)。用于核对机制，而非从课程推断实现。
- 同一 tiktoken commit：[编码定义及词表 hash `tiktoken_ext/openai_public.py`，L75 / L95](https://github.com/openai/tiktoken/blob/97e49cbadd500b5cc9dbb51a486f0b42e6701bee/tiktoken_ext/openai_public.py#L75)；[special-token 策略 `tiktoken/core.py::encode`，L79](https://github.com/openai/tiktoken/blob/97e49cbadd500b5cc9dbb51a486f0b42e6701bee/tiktoken/core.py#L79)；[解码与 UTF-8 边界 `decode`，L272](https://github.com/openai/tiktoken/blob/97e49cbadd500b5cc9dbb51a486f0b42e6701bee/tiktoken/core.py#L272)。
- OpenAI 官方文档，[Conversation state — Managing the context window](https://developers.openai.com/api/docs/guides/conversation-state#managing-the-context-window)，访问日期 2026-09-15；上下文与输出限制按模型核对。
- OpenAI 官方文档，[Reasoning models — Managing the context window](https://developers.openai.com/api/docs/guides/reasoning#managing-the-context-window)，访问日期 2026-09-15；核对 reasoning 的上下文占用、输出计费和 `usage` 字段。
- OpenAI 官方文档，Prompt caching：[How caching works — GPT-5.6 and later](https://developers.openai.com/api/docs/guides/prompt-caching#how-caching-works-gpt-5-6-and-later)、[Monitor cache performance](https://developers.openai.com/api/docs/guides/prompt-caching#monitor-cache-performance)，访问并核实日期 2026-09-15；核对缓存写入/读取费率比例、第二次请求示例用量，以及按 `input_tokens`、`cached_tokens`、`cache_write_tokens` 分类计价的口径。本文中的美元绝对单价均是假设，并非具体模型报价。
