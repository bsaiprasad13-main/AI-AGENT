"""Clustering engine using Groq LLM (Map-Reduce strategy)."""

import json
import logging
import math
import os
import re
from typing import Dict, List, Tuple
from collections import defaultdict

from groq import Groq

from src.models.cluster import ClusterInfo, ClusterMetrics
from src.models.review import SanitizedReview
from src.utils.config_loader import ReasoningConfig, load_settings
from src.utils.token_manager import TokenManager

logger = logging.getLogger(__name__)


class ReviewClusterer:
    """Clusters sanitized reviews into semantic themes using Groq."""

    def __init__(self, config: ReasoningConfig = None):
        settings = load_settings()
        self.config = config or settings.reasoning
        self.client = None
        self.model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self._init_groq()

    def _init_groq(self):
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            try:
                self.client = Groq(api_key=api_key)
                logger.info(f"Initialized Groq client for clustering (Model: {self.model_name})")
            except Exception as e:
                logger.error(f"Failed to init Groq client: {e}")

    def cluster_reviews(
        self, reviews: List[SanitizedReview]
    ) -> Tuple[List[ClusterInfo], List[SanitizedReview]]:
        """Groups reviews into themes using Groq (Map-Reduce)."""
        if not reviews:
            return [], []

        if len(reviews) < 5 or not self.client:
            return [self._create_single_fallback_cluster(reviews, 0)], []

        # MAP: Chunk reviews and extract themes using TokenManager
        # We chunk all reviews into safe token batches
        # Max context tokens for Groq Llama 3 is 8192, we use 6000 as a safe batch buffer.
        batches = TokenManager.chunk_data(
            items=reviews,
            max_tokens=6000,
            text_extractor=lambda r: r.sanitized_content
        )
        
        all_themes = []
        for batch in batches:
            themes = self._extract_themes_from_batch(batch)
            all_themes.extend(themes)

        # REDUCE: Consolidate themes
        final_themes = self._consolidate_themes(all_themes)
        
        # ASSIGN: Map all reviews to the final themes heuristically or via LLM.
        # For cost/speed, we assign based on keyword heuristic derived from final themes.
        return self._assign_reviews_to_themes(reviews, final_themes)

    def _extract_themes_from_batch(self, batch: List[SanitizedReview]) -> List[str]:
        reviews_text = "\n".join([f"- {r.sanitized_content}" for r in batch])
        prompt = f"""Identify the top 3 major issues or themes from these product reviews.
Reviews:
{reviews_text}

Respond with a JSON array of strings, where each string is a concise theme label (e.g. "App Crash on Login", "High Brokerage Fees"). Return ONLY valid JSON."""
        
        try:
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_name,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            # Groq JSON mode requires an object, so we adjust prompt expectation
            # Let's fallback to regex if it didn't return an object with a list
            themes = re.findall(r'"([^"]+)"', content)
            return [t for t in themes if len(t) > 5 and len(t) < 50][:3]
        except Exception as e:
            logger.warning(f"Groq extract themes failed: {e}")
            return []

    def _consolidate_themes(self, themes: List[str]) -> List[str]:
        if not themes:
            return ["General Feedback"]
        themes_text = "\n".join([f"- {t}" for t in set(themes)])
        prompt = f"""Consolidate the following list of review themes into a final list of the top 5 distinct macro-themes.
Themes:
{themes_text}

Respond with a JSON object containing a "macro_themes" key with a list of 5 string labels. Return ONLY valid JSON."""
        try:
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_name,
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            return data.get("macro_themes", ["General Feedback", "App Performance", "Customer Support"])[:5]
        except Exception as e:
            logger.warning(f"Groq consolidate themes failed: {e}")
            return list(set(themes))[:5]

    def _assign_reviews_to_themes(
        self, reviews: List[SanitizedReview], themes: List[str]
    ) -> Tuple[List[ClusterInfo], List[SanitizedReview]]:
        
        clusters_map: Dict[str, List[SanitizedReview]] = defaultdict(list)
        outliers = []
        
        theme_keywords = {t: set(t.lower().split()) for t in themes}
        
        for r in reviews:
            content_lower = r.sanitized_content.lower()
            best_theme = None
            best_score = 0
            for theme, keywords in theme_keywords.items():
                score = sum(1 for k in keywords if k in content_lower)
                if score > best_score:
                    best_score = score
                    best_theme = theme
            
            if best_theme and best_score > 0:
                clusters_map[best_theme].append(r)
            else:
                outliers.append(r)
                
        # If all went to outliers, fallback
        if not clusters_map and reviews:
            clusters_map[themes[0]] = reviews
            outliers = []

        cluster_info_list = []
        c_id = 0
        for theme_name, member_reviews in clusters_map.items():
            if len(member_reviews) < 2:
                outliers.extend(member_reviews)
                continue
                
            info = self._build_cluster_info(c_id, member_reviews, theme_name)
            cluster_info_list.append(info)
            c_id += 1
            
        cluster_info_list.sort(key=lambda c: c.metrics.impact_score, reverse=True)
        return cluster_info_list, outliers

    def _build_cluster_info(
        self, cluster_id: int, member_reviews: List[SanitizedReview], theme_name: str
    ) -> ClusterInfo:
        review_count = len(member_reviews)
        avg_score = sum(r.score for r in member_reviews) / review_count
        total_thumbs_up = sum(r.thumbs_up_count for r in member_reviews)
        negative_count = sum(1 for r in member_reviews if r.is_negative)

        rating_penalty = max(0.1, 5.0 - avg_score)
        thumbs_factor = 1.0 + math.log10(1.0 + total_thumbs_up)
        impact_score = round(review_count * rating_penalty * thumbs_factor, 2)

        metrics = ClusterMetrics(
            cluster_id=cluster_id,
            review_count=review_count,
            average_score=round(avg_score, 2),
            total_thumbs_up=total_thumbs_up,
            negative_count=negative_count,
            impact_score=impact_score,
        )

        sorted_members = sorted(member_reviews, key=lambda r: (r.thumbs_up_count, -r.score), reverse=True)
        sample_limit = min(8, review_count)
        top_members = sorted_members[:sample_limit]

        return ClusterInfo(
            metrics=metrics,
            review_ids=[r.review_id for r in member_reviews],
            representative_review_ids=[r.review_id for r in top_members],
            representative_texts=[r.sanitized_content for r in top_members],
        )

    def _create_single_fallback_cluster(self, reviews: List[SanitizedReview], cluster_id: int) -> ClusterInfo:
        count = len(reviews)
        avg_score = sum(r.score for r in reviews) / count
        thumbs = sum(r.thumbs_up_count for r in reviews)
        neg_count = sum(1 for r in reviews if r.is_negative)
        impact = round(count * (5.0 - avg_score) * (1.0 + math.log10(1.0 + thumbs)), 2)

        metrics = ClusterMetrics(
            cluster_id=cluster_id,
            review_count=count,
            average_score=round(avg_score, 2),
            total_thumbs_up=thumbs,
            negative_count=neg_count,
            impact_score=impact,
        )

        return ClusterInfo(
            metrics=metrics,
            review_ids=[r.review_id for r in reviews],
            representative_review_ids=[r.review_id for r in reviews],
            representative_texts=[r.sanitized_content for r in reviews],
        )
