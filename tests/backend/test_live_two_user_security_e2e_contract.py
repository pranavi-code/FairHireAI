from pathlib import Path


def test_two_user_live_e2e_is_project_locked_and_cleanup_verified() -> None:
    script = Path("scripts/live_two_user_security_e2e.py").read_text(encoding="utf-8")

    assert 'PROJECT_REF = "gfsetwljirztyxegiets"' in script
    assert "--i-understand-live-writes" in script
    assert "if not args.i_understand_live_writes" in script
    assert "_assert_project_url" in script
    assert "fairhireai-e2e-" in script
    assert "synthetic_test_account" in script
    assert "_cleanup_exact_resources" in script
    assert "_storage_object_is_missing" in script
    assert '"not found" in body' in script
    assert 'result["cleanup_verified"] = True' in script
    assert "ROLEREADY_SUPABASE_SECRET_KEY" not in script
    assert 'f"{args.api_base_url.rstrip(\'/\')}/health"' in script


def test_two_user_live_e2e_covers_security_and_report_boundaries() -> None:
    script = Path("scripts/live_two_user_security_e2e.py").read_text(encoding="utf-8")

    for evidence in (
        "User A direct trusted-attempt update",
        "User A direct trusted-attempt delete",
        "User B cross-read attempt",
        "User B cross-update attempt",
        "User B cross-delete attempt",
        "User B cross-download",
        "User B cross-delete storage",
        "Resume extraction without consent",
        "Answer submission without recording consent",
        "Processing without external-AI consent",
        "Authenticated report enqueue",
        "Idempotent report request",
        "User B cross-user report enqueue",
        "Request account deletion",
    ):
        assert evidence in script
    assert "while question_count < 6" in script
    assert '"/progress"' in script
    assert '"roadmap_items"' in script
    assert '"owner_trusted_table_write_blocked": True' in script
