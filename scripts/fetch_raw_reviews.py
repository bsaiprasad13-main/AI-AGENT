"""Utility script to fetch live raw reviews from Google Play Store for Groww."""

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone
from src.ingestion.play_store import PlayStoreIngestionEngine
from src.utils.config_loader import get_product, load_settings


def main():
    parser = argparse.ArgumentParser(description="Fetch raw Play Store reviews for Groww.")
    parser.add_argument("--product", default="groww", help="Product key in products.yaml")
    parser.add_argument("--week", default=None, help="Target ISO Week e.g. 2026-W32 (default: current)")
    parser.add_argument("--force", action="store_true", help="Bypass cache and re-scrape")
    args = parser.parse_args()

    product = get_product(args.product)
    engine = PlayStoreIngestionEngine()

    print(f"Fetching reviews for {product.display_name} ({product.package_name})...")
    raw_reviews = engine.fetch_reviews(
        package_name=product.package_name,
        product_id=product.product_id,
        iso_week=args.week,
        force_refresh=args.force,
    )

    print(f"\n[OK] Fetched {len(raw_reviews)} raw reviews.")
    if raw_reviews:
        print("\n--- Sample Review (Raw) ---")
        sample = raw_reviews[0].model_dump(mode="json")
        print(json.dumps(sample, indent=2, default=str))

    print(f"\nSaved on disk at: data/cache/{product.product_id}_<week>_raw.json")


if __name__ == "__main__":
    main()
