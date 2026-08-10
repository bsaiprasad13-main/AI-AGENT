"""Demo script to verify connectivity and tool discovery on the MCP server."""

import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.agent.mcp_client import MCPClient, MCPClientError


def main():
    print("Testing connection to Google Docs & Gmail MCP Server...")
    client = MCPClient()
    print(f"Target URL: {client.server_url}")

    try:
        status = client.get_server_status()
        print("\n[SUCCESS] Server is online and reachable!")
        print(f"Server Name: {status.get('server')}")
        print(f"Version: {status.get('version')}")
        print(f"Status: {status.get('status')}")
        print(f"Mode: {status.get('mode')}")
        print(f"API Key Required: {status.get('api_key_required')}")
        print("\nExposed Tools:")
        for tool in status.get("tools", []):
            print(f" - {tool.get('name')}: {tool.get('endpoint')} ({tool.get('method')})")
            print(f"   Description: {tool.get('description')}")
            print(f"   Parameters:  {tool.get('required_parameters')}")
    except MCPClientError as e:
        print(f"\n[ERROR] MCP Server communication error: {e}")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")


if __name__ == "__main__":
    main()
