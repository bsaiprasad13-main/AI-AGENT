"""Unit tests for Quote Grounder and anti-hallucination verification."""

from datetime import datetime, timezone
from src.models.cluster import ClusterInfo, ClusterMetrics, ClusterTheme
from src.models.review import SanitizedReview
from src.reasoning.quote_grounder import QuoteGrounder


def _create_review(rid: str, text: str, score: int, thumbs: int = 0) -> SanitizedReview:
    return SanitizedReview(
        review_id=rid,
        masked_user_name="User_ABCD",
        score=score,
        original_content=text,
        sanitized_content=text,
        thumbs_up_count=thumbs,
        at=datetime.now(timezone.utc),
        is_negative=(score <= 2),
        token_count=len(text.split()),
    )


def test_quote_grounder_exact_and_fuzzy_match():
    grounder = QuoteGrounder()

    rev1 = _create_review("r1", "Aadhaar OTP is not delivered to mobile phone during KYC verification.", 1, 15)
    rev2 = _create_review("r2", "Stuck in document upload step for 3 days.", 2, 5)

    cluster = ClusterInfo(
        metrics=ClusterMetrics(
            cluster_id=0,
            review_count=2,
            average_score=1.5,
            total_thumbs_up=20,
            negative_count=2,
            impact_score=85.0,
        ),
        review_ids=["r1", "r2"],
        representative_review_ids=["r1", "r2"],
        representative_texts=[rev1.sanitized_content, rev2.sanitized_content],
    )

    # Theme with authentic quote
    theme = ClusterTheme(
        cluster_id=0,
        theme_title="KYC Aadhaar OTP Delays",
        root_cause_summary="SMS OTP gateway delays during user onboarding.",
        candidate_quotes=["Aadhaar OTP is not delivered to mobile phone during KYC verification."],
    )

    insight = grounder.ground_theme(theme, cluster, [rev1, rev2])
    assert len(insight.verified_quotes) >= 1
    assert insight.verified_quotes[0].review_id == "r1"
    assert insight.verified_quotes[0].is_fallback is False
    assert insight.verified_quotes[0].verification_score >= 0.95


def test_quote_grounder_hallucination_rejection_and_fallback():
    grounder = QuoteGrounder()

    rev1 = _create_review("r1", "Real authentic complaint about order execution failure.", 1, thumbs=25)
    rev2 = _create_review("r2", "Real second review with thumbs up.", 2, thumbs=10)

    cluster = ClusterInfo(
        metrics=ClusterMetrics(
            cluster_id=0,
            review_count=2,
            average_score=1.5,
            total_thumbs_up=35,
            negative_count=2,
            impact_score=90.0,
        ),
        review_ids=["r1", "r2"],
        representative_review_ids=["r1", "r2"],
        representative_texts=[rev1.sanitized_content, rev2.sanitized_content],
    )

    # Theme with a completely fake/hallucinated quote that does not exist in the corpus
    theme = ClusterTheme(
        cluster_id=0,
        theme_title="Crypto Staking Broken",
        root_cause_summary="Fake theme root cause.",
        candidate_quotes=["Completely fabricated quote: I lost 50 Bitcoins on Groww crypto wallet."],
    )

    insight = grounder.ground_theme(theme, cluster, [rev1, rev2])
    assert len(insight.verified_quotes) >= 1
    # Fabricated quote was rejected and replaced by highest thumbs-up real review (r1)
    assert insight.verified_quotes[0].review_id == "r1"
    assert insight.verified_quotes[0].is_fallback is True
    assert "Bitcoins" not in insight.verified_quotes[0].quote_text
