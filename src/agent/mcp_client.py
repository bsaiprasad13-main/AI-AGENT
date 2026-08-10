"""MCP Client Interface for Google Docs & Gmail Cloud MCP Server.

Interacts with the headless-cloud MCP server at https://web-production-c16ea.up.railway.app
Exposes tools:
  - append_to_doc(doc_id, content) -> POST /append_to_doc
  - create_email_draft(to, subject, body) -> POST /create_email_draft
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Union

from src.utils.config_loader import MCPConfig, load_settings

logger = logging.getLogger(__name__)


class MCPClientError(Exception):
    """Base exception for MCP client errors."""
    pass


class MCPConnectionError(MCPClientError):
    """Raised when communication with the MCP server fails or times out."""
    pass


class MCPAuthenticationError(MCPClientError):
    """Raised when authentication with the MCP server fails (HTTP 401/403)."""
    pass


class MCPToolExecutionError(MCPClientError):
    """Raised when an MCP tool returns an error status or fails execution."""
    pass


class MCPClient:
    """HTTP Client adapter for the remote Google Docs & Gmail MCP Server."""

    def __init__(
        self,
        config: Optional[MCPConfig] = None,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        settings = load_settings()
        self.config = config or settings.mcp

        self.server_url = (
            server_url or self.config.server_url or "https://web-production-c16ea.up.railway.app"
        ).rstrip("/")
        self.api_key = api_key if api_key is not None else self.config.api_key
        self.timeout = timeout_seconds or self.config.timeout_seconds
        self.max_retries = self.config.max_retries
        self.retry_backoff = self.config.retry_backoff_seconds

    def _get_headers(self) -> Dict[str, str]:
        """Constructs request headers including optional auth headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ProductReviewAnalysisAgent/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        return headers

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Executes HTTP request with retry logic and error classification."""
        url = f"{self.server_url}/{endpoint.lstrip('/')}"
        headers = self._get_headers()
        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None

        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    url=url,
                    data=data_bytes,
                    headers=headers,
                    method=method.upper(),
                )

                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    status_code = response.getcode()
                    raw_body = response.read().decode("utf-8")

                    try:
                        parsed = json.loads(raw_body) if raw_body else {}
                    except json.JSONDecodeError:
                        parsed = {"raw_response": raw_body, "status_code": status_code}

                    if status_code >= 400:
                        raise MCPToolExecutionError(
                            f"MCP tool endpoint {endpoint} returned error status {status_code}: {raw_body}"
                        )

                    return parsed

            except urllib.error.HTTPError as e:
                status_code = e.code
                error_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
                logger.warning(
                    f"HTTP error {status_code} calling {url} (attempt {attempt}/{self.max_retries}): {error_body}"
                )

                if status_code in (401, 403):
                    raise MCPAuthenticationError(
                        f"Authentication failed for MCP server at {url} (HTTP {status_code}): {error_body}"
                    )

                if 400 <= status_code < 500:
                    # Client errors (e.g. 400 Bad Request, 422 Unprocessable) should not retry
                    raise MCPToolExecutionError(
                        f"MCP tool error (HTTP {status_code}): {error_body}"
                    )

                last_error = MCPToolExecutionError(
                    f"Server error {status_code} from MCP server: {error_body}"
                )

            except (urllib.error.URLError, TimeoutError, OSError) as e:
                logger.warning(
                    f"Connection error calling {url} (attempt {attempt}/{self.max_retries}): {e}"
                )
                last_error = MCPConnectionError(f"Failed to connect to MCP server at {url}: {e}")

            if attempt < self.max_retries:
                sleep_time = self.retry_backoff * (2 ** (attempt - 1))
                time.sleep(sleep_time)

        raise last_error or MCPConnectionError(f"Exhausted retries calling {url}")

    def get_server_status(self) -> Dict[str, Any]:
        """Queries the MCP server root endpoint to verify connectivity and tool availability."""
        return self._make_request("", method="GET")

    def append_to_doc(self, doc_id: str, content: str) -> Dict[str, Any]:
        """Appends formatted text content to a Google Document via the MCP server.

        Args:
            doc_id: Target Google Document ID.
            content: Structured text content to append.

        Returns:
            Server response dictionary.
        """
        if not doc_id:
            raise ValueError("Target 'doc_id' cannot be empty.")
        if not content:
            raise ValueError("'content' to append cannot be empty.")

        payload = {
            "doc_id": doc_id,
            "content": content,
        }
        logger.info(f"Appending content to Google Doc '{doc_id}' via MCP server ({len(content)} chars)...")
        return self._make_request("/append_to_doc", method="POST", payload=payload)

    def create_email_draft(
        self,
        to: Union[str, List[str]],
        subject: str,
        body: str,
    ) -> Dict[str, Any]:
        """Creates a draft email in Gmail via the MCP server.

        Args:
            to: Recipient email address or list of recipient addresses.
            subject: Subject line of the email.
            body: Email body (plain text or HTML).

        Returns:
            Server response dictionary.
        """
        if not to:
            raise ValueError("Recipient 'to' cannot be empty.")
        if not subject:
            raise ValueError("Email 'subject' cannot be empty.")
        if not body:
            raise ValueError("Email 'body' cannot be empty.")

        # Convert list of emails to comma-separated string if needed
        to_str = ", ".join(to) if isinstance(to, list) else str(to)

        payload = {
            "to": to_str,
            "subject": subject,
            "body": body,
        }
        logger.info(f"Creating Gmail draft to '{to_str}' with subject '{subject}' via MCP server...")
        return self._make_request("/create_email_draft", method="POST", payload=payload)

    def send_email(
        self,
        to: Union[str, List[str]],
        subject: str,
        body: str,
    ) -> Dict[str, Any]:
        """Sends an email directly via the MCP server.

        Args:
            to: Recipient email address or list of recipient addresses.
            subject: Subject line of the email.
            body: Email body (plain text or HTML).

        Returns:
            Server response dictionary.
        """
        if not to:
            raise ValueError("Recipient 'to' cannot be empty.")
        if not subject:
            raise ValueError("Email 'subject' cannot be empty.")
        if not body:
            raise ValueError("Email 'body' cannot be empty.")

        to_str = ", ".join(to) if isinstance(to, list) else str(to)

        payload = {
            "to": to_str,
            "subject": subject,
            "body": body,
        }
        logger.info(f"Sending email to '{to_str}' with subject '{subject}' via MCP server...")
        return self._make_request("/send_email", method="POST", payload=payload)
