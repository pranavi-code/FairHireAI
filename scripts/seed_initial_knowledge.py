"""Seed reviewed summaries and learning resources using a server-only key."""

from __future__ import annotations

import argparse
import os

import httpx

from backend.app.domain.knowledge import load_initial_knowledge_seed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--supabase-url", default=os.getenv("ROLEREADY_SUPABASE_URL"))
    parser.add_argument(
        "--secret-key",
        default=os.getenv("ROLEREADY_SUPABASE_SECRET_KEY"),
        help="Server-only Supabase secret/service key. Never expose it to Vite.",
    )
    return parser.parse_args()


def _upsert(
    client: httpx.Client,
    table: str,
    rows: list[dict[str, object]],
    *,
    conflict: str,
) -> None:
    response = client.post(
        f"/rest/v1/{table}",
        params={"on_conflict": conflict},
        headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        json=rows,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or len(payload) != len(rows):
        raise RuntimeError(f"Supabase returned an incomplete {table} seed result")


def main() -> None:
    args = parse_args()
    if not args.supabase_url or not args.secret_key:
        raise RuntimeError(
            "ROLEREADY_SUPABASE_URL and ROLEREADY_SUPABASE_SECRET_KEY are required"
        )
    seed = load_initial_knowledge_seed()
    documents = {document.document_id: document for document in seed.documents}
    with httpx.Client(
        base_url=args.supabase_url.rstrip("/"),
        headers={
            "apikey": args.secret_key,
            "Authorization": f"Bearer {args.secret_key}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    ) as client:
        _upsert(
            client,
            "source_documents",
            [document.document_database_row() for document in seed.documents],
            conflict="id",
        )
        _upsert(
            client,
            "knowledge_chunks",
            [document.chunk_database_row() for document in seed.documents],
            conflict="document_id,chunk_key",
        )
        _upsert(
            client,
            "learning_resources",
            [
                resource.database_row(documents[resource.document_id])
                for resource in seed.resources
            ],
            conflict="id",
        )
        _upsert(
            client,
            "learning_resource_chunks",
            [
                resource.chunk_database_row(documents[resource.document_id])
                for resource in seed.resources
            ],
            conflict="resource_id,chunk_key",
        )
    print(
        "INITIAL KNOWLEDGE SEED PASSED: "
        f"{len(seed.documents)} documents/chunks, {len(seed.resources)} resources"
    )


if __name__ == "__main__":
    main()
