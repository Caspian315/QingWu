from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .errors import AIUnavailableError


class OpenAIProvider:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, model: str = "gpt-5.4-mini", timeout: int = 90):
        if not api_key:
            raise AIUnavailableError("尚未配置 OpenAI API Key", reason="missing_api_key")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def structured(self, *, instructions: str, input_text: str, schema_name: str,
                   schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "store": False,
            "instructions": instructions,
            "input": input_text,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise AIUnavailableError(
                f"OpenAI API 返回 HTTP {exc.code}：{detail}", reason=f"http_{exc.code}",
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AIUnavailableError(f"无法连接 OpenAI API：{exc}", reason="network") from exc
        output_text = self._output_text(result)
        try:
            return json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise AIUnavailableError("OpenAI API 未返回有效的结构化 JSON", reason="invalid_json") from exc

    @staticmethod
    def _output_text(result: dict[str, Any]) -> str:
        for output in result.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        raise AIUnavailableError("OpenAI API 响应中没有可用文本", reason="empty_response")


def fact_extraction_schema(fact_definitions: list[dict[str, Any]]) -> dict[str, Any]:
    allowed = [item["key"] for item in fact_definitions]
    return {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "enum": allowed},
                        "value": {"type": "string"},
                        "original_text": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "needs_date_confirmation": {"type": "boolean"},
                    },
                    "required": ["key", "value", "original_text", "confidence", "needs_date_confirmation"],
                    "additionalProperties": False,
                },
            },
            "conflicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "enum": allowed},
                        "values": {"type": "array", "items": {"type": "string"}},
                        "reason": {"type": "string"},
                    },
                    "required": ["key", "values", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["candidates", "conflicts"],
        "additionalProperties": False,
    }


STYLE_CARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tone": {"type": "string"},
        "greeting": {"type": "string"},
        "paragraph_length": {"type": "string", "enum": ["short", "medium", "long"]},
        "heading_style": {"type": "string"},
        "emoji_policy": {"type": "string"},
        "common_phrases": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
        "forbidden_phrases": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
        "sign_off": {"type": "string"},
        "punctuation": {"type": "string"},
    },
    "required": ["tone", "greeting", "paragraph_length", "heading_style", "emoji_policy",
                 "common_phrases", "forbidden_phrases", "sign_off", "punctuation"],
    "additionalProperties": False,
}
