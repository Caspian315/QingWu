from __future__ import annotations

import re
from typing import Any

from .util import TOKEN_RE, tokens_in


def field_value(field: dict[str, Any]) -> str | None:
    value = field.get("value")
    if field.get("status") != "confirmed" or value is None or str(value).strip() == "":
        return None
    return str(value)


def render_body(body: str, facts: dict[str, dict[str, Any]]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        field = facts.get(key)
        if not field:
            return f"【待填写：{key}】"
        value = field_value(field)
        return value if value is not None else f"【待填写：{field.get('label', key)}】"

    return TOKEN_RE.sub(replace, body)


def missing_required(required_keys: list[str], facts: dict[str, dict[str, Any]]) -> list[str]:
    return [key for key in required_keys if key not in facts or field_value(facts[key]) is None]


def validate_ai_body(body: str, required_tokens: list[str]) -> None:
    present = set(tokens_in(body))
    missing = set(required_tokens) - present
    if missing:
        raise ValueError(f"AI 返回的草稿遗漏事实引用节点：{', '.join(sorted(missing))}")
