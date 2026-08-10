"""Disk cache manager for ingested raw and processed reviews."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from src.models.review import RawReview
from src.utils.config_loader import get_project_root


class ReviewCache:
    """Manages persistent JSON caching of raw reviews to minimize external network requests."""

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = get_project_root() / "data" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, product_id: str, iso_week: str) -> Path:
        """Returns the file path for a specific product and ISO week cache."""
        sanitized_week = iso_week.replace("-", "_").lower()
        return self.cache_dir / f"{product_id}_{sanitized_week}_raw.json"

    def save_raw_reviews(
        self, product_id: str, iso_week: str, reviews: List[RawReview]
    ) -> Path:
        """Persists a list of RawReview objects to disk with deduplication."""
        cache_path = self._get_cache_path(product_id, iso_week)
        
        # Load existing if available to merge
        existing_reviews: Dict[str, dict] = {}
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("reviews", []):
                        existing_reviews[item["review_id"]] = item
            except Exception:
                existing_reviews = {}

        # Merge and overwrite newer
        for review in reviews:
            rev_dict = review.model_dump(mode="json")
            existing_reviews[review.review_id] = rev_dict

        payload = {
            "product_id": product_id,
            "iso_week": iso_week,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "count": len(existing_reviews),
            "reviews": list(existing_reviews.values()),
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        return cache_path

    def load_raw_reviews(
        self, product_id: str, iso_week: str
    ) -> Optional[List[RawReview]]:
        """Loads cached raw reviews if the cache file exists."""
        cache_path = self._get_cache_path(product_id, iso_week)
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            reviews_raw = data.get("reviews", [])
            return [RawReview.model_validate(r) for r in reviews_raw]
        except Exception:
            return None

    def has_cache(self, product_id: str, iso_week: str) -> bool:
        """Checks if a cache file exists and has content."""
        cache_path = self._get_cache_path(product_id, iso_week)
        return cache_path.exists() and cache_path.stat().st_size > 10

    def save_actual_reviews_simple(self, reviews: List[RawReview], filename: str = "actual_reviews.json") -> Path:
        """Saves actual reviews with simplified fields (score, content, thumbs_up_count)."""
        data_dir = get_project_root() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        out_path = data_dir / filename

        simplified = [
            {
                "score": r.score,
                "content": r.content,
                "thumbs_up_count": r.thumbs_up_count,
            }
            for r in reviews
        ]

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(simplified, f, indent=2, ensure_ascii=False)

        return out_path

    def save_normalized_reviews_simple(self, reviews: list, filename: str = "normalized_reviews.json") -> Path:
        """Saves normalized reviews with simplified fields (score, content, thumbs_up_count, is_negative)."""
        data_dir = get_project_root() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        out_path = data_dir / filename

        simplified = [
            {
                "score": r.score,
                "content": r.sanitized_content,
                "thumbs_up_count": r.thumbs_up_count,
                "is_negative": r.is_negative,
            }
            for r in reviews
        ]

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(simplified, f, indent=2, ensure_ascii=False)

        return out_path
