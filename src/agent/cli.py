"""Command-line interface (CLI) for Weekly Product Review Pulse Agent."""

import argparse
import logging
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.agent.idempotency import IdempotencyStore
from src.agent.mcp_client import MCPClient, MCPClientError
from src.agent.orchestrator import ReviewPulseOrchestrator
from src.utils.config_loader import load_products, load_settings


def setup_logging(verbose: bool = False) -> None:
    """Configures application logging format and level."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_run(args: argparse.Namespace) -> int:
    """Executes the pipeline run command."""
    settings = load_settings()

    # Override MCP API Key or URL if supplied on CLI
    if args.api_key:
        settings.mcp.api_key = args.api_key
    if args.server_url:
        settings.mcp.server_url = args.server_url

    mcp_client = MCPClient(config=settings.mcp)
    orchestrator = ReviewPulseOrchestrator(settings=settings, mcp_client=mcp_client)

    is_dry_run = not args.publish

    print("\n" + "=" * 70)
    print(f"🚀 WEEKLY PRODUCT REVIEW PULSE: {args.product.upper()}")
    print(f"Mode: {'DRY RUN (Preview Only)' if is_dry_run else 'LIVE PUBLISH (Google Docs & Gmail)'}")
    print(f"Rolling Window: {args.weeks or settings.ingestion.default_rolling_window_weeks} weeks")
    print(f"MCP Server: {settings.mcp.server_url}")
    print("=" * 70 + "\n")

    result = orchestrator.run(
        product_id=args.product,
        weeks=args.weeks,
        dry_run=is_dry_run,
        force=args.force,
        send_email=args.send_email,
        custom_doc_id=args.doc_id,
        custom_recipients=[r.strip() for r in args.recipients.split(",") if r.strip()] if args.recipients else None,
    )

    if result.status == "success":
        print("\n" + "=" * 70)
        print("✅ [RUN COMPLETED SUCCESSFULLY]")
        print("=" * 70)
        print(f"Run ID:        {result.run_id}")
        print(f"ISO Week:      {result.iso_week}")
        print(f"Reviews Count: {result.report.total_reviews_analyzed if result.report else 0}")
        print(f"Themes Count:  {len(result.report.themes) if result.report else 0}")
        print(f"Avg Rating:    {result.report.average_rating if result.report else 0}/5.0")
        print(f"Negative %:    {result.report.negative_review_percentage if result.report else 0}%")

        if result.report and result.report.themes:
            print("\n📋 Top Themes:")
            for i, theme in enumerate(result.report.themes, 1):
                print(f"  {i}. [{theme.severity_level}] {theme.title} (Impact: {theme.impact_score})")

        if is_dry_run:
            print("\n💡 NOTE: This was a dry run. To publish to Google Docs & Gmail via MCP, pass `--publish`.")
        else:
            print("\n📬 Live Publishing Summary:")
            print(f"  - Google Doc Response: {result.doc_response}")
            print(f"  - Gmail Draft Response: {result.draft_response}")

        return 0

    elif result.status == "skipped_idempotent":
        print(f"\n⚠️  [SKIPPED]: {result.error_message}")
        return 0

    else:
        print(f"\n❌ [RUN FAILED]: {result.error_message}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Checks MCP server connectivity and tool endpoints."""
    settings = load_settings()
    if args.api_key:
        settings.mcp.api_key = args.api_key
    if args.server_url:
        settings.mcp.server_url = args.server_url

    client = MCPClient(config=settings.mcp)
    print(f"Connecting to MCP Server at: {client.server_url} ...")

    try:
        status = client.get_server_status()
        print("\n✅ MCP Server is ONLINE and reachable!")
        print(f"Server Name:      {status.get('server')}")
        print(f"Version:          {status.get('version')}")
        print(f"Status:           {status.get('status')}")
        print(f"Mode:             {status.get('mode')}")
        print(f"API Key Required: {status.get('api_key_required')}")
        print("\nAvailable Tools:")
        for tool in status.get("tools", []):
            print(f"  - {tool.get('name')}: {tool.get('endpoint')} ({tool.get('method')})")
            print(f"    {tool.get('description')}")
        return 0
    except MCPClientError as e:
        print(f"\n❌ MCP Server connection failed: {e}")
        return 1


def cmd_history(args: argparse.Namespace) -> int:
    """Displays audit run history."""
    settings = load_settings()
    store = IdempotencyStore(db_path=settings.storage.audit_db_path)
    records = store.list_history(product_id=args.product, limit=args.limit)

    if not records:
        print(f"No run history found for product '{args.product or 'all'}'.")
        return 0

    print("\n" + "=" * 90)
    print(f"{'Run ID':<16} {'Product':<10} {'Week':<10} {'Reviews':<8} {'Doc Status':<12} {'Draft Status':<12} {'Timestamp':<20}")
    print("=" * 90)
    for r in records:
        print(f"{r.run_id:<16} {r.product_id:<10} {r.iso_week:<10} {r.reviews_count:<8} {r.doc_status:<12} {r.draft_status:<12} {r.created_at[:19]:<20}")
    print("=" * 90 + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Constructs the argument parser for CLI commands."""
    parser = argparse.ArgumentParser(
        prog="pulse-agent",
        description="Weekly Product Review Pulse CLI — AI Agent for Google Play Store Reviews",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. run command
    run_p = subparsers.add_parser("run", help="Execute review pulse analysis for a target product")
    run_p.add_argument("--product", "-p", default="groww", help="Product target ID (default: groww)")
    run_p.add_argument("--weeks", "-w", type=int, default=None, help="Rolling window in weeks (default: 10)")
    run_p.add_argument("--publish", action="store_true", help="Publish directly to Google Docs and Gmail draft via MCP")
    run_p.add_argument("--send-email", action="store_true", help="Deliver email directly to inboxes instead of creating a draft")
    run_p.add_argument("--force", "-f", action="store_true", help="Force execution even if ISO week was already published")
    run_p.add_argument("--doc-id", help="Override target Google Doc ID")
    run_p.add_argument("--recipients", help="Comma-separated recipient emails override")
    run_p.add_argument("--api-key", help="Override MCP Server API Key")
    run_p.add_argument("--server-url", help="Override MCP Server URL")

    # 2. status command
    stat_p = subparsers.add_parser("status", help="Verify MCP Server connectivity and tool discovery")
    stat_p.add_argument("--api-key", help="MCP Server API Key")
    stat_p.add_argument("--server-url", help="MCP Server URL")

    # 3. history command
    hist_p = subparsers.add_parser("history", help="Inspect past audit run logs")
    hist_p.add_argument("--product", "-p", default=None, help="Filter by product target ID")
    hist_p.add_argument("--limit", "-l", type=int, default=20, help="Max records to display")

    return parser


def main() -> None:
    """CLI Entry point."""
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "run":
        sys.exit(cmd_run(args))
    elif args.command == "status":
        sys.exit(cmd_status(args))
    elif args.command == "history":
        sys.exit(cmd_history(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
