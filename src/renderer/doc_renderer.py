"""Google Docs AST & Markdown Renderer for Weekly Product Review Pulse."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import os
from google import genai

from src.models.report import DocSectionAST, ThemeInsight, VerbatimQuote, WeeklyPulseReport
from src.utils.config_loader import RenderingConfig, get_product, load_settings

logger = logging.getLogger(__name__)


class DocRenderer:
    """Renders structured WeeklyPulseReport into Google Docs AST blocks and Markdown."""

    def __init__(self, config: Optional[RenderingConfig] = None):
        settings = load_settings()
        self.config = config or settings.rendering
        self._gemini_client = None
        self._model_name = "gemini-2.0-flash"
        self._init_llm()

    def _init_llm(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and api_key != "your_gemini_api_key_here":
            try:
                self._gemini_client = genai.Client(api_key=api_key)
                self._model_name = os.getenv("LLM_MODEL", "gemini-2.0-flash")
            except Exception as e:
                logger.warning(f"Failed to init Gemini model in DocRenderer: {e}")

    def get_anchor_id(self, product_id: str, iso_week: str) -> str:
        """Generates deterministic Google Docs heading/bookmark anchor ID."""
        clean_week = iso_week.replace("-", "_").lower()
        return f"h.{product_id.lower()}_{clean_week}"

    def get_doc_id(self, product_id: str) -> str:
        """Retrieves configured Google Doc ID for a product."""
        try:
            target = get_product(product_id)
            return target.google_doc_id
        except Exception:
            return "DOC_ID_NOT_CONFIGURED"

    def render_to_ast(
        self,
        report: WeeklyPulseReport,
        custom_anchor: Optional[str] = None,
        custom_doc_id: Optional[str] = None,
    ) -> DocSectionAST:
        """Compiles WeeklyPulseReport into structured DocSectionAST for MCP Google Docs tool."""
        anchor_id = custom_anchor or self.get_anchor_id(report.product_id, report.iso_week)
        doc_id = custom_doc_id or self.get_doc_id(report.product_id)

        start_str = report.start_date.strftime("%b %d, %Y") if isinstance(report.start_date, datetime) else str(report.start_date)
        end_str = report.end_date.strftime("%b %d, %Y") if isinstance(report.end_date, datetime) else str(report.end_date)
        
        section_heading = f"Week {report.iso_week} ({start_str} – {end_str}) — Customer Review Pulse"

        # Build high-level structured block commands for Google Docs MCP tool
        blocks: List[Dict[str, Any]] = []

        # 1. Section Header Block
        blocks.append({
            "type": "heading_1",
            "text": section_heading,
            "anchor_id": anchor_id,
            "metadata": {
                "product_id": report.product_id,
                "iso_week": report.iso_week,
            }
        })

        # 2. Executive KPI Summary Card Block
        kpi_data = {
            "total_reviews": report.total_reviews_analyzed,
            "average_rating": round(report.average_rating, 2),
            "negative_percentage": round(report.negative_review_percentage, 1),
            "themes_count": len(report.themes),
            "outlier_count": report.outlier_count,
            "delta_reviews": report.delta_reviews,
            "delta_rating": report.delta_rating,
        }
        blocks.append({
            "type": "kpi_summary",
            "title": "Executive Summary & Key Metrics",
            "metrics": kpi_data,
        })

        # 3. Theme Breakdown Sections
        for idx, theme in enumerate(report.themes, start=1):
            theme_block = self._build_theme_block(idx, theme)
            blocks.append(theme_block)

        # Build clean formatted text content ready for direct MCP Google Docs append
        append_content = self.render_for_doc_append(report)

        return DocSectionAST(
            document_id=doc_id,
            iso_week=report.iso_week,
            section_heading=section_heading,
            anchor_id=anchor_id,
            content=append_content,
            raw_blocks=blocks,
        )

    def _build_theme_block(self, index: int, theme: ThemeInsight) -> Dict[str, Any]:
        """Constructs a structured theme block with root cause, quotes, and action matrix."""
        quotes_data = []
        for q in theme.verified_quotes:
            quotes_data.append({
                "quote_text": q.quote_text,
                "review_id": q.review_id,
                "score": q.score,
                "stars": "★" * q.score + "☆" * (5 - q.score),
                "thumbs_up_count": q.thumbs_up_count,
                "verification_score": q.verification_score,
                "is_fallback": q.is_fallback,
            })

        return {
            "type": "theme_section",
            "theme_index": index,
            "theme_id": theme.theme_id,
            "title": theme.title,
            "severity": theme.severity_level,
            "root_cause": theme.root_cause,
            "metrics": {
                "impact_score": round(theme.impact_score, 2),
                "review_count": theme.review_count,
                "avg_score": round(theme.avg_score, 2),
            },
            "quotes": quotes_data,
            "actions": {
                "product_roadmap": theme.actions.product_roadmap or "Monitor for further user friction reports.",
                "support_ops": theme.actions.support_ops or "Follow standard response escalation protocols.",
                "engineering_infra": theme.actions.engineering_infra or "Verify telemetry metrics and error logs.",
            },
        }

    def render_to_markdown(self, report: WeeklyPulseReport) -> str:
        """Renders WeeklyPulseReport into a polished, GitHub-flavored Markdown document."""
        anchor_id = self.get_anchor_id(report.product_id, report.iso_week)
        start_str = report.start_date.strftime("%b %d, %Y") if isinstance(report.start_date, datetime) else str(report.start_date)
        end_str = report.end_date.strftime("%b %d, %Y") if isinstance(report.end_date, datetime) else str(report.end_date)

        if self._gemini_client:
            prompt = f"""Format the following Weekly Pulse Report data into a highly readable, executive-ready GitHub-flavored Markdown document.
Data:
- Product: {report.product_display_name} ({report.product_id})
- Week: {report.iso_week} ({start_str} to {end_str})
- Reviews: {report.total_reviews_analyzed}, Avg Rating: {report.average_rating:.2f}, Negative: {report.negative_review_percentage}%
- Themes count: {len(report.themes)}

Include an Executive KPI Snapshot table, and a Deep-Dive Themes & Action Matrix section.
Format it beautifully. Start with `# Week {report.iso_week} ({start_str} – {end_str}) — Customer Review Pulse <a id="{anchor_id}"></a>`
"""
            try:
                response = self._gemini_client.models.generate_content(
                    model=self._model_name,
                    contents=prompt,
                )
                return response.text.strip()
            except Exception as e:
                logger.warning(f"Gemini markdown rendering failed: {e}")
        
        # Fallback to programmatic rendering if Gemini fails
        lines: List[str] = []
        
        # Heading 1 with anchor
        lines.append(f"# Week {report.iso_week} ({start_str} – {end_str}) — Customer Review Pulse <a id=\"{anchor_id}\"></a>")
        lines.append("")
        lines.append(f"**Target Product:** {report.product_display_name} (`{report.product_id}`)  ")
        lines.append(f"**Generated At:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}  ")
        lines.append(f"**Canonical Anchor ID:** `{anchor_id}`")
        lines.append("")

        # KPI Summary Table
        lines.append("## 📊 Executive KPI Snapshot")
        lines.append("")
        lines.append("| Metric | Value | Context / Delta |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(f"| **Total Reviews Analyzed** | `{report.total_reviews_analyzed:,}` | Rolling Window |")
        lines.append(f"| **Average Star Rating** | `{report.average_rating:.2f} / 5.0` | ⭐ {'★' * int(round(report.average_rating))}{'☆' * (5 - int(round(report.average_rating)))} |")
        lines.append(f"| **Negative Review Share (1–2★)** | `{report.negative_review_percentage:.1f}%` | Critical Attention |")
        lines.append(f"| **Identified Core Themes** | `{len(report.themes)}` | Extracted via HDBSCAN + LLM |")
        lines.append(f"| **Unclustered Outliers** | `{report.outlier_count}` | Isolated noise |")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Themes Breakdown
        lines.append("## 🔍 Deep-Dive Themes & Action Matrix")
        lines.append("")

        for idx, theme in enumerate(report.themes, start=1):
            severity_badge = self._get_severity_badge_md(theme.severity_level)
            lines.append(f"### {idx}. {theme.title} {severity_badge}")
            lines.append("")
            lines.append(f"> **Root Cause:** {theme.root_cause}")
            lines.append("")
            lines.append(f"- **Cluster Volume:** `{theme.review_count} reviews` ({theme.review_count / max(report.total_reviews_analyzed, 1) * 100:.1f}% of total)")
            lines.append(f"- **Average Rating:** `{theme.avg_score:.2f} / 5.0` | **Impact Score:** `{theme.impact_score:.2f}`")
            lines.append("")

            # Verbatim Quotes
            lines.append("#### 🗣️ Verified Customer Quotes (Ground-Truth)")
            if theme.verified_quotes:
                for q in theme.verified_quotes:
                    stars = "★" * q.score + "☆" * (5 - q.score)
                    fallback_flag = " *(Substituted verified quote)*" if q.is_fallback else ""
                    lines.append(f"> *\"{q.quote_text}\"*  ")
                    lines.append(f"> — **Rating:** `{stars} ({q.score}/5)` | **Review ID:** `{q.review_id}` | **Thumbs Up:** `{q.thumbs_up_count}` | **Match Confidence:** `{q.verification_score * 100:.0f}%`{fallback_flag}")
                    lines.append(">")
            else:
                lines.append("> *No specific verbatim quotes attached for this theme.*")
            lines.append("")

            # Action Plan Table
            lines.append("#### 🛠️ Cross-Functional Action Plan")
            lines.append("")
            lines.append("| Department / Function | Strategic Action Item |")
            lines.append("| :--- | :--- |")
            lines.append(f"| **🚀 Product Roadmap** | {theme.actions.product_roadmap or 'Monitor for further user friction reports.'} |")
            lines.append(f"| **🎧 Support Ops & Triage** | {theme.actions.support_ops or 'Follow standard response escalation protocols.'} |")
            lines.append(f"| **⚙️ Engineering & Infra** | {theme.actions.engineering_infra or 'Verify telemetry metrics and error logs.'} |")
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def render_for_doc_append(self, report: WeeklyPulseReport) -> str:
        """Renders WeeklyPulseReport into a clean, structured plain-text format for direct Google Docs append."""
        anchor_id = self.get_anchor_id(report.product_id, report.iso_week)
        start_str = report.start_date.strftime("%b %d, %Y") if isinstance(report.start_date, datetime) else str(report.start_date)
        end_str = report.end_date.strftime("%b %d, %Y") if isinstance(report.end_date, datetime) else str(report.end_date)

        lines: List[str] = []
        divider = "=" * 80
        sub_divider = "-" * 80

        lines.append(divider)
        lines.append(f"WEEK {report.iso_week} ({start_str} - {end_str}) -- CUSTOMER REVIEW PULSE")
        lines.append(divider)
        lines.append(f"Product: {report.product_display_name} ({report.product_id})")
        lines.append(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"Section Anchor: #{anchor_id}")
        lines.append("")

        # Executive KPI Snapshot
        lines.append("EXECUTIVE KPI SNAPSHOT")
        lines.append(sub_divider)
        lines.append(f"- Total Reviews Analyzed: {report.total_reviews_analyzed:,}")
        rating_stars = "★" * int(round(report.average_rating)) + "☆" * (5 - int(round(report.average_rating)))
        lines.append(f"- Average Star Rating: {report.average_rating:.2f} / 5.0 ({rating_stars})")
        lines.append(f"- Negative Review Share (1-2 Stars): {report.negative_review_percentage:.1f}%")
        lines.append(f"- Core Themes Identified: {len(report.themes)}")
        lines.append(f"- Outlier / Isolated Reviews: {report.outlier_count}")
        if report.delta_reviews is not None:
            lines.append(f"- Review Volume Delta: {report.delta_reviews:+d}")
        if report.delta_rating is not None:
            lines.append(f"- Rating Delta: {report.delta_rating:+.2f}")
        lines.append("")

        # Deep-Dive Themes & Action Matrix
        lines.append("DEEP-DIVE THEMES & ACTION MATRIX")
        lines.append(sub_divider)
        lines.append("")

        for idx, theme in enumerate(report.themes, start=1):
            severity_str = f"[{theme.severity_level.upper()}]"
            lines.append(f"{idx}. {theme.title.upper()} {severity_str}")
            lines.append(f"   Root Cause: {theme.root_cause}")
            theme_pct = (theme.review_count / max(report.total_reviews_analyzed, 1)) * 100
            lines.append(f"   Volume: {theme.review_count} reviews ({theme_pct:.1f}%) | Impact Score: {theme.impact_score:.2f} | Avg Rating: {theme.avg_score:.2f}/5.0")
            lines.append("")

            # Verified Quotes
            lines.append("   Verified Customer Quotes:")
            if theme.verified_quotes:
                for q in theme.verified_quotes:
                    stars = "★" * q.score + "☆" * (5 - q.score)
                    fallback_flag = " [Substituted verified quote]" if q.is_fallback else ""
                    lines.append(f'   - "{q.quote_text}"')
                    lines.append(f'     Rating: {stars} ({q.score}/5) | Review ID: {q.review_id} | Thumbs Up: {q.thumbs_up_count} | Match: {q.verification_score * 100:.0f}%{fallback_flag}')
            else:
                lines.append("   - No specific verbatim quotes attached for this theme.")
            lines.append("")

            # Action Plan
            lines.append("   Cross-Functional Action Plan:")
            lines.append(f"   * Product Roadmap: {theme.actions.product_roadmap or 'Monitor for further user friction reports.'}")
            lines.append(f"   * Support Ops & Triage: {theme.actions.support_ops or 'Follow standard response escalation protocols.'}")
            lines.append(f"   * Engineering & Infra: {theme.actions.engineering_infra or 'Verify telemetry metrics and error logs.'}")
            lines.append("")
            if idx < len(report.themes):
                lines.append(sub_divider)
                lines.append("")

        lines.append(divider)
        lines.append("")
        return "\n".join(lines)

    def render_to_plain_text(self, report: WeeklyPulseReport) -> str:
        """Generates structured plain-text representation of the report."""
        return self.render_for_doc_append(report)

    def _get_severity_badge_md(self, severity: str) -> str:
        """Returns Markdown badge notation for severity."""
        sev = severity.upper()
        if sev == "CRITICAL":
            return "`🚨 CRITICAL`"
        elif sev == "HIGH":
            return "`⚠️ HIGH`"
        elif sev == "MEDIUM":
            return "`🔷 MEDIUM`"
        else:
            return "`🟢 LOW`"
