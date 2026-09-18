from pathlib import Path
import re

import pytest

from qingwu_core.errors import ConflictError
from qingwu_core.service import QingwuService


@pytest.fixture()
def service(tmp_path: Path):
    instance = QingwuService(db_path=tmp_path / "test.sqlite3")
    yield instance
    instance.close()


def confirmed_activity(service: QingwuService):
    affair = service.affair_create({"template_id": "activity-organization", "title": "十月主题团日"})
    values = {
        "activity_name": "十月主题团日活动", "activity_date": "2026-10-18",
        "start_time": "18:00", "location": "大学生活动中心 203",
        "audience": "计算机 2401 班全体同学", "contact_person": "张同学",
        "organizer": "计算机 2401 团支部",
    }
    service.fact_confirm({"affair_id": affair["id"], "values": values})
    return service.affair_open({"id": affair["id"]})


def test_missing_facts_never_get_invented(service: QingwuService):
    affair = service.affair_create({"template_id": "activity-organization", "title": "测试事务"})
    draft = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
    assert draft["status"] == "missing_facts"
    assert "【待填写：活动日期】" in draft["rendered_body"]
    with pytest.raises(ConflictError):
        service.draft_mark_ready({"id": draft["id"]})


def test_only_affected_draft_becomes_stale(service: QingwuService):
    affair = confirmed_activity(service)
    notice = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
    completion = service.draft_generate({"affair_id": affair["id"], "document_id": "article_recap"})
    service.fact_update({"affair_id": affair["id"], "key": "start_time", "value": "19:00"})
    latest = service.affair_open({"id": affair["id"]})["drafts"]
    by_id = {item["id"]: item for item in latest}
    assert by_id[notice["id"]]["status"] == "stale"
    assert by_id[completion["id"]]["status"] != "stale"


def test_changed_value_requires_reconfirmation(service: QingwuService):
    affair = confirmed_activity(service)
    changed = service.fact_update({"affair_id": affair["id"], "key": "start_time", "value": "19:00"})
    assert changed["facts"]["start_time"]["status"] == "changed"
    draft = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
    assert "【待填写：开始时间】" in draft["rendered_body"]
    service.fact_confirm({"affair_id": affair["id"], "key": "start_time", "value": "19:00"})
    new_draft = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
    assert "19:00" in new_draft["rendered_body"]


def test_manual_version_and_locked_paragraph_survive_regeneration(service: QingwuService):
    affair = confirmed_activity(service)
    first = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
    body = first["body"] + "\n\n这是一段必须保留的人工说明。"
    manual = service.draft_update({
        "id": first["id"], "body": body, "locked_paragraphs": [len(re.split(r"\n{2,}", body.strip())) - 1],
    })
    regenerated = service.draft_generate({
        "affair_id": affair["id"], "document_id": "notice_full", "preserve_locked_from": manual["id"],
    })
    assert regenerated["version"] == 3
    assert "这是一段必须保留的人工说明。" in regenerated["body"]
    assert regenerated["locked_blocks"][0]["text"] == "这是一段必须保留的人工说明。"


def test_conflicting_locations_are_not_auto_confirmed(service: QingwuService, monkeypatch):
    affair = service.affair_create({"template_id": "activity-organization", "title": "地点冲突测试"})

    class FakeProvider:
        def __init__(self, api_key: str, model: str = "gpt-5.4-mini", timeout: int = 90):
            self.model = model

        def structured(self, **kwargs):
            return {
                "candidates": [],
                "conflicts": [{
                    "key": "location",
                    "values": ["大学生活动中心 203", "图书馆报告厅"],
                    "reason": "同一来源出现两个不同地点",
                }],
            }

    monkeypatch.setattr("qingwu_core.service.OpenAIProvider", FakeProvider)
    extracted = service.fact_extract({
        "affair_id": affair["id"],
        "source_text": "请于大学生活动中心 203 集合；另一份通知写的是图书馆报告厅。",
        "api_key": "sk-test-not-real",
    })
    location = extracted["facts"]["location"]
    assert location["status"] == "conflicting"
    assert location["value"] is None
    assert location["conflict"]["values"] == ["大学生活动中心 203", "图书馆报告厅"]

    service.fact_confirm({"affair_id": affair["id"], "values": {
        "activity_name": "十月主题团日活动", "activity_date": "2026-10-18",
        "start_time": "18:00", "audience": "计算机 2401 班全体同学",
        "contact_person": "张同学", "organizer": "计算机 2401 团支部",
    }})
    latest = service.affair_open({"id": affair["id"]})
    assert latest["facts"]["location"]["status"] == "conflicting"

    draft = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
    assert draft["status"] == "missing_facts"
    assert "【待填写：活动地点】" in draft["rendered_body"]
    assert "大学生活动中心 203" not in draft["rendered_body"]
    assert "图书馆报告厅" not in draft["rendered_body"]
    with pytest.raises(ConflictError):
        service.draft_mark_ready({"id": draft["id"]})


def test_relative_date_stays_extracted_until_confirmed(service: QingwuService, monkeypatch):
    affair = service.affair_create({"template_id": "activity-organization", "title": "相对日期测试"})

    class FakeProvider:
        def __init__(self, api_key: str, model: str = "gpt-5.4-mini", timeout: int = 90):
            self.model = model

        def structured(self, **kwargs):
            return {
                "candidates": [{
                    "key": "activity_date",
                    "value": "2026-10-23",
                    "original_text": "本周五",
                    "confidence": 0.6,
                    "needs_date_confirmation": True,
                }],
                "conflicts": [],
            }

    monkeypatch.setattr("qingwu_core.service.OpenAIProvider", FakeProvider)
    extracted = service.fact_extract({
        "affair_id": affair["id"],
        "source_text": "团日活动改到本周五晚上。",
        "api_key": "sk-test-not-real",
    })
    activity_date = extracted["facts"]["activity_date"]
    assert activity_date["status"] == "extracted"
    assert activity_date["value"] == "2026-10-23"
    assert activity_date["source_text"] == "本周五"
    assert activity_date["needs_date_confirmation"] is True

    service.fact_confirm({"affair_id": affair["id"], "values": {
        "activity_name": "十月主题团日活动", "start_time": "18:00",
        "location": "大学生活动中心 203", "audience": "计算机 2401 班全体同学",
        "contact_person": "张同学", "organizer": "计算机 2401 团支部",
    }})
    latest = service.affair_open({"id": affair["id"]})
    assert latest["facts"]["activity_date"]["status"] == "extracted"
    assert latest["facts"]["activity_date"]["source_text"] == "本周五"

    draft = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
    assert draft["status"] == "missing_facts"
    assert "【待填写：活动日期】" in draft["rendered_body"]
    assert "2026-10-23" not in draft["rendered_body"]
    assert "本周五" not in draft["rendered_body"]
    with pytest.raises(ConflictError):
        service.draft_mark_ready({"id": draft["id"]})

    service.fact_confirm({"affair_id": affair["id"], "key": "activity_date", "value": "2026-10-23"})
    confirmed = service.affair_open({"id": affair["id"]})
    assert confirmed["facts"]["activity_date"]["status"] == "confirmed"
    new_draft = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
    assert "2026-10-23" in new_draft["rendered_body"]
    assert "本周五" not in new_draft["rendered_body"]


def test_old_draft_versions_remain_recoverable(service: QingwuService):
    affair = confirmed_activity(service)
    first = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
    second = service.draft_update({
        "id": first["id"],
        "body": first["body"] + "\n\n第二版补充：请携带学生证。",
    })
    compared = service.draft_compare_versions({
        "affair_id": affair["id"], "document_id": "notice_full",
    })
    versions = compared["versions"]
    assert [item["version"] for item in versions] == [1, 2]
    assert versions[0]["id"] == first["id"]
    assert versions[0]["body"] == first["body"]
    assert "第二版补充：请携带学生证。" not in versions[0]["body"]
    assert "第二版补充：请携带学生证。" in versions[1]["body"]

    restored = service.draft_update({"id": first["id"], "body": first["body"]})
    assert restored["version"] == 3
    assert restored["body"] == first["body"].strip()
    after_restore = service.draft_compare_versions({
        "affair_id": affair["id"], "document_id": "notice_full",
    })
    assert [item["version"] for item in after_restore["versions"]] == [1, 2, 3]
    assert after_restore["versions"][0]["body"] == first["body"]
    assert after_restore["versions"][1]["id"] == second["id"]
    assert after_restore["versions"][2]["body"] == first["body"].strip()
    assert "第二版补充：请携带学生证。" not in restored["body"]


def test_notice_and_preview_share_the_same_confirmed_facts(service: QingwuService):
    affair = confirmed_activity(service)
    notice = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
    preview = service.draft_generate({"affair_id": affair["id"], "document_id": "article_preview"})
    assert "大学生活动中心 203" in notice["rendered_body"]
    assert "大学生活动中心 203" in preview["rendered_body"]
    assert "2026-10-18" in notice["rendered_body"]
    assert "2026-10-18" in preview["rendered_body"]
    assert "18:00" in notice["rendered_body"]
    assert "18:00" in preview["rendered_body"]

    service.fact_update({"affair_id": affair["id"], "key": "location", "value": "图书馆报告厅"})
    latest = {item["id"]: item for item in service.affair_open({"id": affair["id"]})["drafts"]}
    assert latest[notice["id"]]["status"] == "stale"
    assert latest[preview["id"]]["status"] == "stale"
    assert "【待填写：活动地点】" in latest[notice["id"]]["rendered_body"]
    assert "【待填写：活动地点】" in latest[preview["id"]]["rendered_body"]
    assert "图书馆报告厅" not in latest[notice["id"]]["rendered_body"]
    assert "图书馆报告厅" not in latest[preview["id"]]["rendered_body"]

    service.fact_confirm({"affair_id": affair["id"], "key": "location", "value": "图书馆报告厅"})
    new_notice = service.draft_generate({"affair_id": affair["id"], "document_id": "notice_full"})
    new_preview = service.draft_generate({"affair_id": affair["id"], "document_id": "article_preview"})
    assert "图书馆报告厅" in new_notice["rendered_body"]
    assert "图书馆报告厅" in new_preview["rendered_body"]
    assert "大学生活动中心 203" not in new_notice["rendered_body"]
    assert "大学生活动中心 203" not in new_preview["rendered_body"]

