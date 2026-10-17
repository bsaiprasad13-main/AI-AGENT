"""Unit tests for Review Synthesizer fallback behaviour (no network calls)."""

from src.models.cluster import ClusterInfo, ClusterMetrics
from src.reasoning.synthesizer import ReviewSynthesizer


def _cluster(cid: int, keywords, texts):
    return ClusterInfo(
        metrics=ClusterMetrics(cluster_id=cid, review_count=20, average_score=1.3, total_thumbs_up=45, negative_count=18, impact_score=122.4),
        review_ids=["r1", "r2"],
        representative_review_ids=["r1", "r2"],
        representative_texts=texts,
        keywords=keywords,
    )


def test_fallback_never_invents_findings(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    synthesizer = ReviewSynthesizer()
    texts = ["Chart lag in F&O options trading makes it unusable.", "Candlestick chart freeze during peak market hours."]
    theme = synthesizer.synthesize_clusters([_cluster(0, ["chart", "lag", "options"], texts)], product_id="groww")[0]

    assert theme.llm_generated is False
    assert theme.theme_title.startswith("Auto-labelled theme: chart, lag, options")
    # No made-up root causes or actions when the LLM is unavailable.
    assert theme.product_action is None and theme.support_action is None and theme.engineering_action is None
    # Quotes are real review text.
    assert theme.candidate_quotes == texts


def test_duplicate_titles_are_disambiguated(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    synthesizer = ReviewSynthesizer()
    a = _cluster(0, [], ["Support never replies to my ticket."])
    b = _cluster(1, ["refund", "delay"], ["Support ignored my refund request."])
    synthesizer._heuristic_fallback_synthesis = lambda c: type(synthesizer)._heuristic_fallback_synthesis(synthesizer, c).model_copy(update={"theme_title": "Support issues"})
    titles = [t.theme_title for t in synthesizer.synthesize_clusters([a, b], product_id="groww")]
    assert titles[0] == "Support issues" and titles[1] == "Support issues (refund, delay)"
