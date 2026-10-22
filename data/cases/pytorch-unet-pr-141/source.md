# 真实历史 PR 案例：Pytorch-UNet #141

## 选择结论

本案例用于演示 ReproGuard 对真实科研代码 PR 的回放。上游仓库 README 明确将项目描述为 U-Net 的 PyTorch 实现，并链接原始论文《U-Net: Convolutional Networks for Biomedical Image Segmentation》。PR #141 已于 2020-03-14 合并，不是为比赛构造的提交。

## 可核验来源

| 项目 | 内容 |
| --- | --- |
| 上游仓库 | https://github.com/milesial/Pytorch-UNet |
| 上游许可证 | GPL-3.0（GitHub 仓库元数据核验） |
| 关联论文 | https://arxiv.org/abs/1505.04597 |
| 历史 PR | https://github.com/milesial/Pytorch-UNet/pull/141 |
| PR 标题 | `Apply sigmoid before calc dice in eval_net()` |
| 合并时间 | `2020-03-14T22:02:51Z` |
| Merge commit | `32ee0fe21170e98f3edb51f8639d8b26d7ce3475` |
| 原始 diff | https://github.com/milesial/Pytorch-UNet/pull/141.diff |
| diff SHA-256 | `4dfe9e0a4f6da928f70ba4b7ca31b923279813486dcc9ef26ee790b5156b4e8b` |

结构化元数据见 [case.json](case.json)。项目不重新分发完整上游 diff；回放时从公开 PR URL 获取并核对 SHA-256，避免把 GPL-3.0 上游代码误标为本项目的 MIT 自研代码。

## 可重复回放

在项目根目录运行：

```powershell
Invoke-WebRequest `
  -Uri "https://github.com/milesial/Pytorch-UNet/pull/141.diff" `
  -OutFile ".tmp-current\pytorch-unet-pr-141.diff"

Get-FileHash `
  -LiteralPath ".tmp-current\pytorch-unet-pr-141.diff" `
  -Algorithm SHA256

python -m src.pr_review `
  --diff ".tmp-current\pytorch-unet-pr-141.diff" `
  --output "reports\pytorch-unet-pr-141" `
  --format both `
  --model-mode rules
```

只有哈希与 `case.json` 一致时，才能把输出作为本案例的回放结果。正式结果见 `reports/pytorch-unet-pr-141.json` 和 `reports/pytorch-unet-pr-141.md`。

## 为什么适合作为比赛案例

该 PR 不是普通格式调整。它同时改变：

- 二分类预测在阈值化前是否执行 sigmoid；
- Dice 指标的输入和批量计算方式；
- 多分类分支的交叉熵计算；
- 验证 DataLoader 是否丢弃最后一个不完整批次；
- 验证结果的归一化单位由样本数变为批次数。

这些变化可能是正确的修复，但会改变评价口径或结果数值。ReproGuard 的职责不是阻止合并，而是要求维护者确认论文/协议、测试、结果表和复现档案是否同步。

## 回放结果与规则演进

首次使用旧规则回放时，系统对该 PR 输出 0 条风险。这是一个真实漏报，不应隐藏。原因是旧规则只识别 `preprocess`、`normalize`、`metric` 等宽泛词，没有覆盖 `sigmoid`、`dice_coeff`、`cross_entropy` 和 `drop_last`。

补充上述评价与数据管线术语后，系统能够在 `eval.py` 和 `train.py` 上生成两条 `pipeline_change` 风险，并保持 `needs_human_review = true`。人工复核随后发现 `n_val = len(loader)` 与 `tot / n_val` 共同改变评价归一化分母，但未被单独报告。

2026-10-22 增加 `evaluation_denominator_change` 规则后，使用哈希一致的完整真实 diff 复测，报告由2条增至3条高风险项：新增证据定位 `eval.py:12` 和 `eval.py:32`，覆盖这处已知漏报。正反例回归测试要求同时存在加载器批次数赋值与评价除法，普通的 `len(loader)` 使用不会单独报警。

这是一条可审计的规则演进记录：旧规则0条风险 → 扩展管线词后2条 → 人工发现分母漏报 → 结构化规则修复后3条。它证明已知失败模式被修复，不证明在未见PR上没有误报或漏报。

## 人工复核要求

`【必须人工复核】`

1. 确认比赛材料中引用的 PR 页面、merge commit 和 diff 哈希仍一致；
2. 确认“评价流程变化”的人工标签，不将“需要同步核验”表述成“该修复是错误的”；
3. 不得声称 GitHub、上游维护者或其他工具当时没有发现该问题；公开记录只能证明 PR 真实发生并被合并；
4. 将此案例纳入混淆矩阵前，由一名团队成员填写姓名、日期和最终标签；
5. 演示截图应同时显示 PR 原始 diff 与 ReproGuard 输出，保留来源链接。

2026-10-20的人工复核已经完成，原始签署结论和后续规则修复记录见 [human-review.md](human-review.md)。
