"""Écrit le contrat OpenAPI : `python -m recallpharma.api.export_openapi ../web/openapi.json`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from recallpharma.api.app import create_app

if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    target.write_text(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Contrat écrit dans {target}", file=sys.stderr)
