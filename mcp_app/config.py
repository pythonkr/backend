import os

API_BASE_URL = os.environ.get("MCP_API_BASE_URL", "http://127.0.0.1:8000")

HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "9000"))
PATH = os.environ.get("MCP_PATH", "/mcp")

HTTP_TIMEOUT = float(os.environ.get("MCP_HTTP_TIMEOUT", "15"))
