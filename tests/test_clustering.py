"""Unit tests for Semantic Embedder and Review Clusterer."""

from datetime import datetime, timezone
import pytest
from src.models.review import SanitizedReview
from src.reasoning.clusterer import ReviewClusterer
from src.reasoning.embedder import SemanticEmbedder


def _create_dummy_review(rid: str, text: str, score: int, thumbs: int = 0) -> SanitizedReview:
    return SanitizedReview(
        review_id=rid,
        masked_user_name="User_1234",
        score=score,
        original_content=text,
        sanitized_content=text,
        thumbs_up_count=thumbs,
        at=datetime.now(timezone.utc),
        is_negative=(score <= 2),
        token_count=len(text.split()),
    )


def test_semantic_embedder():
    embedder = SemanticEmbedder()
    texts = [
        "KYC document verification is stuck on Aadhaar OTP.",
        "Chart lag in F&O options trading.",
        "Aadhaar OTP is not received on mobile number.",
    ]
    embeddings = embedder.embed_texts(texts)
    assert embeddings.shape[0] == 3
    assert embeddings.shape[1] > 0


def test_clustering_grouping_and_impact_ranking():
    clusterer = ReviewClusterer()

    reviews = [
        # Group 1: KYC / Aadhaar
        _create_dummy_review("r1", "KYC verification fails with Aadhaar OTP timeout", 1, thumbs=10),
        _create_dummy_review("r2", "Cannot complete KYC onboarding, OTP never arrives", 1, thumbs=8),
        _create_dummy_review("r3", "Aadhaar OTP is not coming for account activation", 1, thumbs=5),
        _create_dummy_review("r4", "Stuck in document upload verification step for 3 days", 2, thumbs=4),
        # Group 2: F&O Charts
        _create_dummy_review("r5", "TradingView charts lag terribly during 9:15 AM market open", 1, thumbs=25),
        _create_dummy_review("r6", "Candlestick chart freeze causes huge loss in options", 1, thumbs=30),
        _create_dummy_review("r7", "Option chain and live price tick latency is very high", 1, thumbs=15),
        _create_dummy_review("r8", "Chart is freezing when placing stop loss order", 2, thumbs=12),
        # Group 3: UPI / Withdrawals
        _create_dummy_review("r9", "UPI withdrawal to bank is taking more than 24 hours", 1, thumbs=2),
        _create_dummy_review("r10", "Money debited via UPI but wallet balance not updated", 1, thumbs=3),
        _create_dummy_review("r11", "Unable to withdraw funds to my verified bank account", 2, thumbs=1),
        _create_dummy_review("r12", "Bank mandate for SIP failed without reason", 2, thumbs=0),
    ]

    clusters, outliers = clusterer.cluster_reviews(reviews)
    assert len(clusters) >= 2
    
    # Verify impact scores are calculated and sorted descending
    for i in range(len(clusters) - 1):
        assert clusters[i].metrics.impact_score >= clusters[i + 1].metrics.impact_score

    # Check top cluster has representative exemplar reviews
    top_cluster = clusters[0]
    assert len(top_cluster.representative_texts) > 0
    assert top_cluster.metrics.review_count > 0


def test_clustering_single_review_fallback():
    clusterer = ReviewClusterer()
    single_review = [_create_dummy_review("r1", "Great interface and smooth SIP investment", 5, 0)]
    clusters, outliers = clusterer.cluster_reviews(single_review)
    assert len(clusters) == 1
    assert clusters[0].metrics.review_count == 1
    assert clusters[0].metrics.average_score == 5.0
