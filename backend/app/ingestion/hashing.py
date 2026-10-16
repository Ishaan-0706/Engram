from __future__ import annotations

import hashlib


def sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def decode_utf8_round_trip(raw: bytes) -> str:
    text = raw.decode("utf-8")
    if text.encode("utf-8") != raw:
        raise ValueError("source bytes are not a lossless UTF-8 round-trip")
    return text
