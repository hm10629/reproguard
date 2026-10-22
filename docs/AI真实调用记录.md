# AI 真实调用记录

> 当前状态：**DeepSeek真实调用、逐项内容复核和团队成员签名确认均已完成。** 本文件只记录可由现有输出或操作者确认的事实；未随输出保存的信息不作猜测。

## 调用前人工确认

- [x] 输入为项目自造公开样例，不含未公开论文、个人信息或商业秘密。
- [x] 已记录提供方、实际模型参数、调用时间和输出文件；有效基础URL及服务端具体版本未在输出中持久化，按“无法从现有证据复核”披露。
- [x] 仓库敏感信息扫描未发现 API Key；密钥未写入输出或文档。

## 调用记录

| 字段 | 实际值 |
| --- | --- |
| 调用日期与时区 | 2026-10-22 21:10:56，Asia/Shanghai（以输出文件时间为准） |
| 提供方 | DeepSeek API，使用项目的 OpenAI 兼容适配器 |
| 模型名称与版本 | 实际`--model-name`为`deepseek-chat`；服务端具体构建版本未返回 |
| 基础 URL | 保存输出未持久化有效值，无法从现有证据复核；项目默认配置为`https://api.deepseek.com` |
| 输入材料 | `data/examples/incomplete-ml-project/paper.txt`，项目自造公开样例 |
| 调用入口 | `python -m src.protocol_extract --model-mode deepseek` |
| 抽取状态 | `ok`（调用终端结果由操作者确认） |
| 模型输出文件 | `reports/ai-real-call.json`、`reports/ai-real-call.md` |
| 输出性质 | 来源约束和Schema转换后的复现档案；未保存原始HTTP响应 |
| 来源编号是否全部有效 | 是；`P002`、`P004`、`P005`、`P007`均与输入原文一致 |
| 有无虚构、漏项或越权结论 | 未发现虚构编号或无来源数值；发现完整复现信息仍有八类缺失，已保留为复核提醒 |
| 对生成内容的修改 | 未修改两份生成文件；新增独立复核记录，避免把事后修改冒充原始输出 |
| 最终是否采纳 | 已采纳两条主张和四个步骤，保留八类缺失提醒；沈智和于2026-10-22确认 |

完整逐项核对见 [AI真实调用人工复核](AI真实调用人工复核.md)。

## 建议演示命令

本地 Ollama：

```powershell
python -m src.protocol_extract `
  --paper data\examples\incomplete-ml-project\paper.txt `
  --output reports\ai-real-call `
  --model-mode ollama `
  --model-name qwen2.5:3b
```

DeepSeek 兼容接口：

```powershell
$env:DEEPSEEK_API_KEY="在本机输入，不要写入文档"
python -m src.protocol_extract `
  --paper data\examples\incomplete-ml-project\paper.txt `
  --output reports\ai-real-call `
  --model-mode deepseek `
  --model-name deepseek-chat
```

本次已保存处理后输出和逐项复核结论。当前实现未保存DeepSeek原始HTTP响应，材料中不得把处理后档案称为“逐字原始响应”。
