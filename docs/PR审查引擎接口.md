# ReproGuard PR 审查引擎接口

本文档说明底层命令接口，供 `action.yml` 调用。面向仓库维护者的安装方式见 [GitHub Actions 快速开始](GitHub_Actions快速开始.md)。真实历史回放见 [Pytorch-UNet PR #141](../data/cases/pytorch-unet-pr-141/source.md)，最终截图仍由项目材料阶段另行整合。

## 输入

- 标准 unified diff：必需；
- 论文或实验协议：可选，支持 `.txt`、`.md`、`.pdf`；
- 模型模式：可选，规则模式不需要密钥或网络。

## 命令

```powershell
python -m src.pr_review `
  --diff change.diff `
  --constraints docs\paper.pdf `
  --output reports\pr-review `
  --github-annotations
```

可用参数：

| 参数 | 说明 |
| --- | --- |
| `--diff` | diff 文件路径；传 `-` 时从标准输入读取 |
| `--constraints` | 可选论文或协议路径 |
| `--output` | 输出文件前缀 |
| `--format` | `json`、`markdown` 或 `both` |
| `--github-annotations` | 输出 GitHub workflow command 注释 |
| `--fail-on` | `never`、`high` 或 `any`；默认不阻止合并 |
| `--model-mode` | `rules`、`ollama` 或 `deepseek` |

在 GitHub Actions 环境中，命令会自动：

- 将完整 Markdown 追加到 `$GITHUB_STEP_SUMMARY`；
- 将风险数量和报告路径写入 `$GITHUB_OUTPUT`；
- 在启用 `--github-annotations` 时为具体文件和行号输出 warning。

## 当前确定性规则

1. 实验参数发生变化；
2. 随机种子设置被删除；
3. 依赖或运行环境发生变化；
4. 数据处理、数据划分、损失函数或评价指标发生变化。

若论文或协议中能定位到变更前参数，参数变化会升级为高风险，并同时保留论文页码和 diff 行号。不能建立约束时只标记为待人工确认，不自动断言变更错误。

## 模型输出边界

模型只审查本次 diff 与提供的论文/协议来源：

- diff 来源编号为 `D###`；
- 论文或协议来源编号为 `P###`；
- 每条模型风险至少引用一个真实 `D###`；
- 编造的来源编号会被删除；
- 模型建议不会改写确定性规则结论，默认进入人工复核。

规则模式始终可以离线运行。Ollama 可使用 Qwen2.5-Coder、DeepSeek-Coder、CodeLlama 等本地模型；OpenAI 兼容模式可连接由团队选择的兼容服务。使用云端服务前必须确认材料上传范围和服务条款。

## 输出

`<output>.json` 包含：

- 变更文件列表；
- 高、中、低风险数量；
- 每条规则风险的文件、行号、说明、建议和证据；
- 可选模型建议及来源编号；
- `needs_human_review` 人工复核标记。

`<output>.md` 可直接用于 GitHub Step Summary 或 PR 总结评论。
