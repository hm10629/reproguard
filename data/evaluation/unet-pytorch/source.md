# 候选项目来源记录：U-Net（PyTorch 第三方实现）

> **状态：已完成六条核心规则的人工标注与正式评测。** 其余九条规则尚未标注，不纳入指标。人工结论见 `human-core-review.md` 和 `expected-findings.json`，机器可读结果见 `reports/evaluation.json`。
> 首次复验时间：2026-09-30（GMT+8）。2026-10-20 再次通过 GitHub 固定 commit 页面核验文件清单和 README。复验方式：GitHub REST API + 仓库页面 + arXiv 摘要页。

## 基本信息

| 项 | 内容 |
| --- | --- |
| 项目名称 | jaxony/unet-pytorch |
| 论文标题 | U-Net: Convolutional Networks for Biomedical Image Segmentation |
| 论文作者 | Olaf Ronneberger, Philipp Fischer, Thomas Brox |
| 论文链接 | https://arxiv.org/abs/1505.04597 |
| 论文版本信息 | 提交于 2015-05-18；arXiv 备注 `conditionally accepted at MICCAI 2015` |
| 代码仓库 | https://github.com/jaxony/unet-pytorch |

## 定位

**「不完整复现链路 / 缺口发现边界样例」**（T-015 定稿）。

- 该仓库顶层只有 5 个文件，**没有训练脚本、没有数据集处理代码、没有 `requirements.txt`**，是一条不完整的复现链路。
- 它用来检验本工具能否**发现缺口**：论文写得全、代码给得少时应判出 `missing` / `partial`，而不是因为「代码看起来没报错」就判 `found`。
- **不得把它包装成完整复现项目**，也不得用它的评测结果代表「完整项目」的表现。
- 它属于论文 U-Net 的**第三方 PyTorch 重实现**，不是论文作者的原始 Caffe 实现。

## 许可证

- **名称：MIT**
- **复验结论：已核验**
- **证据位置**：GitHub REST API `GET /repos/jaxony/unet-pytorch` 返回
  `license.spdx_id = "MIT"`、`license.name = "MIT License"`；仓库顶层存在 `LICENSE` 文件（1070 字节）。
- 仓库内未发现其他冲突的许可证文件。

## 材料获取状态

| 项 | 状态 |
| --- | --- |
| 是否已固定 commit | **已固定**：`2bb0e44a2d5c7c04b589d5d942673aee52bcff58`（由人确认于 2026-10-05） |
| 观测到的 master HEAD（复验时，仅供参考） | `2bb0e44a2d5c7c04b589d5d942673aee52bcff58`，提交时间 2017-12-04T03:23:15Z；**与固定值一致** |
| 是否已下载论文 | 已临时下载到 `.tmp-current/unet-paper.pdf` 供本地审计，不纳入开放成果 |
| 是否已下载代码 | 已将固定 commit 的 5 个顶层文件复制到 `data/evaluation/unet-pytorch/repository/`，保留原 MIT `LICENSE` |
| 是否已下载权重 | 未下载（该仓库不含权重） |
| 是否已下载数据 | 未下载 |

## 为什么适合本工具评测

1. **规模小、结构清晰**：仓库顶层只有 5 个文件，便于人工逐条核对，不会让标注者陷入大型工程。
2. **正好命中「信息缺口」这个主题**：仓库只提供模型定义，缺训练脚本与数据集处理，是典型「论文写得全、代码给得少」的情形，能有效检验 R004（数据预处理与划分）、R008（实验入口命令）、R010（结果生成）等规则。
3. **论文与代码的对应关系需要人工判断**：论文原始实现基于 Caffe，本仓库是 PyTorch 重新实现，直接命中 R011（模型、数据集与代码名称是否对应）。

## 已知复现风险

1. **仓库不完整，无法直接复现**：顶层文件仅 `.gitignore`、`LICENSE`、`README.md`、`model.py`（8358 字节）、`unet-architecture.png`。**没有训练脚本、没有数据集处理代码、没有 `requirements.txt`**。
2. **是第三方修改版**：README 自述该实现是论文 U-Net 的 modified version，并明确列出两处改动——可改变网络深度、以及提供 ResNet 风格的解码器/编码器合并方式。作者同时写明该合并方式 "may not make sense theoretically and has not been tested"。
3. **与论文原始实现不同**：论文原始实现基于 Caffe，本仓库为 PyTorch 实现，二者不完全对应。
4. **长期不活跃**：最后提交时间为 2017-12-04，GitHub API `archived = false`，但已逾八年无提交。
5. **数据集不在仓库内**：论文使用的 ISBI 数据集需另行获取，本仓库未记录获取方式。

## 已完成人工标注与后续事项

1. 已人工判定 `R001`、`R002`、`R003`、`R008`、`R011`、`R014`，标注者为沈智和，日期为 2026-10-20。
2. 已固定评测 commit：`2bb0e44a2d5c7c04b589d5d942673aee52bcff58`。
3. 论文 PDF 与第三方代码快照只在本机核验，由 `.gitignore` 排除；开放仓库只发布来源、人工依据和评测结果。
4. 外部数据集的许可、申请条件与再分发限制仍未确认，因此 R014 保持 `partial`。
5. 后续可标注其余九条规则并加入未参与规则调优的新项目；当前不得把同组 6/6 解释为跨项目准确率。

## 2026-10-20 首次真实审计与标注

- 规则报告：`reports/unet-audit.md` 和 `reports/unet-audit.json`
- 工具初始输出曾将普通 `output`、权重初始化、`version` 和 issue 链接误判为复现证据；已据此收紧 R008、R010、R012、R013、R015，并增加回归测试。
- 修正后结果：15 项中 `found=4`、`partial=3`、`missing=7`、`needs_review=1`。
- 随后由沈智和独立完成六条核心规则的人工标准答案；初始基线精确状态一致 3/6，经失败分析和规则改进后同组复测为 6/6。该结果的样本限制见 `reports/evaluation.md`。

## 复验记录

| 复验项 | 方法 | 结果 |
| --- | --- | --- |
| 论文标题与作者 | 访问 arXiv 摘要页 | 与上表一致 |
| 仓库存在性 | GitHub REST API | 存在，`full_name = jaxony/unet-pytorch` |
| 许可证 | GitHub REST API `license.spdx_id` | `MIT`，已核验 |
| 归档状态 | GitHub REST API `archived` | `false` |
| 顶层文件清单 | GitHub REST API contents | 5 个文件，见「已知复现风险」第 1 条 |
