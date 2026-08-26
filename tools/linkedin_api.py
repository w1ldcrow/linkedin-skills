"""Minimal LinkedIn client for the three calls this package is allowed to make.

Replaces the linkedin-mcp server. Same OAuth app, same four scopes, three
working endpoints — /v2/userinfo (identity), POST /v2/ugcPosts (publish), and
POST /v2/assets?action=registerUpload (image upload, part of the same
w_member_social share flow). Everything else in the LinkedIn API is
partner-gated and must not be called; see shared/linkedin-access.md.

Unlike the MCP, the token is persisted to disk (.linkedin-token.json at the
repo root, already gitignored), so authorization survives across sessions
until LinkedIn expires it — about 60 days.

CLI:
    python3 tools/linkedin_api.py auth          # browser flow, saves token
    python3 tools/linkedin_api.py whoami        # prints name and email
    python3 tools/linkedin_api.py post FILE [--image PNG [--alt TEXT]]
                                                # publishes FILE, prints URL
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
UGC_POSTS_URL = "https://api.linkedin.com/v2/ugcPosts"
ASSETS_URL = "https://api.linkedin.com/v2/assets?action=registerUpload"

# LinkedIn caps feed images at 8MB.
IMAGE_MAX_BYTES = 8 * 1024 * 1024

REDIRECT_URI = "http://localhost:50001/callback"
SCOPES = ("openid", "profile", "email", "w_member_social")

# LinkedIn caps a post at 3000 characters.
POST_MAX_CHARS = 3000

# A token this close to expiry is treated as expired, so a publish never
# starts with a token that dies mid-flow.
EXPIRY_MARGIN_SECONDS = 60

_DEFAULT_TOKEN_PATH = Path(__file__).resolve().parent.parent / ".linkedin-token.json"


def token_path() -> Path:
    return Path(os.environ.get("LINKEDIN_TOKEN_PATH", _DEFAULT_TOKEN_PATH))


def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": " ".join(SCOPES),
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def parse_callback(path: str, expected_state: str) -> str:
    """Extract the authorization code from the callback path, or raise."""
    params = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
    if params.get("state", [None])[0] != expected_state:
        raise ValueError("state mismatch in OAuth callback; possible forgery, aborting")
    if "error" in params:
        detail = params.get("error_description", params["error"])[0]
        raise ValueError(f"authorization failed: {params['error'][0]} ({detail})")
    code = params.get("code", [None])[0]
    if not code:
        raise ValueError("callback carried no authorization code")
    return code


def token_is_valid(token: dict | None, now: float) -> bool:
    if not token or "access_token" not in token:
        return False
    return token.get("expires_at", 0.0) - EXPIRY_MARGIN_SECONDS > now


def build_post_payload(
    author_urn: str, text: str, asset_urn: str = "", alt_text: str = ""
) -> dict:
    if not text.strip():
        raise ValueError("refusing to publish empty text")
    if len(text) > POST_MAX_CHARS:
        raise ValueError(f"post is {len(text)} characters; LinkedIn caps at {POST_MAX_CHARS}")
    share: dict = {
        "shareCommentary": {"text": text},
        "shareMediaCategory": "IMAGE" if asset_urn else "NONE",
    }
    if asset_urn:
        media: dict = {"status": "READY", "media": asset_urn}
        if alt_text:
            media["description"] = {"text": alt_text}
        share["media"] = [media]
    return {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": share},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }


def build_register_upload_payload(author_urn: str) -> dict:
    return {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": author_urn,
            "serviceRelationships": [
                {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
            ],
        }
    }


def parse_register_upload(body: dict) -> tuple[str, str]:
    """Extract (asset urn, upload url) from a registerUpload response, or raise."""
    try:
        value = body["value"]
        asset = value["asset"]
        upload_url = value["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
    except (KeyError, TypeError) as error:
        raise ValueError(f"unexpected registerUpload response shape: {body}") from error
    if not asset or not upload_url:
        raise ValueError(f"registerUpload response missing asset or uploadUrl: {body}")
    return asset, upload_url


def post_url_from_id(post_id: str) -> str:
    if not post_id:
        raise ValueError("LinkedIn returned no post id")
    return f"https://www.linkedin.com/feed/update/{post_id}/"


# ---------------------------------------------------------------------------
# Network side. Kept thin and unmocked on purpose — the pure logic above is
# what the test suite covers.
# ---------------------------------------------------------------------------


def _http_json(request: urllib.request.Request) -> tuple[dict, dict]:
    """Return (body, headers). Raises SystemExit with LinkedIn's actual error body."""
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return (json.loads(body) if body else {}, dict(response.headers))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"LinkedIn returned HTTP {error.code}: {detail}") from error


def _load_token() -> dict | None:
    try:
        return json.loads(token_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _require_token() -> dict:
    token = _load_token()
    if not token_is_valid(token, now=time.time()):
        raise SystemExit(
            f"no valid token at {token_path()} — run: python3 tools/linkedin_api.py auth"
        )
    return token


def _fetch_userinfo(access_token: str) -> dict:
    request = urllib.request.Request(
        USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
    )
    body, _ = _http_json(request)
    return body


def _exchange_code(code: str, client_id: str, client_secret: str) -> dict:
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
        }
    ).encode("ascii")
    request = urllib.request.Request(
        TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    body, _ = _http_json(request)
    return body


def cmd_auth() -> None:
    client_id = os.environ.get("LINKEDIN_CLIENT_ID")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit("export LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET first — see shared/auth.md")

    state = secrets.token_urlsafe(16)
    url = build_authorize_url(client_id, REDIRECT_URI, state)
    captured: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler contract
            try:
                captured["code"] = parse_callback(self.path, state)
                message = "Autorizado. Pode fechar esta aba."
            except ValueError as error:
                captured["error"] = str(error)
                message = f"Falhou: {error}"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(message.encode("utf-8"))

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("localhost", 50001), Handler)
    print(f"Abra no navegador se não abrir sozinho:\n{url}")
    webbrowser.open(url)
    while not captured:
        server.handle_request()
    server.server_close()

    if "error" in captured:
        raise SystemExit(captured["error"])

    granted = _exchange_code(captured["code"], client_id, client_secret)
    info = _fetch_userinfo(granted["access_token"])
    token = {
        "access_token": granted["access_token"],
        "expires_at": time.time() + float(granted.get("expires_in", 0)),
        "sub": info.get("sub", ""),
        "name": info.get("name", ""),
        "email": info.get("email", ""),
    }
    path = token_path()
    path.write_text(json.dumps(token, indent=2), encoding="utf-8")
    path.chmod(0o600)
    days = int((token["expires_at"] - time.time()) / 86400)
    print(f"Autorizado como {token['name']} <{token['email']}>. Token válido por ~{days} dias em {path}.")


def cmd_whoami() -> None:
    token = _require_token()
    info = _fetch_userinfo(token["access_token"])
    days = int((token["expires_at"] - time.time()) / 86400)
    print(f"{info.get('name', '?')} <{info.get('email', '?')}> — token expira em ~{days} dias")


def _upload_image(upload_url: str, image_path: Path, access_token: str) -> None:
    data = image_path.read_bytes()
    if len(data) > IMAGE_MAX_BYTES:
        raise SystemExit(f"{image_path} is {len(data)} bytes; LinkedIn caps images at 8MB")
    request = urllib.request.Request(
        upload_url,
        data=data,
        method="PUT",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/octet-stream",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status not in (200, 201):
                raise SystemExit(f"image upload returned HTTP {response.status}")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"image upload failed with HTTP {error.code}: {detail}") from error


def cmd_post(*argv: str) -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="linkedin_api.py post")
    parser.add_argument("file")
    parser.add_argument("--image", default="", help="PNG or JPG to attach to the post")
    parser.add_argument("--alt", default="", help="alt text describing the attached image")
    args = parser.parse_args(argv)

    token = _require_token()
    text = Path(args.file).read_text(encoding="utf-8")
    author = f"urn:li:person:{token['sub']}" if token.get("sub") else None
    if not author:
        raise SystemExit("token carries no member id — re-run: python3 tools/linkedin_api.py auth")

    asset_urn = ""
    if args.image:
        image_path = Path(args.image)
        if not image_path.is_file():
            raise SystemExit(f"image not found: {image_path}")
        register = urllib.request.Request(
            ASSETS_URL,
            data=json.dumps(build_register_upload_payload(author)).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token['access_token']}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
        )
        body, _ = _http_json(register)
        try:
            asset_urn, upload_url = parse_register_upload(body)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        _upload_image(upload_url, image_path, token["access_token"])

    payload = build_post_payload(author, text, asset_urn=asset_urn, alt_text=args.alt)
    request = urllib.request.Request(
        UGC_POSTS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token['access_token']}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
    )
    body, headers = _http_json(request)
    post_id = headers.get("X-RestLi-Id") or headers.get("x-restli-id") or body.get("id", "")
    print(post_url_from_id(post_id))


def main(argv: list[str]) -> None:
    commands = {"auth": cmd_auth, "whoami": cmd_whoami, "post": cmd_post}
    if not argv or argv[0] not in commands:
        raise SystemExit("usage: python3 tools/linkedin_api.py auth | whoami | post FILE")
    commands[argv[0]](*argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
