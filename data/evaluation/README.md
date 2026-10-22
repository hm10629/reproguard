# 评测集目录说明

本目录用于存放**真实公开项目**的人工标注，供 `src/evaluation.py` 对照工具判定与人工判定。

## 当前状态

U-Net 真实公开项目已完成 6 条核心规则人工标注，并生成正式评测结果。

U-Net 目录中来自旧 Claude 工作区的迁移文件仍只作为复核线索；正式指标使用人工重新核验后生成的 `unet-pytorch/expected-findings.json`。

当前有 1 个已进入核心规则评测的项目和 2 个未标注候选项目：

| 目录 | 项目 | 许可证 | 固定 commit | 本轮评测范围 | 标注状态 |
| --- | --- | --- | --- | --- | --- |
| `unet-pytorch/` | jaxony/unet-pytorch（U-Net 第三方 PyTorch 实现） | MIT（已核验） | `2bb0e44a2d5c7c04b589d5d942673aee52bcff58` | 不完整复现链路 / 缺口发现边界样例 | **已标注6条核心规则，其余9条未标注** |
| `darknet-yolov3/` | pjreddie/darknet（YOLOv3） | **待确认（`needs_verification`）** | `f6afaabcdf85f77e7aff2ec55c020c0e297c77f9` | **暂缓正式评测**（`needs_verification` 未关闭） | 未标注 |
| `google-bert/` | google-research/bert（BERT，仓库已归档） | Apache-2.0（已核验） | `eedf5716ce1268e56f0a50264a88cafad334ac61` | **只评测微调阶段（fine-tuning）** | 未标注 |

候选项目的来源、许可证证据与已知复现风险见各目录的 `source.md`；汇总说明见 `docs/评测候选项目.md`。

### 本轮已确认决策（由人确认于 2026-10-05，T-016）

| # | 决策 | 落实位置 |
| --- | --- | --- |
| 1 | 三候选定位：U-Net=不完整复现链路样例；darknet=**暂缓正式评测**；BERT=**只评测微调阶段** | 各 `source.md`、`docs/评测候选项目.md` |
| 2 | 固定 commit：unet `2bb0e44a…`、darknet `f6afaabc…`、bert `eedf5716…` | 各 `source.md`、上表 |
| 3 | 论文 PDF 不入库；代码本地 clone 不入库；权重与数据集不入库 | 本文件「材料放置规则」、`.gitignore` |
| 4 | `reports/` 保留一组经检查的演示报告；临时结果另放其他目录 | `docs/评测候选项目.md` |
| 5 | Git 身份、远程仓库、`CONTRIBUTORS.md` 真实署名稍后由人处理 | `docs/评测候选项目.md` 待办 |

- 真实项目需要由人选择合法来源并提供数据，本项目**不会自动下载论文或代码仓库**，也不会虚构标注结果。
- `src/evaluation.py` 只识别含 `expected-findings.json` 的目录；当前会评测 U-Net，并忽略尚未标注的 YOLOv3 与 BERT。
- 当前真实评测仅含 U-Net 的 6 条核心规则：初始基线精确状态一致率50%、缺口召回率50%；针对 R001、R003、R014 的完整性判断改进后，同组复测精确状态一致率与缺口召回率均为100%。全部人工标签均为缺口正类，且规则针对同组失败样本做过修改，因此不能声称已验证误报率或跨项目泛化性能。
- 正式人类可读报告见 `reports/evaluation.md`，机器可读结果见 `reports/evaluation.json`。

只想验证「规则本身有没有写对」时，请把评测脚本指向固定样例目录：

```powershell
python -m src.evaluation --root data\examples
```

`data/examples/incomplete-ml-project/` 是**自造样例**，其 `expected-findings.json` 目前能与工具输出完全一致（15/15）。这只能证明规则在样例上自洽，**不能证明工具在真实论文上有效**。

## 目录格式

每个项目是 `data/evaluation/` 下的一个直接子目录：

```text
data/evaluation/
├─ README.md                     ← 本文件
├─ schema.json                   ← 标注文件格式定义
└─ <项目名>/
   ├─ paper.txt  (或 .md / .pdf)  ← 论文正文
   ├─ repository/                 ← 代码仓库内容
   │  ├─ README.md
   │  ├─ requirements.txt
   │  └─ ...
   └─ expected-findings.json      ← 人工标注
```

要求：

- 论文文件名固定为 `paper.txt` / `paper.md` / `paper.pdf` 之一，脚本会自动探测。
- 仓库目录名固定为 `repository/`。
- 缺少论文、缺少 `repository/`、缺少标注文件，脚本都会给出明确错误，不会静默跳过。
- 没有 `expected-findings.json` 的子目录会被**忽略**，因此可以放未标注的素材。

## 材料放置规则

默认策略（T-015 定稿）：**论文只留来源链接，代码本地 clone 不入库，权重与数据集一律不入库。**

| 材料 | 默认策略 | 说明 |
| --- | --- | --- |
| 论文 | 来源链接 + 本地临时 PDF | 文档中记录论文来源链接；PDF 可在本机用于阅读与评测；**PDF 不入公开仓库**（`.gitignore` 已排除 `data/evaluation/*/paper.pdf`） |
| 代码仓库 | 本地 clone，不入库 | clone 到 `data/evaluation/<项目>/repository/` 供本机运行真实评测；**第三方代码快照不入公开仓库**（`.gitignore` 已排除 `data/evaluation/*/repository/`） |
| 模型权重 | 不入库 | 只记录官方获取方式与体积风险，不下载、不提交 |
| 数据集 | 不入库 | 同上，只记录官方获取方式 |

补充要求：

1. 论文优先选择开放获取（如 arXiv）或已获授权的版本；**没有明确再分发许可的 PDF 不得提交进仓库。**
2. 代码仓库使用许可证明确的开源项目，并**记录仓库地址与 commit**，保证标注可回溯到具体版本。
3. 若材料不适合入库，只提交标注文件，并在 `source.md` / `source` 字段中写明来源与获取方式。
4. 论文与代码的版权归原作者，本项目**不主张其著作权**。

## 标注文件格式

`expected-findings.json` 沿用既有固定样例的字段，不新增编造字段。最小可用形式：

```json
{
  "sample_id": "my-project",
  "purpose": "真实公开项目人工标注",
  "expectations": {
    "R001": "found",
    "R002": "partial",
    "R003": "missing"
  }
}
```

`expectations` 也接受逐条记录形式（便于附加说明）：

```json
{
  "expectations": [
    {"rule_id": "R001", "expected": "found", "note": "README 已说明依赖版本"},
    {"rule_id": "R002", "expected": "missing"}
  ]
}
```

字段约束（由 `schema.json` 定义，同时由 `src/evaluation.py` 强制校验）：

| 约束 | 说明 |
| --- | --- |
| `rule_id` | 必须匹配 `R` 加三位数字，例如 `R005` |
| `expected` | 必须是 `found` / `partial` / `missing` / `not_applicable` / `needs_review` 之一 |
| 重复 `rule_id` | 拒绝（列表形式下可检测） |
| 空 `expectations` | 拒绝 |

> **规则编号命名空间（M4，2026-10-04 核查）**：规则编号固定为 `R001`–`R015`，**不使用 `P` / `F` 等前缀**。`schema.json` 与 `src/evaluation.py` 均以 `^R[0-9]{3}$` 约束 `rule_id`，从格式层面阻断混用。`P###` / `F###` 仅作为**模型辅助层的来源编号**（`src/model_assist.py` 的 `source_refs`）存在，与规则编号属于不同命名空间，二者不共用。

## 人工标注责任与口径

标注必须由人完成，并且**按论文与仓库的原文判**，不是按工具输出反推。判定口径与 `docs/检查规则-v0.1.md` 一致：

| 状态 | 含义 |
| --- | --- |
| `found` | 存在明确、可定位的证据，信息足以支持复现 |
| `partial` | 只找到部分信息，例如说了用哪个数据集但没给版本或划分方式 |
| `missing` | 在当前检查范围内没有找到 |
| `not_applicable` | 该规则不适用于当前项目 |
| `needs_review` | 发现了可能相关的材料，但无法可靠判断 |

标注时建议记录：

- 每条判定的依据（论文页码 / 文件行号），便于复核分歧；
- 标注人与标注日期；
- 若与工具判定不一致，简要写明是人判错、工具错，还是口径有歧义。

**注意：不要把工具的判定结果直接填进 `expected-findings.json`。** 那样得到的将是 100% 一致率，毫无评测意义。

## 指标口径

`src/evaluation.py` 输出三类数字：

| 指标 | 含义 |
| --- | --- |
| `agreement` | 人工与工具状态**完全一致**的比例，覆盖全部 `rule_id` |
| `gap_precision` | 工具标为需处理（`missing` / `partial` / `needs_review`）的条目中，人工也标为需处理的比例 |
| `gap_recall` | 人工标为需处理的条目中，工具也标出的比例 |

分母为零时取值 `0.0` 并在输出中保留计数，不会报错。判断有效性时应**同时看召回率**：只报一致率会掩盖「工具什么都没发现」这种失效。

`docs/项目方案书.md` 第 7 节提到的「证据覆盖率」是另一个指标，它的分母排除了 `missing` 项，因此**不衡量漏报**，不能与上述召回率互相替代。

## 评测前置条件

一个候选项目要进入真实评测，必须**同时**具备以下三项，缺一不可：

- [ ] 论文文件：`paper.txt`（或 `paper.md` / `paper.pdf`）
- [ ] 代码仓库目录：`repository/`
- [ ] 人工完成的标注：`expected-findings.json`

**缺任何一项时**：

- 该项目**不会**被评测脚本识别（脚本只认 `expected-findings.json`）；
- 对该目录运行评测会得到「评测集为空」并**以退出码 2 结束**，这是**预期行为**，不是故障；
- 报告中必须写明缺失原因，**不得静默跳过，也不得用占位数据补齐**。

`annotation-template.json` 是**待标注模板**：其中的 `TODO` 不是合法状态值，无法通过 `schema.json` 校验，也**不会**被脚本识别。完成人工标注后需改名为 `expected-findings.json`。

## 运行方式

```powershell
python -m src.evaluation --root data\evaluation
python -m src.evaluation --root data\evaluation --format json --output reports\evaluation.json
```

退出码：`0` 成功；`2` 评测集为空或标注文件不可用（错误写入标准错误）。

## 许可证注意事项

- 本目录下的标注结果由标注人创作，建议采用与本项目一致的 MIT 许可，或单独声明。
- 引用的论文与代码仓库版权归原作者，本项目**不主张其著作权**。
- 提交前核对每个项目的许可证是否允许你想做的再分发方式；不确定时，只提交标注文件与来源链接，不提交原始文件。
