"""Keeps OAuth authorization codes and tokens out of logs (uvicorn logs full request lines)."""

import logging
import re

_SECRET_PARAM = re.compile(
    r"([?&](?:code|state|access_token|refresh_token|id_token|client_secret|code_verifier))"
    r"=[^&\s\"]*",
    re.IGNORECASE,
)


def redact(text: str) -> str:
    return _SECRET_PARAM.sub(r"\1=REDACTED", text)


class RedactOAuthParams(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Format first: arguments are often objects (e.g. httpx.URL), not strings.
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            return True
        record.msg, record.args = redact(message), ()
        return True


def install_log_redaction() -> None:
    for name in ("uvicorn.access", "uvicorn.error", "httpx", "httpcore"):
        target = logging.getLogger(name)
        if not any(isinstance(f, RedactOAuthParams) for f in target.filters):
            target.addFilter(RedactOAuthParams())
