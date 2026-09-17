from __future__ import annotations

from pathlib import Path

from .errors import ValidationError


def extract_text(path_value: str | Path) -> str:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValidationError(f"历史文案文件不存在：{path}")
    extension = path.suffix.lower()
    try:
        if extension in {".txt", ".md"}:
            return path.read_text(encoding="utf-8")
        if extension == ".docx":
            from docx import Document
            document = Document(path)
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        if extension == ".pdf":
            from pypdf import PdfReader
            return "\n".join((page.extract_text() or "") for page in PdfReader(path).pages)
    except Exception as exc:
        raise ValidationError(f"提取 {path.name} 文本失败：{exc}") from exc
    raise ValidationError(f"不支持的历史文案格式：{extension or '无扩展名'}")
