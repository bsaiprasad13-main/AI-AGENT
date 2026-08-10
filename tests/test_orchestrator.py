"""Unit and integration tests for ReviewPulseOrchestrator."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.agent.idempotency import IdempotencyStore, RunRecord
from src.agent.mcp_client import MCPClient
from src.agent.orchestrator import ReviewPulseOrchestrator
from src.models.review import RawReview
from src.utils.config_loader import load_settings


@pytest.fixture
def sample_raw_reviews():
    now = datetime.now(timezone.utc)
    reviews = []
    # Mix of issues: KYC, F&O order execution, UPI payment failure, Positive
    issues = [
        ("KYC verification is stuck for 7 days despite uploading valid Aadhaar and PAN documents repeatedly.", 1),
        ("My Aadhaar OTP verification fails every single time during the onboarding flow.", 1),
        ("F&O order execution lagged during market volatility causing heavy slippage loss.", 1),
        ("Stop loss trigger failed to execute during extreme market swings.", 1),
        ("UPI auto-pay deduction happened but mutual fund SIP units were not credited.", 2),
        ("Money debited via UPI mandate but transaction showing pending for 48 hours.", 2),
        ("Groww is an excellent and smooth platform for investing in direct mutual funds.", 5),
        ("Super clean user interface and very easy to buy shares and equity.", 5),
    ]
    for i, (text, score) in enumerate(issues * 3):  # 24 reviews
        reviews.append(
            RawReview(
                review_id=f"test_rev_{i}",
                user_name=f"Customer_{i}",
                score=score,
                content=text,
                thumbs_up_count=i % 4,
                review_created_version="14.2.0",
                at=now,
                reply_content=None,
                replied_at=None,
            )
        )
    return reviews


@pytest.fixture
def orchestrator_fixture():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_audit.db")
        store = IdempotencyStore(db_path=db_path)
        settings = load_settings()
        settings.storage.audit_db_path = db_path

        mock_mcp = MagicMock(spec=MCPClient)
        mock_mcp.append_to_doc.return_value = {
            "status": "success",
            "message": "Content appended successfully",
            "doc_id": "test_doc_id",
        }
        mock_mcp.create_email_draft.return_value = {
            "status": "success",
            "message": "Draft created successfully",
            "draft_id": "draft_mock_123",
        }

        mock_google = MagicMock()
        mock_google.is_available = False

        orch = ReviewPulseOrchestrator(
            settings=settings,
            mcp_client=mock_mcp,
            google_client=mock_google,
            idempotency_store=store,
        )
        yield orch, mock_mcp, store


def test_orchestrator_dry_run(orchestrator_fixture, sample_raw_reviews):
    orch, mock_mcp, store = orchestrator_fixture

    result = orch.run(
        product_id="groww",
        dry_run=True,
        raw_reviews_override=sample_raw_reviews,
        iso_week_override="2026-W32",
    )

    assert result.status == "success"
    assert result.is_dry_run is True
    assert result.report is not None
    assert result.report.total_reviews_analyzed == len(sample_raw_reviews)
    assert len(result.report.themes) > 0
    assert result.doc_ast is not None
    assert result.email_payload is not None

    # Verify MCP tools were NOT called in dry run
    mock_mcp.append_to_doc.assert_not_called()
    mock_mcp.create_email_draft.assert_not_called()

    # Verify audit store record
    history = store.list_history("groww")
    assert len(history) == 1
    assert history[0].doc_status == "dry_run"
    assert history[0].draft_status == "dry_run"


def test_orchestrator_live_publish(orchestrator_fixture, sample_raw_reviews):
    orch, mock_mcp, store = orchestrator_fixture

    result = orch.run(
        product_id="groww",
        dry_run=False,
        raw_reviews_override=sample_raw_reviews,
        iso_week_override="2026-W32",
        custom_doc_id="custom_groww_doc_id",
    )

    assert result.status == "success"
    assert result.is_dry_run is False

    # Verify MCP client calls
    mock_mcp.append_to_doc.assert_called_once()
    call_args = mock_mcp.append_to_doc.call_args[1]
    assert call_args["doc_id"] == "custom_groww_doc_id"
    assert "Groww" in call_args["content"]

    mock_mcp.create_email_draft.assert_called_once()

    # Verify audit record marked as appended
    assert store.has_published_for_week("groww", "2026-W32") is True


def test_orchestrator_idempotency_guard(orchestrator_fixture, sample_raw_reviews):
    orch, mock_mcp, store = orchestrator_fixture

    # 1. Run live publish
    result1 = orch.run(
        product_id="groww",
        dry_run=False,
        raw_reviews_override=sample_raw_reviews,
        iso_week_override="2026-W32",
    )
    assert result1.status == "success"

    # 2. Re-run without force -> should skip
    result2 = orch.run(
        product_id="groww",
        dry_run=False,
        raw_reviews_override=sample_raw_reviews,
        iso_week_override="2026-W32",
        force=False,
    )
    assert result2.status == "skipped_idempotent"

    # 3. Re-run with force=True -> should proceed
    result3 = orch.run(
        product_id="groww",
        dry_run=False,
        raw_reviews_override=sample_raw_reviews,
        iso_week_override="2026-W32",
        force=True,
    )
    assert result3.status == "success"
