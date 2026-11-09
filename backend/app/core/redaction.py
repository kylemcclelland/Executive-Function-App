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


def _redact_arg(value):
    if isinstance(value, str):
        return redact(value)
    if type(value).__name__ == "URL":  # httpx logs its URL as an object
        return redact(str(value))
    return value


class RedactOAuthParams(logging.Filter):
    """Redacts in place and keeps ``record.args`` the same shape: uvicorn's access formatter unpacks
    exactly five arguments, so replacing them with a pre-formatted message breaks every log line."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_arg(arg) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: _redact_arg(arg) for key, arg in record.args.items()}
        return True


def install_log_redaction() -> None:
    for name in ("uvicorn.access", "uvicorn.error", "httpx", "httpcore"):
        target = logging.getLogger(name)
        if not any(isinstance(f, RedactOAuthParams) for f in target.filters):
            target.addFilter(RedactOAuthParams())
