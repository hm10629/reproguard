# ReproGuard 在线 Action 验收记录

## 验收信息

| 项目 | 实际值 |
| --- | --- |
| 验收日期 | 2026-10-23 |
| 仓库 | `https://github.com/hm10629/reproguard`（私有） |
| 测试 PR | `https://github.com/hm10629/reproguard/pull/1` |
| 成功运行 | `https://github.com/hm10629/reproguard/actions/runs/39933280765` |
| 测试变更 | `train.py` 中 `batch_size` 默认值由 `64` 改为 `32` |
| 最终结果 | Success，1 项中风险，154 项本地自动化测试通过 |

## 已验证输出

- GitHub warning 精确定位到 `data/examples/incomplete-ml-project/repository/train.py:10`；
- Job Summary 显示 1 个变更文件、1 项中风险；
- GitHub Actions Bot 创建并更新同一条 PR 评论，没有重复刷屏；
- `reproguard-report` artifact 上传成功，包含 JSON 和 Markdown 报告；
- 工作流在规则模式下运行，无需模型或 API Key。

## 线上发现与修复

1. 首次运行失败：私有仓库的网页 `diff_url` 对 `GITHUB_TOKEN` 返回 404。修复为优先调用 PR API URL，并以 diff 媒体类型请求；保留旧事件的 `diff_url` 回退。
2. 第二次运行成功但报告 0 项风险：解析器未覆盖 `argparse.add_argument(..., default=...)`。补充 argparse 默认值解析及回归测试。
3. 第三次运行成功：warning、Summary、单条评论更新和 artifact 四项均通过。

以上修复已经进入 `main`。测试 PR 不合并，专门保留为比赛演示和在线验收证据。

## 结论边界

本次是在私有源仓库中使用 `uses: ./` 完成的同仓库在线验收，证明复合 Action 的核心在线流程可运行。由于仓库尚未公开、`v1` 标签尚未发布，本记录不等同于“第三方公开仓库通过 `hm10629/reproguard@v1` 跨仓库调用成功”。该项应在决定公开范围后另行验证。
