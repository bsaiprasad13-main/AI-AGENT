import json
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from src.agent.idempotency import IdempotencyStore
from src.agent.mcp_client import MCPClient, MCPClientError
from src.agent.orchestrator import ReviewPulseOrchestrator
from src.models.report import WeeklyPulseReport
from src.utils.config_loader import load_settings, get_project_root

app = FastAPI(
    title="Product Review Pulse API",
    description="Backend API to trigger the weekly product review analysis.",
    version="1.0.0",
)

# Allow CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State Tracker
app_state = {
    "status": "idle", # idle, loading, success, error
    "step": "",
    "error": None
}

class StatusLogHandler(logging.Handler):
    """Intercepts logs to update the global step status for the frontend."""
    def emit(self, record):
        msg = record.getMessage()
        if "Ingesting" in msg:
            app_state["step"] = "Scraping Play Store Reviews..."
        elif "Sanitized and prepared" in msg:
            app_state["step"] = "Preprocessing & PII Scrubbing..."
        elif "Formed" in msg:
            app_state["step"] = "Clustering Themes..."
        elif "Publishing" in msg or "Creating" in msg or "Sending" in msg:
            app_state["step"] = "Drafting & Publishing..."
        elif "completed successfully" in msg:
            app_state["step"] = "Done!"

# Attach the handler
status_handler = StatusLogHandler()
logging.getLogger("src.agent.orchestrator").addHandler(status_handler)
logging.getLogger("src.agent.orchestrator").setLevel(logging.INFO)

class TriggerRequest(BaseModel):
    product: str = "groww"
    weeks: Optional[int] = None
    force: bool = False

class PublishRequest(BaseModel):
    product: str = "groww"
    send_email: bool = False
    doc_id: Optional[str] = None
    recipients: Optional[List[str]] = None
    subject: Optional[str] = None
    body: Optional[str] = None

def run_analysis_task(req: TriggerRequest):
    """Background task to run the review pulse orchestrator."""
    global app_state
    app_state["status"] = "loading"
    app_state["step"] = "Starting..."
    app_state["error"] = None
    
    try:
        settings = load_settings()
        mcp_client = MCPClient(config=settings.mcp)
        orchestrator = ReviewPulseOrchestrator(settings=settings, mcp_client=mcp_client)
        
        # Run the analysis ONLY (dry_run=True means do not publish yet)
        res = orchestrator.run(
            product_id=req.product,
            weeks=req.weeks,
            dry_run=True,  # Crucial: This prevents it from sending to Docs/Gmail immediately
            force=req.force,
        )
        
        if res.status == "failed":
            app_state["status"] = "error"
            app_state["error"] = res.error_message
        else:
            app_state["status"] = "success"
            app_state["step"] = "Analysis Complete. Ready for Review."
    except Exception as e:
        app_state["status"] = "error"
        app_state["error"] = str(e)


@app.post("/api/v1/trigger")
async def trigger_analysis(req: TriggerRequest, background_tasks: BackgroundTasks):
    """Triggers the weekly review pulse analysis in the background."""
    if app_state["status"] == "loading":
        raise HTTPException(status_code=400, detail="A run is already in progress.")
        
    background_tasks.add_task(run_analysis_task, req)
    return {
        "status": "accepted",
        "message": f"Analysis for product '{req.product}' started."
    }

@app.get("/api/v1/run-status")
async def get_run_status():
    """Returns the live status of the analysis."""
    return app_state

@app.get("/api/v1/latest-report")
async def get_latest_report(product: str = "groww"):
    """Fetches the latest generated JSON report for visualization."""
    out_dir = get_project_root() / "data"
    report_path = out_dir / f"latest_report_{product}.json"
    
    if not report_path.exists():
        return {"status": "not_found", "message": "No analysis yet. Click Run Analysis to get started."}
        
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        from src.renderer.doc_renderer import DocRenderer
        from src.renderer.email_renderer import EmailRenderer
        from src.utils.config_loader import get_product

        report = WeeklyPulseReport(**data)
        settings = load_settings()
        doc_renderer = DocRenderer(config=settings.rendering)
        email_renderer = EmailRenderer(config=settings.rendering)

        doc_append_text = doc_renderer.render_for_doc_append(report)
        product_config = get_product(product)
        doc_deep_link = email_renderer.get_deep_link_url(
            product_id=product,
            iso_week=report.iso_week,
            custom_doc_id=product_config.google_doc_id
        )
        email_payload = email_renderer.render_email(
            report=report,
            doc_deep_link=doc_deep_link,
            custom_recipients=product_config.recipients
        )

        return {
            "status": "success", 
            "report": data,
            "doc_text": doc_append_text,
            "email_subject": email_payload.subject,
            "email_body": email_payload.body_text
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "success", "report": data}

@app.post("/api/v1/publish")
async def publish_report(req: PublishRequest):
    """Publishes the approved report to Google Docs and Gmail."""
    out_dir = get_project_root() / "data"
    report_path = out_dir / f"latest_report_{req.product}.json"
    
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No generated report found to publish.")
        
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # Rehydrate the model
    report = WeeklyPulseReport(**data)
    
    settings = load_settings()
    mcp_client = MCPClient(config=settings.mcp)
    orchestrator = ReviewPulseOrchestrator(settings=settings, mcp_client=mcp_client)
    
    res = orchestrator.publish_report(
        report=report,
        send_email=req.send_email,
        custom_doc_id=req.doc_id,
        custom_recipients=req.recipients,
        custom_subject=req.subject,
        custom_body=req.body,
    )
    
    if res.status == "failed":
        raise HTTPException(status_code=500, detail=res.error_message)
        
    return {"status": "success", "doc_status": res.doc_response, "draft_status": res.draft_response}


@app.get("/api/v1/history")
async def get_history(product: Optional[str] = None, limit: int = 20):
    """Fetches the history of past analysis runs."""
    settings = load_settings()
    store = IdempotencyStore(db_path=settings.storage.audit_db_path)
    records = store.list_history(product_id=product, limit=limit)
    return {"records": [
        {
            "run_id": r.run_id,
            "product_id": r.product_id,
            "iso_week": r.iso_week,
            "reviews_count": r.reviews_count,
            "doc_status": r.doc_status,
            "draft_status": r.draft_status,
            "error_message": r.error_message,
            "created_at": r.created_at
        }
        for r in records
    ]}

@app.get("/api/v1/status")
async def get_status():
    """Checks MCP connectivity."""
    settings = load_settings()
    client = MCPClient(config=settings.mcp)
    
    try:
        status = client.get_server_status()
        return {
            "status": "online",
            "mcp_server": status
        }
    except MCPClientError as e:
        return {
            "status": "offline",
            "error": str(e)
        }

# Serve the static frontend
static_dir = get_project_root() / "src" / "api" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(content=b"", media_type="image/x-icon")

@app.get("/")
async def serve_frontend():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Frontend not found. Please create index.html in src/api/static"}
