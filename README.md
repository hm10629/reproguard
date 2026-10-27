# ReproGuard 复现守门人

ReproGuard 是一个面向跨学科科研复现的证据化变更审查工具。它把论文、实验协议和开放复现档案中的关键条件，转化为可引用的约束；当代码、配置或实验记录发生 Pull Request 变更时，系统会检查这些变化是否可能破坏复现条件，并把风险定位到文件、行号和来源证据。它的核心优势不是“再做一个 AI 代码审查器”，而是把科研语义、版本协作和可追溯证据连接起来：确定性规则负责可重复判定，开源模型负责受约束的语义解释，最终结果回到 PR 评论、Job Summary 和 Markdown/JSON 报告中，由研究者完成确认。

ReproGuard 将论文、实验协议和开放复现档案中的关键约束，转化为可检查、可引用的证据；再把这些约束与 Pull Request 中的代码和配置变化逐项对照，定位可能影响复现的风险。检查结果会回到 PR 评论、Job Summary 和 Markdown/JSON 报告中，帮助维护者决定是否接受变更，并持续更新项目的复现档案。

当前版本以机器学习代码复现为可运行主线，底层的约束协议、证据链和规则接口同时面向生物信息、化学计算、材料实验和社会科学计算等数字化科研流程扩展。不同学科只需替换约束模板和证据规则，不必重建整套审查与协作流程。

## 当前目标

第一版解决一个可验证的闭环：

> 当科研仓库收到 PR 时，对照论文或实验协议识别实验参数、随机性、数据流程和依赖环境变化，给出带 diff 行号和来源位置的复现风险，交由维护者确认。

## MVP 工作流

```text
读取 GitHub PR diff
        ↓
加载论文、协议或复现档案中的研究约束
        ↓
规则检查参数、随机性、数据流程和环境变化
        ↓
开源模型分析变更的科研语义并引用来源
        ↓
输出 GitHub 行级注释和结构化风险报告
        ↓
维护者接受、驳回或解释，必要时更新复现档案
```

## 第一版暂不做

- 不承诺自动完成完整实验复现；
- 不替代通用 bug、安全、性能或代码风格审查；
- 不自动证明实验事实真实或论文结论正确；
- 不替代科研人员对方法和结果的专业判断；
- 不自动运行任意论文代码或连接实验室仪器；
- 不在第一版建设在线科研社区或企业级多用户系统。

## 目录

```text
docs/       项目方案和检查规则
data/       示例输入和评测数据
src/        应用代码
tests/      自动化测试
```

## 设计原则

1. 每个风险判断都要有证据，证据应指向论文页码、代码文件或配置字段。
2. “未找到信息”和“信息明确缺失”必须区分。
3. 模型负责非结构化步骤抽取和语义对齐，但模型输出默认进入人工复核。
4. 规则和 Schema 负责可解释检查、引用完整性与稳定导出。
5. 档案必须能被下一位研究者复用，而不是只给一个分数。
6. 优先支持本地部署，避免上传未公开的科研资料。

## 相关文档

- [项目方案书](docs/项目方案书.md)
- [重构与交付计划](docs/开放科研复现证据链_重构与交付计划.md)
- [检查规则 v0.1](docs/检查规则-v0.1.md)
- [使用说明](docs/使用说明.md)
- [演示流程](docs/演示流程.md)
- [PR 审查引擎接口](docs/PR审查引擎接口.md)
- [评测集格式说明](data/evaluation/README.md)
- [竞品与差异化对比](docs/竞品与差异化对比.md)
- [开源及第三方资源使用清单](docs/开源及第三方资源使用清单.md)
- [AI 真实调用记录](docs/AI真实调用记录.md)
- [发布检查清单](docs/发布检查清单.md)
- [参赛作品信息](docs/参赛作品信息.md)
- [技术报告初稿](docs/技术报告初稿.md)
- [答辩PPT结构](docs/答辩PPT结构.md)
- [演示视频脚本](docs/演示视频脚本.md)

## 五种运行方式

| 方式 | 说明 | 是否需要模型 |
| --- | --- | --- |
| 手工建档 | 只提供论文或协议，创建待人工填写的复现档案骨架 | 不需要 |
| AI 建档 | 本机开源模型从论文或协议中抽取带来源的研究主张与复现步骤 | 需要本机 Ollama |
| DeepSeek 云端建档 | 通过 OpenAI 兼容接口调用 DeepSeek，沿用相同来源约束 | 需要 API Key，材料会发送到所配置服务 |
| 论文 + 代码体检 | R001-R015 共15条规则检查论文与代码，也可叠加原模型辅助 | 模型可选 |
| PR 复现风险审查 | 读取 unified diff，对照论文/协议生成 GitHub 行级注释和报告 | 模型可选 |

AI 建档只能引用系统提供的 `P###` 来源编号。所有 AI 生成的主张、步骤和证据都标记为 `needs_review`，在研究者确认前不属于已确认科研事实。

## 当前实现

当前已经完成：

- 标准 unified diff 解析及变更文件、行号定位；
- PR 中实验参数、随机种子、依赖环境和数据/评价流程变化检查；
- 参数变更与论文/协议旧值的来源对齐；
- GitHub workflow command、Step Summary 和 JSON/Markdown 输出；
- PR 模型提示协议，强制模型风险引用真实 `D###` / `P###` 来源；
- 定义跨学科复现档案模型与 JSON Schema；
- 支持只输入论文或实验协议，不要求代码仓库；
- 支持本地开源模型抽取带来源的研究主张与复现步骤；
- 模型引用白名单、跨对象引用校验和人工复核状态；
- 复现档案 JSON / Markdown 导入、校验与导出；
- 网页工作台提供“论文/协议建档”和“论文+代码体检”双入口；
- 支持网页手工新增复现步骤，并记录逐步骤实际状态、参数、证据和主要结果；
- 自动检查预期参数与实际参数、完成步骤缺失证据等明确偏差；
- 支持署名的人工接受、驳回和修订记录；
- 支持 `.txt`、`.md` 和 `.pdf` 论文输入
- 扫描本地代码仓库并保留文件行号证据
- 执行 R001-R015 共 15 条确定性检查
- 输出 JSON 和 Markdown 报告
- 提供标准库网页界面，可在规则模式与本地模型模式之间切换
- 可选接入本机 Ollama 的开放模型，模型只负责抽取与提示
- 可选接入 DeepSeek/OpenAI 兼容 API，API Key 仅从指定环境变量读取
- 使用标准库 `unittest` 测试，默认规则模式不依赖大模型或网络
- 提供评测骨架 `src/evaluation.py`，可按 `rule_id` 对照工具判定与人工标注

当前工程主线已经切换为 PR 复现风险审查。U-Net论文与固定版本仓库继续作为复现基线案例；可复用的复合Action和入口workflow已建立，[Pytorch-UNet PR #141](data/cases/pytorch-unet-pr-141/source.md)已形成真实历史PR回放，并完成签署人工复核及漏报修复。U-Net 6条核心规则的真实人工标注、混淆矩阵、前后对照和带官方来源的竞品表也已完成。2026-10-22已完成一次`deepseek-chat`真实调用、逐项内容复核和沈智和签名确认；PR #1已完成在线Action验收，warning、Job Summary、单条评论更新和报告artifact均通过。非代码协议可通过同一diff接口检查温度、浓度、时长等字段，但系统只审查提交的数字材料，不证明线下实验真实发生。

## 快速开始

在其他GitHub仓库中启用PR自动审查，见[GitHub Actions快速开始](docs/GitHub_Actions快速开始.md)。当前仓库已公开，并完成同仓库与公开测试仓库的在线验收，记录见[在线Action验收记录](docs/在线Action验收记录.md)。`v1`标签已发布，其他仓库可通过 `hm10629/reproguard@v1` 接入。

启动网页：

```powershell
python -m src.web --host 127.0.0.1 --port 8765
```

只提供论文或实验协议，创建待人工填写的档案：

```powershell
python -m src.protocol_extract `
  --paper data\examples\incomplete-ml-project\paper.txt `
  --output reports\reproduction-passport
```

使用本地开源模型抽取步骤：

```powershell
python -m src.protocol_extract `
  --paper data\examples\incomplete-ml-project\paper.txt `
  --output reports\reproduction-passport `
  --model-mode ollama --model-name qwen2.5:3b
```

使用 DeepSeek 云端抽取前，先在当前 PowerShell 会话设置密钥：

```powershell
$env:DEEPSEEK_API_KEY="你的密钥"
python -m src.protocol_extract `
  --paper data\examples\incomplete-ml-project\paper.txt `
  --output reports\reproduction-passport `
  --model-mode deepseek
```

`【必须人工决定】` 未公开论文、实验记录或敏感数据是否允许发送到云端服务。默认演示优先使用 Ollama；不得把 API Key 写入仓库、报告或截图。

校验已有复现档案：

```powershell
python -m src.passport `
  --input data\examples\reproduction-passport-demo.json
```

## 评测状态

评测骨架已建立并可运行；U-Net 真实公开项目的 6 条核心规则已经完成人工标注与正式评测。

- 当前只有一个自造固定样例 `data/examples/incomplete-ml-project/`，含 R001-R015 共 15 条人工预期值。它的用途是验证规则本身，**不是真实论文评测集**，不能用于声称准确率。
- `data/evaluation/unet-pytorch/` 已完成 R001、R002、R003、R008、R011、R014 共 6 条核心规则的独立人工标注。初始基线精确状态一致率为 50%（3/6）；针对三条 `partial` 漏报改进完整性规则后，同组复测为 100%（6/6）。由于改进与复测使用同一项目且样本全部为缺口正类，该结果不能代表跨项目准确率，也不能评估误报率。详见 [真实项目核心规则评测](reports/evaluation.md)。
- YOLOv3 与 BERT 仍是候选项目，尚未纳入指标；汇总见 [评测候选项目](docs/评测候选项目.md)。
- 运行方式：

```powershell
python -m src.evaluation --root data\evaluation
```

- 10 月 25 日前的 U-Net 真实代码主案例核心标注已经完成；其余 9 条 U-Net 规则及其他候选项目属于扩展项。
- 真实项目需要由人选择合法来源并提供数据，本项目不自动下载论文或代码。

本地模型模式的演示命令：

```powershell
python -m src.cli `
  --paper data\examples\incomplete-ml-project\paper.txt `
  --repo data\examples\incomplete-ml-project\repository `
  --output reports\first-report `
  --model-mode ollama --model-name qwen2.5:3b
```

模型名可替换为本机已拉取的任意 Ollama 模型。模型服务不属于默认依赖，未安装时规则模式仍可离线运行。
