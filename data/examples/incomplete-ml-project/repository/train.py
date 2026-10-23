import argparse
import json
import random
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main():
    args = parse_args()
    random.seed(args.seed)

    # 模拟训练结果，使样例可快速运行且不需要下载数据。
    result = {
        "model": "TinyCNN",
        "dataset": "CIFAR-10",
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "seed": args.seed,
        "metric": "accuracy",
        "value": 0.81,
    }

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
