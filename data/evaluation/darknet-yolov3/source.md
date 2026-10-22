# 候选项目来源记录：YOLOv3（pjreddie/darknet）

> **状态：候选项目，未完成真实评测。** 本文件只记录来源与待标注事项，不含任何人工标注结论。
> 复验时间：2026-09-30（GMT+8）。复验方式：GitHub REST API + 仓库页面 + arXiv 摘要页。

## 基本信息

| 项 | 内容 |
| --- | --- |
| 项目名称 | pjreddie/darknet（Darknet 框架，YOLOv3 官方实现所在仓库） |
| 论文标题 | YOLOv3: An Incremental Improvement |
| 论文作者 | Joseph Redmon, Ali Farhadi |
| 论文链接 | https://arxiv.org/abs/1804.02767 |
| 论文版本信息 | 提交于 2018-04-08；arXiv 备注 `Tech Report` |
| 代码仓库 | https://github.com/pjreddie/darknet |

## 定位

候选状态（T-016 定稿，由人确认于 2026-10-05）：**暂缓正式评测；仍为候选；`needs_verification` 未关闭**。

- **本轮决定**：darknet 暂时保留为候选，**不纳入正式评测、不生成任何正式指标**；待下节两项 `needs_verification` 关闭后再评估是否纳入。
- 固定 commit 已写入「材料获取状态」，但 `needs_verification` 未关闭前，标注与指标均**不启动**。

| 待确认项 | 当前判定 | 说明 |
| --- | --- | --- |
| 许可证 | `needs_verification` | 主 `LICENSE` 自称 public domain，但 GitHub 判为 `NOASSERTION`，且仓库内有 7 个互相冲突的 license 文件。详见下节 |
| **论文与仓库的对应范围** | `needs_verification` | 该仓库 README 已转向 YOLOv7 / YOLOv4 并指向其他仓库，它与 YOLOv3 论文的对应关系需人工确认 |

在两项确认关闭之前，**本项目材料中不得把它简写为「MIT」「GPL」或「已确认 public domain」，也不得断言它就是 YOLOv3 的官方复现对象**。

## 许可证

- **名称：`needs_verification`（需人工或法务确认，本轮不判为已核验）**
- **已核验的事实**：
  1. 仓库顶层主 `LICENSE` 文件（515 字节）标题为 `YOLO LICENSE`、`Version 2, July 29 2016`，正文原文为：
     > `0. Darknet is public domain.`
     > `1. Do whatever you want with it.`
     > `2. Stop emailing me about it!`
  2. 但 GitHub REST API 对该仓库返回 `license.spdx_id = "NOASSERTION"`、`license.name = "Other"`，即 GitHub 未能识别为标准许可证。
  3. 仓库顶层同时存在 **7 个** license 类文件，彼此冲突：

     | 文件 | 大小 |
     | --- | ---: |
     | `LICENSE` | 515 字节 |
     | `LICENSE.fuck` | 474 字节 |
     | `LICENSE.gen` | 6652 字节 |
     | `LICENSE.gpl` | 35141 字节 |
     | `LICENSE.meta` | 360 字节 |
     | `LICENSE.mit` | 1071 字节 |
     | `LICENSE.v1` | 461 字节 |

- **为什么标为 `needs_verification`**：主许可证文本自称 public domain，但其文本为非标准自定义表述（且含玩笑性质的措辞），GitHub 无法识别；同一仓库内还存在 `LICENSE.gpl`、`LICENSE.mit` 等互相冲突的文件。因此**在本项目材料中不得把该仓库的许可证简写为「MIT」或「GPL」**，也不宜直接断言「已是 public domain」。使用前需人工确认应以哪个文件为准。

## 材料获取状态

| 项 | 状态 |
| --- | --- |
| 是否已固定 commit | **已固定**：`f6afaabcdf85f77e7aff2ec55c020c0e297c77f9`（由人确认于 2026-10-05） |
| 观测到的 master HEAD（复验时，仅供参考） | `f6afaabcdf85f77e7aff2ec55c020c0e297c77f9`，提交时间 2022-07-17T21:26:40Z；**与固定值一致** |
| 是否已下载论文 | 未下载 |
| 是否已下载代码 | 未下载 |
| 是否已下载权重 | **未下载**（权重属大文件，仅记录官方获取方式） |
| 是否已下载数据 | 未下载（COCO 等数据集属大文件） |

## 为什么适合本工具评测

1. **是编译型 C/CUDA 项目**：仓库含 `Makefile`、`src/`、`include/`、`cfg/`、`data/`、`scripts/`，与 Python 项目形态不同，能检验规则在非 Python 工程上的表现。
2. **配置与硬件信息密集**：`cfg/` 下有网络结构与训练配置，适合检验 R006（关键训练超参数）、R007（硬件与运行环境）、R008（实验入口命令）。
3. **权重与数据的获取是典型复现门槛**：正好对应 R012（预训练权重或外部权重来源）与 R003（数据集来源和下载方式）。
4. **论文与仓库的对应关系在今日已发生变化**，适合检验 R011。

## 已知复现风险

1. **仓库 README 已不再以 YOLOv3 为主**：当前 README 主要介绍 YOLOv7 与 YOLOv4，并把「用于复现结果的源码」指向其他仓库（如 `WongKinYiu/yolov7`、`AlexeyAB/darknet`）。因此「本仓库 = YOLOv3 官方实现」这一说法需要人工确认，与论文的直接对应关系已不清晰。
2. **需要编译**：项目为 C 与 CUDA，需 `make`，并可能依赖 OpenCV 与 CUDA 工具链；对无 GPU 环境不友好。
3. **权重文件不在仓库内**：官方权重需另行下载，属大文件，本轮未下载，也不建议入库。
4. **数据集不在仓库内**：COCO 等数据集需另行获取，属大文件。
5. **许可证状态不明**：见上节，存在 7 个互相冲突的 license 文件。
6. **仓库最后提交 2022-07-17**，其后的仓库 API `pushed_at` 为 2024-05-03（可能来自分支或标签），主分支内容以 2022 年为准。

## 待人工标注事项

1. 逐条判定 `R001`–`R015` 的状态，填入 `annotation-template.json` 并改名为 `expected-findings.json`。
2. 固定用于评测的 commit —— **已由人确认于 2026-10-05**：`f6afaabcdf85f77e7aff2ec55c020c0e297c77f9`。
3. **人工确认许可证**：应以哪个 license 文件为准，是否可用于本项目引用。**未关闭前本项目暂缓正式评测。**
4. **人工确认论文与仓库的对应关系**：是否仍以 `pjreddie/darknet` 作为 YOLOv3 的复现对象，还是改用其他维护中的实现。
5. 决定材料获取策略：只保留来源链接，还是下载代码快照入库；权重与数据集一律只记录获取方式。
6. 确认在无 GPU 环境下如何演示本项目（可能只能演示「缺什么」而无法演示训练）。

## 复验记录

| 复验项 | 方法 | 结果 |
| --- | --- | --- |
| 论文标题与作者 | 访问 arXiv 摘要页 | 与上表一致 |
| 仓库存在性 | GitHub REST API | 存在，`full_name = pjreddie/darknet` |
| 许可证 | GitHub REST API + `LICENSE` 原文 | `NOASSERTION` / `Other`；主 LICENSE 自称 public domain，另存 7 个冲突 license 文件 → `needs_verification` |
| 归档状态 | GitHub REST API `archived` | `false` |
| README 现状 | 仓库页面 | 已转向 YOLOv7 / YOLOv4，指向其他仓库 |
