# Decision log: Weekly Product Review Pulse

What the agent does, what I decided, why, what it cost, and how I checked it.
Numbers come from [eval_clustering.md](eval_clustering.md) (one week of live Groww reviews, 9 Sep to 16 Oct 2026).

## The problem

Groww gets thousands of Play Store reviews a month. Product, support and leadership teams each want to know **what users are complaining about this week**, but nobody reads 5,000 reviews, and ad-hoc spreadsheet triage is slow and inconsistent.

**Goal:** every week, automatically turn raw reviews into a short, trustworthy brief (the top themes, real quotes, and suggested actions per team) delivered where people already work (a Google Doc and an email).

**What "trustworthy" means here:**
- Themes come from the data, not from an LLM's imagination.
- Every quote is a real review.
- Headline numbers represent all users, not a filtered subset.
- If a step fails, the report says so instead of making something up.

## Pipeline

```
Play Store (5,174 reviews) → clean (English, 8+ words, PII masked, injection text neutralised, spam removed)
  → embed (MiniLM, 384-d, local) → UMAP (5-d) → HDBSCAN (themes + noise)
  → rank by impact → Gemini writes title / root cause / quotes / actions per top theme
  → quotes checked against real reviews → Google Doc section + teaser email (dry run by default)
```

## Decisions and tradeoffs

### 1. Clean hard, then measure on everything
- **Kept for theme analysis:** English reviews with 8+ words, PII masked, and spam removed by an LLM. That's about **640–700 of 5,174 (13–14%)**.
- **Why:** "Great app 👍" carries no theme information, and non-English or very short text clusters badly.
- **The trap I found and fixed:** the old report averaged ratings over the *cleaned* set and showed **~3.0★**. The real average across all reviews is **4.4★**. Short reviews are mostly 5-star praise, so filtering them out made the product look far worse. Headline rating and % negative now use **all** reviews; themes use the cleaned set. The eval shows both.

### 2. Themes from embeddings + UMAP + HDBSCAN, not from an LLM reading batches
The first version asked an LLM to name themes from batches, then assigned reviews to themes by **keyword overlap**. A theme like "App Crash on Login" matched any review containing "app" or "on", so one theme swallowed hundreds of unrelated reviews, and its output listed duplicate themes.
- **Embeddings** (MiniLM, run locally: free, deterministic, review text stays on the machine) put reviews that *mean* the same thing close together even with different words ("money stuck" vs "withdrawal pending").
- **UMAP** reduces 384 dimensions to 5. **Ablation:** HDBSCAN directly on 384-d found **0 themes** (everything was noise), because distances become meaningless in high dimensions.
- **HDBSCAN** doesn't need the number of themes in advance and leaves one-off complaints as **noise** instead of forcing them into a theme. About a third of cleaned reviews are noise. They're counted, not hidden.

### 3. Tuned with a rule fixed in advance
`scripts/tune_clustering.py` swept 96 settings. **The rule, written before looking:** largest theme under 40% of reviews, noise under 40%, 5–25 themes, then the highest silhouette.
- **Ablation:** HDBSCAN's default `eom` selection put **~93–95% of reviews in one cluster.** `leaf` selection gives ~19 themes, the largest about 7%.
- **Caveat:** silhouette ignores noise, so it slightly favours settings that leave more reviews unassigned. That's why the noise cap is part of the rule.

### 4. Rank by impact, not by size
Impact = reviews × (5 − average rating) × (1 + log10(1 + thumbs-up)).
- **Why:** a theme matters more if more people raise it, they're angrier, and other users agree (thumbs-up). The log stops one viral review from dominating.
- Only the top 5 go into the report; leadership reads five themes, not nineteen.

### 5. The LLM explains themes; it doesn't find them
Gemini sees one cluster at a time: its size, average rating, distinctive words (class-based TF-IDF) and the 8 reviews closest to the cluster's centre (the most *typical*, not the loudest). It writes a title, root cause, two quotes, and one suggested action each for product, support and engineering.
- Reviews are marked as data, not instructions, to resist prompt injection.
- Duplicate titles across clusters are made distinct automatically.

### 6. Quotes must be real
Every quote is matched against the cluster's actual reviews (exact or ≥95% fuzzy match). If the LLM's quote fails, the top real review is used instead and flagged as a fallback. A quote in the report is always something a real user wrote.

### 7. Fail honestly
The old fallback, used when the LLM was down, produced **pre-written themes** with specific-sounding causes ("null pointer crash in splash screen") that weren't derived from the reviews, and that's what went into a published report. Now, if Gemini is unavailable after retries, the theme is labelled `Auto-labelled theme: <top words>` with real quotes and **no invented actions**.
- Free-tier Gemini returns "503 busy" on about 1 in 3 calls, so calls retry with backoff (5s, 15s, 30s).
- Gemini's free tier also caps requests at **20 per day**, which my testing exhausted. So there's a **backup writer** (gpt-oss-120b on Groq) before the auto-label fallback. Order: Gemini → Groq → honest auto-label. Once Gemini reports its daily quota is gone, the run stops retrying it.
- **Formatting uses templates, not an LLM.** The doc and email renderers used to call Gemini just to format text. That spent scarce quota and could silently change numbers in the report, so it's now off by default (`RENDER_WITH_LLM=true` re-enables it).
- The Groq spam filter used to swallow errors silently. That hid the fact that its model had been retired and the filter had stopped working. Failures are now logged and counted, and a failed batch keeps its reviews rather than dropping them.

### 8. Respect free-tier limits instead of losing data
Groq's free tier allows 8,000 tokens per minute. Large batches were rejected, so batches are now smaller and spaced 30 seconds apart. It's a weekly batch job, so a few minutes of pacing costs nothing.

### 9. Safe delivery
- **Dry run is the default:** a run renders everything but publishes nothing unless asked, and email is a **draft** unless `--send-email` is given.
- One section per (product, ISO week). A repeat run is skipped unless `force` is used. (During my testing week 32 was re-published several times with `force`; the guard itself works.)
- Every run is logged to SQLite (counts, doc ID, draft ID, errors) for audit.
- The Doc/Gmail actions sit behind a separate tool server so Google credentials stay out of the agent. **To be precise:** that server is a REST API modelled on MCP tools, not the official MCP protocol (JSON-RPC). Moving to the official protocol is on the roadmap.

### 10. Privacy
Phone numbers, emails, UPI IDs, PAN, Aadhaar, bank and demat numbers are masked **before** any text goes to an LLM or into the report. Usernames are masked.

## How I measured it (see eval_clustering.md)

| What | Result | What it tells me |
|---|---|---|
| Ablation: no UMAP | 0 themes (100% noise) | UMAP is necessary |
| Ablation: default `eom` | 1 cluster holds ~93–95% | `leaf` selection is necessary |
| Themes found / largest theme / noise | 19 / 7–9% / 32–38% | Usable, distinct themes; about a third of reviews are one-offs |
| Silhouette (excl. noise) | 0.55–0.56 | Themes are reasonably separated |
| Stability across 3 random seeds (ARI) | 0.54–0.61 | Moderate: big themes persist, small ones shift. Report only the top 5, and track over weeks |
| Theme precision (LLM judge from a third vendor, Qwen, so no model grades its own work) | 62–64% | Titles describe most of a theme but not all; some clusters mix related issues |
| False-match rate (other themes' reviews match a title) | 0–4% | Themes are distinct from each other |

**What I tried that didn't help:** asking the LLM to describe what "most" reviews share moved theme precision from 64% to 62%, which is within noise. The limit is cluster purity, not wording. Next I'd try a higher `min_samples` for tighter clusters, or split mixed clusters, and **validate with a human-labelled sample** (the LLM judge is a proxy).

## Known limitations
- Each run is capped at about 5,000 reviews (about 5 weeks for Groww), not the configured 10.
- Hinglish reviews written in English letters pass the English filter and form their own cluster.
- One week's numbers move; trends over several weeks are more reliable than any single run.
- The tool server's Railway deployment is currently offline.
- Free-tier limits: Gemini allows ~20 requests/day and Groq ~200k tokens/day per model. A weekly run fits easily (about 6 LLM calls and ~40k tokens), but repeated test runs in one day exhaust them, which is why the spam filter failed on many batches in my final runs. Failed batches keep their reviews, so the cost is a little extra noise, not lost data.
- The top 5 by impact can include a large *praise* theme (e.g. "easy, user-friendly interface", 4.5★). That's honest, but a v2 report should split "what users love" from "what's hurting them".
