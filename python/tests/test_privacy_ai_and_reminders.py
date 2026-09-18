import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from io import BytesIO

import pytest

from qingwu_core.ai import OpenAIProvider
from qingwu_core.errors import AIUnavailableError, ValidationError
from qingwu_core.service import QingwuService


def test_style_preview_flags_pii_and_confirm_can_delete_cache(tmp_path: Path):
    service = QingwuService(db_path=tmp_path / "style.sqlite3")
    try:
        texts = [
            "各位同学，请联系 13800138000。",
            "材料以学号 202612345678 命名。",
            "感谢大家配合。",
        ]
        preview = service.style_preview_upload({"texts": texts})
        assert preview["sample_count"] == 3
        assert {item["type"] for item in preview["pii_warnings"]} >= {"疑似手机号", "疑似学号"}
        imported = service.style_import_examples({"name": "团委通知", "document_kind": "notice", "texts": texts})
        card = {
            "tone": "正式但不生硬", "greeting": "各位同学：", "paragraph_length": "short",
            "heading_style": "序号加短标题", "emoji_policy": "不用", "common_phrases": ["感谢配合"],
            "forbidden_phrases": ["家人们"], "sign_off": "计算机学院团委", "punctuation": "中文全角标点",
        }
        confirmed = service.style_confirm_card({"id": imported["id"], "card": card, "delete_cache": True})
        assert confirmed["confirmed"] is True
        assert service.db.one("SELECT cache_text FROM style_cards WHERE id=?", (imported["id"],))["cache_text"] is None
    finally:
        service.close()


def test_reminders_are_deduplicated(tmp_path: Path):
    service = QingwuService(db_path=tmp_path / "reminders.sqlite3")
    try:
        affair = service.affair_create({"template_id": "activity-organization", "title": "提醒测试"})
        event = datetime.now().astimezone() + timedelta(minutes=20)
        service.fact_confirm({"affair_id": affair["id"], "values": {
            "activity_name": "提醒测试", "activity_date": event.date().isoformat(),
            "start_time": event.strftime("%H:%M"), "location": "活动室", "audience": "全体同学",
            "contact_person": "负责人", "organizer": "测试组织",
        }})
        first = service.timeline_due_reminders()
        second = service.timeline_due_reminders()
        assert any(item["title"] == "拍摄活动照片" and item["offset_minutes"] == 30 for item in first)
        assert second == []
    finally:
        service.close()


def test_openai_provider_sets_store_false(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"output": [{"content": [{"type": "output_text", "text": "{\"value\":\"ok\"}"}]}]}).encode()

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode("utf-8")))
        assert timeout == 90
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = OpenAIProvider("test-key").structured(
        instructions="test", input_text="test", schema_name="test_schema",
        schema={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False},
    )
    assert result == {"value": "ok"}
    assert captured["store"] is False
    assert captured["model"] == "gpt-5.4-mini"


SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "string"}},
    "required": ["value"],
    "additionalProperties": False,
}


def _call_provider():
    return OpenAIProvider("test-key").structured(
        instructions="test", input_text="test", schema_name="test_schema", schema=SCHEMA,
    )


def test_openai_provider_rejects_missing_api_key():
    with pytest.raises(AIUnavailableError, match="尚未配置 OpenAI API Key"):
        OpenAIProvider("")


def test_openai_provider_maps_http_errors(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=BytesIO(b'{"error":"invalid_api_key"}'))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(AIUnavailableError, match="OpenAI API 返回 HTTP 401") as exc_info:
        _call_provider()
    assert "invalid_api_key" in str(exc_info.value)
    assert "sk-" not in str(exc_info.value)


def test_openai_provider_maps_rate_limit_and_missing_model(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 429, "Too Many Requests", hdrs=None, fp=BytesIO(b"rate limited"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(AIUnavailableError, match="OpenAI API 返回 HTTP 429"):
        _call_provider()

    def missing_model(request, timeout):
        raise HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=BytesIO(b"model_not_found"))

    monkeypatch.setattr("urllib.request.urlopen", missing_model)
    with pytest.raises(AIUnavailableError, match="OpenAI API 返回 HTTP 404"):
        OpenAIProvider("test-key", model="not-a-real-model").structured(
            instructions="test", input_text="test", schema_name="test_schema", schema=SCHEMA,
        )


def test_openai_provider_maps_network_and_invalid_payloads(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: (_ for _ in ()).throw(URLError("timed out")))
    with pytest.raises(AIUnavailableError, match="无法连接 OpenAI API"):
        _call_provider()

    class EmptyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"output": []}).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: EmptyResponse())
    with pytest.raises(AIUnavailableError, match="OpenAI API 响应中没有可用文本"):
        _call_provider()

    class InvalidJsonResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"output": [{"content": [{"type": "output_text", "text": "not-json"}]}]}).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: InvalidJsonResponse())
    with pytest.raises(AIUnavailableError, match="OpenAI API 未返回有效的结构化 JSON"):
        _call_provider()


def confirmed_activity(service: QingwuService):
    affair = service.affair_create({"template_id": "activity-organization", "title": "十月主题团日"})
    service.fact_confirm({"affair_id": affair["id"], "values": {
        "activity_name": "十月主题团日活动", "activity_date": "2026-10-18",
        "start_time": "18:00", "location": "大学生活动中心 203",
        "audience": "计算机 2401 班全体同学", "contact_person": "张同学",
        "organizer": "计算机 2401 团支部",
    }})
    return service.affair_open({"id": affair["id"]})


def test_ai_draft_missing_fact_tokens_is_rejected(tmp_path: Path, monkeypatch):
    service = QingwuService(db_path=tmp_path / "ai-draft.sqlite3")
    try:
        affair = confirmed_activity(service)

        class FakeProvider:
            def __init__(self, api_key: str, model: str = "gpt-5.4-mini", timeout: int = 90):
                self.model = model

            def structured(self, **kwargs):
                return {"body": "活动将在大学生活动中心 203 举行，请按时参加。"}

        monkeypatch.setattr("qingwu_core.service.OpenAIProvider", FakeProvider)
        with pytest.raises(ValidationError, match="遗漏事实引用节点"):
            service.draft_generate({
                "affair_id": affair["id"], "document_id": "notice_full",
                "use_ai": True, "api_key": "sk-test-not-real",
            })
        latest = service.affair_open({"id": affair["id"]})
        assert latest["drafts"] == []
        run = service.db.one("SELECT purpose, success, error_code, model FROM ai_runs WHERE affair_id=?", (affair["id"],))
        assert run["purpose"] == "draft.generate"
        assert run["success"] == 0
        assert run["error_code"] == "missing_fact_tokens"
        assert run["model"] == "gpt-5.4-mini"
        assert "大学生活动中心 203" not in json.dumps(dict(run), ensure_ascii=False)
    finally:
        service.close()


def test_offline_draft_still_works_after_ai_failure(tmp_path: Path, monkeypatch):
    service = QingwuService(db_path=tmp_path / "offline.sqlite3")
    try:
        affair = confirmed_activity(service)

        class FailingProvider:
            def __init__(self, api_key: str, model: str = "gpt-5.4-mini", timeout: int = 90):
                self.model = model

            def structured(self, **kwargs):
                raise AIUnavailableError("无法连接 OpenAI API：timed out")

        monkeypatch.setattr("qingwu_core.service.OpenAIProvider", FailingProvider)
        with pytest.raises(AIUnavailableError, match="无法连接 OpenAI API"):
            service.draft_generate({
                "affair_id": affair["id"], "document_id": "notice_full",
                "use_ai": True, "api_key": "sk-test-not-real",
            })
        assert service.affair_open({"id": affair["id"]})["drafts"] == []

        offline = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
        assert offline["ai_generated"] == 0
        assert "{{location}}" in offline["body"]
        assert "大学生活动中心 203" in offline["rendered_body"]
        assert offline["status"] == "needs_review"
    finally:
        service.close()

