from pathlib import Path

from qingwu_core.paths import PROJECT_DIR
from qingwu_core.templates import TemplateRepository
from qingwu_core.errors import ValidationError


def test_builtin_templates_validate():
    repository = TemplateRepository()
    templates = repository.list()
    assert {item["id"] for item in templates} == {
        "activity-organization", "material-collection", "reimbursement"
    }


def test_templates_are_declarative_only():
    forbidden = {".py", ".js", ".ps1", ".sh", "command", "script"}
    for path in (PROJECT_DIR / "templates").glob("*.yaml"):
        lowered = path.read_text(encoding="utf-8").lower()
        assert not any(f"{word}:" in lowered for word in forbidden)


def test_template_rejects_archive_path_traversal(tmp_path):
    source = (PROJECT_DIR / "templates" / "material-collection.yaml").read_text(encoding="utf-8")
    malicious = source.replace("output_path: materials/提交材料", "output_path: ../escape")
    path = tmp_path / "malicious.yaml"
    path.write_text(malicious, encoding="utf-8")
    try:
        TemplateRepository().validate_file(path)
        assert False, "path traversal should be rejected"
    except ValidationError as exc:
        assert "不安全的归档路径" in str(exc)
