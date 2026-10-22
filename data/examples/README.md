# 示例项目

这里保存用于开发和评测“科研复现体检员”的本地模拟样例。

当前样例 `incomplete-ml-project` 故意保留若干复现信息缺口，用来验证检查规则能否正确发现问题。样例不需要联网，也不需要真正训练模型。

## 预期检查结果

- R001 项目说明文档：found
- R002 依赖及版本：partial
- R003 数据集来源和下载方式：partial
- R004 数据预处理和划分：missing
- R005 随机种子：found
- R006 关键训练超参数：partial
- R007 硬件和运行环境：missing
- R008 实验入口命令：found
- R009 评价指标计算：partial
- R010 结果输出：found
- R011 模型、数据集和代码名称对应：found
- R012 预训练权重来源：missing
- R013 关键版本或提交号：missing
- R014 许可证和数据限制：missing
- R015 常见问题说明：missing

上表与 `incomplete-ml-project/expected-findings.json` 一致，由 `tests/test_rules.py` 的 `test_matches_sample_expectations` 逐条校验。

## 覆盖边界

本样例覆盖 `found`、`partial`、`missing` 三种状态，**不覆盖** `needs_review`。

`needs_review` 由 `tests/test_rules.py` 中的临时样例覆盖，不落在本目录。该样例的论文不出现 `tinycnn`、`cifar-10`、`imagenet`、`mnist` 四个术语，使 R011 走兜底分支返回 `needs_review`，且按设计不附带任何证据。

为什么不把该状态并入本样例：

- R011 在本样例的预期状态是 `found`，改判为 `needs_review` 会连带修改 `expected-findings.json` 和全部报告产物
- 用临时目录样例可以在不改变固定样例报告结果的前提下覆盖该状态

对应测试为 `test_r011_returns_needs_review_without_known_terms` 与 `test_needs_review_finding_enters_action_items`。
