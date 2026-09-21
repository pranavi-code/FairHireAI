from pathlib import Path


def test_live_e2e_is_guarded_and_uses_only_a_disposable_account() -> None:
    script = Path("scripts/live_product_e2e.py").read_text(encoding="utf-8")
    assert "--i-understand-live-writes" in script
    assert "if not args.i_understand_live_writes" in script
    assert "fairhireai-e2e-" in script
    assert "synthetic_test_account" in script
    assert "raw/FirstImpressionsV2/train" in script
    assert "processed/fi_v2_pilot10/video" not in script
    assert "Request disposable-account deletion" in script
    assert "_wait_for_account_deletion" in script
    assert "ROLEREADY_SUPABASE_SECRET_KEY" not in script


def test_live_e2e_covers_the_real_student_pipeline() -> None:
    script = Path("scripts/live_product_e2e.py").read_text(encoding="utf-8")
    required_routes = {
        "/privacy/consents",
        "/attempts",
        "/documents/resume",
        "/resume",
        "/next-question",
        "/answers",
        "/process",
        "/jobs",
        "/report",
        "/progress",
        "/privacy/deletion-requests",
    }
    for route in required_routes:
        assert route in script
    assert "roleready-documents" in script
    assert "roleready-interview-video" in script
    assert "Completed attempt has no evidence nodes" in script
    assert "Completed attempt has an invalid roadmap payload" in script
    assert "Confirm interview completion" in script
    assert 'f"{args.api_base_url.rstrip(\'/\')}/health"' in script
