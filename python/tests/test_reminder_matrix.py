from datetime import datetime, timedelta, timezone
from pathlib import Path

from qingwu_core.service import QingwuService


class FrozenDateTime(datetime):
    current = datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.current if tz is None else cls.current.astimezone(tz)


def reminder_task(service: QingwuService, due: datetime) -> tuple[str, str]:
    affair = service.affair_create({"template_id": "material-collection", "title": "提醒矩阵"})
    task = affair["tasks"][0]
    service.timeline_update_task({
        "id": task["id"],
        "due_at": due.isoformat(),
        "reminder_offsets": [1440, 120, 0],
    })
    return affair["id"], task["id"]


def offsets(reminders: list[dict[str, object]]) -> list[int]:
    return [int(item["offset_minutes"]) for item in reminders]


def test_24_hour_2_hour_and_due_reminders_fire_once(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("qingwu_core.service.datetime", FrozenDateTime)
    service = QingwuService(db_path=tmp_path / "matrix.sqlite3")
    due = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
    try:
        reminder_task(service, due)

        FrozenDateTime.current = due - timedelta(hours=24)
        assert offsets(service.timeline_due_reminders()) == [1440]
        assert service.timeline_due_reminders() == []

        FrozenDateTime.current = due - timedelta(hours=2)
        assert offsets(service.timeline_due_reminders()) == [120]
        assert service.timeline_due_reminders() == []

        FrozenDateTime.current = due
        assert offsets(service.timeline_due_reminders()) == [0]
        assert service.timeline_due_reminders() == []
    finally:
        service.close()


def test_restart_keeps_sent_reminders_deduplicated(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("qingwu_core.service.datetime", FrozenDateTime)
    database = tmp_path / "restart.sqlite3"
    due = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
    FrozenDateTime.current = due - timedelta(hours=24)

    service = QingwuService(db_path=database)
    try:
        reminder_task(service, due)
        assert offsets(service.timeline_due_reminders()) == [1440]
    finally:
        service.close()

    restarted = QingwuService(db_path=database)
    try:
        assert restarted.timeline_due_reminders() == []
    finally:
        restarted.close()


def test_resume_emits_only_latest_missed_reminder(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("qingwu_core.service.datetime", FrozenDateTime)
    service = QingwuService(db_path=tmp_path / "resume.sqlite3")
    due = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
    try:
        reminder_task(service, due)

        # Simulate the first poll after the computer slept across every trigger.
        FrozenDateTime.current = due + timedelta(hours=1)
        assert offsets(service.timeline_due_reminders()) == [0]
        assert service.timeline_due_reminders() == []
    finally:
        service.close()


def test_deadline_change_rearms_reminders(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("qingwu_core.service.datetime", FrozenDateTime)
    service = QingwuService(db_path=tmp_path / "deadline.sqlite3")
    original_due = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
    changed_due = original_due + timedelta(days=1)
    try:
        _, task_id = reminder_task(service, original_due)
        FrozenDateTime.current = original_due - timedelta(hours=24)
        assert offsets(service.timeline_due_reminders()) == [1440]

        updated = service.timeline_update_task({"id": task_id, "due_at": changed_due.isoformat()})
        assert updated["sent_reminders"] == []
        FrozenDateTime.current = changed_due - timedelta(hours=24)
        assert offsets(service.timeline_due_reminders()) == [1440]
    finally:
        service.close()


def test_completed_or_disabled_tasks_do_not_remind(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("qingwu_core.service.datetime", FrozenDateTime)
    due = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
    FrozenDateTime.current = due
    service = QingwuService(db_path=tmp_path / "completed.sqlite3")
    try:
        _, completed_id = reminder_task(service, due)
        service.timeline_update_task({"id": completed_id, "completed": True})

        _, disabled_id = reminder_task(service, due)
        service.timeline_update_task({"id": disabled_id, "reminder_enabled": False})

        assert service.timeline_due_reminders() == []
    finally:
        service.close()
