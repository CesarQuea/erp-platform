from __future__ import annotations

import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.bootstrap.application import create_app
from app.core.config.settings import Settings


OPENAPI_BASELINE = REPOSITORY_ROOT / "contracts" / "api" / "v1" / "openapi.json"


def generate_openapi_document() -> dict[str, object]:
    app = create_app(settings=Settings(environment="test"))
    return app.openapi()


def render_openapi_document(document: dict[str, object]) -> str:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) + "\n"


def main() -> None:
    OPENAPI_BASELINE.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_BASELINE.write_text(
        render_openapi_document(generate_openapi_document()),
        encoding="utf-8",
    )
    print(OPENAPI_BASELINE.relative_to(REPOSITORY_ROOT))


if __name__ == "__main__":
    main()
