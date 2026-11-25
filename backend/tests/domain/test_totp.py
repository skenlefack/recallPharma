"""TOTP : vecteurs de la RFC 6238 (SHA-1), fenêtre de tolérance, anti-rejeu."""

from __future__ import annotations

import base64

from recallpharma.domain import totp

# Secret de la RFC 6238 (« 12345678901234567890 ») ; codes de référence tronqués à 6 chiffres.
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")


def test_rfc6238_vectors() -> None:
    assert totp.code_at(RFC_SECRET, 59) == "287082"
    assert totp.code_at(RFC_SECRET, 1111111109) == "081804"
    assert totp.code_at(RFC_SECRET, 1234567890) == "005924"
    assert totp.code_at(RFC_SECRET, 2000000000) == "279037"


def test_window_and_replay() -> None:
    now = 1_700_000_000.0
    previous = totp.code_at(RFC_SECRET, now - 30)
    step = totp.verify(RFC_SECRET, previous, now)
    assert step == int(now // 30) - 1
    assert totp.verify(RFC_SECRET, previous, now, last_step=step) is None  # déjà utilisé
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, now - 90), now) is None  # trop ancien
    assert totp.verify(RFC_SECRET, "12345", now) is None
    assert totp.verify(RFC_SECRET, "abcdef", now) is None


def test_provisioning_uri() -> None:
    secret = totp.new_secret()
    assert len(secret) == 32
    uri = totp.provisioning_uri(secret, "demo@exemple.fr")
    assert uri.startswith("otpauth://totp/RecallPharma%3Ademo%40exemple.fr?")
    assert f"secret={secret}" in uri
