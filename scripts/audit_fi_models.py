"""Run the permitted FI V2 fairness and error audit."""

from __future__ import annotations

import argparse
import json

from ml_service.evaluation.fairness_audit import run_fairness_error_audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--selected-run", default="fi_v2_mag_bert")
    args = parser.parse_args()
    audit = run_fairness_error_audit(
        config_root=args.config_root,
        output_root=args.output_root,
        selected_run=args.selected_run,
    )
    print(
        json.dumps(
            {
                "schema_version": audit["schema_version"],
                "experiments": audit["experiment_count"],
                "validation_samples": audit["validation_samples"],
                "decision": audit["decision"],
                "artifacts": audit["artifacts"],
            },
            indent=2,
        )
    )
    print("FI FAIRNESS AND ERROR AUDIT PASSED")


if __name__ == "__main__":
    main()
