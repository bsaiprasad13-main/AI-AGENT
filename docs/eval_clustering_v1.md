# Clustering evaluation — v1 (before Groq pacing fix and title-prompt change)

Data: 5174 Google Play reviews for Groww, 2026-09-09 to 2026-10-16 · run 2026-10-17
Run: `python -m scripts.evaluate_clustering <raw.pkl>`

## 1. Funnel

| Stage | Reviews | Avg rating |
|---|---|---|
| Scraped (all in window) | 5174 | 4.40 |
| After cleaning (English, 8+ words, PII masked, spam removed) | 700 | 3.04 |
| Assigned to a theme | 460 | |
| Noise (fits no theme) | 240 (34.3%) | |

Groq spam filter: {'batches': 6, 'failed_batches': 4, 'removed_as_spam': 9}

The cleaned set is far more negative than the whole (3.04 vs 4.40) because most short reviews are 5-star praise.
That is why headline ratings in the report are computed on all reviews, and themes on the cleaned set.

## 2. Cluster quality (UMAP 5-D + HDBSCAN leaf, min_cluster_size 10)

| Metric | Value |
|---|---|
| Themes found | 19 |
| Noise | 34.3% |
| Largest theme | 7.1% of reviews |
| Silhouette (excl. noise) | 0.552 |
| Theme sizes | 50, 42, 39, 37, 35, 30, 27, 22, 22, 20, 19, 17, 17, 16, 15, 15, 14, 13, 10 |
| Runtime | 64s |

## 3. Stability across random seeds (42, 7, 123)

Adjusted Rand Index between runs: 0.60, 0.60, 0.63 (mean **0.61**; 1.0 = identical, 0 = no better than random)

## 4. Ablations

| Variant | Themes | Noise % | Largest theme % |
|---|---|---|---|
| **Chosen:** UMAP + HDBSCAN (leaf) | 19 | 34.3 | 7.1 |
| No UMAP (HDBSCAN on raw 384-d) | 0 | 100.0 | 100.0 |
| UMAP + HDBSCAN default (eom) | 3 | 0.0 | 92.9 |

## 5. Top themes and theme accuracy (judge: openai/gpt-oss-120b, writer: Gemini)

| # | Theme (LLM title) | Reviews | Avg ★ | Impact | Distinctive words | Members matching title | Other-theme reviews matching |
|---|---|---|---|---|---|---|---|
| 1 | Unresponsive customer support and ineffective automated chat responses | 37 | 1.46 | 479.7 | customer, service, support, customer service | 9/10 | 0/5 |
| 2 | App failing to open and throwing network errors after recent updates | 30 | 2.1 | 207.08 | working, pan, explore, details | 4/10 | 0/5 |
| 3 | High brokerage charges impacting small investors and intraday trades | 39 | 3.15 | 164.07 | brokerage, charges, rs, broker | 6/10 | 0/5 |
| 4 | Failures in family account linking, account switching, and minor account setup | 22 | 2.14 | 160.28 | account, family, switch, minor | 5/10 | 0/5 |
| 5 | Unresponsive customer support and critical delays in withdrawals and order execution | 17 | 1.47 | 151.89 | loss, account, support, customer | 8/10 | 0/5 |

**Theme precision:** 32/50 (64%) of sampled member reviews match their theme title.
**False-match rate:** 0/25 (0%) of reviews from other themes match the title.
Titles written by the LLM: 5/5 (the rest were auto-labelled because the LLM was unavailable).

## Caveats

- One week of data; numbers will move week to week. Track them over time rather than trusting one run.
- Silhouette ignores noise, so it slightly favours settings that leave more reviews unassigned.
- LLM-as-judge is itself imperfect; a human-labelled sample is the gold standard next step.
- About a third of reviews land in noise. These are mostly one-off complaints; they are counted, not hidden.
