"""Unit tests for Pydantic domain models."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from src.models.review import RawReview, SanitizedReview, ReviewBatch
from src.models.cluster import ClusterMetrics, ClusterInfo, ClusterTheme
from src.models.report import (
    WeeklyPulseReport,
    ThemeInsight,
    VerbatimQuote,
    ActionRecommendation,
    DocSectionAST,
    EmailPayload,
)


def test_raw_review_valid():
    review = RawReview(
        review_id="gp:test_123",
        user_name="Rahul Sharma",
        score=1,
        content="App keeps freezing on login page.",
        thumbs_up_count=5,
        review_created_version="14.2.0",
        at=datetime.now(timezone.utc),
    )
    assert review.review_id == "gp:test_123"
    assert review.score == 1
    assert review.thumbs_up_count == 5


def test_raw_review_score_validation():
    with pytest.raises(ValidationError):
        RawReview(
            review_id="gp:test_invalid",
            score=6,  # Out of range 1-5
            content="Invalid score review",
            at=datetime.now(timezone.utc),
        )


def test_sanitized_review():
    sanitized = SanitizedReview(
        review_id="gp:test_123",
        masked_user_name="User_A19B",
        score=2,
        original_content="Call me at 9876543210 for account issue.",
        sanitized_content="Call me at [REDACTED_PHONE] for account issue.",
        thumbs_up_count=3,
        at=datetime.now(timezone.utc),
        is_negative=True,
        token_count=8,
    )
    assert "[REDACTED_PHONE]" in sanitized.sanitized_content
    assert sanitized.is_negative is True


def test_cluster_metrics_and_theme():
    metrics = ClusterMetrics(
        cluster_id=0,
        review_count=45,
        average_score=1.8,
        total_thumbs_up=120,
        negative_count=38,
        impact_score=144.5,
    )
    assert metrics.cluster_id == 0
    assert metrics.impact_score > 100

    theme = ClusterTheme(
        cluster_id=0,
        theme_title="KYC Document Upload Failure",
        root_cause_summary="Aadhaar OTP timeouts causing verification loop during onboarding.",
        candidate_quotes=["OTP is never delivered during KYC."],
        product_action="Add alternative Digilocker verification path.",
    )
    assert theme.theme_title == "KYC Document Upload Failure"
    assert len(theme.candidate_quotes) == 1


def test_weekly_pulse_report_and_payloads():
    quote = VerbatimQuote(
        quote_text="Cannot sell options on expiry day, graph lag is terrible.",
        review_id="gp:quote_1",
        score=1,
        thumbs_up_count=12,
        verification_score=0.98,
        is_fallback=False,
    )

    theme = ThemeInsight(
        theme_id="theme_1",
        title="F&O Chart Lag and Order Execution Delays",
        root_cause="High socket latency during market opening spikes causes price tick lag.",
        impact_score=210.0,
        review_count=60,
        avg_score=1.4,
        severity_level="CRITICAL",
        verified_quotes=[quote],
        actions=ActionRecommendation(
            product_roadmap="Introduce dedicated high-frequency TradingView chart mode.",
            engineering_infra="Scale chart streaming web-sockets cluster.",
        ),
    )

    report = WeeklyPulseReport(
        product_id="groww",
        product_display_name="Groww",
        iso_week="2026-W32",
        start_date=datetime(2026, 8, 3),
        end_date=datetime(2026, 8, 9),
        total_reviews_analyzed=1250,
        average_rating=3.85,
        negative_review_percentage=28.5,
        themes=[theme],
    )

    assert report.product_id == "groww"
    assert len(report.themes) == 1
    assert report.themes[0].severity_level == "CRITICAL"
    assert report.themes[0].verified_quotes[0].is_fallback is False


def test_ast_and_email_payloads():
    ast = DocSectionAST(
        document_id="doc_12345",
        iso_week="2026-W32",
        section_heading="Week 2026-W32 — (Aug 03 to Aug 09)",
        anchor_id="h.groww_2026_w32",
        content="========================================\nWEEK 2026-W32\n========================================",
        raw_blocks=[{"insertText": "Summary"}],
    )
    assert ast.anchor_id == "h.groww_2026_w32"
    assert "WEEK 2026-W32" in ast.content

    email = EmailPayload(
        recipient_list=["product@groww.in"],
        subject="Groww Review Pulse — Week 2026-W32",
        body_html="<p>Executive preview...</p>",
        body_text="Executive preview...",
        deep_link_url="https://docs.google.com/document/d/doc_12345/edit#heading=h.groww_2026_w32",
        is_draft=True,
    )
    assert email.is_draft is True
    assert "h.groww_2026_w32" in email.deep_link_url
