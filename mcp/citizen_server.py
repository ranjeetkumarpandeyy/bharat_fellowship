import os
from typing import Any

from mcp.server.mcpserver import MCPServer, Context
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token

from .auth import RoleTokenVerifier
from .portal_client import PortalClient, PortalError
from .common import PUBLIC_BASE_URL

RESOURCE_URL = os.environ.get("CITIZEN_MCP_URL", PUBLIC_BASE_URL + "/mcp/citizen")

server = MCPServer(
    "sewa-setu-citizen",
    instructions=(
        "You are the citizen-facing Sewa Setu agent interface. "
        "Use the official portal tools; never invent eligibility, status, or "
        "application numbers. The portal is the system of record."
    ),
    token_verifier=RoleTokenVerifier("citizen", RESOURCE_URL),
    auth=AuthSettings(
        issuer_url=PUBLIC_BASE_URL,
        resource_server_url=RESOURCE_URL,
        required_scopes=["citizen"],
        validate_token_resource=True,
    ),
)

def client() -> PortalClient:
    token = get_access_token()
    if not token or not token.subject:
        raise RuntimeError("Authentication required")
    return PortalClient(token.subject, "citizen")

@server.tool()
def who_am_i() -> dict[str, Any]:
    """Return the authenticated citizen identity."""
    return client().me()

@server.tool()
def check_pension_eligibility(
    applicant_name: str,
    dob: str,
    village: str,
    block: str,
    bank_account: str,
    ifsc: str = "",
) -> dict[str, Any]:
    """Check whether the supplied application data passes the portal's validation rules."""
    try:
        return client().eligibility({
            "applicant_name": applicant_name,
            "dob": dob,
            "village": village,
            "block": block,
            "bank_account": bank_account,
            "ifsc": ifsc,
        })
    except PortalError as e:
        return {"ok": False, "error": str(e)}

@server.tool()
def apply_for_pension(
    applicant_name: str,
    dob: str,
    village: str,
    block: str,
    bank_account: str,
    ifsc: str,
    gender: str = "",
    marital_status: str = "",
    husband_name: str = "",
    age_proof_path: str = "",
) -> dict[str, Any]:
    """Submit an old-age pension application through the same portal validation path as the web form.

    age_proof_path must identify a document already uploaded through the agent upload API.
    """
    try:
        return client().submit({
            "applicant_name": applicant_name,
            "dob": dob,
            "village": village,
            "block": block,
            "bank_account": bank_account,
            "ifsc": ifsc,
            "gender": gender,
            "marital_status": marital_status,
            "husband_name": husband_name,
            "age_proof_path": age_proof_path,
        })
    except PortalError as e:
        return {"ok": False, "error": str(e)}

@server.tool()
def get_my_application() -> dict[str, Any]:
    """Get the authenticated citizen's latest application."""
    try:
        return client().my_application()
    except PortalError as e:
        return {"ok": False, "error": str(e)}

@server.tool()
def withdraw_my_pending_application() -> dict[str, Any]:
    """Withdraw the authenticated citizen's own pending application."""
    try:
        return client().withdraw()
    except PortalError as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    server.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8101")),
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
    )
