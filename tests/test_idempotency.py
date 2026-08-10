"""Unit tests for SQLite idempotency and audit store."""

import tempfile
from pathlib import Path
import pytest
from src.agent.idempotency import IdempotencyStore, RunRecord


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_audit.db"
        yield str(db_path)


def test_idempotency_store_init(temp_db):
    store = IdempotencyStore(db_path=temp_db)
    assert Path(temp_db).exists()
    assert not store.has_published_for_week("groww", "2026-W32")


def test_record_and_get_run(temp_db):
    store = IdempotencyStore(db_path=temp_db)
    rec = RunRecord(
        run_id="run_12345",
        product_id="groww",
        iso_week="2026-W32",
        reviews_count=150,
        themes_count=4,
        avg_rating=3.2,
        doc_id="doc_abc",
        doc_status="appended",
        draft_id="draft_xyz",
        draft_status="created",
    )
    store.record_run(rec)

    fetched = store.get_run("run_12345")
    assert fetched is not None
    assert fetched.run_id == "run_12345"
    assert fetched.product_id == "groww"
    assert fetched.iso_week == "2026-W32"
    assert fetched.reviews_count == 150
    assert fetched.doc_status == "appended"
    assert fetched.draft_status == "created"

    assert store.has_published_for_week("groww", "2026-W32") is True
    assert store.has_published_for_week("groww", "2026-W33") is False


def test_list_history(temp_db):
    store = IdempotencyStore(db_path=temp_db)
    r1 = RunRecord(
        run_id="run_1",
        product_id="groww",
        iso_week="2026-W31",
        doc_status="appended",
        draft_status="created",
    )
    r2 = RunRecord(
        run_id="run_2",
        product_id="groww",
        iso_week="2026-W32",
        doc_status="appended",
        draft_status="created",
    )
    store.record_run(r1)
    store.record_run(r2)

    history = store.list_history("groww")
    assert len(history) == 2
    assert history[0].run_id in ("run_1", "run_2")
