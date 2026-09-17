from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from .errors import QingwuError
from .service import QingwuService


def response(request_id: Any, *, result: Any = None, error: dict[str, Any] | None = None) -> str:
    payload = {"id": request_id, "ok": error is None}
    if error is None:
        payload["result"] = result
    else:
        payload["error"] = error
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    service = QingwuService()
    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            request_id = None
            try:
                request = json.loads(line)
                request_id = request.get("id")
                method = request.get("method")
                if not isinstance(method, str):
                    raise ValueError("请求缺少 method")
                result = service.dispatch(method, request.get("params") or {})
                print(response(request_id, result=result), flush=True)
            except QingwuError as exc:
                print(response(request_id, error=exc.as_dict()), flush=True)
            except (ValueError, TypeError, KeyError) as exc:
                print(response(request_id, error={"code": "invalid_request", "message": str(exc)}), flush=True)
            except Exception as exc:  # Keep the sidecar alive, but do not expose paths or payloads.
                print(response(request_id, error={"code": "internal_error", "message": str(exc)}), flush=True)
                traceback.print_exc(file=sys.stderr)
    finally:
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
