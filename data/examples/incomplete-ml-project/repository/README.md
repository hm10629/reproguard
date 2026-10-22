# TinyCNN 示例仓库

这是一个用于复现 CIFAR-10 图像分类实验的模拟代码仓库。

## 安装

```powershell
pip install -r requirements.txt
```

## 运行

```powershell
python train.py --epochs 20 --batch-size 64 --seed 42
```

训练结果会写入 `outputs/result.json`。

## 数据

程序使用 CIFAR-10，并由训练脚本自动加载。

注意：该仓库是检查器测试夹具，并非完整的可运行研究代码。
