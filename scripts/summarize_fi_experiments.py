"""Create a comparison table from completed FI experiment runs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from ml_service.training.engine import TrainingConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--config-pattern",
        default="*_laptop.json",
        help="Only summarize runnable experiment configs matching this glob.",
    )
    args = parser.parse_args()
    config_root = Path(args.config_root).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for config_path in sorted(config_root.glob(args.config_pattern)):
        config = TrainingConfig.load(config_path)
        run_root = Path(config.output_dir)
        summary_path = run_root / "training_summary.json"
        metrics_path = run_root / "metrics.jsonl"
        row: dict[str, Any] = {
            "run_name": config.run_name,
            "model_type": config.model_type,
            "modalities": config.modalities,
            "loss": config.loss,
            "configured_epochs": config.epochs,
            "status": "pending",
            "completed_epochs": 0,
            "validation_loss": None,
            "mae": None,
            "rmse": None,
            "pearson": None,
            "threshold_accuracy": None,
            "threshold_f1": None,
            "best_checkpoint": None,
        }
        if metrics_path.is_file():
            metric_rows = [
                json.loads(line)
                for line in metrics_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if metric_rows:
                best = min(metric_rows, key=lambda item: item["validation_loss"])
                row.update(
                    {
                        key: best[key]
                        for key in (
                            "validation_loss",
                            "mae",
                            "rmse",
                            "pearson",
                            "threshold_accuracy",
                            "threshold_f1",
                        )
                    }
                )
                row["completed_epochs"] = max(int(item["epoch"]) for item in metric_rows)
                row["status"] = "incomplete"
        if summary_path.is_file():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            row["status"] = "complete"
            row["completed_epochs"] = summary["completed_epochs"]
            row["best_checkpoint"] = summary["best_checkpoint"]
        rows.append(row)
    if not rows:
        raise RuntimeError(
            f"No experiment configs matched {args.config_pattern!r} in {config_root}"
        )
    csv_path = output_root / "fi_experiment_comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    json_path = output_root / "fi_experiment_comparison.json"
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps(rows, indent=2))
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
