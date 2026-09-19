import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from qingwu_core.errors import ConflictError
from qingwu_core.service import QingwuService


PNG_BYTES = b"\x89PNG\r\n\x1a\nexample-image"


def test_material_hash_change_is_detected(tmp_path: Path):
    service = QingwuService(db_path=tmp_path / "test.sqlite3")
    try:
        affair = service.affair_create({"template_id": "material-collection", "title": "截图收集"})
        material = tmp_path / "张三-截图.png"
        material.write_bytes(b"first")
        imported = service.material_import({"affair_id": affair["id"], "path": str(material)})["materials"][0]
        service.material_assign({"id": imported["id"], "slot_id": "submissions"})
        assert not any(item["code"] == "material_changed" for item in service.affair_check({"affair_id": affair["id"]})["issues"])
        material.write_bytes(b"second")
        assert any(item["code"] == "material_changed" for item in service.affair_check({"affair_id": affair["id"]})["issues"])
    finally:
        service.close()


def test_archive_contains_manifest_and_hash_preserved(tmp_path: Path):
    service = QingwuService(db_path=tmp_path / "test.sqlite3")
    try:
        affair = service.affair_create({"template_id": "material-collection", "title": "青年大学习截图"})
        service.fact_confirm({"affair_id": affair["id"], "values": {
            "collection_name": "青年大学习截图",
            "contact_method": "13800138000",
        }})
        material = tmp_path / "截图.png"
        material.write_bytes(b"example image bytes")
        imported = service.material_import({"affair_id": affair["id"], "path": str(material)})["materials"][0]
        service.material_assign({"id": imported["id"], "slot_id": "submissions"})
        result = service.affair_export({"affair_id": affair["id"], "output": str(tmp_path / "out.zip")})
        with ZipFile(result["path"]) as archive:
            names = set(archive.namelist())
            assert "qingwu-manifest.json" in names
            assert "qingwu-checklist.html" in names
            assert "qingwu-checklist.pdf" in names
            material_name = next(name for name in names if name.startswith("materials/提交材料/"))
            assert archive.read(material_name) == material.read_bytes()
            manifest_text = archive.read("qingwu-manifest.json").decode("utf-8")
            manifest = json.loads(manifest_text)
            assert str(tmp_path) not in manifest_text
            assert manifest["confirmed_facts"] == {
                "collection_name": {
                    "label": "收集事项",
                    "value": "青年大学习截图",
                    "status": "confirmed",
                }
            }
    finally:
        service.close()


def test_duplicate_and_signature_mismatch_are_reported(tmp_path: Path):
    service = QingwuService(db_path=tmp_path / "test.sqlite3")
    try:
        affair = service.affair_create({"template_id": "material-collection", "title": "格式检查"})
        first = tmp_path / "截图一.png"
        second = tmp_path / "截图二.png"
        content = b"%PDF-1.4\nnot really an image"
        first.write_bytes(content)
        second.write_bytes(content)
        for path in (first, second):
            imported = service.material_import({"affair_id": affair["id"], "path": str(path)})["materials"][0]
            service.material_assign({"id": imported["id"], "slot_id": "submissions"})
        issues = service.affair_check({"affair_id": affair["id"]})["issues"]
        codes = {item["code"] for item in issues}
        assert "duplicate_material" in codes
        assert "material_signature_mismatch" in codes
    finally:
        service.close()


def test_import_does_not_move_or_modify_source_file(tmp_path: Path):
    service = QingwuService(db_path=tmp_path / "test.sqlite3")
    try:
        affair = service.affair_create({"template_id": "material-collection", "title": "源文件保护"})
        material = tmp_path / "示例截图.png"
        material.write_bytes(PNG_BYTES)
        imported = service.material_import({"affair_id": affair["id"], "path": str(material)})["materials"][0]
        assert material.exists()
        assert material.read_bytes() == PNG_BYTES
        assert imported["original_name"] == "示例截图.png"
        assert Path(imported["source_path"]).resolve() == material.resolve()
    finally:
        service.close()


def test_deleted_material_is_reported_missing(tmp_path: Path):
    service = QingwuService(db_path=tmp_path / "test.sqlite3")
    try:
        affair = service.affair_create({"template_id": "material-collection", "title": "材料缺失"})
        material = tmp_path / "待提交.png"
        material.write_bytes(PNG_BYTES)
        imported = service.material_import({"affair_id": affair["id"], "path": str(material)})["materials"][0]
        service.material_assign({"id": imported["id"], "slot_id": "submissions"})
        material.unlink()
        issues = service.affair_check({"affair_id": affair["id"]})["issues"]
        assert any(item["code"] == "material_missing" for item in issues)
        assert not any(item["code"] == "material_changed" for item in issues)
    finally:
        service.close()


def test_export_rejects_changed_source_and_renames_existing_zip(tmp_path: Path):
    service = QingwuService(db_path=tmp_path / "test.sqlite3")
    try:
        affair = service.affair_create({"template_id": "material-collection", "title": "导出冲突"})
        service.fact_confirm({"affair_id": affair["id"], "values": {"collection_name": "导出冲突收集"}})
        material = tmp_path / "归档材料.png"
        material.write_bytes(PNG_BYTES)
        imported = service.material_import({"affair_id": affair["id"], "path": str(material)})["materials"][0]
        service.material_assign({"id": imported["id"], "slot_id": "submissions"})

        first_zip = tmp_path / "out.zip"
        first_zip.write_bytes(b"existing-archive")
        exported = service.affair_export({"affair_id": affair["id"], "output": str(first_zip)})
        assert Path(exported["path"]).name == "out-2.zip"
        assert first_zip.read_bytes() == b"existing-archive"

        material.write_bytes(PNG_BYTES + b"-changed")
        with pytest.raises(ConflictError, match="导出时材料内容发生变化"):
            service.affair_export({"affair_id": affair["id"], "output": str(tmp_path / "changed.zip")})
        assert material.read_bytes() == PNG_BYTES + b"-changed"
    finally:
        service.close()


def test_sensitive_facts_and_absolute_paths_stay_out_of_archive(tmp_path: Path):
    service = QingwuService(db_path=tmp_path / "test.sqlite3")
    try:
        affair = service.affair_create({"template_id": "material-collection", "title": "脱敏归档"})
        service.fact_confirm({"affair_id": affair["id"], "values": {
            "collection_name": "脱敏归档收集",
            "contact_person": "李同学",
            "contact_method": "13800138000",
        }})
        material = tmp_path / "脱敏材料.png"
        material.write_bytes(PNG_BYTES)
        imported = service.material_import({"affair_id": affair["id"], "path": str(material)})["materials"][0]
        service.material_assign({"id": imported["id"], "slot_id": "submissions"})
        result = service.affair_export({"affair_id": affair["id"], "output": str(tmp_path / "private.zip")})
        with ZipFile(result["path"]) as archive:
            manifest_text = archive.read("qingwu-manifest.json").decode("utf-8")
            checklist = archive.read("qingwu-checklist.html").decode("utf-8")
            payload = "\n".join(archive.read(name).decode("utf-8", errors="ignore") for name in archive.namelist() if name.endswith((".json", ".html", ".txt", ".md")))
        assert "13800138000" not in manifest_text
        assert "contact_method" not in json.loads(manifest_text)["confirmed_facts"]
        assert str(tmp_path) not in payload
        assert material.name in checklist or "脱敏材料.png" in json.loads(manifest_text)["materials"][0]["name"]
        assert json.loads(manifest_text)["confirmed_facts"]["collection_name"]["value"] == "脱敏归档收集"
    finally:
        service.close()


def test_blocking_errors_can_stop_export(tmp_path: Path):
    service = QingwuService(db_path=tmp_path / "test.sqlite3")
    try:
        affair = service.affair_create({"template_id": "material-collection", "title": "阻断导出"})
        with pytest.raises(ConflictError, match="事务仍有阻断问题，不能导出"):
            service.affair_export({
                "affair_id": affair["id"],
                "output": str(tmp_path / "blocked.zip"),
                "allow_warnings": False,
            })
        assert not (tmp_path / "blocked.zip").exists()
    finally:
        service.close()


def test_reimbursement_requires_item_and_receipts(tmp_path: Path):
    service = QingwuService(db_path=tmp_path / "test.sqlite3")
    try:
        affair = service.affair_create({"template_id": "reimbursement", "title": "报销缺项"})
        service.fact_confirm({"affair_id": affair["id"], "values": {
            "project_name": "示例活动报销",
            "handler": "李同学",
            "organization": "计算机 2401 团支部",
            "description": "购买活动物料",
        }})
        missing_group = {item["code"] for item in service.affair_check({"affair_id": affair["id"]})["issues"]}
        assert "group_missing" in missing_group

        instance = service.group_add({
            "affair_id": affair["id"], "group_id": "expense_item",
            "title": "物料采购",
            "facts": {"purpose": "活动物料", "expense_date": "2026-10-18", "amount": "128.50"},
        })
        issues = service.affair_check({"affair_id": affair["id"]})["issues"]
        codes = {item["code"] for item in issues}
        assert "group_missing" not in codes
        assert "material_slot_missing" in codes
        assert any("发票或票据" in item["message"] for item in issues)
        assert any("支付凭证" in item["message"] for item in issues)

        invoice = tmp_path / "发票.png"
        proof = tmp_path / "支付凭证.png"
        invoice.write_bytes(PNG_BYTES)
        proof.write_bytes(PNG_BYTES + b"-proof")
        invoice_id = service.material_import({"affair_id": affair["id"], "path": str(invoice)})["materials"][0]["id"]
        proof_id = service.material_import({"affair_id": affair["id"], "path": str(proof)})["materials"][0]["id"]
        service.material_assign({"id": invoice_id, "slot_id": "invoice", "group_instance_id": instance["id"]})
        service.material_assign({"id": proof_id, "slot_id": "payment_proof", "group_instance_id": instance["id"]})
        complete = {item["code"] for item in service.affair_check({"affair_id": affair["id"]})["issues"]}
        assert "material_slot_missing" not in complete
        assert "group_missing" not in complete
    finally:
        service.close()

