# Weekly Product Review Pulse (AI-AGENT)

**Weekly Product Review Pulse** is an automated intelligence agent designed to ingest, analyze, synthesize, and deliver customer feedback from public mobile application store reviews. Currently, it is focused on tracking **Groww** via the **Google Play Store**.

Instead of manual spreadsheet analysis or ad-hoc API integrations, this agent leverages modern ML clustering and LLM synthesis to provide product, support, and leadership teams with a reliable, automated, and repeatable weekly pulse of public customer sentiment. It publishes its findings directly to **Google Docs** and **Gmail** via a dedicated **Model Context Protocol (MCP)** Server.

## Key Features

- **Automated Data Ingestion**: Scrapes Google Play Store reviews for Groww (`com.nextbillion.groww`) on a configurable rolling window (8–12 weeks).
- **Intelligent Preprocessing & Safety**: Performs comprehensive PII scrubbing (phone numbers, emails, UPI, etc.) and guards against prompt injections.
- **Advanced Clustering & Reasoning**: 
  - Uses sentence embeddings (`sentence-transformers/all-MiniLM-L6-v2`) mapped into a 5D UMAP manifold.
  - Clusters semantic density using HDBSCAN to find the most impactful themes while isolating noise.
- **LLM Synthesis & Quote Grounding**: Generates actionable insights using Gemini/Groq LLMs while rigorously ensuring extracted verbatim quotes exist in the raw source data (anti-hallucination).
- **Google Workspace MCP Integration**: Uses an independent MCP server (`https://web-production-c16ea.up.railway.app`) to format and append sections to a living Google Doc and draft teaser emails in Gmail.
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
- **LLM Integration**: Google GenAI, Groq
- **Integrations**: Model Context Protocol (MCP) SDK, Google Workspace APIs (Docs & Gmail)

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
- `ENVIRONMENT`: Set to `development` to strictly draft emails, or `production` to send them.

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

## Roadmap & Future Scope
- Expand platform ingestion to Apple App Store.
- Add support for more products (INDMoney, PowerUp Money, Wealth Monitor, Kuvera).
- Enhanced historical trend tracking and visualization.

---
*Built with ❤️ to surface real user voices automatically.*
