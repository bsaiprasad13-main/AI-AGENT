"""Phase 5 Demo Script: Renders Doc AST, Markdown, and Email Previews from weekly report."""

import json
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.models.report import WeeklyPulseReport
from src.renderer.doc_renderer import DocRenderer
from src.renderer.email_renderer import EmailRenderer


def main():
    root_dir = Path(__file__).resolve().parent.parent
    report_path = root_dir / "data" / "weekly_pulse_report_groww.json"

    if not report_path.exists():
        print(f"Report file not found at {report_path}. Run Phase 3 analysis first.")
        return

    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    report = WeeklyPulseReport.model_validate(data)
    print(f"Loaded report: {report.product_display_name} - {report.iso_week}")
    print(f"Total reviews: {report.total_reviews_analyzed}, Themes: {len(report.themes)}")

    # 1. Render Google Docs Append Content, AST & Markdown
    doc_renderer = DocRenderer()
    ast = doc_renderer.render_to_ast(report)
    md_content = doc_renderer.render_to_markdown(report)
    append_text = doc_renderer.render_for_doc_append(report)

    append_path = root_dir / "data" / "doc_append_content.txt"
    with open(append_path, "w", encoding="utf-8") as f:
        f.write(append_text)
    print(f"[OK] Google Docs direct append payload saved to: {append_path}")

    ast_path = root_dir / "data" / "doc_section_ast.json"
    with open(ast_path, "w", encoding="utf-8") as f:
        f.write(ast.model_dump_json(indent=2))
    print(f"[OK] Google Docs AST saved to: {ast_path}")

    md_path = root_dir / "data" / "doc_preview.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[OK] Google Docs Markdown preview saved to: {md_path}")

    # 2. Render Email HTML & Plain Text
    email_renderer = EmailRenderer()
    email_payload = email_renderer.render_email(report)

    html_path = root_dir / "data" / "email_preview.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(email_payload.body_html)
    print(f"[OK] Email HTML preview saved to: {html_path}")

    txt_path = root_dir / "data" / "email_preview.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(email_payload.body_text)
    print(f"[OK] Email Plain Text preview saved to: {txt_path}")

    print("\n--- Summary of Rendered Artifacts ---")
    print(f"Subject: {email_payload.subject}")
    print(f"Anchor ID: {ast.anchor_id}")
    print(f"Deep Link: {email_payload.deep_link_url}")
    print(f"Recipients: {email_payload.recipient_list}")


if __name__ == "__main__":
    main()
