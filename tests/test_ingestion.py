"""Unit tests for Play Store ingestion and disk caching."""

from datetime import datetime, timedelta, timezone
import json
import pytest
from src.ingestion.cache import ReviewCache
from src.ingestion.play_store import (
    PlayStoreIngestionEngine,
    calculate_rolling_window,
    parse_iso_week,
)
from src.models.review import RawReview


def test_parse_iso_week():
    start_dt, end_dt = parse_iso_week("2026-W32")
    # 2026-W32 Monday is Aug 3, 2026, Sunday is Aug 9, 2026
    assert start_dt.year == 2026
    assert start_dt.month == 8
    assert start_dt.day == 3
    assert start_dt.hour == 0
    assert end_dt.day == 9
    assert end_dt.hour == 23


def test_parse_iso_week_invalid():
    with pytest.raises(ValueError):
        parse_iso_week("invalid-week-string")


def test_calculate_rolling_window():
    end_dt = datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc)
    window_start = calculate_rolling_window(end_dt, rolling_weeks=10)
    delta_days = (end_dt - window_start).days
    assert delta_days == 70  # 10 weeks * 7 days


def test_review_cache(tmp_path):
    cache = ReviewCache(cache_dir=str(tmp_path))
    assert not cache.has_cache("groww", "2026-W32")

    sample_reviews = [
        RawReview(
            review_id="r1",
            user_name="User One",
            score=1,
            content="Bug in SIP payment",
            thumbs_up_count=2,
            at=datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
        ),
        RawReview(
            review_id="r2",
            user_name="User Two",
            score=5,
            content="Great UI experience",
            thumbs_up_count=0,
            at=datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc),
        ),
    ]

    saved_path = cache.save_raw_reviews("groww", "2026-W32", sample_reviews)
    assert saved_path.exists()
    assert cache.has_cache("groww", "2026-W32")

    loaded = cache.load_raw_reviews("groww", "2026-W32")
    assert loaded is not None
    assert len(loaded) == 2
    assert loaded[0].review_id == "r1"
    assert loaded[1].score == 5

    # Test simplified actual and normalized review file exports
    actual_file = cache.save_actual_reviews_simple(sample_reviews, filename="test_actual.json")
    assert actual_file.exists()

    with open(actual_file, "r", encoding="utf-8") as f:
        actual_json = json.load(f)
    assert len(actual_json) == 2
    assert "review_id" not in actual_json[0]
    assert "user_name" not in actual_json[0]
    assert actual_json[0]["score"] == 1
    assert actual_json[0]["content"] == "Bug in SIP payment"
    assert actual_json[0]["thumbs_up_count"] == 2


def test_ingestion_mocked_scraper(tmp_path):
    mock_reviews_data = [
        {
            "reviewId": "gp:mock_1",
            "userName": "Amit Kumar",
            "score": 1,
            "content": "Order execution is very slow during market open.",
            "thumbsUpCount": 15,
            "reviewCreatedVersion": "14.5.1",
            "at": datetime(2026, 8, 6, 10, 30, tzinfo=timezone.utc),
            "replyContent": None,
            "repliedAt": None,
        },
        {
            "reviewId": "gp:mock_2",
            "userName": "Pooja Verma",
            "score": 2,
            "content": "Unable to withdraw funds to HDFC bank account.",
            "thumbsUpCount": 4,
            "reviewCreatedVersion": "14.5.0",
            "at": datetime(2026, 8, 4, 9, 15, tzinfo=timezone.utc),
            "replyContent": None,
            "repliedAt": None,
        },
    ]

    def mock_scraper_fn(*args, **kwargs):
        return mock_reviews_data, None

    cache = ReviewCache(cache_dir=str(tmp_path))
    engine = PlayStoreIngestionEngine(cache=cache, scraper_fn=mock_scraper_fn)

    results = engine.fetch_reviews(
        package_name="com.nextbillion.groww",
        product_id="groww",
        iso_week="2026-W32",
        use_cache=False,
    )

    assert len(results) == 2
    assert results[0].review_id == "gp:mock_1"
    assert results[0].score == 1
    assert results[1].score == 2
    assert cache.has_cache("groww", "2026-W32")
