from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from backend.app.domain.knowledge import (
    QuestionSearchRequest,
    ResourceSearchRequest,
    build_seed_question_packages,
    load_initial_knowledge_seed,
    load_source_registry,
    resolve_source_document_id,
)
from backend.app.domain.roles import list_role_templates
from backend.app.repositories.supabase import SupabaseAttemptRepository


def test_source_registry_is_versioned_and_retrieval_safe() -> None:
    load_source_registry.cache_clear()
    sources = load_source_registry()
    assert len(sources) == 10
    assert len({source.source_id for source in sources}) == len(sources)
    assert all(
        not source.retrieval_enabled or source.review_status == "approved"
        for source in sources
    )
    assert all(
        source.license_url is not None
        for source in sources
        if source.content_policy == "open_content"
    )


def test_seed_question_packages_cover_every_role_but_remain_gated() -> None:
    packages = build_seed_question_packages()
    expected = sum(len(role.competencies) for role in list_role_templates())
    assert len(packages) == expected
    assert len({package.question_id for package in packages}) == expected
    assert all(
        package.validation_status == "pending_automatic_validation"
        for package in packages
    )
    assert all(set(package.rubric) == {"1", "2", "3", "4", "5"} for package in packages)


def test_initial_knowledge_seed_has_verified_relations_and_hashes() -> None:
    load_initial_knowledge_seed.cache_clear()
    seed = load_initial_knowledge_seed()
    documents = {document.document_id: document for document in seed.documents}
    assert len(seed.documents) == 14
    assert len(seed.resources) == 17
    assert len(
        {
            (
                document.source_id,
                str(document.canonical_url),
                document.version_label,
            )
            for document in seed.documents
        }
    ) == len(seed.documents)
    assert all(len(document.content_sha256) == 64 for document in seed.documents)
    assert all(resource.document_id in documents for resource in seed.resources)
    assert all(
        resource.database_row(documents[resource.document_id])["url_status"] == "valid"
        for resource in seed.resources
    )


def test_source_document_resolution_uses_source_and_competency() -> None:
    seed = load_initial_knowledge_seed()
    assert (
        resolve_source_document_id(
            "SRC-012",
            "frontend_engineering",
            seed=seed,
        )
        == "DOC-CS2023-FE-001"
    )
    assert (
        resolve_source_document_id(
            "SRC-013",
            "frontend_engineering",
            concepts=["component boundaries", "API lifecycle", "testing"],
            seed=seed,
        )
        == "DOC-MDN-HTTP-001"
    )


def test_search_contract_rejects_wrong_embedding_dimension() -> None:
    with pytest.raises(ValidationError, match="exactly 384"):
        QuestionSearchRequest(query="JWT authorization", query_embedding=[0.1] * 383)
    with pytest.raises(ValidationError, match="exactly 384"):
        ResourceSearchRequest(query="query plans", query_embedding=[0.1] * 385)


def test_repository_forwards_question_filters_to_hybrid_rpc() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(200, json=[])

    repository = SupabaseAttemptRepository(
        base_url="https://example.supabase.co",
        publishable_key="publishable",
        access_token="user-token",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = repository.search_question_packages(
            QuestionSearchRequest(
                query="junior API authorization",
                role_id="junior_backend_developer",
                competency_id="api_design",
                match_count=5,
            )
        )
    finally:
        repository.close()

    assert result == []
    assert captured["path"] == "/rest/v1/rpc/match_question_packages"
    assert '"p_competency_id":"api_design"' in str(captured["body"])
    assert '"p_query_embedding":null' in str(captured["body"])
