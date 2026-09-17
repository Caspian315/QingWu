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
