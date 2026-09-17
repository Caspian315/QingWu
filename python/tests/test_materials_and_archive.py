import json
from pathlib import Path
from zipfile import ZipFile

from qingwu_core.service import QingwuService


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
