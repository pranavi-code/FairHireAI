"""Build deterministic, idempotent SQL for reviewed knowledge and questions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

from backend.app.domain.knowledge import (
    load_initial_knowledge_seed,
    resolve_source_document_id,
)

SqlKind = Literal["scalar", "json", "text_array", "vector"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--knowledge-output",
        type=Path,
        default=Path("outputs/knowledge/supabase_knowledge_seed.sql"),
    )
    parser.add_argument(
        "--questions-output",
        type=Path,
        default=Path("outputs/knowledge/supabase_question_seed.sql"),
    )
    parser.add_argument(
        "--knowledge-embeddings",
        type=Path,
        default=Path("outputs/knowledge/gemini_embeddings.v1.json"),
    )
    parser.add_argument(
        "--validated-questions",
        type=Path,
        default=Path("outputs/knowledge/question_bank_validation.v1.json"),
    )
    return parser.parse_args()


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _value(value: Any, kind: SqlKind = "scalar") -> str:
    if value is None:
        return "null"
    if kind == "json":
        return f"{_quote(json.dumps(value, ensure_ascii=False, separators=(',', ':')))}::jsonb"
    if kind == "text_array":
        return (
            "array["
            + ",".join(_quote(str(item)) for item in value)
            + "]::text[]"
        )
    if kind == "vector":
        if not isinstance(value, list) or len(value) != 384:
            raise RuntimeError("Every published embedding must have 384 dimensions")
        return (
            _quote(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            + "::extensions.vector(384)"
        )
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return _quote(str(value))


def _upsert(
    *,
    table: str,
    row: dict[str, Any],
    conflicts: list[str],
    kinds: dict[str, SqlKind] | None = None,
) -> str:
    kinds = kinds or {}
    columns = list(row)
    values = [_value(row[column], kinds.get(column, "scalar")) for column in columns]
    updates = [
        f"{column} = excluded.{column}"
        for column in columns
        if column not in conflicts
    ]
    return (
        f"insert into public.{table} ({', '.join(columns)})\n"
        f"values ({', '.join(values)})\n"
        f"on conflict ({', '.join(conflicts)}) do update set\n    "
        + ",\n    ".join(updates)
        + ";\n"
    )


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return payload


def main() -> None:
    args = parse_args()
    seed = load_initial_knowledge_seed()
    embeddings = _load_json(args.knowledge_embeddings)
    validated = _load_json(args.validated_questions)
    if validated.get("validated_count") != 36 or validated.get("rejected_count") != 0:
        raise RuntimeError("Refusing to publish an incomplete validated question bank")

    knowledge_vectors = {
        (str(row["document_id"]), str(row["chunk_key"])): row
        for row in embeddings["knowledge_chunks"]
    }
    resource_vectors = {
        (str(row["resource_id"]), str(row["chunk_key"])): row
        for row in embeddings["learning_resources"]
    }
    documents = {item.document_id: item for item in seed.documents}
    knowledge_statements = ["begin;\n"]
    for document in seed.documents:
        knowledge_statements.append(
            _upsert(
                table="source_documents",
                row=document.document_database_row(),
                conflicts=["id"],
                kinds={"metadata": "json"},
            )
        )
        chunk = document.chunk_database_row()
        vector = knowledge_vectors[(document.document_id, document.chunk_key)]
        chunk["embedding"] = vector["embedding"]
        chunk["embedding_model"] = vector["embedding_model"]
        knowledge_statements.append(
            _upsert(
                table="knowledge_chunks",
                row=chunk,
                conflicts=["document_id", "chunk_key"],
                kinds={
                    "competency_ids": "text_array",
                    "skill_terms": "text_array",
                    "technologies": "text_array",
                    "embedding": "vector",
                },
            )
        )
    for resource in seed.resources:
        document = documents[resource.document_id]
        vector = resource_vectors[(resource.resource_id, "reviewed-summary")]
        resource_row = resource.database_row(document)
        resource_row["embedding"] = vector["embedding"]
        resource_row["embedding_model"] = vector["embedding_model"]
        knowledge_statements.append(
            _upsert(
                table="learning_resources",
                row=resource_row,
                conflicts=["id"],
                kinds={
                    "competency_ids": "json",
                    "skill_terms": "text_array",
                    "technologies": "text_array",
                    "learning_outcomes": "text_array",
                    "embedding": "vector",
                },
            )
        )
        chunk = resource.chunk_database_row(document)
        chunk["embedding"] = vector["embedding"]
        chunk["embedding_model"] = vector["embedding_model"]
        knowledge_statements.append(
            _upsert(
                table="learning_resource_chunks",
                row=chunk,
                conflicts=["resource_id", "chunk_key"],
                kinds={"embedding": "vector"},
            )
        )
    knowledge_statements.append("commit;\n")

    package_fields = [
        "id",
        "package_key",
        "version",
        "role_id",
        "competency_id",
        "skill_concept_ids",
        "seniority",
        "difficulty",
        "question_type",
        "prompt",
        "expected_concepts",
        "rubric",
        "follow_ups",
        "reference_explanation",
        "source_to_concept_mapping",
        "author_type",
        "model_id",
        "prompt_version",
        "validation_status",
        "automatic_validation",
        "reviewer_id",
        "embedding",
        "embedding_model",
    ]
    question_statements = ["begin;\n"]
    for raw_package in validated["packages"]:
        package = {field: raw_package.get(field) for field in package_fields}
        question_statements.append(
            _upsert(
                table="question_packages",
                row=package,
                conflicts=["id"],
                kinds={
                    "skill_concept_ids": "text_array",
                    "expected_concepts": "json",
                    "rubric": "json",
                    "follow_ups": "json",
                    "source_to_concept_mapping": "json",
                    "automatic_validation": "json",
                    "embedding": "vector",
                },
            )
        )
        for source_id, concepts in raw_package["source_to_concept_mapping"].items():
            source_document_id = resolve_source_document_id(
                source_id,
                str(raw_package["competency_id"]),
                concepts=[str(concept) for concept in concepts],
                seed=seed,
            )
            question_statements.append(
                _upsert(
                    table="question_package_sources",
                    row={
                        "question_package_id": raw_package["id"],
                        "source_document_id": source_document_id,
                        "supported_concepts": concepts,
                    },
                    conflicts=["question_package_id", "source_document_id"],
                    kinds={"supported_concepts": "text_array"},
                )
            )
    question_statements.append("commit;\n")

    args.knowledge_output.parent.mkdir(parents=True, exist_ok=True)
    args.knowledge_output.write_text(
        "".join(knowledge_statements),
        encoding="utf-8",
    )
    args.questions_output.parent.mkdir(parents=True, exist_ok=True)
    args.questions_output.write_text(
        "".join(question_statements),
        encoding="utf-8",
    )
    print(
        "SUPABASE SEED SQL BUILT: "
        f"{len(seed.documents)} documents, {len(seed.resources)} resources, "
        f"{len(validated['packages'])} question packages"
    )


if __name__ == "__main__":
    main()
