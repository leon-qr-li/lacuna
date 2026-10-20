"""Cloud mode: LACUNA on the DigitalOcean server behind Cloudflare Tunnel + Access (decision cloud-deploy).

Off unless ``LACUNA_CLOUD=1``; a local development checkout never sees any of this. When on:

* Every request must carry a valid Cloudflare Access token (``Cf-Access-Jwt-Assertion``, RS256, signed
  by the team's keys, our application's audience). Cloudflare Access is the first door (invite list +
  email code); checking its token here means a request that somehow reaches the container without
  passing Access is refused. Only the container's own loopback (the host's deploy health check, run
  with ``docker exec``) is exempt.
* Local-only actions answer 404: saving API keys from the browser (keys
  come from the server's environment), opening folders on the server.
* Before sign-in, ``/api/app`` and ``/api/health`` answer only the version.
* ``GET /api/version`` answers the version string and nothing else, with no Access token: the deploy check
  reads it through a path-scoped Access bypass (deploy/provision.py), so a deploy needs no Cloudflare API
  call (decision ``public-version-check``; withdrawn before public launch).

Settings (environment, set by deploy/provision.py): ``LACUNA_OWNER_EMAIL`` (see ``owner_email``), ``CF_ACCESS_TEAM_DOMAIN`` (``<team>.cloudflareaccess.com``),
``CF_ACCESS_AUD`` (the Access application's audience tag). Missing settings stop the server from
starting: cloud mode fails closed.

``access_allow`` / ``access_revoke`` keep the Access invite list in step with in-app invites; they need
``CF_ACCESS_API_TOKEN``, ``CF_ACCOUNT_ID`` and ``CF_ACCESS_GROUP_ID`` and do nothing outside the cloud.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from typing import Callable

ACCESS_HEADER = b"cf-access-jwt-assertion"
LOOPBACK = {"127.0.0.1", "::1"}
CF_API = "https://api.cloudflare.com/client/v4"

# local-only actions (a development checkout): no meaning (or a risk) on a shared server
BLOCKED = [
    ("POST", re.compile(r"^/api/app/api-key$")),
    ("POST", re.compile(r"^/api/auth/resend-key$")),
    ("POST", re.compile(r"^/api/episodes/[^/]+/exports/open$")),
    ("POST", re.compile(r"^/api/library/open$")),
]
# answered with the version only until the visitor has signed in to the app
PUBLIC_INFO = {"/api/app", "/api/health"}
VERSION_PATH = "/api/version"        # the version string only; open to anyone (deploy/provision.py VERSION_PATH)


class CloudConfigError(RuntimeError):
    pass


def enabled() -> bool:
    return os.environ.get("LACUNA_CLOUD") == "1"


def staging() -> bool:
    """The staging site (preview.<domain>, decision staging-site): a copy where Leon checks new work."""
    return enabled() and os.environ.get("LACUNA_STAGING") == "1"


def blocked(method: str, path: str) -> bool:
    return any(m == method and rx.match(path) for m, rx in BLOCKED)


class AccessVerifier:
    """Checks Cloudflare Access tokens against the team's published signing keys (cached, refreshed
    when a token names a key we don't have yet, at most once a minute)."""

    def __init__(self, team_domain: str, audience: str, fetch_keys: Callable[[str], dict] | None = None):
        team_domain = team_domain.strip().removeprefix("https://").rstrip("/")
        if not team_domain or not audience.strip():
            raise CloudConfigError("cloud mode needs CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD")
        self.issuer = f"https://{team_domain}"
        self.certs_url = f"{self.issuer}/cdn-cgi/access/certs"
        self.audience = audience.strip()
        self._fetch = fetch_keys or _fetch_json
        self._keys: dict[str, object] = {}
        self._fetched = 0.0
        self._lock = threading.Lock()

    def _key(self, kid: str):
        import jwt

        with self._lock:
            if kid not in self._keys and time.time() - self._fetched > 60:
                self._fetched = time.time()
                try:
                    jwks = self._fetch(self.certs_url)
                    self._keys = {k["kid"]: jwt.PyJWK(k).key for k in jwks.get("keys", []) if "kid" in k}
                except Exception:
                    pass     # keep the keys we had; this token is refused if its key is unknown
            return self._keys.get(kid)

    def verify(self, token: str) -> dict | None:
        """The token's claims when it is valid, else None."""
        import jwt

        try:
            kid = jwt.get_unverified_header(token).get("kid")
            key = self._key(kid) if kid else None
            if key is None:
                return None
            return jwt.decode(token, key, algorithms=["RS256"], audience=self.audience, issuer=self.issuer,
                              options={"require": ["exp", "iat", "aud", "iss"]}, leeway=30)
        except jwt.PyJWTError:
            return None


def _fetch_json(url: str, timeout: float = 10) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "LACUNA"}), timeout=timeout) as r:
        return json.loads(r.read())


class CloudGate:
    """ASGI middleware, outermost: Access token check, local-only actions, minimal pre-sign-in info."""

    def __init__(self, app, verifier: AccessVerifier, signed_in: Callable[[str], bool], version: Callable[[], str]):
        self.app, self.verifier, self.signed_in, self.version = app, verifier, signed_in, version

    async def __call__(self, scope, receive, send):
        from fastapi.responses import JSONResponse, PlainTextResponse

        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        if scope["type"] == "http" and scope["method"] == "GET" and scope["path"] == VERSION_PATH:
            return await JSONResponse({"version": self.version()})(scope, receive, send)
        client = (scope.get("client") or ("", 0))[0]
        headers = dict(scope.get("headers") or [])
        if client not in LOOPBACK:
            token = headers.get(ACCESS_HEADER, b"").decode("latin-1")
            claims = self.verifier.verify(token) if token else None
            if claims is None:
                if scope["type"] == "websocket":
                    return await send({"type": "websocket.close", "code": 1008})
                return await PlainTextResponse("Forbidden", status_code=403)(scope, receive, send)
            # the email Cloudflare Access verified (one-time code sent to it); request.state.access_email
            scope.setdefault("state", {})["access_email"] = str(claims.get("email") or "").strip().lower() or None
        if scope["type"] == "http":
            method, path = scope["method"], scope["path"]
            if blocked(method, path):
                return await JSONResponse({"detail": "Not Found"}, status_code=404)(scope, receive, send)
            if method == "GET" and path in PUBLIC_INFO and client not in LOOPBACK \
                    and not self.signed_in(headers.get(b"cookie", b"").decode("latin-1")):
                return await JSONResponse({"ok": True, "version": self.version(), "cloud": True})(scope, receive, send)
        return await self.app(scope, receive, send)


def access_email(request) -> str | None:
    """The email Cloudflare Access verified for this request (cloud only; None on loopback / locally)."""
    return getattr(request.state, "access_email", None) if enabled() else None


def owner_email() -> str | None:
    """The site owner's email (``LACUNA_OWNER_EMAIL``, the first ACCESS_EMAILS entry), cloud only. A first
    account registered by a request whose Access email is this one needs no setup code: there is no
    shell on the server to read a code from, and Access already proved the email."""
    e = os.environ.get("LACUNA_OWNER_EMAIL", "").strip().lower()
    return e if enabled() and e else None


# ---------------------------------------------------------------- Access invite list (for invites)
def _cf(method: str, path: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{CF_API}{path}", data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read())
    if not out.get("success"):
        raise RuntimeError(f"Cloudflare API {method} {path}: {out.get('errors')}")
    return out["result"]


def _access_group() -> tuple[str, str, str] | None:
    token, account, group = (os.environ.get(k, "").strip() for k in
                             ("CF_ACCESS_API_TOKEN", "CF_ACCOUNT_ID", "CF_ACCESS_GROUP_ID"))
    return (token, account, group) if enabled() and token and account and group else None


def _edit_group(email: str, add: bool, cf=_cf) -> bool:
    cfg = _access_group()
    if cfg is None:
        return False
    token, account, group = cfg
    email = email.strip().lower()
    path = f"/accounts/{account}/access/groups/{group}"
    g = cf("GET", path, token)
    include = [r for r in g.get("include", []) if (r.get("email") or {}).get("email", "").lower() != email]
    if add:
        include.append({"email": {"email": email}})
    if not include:      # Access refuses an empty group; keep the owner in by never removing the last one
        return False
    cf("PUT", path, token, {"name": g["name"], "include": include, "exclude": g.get("exclude", []),
                            "require": g.get("require", [])})
    return True


def access_allow(email: str) -> bool:
    """Let `email` through Cloudflare Access (an invite was sent). False when not in the cloud."""
    return _edit_group(email, True)


def access_revoke(email: str) -> bool:
    """Stop `email` at Cloudflare Access (invite revoked, account removed)."""
    return _edit_group(email, False)


# ---------------------------------------------------------------- wiring
def install(app, signed_in: Callable[[str], bool], version: Callable[[], str],
            verifier: AccessVerifier | None = None) -> bool:
    """Add the cloud gate when cloud mode is on; True when installed."""
    if not enabled():
        return False
    verifier = verifier or AccessVerifier(os.environ.get("CF_ACCESS_TEAM_DOMAIN", ""),
                                          os.environ.get("CF_ACCESS_AUD", ""))
    app.add_middleware(CloudGate, verifier=verifier, signed_in=signed_in, version=version)
    return True
