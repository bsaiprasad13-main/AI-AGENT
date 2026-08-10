"""Script to generate and persist actual and normalized review datasets with simplified schemas."""

import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.review import RawReview
from src.preprocessing.sanitization import ReviewSanitizationPipeline
from src.utils.config_loader import get_project_root


def generate_datasets():
    root = get_project_root()
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_file = data_dir / "cache" / "groww_2026_w32_raw.json"

    if not cache_file.exists():
        print(f"Error: Cache file {cache_file} does not exist. Run fetch_raw_reviews.py first.")
        return

    with open(cache_file, "r", encoding="utf-8") as f:
        raw_cache = json.load(f)

    raw_items = raw_cache.get("reviews", [])
    raw_models = [RawReview.model_validate(r) for r in raw_items]

    # 1. Actual reviews with simplified schema (score, content, thumbs_up_count)
    actual_reviews = [
        {
            "score": r.score,
            "content": r.content,
            "thumbs_up_count": r.thumbs_up_count,
        }
        for r in raw_models
    ]

    actual_file = data_dir / "actual_reviews.json"
    with open(actual_file, "w", encoding="utf-8") as f:
        json.dump(actual_reviews, f, indent=2, ensure_ascii=False)

    print(f"[OK] Saved {len(actual_reviews)} actual reviews -> {actual_file}")

    # 2. Normalized reviews (filtered for >= 8 words, 0 emojis, English only, PII redacted)
    pipeline = ReviewSanitizationPipeline()
    batch = pipeline.process_batch(raw_models, product_id="groww", iso_week="2026-W32")

    normalized_reviews = [
        {
            "score": r.score,
            "content": r.sanitized_content,
            "thumbs_up_count": r.thumbs_up_count,
            "is_negative": r.is_negative,
        }
        for r in batch.reviews
    ]

    normalized_file = data_dir / "normalized_reviews.json"
    with open(normalized_file, "w", encoding="utf-8") as f:
        json.dump(normalized_reviews, f, indent=2, ensure_ascii=False)

    print(f"[OK] Saved {len(normalized_reviews)} normalized reviews -> {normalized_file}")


if __name__ == "__main__":
    generate_datasets()
