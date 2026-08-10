"""Unit tests for Google Docs AST & Markdown Renderer."""

from datetime import datetime, timezone
import pytest

from src.models.report import (
    ActionRecommendation,
    DocSectionAST,
    ThemeInsight,
    VerbatimQuote,
    WeeklyPulseReport,
)
from src.renderer.doc_renderer import DocRenderer


@pytest.fixture
def sample_pulse_report():
    theme1 = ThemeInsight(
        theme_id="theme_1",
        title="KYC Verification Latency",
        root_cause="SMS OTP timeout during onboarding.",
        impact_score=150.5,
        review_count=85,
        avg_score=1.8,
        severity_level="CRITICAL",
        verified_quotes=[
            VerbatimQuote(
                quote_text="OTP never arrived on my Airtel number during KYC.",
                review_id="rev_101",
                score=1,
                thumbs_up_count=12,
                verification_score=1.0,
                is_fallback=False,
            )
        ],
        actions=ActionRecommendation(
            product_roadmap="Introduce alternate Digilocker flow.",
            support_ops="Create priority queue for KYC tickets.",
            engineering_infra="Add secondary SMS gateway vendor.",
        ),
    )

    theme2 = ThemeInsight(
        theme_id="theme_2",
        title="Smooth Mutual Fund SIP Experience",
        root_cause="Users appreciate one-click SIP setup.",
        impact_score=5.0,
        review_count=30,
        avg_score=4.9,
        severity_level="LOW",
        verified_quotes=[],
        actions=ActionRecommendation(
            product_roadmap="Promote auto-pay feature.",
        ),
    )

    return WeeklyPulseReport(
        product_id="groww",
        product_display_name="Groww",
        iso_week="2026-W32",
        start_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 8, 7, tzinfo=timezone.utc),
        generated_at=datetime(2026, 8, 8, 10, 0, 0, tzinfo=timezone.utc),
        total_reviews_analyzed=500,
        average_rating=3.85,
        negative_review_percentage=22.4,
        themes=[theme1, theme2],
        outlier_count=15,
    )


def test_anchor_id_generation():
    renderer = DocRenderer()
    anchor = renderer.get_anchor_id("groww", "2026-W32")
    assert anchor == "h.groww_2026_w32"


def test_render_to_ast(sample_pulse_report):
    renderer = DocRenderer()
    ast = renderer.render_to_ast(sample_pulse_report)

    assert isinstance(ast, DocSectionAST)
    assert ast.iso_week == "2026-W32"
    assert ast.anchor_id == "h.groww_2026_w32"
    assert "Week 2026-W32" in ast.section_heading
    assert len(ast.raw_blocks) >= 3

    # Direct append content verification
    assert ast.content is not None
    assert "WEEK 2026-W32" in ast.content
    assert "EXECUTIVE KPI SNAPSHOT" in ast.content
    assert "KYC VERIFICATION LATENCY" in ast.content.upper()

    # Heading block
    h_block = ast.raw_blocks[0]
    assert h_block["type"] == "heading_1"
    assert h_block["anchor_id"] == "h.groww_2026_w32"

    # KPI summary block
    kpi_block = ast.raw_blocks[1]
    assert kpi_block["type"] == "kpi_summary"
    assert kpi_block["metrics"]["total_reviews"] == 500
    assert kpi_block["metrics"]["average_rating"] == 3.85
    assert kpi_block["metrics"]["negative_percentage"] == 22.4

    # Theme block
    t_block = ast.raw_blocks[2]
    assert t_block["type"] == "theme_section"
    assert t_block["title"] == "KYC Verification Latency"
    assert t_block["severity"] == "CRITICAL"
    assert len(t_block["quotes"]) == 1
    assert t_block["quotes"][0]["stars"] == "★☆☆☆☆"


def test_render_for_doc_append(sample_pulse_report):
    renderer = DocRenderer()
    text_content = renderer.render_for_doc_append(sample_pulse_report)
    plain_text = renderer.render_to_plain_text(sample_pulse_report)

    assert text_content == plain_text
    assert "WEEK 2026-W32" in text_content
    assert "Groww (groww)" in text_content
    assert "#h.groww_2026_w32" in text_content
    assert "Total Reviews Analyzed: 500" in text_content
    assert "Average Star Rating: 3.85 / 5.0" in text_content
    assert "KYC VERIFICATION LATENCY [CRITICAL]" in text_content
    assert "OTP never arrived on my Airtel number during KYC." in text_content
    assert "Introduce alternate Digilocker flow." in text_content
    assert "<a id=" not in text_content  # Ensure no raw HTML anchor tags


def test_render_to_markdown(sample_pulse_report):
    renderer = DocRenderer()
    md = renderer.render_to_markdown(sample_pulse_report)

    assert "# Week 2026-W32" in md
    assert "h.groww_2026_w32" in md
    assert "Executive KPI Snapshot" in md
    assert "KYC Verification Latency" in md
    assert "CRITICAL" in md
    assert "OTP never arrived on my Airtel number during KYC." in md
    assert "Cross-Functional Action Plan" in md
    assert "Introduce alternate Digilocker flow." in md
