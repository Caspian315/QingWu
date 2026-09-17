from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .errors import QingwuError, ValidationError
from .service import QingwuService
from .templates import TemplateRepository


def _affair_context(value: str) -> tuple[QingwuService, str]:
    path = Path(value).expanduser()
    if path.is_dir():
        marker = path / ".qingwu-affair.json"
        if not marker.is_file():
            raise ValidationError(f"目录中没有 .qingwu-affair.json：{path}")
        data = json.loads(marker.read_text(encoding="utf-8"))
        return QingwuService(db_path=data["database"]), str(data["id"])
    service = QingwuService()
    return service, value


def human_check(result: dict[str, Any]) -> str:
    status = "通过" if result["ok"] else "未通过"
    lines = [f"事务检查：{status}", f"错误 {result['summary']['errors']}，警告 {result['summary']['warnings']}"]
    for issue in result["issues"]:
        marker = "错误" if issue["severity"] == "error" else "警告"
        lines.append(f"- [{marker}] {issue['message']}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qingwu", description="轻务维护者 CLI")
    parser.add_argument("--version", action="version", version="qingwu 0.1.0")
    area = parser.add_subparsers(dest="area", required=True)
    template = area.add_parser("template", help="事务模板工具")
    template_action = template.add_subparsers(dest="action", required=True)
    validate = template_action.add_parser("validate", help="校验 YAML 事务模板")
    validate.add_argument("path")
    affair = area.add_parser("affair", help="事务检查与归档")
    affair_action = affair.add_subparsers(dest="action", required=True)
    check = affair_action.add_parser("check", help="检查事务")
    check.add_argument("affair")
    check.add_argument("--format", choices=["human", "json"], default="human")
    export = affair_action.add_parser("export", help="导出事务归档")
    export.add_argument("affair")
    export.add_argument("--output", required=True)
    export.add_argument("--fail-on-errors", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    service: QingwuService | None = None
    try:
        if args.area == "template":
            template = TemplateRepository().validate_file(args.path)
            result = {"valid": True, "template": {key: template.get(key) for key in ("id", "version", "title", "description")}}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        service, affair_id = _affair_context(args.affair)
        if args.action == "check":
            result = service.affair_check({"affair_id": affair_id})
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json" else human_check(result))
            return 0 if result["ok"] else 2
        result = service.affair_export({
            "affair_id": affair_id, "output": args.output, "allow_warnings": not args.fail_on_errors,
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except QingwuError as exc:
        print(f"qingwu: {exc}", file=sys.stderr)
        return 2
    finally:
        if service:
            service.close()


if __name__ == "__main__":
    raise SystemExit(main())
