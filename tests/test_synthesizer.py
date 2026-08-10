"""Unit tests for Review Synthesizer and theme generation."""

from src.models.cluster import ClusterInfo, ClusterMetrics
from src.reasoning.synthesizer import ReviewSynthesizer


def test_heuristic_synthesizer():
    synthesizer = ReviewSynthesizer()

    # Cluster with chart lag reviews
    metrics = ClusterMetrics(
        cluster_id=0,
        review_count=20,
        average_score=1.3,
        total_thumbs_up=45,
        negative_count=18,
        impact_score=122.4,
    )
    cluster = ClusterInfo(
        metrics=metrics,
        review_ids=["r1", "r2"],
        representative_review_ids=["r1", "r2"],
        representative_texts=[
            "Chart lag in F&O options trading makes it unusable.",
            "Candlestick chart freeze during peak market hours.",
        ],
    )

    themes = synthesizer.synthesize_clusters([cluster], product_id="groww")
    assert len(themes) == 1
    theme = themes[0]
    assert "Chart" in theme.theme_title or "F&O" in theme.theme_title
    assert theme.product_action is not None
    assert theme.support_action is not None
    assert theme.engineering_action is not None
    assert len(theme.candidate_quotes) >= 1
