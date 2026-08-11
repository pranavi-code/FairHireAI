from __future__ import annotations

import argparse

from backend.app.config import get_settings
from backend.app.workers.runtime import run_worker


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FairHireAI durable worker.")
    parser.add_argument("--once", action="store_true", help="Claim at most one job.")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if not 0.25 <= args.poll_seconds <= 60:
        parser.error("--poll-seconds must be between 0.25 and 60")
    run_worker(
        get_settings(),
        once=args.once,
        poll_seconds=args.poll_seconds,
    )


if __name__ == "__main__":
    main()
