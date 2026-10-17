"""Executive Email Renderer for Weekly Product Review Pulse."""

import html
import logging
from datetime import datetime
from typing import List, Optional
import os
from google import genai

from src.models.report import EmailPayload, ThemeInsight, WeeklyPulseReport
from src.utils.config_loader import RenderingConfig, get_product, load_settings

logger = logging.getLogger(__name__)


class EmailRenderer:
    """Renders high-impact executive email teaser payloads (HTML & Plain Text)."""

    def __init__(self, config: Optional[RenderingConfig] = None):
        settings = load_settings()
        self.config = config or settings.rendering
        self._gemini_client = None
        self._model_name = "gemini-2.0-flash"
        self._init_llm()

    def _init_llm(self):
        # Formatting uses deterministic templates by default: an LLM rewriting the
        # report could change numbers, and each call spends scarce free-tier quota.
        if os.getenv("RENDER_WITH_LLM", "false").lower() != "true":
            return
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and api_key != "your_gemini_api_key_here":
            try:
                self._gemini_client = genai.Client(api_key=api_key)
                self._model_name = os.getenv("LLM_MODEL", "gemini-2.0-flash")
            except Exception as e:
                logger.warning(f"Failed to init Gemini model in EmailRenderer: {e}")

    def get_deep_link_url(self, product_id: str, iso_week: str, custom_doc_id: Optional[str] = None) -> str:
        """Constructs direct Google Docs anchor URL."""
        clean_week = iso_week.replace("-", "_").lower()
        anchor_id = f"h.{product_id.lower()}_{clean_week}"
        
        doc_id = custom_doc_id
        if not doc_id:
            try:
                doc_id = get_product(product_id).google_doc_id
            except Exception:
                doc_id = "DOC_ID_PLACEHOLDER"

        return f"https://docs.google.com/document/d/{doc_id}/edit#heading={anchor_id}"

    def get_recipients(self, product_id: str) -> List[str]:
        """Retrieves configured recipient distribution list."""
        try:
            return get_product(product_id).recipients
        except Exception:
            return ["product-leads@example.com"]

    def render_email(
        self,
        report: WeeklyPulseReport,
        doc_deep_link: Optional[str] = None,
        custom_recipients: Optional[List[str]] = None,
        is_draft: bool = True,
    ) -> EmailPayload:
        """Generates an executive EmailPayload with HTML and plain-text formats."""
        deep_link = doc_deep_link or self.get_deep_link_url(report.product_id, report.iso_week)
        recipients = custom_recipients or self.get_recipients(report.product_id)

        subject = (
            f"[{report.product_display_name} Pulse] {report.iso_week}: "
            f"{len(report.themes)} Key Customer Themes & Action Plan"
        )

        body_html = self._render_html(report, deep_link)
        body_text = self._render_plain_text(report, deep_link)

        return EmailPayload(
            recipient_list=recipients,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            deep_link_url=deep_link,
            is_draft=is_draft,
        )

    def _render_html(self, report: WeeklyPulseReport, deep_link: str) -> str:
        """Constructs a responsive, modern HTML email template with inline styles."""
        start_str = report.start_date.strftime("%b %d, %Y") if isinstance(report.start_date, datetime) else str(report.start_date)
        end_str = report.end_date.strftime("%b %d, %Y") if isinstance(report.end_date, datetime) else str(report.end_date)
        
        # Build theme cards
        theme_cards_html = []
        for idx, theme in enumerate(report.themes, start=1):
            severity_bg, severity_fg = self._get_severity_colors(theme.severity_level)
            
            quotes_preview_html = ""
            if theme.verified_quotes:
                top_q = theme.verified_quotes[0]
                q_text = html.escape(top_q.quote_text[:180] + ("..." if len(top_q.quote_text) > 180 else ""))
                stars = "★" * top_q.score + "☆" * (5 - top_q.score)
                quotes_preview_html = f"""
                <div style="margin-top: 10px; padding: 10px 14px; background-color: #f8fafc; border-left: 3px solid #6366f1; border-radius: 4px; font-size: 13px; color: #334155; font-style: italic;">
                  "{q_text}"
                  <div style="margin-top: 4px; font-size: 11px; color: #64748b; font-style: normal; font-weight: 600;">
                    {stars} ({top_q.score}/5) &bull; Verified Review ({top_q.thumbs_up_count} likes)
                  </div>
                </div>
                """

            primary_action = (
                theme.actions.product_roadmap
                or theme.actions.engineering_infra
                or theme.actions.support_ops
                or "Review detailed breakdown in Google Doc."
            )

            theme_cards_html.append(f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
              <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <div style="font-size: 15px; font-weight: 700; color: #0f172a;">
                  {idx}. {html.escape(theme.title)}
                </div>
                <span style="background-color: {severity_bg}; color: {severity_fg}; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 12px; text-transform: uppercase; letter-spacing: 0.5px;">
                  {theme.severity_level}
                </span>
              </div>
              <div style="font-size: 13px; color: #475569; line-height: 1.5; margin-bottom: 8px;">
                <strong style="color: #1e293b;">Root Cause:</strong> {html.escape(theme.root_cause)}
              </div>
              <div style="font-size: 12px; color: #64748b; margin-bottom: 10px;">
                <strong>Volume:</strong> {theme.review_count} reviews ({theme.review_count / max(report.total_reviews_analyzed, 1) * 100:.1f}%) &bull; 
                <strong>Avg Rating:</strong> {theme.avg_score:.2f}★ &bull; 
                <strong>Impact Score:</strong> {theme.impact_score:.1f}
              </div>
              {quotes_preview_html}
              <div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed #e2e8f0; font-size: 12px; color: #0369a1;">
                <strong>⚡ Key Action:</strong> {html.escape(primary_action)}
              </div>
            </div>
            """)

        themes_rendered = "\n".join(theme_cards_html)

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>[{html.escape(report.product_display_name)} Pulse] {html.escape(report.iso_week)}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #0f172a; -webkit-font-smoothing: antialiased;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 24px 0;">
    <tr>
      <td align="center">
        <!-- Container Table -->
        <table width="600" border="0" cellspacing="0" cellpadding="0" style="width: 100%; max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05);">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 28px 24px; color: #ffffff;">
              <div style="font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: #38bdf8; margin-bottom: 6px;">
                WEEKLY CUSTOMER INTELLIGENCE PULSE
              </div>
              <div style="font-size: 22px; font-weight: 800; color: #ffffff; line-height: 1.2;">
                {html.escape(report.product_display_name)} — {html.escape(report.iso_week)}
              </div>
              <div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">
                Rolling Review Window: {start_str} – {end_str}
              </div>
            </td>
          </tr>

          <!-- KPI Summary Cards Grid -->
          <tr>
            <td style="padding: 20px 24px; background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <!-- Card 1: Reviews Analyzed -->
                  <td width="33%" align="center" style="padding: 10px; background-color: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0;">
                    <div style="font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase;">Analyzed</div>
                    <div style="font-size: 20px; font-weight: 800; color: #0f172a; margin-top: 2px;">{report.total_reviews_analyzed:,}</div>
                    <div style="font-size: 11px; color: #10b981; margin-top: 2px;">Reviews</div>
                  </td>
                  <td width="10">&nbsp;</td>
                  <!-- Card 2: Average Rating -->
                  <td width="33%" align="center" style="padding: 10px; background-color: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0;">
                    <div style="font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase;">Avg Rating</div>
                    <div style="font-size: 20px; font-weight: 800; color: #0f172a; margin-top: 2px;">{report.average_rating:.2f}★</div>
                    <div style="font-size: 11px; color: #f59e0b; margin-top: 2px;">Play Store</div>
                  </td>
                  <td width="10">&nbsp;</td>
                  <!-- Card 3: Negative % -->
                  <td width="33%" align="center" style="padding: 10px; background-color: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0;">
                    <div style="font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase;">Negative</div>
                    <div style="font-size: 20px; font-weight: 800; color: {'#ef4444' if report.negative_review_percentage > 25 else '#0f172a'}; margin-top: 2px;">{report.negative_review_percentage:.1f}%</div>
                    <div style="font-size: 11px; color: #64748b; margin-top: 2px;">1–2 Star Share</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Section: Top Themes -->
          <tr>
            <td style="padding: 24px 24px 12px 24px;">
              <div style="font-size: 16px; font-weight: 700; color: #0f172a; margin-bottom: 14px; display: flex; align-items: center;">
                🔥 Top Customer Themes & Critical Friction Points
              </div>
              {themes_rendered}
            </td>
          </tr>

          <!-- Call To Action Button -->
          <tr>
            <td align="center" style="padding: 16px 24px 28px 24px;">
              <table border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td align="center" style="background-color: #2563eb; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(37,99,235,0.3);">
                    <a href="{deep_link}" target="_blank" style="display: inline-block; padding: 14px 28px; font-size: 15px; font-weight: 700; color: #ffffff; text-decoration: none; border-radius: 8px; letter-spacing: 0.2px;">
                      Open Full Section in Google Docs &rarr;
                    </a>
                  </td>
                </tr>
              </table>
              <div style="font-size: 12px; color: #64748b; margin-top: 10px;">
                Direct deep link: <a href="{deep_link}" style="color: #2563eb; text-decoration: underline;">{deep_link}</a>
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 18px 24px; text-align: center;">
              <div style="font-size: 12px; color: #64748b; line-height: 1.5;">
                This automated report was generated by <strong>Weekly Product Review Pulse Agent</strong>.<br>
                All quotes are verified against authentic Google Play Store reviews with strict PII redaction.
              </div>
              <div style="font-size: 11px; color: #94a3b8; margin-top: 8px;">
                Generated at {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')} &bull; Confidential & Internal Only
              </div>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
        if self._gemini_client:
            prompt = f"""Format the following Weekly Pulse Report data into a responsive, modern HTML email template for executives.
Data:
- Product: {report.product_display_name}
- Week: {report.iso_week}
- Reviews: {report.total_reviews_analyzed}, Avg Rating: {report.average_rating:.2f}
- Themes count: {len(report.themes)}

Include a Deep Link button at the bottom pointing to: {deep_link}

Make it look like a highly polished, styled HTML email teaser. Return only the raw HTML code (no markdown code blocks).
"""
            try:
                response = self._gemini_client.models.generate_content(
                    model=self._model_name,
                    contents=prompt,
                )
                content = response.text.strip()
                if content.startswith("```html"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                return content.strip()
            except Exception as e:
                logger.warning(f"Gemini email HTML rendering failed: {e}")

        return html_template

    def _render_plain_text(self, report: WeeklyPulseReport, deep_link: str) -> str:
        """Constructs a clean plain-text version for email clients that do not render HTML."""
        start_str = report.start_date.strftime("%b %d, %Y") if isinstance(report.start_date, datetime) else str(report.start_date)
        end_str = report.end_date.strftime("%b %d, %Y") if isinstance(report.end_date, datetime) else str(report.end_date)

        lines = [
            f"==================================================================",
            f"  WEEKLY CUSTOMER INTELLIGENCE PULSE: {report.product_display_name.upper()}",
            f"  Week: {report.iso_week} ({start_str} – {end_str})",
            f"==================================================================",
            "",
            "KEY METRICS SUMMARY:",
            f"  - Reviews in window:      {report.total_reviews_extracted:,} (used for themes: {report.total_reviews_analyzed:,})",
            f"  - Average Star Rating:    {report.average_rating:.2f} / 5.0",
            f"  - Negative Review Share:  {report.negative_review_percentage:.1f}%",
            f"  - Core Themes Extracted:  {len(report.themes)}",
            "",
            "------------------------------------------------------------------",
            "TOP CUSTOMER THEMES & ACTION ITEMS:",
            "------------------------------------------------------------------",
        ]

        for idx, theme in enumerate(report.themes, start=1):
            lines.append(f"\n[{idx}] {theme.title} ({theme.severity_level})")
            lines.append(f"    Root Cause: {theme.root_cause}")
            lines.append(f"    Volume: {theme.review_count} reviews | Avg Rating: {theme.avg_score:.2f}★ | Impact Score: {theme.impact_score:.2f}")
            
            if theme.verified_quotes:
                lines.append(f"    Sample Quote: \"{theme.verified_quotes[0].quote_text}\"")

            lines.append("    Strategic Actions:")
            if theme.actions.product_roadmap:
                lines.append(f"      * Product: {theme.actions.product_roadmap}")
            if theme.actions.support_ops:
                lines.append(f"      * Support: {theme.actions.support_ops}")
            if theme.actions.engineering_infra:
                lines.append(f"      * Eng/Infra: {theme.actions.engineering_infra}")

        lines.extend([
            "",
            "------------------------------------------------------------------",
            "VIEW FULL ANALYSIS & VERBATIM EVIDENCE IN GOOGLE DOCS:",
            f"--> {deep_link}",
            "------------------------------------------------------------------",
            "",
            f"Generated automatically at {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "Confidential & Internal Distribution Only.",
        ])

        return "\n".join(lines)

    def _get_severity_colors(self, severity: str) -> tuple:
        """Returns background and foreground hex colors for HTML severity badges."""
        sev = severity.upper()
        if sev == "CRITICAL":
            return "#fee2e2", "#991b1b"  # Light Red bg, Dark Red text
        elif sev == "HIGH":
            return "#ffedd5", "#9a3412"  # Light Orange bg, Dark Orange text
        elif sev == "MEDIUM":
            return "#e0f2fe", "#075985"  # Light Blue bg, Dark Blue text
        else:
            return "#dcfce7", "#166534"  # Light Green bg, Dark Green text
