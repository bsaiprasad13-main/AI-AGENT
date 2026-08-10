"""Quote Grounding & Anti-Hallucination Engine."""

import logging
import re
from typing import Dict, List, Optional
from rapidfuzz import fuzz

from src.models.cluster import ClusterInfo, ClusterTheme
from src.models.report import (
    ActionRecommendation,
    ThemeInsight,
    VerbatimQuote,
)
from src.models.review import SanitizedReview
from src.utils.config_loader import QuoteGroundingConfig, load_settings

logger = logging.getLogger(__name__)


class QuoteGrounder:
    """Verifies that all published customer quotes are grounded in authentic review text."""

    def __init__(self, config: Optional[QuoteGroundingConfig] = None):
        settings = load_settings()
        self.config = config or settings.reasoning.quote_grounding

    def ground_theme(
        self,
        theme: ClusterTheme,
        cluster: ClusterInfo,
        all_reviews: List[SanitizedReview],
    ) -> ThemeInsight:
        """Grounds candidate quotes for a theme and constructs a verified ThemeInsight."""
        # Index reviews by review_id
        review_map: Dict[str, SanitizedReview] = {r.review_id: r for r in all_reviews}
        cluster_reviews: List[SanitizedReview] = [
            review_map[rid] for rid in cluster.review_ids if rid in review_map
        ]

        # If cluster_reviews is empty, fallback to representative reviews
        if not cluster_reviews and all_reviews:
            cluster_reviews = all_reviews[:10]

        verified_quotes: List[VerbatimQuote] = []

        # 1. Attempt to verify each candidate quote from LLM
        for cand_quote in theme.candidate_quotes:
            if len(verified_quotes) >= self.config.quotes_per_theme:
                break

            matched_quote = self._find_matching_grounding(cand_quote, cluster_reviews)
            if matched_quote:
                verified_quotes.append(matched_quote)
            else:
                logger.warning(
                    f"LLM Quote failed grounding verification (< {self.config.similarity_threshold * 100}%): '{cand_quote}'"
                )

        # 2. If insufficient quotes verified, apply deterministic fallback to top authentic reviews
        if len(verified_quotes) < self.config.quotes_per_theme and cluster_reviews:
            # Sort cluster reviews by thumbs_up_count descending, then rating ascending
            sorted_by_impact = sorted(
                cluster_reviews,
                key=lambda r: (r.thumbs_up_count, -r.score),
                reverse=True,
            )

            existing_rev_ids = {q.review_id for q in verified_quotes}
            for fallback_rev in sorted_by_impact:
                if len(verified_quotes) >= self.config.quotes_per_theme:
                    break
                if fallback_rev.review_id in existing_rev_ids:
                    continue

                fallback_quote = VerbatimQuote(
                    quote_text=fallback_rev.sanitized_content,
                    review_id=fallback_rev.review_id,
                    score=fallback_rev.score,
                    thumbs_up_count=fallback_rev.thumbs_up_count,
                    app_version=fallback_rev.app_version,
                    verification_score=1.0,
                    is_fallback=True,
                )
                verified_quotes.append(fallback_quote)
                existing_rev_ids.add(fallback_rev.review_id)

        # 3. Determine severity level from cluster metrics
        avg_score = cluster.metrics.average_score
        impact = cluster.metrics.impact_score

        if avg_score <= 1.5 or impact > 200:
            severity = "CRITICAL"
        elif avg_score <= 2.5 or impact > 100:
            severity = "HIGH"
        elif avg_score <= 3.5:
            severity = "MEDIUM"
        else:
            severity = "LOW"

        actions = ActionRecommendation(
            product_roadmap=theme.product_action,
            support_ops=theme.support_action,
            engineering_infra=theme.engineering_action,
        )

        return ThemeInsight(
            theme_id=f"theme_{cluster.metrics.cluster_id + 1}",
            title=theme.theme_title,
            root_cause=theme.root_cause_summary,
            impact_score=cluster.metrics.impact_score,
            review_count=cluster.metrics.review_count,
            avg_score=cluster.metrics.average_score,
            severity_level=severity,
            verified_quotes=verified_quotes,
            actions=actions,
        )

    def _find_matching_grounding(
        self, candidate: str, cluster_reviews: List[SanitizedReview]
    ) -> Optional[VerbatimQuote]:
        """Performs exact and fuzzy grounding verification against cluster reviews."""
        if not candidate or len(candidate.strip()) < 5:
            return None

        clean_cand = self._normalize_text(candidate)

        best_match: Optional[VerbatimQuote] = None
        highest_ratio = 0.0

        for rev in cluster_reviews:
            clean_rev = self._normalize_text(rev.sanitized_content)

            # 1. Exact substring check (100% match)
            if clean_cand in clean_rev or clean_rev in clean_cand:
                return VerbatimQuote(
                    quote_text=rev.sanitized_content,
                    review_id=rev.review_id,
                    score=rev.score,
                    thumbs_up_count=rev.thumbs_up_count,
                    app_version=rev.app_version,
                    verification_score=1.0,
                    is_fallback=False,
                )

            # 2. Fuzzy partial ratio check
            if self.config.use_fuzzy_fallback:
                ratio = fuzz.token_set_ratio(clean_cand, clean_rev) / 100.0
                if ratio > highest_ratio:
                    highest_ratio = ratio
                    if ratio >= self.config.similarity_threshold:
                        best_match = VerbatimQuote(
                            quote_text=rev.sanitized_content,
                            review_id=rev.review_id,
                            score=rev.score,
                            thumbs_up_count=rev.thumbs_up_count,
                            app_version=rev.app_version,
                            verification_score=round(ratio, 3),
                            is_fallback=False,
                        )

        return best_match

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalizes punctuation, curly quotes, and whitespace for robust string comparison."""
        t = text.lower()
        t = re.sub(r'[""\'`]', '"', t)
        t = re.sub(r"\s+", " ", t)
        return t.strip()
