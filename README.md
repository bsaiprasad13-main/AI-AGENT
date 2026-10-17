# Weekly Product Review Pulse (AI-AGENT)

**Weekly Product Review Pulse** is an automated intelligence agent designed to ingest, analyze, synthesize, and deliver customer feedback from public mobile application store reviews. Currently, it is focused on tracking **Groww** via the **Google Play Store**.

Instead of manual spreadsheet analysis or ad-hoc API integrations, this agent leverages modern ML clustering and LLM synthesis to provide product, support, and leadership teams with a reliable, automated, and repeatable weekly pulse of public customer sentiment. It publishes its findings to **Google Docs** and **Gmail**, either directly with Google OAuth or through a separate tool server that exposes `append_to_doc`, `create_email_draft` and `send_email` as MCP-style tools over REST.

## Key Features

- **Automated Data Ingestion**: Scrapes Google Play Store reviews for Groww (`com.nextbillion.groww`) on a configurable rolling window (8–12 weeks).
- **Intelligent Preprocessing & Safety**: Performs comprehensive PII scrubbing (phone numbers, emails, UPI, etc.) and guards against prompt injections.
- **Theme discovery (embeddings + UMAP + HDBSCAN)**:
  - Embeds each review locally with `all-MiniLM-L6-v2` (384-d), reduces to 5-D with UMAP, clusters with HDBSCAN (`leaf` selection), and keeps one-off complaints as noise instead of forcing them into a theme.
  - Settings chosen with `scripts/tune_clustering.py`; quality, stability and theme accuracy measured in [docs/eval_clustering.md](docs/eval_clustering.md).
  - Themes ranked by impact = reviews x (5 - avg rating) x (1 + log10(1 + thumbs-up)).
- **LLM Synthesis & Quote Grounding**: Generates actionable insights using Gemini/Groq LLMs while rigorously ensuring extracted verbatim quotes exist in the raw source data (anti-hallucination).
- **Google Workspace delivery**: Appends a weekly section to a living Google Doc and drafts or sends a teaser email, via direct Google OAuth or the separate tool server ([MCP-server repo](https://github.com/bsaiprasad13-main/MCP-server)). The server is REST, modelled on MCP tools; moving it to the official MCP protocol is on the roadmap.
- **Idempotency & Safety**: Safe to re-run; it will not duplicate Google Doc sections or spam emails for the same ISO week.

## Architecture

The system is built on **Clean Architecture** principles, segregating data ingestion, preprocessing, clustering, rendering, and delivery. 

For detailed diagrams and architectural deep-dives, see:
- [docs/architecture.md](docs/architecture.md)
- [docs/problemStatement.md](docs/problemStatement.md)

## Tech Stack

- **Core & API**: Python 3.10+, FastAPI, Uvicorn, Click, Rich
- **Data Gathering**: google-play-scraper
- **Machine Learning & NLP**: sentence-transformers, UMAP, HDBSCAN, scikit-learn
- **LLM Integration**: Gemini 3.5 Flash (theme summaries), Groq gpt-oss-20b (spam filter), gpt-oss-120b (evaluation judge)
- **Integrations**: Google Workspace APIs (Docs & Gmail), REST tool server (MCP-style)

## Setup and Installation

### 1. Clone the repository
```bash
git clone https://github.com/bsaiprasad13-main/AI-AGENT.git
cd AI-AGENT
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Variables
Copy the `.env.example` file to `.env` and fill in your credentials.
```bash
cp .env.example .env
```
Key variables include:
- `GEMINI_API_KEY`: Your Gemini API key for LLM synthesis.
- `MCP_SERVER_URL`: Your hosted MCP server URL.
- `ENVIRONMENT`: Set to `development` to strictly draft emails. Use the `--send-email` flag in the CLI to actually send emails.

### 4. Running the Application

To run the Web API:
```bash
python scripts/start_api.py
```

To run the Agent Pipeline manually via CLI:
```bash
python -m src.agent.cli --product groww --week 2026-W32
```

## Deployment

The project can be deployed to modern PaaS providers like Railway. See the [Deployment Guide](deployment.md) for step-by-step instructions.

## Design decisions and evaluation

See [docs/DECISIONS.md](docs/DECISIONS.md) and [docs/eval_clustering.md](docs/eval_clustering.md).

## Roadmap & Future Scope
- Move the tool server to the official MCP protocol.
- Human-labelled sample to validate theme accuracy (the current check uses an LLM judge).
- Expand platform ingestion to Apple App Store.
- Add support for more products (INDMoney, PowerUp Money, Wealth Monitor, Kuvera).
- Enhanced historical trend tracking and visualization.

---
*Built with ❤️ to surface real user voices automatically.*
