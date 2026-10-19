from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import JWT_SECRET, JWT_TTL_HOURS

ALGORITHM = "HS256"


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=JWT_TTL_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
