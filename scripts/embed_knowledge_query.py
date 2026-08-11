"""Create one Gemini retrieval-query embedding for semantic-search verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.config import get_settings
from backend.app.providers.gemini import GeminiClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/knowledge/query_embedding.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    if not settings.gemini_configured or settings.gemini_api_key is None:
        raise RuntimeError("ROLEREADY_GEMINI_API_KEY is required")
    with GeminiClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        generation_model=settings.gemini_generation_model,
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.gemini_embedding_dimensions,
        timeout_seconds=settings.gemini_timeout_seconds,
        max_retries=settings.gemini_max_retries,
    ) as client:
        vector = client.embed(args.query, task_type="RETRIEVAL_QUERY")
    payload = {
        "query": args.query,
        "embedding_model": settings.gemini_embedding_model,
        "embedding": vector,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"GEMINI QUERY EMBEDDING PASSED: {len(vector)} dimensions")


if __name__ == "__main__":
    main()
