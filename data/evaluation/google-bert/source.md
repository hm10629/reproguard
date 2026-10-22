# 候选项目来源记录：BERT（google-research/bert）

> **状态：候选项目，未完成真实评测。** 本文件只记录来源与待标注事项，不含任何人工标注结论。
> 复验时间：2026-09-30（GMT+8）。复验方式：GitHub REST API + 仓库页面 + arXiv 摘要页。

## 基本信息

| 项 | 内容 |
| --- | --- |
| 项目名称 | google-research/bert |
| 论文标题 | BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding |
| 论文作者 | Jacob Devlin, Ming-Wei Chang, Kenton Lee, Kristina Toutanova |
| 论文链接 | https://arxiv.org/abs/1810.04805 |
| 论文版本信息 | v1 提交于 2018-10-11；v2 修订于 2019-05-24 |
| 代码仓库 | https://github.com/google-research/bert |

## 定位

评测范围（T-016 定稿，由人确认于 2026-10-05）：**只评测微调阶段（fine-tuning）**。

- BERT 的完整复现分为**预训练**与**微调**两阶段，两阶段的复现条件完全不同：预训练需 TPU 集群级算力，个人环境不可复现；微调在单卡上可行。
- **本轮范围已定**：R001–R015 的判定**只依据微调相关材料**；**不评测预训练阶段**。
- 若某条规则只与预训练有关（例如预训练语料的获取方式），按 `not_applicable` 处理并在 note 中说明，**不计入 `found`**。
- 本仓库**已归档（只读）**，只能作为历史论文复现项目引用，不得描述为「活跃维护中」。
- 它是三个候选中**代码完整度最高**的一个（含 `requirements.txt` 与多个入口脚本），与 U-Net 候选构成「完整 vs 不完整」的对照。

## 许可证

- **名称：Apache-2.0**
- **复验结论：已核验**
- **证据位置**：
  1. GitHub REST API `GET /repos/google-research/bert` 返回 `license.spdx_id = "Apache-2.0"`、`license.name = "Apache License 2.0"`。
  2. 仓库顶层存在 `LICENSE` 文件（11358 字节）。
  3. README 原文声明：`All code *and* models are released under the Apache 2.0 license.`
- **需一并记录的限制**：同一 README 声明 `This is not an official Google product.`

## 归档状态（单独列出，因为影响引用方式）

- **已归档（archived）：是**，本轮已核验。
- 证据：GitHub REST API 返回 `archived = true`。
- 含义：该仓库为只读，不再接受改动与维护。**只能作为历史论文复现项目引用，不得描述为「活跃维护中」。**

## 材料获取状态

| 项 | 状态 |
| --- | --- |
| 是否已固定 commit | **已固定**：`eedf5716ce1268e56f0a50264a88cafad334ac61`（由人确认于 2026-10-05） |
| 观测到的 master HEAD（复验时，仅供参考） | `eedf5716ce1268e56f0a50264a88cafad334ac61`，提交时间 2020-03-11T15:19:54Z；**与固定值一致** |
| 是否已下载论文 | 未下载 |
| 是否已下载代码 | 未下载 |
| 是否已下载权重 | **未下载**（预训练模型属大文件，仅记录官方获取方式） |
| 是否已下载数据 | 未下载（预训练语料属大文件） |

## 为什么适合本工具评测

1. **代码完整度最高**：顶层含 `requirements.txt`、`modeling.py`、`tokenization.py`、`optimization.py`、`run_pretraining.py`、`run_classifier.py`、`run_squad.py`、`create_pretraining_data.py`、`extract_features.py` 等，具备完整的入口脚本，与 U-Net 候选形成「完整 vs 不完整」的对照。
2. **依赖与硬件约束是核心复现门槛**：适合检验 R002（依赖及版本）、R007（硬件和运行环境）、R012（预训练权重来源）。
3. **天然适合检验「复现范围」**：论文级预训练需要 TPU 级算力，个人环境不可复现，正好检验工具是否会区分「具备复现条件」与「不可复现」。
4. **含 `requirements.txt` 且版本陈旧**，可检验 R002 能否发现依赖版本问题。

## 已知复现风险

1. **依赖 TensorFlow 1.x**：仓库含 `requirements.txt`（110 字节），指向已停止维护的 TensorFlow 1.x 系列，在当前 Python 版本上安装困难，这是最直接的复现障碍。
2. **预训练不可在个人设备复现**：论文中的预训练规模需要 TPU 集群，普通设备无法完成；本工具应能指出该限制，而不是判定「可复现」。
3. **预训练权重与语料是大文件**：需另行获取，本轮未下载，也不建议入库。
4. **仓库已归档**：最后提交 2020-03-11，不再修复问题，遇到环境问题无上游支持。
5. **论文与代码的分工需要人工判断**：BERT 的完整复现分为「预训练」与「微调」两阶段，两阶段的可复现性完全不同，标注时必须明确标注的是哪一阶段。

## 待人工标注事项

1. 逐条判定 `R001`–`R015` 的状态，填入 `annotation-template.json` 并改名为 `expected-findings.json`。
2. 固定用于评测的 commit —— **已由人确认于 2026-10-05**：`eedf5716ce1268e56f0a50264a88cafad334ac61`。
3. **标注范围 —— 已由人确认于 2026-10-05**：只标注**微调阶段**（fine-tuning），不标注预训练阶段。
4. 决定材料获取策略：只保留来源链接，还是下载代码快照入库；权重与语料一律只记录获取方式。
5. 确认 TensorFlow 1.x 在本机是否可安装；若不可安装，需在标注中说明这不影响「是否具备复现条件」的检查。

## 复验记录

| 复验项 | 方法 | 结果 |
| --- | --- | --- |
| 论文标题与作者 | 访问 arXiv 摘要页 | 与上表一致 |
| 仓库存在性 | GitHub REST API | 存在，`full_name = google-research/bert` |
| 许可证 | GitHub REST API + README 原文 | `Apache-2.0`，已核验 |
| 归档状态 | GitHub REST API `archived` | `true`，已核验 |
| 顶层文件清单 | GitHub REST API contents | 21 个文件，含 `requirements.txt` 与多个入口脚本 |
