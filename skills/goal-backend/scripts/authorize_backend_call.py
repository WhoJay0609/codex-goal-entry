from __future__ import annotations

import argparse
import json
from typing import Any, Mapping

from goal_backend_common import authorize as _authorize, load_json_value


def authorize(request: Mapping[str, Any]) -> dict:
    return _authorize(request)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authorize one Goal backend capability call."
    )
    parser.add_argument("--authorization-json", required=True)
    args = parser.parse_args()
    result = authorize(load_json_value(args.authorization_json))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
