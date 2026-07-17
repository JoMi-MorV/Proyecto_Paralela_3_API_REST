# app/errors.py
from datetime import datetime, timezone

from fastapi import Request


def _utc_timestamp() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond:06d}000Z"


def build_error(request: Request, status: int, detail: str, error_code: str, error_label: str):
    return {
        "detail": detail,
        "instance": str(request.url.path),
        "status": status,
        "title": "Bad Request" if status == 400 else "Internal Server Error",
        "type": f"https://developer.mozilla.org/es/docs/Web/HTTP/Reference/Status/{status}",
        "timestamp": _utc_timestamp(),
        "errorCode": error_code,
        "errorLabel": error_label,
        "method": request.method,
    }
