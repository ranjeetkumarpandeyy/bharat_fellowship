import time
from typing import Any
import jwt
from mcp.server.auth.provider import AccessToken, TokenVerifier

from .common import PUBLIC_BASE_URL, AGENT_API_AUDIENCE

class SewaSetuTokenVerifier(TokenVerifier):
    """Verifies the JWTs issued by the existing Sewa Setu OAuth server."""

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            # The supplied portal keeps its RSA signing key in oauth_keys and
            # exposes JWKS. Fetching JWKS here avoids sharing the private key.
            import requests
            jwks = requests.get(
                f"{PUBLIC_BASE_URL}/.well-known/jwks.json", timeout=5
            ).json()
            header = jwt.get_unverified_header(token)
            key_data = next(
                (k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")),
                None,
            )
            if not key_data:
                return None
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=AGENT_API_AUDIENCE.replace("/api/agent", "/mcp/citizen"),
                issuer=PUBLIC_BASE_URL,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
            scope = claims.get("scope")
            if isinstance(scope, str):
                scopes = scope.split()
            else:
                scopes = list(scope or [])
            return AccessToken(
                token=token,
                client_id=str(claims.get("client_id", "")),
                scopes=scopes,
                expires_at=int(claims["exp"]),
                resource=str(claims.get("aud", "")),
                subject=str(claims.get("sub", "")),
                claims=claims,
            )
        except Exception:
            return None

class RoleTokenVerifier(SewaSetuTokenVerifier):
    def __init__(self, expected_role: str, expected_audience: str):
        self.expected_role = expected_role
        self.expected_audience = expected_audience

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            import requests
            jwks = requests.get(
                f"{PUBLIC_BASE_URL}/.well-known/jwks.json", timeout=5
            ).json()
            header = jwt.get_unverified_header(token)
            key_data = next(
                (k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")),
                None,
            )
            if not key_data:
                return None
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
            claims = jwt.decode(
                token, public_key, algorithms=["RS256"],
                audience=self.expected_audience,
                issuer=PUBLIC_BASE_URL,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
            if claims.get("role") != self.expected_role:
                return None
            scope = claims.get("scope", "")
            scopes = scope.split() if isinstance(scope, str) else list(scope or [])
            if self.expected_role not in scopes:
                return None
            return AccessToken(
                token=token,
                client_id=str(claims.get("client_id", "")),
                scopes=scopes,
                expires_at=int(claims["exp"]),
                resource=str(claims.get("aud", "")),
                subject=str(claims.get("sub", "")),
                claims=claims,
            )
        except Exception:
            return None
