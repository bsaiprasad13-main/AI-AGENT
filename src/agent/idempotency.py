"""SQLite-backed Idempotency and Audit Store for Pipeline Runs.

Records weekly run executions, preventing duplicate publishes for the same
product and ISO week, and maintains a persistent audit log of MCP interactions.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
from pydantic import BaseModel, Field


class RunRecord(BaseModel):
    """Pydantic model representing a completed or attempted pipeline execution."""
    run_id: str
    product_id: str
    iso_week: str
    reviews_count: int = 0
    themes_count: int = 0
    avg_rating: float = 0.0
    doc_id: Optional[str] = None
    doc_status: str = "pending"  # "appended", "dry_run", "skipped", "failed"
    draft_id: Optional[str] = None
    draft_status: str = "pending"  # "created", "dry_run", "skipped", "failed"
    error_message: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class IdempotencyStore:
    """Manages SQLite database for idempotent execution and run auditing."""

    def __init__(self, db_path: Optional[str] = "data/audit.db"):
        self.db_path = Path(db_path) if db_path else Path("data/audit.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager that safely opens and closes SQLite connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Creates the audit table and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS run_audit (
                    run_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    iso_week TEXT NOT NULL,
                    reviews_count INTEGER DEFAULT 0,
                    themes_count INTEGER DEFAULT 0,
                    avg_rating REAL DEFAULT 0.0,
                    doc_id TEXT,
                    doc_status TEXT NOT NULL,
                    draft_id TEXT,
                    draft_status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_product_week 
                ON run_audit(product_id, iso_week)
            """)

    def has_published_for_week(self, product_id: str, iso_week: str) -> bool:
        """Checks if a successful document append has already occurred for this product & week."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM run_audit
                WHERE product_id = ? AND iso_week = ? AND doc_status = 'appended'
                """,
                (product_id, iso_week),
            )
            row = cursor.fetchone()
            return bool(row["cnt"] > 0 if row else False)

    def record_run(self, record: RunRecord) -> None:
        """Inserts or replaces a run execution record in the audit database."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO run_audit (
                    run_id, product_id, iso_week, reviews_count,
                    themes_count, avg_rating, doc_id, doc_status,
                    draft_id, draft_status, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.product_id,
                    record.iso_week,
                    record.reviews_count,
                    record.themes_count,
                    record.avg_rating,
                    record.doc_id,
                    record.doc_status,
                    record.draft_id,
                    record.draft_status,
                    record.error_message,
                    record.created_at,
                ),
            )

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        """Retrieves a single run record by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM run_audit WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return RunRecord(**dict(row))

    def list_history(self, product_id: Optional[str] = None, limit: int = 50) -> List[RunRecord]:
        """Retrieves execution history, optionally filtered by product."""
        with self._get_connection() as conn:
            if product_id:
                cursor = conn.execute(
                    "SELECT * FROM run_audit WHERE product_id = ? ORDER BY created_at DESC LIMIT ?",
                    (product_id, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM run_audit ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            return [RunRecord(**dict(row)) for row in cursor.fetchall()]
