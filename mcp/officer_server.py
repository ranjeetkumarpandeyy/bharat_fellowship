import os
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token

from .auth import RoleTokenVerifier
from .portal_client import PortalClient, PortalError
from .common import PUBLIC_BASE_URL, ENABLED_BLOCKS

RESOURCE_URL = os.environ.get("OFFICER_MCP_URL", PUBLIC_BASE_URL + "/mcp/officer")

server = MCPServer(
    "sewa-setu-officer",
    instructions=(
        "You are the block-officer assistant for Sewa Setu. "
        "Show the officer what is waiting, retrieve cases, and record only "
        "explicit officer approve/reject decisions with a reason. Never decide "
        "a case on the officer's behalf."
    ),
    token_verifier=RoleTokenVerifier("officer", RESOURCE_URL),
    auth=AuthSettings(
        issuer_url=PUBLIC_BASE_URL,
        resource_server_url=RESOURCE_URL,
        required_scopes=["officer"],
        validate_token_resource=True,
    ),
)

def client() -> PortalClient:
    token = get_access_token()
    if not token or not token.subject:
        raise RuntimeError("Authentication required")
    return PortalClient(token.subject, "officer")

@server.tool()
def officer_identity() -> dict[str, Any]:
    """Return the authenticated officer identity."""
    return client().me()

@server.tool()
def list_pending_applications(block: str = "", limit: int = 20) -> dict[str, Any]:
    """List pending applications, restricted to the configured agent-enabled blocks."""
    if block and block not in ENABLED_BLOCKS:
        return {"ok": False, "error": f"Block is not enabled for the agent: {block}"}
    try:
        return client().pending(block=block or None, limit=min(max(limit, 1), 50))
    except PortalError as e:
        return {"ok": False, "error": str(e)}

@server.tool()
def get_application(application_id: int) -> dict[str, Any]:
    """Retrieve one application and its audit history."""
    try:
        return client().application(application_id)
    except PortalError as e:
        return {"ok": False, "error": str(e)}

@server.tool()
def decide_application(application_id: int, decision: str, reason: str) -> dict[str, Any]:
    """Record an explicit officer approve/reject decision with a non-empty reason."""
    decision = decision.upper().strip()
    reason = reason.strip()
    if decision not in {"APPROVED", "REJECTED"}:
        return {"ok": False, "error": "decision must be APPROVED or REJECTED"}
    if not reason:
        return {"ok": False, "error": "A reason is required"}
    try:
        return client().decide(application_id, decision, reason)
    except PortalError as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    server.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8102")),
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
    )
