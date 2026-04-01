from __future__ import annotations

import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parent

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.main import app


def main() -> None:
    schema = app.openapi()
    rendered = json.dumps(schema, indent=2)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(f"{rendered}\n", encoding="utf-8")
        return

    print(rendered)


if __name__ == "__main__":
    main()
