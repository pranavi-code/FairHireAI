"""Train a text baseline, MAG-BERT, or MAG-BERT-ARL model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml_service.training.engine import Trainer, TrainingConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--resume")
    args = parser.parse_args()
    config = TrainingConfig.load(Path(args.config).resolve())
    result = Trainer(config).fit(resume=args.resume)
    print(json.dumps(result, indent=2))
    print("FI TRAINING COMPLETE")


if __name__ == "__main__":
    main()
