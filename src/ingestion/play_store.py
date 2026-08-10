"""Google Play Store scraper and ingestion engine for Groww."""

import logging
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Callable, List, Optional, Tuple

from google_play_scraper import Sort, reviews

from src.ingestion.cache import ReviewCache
from src.models.review import RawReview
from src.utils.config_loader import IngestionConfig, load_settings

logger = logging.getLogger(__name__)


def parse_iso_week(iso_week_str: str) -> Tuple[datetime, datetime]:
    """Parses an ISO week string (e.g., '2026-W32') into (start_datetime_utc, end_datetime_utc).
    
    Monday 00:00:00 UTC to Sunday 23:59:59.999999 UTC.
    """
    # Expected format: YYYY-Www or YYYY-Ww
    parts = iso_week_str.upper().split("-W")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid ISO week format '{iso_week_str}'. Expected format like '2026-W32'."
        )

    year = int(parts[0])
    week = int(parts[1])

    # Date of Monday in ISO week
    monday = date.fromisocalendar(year, week, 1)
    sunday = date.fromisocalendar(year, week, 7)

    start_dt = datetime.combine(monday, dtime.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(sunday, dtime.max, tzinfo=timezone.utc)
    return start_dt, end_dt


def calculate_rolling_window(
    target_end_date: datetime, rolling_weeks: int = 10
) -> datetime:
    """Calculates the start date for the rolling analysis window."""
    # Rolling N weeks back from target_end_date
    return target_end_date - timedelta(weeks=rolling_weeks)


class PlayStoreIngestionEngine:
    """Ingestion engine for fetching and normalizing Play Store reviews."""

    def __init__(
        self,
        config: Optional[IngestionConfig] = None,
        cache: Optional[ReviewCache] = None,
        scraper_fn: Optional[Callable] = None,
    ):
        settings = load_settings()
        self.config = config or settings.ingestion
        self.cache = cache or ReviewCache()
        self._scraper_fn = scraper_fn or reviews

    def fetch_reviews(
        self,
        package_name: str = "com.nextbillion.groww",
        product_id: str = "groww",
        iso_week: Optional[str] = None,
        use_cache: bool = True,
        force_refresh: bool = False,
    ) -> List[RawReview]:
        """Fetches reviews from Play Store for the designated product and rolling window.
        
        Args:
            package_name: Play store package ID (e.g., 'com.nextbillion.groww')
            product_id: Product identifier for cache keying ('groww')
            iso_week: Target ISO week (e.g., '2026-W32'). If None, defaults to current ISO week.
            use_cache: If True, returns cached reviews if present.
            force_refresh: If True, bypasses cache and re-scrapes.
            
        Returns:
            List of strongly-typed RawReview records.
        """
        if iso_week is None:
            now = datetime.now(timezone.utc)
            year, week, _ = now.isocalendar()
            iso_week = f"{year}-W{week:02d}"

        target_start_dt, target_end_dt = parse_iso_week(iso_week)
        window_start_dt = calculate_rolling_window(
            target_end_dt, self.config.default_rolling_window_weeks
        )

        logger.info(
            f"Ingesting reviews for '{product_id}' ({package_name}). Target Week: {iso_week} "
            f"({target_start_dt.date()} to {target_end_dt.date()}), "
            f"Rolling Window: {window_start_dt.date()} to {target_end_dt.date()}"
        )

        # Check disk cache first
        if use_cache and not force_refresh:
            cached_data = self.cache.load_raw_reviews(product_id, iso_week)
            if cached_data is not None and len(cached_data) > 0:
                logger.info(
                    f"Loaded {len(cached_data)} raw reviews from local cache for {iso_week}."
                )
                return cached_data

        scraped_raw: List[RawReview] = []
        continuation_token = None
        has_more = True
        total_fetched = 0

        while has_more and total_fetched < self.config.max_reviews_per_fetch:
            batch_result, continuation_token = self._fetch_batch_with_retry(
                package_name=package_name,
                continuation_token=continuation_token,
            )

            if not batch_result:
                break

            reached_older_bound = False
            for item in batch_result:
                created_at = item.get("at")
                if not created_at:
                    continue

                # Ensure timezone-aware datetime
                if isinstance(created_at, datetime):
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                else:
                    # Parse string if needed
                    try:
                        created_at = datetime.fromisoformat(str(created_at))
                        if created_at.tzinfo is None:
                            created_at = created_at.replace(tzinfo=timezone.utc)
                    except Exception:
                        created_at = datetime.now(timezone.utc)

                # If review is newer than target_end_dt, skip but keep paginating backwards
                if created_at > target_end_dt:
                    continue

                # If review is older than window_start_dt, we have reached the historical cutoff
                if created_at < window_start_dt:
                    reached_older_bound = True
                    break

                # Normalize to RawReview model
                raw_rec = RawReview(
                    review_id=str(item.get("reviewId") or f"gp:{total_fetched}_{time.time()}"),
                    user_name=str(item.get("userName") or "Anonymous"),
                    score=int(item.get("score") or 1),
                    content=str(item.get("content") or "").strip(),
                    thumbs_up_count=int(item.get("thumbsUpCount") or 0),
                    review_created_version=item.get("reviewCreatedVersion"),
                    at=created_at,
                    reply_content=item.get("replyContent"),
                    replied_at=item.get("repliedAt"),
                )
                scraped_raw.append(raw_rec)
                total_fetched += 1

            if reached_older_bound or continuation_token is None:
                has_more = False

        logger.info(
            f"Successfully scraped {len(scraped_raw)} normalized reviews within rolling window."
        )

        # Cache on disk
        if scraped_raw:
            self.cache.save_raw_reviews(product_id, iso_week, scraped_raw)

        return scraped_raw

    def _fetch_batch_with_retry(
        self,
        package_name: str,
        continuation_token: Optional[object] = None,
    ) -> Tuple[List[dict], Optional[object]]:
        """Executes a scraping batch with retry and exponential backoff."""
        retries = self.config.rate_limit_retries
        backoff = self.config.rate_limit_backoff_seconds

        for attempt in range(1, retries + 1):
            try:
                result, token = self._scraper_fn(
                    package_name,
                    lang=self.config.language,
                    country=self.config.country,
                    sort=Sort.NEWEST,
                    count=199,
                    continuation_token=continuation_token,
                )
                return result, token
            except Exception as e:
                logger.warning(
                    f"Play Store scrape attempt {attempt}/{retries} failed: {e}"
                )
                if attempt == retries:
                    logger.error(
                        f"All {retries} scrape attempts failed for '{package_name}'."
                    )
                    return [], None
                time.sleep(backoff * attempt)
        return [], None
