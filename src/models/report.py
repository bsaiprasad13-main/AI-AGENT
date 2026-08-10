"""Report, insight, and delivery payload data models."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VerbatimQuote(BaseModel):
    """Verified, grounded customer quote directly sourced from authentic review text."""

    quote_text: str = Field(..., description="Verbatim customer quote")
    review_id: str = Field(..., description="Source review ID")
    score: int = Field(..., ge=1, le=5, description="Review star rating")
    thumbs_up_count: int = Field(default=0, ge=0)
    app_version: Optional[str] = Field(default=None)
    verification_score: float = Field(
        default=1.0, ge=0.0, le=1.0, description="String / fuzzy match confidence"
    )
    is_fallback: bool = Field(
        default=False, description="True if substituted after LLM hallucination rejection"
    )


class ActionRecommendation(BaseModel):
    """Actionable recommendations mapped across product, support, and engineering functions."""

    product_roadmap: Optional[str] = Field(
        default=None, description="Proposed feature, flow redesign, or UX enhancement"
    )
    support_ops: Optional[str] = Field(
        default=None, description="Support team SLA, macro update, or triage checklist"
    )
    engineering_infra: Optional[str] = Field(
        default=None, description="Technical fix, timeout adjustment, or crash resolution"
    )


class ThemeInsight(BaseModel):
    """Fully validated theme item for publication in Google Docs and Gmail."""

    theme_id: str = Field(..., description="Identifier e.g. theme_1")
    title: str = Field(..., description="Action-oriented theme headline")
    root_cause: str = Field(..., description="Root cause summary sentence")
    impact_score: float = Field(..., ge=0.0)
    review_count: int = Field(..., ge=0)
    avg_score: float = Field(..., ge=1.0, le=5.0)
    severity_level: str = Field(
        default="HIGH", description="CRITICAL | HIGH | MEDIUM | LOW"
    )
    verified_quotes: List[VerbatimQuote] = Field(default_factory=list)
    actions: ActionRecommendation = Field(default_factory=ActionRecommendation)


class WeeklyPulseReport(BaseModel):
    """Complete Weekly Pulse report structure ready for rendering."""

    product_id: str = Field(..., description="Target product, e.g., groww")
    product_display_name: str = Field(default="Groww")
    iso_week: str = Field(..., description="ISO Week, e.g. 2026-W32")
    start_date: datetime
    end_date: datetime
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    total_reviews_extracted: int = Field(default=0, ge=0)
    total_reviews_analyzed: int = Field(default=0, ge=0)
    average_rating: float = Field(default=0.0, ge=0.0, le=5.0)
    negative_review_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    delta_reviews: Optional[int] = Field(
        default=None, description="Delta from previous week"
    )
    delta_rating: Optional[float] = Field(
        default=None, description="Delta rating from previous week"
    )
    themes: List[ThemeInsight] = Field(default_factory=list)
    outlier_count: int = Field(default=0, ge=0)


class DocSectionAST(BaseModel):
    """Payload for Google Docs append operations and batchUpdate commands."""

    document_id: str
    iso_week: str
    section_heading: str
    anchor_id: str = Field(
        ..., description="Deterministic named range or heading ID e.g. h.groww_2026_w32"
    )
    content: str = Field(
        default="", description="Rendered structured text content ready for direct MCP Google Docs append"
    )
    raw_blocks: List[Dict[str, Any]] = Field(
        default_factory=list, description="Structured block commands for Docs batchUpdate if supported"
    )


class EmailPayload(BaseModel):
    """Executive teaser email payload for Gmail draft or send dispatch."""

    recipient_list: List[str] = Field(default_factory=list)
    subject: str
    body_html: str
    body_text: str
    deep_link_url: str = Field(
        ..., description="Direct anchor URL to the Google Doc section"
    )
    is_draft: bool = Field(default=True)
