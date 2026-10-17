"""Grid-search UMAP/HDBSCAN settings on one week's cleaned reviews.

Selection rule (decided before looking at results):
  - largest theme holds < 40% of reviews (otherwise "themes" are just "everything")
  - noise (unassigned reviews) < 40%
  - between 5 and 25 themes (enough to be useful, few enough to read)
  then pick the highest silhouette score among the settings that pass.

Run:  python -m scripts.tune_clustering
"""

from __future__ import annotations

import itertools
import os
import pickle
import sys

import hdbscan
import numpy as np
import umap
from sklearn.metrics import silhouette_score

from src.preprocessing.sanitization import ReviewSanitizationPipeline
from src.reasoning.embedder import SemanticEmbedder
from src.utils.config_loader import load_settings


def evaluate(reduced: np.ndarray, labels: np.ndarray) -> dict:
    mask = labels != -1
    k = len(set(labels[mask]))
    sizes = sorted((int((labels == c).sum()) for c in set(labels[mask])), reverse=True)
    sil = float(silhouette_score(reduced[mask], labels[mask])) if k >= 2 else float("nan")
    return {
        "clusters": k,
        "noise_pct": round(100 * (~mask).mean(), 1),
        "largest_pct": round(100 * sizes[0] / len(labels), 1) if sizes else 100.0,
        "silhouette": round(sil, 3),
    }


def passes(m: dict) -> bool:
    return m["largest_pct"] < 40 and m["noise_pct"] < 40 and 5 <= m["clusters"] <= 25


def main(raw_path: str) -> None:
    os.environ.pop("GROQ_API_KEY", None)  # deterministic cleaning only
    settings = load_settings()
    raw = pickle.load(open(raw_path, "rb"))
    reviews = ReviewSanitizationPipeline(config=settings.preprocessing).process_batch(raw, "groww", "tune").reviews
    emb = SemanticEmbedder(config=settings.reasoning.embedding).embed_texts([r.sanitized_content for r in reviews])
    print(f"{len(reviews)} cleaned reviews")

    rows = []
    for min_dist, n_neighbors in itertools.product([0.0, 0.1], [10, 15, 30]):
        reduced = umap.UMAP(n_neighbors=n_neighbors, n_components=5, min_dist=min_dist, metric="cosine", random_state=42).fit_transform(emb)
        for method, mcs, ms in itertools.product(["eom", "leaf"], [8, 10, 15, 20], [3, 5]):
            labels = hdbscan.HDBSCAN(min_cluster_size=mcs, min_samples=ms, cluster_selection_method=method).fit_predict(reduced)
            m = evaluate(reduced, labels)
            rows.append({"min_dist": min_dist, "n_neighbors": n_neighbors, "method": method, "min_cluster_size": mcs, "min_samples": ms, **m, "pass": passes(m)})

    print(f"{'min_dist':>8} {'nn':>3} {'method':>6} {'mcs':>4} {'ms':>3} | {'k':>3} {'noise%':>7} {'largest%':>9} {'silh':>6} pass")
    for r in rows:
        print(f"{r['min_dist']:>8} {r['n_neighbors']:>3} {r['method']:>6} {r['min_cluster_size']:>4} {r['min_samples']:>3} | "
              f"{r['clusters']:>3} {r['noise_pct']:>7} {r['largest_pct']:>9} {r['silhouette']:>6} {'yes' if r['pass'] else ''}")
    ok = [r for r in rows if r["pass"]]
    if ok:
        best = max(ok, key=lambda r: r["silhouette"])
        print("\nSELECTED:", best)
    else:
        print("\nNo setting passed the rule.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1])
