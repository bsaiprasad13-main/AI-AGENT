"""Unit tests for Executive Email Renderer."""

from datetime import datetime, timezone
import pytest

from src.models.report import (
    ActionRecommendation,
    EmailPayload,
    ThemeInsight,
    VerbatimQuote,
    WeeklyPulseReport,
)
from src.renderer.email_renderer import EmailRenderer


@pytest.fixture
def sample_pulse_report():
    theme1 = ThemeInsight(
        theme_id="theme_1",
        title="App Hang on Fast Order Execution",
        root_cause="Order execution latency during morning market opening.",
        impact_score=320.0,
        review_count=120,
        avg_score=1.4,
        severity_level="CRITICAL",
        verified_quotes=[
            VerbatimQuote(
                quote_text="App hanged while placing option buy order at 9:15 AM.",
                review_id="rev_202",
                score=1,
                thumbs_up_count=8,
                verification_score=1.0,
            )
        ],
        actions=ActionRecommendation(
            product_roadmap="Add one-click fast order mode with instant confirmation.",
            engineering_infra="Scale websocket order router nodes for 9:15 AM burst.",
        ),
    )

    return WeeklyPulseReport(
        product_id="groww",
        product_display_name="Groww",
        iso_week="2026-W32",
        start_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 8, 7, tzinfo=timezone.utc),
        generated_at=datetime(2026, 8, 8, 10, 0, 0, tzinfo=timezone.utc),
        total_reviews_analyzed=650,
        average_rating=3.42,
        negative_review_percentage=28.5,
        themes=[theme1],
        outlier_count=5,
    )


def test_deep_link_generation():
    renderer = EmailRenderer()
    url = renderer.get_deep_link_url("groww", "2026-W32", custom_doc_id="DOC_12345")
    assert url == "https://docs.google.com/document/d/DOC_12345/edit#heading=h.groww_2026_w32"


def test_render_email_payload(sample_pulse_report):
    renderer = EmailRenderer()
    email = renderer.render_email(
        sample_pulse_report,
        custom_recipients=["test-lead@groww.in"],
        is_draft=True,
    )

    assert isinstance(email, EmailPayload)
    assert email.recipient_list == ["test-lead@groww.in"]
    assert "[Groww Pulse] 2026-W32: 1 Key Customer Themes & Action Plan" in email.subject
    assert email.is_draft is True

    # HTML checks
    assert "650" in email.body_html
    assert "3.42★" in email.body_html
    assert "28.5%" in email.body_html
    assert "App Hang on Fast Order Execution" in email.body_html
    assert "CRITICAL" in email.body_html
    assert "Open Full Section in Google Docs" in email.body_html
    assert email.deep_link_url in email.body_html

    # Plain text checks
    assert "WEEKLY CUSTOMER INTELLIGENCE PULSE: GROWW" in email.body_text
    assert "Total Reviews Analyzed: 650" in email.body_text
    assert "App Hang on Fast Order Execution" in email.body_text
    assert email.deep_link_url in email.body_text
