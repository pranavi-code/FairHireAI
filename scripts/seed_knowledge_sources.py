"""Idempotently seed the trusted source registry through the Supabase Data API."""

from __future__ import annotations

import argparse
import os

import httpx

from backend.app.domain.knowledge import load_source_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--supabase-url",
        default=os.getenv("ROLEREADY_SUPABASE_URL"),
    )
    parser.add_argument(
        "--secret-key",
        default=os.getenv("ROLEREADY_SUPABASE_SECRET_KEY"),
        help="Server-only Supabase secret/service key. Never use a frontend key.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.supabase_url or not args.secret_key:
        raise RuntimeError(
            "ROLEREADY_SUPABASE_URL and ROLEREADY_SUPABASE_SECRET_KEY are required"
        )
    rows = [source.database_row() for source in load_source_registry()]
    with httpx.Client(
        base_url=args.supabase_url.rstrip("/"),
        headers={
            "apikey": args.secret_key,
            "Authorization": f"Bearer {args.secret_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        },
        timeout=30.0,
    ) as client:
        response = client.post(
            "/rest/v1/knowledge_sources",
            params={"on_conflict": "id"},
            json=rows,
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list) or len(payload) != len(rows):
        raise RuntimeError("Supabase returned an incomplete source-registry seed result")
    print(f"KNOWLEDGE SOURCE SEED PASSED: {len(payload)} upserted")


if __name__ == "__main__":
    main()
