"""Password hashing, session tokens, and the current-user dependency.

This is deliberately plain email/password auth, not SSO — good enough for
"it just needs to work" while DKK's real requirements are still unknown.
When DKK is ready, the real target (per the architecture doc) is their own
SSO provider restricted to @dkkcinc.com; that's a provider swap behind
these same signup/login endpoints, not a rewrite of how the rest of the
app checks who's asking.

Every endpoint that currently trusts a client-supplied user_id should move
to Depends(get_current_user) instead — otherwise a login screen is
decorative, since anyone could still claim to be any user_id in a request
body.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

ALGORITHM = "HS256"
TOKEN_TTL_DAYS = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def _decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired session — please log in again.")


def get_current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not logged in.")

    user_id = _decode_token(authorization.removeprefix("Bearer "))
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session — please log in again.")
    return user
