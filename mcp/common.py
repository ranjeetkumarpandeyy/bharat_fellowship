import os
from typing import Any

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
PORTAL_BASE_URL = os.environ.get("PORTAL_BASE_URL", PUBLIC_BASE_URL).rstrip("/")
AGENT_API_AUDIENCE = os.environ.get("AGENT_API_AUDIENCE", PORTAL_BASE_URL + "/api/agent")
AGENT_INTERNAL_SECRET = os.environ.get("AGENT_INTERNAL_SECRET", "change-this-agent-secret")
ENABLED_BLOCKS = tuple(
    b.strip() for b in os.environ.get(
        "AGENT_ENABLED_BLOCKS",
        "Sonari,Rajapara,Dhemaji Pathar,Borgaon,Namti,Khelua",
    ).split(",") if b.strip()
)

def error(message: str, code: str = "invalid_request") -> dict[str, Any]:
    return {"ok": False, "error": code, "message": message}

def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}
