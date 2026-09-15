---
id: llm-0019
title: 文生图与参考图生图怎样选择，如何保持角色一致性并决定是否增加 Prompt 改写层？
category: llm
tags: [image-generation, conditioning, character-consistency, prompt-rewriting, evaluation]
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

文生图与参考图生图怎样选择，如何保持角色一致性并决定是否增加 Prompt 改写层？请设计同一角色换场景的对照矩阵，分别验收身份、服装和风格，并说明 seed、改写保真与额外延迟的边界。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**先明确哪些角色属性不能变，再选择能传递这些条件的生成方式；参考图和 Prompt 改写都要通过分项对照验证。** 一张图“很漂亮”、衣服颜色相同或 seed 相同，都不足以证明它仍是目标角色。

本题讨论图像条件与一致性评估。需要长期定制角色时，LoRA 可作为备选，原理见 [llm-0001](llm-0001-lora-fine-tuning.md)；它是参数适配方法，不是参考图输入的同义词。随机采样的确定性限制也可对照 [llm-0012](llm-0012-decoding-sampling-beam.md)。

### 1. 先问清“参考图”进入模型的哪一层

以 latent diffusion 为例，文生图通过文本编码等条件引导从噪声逐步生成图像；文本中的“红狐、短外套”描述的是语义集合，通常不能唯一指定一个角色实例。角色名字也不会自动让独立请求共享外貌记忆。其他生图架构或托管 API 的内部实现可能不同，不能把这一机制套到所有模型。

| 方案 | 条件如何起作用 | 适合什么 | 主要取舍与不适用场景 |
| --- | --- | --- | --- |
| 纯文生图 | 通过文本说明对象、场景、构图和风格 | 探索新角色、海报草图，没有严格实例身份约束 | 门槛低、变化自由；重复相同描述也可能换脸/换轮廓，不适合未经验收就批量交付固定角色 |
| 初始图重绘 / 局部编辑 | 某些 diffusion img2img 将初始图编码、加噪后再去噪；inpainting 还指定编辑区域 | 保留已有构图、局部换背景或修正服饰 | 保留与变化之间存在取舍，遮罩边缘和未编辑区域也要检查；强行大幅换姿态可能受原构图限制 |
| 图像条件 / 身份参考 | 如 IP-Adapter 为图像特征提供独立于文本的条件分支 | 保留可视身份线索，同时更换场景 | 不等于像素复制或硬性身份锁；可能连衣服、风格、背景一起带入，过强参考也可能损害场景服从 |
| 空间条件控制 | 如 ControlNet 使用边缘、深度、姿态等条件 | 固定姿态、布局或轮廓 | 能控制“怎么站/放在哪”，不能仅凭骨架保证“是谁” |
| 主体定制训练 | 如 DreamBooth 学习主体与标识的关联；可评估 LoRA 等参数适配方式 | 参考条件仍不够、长期反复使用且有足够合法素材的角色 | 有数据、训练和维护成本，可能把某套衣服/背景与身份过度绑定；不宜为一次性任务贸然训练 |

“保留强度”不是跨接口通用旋钮。Diffusers v0.35.1 的 img2img `strength` 与 IP-Adapter 的 `set_ip_adapter_scale` 分别影响初始图重绘和图像条件权重，含义不同；不能把同一个数值直接搬到另一模型，也不能把权重解释为“身份正确概率”。应在独立校准样本上选择范围，再锁定参数进入验收集，不能看完测试图后只留下最有利的设置。

### 2. 把身份、服装、风格拆成契约

下面是**原创文字角色设定与实验设计，未生成参考图或测试图片，没有实际生图效果数据**。虚构拟人赤狐“小岚”的三份契约如下；编号只是记录键，真正给模型的 Prompt 要展开字段，不能只传编号期待模型知道内容。

| 维度 | 本例必须保持的条件 | 如何验收 |
| --- | --- | --- |
| 身份 I0 | 短圆口鼻、琥珀眼、奶油色心形额斑、角色自身左耳尖缺口、白色尾尖及固定体态比例 | 与基准设计逐项核对形状和局部标记，再看跨场景是否仍为同一角色；左耳按角色解剖方向判断，不按画面左右。衣服相同不能补偿身份错误 |
| 服装 C0 | 钴蓝短外套、橙色斜挎包、白底短靴 | 分别检查单品、相对颜色、版型和佩戴关系，允许光照带来的合理明暗变化；本轮明确不允许换装 |
| 风格 ST0 | 二维水彩、简化线稿、低饱和纸纹 | 检查媒介质感、线条与色彩表现，不以场景或衣服颜色代替风格判断 |

另设场景服从维度：要求指定地点和动作、全身可见、脸和服装足够清楚。不清晰/遮挡不能猜成通过：某轴记为 `None`（无法判断），同时记录是否违反构图要求。若用户明确要求换装，就把该次的服装目标改为 C1，身份 I0 仍保持；不要把“换衣服”误判成“换角色”。风格变化也应按新的风格目标单独验收。

计划参考资产 R0 应由自制或合法授权素材构成，包含清楚的正面/四分之三视角和必要局部标记；按实际接口支持选择单图或多图，不能假设拼贴一定能被正确分离。保存来源、授权范围、裁剪/预处理版本和文件 hash；每次实验用同一资产版本。**本题 R0 尚未制作，hash 与授权文件状态不能虚填为已完成**。执行前需要完成这些准备；不取用课程中的角色图片，也不把无授权网络图片当参考。

### 3. 同一角色换场景的四组对照

预先固定三个场景：SC1 书店选书、SC2 海边看灯塔、SC3 夜市等车；均保持 I0/C0/ST0，构图规则相同。夜市可改变环境光，但仍需让身份锚点和服装可判断。

| 实验臂 | 可视条件 | 文本条件 | 主要比较 |
| --- | --- | --- | --- |
| A | 无参考图的文本基线 | 展开角色契约 + 原始场景描述 P0 | 与 C 比较参考条件，与 B 比较外加改写 |
| B | 与 A 相同 | 同一契约 + 冻结的改写候选 P1 | 相对 A 衡量改写增量 |
| C | 固定参考 R0、固定参考配置 | 与 A 完全相同的 P0 | 相对 A 衡量参考配置增量 |
| D | 与 C 相同 | 与 B 完全相同的 P1 | 相对 C 衡量改写增量，与 B 比较参考配置 |

每个场景预先选 seed `{17, 29, 43, 61, 79}`，每格计划 5 张，不挑最佳图替代全量结果。下表每格都须分别记录 **I（身份）/C（服装）/ST（风格）**，再记录场景服从；“待评”不是零分或成功。

| 场景，I0/C0/ST0 不变 | A 文本 | B 文本+改写 | C 参考 | D 参考+改写 |
| --- | --- | --- | --- | --- |
| SC1 书店选书 | 5 张；I/C/ST 待评 | 5 张；I/C/ST 待评 | 5 张；I/C/ST 待评 | 5 张；I/C/ST 待评 |
| SC2 海边看灯塔 | 5 张；I/C/ST 待评 | 5 张；I/C/ST 待评 | 5 张；I/C/ST 待评 | 5 张；I/C/ST 待评 |
| SC3 夜市等车 | 5 张；I/C/ST 待评 | 5 张；I/C/ST 待评 | 5 张；I/C/ST 待评 | 5 张；I/C/ST 待评 |

共 `4 × 3 × 5 = 60` 个计划样本、`4 × 5 = 20` 个三场景角色组。对于每臂的同一 seed，还要把三个场景并排检查身份一致性；既要像基准角色，也要彼此一致，不能把“稳定生成了另一只狐狸”当成功。

运行前锁定模型 checkpoint/revision、adapter/图像编码器及权重 hash、scheduler/采样器、steps、guidance、尺寸/比例、negative prompt、参考预处理、dtype、运行库和硬件。参考臂 C/D 的参数一致，P1 在每个场景生成并审查一次后冻结，B/D 复用同一字符串，以免同时更换参考和改写内容。如果服务会内部自动改写而不能关闭，A 是“平台默认文本流程”，不能称为严格无改写实验。

优先用同一底座支持的文本/图像条件进行比较。若做细粒度消融，可在适用的固定 IP-Adapter 实现中比较图像分支 scale=0 与预先选定的非零值，并检查预处理等其他条件不变；这与原生纯文本路径的运行成本未必相同。如果两条产品路径需要不同模型/架构，矩阵仍可比较配置优劣，但不能把全部差异因果归给“多了一张参考图”。

本轮没有执行生图，因此没有可报告的模型权重 revision、参考 hash、实际延迟或合格率。本文对机制的实现依据固定到 Diffusers v0.35.1、PyTorch v2.5.1；这两份源码依据不等于已经部署了某个生成模型。执行矩阵前应补齐上述配置清单，禁止把只有计划字段的记录混入结果表。

### 4. seed 与评测分数都不能代替身份保证

**seed 控制随机过程，不编码角色身份。** 即使 seed 相同，Prompt、参考图、模型权重、latent 形状、采样器、步数或随机数消费顺序变了，输出也可能变化；跨框架版本、平台和 CPU/GPU 也不保证逐像素复现。Diffusers 的 `Generator` 有状态，传递同一个已消费的对象不等于重新使用同一随机起点；配对运行应按所用实现重置/重建随机状态，并保存实际配置。API 未暴露 seed 时应记录“不支持”，用独立重复和随机执行顺序评估，不能虚构配对 seed。

本例可预注册以下**教学验收规则**，真实产品须校准：每张图的 I/C/ST/场景分别评分，2=清楚满足全部指定条件，1=部分偏离，0=明显不符，`None`=无法判断。任一已知轴低于 2 即联合不通过；没有低分但含未知项则待复核；全部为 2 才通过。这样“同一角色但衣服错了”与“衣服对但换了角色”会进入不同失败原因，风格漂亮也不能抵消身份错误。

安排两位不知道实验臂的评审独立打分，分歧复核并保留原始评分；按场景和 seed 展示全部候选、失败和无法判断项。通用图像 embedding/CLIP 相似度可受衣服、风格和背景影响，不能单独作为身份真值；裁剪身份区域、人工锚点核对和跨场景组比较可互补，针对拟人角色的自动指标尤其需要校准。

实际运行后，分别报告生成成功率、各轴可判断率和达标率、联合通过率，以及跨场景组的身份一致性。质量条件分母要说明是已生成、可判断还是全部已请求；端到端联合通过率应把已请求但未交付的失败留在分母，未知项不能默认为通过。**计划 60 张不代表已经请求 60 张；当前观测为 0，合格率应为空。** 三场景共用角色和 seed，会产生相关性，不能把它们当大量独立样本夸大置信度；五个 seed 也只能支持小规模排错，后续需保留场景/seed 验收集。

### 5. Prompt 改写先保真，再看收益和时延

改写层可以把含糊需求整理为可见属性和构图要求，适合输入不稳定或业务需要统一模板的场景；理解自然语言已足够好的模型、明确简洁的输入或低延迟任务，可能不值得外加这一层。**不是所有模型都必须扩写，也不是越长越好。** 一次扩写可能改变参考优先级、引入冲突风格或无关物件。

例如原始场景描述 P0 为“在海边看灯塔，全身入画，脸和衣服清楚”。一个**人工编写的改写示意** P1 是“海边场景，小岚面向灯塔站立；画面保留完整身体，并清楚呈现脸部与服装”。两者都由固定模板附上 I0/C0/ST0 全文，没有调用 LLM，也没有证明 P1 的实际生图质量更高。把“小岚”改成写实人类、加上新帽子或把水彩改成油画，都是改写保真失败，而非质量提升。

可以让改写器只处理允许变化的 scene_description，由程序保留锁定字段；保存用户原文、改写候选、改写器模型/版本、系统提示和差异检查。结构字段未变不保证自然语言含义没变，仍需校验新增/遗漏/矛盾属性及参考指代，不能只做字符串长度检查。保真未通过则使用已验证的原始模板或返回修订，不能静默带着改动生图。

画面质量对照中 B/D 复用冻结的 P1，但测产品延迟时要把实际改写成本算回去，区分每次冷调用与缓存命中。对必须等改写完成才能生图的串行路径，每请求可记：`T总 = T改写排队与执行 + T保真检查 + T生图排队与执行 + T其他固定处理`。改写也可能改变生图时间或重试次数，应测真实端到端分布；不能把各阶段 p95 简单相加，也不能把改写文本开始流出当成首张图已经可用。

**纯算例，非实测：**假定直接路径 8000 ms，外加改写 1200 ms、检查 80 ms，其他阶段及生图时间完全不变，则新路径为 9280 ms，增加 1280 ms（1.28 s，16%）。是否采用应同时看保真拒绝率、I/C/ST/场景分项变化、联合通过率、实际成本与 p50/p95；没有质量或易用性收益时不应只为流程“更完整”保留额外调用。

下面的 Python 3.11.8 代码只生成计划、检验分项门槛和核算上述人工延迟假设，不调用生图/改写模型，不加载图片：

```python
import json
from itertools import product

SCENES = ("SC1-bookstore", "SC2-seaside", "SC3-night-market")
SEEDS = (17, 29, 43, 61, 79)
ARMS = {"A": (False, False), "B": (False, True),
        "C": (True, False), "D": (True, True)}  # (参考图, 外加改写)
AXES = ("identity", "clothing", "style", "scene")


def build_plan():
    rows = []
    for arm, scene, seed in product(ARMS, SCENES, SEEDS):
        reference, rewrite = ARMS[arm]
        rows.append({
            "id": f"{arm}/{scene}/{seed}", "arm": arm, "scene": scene, "seed": seed,
            "reference_id": "R0-planned" if reference else None,
            "prompt_id": f"{scene}/{'rewrite' if rewrite else 'raw'}",
            "status": "not_run", "image_sha256": None,
            "scores": dict.fromkeys(AXES),
        })
    return rows


def joint_gate(scores):
    if type(scores) is not dict or set(scores) != set(AXES):
        raise ValueError("score fields")
    # 先校验所有输入；None 不掩盖其他字段的非法类型或越界值。
    for value in scores.values():
        if value is not None and (type(value) is not int or value not in (0, 1, 2)):
            raise ValueError("score must be 0/1/2 or None")
    if any(value is not None and value < 2 for value in scores.values()):
        return "fail"  # 已有一项明确不达标，其余未知项仍保留 None。
    if any(value is None for value in scores.values()):
        return "unjudged"
    return "pass"


def example():
    rows = build_plan()
    groups = {(row["arm"], row["seed"]) for row in rows}
    # 仅计算人工假定的串行延迟；不是生图服务实测。
    direct_ms, rewrite_ms, check_ms = 8000, 1200, 80
    return {"design_only": True, "planned_images": len(rows),
            "planned_three_scene_groups": len(groups), "observed_images": 0,
            "quality_rates": None,
            "illustrative_latency_ms": {"direct": direct_ms,
                "with_rewrite": direct_ms + rewrite_ms + check_ms,
                "extra": rewrite_ms + check_ms}}


if __name__ == "__main__":
    print(json.dumps(example(), ensure_ascii=False, indent=2))
```

本地运行输出为 `planned_images=60`、`planned_three_scene_groups=20`、`observed_images=0`、`quality_rates=null`，延迟算例为 `8000 → 9280 ms`。验证记录检查组合覆盖、未知评分、类型/分项边界和算术；没有把这些检查称为角色一致性实测。

## 延伸 / 追问

**追问 1：有参考图后衣服一直正确，但角色仍漂移，怎么排查？**

先把身份裁剪/锚点评分与服装评分分开，检查参考图是否清楚、预处理有没有裁掉标记、Prompt 是否与参考冲突、实现到底用了哪类图像条件。再在独立校准集上比较参考强度、局部编辑或主体定制；不要只凭全图相似度提高就宣布身份问题解决。

**追问 2：固定 seed 后换模型得到另一张脸，是不是接口坏了？**

不能据此判断。seed 只选择特定实现中的随机起点，模型和采样轨迹变化会改变结果。先固定同一配置排查复现性，再以角色锚点和多 seed 评测处理身份一致性，跨模型不得沿用 seed 的身份含义。

**追问 3：Prompt 扩写让图片更好看，为什么验收仍可能失败？**

它可能改变了用户明确指定的身份、服装或风格；美观分不能补偿保真失败。回看原文与改写差异，缩小允许改动范围，再在同底座、同参考和配对样本上比较收益，同时计入改写检查和失败回退的成本。

## 常见误区

- **“固定 seed 保证跨模型还是同一角色。”** seed 不是身份编码，也不提供跨版本或跨硬件逐像素保证。
- **“加参考图就一定锁住外貌。”** 参考是条件信号，可能遗漏身份线索或携带不需要的服装/背景/风格。
- **“Prompt 扩写是所有生图模型的必经步骤。”** 这是待验证的产品选择，要衡量保真、质量、时延和成本。
- **“服装和画风一样就说明角色一致。”** 三个维度须分别验收，还要核对场景和跨场景身份。
- **“挑到一张好图就能证明方案可靠。”** 保留预先规定的全部样本、失败与未知项，不能把计划矩阵或示意评分当实测结果。

## 参考

- 课程线索：洛小山《AI 产品从入门到精通》learn-ai，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/9-1.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/9-1.html)、[slides/9-2.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/9-2.html)、[slides/9-3.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/9-3.html)、[slides/9-5.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/9-5.html)。仅作选题线索；未沿用“参考图保证一致/改写保证质量”等绝对结论，未复制 AGPL 角色素材、正文或代码。
- Rombach 等，[High-Resolution Image Synthesis with Latent Diffusion Models, arXiv:2112.10752v2](https://arxiv.org/abs/2112.10752v2)：latent diffusion 与 cross-attention 条件机制；Meng 等，[SDEdit, arXiv:2108.01073v2](https://arxiv.org/abs/2108.01073v2)：初始图加噪/去噪和输入保真取舍。本文不引用其任务分数作为本例效果。
- Ye 等，[IP-Adapter, arXiv:2308.06721v1](https://arxiv.org/abs/2308.06721v1)：文本/图像的解耦 cross-attention；Zhang 等，[Adding Conditional Control to Text-to-Image Diffusion Models, arXiv:2302.05543v3](https://arxiv.org/abs/2302.05543v3)：ControlNet 的空间条件。二者控制对象不同，都不是通用身份保证。
- Ruiz 等，[DreamBooth, arXiv:2208.12242v1](https://arxiv.org/abs/2208.12242v1)：主体标识与定制生成；用于说明需要训练的备选路线，不表示本题已经训练角色模型。
- Diffusers v0.35.1，commit `0f252be0ed42006c125ef4429156cb13ae6c1d60`：[img2img](https://github.com/huggingface/diffusers/blob/0f252be0ed42006c125ef4429156cb13ae6c1d60/docs/source/en/using-diffusers/img2img.md)、[IP-Adapter](https://github.com/huggingface/diffusers/blob/0f252be0ed42006c125ef4429156cb13ae6c1d60/docs/source/en/using-diffusers/ip_adapter.md)、[attention_processor.py](https://github.com/huggingface/diffusers/blob/0f252be0ed42006c125ef4429156cb13ae6c1d60/src/diffusers/models/attention_processor.py)：初始图与图像条件参数的实现边界，部分 IP-Adapter processor 的零权重分支跳过逻辑；具体 pipeline 仍须核对。
- 同版本 [Reproducible pipelines](https://github.com/huggingface/diffusers/blob/0f252be0ed42006c125ef4429156cb13ae6c1d60/docs/source/en/using-diffusers/reusing_seeds.md)；PyTorch v2.5.1，commit `a8d6afb511a69687bbb2b7e88a3cf67917e1697e`，[Reproducibility](https://github.com/pytorch/pytorch/blob/a8d6afb511a69687bbb2b7e88a3cf67917e1697e/docs/source/notes/randomness.rst)：随机状态消费、运行环境与确定性的限制。

来源核实与计划检查日期：**2026-09-15**。本文没有实际生图图片、模型质量数据、供应商现价或性能测量；原创文字设定不替代执行前的参考素材准备与授权核验。
