import json
from datetime import datetime, timedelta
from pathlib import Path

from qingwu_core.ai import OpenAIProvider
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
