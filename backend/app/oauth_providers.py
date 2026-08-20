# ── Google / Microsoft ID-token verification ────────────────────────────────
#
# The frontend never sends us a password for these providers — it gets a
# signed OpenID-Connect ID token directly from Google/Microsoft's own login
# UI (via their JS SDKs) and hands that token to us. All we do here is verify
# the token's signature and audience match our app, then read the verified
# email claim out of it. Neither provider's client secret is needed for this
# flow, since we're validating a token, not exchanging an auth code.
#
# client_id/tenant_id are passed in by main.py from the OAuthProviderConfig
# DB row (Settings > OAuth Providers) rather than read from an env var here
# — this module has no DB access of its own, and stays easy to unit-test by
# passing whatever/None directly.
import time

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError
from jose import jwt as jose_jwt

_google_request = google_requests.Request()

# Keyed by tenant, since an admin can change MICROSOFT_TENANT_ID at runtime
# now (via Settings) instead of it being fixed for the process's lifetime.
_ms_jwks_cache: dict[str, dict] = {}
_MS_JWKS_TTL_SECONDS = 3600


class OAuthVerificationError(Exception):
    """Raised when a provider ID token fails verification or is unusable."""


def verify_google_id_token(token: str, client_id: str | None) -> str:
    """Verify a Google ID token and return the account's verified email."""
    if not client_id:
        raise OAuthVerificationError("Google sign-in is not configured on this server")
    try:
        claims = google_id_token.verify_oauth2_token(token, _google_request, client_id)
    except ValueError as exc:
        raise OAuthVerificationError(f"Invalid Google token: {exc}") from exc

    if not claims.get("email_verified", False):
        raise OAuthVerificationError("Google account email is not verified")
    email = claims.get("email")
    if not email:
        raise OAuthVerificationError("Google token did not include an email address")
    return email


async def _microsoft_jwks(tenant: str, force_refresh: bool = False) -> list:
    now = time.time()
    cached = _ms_jwks_cache.get(tenant)
    if not force_refresh and cached is not None and now - cached["fetched_at"] < _MS_JWKS_TTL_SECONDS:
        return cached["keys"]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
        )
        resp.raise_for_status()
        keys = resp.json()["keys"]
    _ms_jwks_cache[tenant] = {"keys": keys, "fetched_at": now}
    return keys


async def verify_microsoft_id_token(token: str, client_id: str | None, tenant_id: str | None = None) -> str:
    """Verify a Microsoft/Azure AD ID token and return the account's email."""
    if not client_id:
        raise OAuthVerificationError("Microsoft sign-in is not configured on this server")
    tenant = tenant_id or "common"

    try:
        header = jose_jwt.get_unverified_header(token)
    except JWTError as exc:
        raise OAuthVerificationError(f"Invalid Microsoft token: {exc}") from exc

    keys = await _microsoft_jwks(tenant)
    jwk = next((k for k in keys if k.get("kid") == header.get("kid")), None)
    if jwk is None:
        # Signing key may have rotated since our last cache — refresh once.
        keys = await _microsoft_jwks(tenant, force_refresh=True)
        jwk = next((k for k in keys if k.get("kid") == header.get("kid")), None)
    if jwk is None:
        raise OAuthVerificationError("Unable to verify Microsoft token signature")

    try:
        claims = jose_jwt.decode(
            token,
            jwk,
            algorithms=["RS256"],
            audience=client_id,
            # Multi-tenant ("common") sign-in means the issuer contains the
            # signing tenant's own GUID, which we can't pin to a fixed
            # string — signature + audience verification above is what
            # actually proves the token is ours.
            options={"verify_iss": False},
        )
    except JWTError as exc:
        raise OAuthVerificationError(f"Invalid Microsoft token: {exc}") from exc

    email = claims.get("email") or claims.get("preferred_username")
    if not email:
        raise OAuthVerificationError("Microsoft token did not include an email address")
    return email
