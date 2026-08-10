"""Review data models for ingestion and preprocessing."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class RawReview(BaseModel):
    """Raw review record ingested from app store scraper."""

    review_id: str = Field(..., description="Unique review identifier from Play Store")
    user_name: str = Field(default="Anonymous", description="Author display name")
    score: int = Field(..., ge=1, le=5, description="Star rating (1 to 5)")
    content: str = Field(..., description="Raw textual review content")
    thumbs_up_count: int = Field(default=0, ge=0, description="Helpful / upvote count")
    review_created_version: Optional[str] = Field(
        default=None, description="App version at time of review submission"
    )
    at: datetime = Field(..., description="Timestamp when review was created")
    reply_content: Optional[str] = Field(
        default=None, description="Developer reply text if available"
    )
    replied_at: Optional[datetime] = Field(
        default=None, description="Timestamp of developer reply"
    )


class SanitizedReview(BaseModel):
    """Review record after PII scrubbing, noise filtering, and sanitization."""

    review_id: str = Field(..., description="Unique review identifier")
    masked_user_name: str = Field(..., description="Anonymized username, e.g., User_A12B")
    score: int = Field(..., ge=1, le=5, description="Star rating (1 to 5)")
    original_content: str = Field(
        ..., description="Original raw content preserved for grounding verification"
    )
    sanitized_content: str = Field(
        ..., description="PII-redacted and injection-shielded review text"
    )
    thumbs_up_count: int = Field(default=0, ge=0, description="Upvote count")
    app_version: Optional[str] = Field(default=None, description="App version")
    at: datetime = Field(..., description="Timestamp")
    is_negative: bool = Field(
        default=False, description="True if score <= 2 (pain points focus)"
    )
    token_count: int = Field(default=0, ge=0, description="Approximate token/word count")


class ReviewBatch(BaseModel):
    """Container for a batch of reviews for an analysis window."""

    product_id: str = Field(..., description="Product identifier, e.g. groww")
    iso_week: str = Field(..., description="Target ISO Week identifier, e.g. 2026-W32")
    start_date: datetime = Field(..., description="Analysis window start date")
    end_date: datetime = Field(..., description="Analysis window end date")
    total_scraped: int = Field(default=0, ge=0)
    total_sanitized: int = Field(default=0, ge=0)
    reviews: List[SanitizedReview] = Field(default_factory=list)
    average_rating: float = Field(default=0.0, ge=0.0, le=5.0)
    negative_ratio: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Percentage of 1-2 star reviews"
    )
