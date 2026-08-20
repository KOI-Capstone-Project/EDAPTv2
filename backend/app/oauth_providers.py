# ── Google / Microsoft ID-token verification ────────────────────────────────
#
# The frontend never sends us a password for these providers — it gets a
# signed OpenID-Connect ID token directly from Google/Microsoft's own login
# UI (via their JS SDKs) and hands that token to us. All we do here is verify
# the token's signature and audience match our app, then read the verified
# email claim out of it. Neither provider's client secret is needed for this
# flow, since we're validating a token, not exchanging an auth code.
#
# Env vars are read lazily (inside each function) rather than at import time,
# since this module is imported by main.py before main.py's own load_dotenv()
# call runs.
import os
import time

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError
from jose import jwt as jose_jwt

_google_request = google_requests.Request()

_ms_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}
_MS_JWKS_TTL_SECONDS = 3600


class OAuthVerificationError(Exception):
    """Raised when a provider ID token fails verification or is unusable."""


def verify_google_id_token(token: str) -> str:
    """Verify a Google ID token and return the account's verified email."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
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


async def _microsoft_jwks(force_refresh: bool = False) -> list:
    tenant = os.getenv("MICROSOFT_TENANT_ID", "common")
    now = time.time()
    if (
        not force_refresh
        and _ms_jwks_cache["keys"] is not None
        and now - _ms_jwks_cache["fetched_at"] < _MS_JWKS_TTL_SECONDS
    ):
        return _ms_jwks_cache["keys"]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
        )
        resp.raise_for_status()
        keys = resp.json()["keys"]
    _ms_jwks_cache["keys"] = keys
    _ms_jwks_cache["fetched_at"] = now
    return keys


async def verify_microsoft_id_token(token: str) -> str:
    """Verify a Microsoft/Azure AD ID token and return the account's email."""
    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    if not client_id:
        raise OAuthVerificationError("Microsoft sign-in is not configured on this server")

    try:
        header = jose_jwt.get_unverified_header(token)
    except JWTError as exc:
        raise OAuthVerificationError(f"Invalid Microsoft token: {exc}") from exc

    keys = await _microsoft_jwks()
    jwk = next((k for k in keys if k.get("kid") == header.get("kid")), None)
    if jwk is None:
        # Signing key may have rotated since our last cache — refresh once.
        keys = await _microsoft_jwks(force_refresh=True)
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
