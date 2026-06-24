from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import bcrypt
import requests
from sqlalchemy.exc import IntegrityError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials

from remindee.models.user import User
from remindee.utils.database import get_session
from remindee.utils.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

_GOOGLE_CLIENT_CONFIG = {
    "installed": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"],
    }
}


class LocalAuthService:
    @staticmethod
    def register(username: str, email: str, password: str) -> User:
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        try:
            with get_session() as session:
                user = User(
                    username=username,
                    email=email.lower().strip(),
                    password_hash=pw_hash,
                    display_name=username,
                )
                session.add(user)
                session.flush()
                session.refresh(user)
                # detach so the object lives beyond this session
                session.expunge(user)
        except IntegrityError:
            raise ValueError("Email already registered")
        return user

    @staticmethod
    def login(email: str, password: str) -> Optional[User]:
        with get_session() as session:
            user = session.query(User).filter_by(email=email.lower().strip()).first()
            if user is None or user.password_hash is None:
                return None
            if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
                return None
            user.last_login = datetime.utcnow()
            session.flush()
            session.refresh(user)
            session.expunge(user)
        return user

    @staticmethod
    def email_exists(email: str) -> bool:
        with get_session() as session:
            return session.query(User).filter_by(email=email.lower().strip()).count() > 0


class GoogleAuthService:
    def __init__(self) -> None:
        self._flow: Optional[InstalledAppFlow] = None

    def create_flow(self) -> InstalledAppFlow:
        self._flow = InstalledAppFlow.from_client_config(
            _GOOGLE_CLIENT_CONFIG, scopes=GOOGLE_SCOPES
        )
        return self._flow

    def run_local_server(self) -> Optional[Credentials]:
        """Blocking call — must be run in a QThread."""
        if self._flow is None:
            self.create_flow()
        return self._flow.run_local_server(port=0, open_browser=True)

    def get_or_create_user(self, credentials: Credentials) -> User:
        try:
            resp = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {credentials.token}"},
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Failed to fetch Google user info: {exc}"
            ) from exc
        info = resp.json()

        google_id = info.get("sub", "")
        email = info.get("email", "").lower().strip()
        display_name = info.get("name", "")
        avatar_url = info.get("picture", "")

        expiry = None
        if credentials.expiry:
            expiry = credentials.expiry.replace(tzinfo=None)

        with get_session() as session:
            user = session.query(User).filter_by(google_id=google_id).first()
            if user is None:
                user = session.query(User).filter_by(email=email).first()
            if user is None:
                user = User(email=email)
                session.add(user)

            user.google_id = google_id
            user.google_access_token = credentials.token
            user.google_refresh_token = credentials.refresh_token
            user.token_expiry = expiry
            user.display_name = display_name
            user.avatar_url = avatar_url
            user.last_login = datetime.utcnow()
            session.flush()
            session.refresh(user)
            session.expunge(user)

        return user

    @staticmethod
    def refresh_credentials(user: User) -> Optional[Credentials]:
        if not user.google_refresh_token:
            return None
        creds = Credentials(
            token=user.google_access_token,
            refresh_token=user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
        )
        if creds.expired:
            creds.refresh(GoogleRequest())
            with get_session() as session:
                db_user = session.get(User, user.id)
                if db_user:
                    db_user.google_access_token = creds.token
                    if creds.expiry:
                        db_user.token_expiry = creds.expiry.replace(tzinfo=None)
        return creds

    @staticmethod
    def is_configured() -> bool:
        return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
