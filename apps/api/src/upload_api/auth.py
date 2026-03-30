from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, WebSocket, status
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings


SESSION_COOKIE_NAME = "merlin_alpha_session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
PBKDF2_ITERATIONS = 390_000


class AlphaUserConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1)
    password_hash: str | None = None
    password: str | None = None


@dataclass(frozen=True)
class AuthenticatedActor:
    username: str


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password must not be empty.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = _b64url_decode(salt_raw)
        expected = _b64url_decode(digest_raw)
    except Exception:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


class AuthManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._users = self._load_users(settings.alpha_users_json)

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        return self._settings.app_allowed_origins

    @property
    def session_cookie_secure(self) -> bool:
        return self._settings.session_cookie_secure

    @property
    def session_cookie_domain(self) -> str | None:
        return self._settings.session_cookie_domain

    @property
    def session_cookie_samesite(self) -> str:
        return self._settings.session_cookie_samesite

    def authenticate(self, username: str, password: str) -> AuthenticatedActor | None:
        stored_hash = self._users.get(username.strip())
        if not stored_hash or not verify_password(password, stored_hash):
            return None
        return AuthenticatedActor(username=username.strip())

    def issue_session_token(self, actor: AuthenticatedActor) -> str:
        payload = {
            "sub": actor.username,
            "exp": int(time.time()) + SESSION_MAX_AGE_SECONDS,
            "iat": int(time.time()),
        }
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_part = _b64url_encode(payload_bytes)
        signature = hmac.new(
            self._settings.session_secret.encode("utf-8"),
            payload_part.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{payload_part}.{_b64url_encode(signature)}"

    def get_optional_actor_from_request(self, request: Request) -> AuthenticatedActor | None:
        token = request.cookies.get(SESSION_COOKIE_NAME)
        return self._decode_session_token(token)

    def get_required_actor_from_request(self, request: Request) -> AuthenticatedActor:
        actor = self.get_optional_actor_from_request(request)
        if actor is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
        request.state.actor_username = actor.username
        return actor

    def get_required_actor_from_websocket(self, websocket: WebSocket) -> AuthenticatedActor:
        token = websocket.cookies.get(SESSION_COOKIE_NAME)
        actor = self._decode_session_token(token)
        if actor is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
        return actor

    def validate_origin(self, origin: str | None) -> None:
        if origin is None or not origin.strip():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin header is required.")
        if origin not in self._settings.app_allowed_origins:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin is not allowed.")

    def require_request_origin(self, request: Request) -> None:
        self.validate_origin(request.headers.get("origin"))

    def require_websocket_origin(self, websocket: WebSocket) -> None:
        self.validate_origin(websocket.headers.get("origin"))

    def _decode_session_token(self, token: str | None) -> AuthenticatedActor | None:
        if not token:
            return None
        try:
            payload_part, signature_part = token.split(".", 1)
            expected_signature = hmac.new(
                self._settings.session_secret.encode("utf-8"),
                payload_part.encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(expected_signature, _b64url_decode(signature_part)):
                return None
            payload = json.loads(_b64url_decode(payload_part))
            if not isinstance(payload, dict):
                return None
            username = str(payload.get("sub") or "").strip()
            exp = int(payload.get("exp") or 0)
            if not username or exp < int(time.time()):
                return None
            if username not in self._users:
                return None
            return AuthenticatedActor(username=username)
        except Exception:
            return None

    def _load_users(self, raw_json: str | None) -> dict[str, str]:
        if raw_json is None or not raw_json.strip():
            raise RuntimeError("ALPHA_USERS_JSON must not be empty.")
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("ALPHA_USERS_JSON must be valid JSON.") from exc
        if not isinstance(payload, list):
            raise RuntimeError("ALPHA_USERS_JSON must be a JSON array.")

        users: dict[str, str] = {}
        for row in payload:
            cfg = AlphaUserConfig.model_validate(row)
            if cfg.password_hash:
                users[cfg.username.strip()] = cfg.password_hash
                continue
            if cfg.password:
                users[cfg.username.strip()] = hash_password(cfg.password)
                continue
            raise RuntimeError(f"User '{cfg.username}' must define either password or password_hash.")
        if not users:
            raise RuntimeError("At least one alpha user must be configured.")
        return users


def build_cookie_settings(auth_manager: AuthManager) -> dict[str, Any]:
    return {
        "key": SESSION_COOKIE_NAME,
        "httponly": True,
        "max_age": SESSION_MAX_AGE_SECONDS,
        "samesite": auth_manager.session_cookie_samesite,
        "secure": auth_manager.session_cookie_secure,
        "path": "/",
        "domain": auth_manager.session_cookie_domain,
    }
