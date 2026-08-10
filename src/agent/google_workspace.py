"""Direct Google Workspace Client using local OAuth credentials (token.json).

Provides secure, private access to Google Docs and Gmail without requiring
documents to be made public on the web.
"""

from __future__ import annotations

import base64
import json
import logging
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import google.auth.transport.requests
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

logger = logging.getLogger(__name__)


class GoogleWorkspaceClient:
    """Direct Google Docs and Gmail client authenticated via OAuth token.json."""

    def __init__(self, token_path: Optional[str] = "token.json"):
        self.token_path = Path(token_path) if token_path else Path("token.json")
        self._credentials: Optional[Credentials] = None
        self._docs_service = None
        self._gmail_service = None
        self._init_credentials()

    def _init_credentials(self) -> None:
        """Loads and refreshes OAuth credentials from token.json if available."""
        if not GOOGLE_API_AVAILABLE:
            logger.warning("google-api-python-client or google-auth not installed.")
            return

        if not self.token_path.exists():
            logger.debug(f"OAuth credentials file '{self.token_path}' not found.")
            return

        try:
            self._credentials = Credentials.from_authorized_user_file(str(self.token_path))
            if self._credentials.expired and self._credentials.refresh_token:
                logger.info("Refreshing expired Google OAuth access token...")
                request = google.auth.transport.requests.Request()
                self._credentials.refresh(request)
                # Save refreshed token back to disk
                with open(self.token_path, "w", encoding="utf-8") as f:
                    f.write(self._credentials.to_json())
                logger.info("Google OAuth token refreshed and saved.")
            
            self._docs_service = build("docs", "v1", credentials=self._credentials)
            self._gmail_service = build("gmail", "v1", credentials=self._credentials)
            logger.info("Direct Google Workspace client initialized successfully.")
        except Exception as e:
            logger.warning(f"Failed to initialize direct Google credentials: {e}")
            self._credentials = None

    @property
    def is_available(self) -> bool:
        """Returns True if local OAuth credentials are valid and active."""
        return self._credentials is not None and self._docs_service is not None

    def append_to_doc(self, doc_id: str, content: str) -> Dict[str, Any]:
        """Appends plaintext markdown content to the end of a private Google Document.

        Args:
            doc_id: Target Google Doc ID.
            content: Text content to append.

        Returns:
            Dictionary containing execution status and metadata.
        """
        if not self.is_available:
            raise RuntimeError("Google Workspace client is not authenticated with token.json.")

        logger.info(f"Appending content directly to Google Doc '{doc_id}' via OAuth...")

        # 1. Fetch document metadata to determine insertion index at EOF
        doc = self._docs_service.documents().get(documentId=doc_id).execute()
        body = doc.get("body", {})
        doc_content = body.get("content", [])
        
        insert_index = 1
        if doc_content:
            end_index = doc_content[-1].get("endIndex", 1)
            insert_index = max(1, end_index - 1)

        # 2. Append content at document end
        text_to_insert = f"\n\n{content}\n"
        requests = [
            {
                "insertText": {
                    "location": {"index": insert_index},
                    "text": text_to_insert,
                }
            }
        ]

        result = (
            self._docs_service.documents()
            .batchUpdate(documentId=doc_id, body={"requests": requests})
            .execute()
        )

        logger.info(f"Successfully appended {len(content)} characters to Google Doc '{doc_id}'.")
        return {
            "status": "success",
            "doc_id": doc_id,
            "document_title": doc.get("title", ""),
            "appended_chars": len(content),
            "result": result,
            "provider": "direct_oauth",
        }

    def create_email_draft(
        self,
        recipients: List[str],
        subject: str,
        body: str,
        is_html: bool = True,
    ) -> Dict[str, Any]:
        """Creates a draft email in the user's Gmail account.

        Args:
            recipients: List of recipient email addresses.
            subject: Subject line.
            body: Body content (HTML or plain text).
            is_html: If True, formats as text/html.

        Returns:
            Dictionary containing draft ID and execution status.
        """
        if not self.is_available:
            raise RuntimeError("Google Workspace client is not authenticated with token.json.")

        logger.info(f"Creating Gmail draft: '{subject}' for {recipients} via OAuth...")

        mime_subtype = "html" if is_html else "plain"
        message = MIMEText(body, mime_subtype, "utf-8")
        message["to"] = ", ".join(recipients) if isinstance(recipients, list) else recipients
        message["subject"] = subject

        raw_encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        draft_payload = {"message": {"raw": raw_encoded}}

        draft = (
            self._gmail_service.users()
            .drafts()
            .create(userId="me", body=draft_payload)
            .execute()
        )

        draft_id = draft.get("id", "")
        logger.info(f"Successfully created Gmail draft (ID: {draft_id}).")
        return {
            "status": "success",
            "draft_id": draft_id,
            "subject": subject,
            "recipients": recipients,
            "provider": "direct_oauth",
        }

    def send_email(
        self,
        recipients: List[str],
        subject: str,
        body: str,
        is_html: bool = True,
    ) -> Dict[str, Any]:
        """Sends an email directly to recipients via Gmail API.

        Args:
            recipients: List of recipient email addresses.
            subject: Subject line.
            body: Body content (HTML or plain text).
            is_html: If True, formats as text/html.

        Returns:
            Dictionary containing message ID and execution status.
        """
        if not self.is_available:
            raise RuntimeError("Google Workspace client is not authenticated with token.json.")

        logger.info(f"Sending email: '{subject}' to {recipients} via OAuth...")

        mime_subtype = "html" if is_html else "plain"
        message = MIMEText(body, mime_subtype, "utf-8")
        message["to"] = ", ".join(recipients) if isinstance(recipients, list) else recipients
        message["subject"] = subject

        raw_encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        send_payload = {"raw": raw_encoded}

        sent = (
            self._gmail_service.users()
            .messages()
            .send(userId="me", body=send_payload)
            .execute()
        )

        msg_id = sent.get("id", "")
        logger.info(f"Successfully sent email (Message ID: {msg_id}).")
        return {
            "status": "success",
            "message_id": msg_id,
            "subject": subject,
            "recipients": recipients,
            "provider": "direct_oauth",
        }
