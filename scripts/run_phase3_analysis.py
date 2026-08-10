"""Pipeline script to execute Phase 3 (Reasoning Engine) on the normalized review dataset."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.report import WeeklyPulseReport
from src.models.review import SanitizedReview
from src.reasoning.clusterer import ReviewClusterer
from src.reasoning.embedder import SemanticEmbedder
from src.reasoning.quote_grounder import QuoteGrounder
from src.reasoning.synthesizer import ReviewSynthesizer
from src.utils.config_loader import get_project_root


def run_reasoning_pipeline():
    root = get_project_root()
    norm_file = root / "data" / "normalized_reviews.json"
    raw_cache_file = root / "data" / "cache" / "groww_2026_w32_raw.json"

    if not norm_file.exists():
        print("Error: data/normalized_reviews.json does not exist. Run scripts/save_review_datasets.py first.")
        return

    print("Loading normalized reviews...")
    with open(norm_file, "r", encoding="utf-8") as f:
        norm_data = json.load(f)

    # Convert to SanitizedReview objects
    sanitized_reviews = [
        SanitizedReview(
            review_id=f"rev_{i}",
            masked_user_name=f"User_{i:04X}",
            score=item["score"],
            original_content=item["content"],
            sanitized_content=item["content"],
            thumbs_up_count=item.get("thumbs_up_count", 0),
            is_negative=item.get("is_negative", item["score"] <= 2),
            at=datetime.now(timezone.utc),
            token_count=len(item["content"].split()),
        )
        for i, item in enumerate(norm_data)
    ]

    print(f"Loaded {len(sanitized_reviews)} normalized reviews.")

    # 1. Clustering
    print("\n[Step 1/3] Embedding and clustering reviews via UMAP/SVD + HDBSCAN...")
    embedder = SemanticEmbedder()
    clusterer = ReviewClusterer(embedder=embedder)
    clusters, outliers = clusterer.cluster_reviews(sanitized_reviews)
    print(f"-> Generated {len(clusters)} issue clusters (and {len(outliers)} outliers).")

    # 2. LLM / Heuristic Synthesis
    print("\n[Step 2/3] Synthesizing top themes and 3-column action items...")
    synthesizer = ReviewSynthesizer()
    themes = synthesizer.synthesize_clusters(clusters[:5], product_id="groww")

    # 3. Quote Grounding & Report Generation
    print("\n[Step 3/3] Verifying quote grounding (anti-hallucination check >= 95%)...")
    grounder = QuoteGrounder()
    theme_insights = []
    cluster_map = {c.metrics.cluster_id: c for c in clusters}

    for theme in themes:
        c_obj = cluster_map[theme.cluster_id]
        insight = grounder.ground_theme(theme, c_obj, sanitized_reviews)
        theme_insights.append(insight)

    # Calculate overall metrics
    total_reviews = len(sanitized_reviews)
    avg_score = round(sum(r.score for r in sanitized_reviews) / total_reviews, 2)
    neg_count = sum(1 for r in sanitized_reviews if r.is_negative)
    pos_count = sum(1 for r in sanitized_reviews if r.score >= 4)
    neu_count = total_reviews - neg_count - pos_count

    report = WeeklyPulseReport(
        product_id="groww",
        product_name="Groww (Stocks, Mutual Funds, UPI)",
        iso_week="2026-W32",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc),
        total_reviews_analyzed=total_reviews,
        average_score=avg_score,
        negative_ratio=round(neg_count / total_reviews, 3),
        positive_count=pos_count,
        neutral_count=neu_count,
        negative_count=neg_count,
        clusters=clusters[:5],
        themes=theme_insights,
    )

    # Save output report
    output_file = root / "data" / "weekly_pulse_report_groww.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

    print(f"\n[SUCCESS] Weekly Pulse Report generated and saved to: {output_file}")
    print("\n================ TOP SYNTHESIZED THEMES ================")
    for i, t in enumerate(theme_insights, 1):
        print(f"\nTheme {i} [{t.severity_level} | Impact: {t.impact_score}]: {t.title}")
        print(f"  Root Cause: {t.root_cause}")
        print(f"  Product Action: {t.actions.product_roadmap}")
        print(f"  Support Action: {t.actions.support_ops}")
        print(f"  Engineering Action: {t.actions.engineering_infra}")
        print(f"  Verified Quotes ({len(t.verified_quotes)}):")
        for q in t.verified_quotes:
            print(f'    - "{q.quote_text[:90]}..." (Rating: {q.score}/5, Match: {q.verification_score * 100:.0f}%)')


if __name__ == "__main__":
    run_reasoning_pipeline()
