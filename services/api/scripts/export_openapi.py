"""Export the application's OpenAPI contract without connecting to storage."""

from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))

create_app = import_module("health_api.main").create_app


def main() -> None:
    destination = ROOT / "contracts" / "openapi" / "openapi.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = create_app().openapi()
    destination.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
