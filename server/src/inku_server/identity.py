from __future__ import annotations

import unicodedata
from hashlib import sha256


def canonicalize_description(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.strip()


def description_hash(text: str) -> str:
    # dh1 is deterministic identity, not encryption, authentication, or proof of ownership.
    canonical = canonicalize_description(text)
    return "dh1:" + sha256(canonical.encode("utf-8")).hexdigest()
