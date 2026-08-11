from uuid import uuid4

from pydantic import ValidationError

from backend.app.domain.privacy import DeletionRequestCreate


def test_attempt_deletion_requires_attempt_id() -> None:
    try:
        DeletionRequestCreate(scope="attempt")
    except ValidationError as exc:
        assert "requires attempt_id" in str(exc)
    else:
        raise AssertionError("Attempt deletion without an attempt must fail")


def test_account_deletion_rejects_attempt_id() -> None:
    try:
        DeletionRequestCreate(scope="account", attempt_id=uuid4())
    except ValidationError as exc:
        assert "cannot contain attempt_id" in str(exc)
    else:
        raise AssertionError("Account deletion cannot be narrowed to one attempt")
