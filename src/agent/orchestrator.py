"""End-to-end Orchestrator for the Weekly Product Review Pulse Pipeline.

Connects and automates:
  1. Data Ingestion (Google Play Store reviews)
  2. Preprocessing & PII Scrubbing (Phone, UPI, Email, Prompt Injection defense)
  3. Semantic Reasoning (Embedding, HDBSCAN clustering, LLM theme synthesis, Quote grounding)
  4. Output Rendering (Google Docs plain-text append payload, Gmail HTML/plain-text teaser)
  5. MCP Tool Execution (Appends to Google Doc, creates Gmail draft via Railway MCP Server)
  6. Idempotency & Audit Tracking (SQLite audit store)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.agent.google_workspace import GoogleWorkspaceClient
from src.agent.idempotency import IdempotencyStore, RunRecord
from src.agent.mcp_client import MCPClient, MCPClientError
from src.ingestion.play_store import PlayStoreIngestionEngine
from src.models.report import DocSectionAST, EmailPayload, WeeklyPulseReport
from src.models.review import RawReview, SanitizedReview
from src.preprocessing.sanitization import ReviewSanitizationPipeline
from src.reasoning.clusterer import ReviewClusterer
from src.reasoning.embedder import SemanticEmbedder
from src.reasoning.quote_grounder import QuoteGrounder
from src.reasoning.synthesizer import ReviewSynthesizer
from src.renderer.doc_renderer import DocRenderer
from src.renderer.email_renderer import EmailRenderer
from src.utils.config_loader import (
    PipelineSettings,
    ProductTarget,
    get_product,
    get_project_root,
    load_settings,
)

logger = logging.getLogger(__name__)


class OrchestrationResult(BaseModel):
    """Encapsulates the complete result and execution metadata of an orchestrator run."""
    run_id: str
    product_id: str
    iso_week: str
    status: str  # "success", "skipped_idempotent", "failed"
    is_dry_run: bool
    report: Optional[WeeklyPulseReport] = None
    doc_ast: Optional[DocSectionAST] = None
    email_payload: Optional[EmailPayload] = None
    doc_response: Optional[Dict[str, Any]] = None
    draft_response: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ReviewPulseOrchestrator:
    """Coordinates and executes the entire Weekly Product Review Pulse Pipeline."""

    def __init__(
        self,
        settings: Optional[PipelineSettings] = None,
        mcp_client: Optional[MCPClient] = None,
        google_client: Optional[GoogleWorkspaceClient] = None,
        idempotency_store: Optional[IdempotencyStore] = None,
    ):
        self.settings = settings or load_settings()
        self.mcp_client = mcp_client or MCPClient(config=self.settings.mcp)
        self.google_client = google_client or GoogleWorkspaceClient()
        self.idempotency_store = idempotency_store or IdempotencyStore(
            db_path=self.settings.storage.audit_db_path
        )

        # Initialize sub-modules
        self.ingestion_engine = PlayStoreIngestionEngine(config=self.settings.ingestion)
        self.sanitizer = ReviewSanitizationPipeline(config=self.settings.preprocessing)
        self.embedder = SemanticEmbedder(config=self.settings.reasoning.embedding)
        self.clusterer = ReviewClusterer(
            config=self.settings.reasoning,
        )
        self.synthesizer = ReviewSynthesizer(config=self.settings.reasoning.synthesis)
        self.quote_grounder = QuoteGrounder(config=self.settings.reasoning.quote_grounding)
        self.doc_renderer = DocRenderer(config=self.settings.rendering)
        self.email_renderer = EmailRenderer(config=self.settings.rendering)

    def run(
        self,
        product_id: str = "groww",
        weeks: Optional[int] = None,
        dry_run: bool = True,
        force: bool = False,
        send_email: bool = False,
        custom_doc_id: Optional[str] = None,
        custom_recipients: Optional[List[str]] = None,
        raw_reviews_override: Optional[List[RawReview]] = None,
        iso_week_override: Optional[str] = None,
    ) -> OrchestrationResult:
        """Executes the full pipeline for the specified product.

        Args:
            product_id: Target product key in products.yaml (default: "groww").
            weeks: Rolling window in weeks (default from settings: 10).
            dry_run: If True, renders all assets and previews without writing to Google Doc / Gmail.
            force: If True, bypasses idempotency guard for previously completed weeks.
            send_email: If True and publishing, delivers email directly to inboxes rather than saving as draft.
            custom_doc_id: Overrides target Google Doc ID.
            custom_recipients: Overrides recipient email list.
            raw_reviews_override: Ingests provided raw reviews instead of scraping.
            iso_week_override: Overrides calculated ISO week (e.g. for deterministic testing).

        Returns:
            OrchestrationResult containing all generated reports, render payloads, and execution statuses.
        """
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        window_weeks = weeks or self.settings.ingestion.default_rolling_window_weeks
        now = datetime.now(timezone.utc)
        iso_week = iso_week_override or f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"

        logger.info(f"Starting pipeline run '{run_id}' for product '{product_id}' (Week: {iso_week}, Dry Run: {dry_run})")

        # 1. Load and validate target product configuration
        product: ProductTarget = get_product(product_id)
        target_doc_id = custom_doc_id or product.google_doc_id
        target_recipients = custom_recipients or product.recipients

        # 2. Idempotency guard check
        if not force and not dry_run and self.idempotency_store.has_published_for_week(product_id, iso_week):
            msg = f"ISO week {iso_week} has already been published for {product_id}. Use force=True to re-publish."
            logger.warning(msg)
            return OrchestrationResult(
                run_id=run_id,
                product_id=product_id,
                iso_week=iso_week,
                status="skipped_idempotent",
                is_dry_run=dry_run,
                error_message=msg,
            )

        try:
            # 3. Data Ingestion
            if raw_reviews_override is not None:
                logger.info(f"Using {len(raw_reviews_override)} provided raw reviews...")
                raw_reviews = raw_reviews_override
            else:
                logger.info(f"Ingesting Google Play reviews for {product.package_name} (rolling {window_weeks} weeks)...")
                raw_reviews = self.ingestion_engine.fetch_reviews(
                    package_name=product.package_name,
                    product_id=product.product_id,
                    iso_week=iso_week,
                    force_refresh=force,
                )

            if not raw_reviews:
                raise ValueError(f"No reviews found or ingested for {product_id}.")

            logger.info(f"Ingested {len(raw_reviews)} raw reviews.")

            # 4. Preprocessing: PII Scrubbing & Sanitization
            batch = self.sanitizer.process_batch(
                raw_reviews=raw_reviews,
                product_id=product_id,
                iso_week=iso_week,
            )
            sanitized_reviews = batch.reviews

            if not sanitized_reviews:
                raise ValueError("All reviews were filtered out during preprocessing.")

            logger.info(f"Sanitized and prepared {len(sanitized_reviews)} valid reviews.")

            # 5. Semantic Reasoning: Clustering, LLM Theme Synthesis & Quote Grounding
            clusters, outliers = self.clusterer.cluster_reviews(sanitized_reviews)
            logger.info(f"Formed {len(clusters)} issue clusters (outliers: {len(outliers)}).")

            raw_themes = self.synthesizer.synthesize_clusters(
                clusters=clusters[:5],
                product_id=product_id,
            )

            # Ground quotes and verify against verbatim source text
            cluster_map = {c.metrics.cluster_id: c for c in clusters}
            theme_insights = []
            for theme in raw_themes:
                c_obj = cluster_map.get(theme.cluster_id)
                if c_obj:
                    grounded = self.quote_grounder.ground_theme(theme, c_obj, sanitized_reviews)
                    theme_insights.append(grounded)

            # Headline metrics describe ALL reviews in the window. Only ~14% survive
            # cleaning (English, 8+ words, not spam), and short reviews are mostly
            # 5-star praise, so averaging the cleaned set alone reported ~3.0 stars
            # when the real average was ~4.4.
            total_reviews = len(sanitized_reviews)
            avg_score = round(sum(r.score for r in raw_reviews) / len(raw_reviews), 2)
            neg_count_all = sum(1 for r in raw_reviews if r.score <= 2)
            logger.info(
                f"Ratings: all {len(raw_reviews)} reviews avg {avg_score}; "
                f"analysed {total_reviews} avg {round(sum(r.score for r in sanitized_reviews) / total_reviews, 2)}"
            )

            # Construct final report
            report = WeeklyPulseReport(
                product_id=product_id,
                product_display_name=product.display_name,
                iso_week=iso_week,
                start_date=sanitized_reviews[-1].at if sanitized_reviews else now,
                end_date=now,
                total_reviews_extracted=len(raw_reviews),
                total_reviews_analyzed=total_reviews,
                average_rating=avg_score,
                negative_review_percentage=round((neg_count_all / len(raw_reviews)) * 100, 1),
                themes=theme_insights,
                outlier_count=len(outliers),
            )
            
            # Save latest report to disk for frontend to read
            out_dir = get_project_root() / "data"
            out_dir.mkdir(exist_ok=True)
            with open(out_dir / f"latest_report_{product_id}.json", "w", encoding="utf-8") as f:
                f.write(report.model_dump_json(indent=2))

            # 6. Render Output Payloads
            doc_ast = self.doc_renderer.render_to_ast(report)
            doc_append_text = self.doc_renderer.render_for_doc_append(report)
            doc_deep_link = self.email_renderer.get_deep_link_url(
                product_id=product_id,
                iso_week=iso_week,
                custom_doc_id=target_doc_id,
            )
            email_payload = self.email_renderer.render_email(
                report=report,
                doc_deep_link=doc_deep_link,
                custom_recipients=target_recipients,
            )

            # 7. MCP Publishing (if not dry run)
            doc_response: Optional[Dict[str, Any]] = None
            draft_response: Optional[Dict[str, Any]] = None
            doc_status = "dry_run" if dry_run else "pending"
            draft_status = "dry_run" if dry_run else "pending"

            if not dry_run:
                # 7a. Append to Google Doc (via local token.json if available, or MCP server)
                try:
                    if self.google_client and self.google_client.is_available:
                        logger.info(f"Publishing to Google Doc '{target_doc_id}' via direct Google OAuth (token.json)...")
                        doc_response = self.google_client.append_to_doc(
                            doc_id=target_doc_id,
                            content=doc_append_text,
                        )
                    else:
                        logger.info(f"Publishing to Google Doc '{target_doc_id}' via MCP server...")
                        doc_response = self.mcp_client.append_to_doc(
                            doc_id=target_doc_id,
                            content=doc_append_text,
                        )
                    doc_status = "appended"
                except Exception as e:
                    logger.error(f"Failed to append to Google Doc: {e}")
                    doc_status = "failed"
                    raise

                # 7b. Deliver or Draft Email (via local token.json if available, or MCP server)
                try:
                    if send_email:
                        if self.google_client and self.google_client.is_available:
                            logger.info(f"Sending live email to {target_recipients} via direct Google OAuth (token.json)...")
                            draft_response = self.google_client.send_email(
                                recipients=target_recipients,
                                subject=email_payload.subject,
                                body=email_payload.body_html or email_payload.body_text,
                                is_html=bool(email_payload.body_html),
                            )
                        else:
                            logger.info(f"Sending live email to {target_recipients} via MCP server...")
                            draft_response = self.mcp_client.send_email(
                                to=target_recipients,
                                subject=email_payload.subject,
                                body=email_payload.body_html or email_payload.body_text,
                            )
                        draft_status = "sent"
                    else:
                        if self.google_client and self.google_client.is_available:
                            logger.info(f"Creating Gmail draft for {target_recipients} via direct Google OAuth (token.json)...")
                            draft_response = self.google_client.create_email_draft(
                                recipients=target_recipients,
                                subject=email_payload.subject,
                                body=email_payload.body_html or email_payload.body_text,
                                is_html=bool(email_payload.body_html),
                            )
                        else:
                            logger.info(f"Creating Gmail draft for {target_recipients} via MCP server...")
                            draft_response = self.mcp_client.create_email_draft(
                                to=target_recipients,
                                subject=email_payload.subject,
                                body=email_payload.body_text,
                            )
                        draft_status = "created"
                except Exception as e:
                    logger.error(f"Failed to process Gmail message/draft: {e}")
                    draft_status = "failed"

            # 8. Record audit log in SQLite
            run_rec = RunRecord(
                run_id=run_id,
                product_id=product_id,
                iso_week=iso_week,
                reviews_count=total_reviews,
                themes_count=len(theme_insights),
                avg_rating=avg_score,
                doc_id=target_doc_id,
                doc_status=doc_status,
                draft_id=draft_response.get("draft_id") if draft_response else None,
                draft_status=draft_status,
                error_message=None,
            )
            self.idempotency_store.record_run(run_rec)

            logger.info(f"Run '{run_id}' completed successfully! (Doc: {doc_status}, Draft: {draft_status})")

            return OrchestrationResult(
                run_id=run_id,
                product_id=product_id,
                iso_week=iso_week,
                status="success",
                is_dry_run=dry_run,
                report=report,
                doc_ast=doc_ast,
                email_payload=email_payload,
                doc_response=doc_response,
                draft_response=draft_response,
            )

        except Exception as e:
            logger.exception(f"Pipeline run '{run_id}' failed: {e}")
            fail_rec = RunRecord(
                run_id=run_id,
                product_id=product_id,
                iso_week=iso_week,
                reviews_count=0,
                themes_count=0,
                avg_rating=0.0,
                doc_id=target_doc_id,
                doc_status="failed",
                draft_status="failed",
                error_message=str(e),
            )
            self.idempotency_store.record_run(fail_rec)

            return OrchestrationResult(
                run_id=run_id,
                product_id=product_id,
                iso_week=iso_week,
                status="failed",
                is_dry_run=dry_run,
                error_message=str(e),
            )

    def publish_report(
        self,
        report: WeeklyPulseReport,
        send_email: bool = False,
        custom_doc_id: Optional[str] = None,
        custom_recipients: Optional[List[str]] = None,
        custom_subject: Optional[str] = None,
        custom_body: Optional[str] = None,
    ) -> OrchestrationResult:
        """Publishes an already generated report to Google Docs and Gmail."""
        run_id = f"pub_{uuid.uuid4().hex[:12]}"
        logger.info(f"Publishing report '{run_id}' for '{report.product_id}'")
        
        product: ProductTarget = get_product(report.product_id)
        target_doc_id = custom_doc_id or product.google_doc_id
        target_recipients = custom_recipients or product.recipients

        try:
            doc_ast = self.doc_renderer.render_to_ast(report)
            doc_append_text = self.doc_renderer.render_for_doc_append(report)
            
            doc_deep_link = self.email_renderer.get_deep_link_url(
                product_id=report.product_id,
                iso_week=report.iso_week,
                custom_doc_id=target_doc_id,
            )
            
            # If custom subject/body are not provided, render defaults
            if not custom_subject or not custom_body:
                default_email = self.email_renderer.render_email(
                    report=report,
                    doc_deep_link=doc_deep_link,
                    custom_recipients=target_recipients,
                )
                subject = custom_subject or default_email.subject
                body = custom_body or default_email.body_html or default_email.body_text
                is_html = True if custom_body else bool(default_email.body_html)
            else:
                subject = custom_subject
                body = custom_body
                is_html = True # Assume custom body is HTML capable
                
                # Reconstruct payload object to pass back
                default_email = EmailPayload(
                    recipient_list=target_recipients,
                    subject=subject,
                    body_text=body,
                    body_html=body,
                    deep_link_url=doc_deep_link,
                )

            doc_response = None
            draft_response = None

            # Append to Google Doc
            if self.google_client and self.google_client.is_available:
                doc_response = self.google_client.append_to_doc(doc_id=target_doc_id, content=doc_append_text)
            else:
                doc_response = self.mcp_client.append_to_doc(doc_id=target_doc_id, content=doc_append_text)
            doc_status = "appended"

            # Deliver or Draft Email
            if send_email:
                if self.google_client and self.google_client.is_available:
                    draft_response = self.google_client.send_email(
                        recipients=target_recipients, subject=subject, body=body, is_html=is_html
                    )
                else:
                    draft_response = self.mcp_client.send_email(
                        to=target_recipients, subject=subject, body=body
                    )
                draft_status = "sent"
            else:
                if self.google_client and self.google_client.is_available:
                    draft_response = self.google_client.create_email_draft(
                        recipients=target_recipients, subject=subject, body=body, is_html=is_html
                    )
                else:
                    draft_response = self.mcp_client.create_email_draft(
                        to=target_recipients, subject=subject, body=body
                    )
                draft_status = "created"

            # Record audit
            run_rec = RunRecord(
                run_id=run_id,
                product_id=report.product_id,
                iso_week=report.iso_week,
                reviews_count=report.total_reviews_analyzed,
                themes_count=len(report.themes),
                avg_rating=report.average_rating,
                doc_id=target_doc_id,
                doc_status=doc_status,
                draft_id=draft_response.get("draft_id") if draft_response else None,
                draft_status=draft_status,
                error_message=None,
            )
            self.idempotency_store.record_run(run_rec)

            return OrchestrationResult(
                run_id=run_id, product_id=report.product_id, iso_week=report.iso_week,
                status="success", is_dry_run=False, report=report, doc_ast=doc_ast,
                email_payload=default_email, doc_response=doc_response, draft_response=draft_response,
            )
        except Exception as e:
            logger.exception(f"Publishing failed: {e}")
            self.idempotency_store.record_run(RunRecord(
                run_id=run_id, product_id=report.product_id, iso_week=report.iso_week,
                reviews_count=report.total_reviews_analyzed, themes_count=len(report.themes),
                avg_rating=report.average_rating, doc_id=target_doc_id,
                doc_status="failed", draft_status="failed", error_message=str(e),
            ))
            raise
