from io import BytesIO
from uuid import uuid4

from docx import Document
from fastapi.testclient import TestClient

from backend.app.api.dependencies import authenticated_user_id
from backend.app.domain.documents import DocumentExtractionError, extract_document
from backend.app.domain.resume import extract_resume_evidence
from backend.app.main import app


def test_text_resume_extraction_retains_exact_spans() -> None:
    content = (
        b"Roopika Example\n"
        b"Technical Skills\n"
        b"Python, FastAPI, PostgreSQL\n"
        b"Projects\n"
        b"- Placement readiness API with audit logs\n"
        b"Certifications\n"
        b"Cloud fundamentals certificate\n"
    )
    document = extract_document("resume.txt", content)
    evidence = extract_resume_evidence(document)

    assert document.sha256 == evidence.document_sha256
    assert [claim.claim_type for claim in evidence.claims] == [
        "skill",
        "skill",
        "skill",
        "project",
        "certification",
    ]
    for claim in evidence.claims:
        source = claim.source
        assert document.text[source.start_character : source.end_character] == source.source_text
    assert evidence.claims[0].normalized_text == "Python"


def test_docx_extraction_reads_paragraphs_and_tables() -> None:
    source = Document()
    source.add_paragraph("Junior Backend Developer")
    table = source.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Python"
    table.cell(0, 1).text = "SQL"
    output = BytesIO()
    source.save(output)

    document = extract_document("role.docx", output.getvalue())

    assert document.document_kind == "docx"
    assert "Junior Backend Developer" in document.text
    assert "Python | SQL" in document.text
    assert document.pages[0].page is None


def test_extension_and_content_mismatch_is_rejected() -> None:
    try:
        extract_document("fake.txt", b"%PDF-1.7\n")
    except DocumentExtractionError as exc:
        assert exc.code == "type_mismatch"
    else:
        raise AssertionError("Mismatched PDF content should be rejected")


def test_jd_upload_extracts_and_maps_supported_role() -> None:
    app.dependency_overrides[authenticated_user_id] = uuid4
    client = TestClient(app)
    jd = (
        "We are hiring a Junior Backend Developer to build REST APIs using "
        "Python, FastAPI, PostgreSQL, Git, testing, and debugging."
    )

    try:
        response = client.post(
            "/api/v1/documents/job-description",
            files={"file": ("job.txt", jd.encode(), "text/plain")},
        )
    finally:
        app.dependency_overrides.pop(authenticated_user_id, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["document"]["sha256"]
    assert payload["role_mapping"]["status"] == "detected"
    assert payload["role_mapping"]["mapping_version"] == "optional-jd-mapper-v2"
    assert payload["role_mapping"]["role_id"] == "junior_backend_developer"


def test_resume_upload_returns_traceable_evidence() -> None:
    app.dependency_overrides[authenticated_user_id] = uuid4
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/documents/resume",
            files={
                "file": (
                    "resume.md",
                    b"Skills\nPython, SQL\nProjects\n- Built a REST API",
                    "text/markdown",
                )
            },
        )
    finally:
        app.dependency_overrides.pop(authenticated_user_id, None)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["evidence"]["claims"]) == 3
    assert payload["evidence"]["claims"][0]["source"]["source_text"] == "Python"


def test_scanned_or_blank_text_is_rejected() -> None:
    app.dependency_overrides[authenticated_user_id] = uuid4
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/documents/resume",
            files={"file": ("empty.txt", b" \n\t", "text/plain")},
        )
    finally:
        app.dependency_overrides.pop(authenticated_user_id, None)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "no_extractable_text"


def test_document_upload_requires_authentication() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/documents/resume",
        files={"file": ("resume.txt", b"Skills\nPython", "text/plain")},
    )
    assert response.status_code == 401
