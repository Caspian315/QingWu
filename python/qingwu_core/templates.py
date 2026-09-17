from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .errors import NotFoundError, ValidationError
from .paths import builtin_templates_dir, schema_path
from .util import safe_relative_path


class TemplateRepository:
    def __init__(self, directory: Path | None = None, schema_file: Path | None = None):
        self.directory = (directory or builtin_templates_dir()).resolve()
        schema = json.loads((schema_file or schema_path()).read_text(encoding="utf-8"))
        self.validator = Draft202012Validator(schema)

    def validate_file(self, path: str | Path) -> dict[str, Any]:
        source = Path(path).expanduser().resolve()
        try:
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ValidationError(f"无法读取模板 {source.name}：{exc}") from exc
        if not isinstance(data, dict):
            raise ValidationError("模板根节点必须是对象")
        errors = sorted(self.validator.iter_errors(data), key=lambda item: list(item.path))
        if errors:
            formatted = []
            for error in errors:
                location = ".".join(str(part) for part in error.absolute_path) or "<root>"
                formatted.append(f"{location}: {error.message}")
            raise ValidationError("模板校验失败：\n" + "\n".join(formatted))
        self._validate_semantics(data)
        data["_source_path"] = str(source)
        return data

    def _validate_semantics(self, data: dict[str, Any]) -> None:
        fact_keys = [item["key"] for item in data.get("facts", [])]
        if len(fact_keys) != len(set(fact_keys)):
            raise ValidationError("facts 中存在重复 key")
        document_ids = [item["id"] for item in data.get("documents", [])]
        if len(document_ids) != len(set(document_ids)):
            raise ValidationError("documents 中存在重复 id")
        task_ids = [item["id"] for item in data.get("tasks", [])]
        if len(task_ids) != len(set(task_ids)):
            raise ValidationError("tasks 中存在重复 id")
        stage_ids = {item["id"] for item in data.get("stages", [])}
        for task in data.get("tasks", []):
            if task["stage"] not in stage_ids:
                raise ValidationError(f"任务 {task['id']} 引用了不存在的阶段 {task['stage']}")
            relative_to = task.get("relative_to")
            if relative_to and relative_to not in fact_keys:
                raise ValidationError(f"任务 {task['id']} 引用了不存在的事实 {relative_to}")
        for document in data.get("documents", []):
            unknown = set(document.get("required_facts", [])) - set(fact_keys)
            if unknown:
                raise ValidationError(f"文案 {document['id']} 引用了不存在的事实：{', '.join(sorted(unknown))}")
        for slot in data.get("material_slots", []):
            try:
                safe_relative_path(slot["output_path"])
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        for group in data.get("groups", []):
            for slot in group.get("material_slots", []):
                try:
                    safe_relative_path(slot["output_path"])
                except ValueError as exc:
                    raise ValidationError(f"可重复项目 {group['id']}：{exc}") from exc

    def get(self, template_id: str) -> dict[str, Any]:
        for suffix in (".yaml", ".yml"):
            candidate = self.directory / f"{template_id}{suffix}"
            if candidate.exists():
                return self.validate_file(candidate)
        raise NotFoundError(f"未找到事务模板：{template_id}")

    def list(self) -> list[dict[str, Any]]:
        result = []
        for path in sorted((*self.directory.glob("*.yaml"), *self.directory.glob("*.yml"))):
            item = self.validate_file(path)
            result.append({key: item.get(key) for key in ("id", "version", "title", "description")})
        return result
