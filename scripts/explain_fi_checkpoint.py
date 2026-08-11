"""Generate Gradient SHAP evidence for one trained FI sample."""

from __future__ import annotations

import argparse
import json

from ml_service.explainability.gradient_shap import explain_checkpoint_sample


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--noise-standard-deviation", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=8)
    args = parser.parse_args()
    artifacts = explain_checkpoint_sample(
        config_path=args.config,
        checkpoint_path=args.checkpoint,
        video_id=args.video_id,
        output_root=args.output_root,
        samples=args.samples,
        noise_standard_deviation=args.noise_standard_deviation,
        seed=args.seed,
    )
    print(
        json.dumps(
            {
                "summary": str(artifacts.summary_path),
                "arrays": str(artifacts.arrays_path),
            },
            indent=2,
        )
    )
    print("FI GRADIENT SHAP PASSED")


if __name__ == "__main__":
    main()
