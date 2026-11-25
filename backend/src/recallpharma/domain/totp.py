"""Codes à usage unique basés sur le temps (TOTP, RFC 6238) : HMAC-SHA1, 6 chiffres, pas de 30 secondes.

Compatible avec les applications d'authentification courantes (FreeOTP, Google Authenticator, Microsoft Authenticator).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote, urlencode

DIGITS = 6
PERIOD = 30
WINDOW = 1  # tolérance d'un pas avant ou après (décalage d'horloge du téléphone)


def new_secret() -> str:
    """Secret de 160 bits, en base 32 sans bourrage (format attendu par les applications)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def code_at(secret: str, timestamp: float) -> str:
    return _code(secret, int(timestamp // PERIOD))


def verify(secret: str, code: str, timestamp: float, last_step: int | None = None) -> int | None:
    """Renvoie le pas accepté, ou None. Un pas déjà utilisé (ou antérieur) est refusé : pas de rejeu."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    now = int(timestamp // PERIOD)
    for step in range(now - WINDOW, now + WINDOW + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(_code(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "RecallPharma") -> str:
    label = quote(f"{issuer}:{account}")
    query = urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": PERIOD})
    return f"otpauth://totp/{label}?{query}"
