import base64
import hashlib
import hmac
import json
import time
from typing import Any

import requests

from .common import PORTAL_BASE_URL, AGENT_INTERNAL_SECRET

class PortalError(RuntimeError):
    pass

def _principal_headers(subject: str, role: str) -> dict[str, str]:
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(time.time()),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = hmac.new(
        AGENT_INTERNAL_SECRET.encode(), encoded.encode(), hashlib.sha256
    ).hexdigest()
    return {
        "X-SewaSetu-Agent-Principal": encoded,
        "X-SewaSetu-Agent-Signature": sig,
    }

class PortalClient:
    def __init__(self, subject: str, role: str):
        self.subject = subject
        self.role = role
        self.headers = _principal_headers(subject, role)

    def call(self, path: str, method: str = "GET", **kwargs) -> dict[str, Any]:
        url = PORTAL_BASE_URL + path
        r = requests.request(method, url, headers=self.headers, timeout=20, **kwargs)
        try:
            body = r.json()
        except Exception:
            body = {"message": r.text}
        if r.status_code >= 400:
            raise PortalError(body.get("message", f"Portal returned HTTP {r.status_code}"))
        return body

    def me(self):
        return self.call("/api/agent/me")

    def eligibility(self, data):
        return self.call("/api/agent/citizen/eligibility", "POST", json=data)

    def submit(self, data):
        return self.call("/api/agent/citizen/applications", "POST", json=data)

    def my_application(self):
        return self.call("/api/agent/citizen/application")

    def withdraw(self):
        return self.call("/api/agent/citizen/application/withdraw", "POST")

    def pending(self, block=None, limit=20):
        params = {"limit": limit}
        if block:
            params["block"] = block
        return self.call("/api/agent/officer/applications", params=params)

    def application(self, app_id):
        return self.call(f"/api/agent/officer/applications/{int(app_id)}")

    def decide(self, app_id, decision, reason):
        return self.call(
            f"/api/agent/officer/applications/{int(app_id)}/decision",
            "POST",
            json={"decision": decision, "reason": reason},
        )
