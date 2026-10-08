import jwt
from mcp.server.auth.provider import AccessToken, TokenVerifier

from .common import PUBLIC_BASE_URL, PORTAL_BASE_URL


class RoleTokenVerifier(TokenVerifier):
    """Verify portal-issued JWTs without sharing the portal private key."""

    def __init__(self, expected_role: str, expected_audience: str):
        self.expected_role = expected_role
        self.expected_audience = expected_audience

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            import requests

            jwks = requests.get(
                f"{PORTAL_BASE_URL}/.well-known/jwks.json", timeout=5
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
