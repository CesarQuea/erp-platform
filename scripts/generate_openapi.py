from __future__ import annotations

import json
from pathlib import Path

from app.bootstrap.application import create_app
from app.core.config.settings import Settings


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OPENAPI_BASELINE = REPOSITORY_ROOT / "contracts" / "api" / "v1" / "openapi.json"


def generate_openapi_document() -> dict[str, object]:
    app = create_app(settings=Settings(environment="test"))
    return app.openapi()


def render_openapi_document(document: dict[str, object]) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    OPENAPI_BASELINE.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_BASELINE.write_text(
        render_openapi_document(generate_openapi_document()),
        encoding="utf-8",
    )
    print(OPENAPI_BASELINE.relative_to(REPOSITORY_ROOT))


if __name__ == "__main__":
    main()
