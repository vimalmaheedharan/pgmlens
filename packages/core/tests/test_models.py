from datetime import datetime

import pytest
from factories import NOW, make_dataset, make_issue
from pgmlens_core import Dataset, Issue, Status
from pydantic import ValidationError


def test_naive_datetimes_are_treated_as_utc():
    issue = Issue(
        id="a", project_id="p1", key="A-1", title="t", status="todo",
        created_at=datetime(2026, 1, 1, 12, 0), updated_at=datetime(2026, 1, 2, 12, 0),
    )  # fmt: skip
    assert issue.created_at.tzinfo is not None
    assert issue.created_at.utcoffset().total_seconds() == 0


def test_done_issue_without_resolved_at_gets_one():
    issue = Issue(
        id="a", project_id="p1", key="A-1", title="t", status="done",
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 5),
    )  # fmt: skip
    assert issue.resolved_at == issue.updated_at


def test_updated_before_created_is_rejected():
    with pytest.raises(ValidationError, match="earlier than created_at"):
        Issue(
            id="a", project_id="p1", key="A-1", title="t", status="todo",
            created_at=datetime(2026, 1, 5), updated_at=datetime(2026, 1, 1),
        )  # fmt: skip


def test_unknown_project_is_rejected():
    with pytest.raises(ValidationError, match="unknown project_id"):
        make_dataset([make_issue("A-1", project="nope")])


def test_unknown_milestone_is_rejected():
    with pytest.raises(ValidationError, match="unknown milestone_id"):
        make_dataset([make_issue("A-1", milestone="nope")])


def test_duplicate_issue_ids_are_rejected():
    with pytest.raises(ValidationError, match="Duplicate issue ids"):
        make_dataset([make_issue("A-1"), make_issue("A-1")])


def test_dependency_on_unknown_issue_is_rejected():
    with pytest.raises(ValidationError, match="unknown issue"):
        make_dataset([make_issue("A-1")], [("A-1", "A-2")])


def test_self_dependency_is_rejected():
    with pytest.raises(ValidationError, match="cannot block itself"):
        make_dataset([make_issue("A-1")], [("A-1", "A-1")])


def test_typos_in_field_names_fail_loudly():
    with pytest.raises(ValidationError, match="Extra inputs"):
        Dataset.model_validate(
            {"program": {"id": "x", "name": "x"}, "as_of": NOW.isoformat(), "isues": []}
        )


def test_unsupported_schema_version_is_rejected():
    with pytest.raises(ValidationError, match="Unsupported schema_version"):
        Dataset.model_validate(
            {"schema_version": "99", "program": {"id": "x", "name": "x"}, "as_of": NOW.isoformat()}
        )


def test_status_helpers():
    assert make_issue("A-1", Status.DONE, resolved=2).is_open is False
    assert make_issue("A-2", Status.BLOCKED).is_open is True
