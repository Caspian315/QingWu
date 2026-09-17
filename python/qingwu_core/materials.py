from __future__ import annotations

from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from .util import sha256_file


def inspect_file(path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"材料文件不存在：{path}")
    stat = path.stat()
    return {
        "source_path": str(path),
        "original_name": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "sha256": sha256_file(path),
    }


def recommend_slots(file_info: dict[str, Any], template: dict[str, Any]) -> list[dict[str, Any]]:
    name = str(file_info["original_name"]).lower()
    extension = str(file_info["extension"]).lower()
    suggestions = []
    for slot in template.get("material_slots", []):
        allowed = {str(item).lower() for item in slot.get("extensions", [])}
        keywords = [str(item).lower() for item in slot.get("filename_keywords", [])]
        extension_score = 2 if not allowed or extension in allowed else -4
        keyword_hits = [keyword for keyword in keywords if keyword and keyword in name]
        score = extension_score + len(keyword_hits) * 3
        if score > 0:
            suggestions.append({
                "slot_id": slot["id"], "title": slot["title"], "score": score,
                "reasons": ([f"扩展名 {extension} 符合"] if extension_score > 0 else [])
                + ([f"文件名包含 {', '.join(keyword_hits)}"] if keyword_hits else []),
            })
    suggestions.sort(key=lambda item: (-item["score"], item["title"]))
    return suggestions


def check_material_integrity(material: dict[str, Any]) -> tuple[str, str | None]:
    path = Path(material["source_path"])
    if not path.is_file():
        return "missing", None
    current_hash = sha256_file(path)
    return ("ok", current_hash) if current_hash == material["sha256"] else ("changed", current_hash)


def detected_extension(path_value: str | Path) -> str | None:
    path = Path(path_value)
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return None
    if header.startswith(b"%PDF-"):
        return ".pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"PK\x03\x04"):
        try:
            with ZipFile(path) as archive:
                names = archive.namelist()
            if any(name.startswith("word/") for name in names):
                return ".docx"
            if any(name.startswith("xl/") for name in names):
                return ".xlsx"
        except (BadZipFile, OSError):
            pass
        return ".zip"
    return None
