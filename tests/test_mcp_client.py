"""Unit tests for MCPClient adapter."""

import io
import json
import urllib.error
import pytest
from unittest.mock import MagicMock, patch

from src.agent.mcp_client import (
    MCPClient,
    MCPClientError,
    MCPConnectionError,
    MCPAuthenticationError,
    MCPToolExecutionError,
)
from src.utils.config_loader import MCPConfig


@pytest.fixture
def sample_mcp_config():
    return MCPConfig(
        server_url="https://web-production-c16ea.up.railway.app",
        api_key="test_secret_key",
        timeout_seconds=5.0,
        max_retries=2,
        retry_backoff_seconds=0.01,
    )


def test_mcp_client_init_and_headers(sample_mcp_config):
    client = MCPClient(config=sample_mcp_config)
    assert client.server_url == "https://web-production-c16ea.up.railway.app"
    assert client.api_key == "test_secret_key"

    headers = client._get_headers()
    assert headers["Authorization"] == "Bearer test_secret_key"
    assert headers["X-API-Key"] == "test_secret_key"
    assert headers["Content-Type"] == "application/json"


def test_mcp_client_headers_without_api_key():
    config = MCPConfig(
        server_url="https://web-production-c16ea.up.railway.app",
        api_key="",
    )
    client = MCPClient(config=config)
    headers = client._get_headers()
    assert "Authorization" not in headers
    assert "X-API-Key" not in headers


@patch("urllib.request.urlopen")
def test_get_server_status_success(mock_urlopen, sample_mcp_config):
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = json.dumps({
        "server": "Google Docs & Gmail MCP Server",
        "version": "1.0.0",
        "status": "online",
        "tools": [
            {"name": "append_to_doc", "endpoint": "/append_to_doc"},
            {"name": "create_email_draft", "endpoint": "/create_email_draft"},
        ]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    client = MCPClient(config=sample_mcp_config)
    status = client.get_server_status()

    assert status["server"] == "Google Docs & Gmail MCP Server"
    assert status["status"] == "online"
    assert len(status["tools"]) == 2


@patch("urllib.request.urlopen")
def test_append_to_doc_success(mock_urlopen, sample_mcp_config):
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = json.dumps({
        "status": "success",
        "message": "Content appended successfully",
        "doc_id": "doc_xyz123",
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    client = MCPClient(config=sample_mcp_config)
    result = client.append_to_doc(doc_id="doc_xyz123", content="Weekly Pulse Section")

    assert result["status"] == "success"
    assert result["doc_id"] == "doc_xyz123"

    # Verify request payload
    called_req = mock_urlopen.call_args[0][0]
    assert called_req.full_url == "https://web-production-c16ea.up.railway.app/append_to_doc"
    assert called_req.get_method() == "POST"
    sent_payload = json.loads(called_req.data.decode("utf-8"))
    assert sent_payload["doc_id"] == "doc_xyz123"
    assert sent_payload["content"] == "Weekly Pulse Section"


@patch("urllib.request.urlopen")
def test_create_email_draft_success(mock_urlopen, sample_mcp_config):
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = json.dumps({
        "status": "success",
        "draft_id": "draft_abc456",
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    client = MCPClient(config=sample_mcp_config)
    result = client.create_email_draft(
        to=["team@groww.in", "pm@groww.in"],
        subject="Weekly Report",
        body="<p>Snapshot</p>",
    )

    assert result["status"] == "success"
    assert result["draft_id"] == "draft_abc456"

    # Verify payload format
    called_req = mock_urlopen.call_args[0][0]
    sent_payload = json.loads(called_req.data.decode("utf-8"))
    assert sent_payload["to"] == "team@groww.in, pm@groww.in"
    assert sent_payload["subject"] == "Weekly Report"


def test_input_validations(sample_mcp_config):
    client = MCPClient(config=sample_mcp_config)

    with pytest.raises(ValueError, match="Target 'doc_id' cannot be empty"):
        client.append_to_doc(doc_id="", content="Some content")

    with pytest.raises(ValueError, match="'content' to append cannot be empty"):
        client.append_to_doc(doc_id="doc_123", content="")

    with pytest.raises(ValueError, match="Recipient 'to' cannot be empty"):
        client.create_email_draft(to="", subject="Subj", body="Body")

    with pytest.raises(ValueError, match="Email 'subject' cannot be empty"):
        client.create_email_draft(to="a@b.com", subject="", body="Body")

    with pytest.raises(ValueError, match="Email 'body' cannot be empty"):
        client.create_email_draft(to="a@b.com", subject="Subj", body="")


@patch("urllib.request.urlopen")
def test_authentication_error_handling(mock_urlopen, sample_mcp_config):
    http_error = urllib.error.HTTPError(
        url="https://web-production-c16ea.up.railway.app/append_to_doc",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(b'{"error": "Invalid API key"}'),
    )
    mock_urlopen.side_effect = http_error

    client = MCPClient(config=sample_mcp_config)
    with pytest.raises(MCPAuthenticationError, match="Authentication failed for MCP server"):
        client.append_to_doc("doc_123", "Some content")


@patch("urllib.request.urlopen")
def test_connection_error_handling(mock_urlopen, sample_mcp_config):
    mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")

    client = MCPClient(config=sample_mcp_config)
    with pytest.raises(MCPConnectionError, match="Failed to connect to MCP server"):
        client.append_to_doc("doc_123", "Some content")
