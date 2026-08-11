"""Create 384-d Gemini embeddings and optionally write them to Supabase."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx

from backend.app.config import get_settings
from backend.app.domain.knowledge import load_initial_knowledge_seed
from backend.app.providers.gemini import GeminiClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/knowledge/gemini_embeddings.v1.json"),
    )
    parser.add_argument(
        "--write-supabase",
        action="store_true",
        help="Write embeddings with the server-only Supabase secret key.",
    )
    parser.add_argument("--supabase-url", default=os.getenv("ROLEREADY_SUPABASE_URL"))
    parser.add_argument(
        "--secret-key",
        default=os.getenv("ROLEREADY_SUPABASE_SECRET_KEY"),
    )
    return parser.parse_args()


def _patch(
    client: httpx.Client,
    table: str,
    *,
    filters: dict[str, str],
    row: dict[str, object],
) -> None:
    response = client.patch(
        f"/rest/v1/{table}",
        params={key: f"eq.{value}" for key, value in filters.items()},
        headers={"Prefer": "return=minimal"},
        json=row,
    )
    response.raise_for_status()


def _write_output(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    args = parse_args()
    settings = get_settings()
    if not settings.gemini_configured or settings.gemini_api_key is None:
        raise RuntimeError("ROLEREADY_GEMINI_API_KEY is required")
    if settings.gemini_embedding_dimensions != 384:
        raise RuntimeError("The current Supabase knowledge schema requires 384 dimensions")

    seed = load_initial_knowledge_seed()
    documents = {item.document_id: item for item in seed.documents}
    payload: dict[str, object] = {
        "schema_version": "gemini-knowledge-embeddings-v1",
        "model": settings.gemini_embedding_model,
        "dimensions": settings.gemini_embedding_dimensions,
        "knowledge_chunks": [],
        "learning_resources": [],
    }
    if args.output.is_file():
        try:
            existing = json.loads(args.output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if (
            isinstance(existing, dict)
            and existing.get("model") == settings.gemini_embedding_model
            and existing.get("dimensions") == settings.gemini_embedding_dimensions
        ):
            payload["knowledge_chunks"] = existing.get("knowledge_chunks", [])
            payload["learning_resources"] = existing.get("learning_resources", [])
    existing_knowledge = {
        (str(item["document_id"]), str(item["chunk_key"])): item
        for item in payload["knowledge_chunks"]
        if isinstance(item, dict)
    }
    existing_resources = {
        (str(item["resource_id"]), str(item["chunk_key"])): item
        for item in payload["learning_resources"]
        if isinstance(item, dict)
    }
    with GeminiClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        generation_model=settings.gemini_generation_model,
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.gemini_embedding_dimensions,
        timeout_seconds=settings.gemini_timeout_seconds,
        max_retries=settings.gemini_max_retries,
    ) as gemini:
        knowledge_rows = []
        for document in seed.documents:
            key = (document.document_id, document.chunk_key)
            row = existing_knowledge.get(key)
            if row is None:
                vector = gemini.embed(
                    f"{document.context_prefix}\n{document.content}",
                    task_type="RETRIEVAL_DOCUMENT",
                )
                row = {
                    "document_id": document.document_id,
                    "chunk_key": document.chunk_key,
                    "embedding": vector,
                    "embedding_model": settings.gemini_embedding_model,
                }
                existing_knowledge[key] = row
                payload["knowledge_chunks"] = list(existing_knowledge.values())
                _write_output(args.output, payload)
            knowledge_rows.append(row)
        resource_rows = []
        for resource in seed.resources:
            document = documents[resource.document_id]
            key = (resource.resource_id, "reviewed-summary")
            row = existing_resources.get(key)
            if row is None:
                vector = gemini.embed(
                    (
                        f"{resource.title}\n{resource.description}\n"
                        f"{' | '.join(resource.learning_outcomes)}\n{document.content}"
                    ),
                    task_type="RETRIEVAL_DOCUMENT",
                )
                row = {
                    "resource_id": resource.resource_id,
                    "chunk_key": "reviewed-summary",
                    "embedding": vector,
                    "embedding_model": settings.gemini_embedding_model,
                }
                existing_resources[key] = row
                payload["learning_resources"] = list(existing_resources.values())
                _write_output(args.output, payload)
            resource_rows.append(row)
    payload["knowledge_chunks"] = knowledge_rows
    payload["learning_resources"] = resource_rows
    _write_output(args.output, payload)

    if args.write_supabase:
        if not args.supabase_url or not args.secret_key:
            raise RuntimeError(
                "ROLEREADY_SUPABASE_URL and ROLEREADY_SUPABASE_SECRET_KEY are required"
            )
        with httpx.Client(
            base_url=args.supabase_url.rstrip("/"),
            headers={
                "apikey": args.secret_key,
                "Authorization": f"Bearer {args.secret_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        ) as supabase:
            for row in knowledge_rows:
                _patch(
                    supabase,
                    "knowledge_chunks",
                    filters={
                        "document_id": str(row["document_id"]),
                        "chunk_key": str(row["chunk_key"]),
                    },
                    row={
                        "embedding": row["embedding"],
                        "embedding_model": row["embedding_model"],
                    },
                )
            for row in resource_rows:
                _patch(
                    supabase,
                    "learning_resource_chunks",
                    filters={
                        "resource_id": str(row["resource_id"]),
                        "chunk_key": str(row["chunk_key"]),
                    },
                    row={
                        "embedding": row["embedding"],
                        "embedding_model": row["embedding_model"],
                    },
                )
                _patch(
                    supabase,
                    "learning_resources",
                    filters={"id": str(row["resource_id"])},
                    row={
                        "embedding": row["embedding"],
                        "embedding_model": row["embedding_model"],
                    },
                )
    print(
        "GEMINI KNOWLEDGE EMBEDDINGS PASSED: "
        f"{len(knowledge_rows)} knowledge chunks, {len(resource_rows)} resources"
    )


if __name__ == "__main__":
    main()
