"""Clustering and vector space data models."""

from typing import List, Optional
from pydantic import BaseModel, Field


class ClusterMetrics(BaseModel):
    """Statistical summary metrics for an individual review cluster."""

    cluster_id: int = Field(..., description="HDBSCAN cluster ID (-1 is noise)")
    review_count: int = Field(..., ge=0, description="Total reviews in this cluster")
    average_score: float = Field(
        ..., ge=1.0, le=5.0, description="Mean star rating in cluster"
    )
    total_thumbs_up: int = Field(
        default=0, ge=0, description="Sum of thumbs-up in cluster"
    )
    negative_count: int = Field(
        default=0, ge=0, description="Count of 1-2 star reviews"
    )
    impact_score: float = Field(
        default=0.0, ge=0.0, description="Calculated impact ranking score"
    )


class ClusterInfo(BaseModel):
    """Detailed cluster representation with member reviews and representative exemplars."""

    metrics: ClusterMetrics
    review_ids: List[str] = Field(
        default_factory=list, description="IDs of reviews belonging to this cluster"
    )
    representative_review_ids: List[str] = Field(
        default_factory=list,
        description="Top reviews closest to centroid for LLM prompt context",
    )
    representative_texts: List[str] = Field(
        default_factory=list,
        description="Cleaned text snippets passed into synthesis prompt",
    )


class ClusterTheme(BaseModel):
    """Preliminary theme structure extracted by the LLM before quote verification."""

    cluster_id: int
    theme_title: str = Field(..., description="Crisp, actionable 1-line theme headline")
    root_cause_summary: str = Field(
        ..., description="1-sentence explanation of what is breaking or missing"
    )
    candidate_quotes: List[str] = Field(
        default_factory=list,
        description="Proposed verbatim customer quotes from LLM",
    )
    product_action: Optional[str] = Field(
        default=None, description="Concrete product feature or UX improvement"
    )
    support_action: Optional[str] = Field(
        default=None, description="Support team triage rule, FAQ, or ticket SLA action"
    )
    engineering_action: Optional[str] = Field(
        default=None, description="Infra, latency, crash fix, or backend reliability fix"
    )
