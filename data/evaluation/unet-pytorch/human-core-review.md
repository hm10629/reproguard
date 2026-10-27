# U-Net 主案例：6 条核心人工复核清单

> 目标：用最少人工工作形成一份独立标准答案。请先阅读固定 commit 的仓库材料，再运行本项目工具，避免根据工具输出反推答案。

固定仓库 commit：`2bb0e44a2d5c7c04b589d5d942673aee52bcff58`

合法状态：`found`、`partial`、`missing`、`not_applicable`、`needs_review`。

| 规则 | 人工检查问题 | 人工状态 | 证据文件与行号 | 理由/备注 |
| --- | --- | --- | --- | --- |
| R001 | 是否存在足以说明项目用途和基本使用方式的 README？ | `partial` | `README.md:3`、`README.md:7–35` | README 说明项目用途（U-Net 语义分割）并给出 loss 用法示例，但缺少安装、训练和评测步骤，基本使用方法不完整。 |
| R002 | 是否声明运行依赖及关键版本？ | `missing` | 仓库根目录文件清单；`model.py:1–7` | 根目录无 `requirements.txt`、`setup.py`、`environment.yml` 等依赖文件；README 未声明依赖；代码只导入 torch/numpy，未给出关键版本。 |
| R003 | 是否说明论文所需数据集的来源和获取方式？ | `partial` | 论文 §4；`README.md` 全文 | 论文说明数据集名称（ISBI 2012 EM challenge）、来源与规模（30张 512×512），但未给直接下载方式；仓库 README 未提供下载地址、目录结构、预处理或准备命令。 |
| R008 | 是否存在可以直接执行的训练或评测入口命令？ | `missing` | 仓库根目录；`model.py:238–246` | 固定 commit 仅含 `model.py`，无训练或评测入口；README 无执行命令；`__main__` 仅为前向与反向 smoke test。 |
| R011 | 仓库实现与论文模型、框架和改动是否能准确对应？ | `needs_review` | `README.md:3`；`LICENSE:3`；`model.py:112–133` | 可确认其为第三方 PyTorch 修改版且具备编码器、解码器和跳跃连接，但缺少论文的加权损失、弹性形变、overlap-tile 等实验设置，无法确认能否等价复现论文实验。 |
| R014 | 是否提供代码许可证，并说明外部数据的使用限制？ | `partial` | `LICENSE:1–21`；`README.md` 全文 | 代码采用 MIT 许可证并允许修改和再分发，但 README 与论文均未说明数据集的使用限制、申请要求或再分发条款；代码许可不等于数据许可。 |

## 人工签署

- 复核人：沈智和
- 复核日期：2026-10-20
- 是否独立于工具输出完成：是
- 是否确认仓库 commit 一致：是
- 是否确认没有把最小运行写成论文精度复现：是

## 已迁入的 Claude 标注线索

Claude 工作区的二分类标注已经迁入 `imported/`，但存在 commit、文件路径和两条结论冲突，不能直接当作本项目标准答案。逐条映射见：

- `imported/claude-ground-truth.original.json`
- `imported/claude-to-reproguard-mapping.json`

可优先复核以下建议，减少重复阅读：

| ReproGuard 规则 | 迁入建议 | 仍需人工确认 |
| --- | --- | --- |
| R001 | `partial` | README 是否已足以说明用途和基本使用方式 |
| R002 | `missing` | 固定 commit 是否确无依赖文件 |
| R003 | `needs_review` | Claude 原标注与当前 README 冲突，需查论文原文 |
| R008 | `missing` | 固定 commit 是否确无训练/评测入口命令 |
| R011 | `needs_review` | 第三方 PyTorch 修改版与原始 Caffe 论文的对应边界 |
| R014 | `partial` | MIT LICENSE 已有，但外部数据使用限制尚未确认 |

这些只是迁入建议。请在上方“人工状态”栏填写你核对后的最终结论，并补证据文件和行号。

## 完成后的处理

1. 将 6 条人工状态录入评测文件；其余规则可以继续保持未标注。
2. 再运行工具，对比机器判断和人工答案。
3. 对不一致项逐条记录：机器判断、人工判断、证据位置和最终解释。
4. 演示中只展示已人工复核的规则，不用未标注规则计算准确率。
