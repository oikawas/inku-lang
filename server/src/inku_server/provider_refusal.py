"""What a provider's refusal says, safe to write to the log."""

from __future__ import annotations

import json
import re
from typing import Any

_SECRET_LIKE = re.compile(r"\b(?:sk|key|AIza)[-_A-Za-z0-9*]{6,}")


def provider_error(raw: bytes) -> dict[str, Any]:
    """What a refusal says, without anything that could carry a key.

    OpenAI, Anthropic and Gemini all answer {"error": {...}}; the code, type,
    param and status fields name the reason. The message is kept short and with
    anything shaped like a key masked, since a 401 echoes part of the key.
    """
    try:
        error = json.loads(raw).get("error")
    except (ValueError, AttributeError):
        return {}
    if not isinstance(error, dict):
        return {}
    found = {key: error[key] for key in ("code", "type", "param", "status")
             if isinstance(error.get(key), (str, int)) and error.get(key) != ""}
    message = error.get("message")
    if isinstance(message, str) and message:
        found["message"] = _SECRET_LIKE.sub("***", message)[:240]
    return found
