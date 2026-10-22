# ReproGuard PR 复现风险报告

- 变更文件：2
- 规则风险：3
- 高 / 中 / 低：3 / 0 / 0
- 结论边界：所有风险均需项目维护者确认，不代表自动判定研究无效。

## 规则检查

### PR001 [HIGH] 评价结果的归一化分母改为数据加载批次数

- 位置：`eval.py:12`
- 类型：`evaluation_denominator_change`
- 判断：本次 PR 新增了按 `len(loader)` 计算的计数，并将该计数用于评价结果除法。当批大小、尾批处理或样本数变化时，这可能改变指标口径。
- 建议：确认指标应按样本数还是批次数归一化；记录尾批处理方式，并补充变更前后的数值对比测试。
- 状态：等待人工确认
- 证据：
  - `eval.py:12`：    n_val = len(loader)  # the number of batch
  - `eval.py:32`：    return tot / n_val

### PR002 [HIGH] 数据处理或评价流程发生变化

- 位置：`eval.py:25`
- 类型：`pipeline_change`
- 判断：本次 PR 修改了数据处理、数据划分、损失函数或评价指标相关内容。
- 建议：确认论文/协议、配置、测试和结果说明是否同步，并补充变化前后的结果对比。
- 状态：等待人工确认
- 证据：
  - `eval.py:25`：                tot += F.cross_entropy(mask_pred, true_masks).item()
  - `eval.py:27`：                pred = torch.sigmoid(mask_pred)
  - `eval.py:29`：                tot += dice_coeff(pred, true_masks).item()

### PR003 [HIGH] 数据处理或评价流程发生变化

- 位置：`train.py:38`
- 类型：`pipeline_change`
- 判断：本次 PR 修改了数据处理、数据划分、损失函数或评价指标相关内容。
- 建议：确认论文/协议、配置、测试和结果说明是否同步，并补充变化前后的结果对比。
- 状态：等待人工确认
- 证据：
  - `train.py:38`：    val_loader = DataLoader(val, batch_size=batch_size, shuffle=False, num_workers=8, pin_memory=True, drop_last=True)
  - `train.py:38 (removed)`：    val_loader = DataLoader(val, batch_size=batch_size, shuffle=False, num_workers=8, pin_memory=True)
