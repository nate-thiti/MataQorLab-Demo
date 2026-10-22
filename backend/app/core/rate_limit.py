from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _rate_limit_key(request: Request) -> str:
    auth = request.headers.get("Authorization", "").strip()
    if auth.startswith("Bearer ") and len(auth) > 20:
        return f"user:{auth[-48:]}"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key, default_limits=["120/minute"])
