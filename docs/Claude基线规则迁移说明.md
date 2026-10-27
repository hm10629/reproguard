# Claude 基线规则迁移说明

## 迁移结论

Claude 工作区的规则适合作为“仓库基础完整性检查”，ReproGuard 项目的规则适合作为“论文-代码-数据复现证据检查”。本次迁移保留 Claude 的原始人工判断，并把它们映射为 ReproGuard 人工复核线索；没有直接覆盖 ReproGuard 的 `R001-R015`，也没有把迁入结果伪装成正式标准答案。

迁入文件：

- `data/evaluation/unet-pytorch/imported/claude-ground-truth.original.json`：Claude 人工标注原始留档。
- `data/evaluation/unet-pytorch/imported/claude-to-reproguard-mapping.json`：逐条映射、建议状态、冲突和待复核项。
- `data/evaluation/unet-pytorch/human-core-review.md`：人工最终确认入口。

## 为什么不能直接改名

Claude 文件使用 `expected_passed: true/false`，同名规则主要检查入口文件、依赖、配置和代码结构。ReproGuard 文件使用 `found/partial/missing/not_applicable/needs_review`，同名规则检查论文、仓库和数据证据的完整程度。两个项目中的 `R001` 并不是同一条规则，所以直接复制或改名会生成错误的混淆矩阵。

## 编号处理

迁移记录把 Claude 原编号显示为 `CLAUDE-R001` 至 `CLAUDE-R015`，ReproGuard 主规则继续使用 `R001` 至 `R015`。`CLAUDE-` 只用于迁移文档和来源追踪，不会送入 `src/evaluation.py`。

## 当前阻塞项

1. Claude 材料声明 commit `18e9c4c`，ReproGuard 主案例固定 commit 为 `2bb0e44a2d5c7c04b589d5d942673aee52bcff58`。
2. Claude 标注引用 `unet/model.py`，ReproGuard 固定快照中的实际文件是根目录 `model.py`。
3. Claude `R011` 声称 README 提及 ISBI 和数据获取方式，但 ReproGuard 固定快照 README 中没有这些内容。
4. Claude `R014` 的 `expected_passed: false` 与备注中的 “Rule passes” 自相矛盾。

以上四项解决前，迁入数据只能称为“待复核草稿”，不能作为目标 commit 的正式人工真值。

## 转换口径

- 直接对应且证据一致：转换为 ReproGuard 的建议状态，但仍需确认 commit。
- 只覆盖目标规则的一部分：转换为 `partial` 或 `needs_review` 建议，不自动定案。
- 语义冲突或证据错误：标记为 `blocked`，必须人工重判。
- ReproGuard 独有规则：继续人工标注，不从 Claude 结果推断。

## 正式启用条件

人工复核完成后，创建 `data/evaluation/unet-pytorch/expected-findings.json`。可以只写已确认的规则；`src/evaluation.py` 会列出尚未标注的规则，不要求一次填满 15 条。正式文件至少应记录标注人、日期、固定 commit 和证据依据。

不要把 `imported/claude-to-reproguard-mapping.json` 改名为 `expected-findings.json`。它是迁移审计记录，不符合正式标注 schema。
