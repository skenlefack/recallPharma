"""Normalisation des identifiants réglementaires."""

from __future__ import annotations

import re


def normalise_ma_number(number: str) -> str:
    """RG-01 : comparaison insensible à la casse, aux espaces et aux séparateurs."""
    return re.sub(r"[\s\-_/.]", "", number).upper()
