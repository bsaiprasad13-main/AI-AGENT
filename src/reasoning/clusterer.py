"""Theme discovery: sentence embeddings -> UMAP -> HDBSCAN.

Why this shape:
- Embeddings put reviews that *mean* the same thing close together, even when they
  share no words ("money stuck" vs "withdrawal pending").
- UMAP squeezes 384 dimensions down to 5. Density-based clustering works poorly in
  very high dimensions (every point looks equally far away); 5-D keeps the
  neighbourhood structure while making density meaningful.
- HDBSCAN does not need the number of themes in advance and labels reviews that fit
  no theme as noise, instead of forcing every one-off complaint into a theme.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS

from src.models.cluster import ClusterInfo, ClusterMetrics
from src.models.review import SanitizedReview
from src.reasoning.embedder import SemanticEmbedder
from src.utils.config_loader import ReasoningConfig, load_settings

logger = logging.getLogger(__name__)

# Words that appear in nearly every Groww review and say nothing about the theme.
DOMAIN_STOP_WORDS = {"app", "groww", "use", "using", "used", "good", "nice", "best", "bad", "worst", "please", "like", "just", "really", "very"}


@dataclass
class ClusteringDiagnostics:
    """Numbers that describe how well the clustering went (used by evals and logs)."""

    n_reviews: int = 0
    n_clusters: int = 0
    noise_count: int = 0
    noise_pct: float = 0.0
    silhouette: Optional[float] = None
    min_cluster_size_used: int = 0
    used_fallback_size: bool = False
    cluster_sizes: List[int] = field(default_factory=list)


class ReviewClusterer:
    """Groups sanitized reviews into themes using embeddings + UMAP + HDBSCAN."""

    def __init__(self, config: Optional[ReasoningConfig] = None, embedder: Optional[SemanticEmbedder] = None):
        self.config = config or load_settings().reasoning
        self.embedder = embedder or SemanticEmbedder(config=self.config.embedding)
        self.last_diagnostics = ClusteringDiagnostics()
        self.last_labels: Optional[np.ndarray] = None
        self.last_reduced: Optional[np.ndarray] = None

    # ------------------------------------------------------------------ public

    def cluster_reviews(
        self, reviews: List[SanitizedReview], random_state: Optional[int] = None
    ) -> Tuple[List[ClusterInfo], List[SanitizedReview]]:
        """Return (clusters sorted by impact, outlier reviews)."""
        if not reviews:
            return [], []
        # Too few reviews to find structure: report them as one group, honestly sized.
        if len(reviews) < 3 * self.config.fallback_hierarchy.min_cluster_size_fallback:
            self.last_diagnostics = ClusteringDiagnostics(n_reviews=len(reviews), n_clusters=1, cluster_sizes=[len(reviews)])
            return [self._build_cluster_info(0, reviews, None)], []

        texts = [r.sanitized_content for r in reviews]
        embeddings = self.embedder.embed_texts(texts)
        reduced = self._reduce(embeddings, random_state)
        labels, size_used, used_fallback = self._cluster(reduced)

        self.last_labels, self.last_reduced = labels, reduced
        clusters, outliers = self._build_clusters(reviews, embeddings, labels)
        self.last_diagnostics = self._diagnostics(reviews, labels, reduced, size_used, used_fallback)
        d = self.last_diagnostics
        logger.info(
            "Clustering: %d reviews -> %d themes, %.1f%% noise, silhouette=%s (min_cluster_size=%d)",
            d.n_reviews, d.n_clusters, d.noise_pct, d.silhouette, d.min_cluster_size_used,
        )
        return clusters, outliers

    # ---------------------------------------------------------------- pipeline

    def _reduce(self, embeddings: np.ndarray, random_state: Optional[int]) -> np.ndarray:
        import umap

        cfg = self.config.umap
        n_neighbors = min(cfg.n_neighbors, len(embeddings) - 1)
        reducer = umap.UMAP(
            n_neighbors=n_neighbors,
            n_components=cfg.n_components,
            min_dist=cfg.min_dist,
            metric=cfg.metric,
            random_state=cfg.random_state if random_state is None else random_state,
        )
        return reducer.fit_transform(embeddings)

    def _cluster(self, reduced: np.ndarray) -> Tuple[np.ndarray, int, bool]:
        """Run HDBSCAN; if it finds too few themes, retry once with a smaller minimum size."""
        import hdbscan

        cfg = self.config.hdbscan
        sizes = [cfg.min_cluster_size]
        if self.config.fallback_hierarchy.enabled:
            sizes.append(self.config.fallback_hierarchy.min_cluster_size_fallback)

        labels = np.full(len(reduced), -1)
        for i, size in enumerate(sizes):
            model = hdbscan.HDBSCAN(
                min_cluster_size=size,
                min_samples=min(cfg.min_samples, size),
                metric=cfg.metric,
                cluster_selection_method=cfg.cluster_selection_method,
            )
            labels = model.fit_predict(reduced)
            n_found = len(set(labels) - {-1})
            if n_found >= self.config.synthesis.min_themes:
                return labels, size, i > 0
        return labels, sizes[-1], len(sizes) > 1

    def _build_clusters(
        self, reviews: List[SanitizedReview], embeddings: np.ndarray, labels: np.ndarray
    ) -> Tuple[List[ClusterInfo], List[SanitizedReview]]:
        outliers = [r for r, lab in zip(reviews, labels) if lab == -1]
        cluster_ids = sorted(set(labels) - {-1})
        if not cluster_ids:
            return [self._build_cluster_info(0, reviews, None)], []

        keywords = self._cluster_keywords(reviews, labels, cluster_ids)
        infos = []
        for cid in cluster_ids:
            idx = np.where(labels == cid)[0]
            members = [reviews[i] for i in idx]
            # Representatives = reviews closest to the cluster's centre in meaning,
            # i.e. the most "typical" complaints, not the loudest ones.
            centroid = embeddings[idx].mean(axis=0)
            order = idx[np.argsort(-(embeddings[idx] @ centroid))]
            reps = [reviews[i] for i in order]
            infos.append(self._build_cluster_info(int(cid), members, reps, keywords.get(int(cid), [])))

        infos.sort(key=lambda c: c.metrics.impact_score, reverse=True)
        return infos, outliers

    def _cluster_keywords(
        self, reviews: List[SanitizedReview], labels: np.ndarray, cluster_ids: List[int], top_n: int = 6
    ) -> Dict[int, List[str]]:
        """Class-based TF-IDF: words frequent in one cluster but rare in the others."""
        docs = [" ".join(r.sanitized_content for r, lab in zip(reviews, labels) if lab == cid) for cid in cluster_ids]
        vectorizer = CountVectorizer(
            stop_words=list(ENGLISH_STOP_WORDS | DOMAIN_STOP_WORDS), ngram_range=(1, 2), min_df=1, token_pattern=r"(?u)\b[a-zA-Z&][a-zA-Z&]+\b"
        )
        counts = vectorizer.fit_transform(docs).toarray().astype(float)
        tf = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1)
        avg_words = counts.sum() / len(cluster_ids)
        idf = np.log(1 + avg_words / np.maximum(counts.sum(axis=0), 1))
        scores = tf * idf
        vocab = vectorizer.get_feature_names_out()
        return {cid: [vocab[j] for j in np.argsort(-scores[i])[:top_n]] for i, cid in enumerate(cluster_ids)}

    # ----------------------------------------------------------------- helpers

    def _build_cluster_info(
        self,
        cluster_id: int,
        members: List[SanitizedReview],
        representatives: Optional[List[SanitizedReview]],
        keywords: Optional[List[str]] = None,
    ) -> ClusterInfo:
        scoring = self.config.impact_scoring
        count = len(members)
        avg_score = sum(r.score for r in members) / count
        thumbs = sum(r.thumbs_up_count for r in members)
        # Impact = how many people x how unhappy they are x how many others agreed.
        rating_penalty = max(0.1, scoring.rating_invert_scale - avg_score)
        thumbs_factor = 1.0 + math.log(1.0 + thumbs, scoring.thumbs_up_log_base)
        impact = round(scoring.count_weight * count * rating_penalty * thumbs_factor, 2)

        reps = (representatives or members)[: self.config.synthesis.reviews_per_cluster_sample]
        return ClusterInfo(
            metrics=ClusterMetrics(
                cluster_id=cluster_id,
                review_count=count,
                average_score=round(avg_score, 2),
                total_thumbs_up=thumbs,
                negative_count=sum(1 for r in members if r.is_negative),
                impact_score=impact,
            ),
            review_ids=[r.review_id for r in members],
            representative_review_ids=[r.review_id for r in reps],
            representative_texts=[r.sanitized_content for r in reps],
            keywords=keywords or [],
        )

    def _diagnostics(
        self, reviews: List[SanitizedReview], labels: np.ndarray, reduced: np.ndarray, size_used: int, used_fallback: bool
    ) -> ClusteringDiagnostics:
        from sklearn.metrics import silhouette_score

        mask = labels != -1
        n_clusters = len(set(labels[mask]))
        silhouette = None
        if n_clusters >= 2 and mask.sum() > n_clusters:
            silhouette = round(float(silhouette_score(reduced[mask], labels[mask])), 3)
        noise = int((~mask).sum())
        return ClusteringDiagnostics(
            n_reviews=len(reviews),
            n_clusters=n_clusters,
            noise_count=noise,
            noise_pct=round(100 * noise / len(reviews), 1),
            silhouette=silhouette,
            min_cluster_size_used=size_used,
            used_fallback_size=used_fallback,
            cluster_sizes=sorted((int((labels == c).sum()) for c in set(labels[mask])), reverse=True),
        )
