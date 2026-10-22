# GitHub Actions 快速开始

ReproGuard 提供复合 Action。目标仓库无需复制 `src/`；发布 `v1` 标签后，只需添加一个 workflow，并将 `constraints` 改成仓库内论文或实验协议的路径。

```yaml
name: ReproGuard

on:
  pull_request:

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hm10629/reproguard@v1
        with:
          constraints: docs/paper.pdf
```

`hm10629/reproguard@v1` 是计划发布地址；在远程仓库和 `v1` 标签创建完成前，该引用尚不可用。仓库没有可公开的论文或协议时，可以删去 `constraints`，系统仍会检查参数、随机种子、依赖环境和数据/评价流程变更，但不能给出论文页码证据。

## 默认行为

- 从 `pull_request` 事件下载真实 unified diff；
- 运行确定性规则，不需要 API Key；
- 在改动行生成 GitHub warning；
- 把完整报告写入 Job Summary；
- 创建一条带隐藏标记的 PR 评论，后续提交更新同一条评论，不重复刷屏；
- 输出 `reproguard-report.json` 和 `reproguard-report.md`。

来自 fork 的 PR 可能拿不到写评论权限。这种情况下 Action 会保留 Job Summary 和报告文件，只把评论失败降级为 warning，不会丢失审查结果。

## 可选输入

| 输入 | 默认值 | 说明 |
| --- | --- | --- |
| `constraints` | 空 | 论文或实验协议路径，支持 `.txt`、`.md`、`.pdf` |
| `fail-on` | `never` | `never`、`high` 或 `any` |
| `post-comment` | `true` | 是否创建或更新 PR 评论 |
| `model-mode` | `rules` | `rules`、`ollama` 或 `deepseek` |
| `model-name` | 空 | 模型名覆盖值 |
| `diff-path` | 空 | 本地历史 diff，用于真实 PR 回放 |

## DeepSeek 模式

先在目标仓库创建名为 `DEEPSEEK_API_KEY` 的 Actions Secret，再增加：

```yaml
      - uses: hm10629/reproguard@v1
        with:
          constraints: docs/paper.pdf
          model-mode: deepseek
          model-name: deepseek-chat
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
```

`【必须人工复核】` 启用云端模型前，确认论文、协议和 diff 允许发送给该服务。模型建议仅作为待确认信息，不能替代确定性规则或维护者决定。

## 发布前人工步骤

1. 确认团队 GitHub 组织或账号、仓库名和公开范围；
2. 确认 `hm10629/reproguard@v1` 已能从公开测试仓库成功调用；
3. 在 GitHub 上创建 `v1` 发布标签；
4. 用一个公开测试仓库提交 PR，确认 warning、Job Summary、评论更新和 artifact 均正常；
5. 截取普通代码审查与 ReproGuard 输出的并排画面。
