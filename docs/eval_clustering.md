# Clustering evaluation

Data: 5174 Google Play reviews for Groww, 2026-09-09 to 2026-10-16 · run 2026-10-17
Run: `python -m scripts.evaluate_clustering <raw.pkl>`

## 1. Funnel

| Stage | Reviews | Avg rating |
|---|---|---|
| Scraped (all in window) | 5174 | 4.40 |
| After cleaning (English, 8+ words, PII masked, spam removed) | 676 | 3.08 |
| Assigned to a theme | 462 | |
| Noise (fits no theme) | 214 (31.7%) | |

Groq spam filter: {'batches': 14, 'failed_batches': 12, 'removed_as_spam': 33}

The cleaned set is far more negative than the whole (3.08 vs 4.40) because most short reviews are 5-star praise.
That is why headline ratings in the report are computed on all reviews, and themes on the cleaned set.

## 2. Cluster quality (UMAP 5-D + HDBSCAN leaf, min_cluster_size 10)

| Metric | Value |
|---|---|
| Themes found | 19 |
| Noise | 31.7% |
| Largest theme | 9.2% of reviews |
| Silhouette (excl. noise) | 0.548 |
| Theme sizes | 62, 38, 36, 35, 33, 32, 31, 28, 28, 25, 16, 15, 15, 14, 13, 11, 10, 10, 10 |
| Runtime | 68s |

## 3. Stability across random seeds (42, 7, 123)

Adjusted Rand Index between runs: 0.62, 0.48, 0.53 (mean **0.54**; 1.0 = identical, 0 = no better than random)

## 4. Ablations

| Variant | Themes | Noise % | Largest theme % |
|---|---|---|---|
| **Chosen:** UMAP + HDBSCAN (leaf) | 19 | 31.7 | 9.2 |
| No UMAP (HDBSCAN on raw 384-d) | 0 | 100.0 | 100.0 |
| UMAP + HDBSCAN default (eom) | 3 | 0.0 | 92.6 |

## 5. Top themes and theme accuracy (judge: qwen/qwen3.8-27b; writers: Gemini, backup gpt-oss-120b)

| # | Theme (LLM title) | Reviews | Avg ★ | Impact | Distinctive words | Members matching title | Other-theme reviews matching |
|---|---|---|---|---|---|---|---|
| 1 | Consistently poor customer service and unresponsive support | 36 | 1.44 | 469.79 | service, customer, support, customer support | 9/10 | 0/5 |
| 2 | Withdrawal and fund credit delays/failures causing loss of money | 33 | 1.79 | 276.96 | money, account, bank, withdrawal | 6/10 | 0/5 |
| 3 | Account opening and family account management failures for minors and linked accounts | 25 | 2.04 | 191.74 | account, minor, family, switch | 3/10 | 0/5 |
| 4 | App fails to launch or work after recent updates | 28 | 2.39 | 176.29 | working, issue, open, previously | 7/10 | 0/5 |
| 5 | Highly praised for its easy and user‑friendly interface | 62 | 4.5 | 156.11 | easy, super, friendly, user | 6/10 | 0/5 |

**Theme precision:** 31/50 (62%) of sampled member reviews match their theme title.
**False-match rate:** 0/25 (0%) of reviews from other themes match the title.
Titles written by the LLM: 5/5 (the rest were auto-labelled because the LLM was unavailable).

## Caveats

- One week of data; numbers will move week to week. Track them over time rather than trusting one run.
- Silhouette ignores noise, so it slightly favours settings that leave more reviews unassigned.
- LLM-as-judge is itself imperfect; a human-labelled sample is the gold standard next step.
- About a third of reviews land in noise. These are mostly one-off complaints; they are counted, not hidden.
