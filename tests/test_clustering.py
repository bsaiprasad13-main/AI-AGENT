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


GROUPS = {
    "kyc": ["KYC verification fails because the Aadhaar OTP times out",
            "Cannot finish KYC onboarding since the OTP never arrives on my phone",
            "Aadhaar OTP is not coming so my account is still not activated",
            "Document upload for KYC verification has been stuck for days",
            "My PAN and Aadhaar verification keeps failing during KYC"],
    "charts": ["Charts lag terribly during the market open at 9:15",
               "Candlestick chart freezes and I lose money in options",
               "Option chain prices update very slowly while trading",
               "The chart keeps freezing when I place a stop loss order",
               "Live price ticks are delayed on the trading screen"],
    "withdraw": ["Withdrawal to my bank account is taking more than two days",
                 "Money was debited but my balance in the app is not updated",
                 "I am unable to withdraw my funds to my verified bank account",
                 "Withdrawal request is pending and support gives no answer about my money",
                 "Funds withdrawal keeps failing and the money is not credited to my bank"],
}


def _grouped_reviews():
    reviews, truth = [], {}
    prefixes = ["", "Honestly, ", "Since last week ", "Again today ", "Very annoying: "]
    n = 0
    for group, texts in GROUPS.items():
        for prefix in prefixes:
            for text in texts:
                n += 1
                rid = f"r{n}"
                reviews.append(_create_dummy_review(rid, prefix + text, 1 if group != "kyc" else 2, thumbs=n % 7))
                truth[rid] = group
    return reviews, truth


def test_umap_hdbscan_separates_distinct_issues():
    reviews, truth = _grouped_reviews()
    clusterer = ReviewClusterer()
    clusters, outliers = clusterer.cluster_reviews(reviews)

    assert len(clusters) >= 2
    # Each theme should be mostly one kind of issue (purity), not a mix.
    for c in clusters:
        groups = [truth[rid] for rid in c.review_ids]
        purity = max(groups.count(g) for g in set(groups)) / len(groups)
        assert purity >= 0.8, (c.keywords, purity)
    # Ranked by impact, highest first, with keywords and typical examples.
    scores = [c.metrics.impact_score for c in clusters]
    assert scores == sorted(scores, reverse=True)
    assert all(c.representative_texts and c.keywords for c in clusters)
    d = clusterer.last_diagnostics
    assert d.n_reviews == len(reviews) and d.n_clusters == len(clusters)


def test_small_input_falls_back_to_one_group():
    clusterer = ReviewClusterer()
    few = [_create_dummy_review(f"r{i}", f"Review number {i} about the app experience", 3) for i in range(5)]
    clusters, outliers = clusterer.cluster_reviews(few)
    assert len(clusters) == 1 and clusters[0].metrics.review_count == 5 and outliers == []


def test_clustering_single_review_fallback():
    clusterer = ReviewClusterer()
    single_review = [_create_dummy_review("r1", "Great interface and smooth SIP investment", 5, 0)]
    clusters, outliers = clusterer.cluster_reviews(single_review)
    assert len(clusters) == 1
    assert clusters[0].metrics.review_count == 1
    assert clusters[0].metrics.average_score == 5.0
