from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .ai import STYLE_CARD_SCHEMA, OpenAIProvider, fact_extraction_schema
from .archive import build_manifest, export_affair
from .database import Database
from .drafting import field_value, missing_required, render_body, validate_ai_body
from .errors import ConflictError, NotFoundError, ValidationError
from .materials import check_material_integrity, detected_extension, inspect_file, recommend_slots
from .templates import TemplateRepository
from .text_import import extract_text
from .util import json_dumps, json_loads, tokens_in, utc_now


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in list(result):
        if key.endswith("_json"):
            result[key[:-5]] = json_loads(result.pop(key), [])
        elif key in {"completed", "reminder_enabled", "ai_generated", "ai_used", "archived", "confirmed"}:
            result[key] = bool(result[key])
    return result


class QingwuService:
    def __init__(self, db_path: str | Path | None = None, template_dir: str | Path | None = None):
        self.db = Database(db_path)
        self.templates = TemplateRepository(Path(template_dir) if template_dir else None)

    def close(self) -> None:
        self.db.close()

    # Profiles and style cards -------------------------------------------------
    def profile_create(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip()
        if not name:
            raise ValidationError("组织档案名称不能为空")
        now, profile_id = utc_now(), _id("profile")
        data = dict(params.get("data") or {})
        organization = str(params.get("organization", "")).strip()
        self.db.execute(
            "INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?)",
            (profile_id, name, organization, json_dumps(data), now, now),
        )
        return self._profile(profile_id)

    def profile_update(self, params: dict[str, Any]) -> dict[str, Any]:
        profile = self._profile(str(params.get("id", "")))
        name = str(params.get("name", profile["name"])).strip()
        if not name:
            raise ValidationError("组织档案名称不能为空")
        organization = str(params.get("organization", profile["organization"])).strip()
        data = params.get("data", profile["data"])
        self.db.execute(
            "UPDATE profiles SET name=?, organization=?, data_json=?, updated_at=? WHERE id=?",
            (name, organization, json_dumps(data), utc_now(), profile["id"]),
        )
        return self._profile(profile["id"])

    def _profile(self, profile_id: str) -> dict[str, Any]:
        row = self.db.one("SELECT * FROM profiles WHERE id=?", (profile_id,))
        if not row:
            raise NotFoundError(f"未找到组织档案：{profile_id}")
        row["data"] = json_loads(row.pop("data_json"), {})
        return row

    def style_preview_upload(self, params: dict[str, Any]) -> dict[str, Any]:
        examples = self._load_examples(params)
        combined = "\n\n--- 样本分隔 ---\n\n".join(examples)
        pii = []
        patterns = {
            "疑似手机号": r"(?<!\d)1[3-9]\d{9}(?!\d)",
            "疑似学号": r"(?<!\d)\d{8,14}(?!\d)",
            "疑似邮箱": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        }
        for label, pattern in patterns.items():
            matches = re.findall(pattern, combined)
            if matches:
                pii.append({"type": label, "count": len(matches), "examples": matches[:3]})
        return {
            "sample_count": len(examples), "text_length": len(combined), "pii_warnings": pii,
            "preview": combined[:3000], "truncated": len(combined) > 3000,
        }

    def style_import_examples(self, params: dict[str, Any]) -> dict[str, Any]:
        examples = self._load_examples(params)
        if not examples:
            raise ValidationError("至少需要一篇历史文案")
        now, card_id = utc_now(), _id("style")
        name = str(params.get("name", "新风格卡")).strip() or "新风格卡"
        kind = str(params.get("document_kind", "notice"))
        cache = "\n\n--- 样本分隔 ---\n\n".join(examples)
        empty_card = {
            "tone": "", "greeting": "", "paragraph_length": "short", "heading_style": "",
            "emoji_policy": "", "common_phrases": [], "forbidden_phrases": [], "sign_off": "",
            "punctuation": "中文全角标点",
        }
        self.db.execute(
            "INSERT INTO style_cards VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
            (card_id, params.get("profile_id"), name, kind, json_dumps(empty_card), len(examples), cache, now, now),
        )
        return self._style_card(card_id, include_cache=False)

    def style_generate_card(self, params: dict[str, Any]) -> dict[str, Any]:
        card = self._style_card(str(params.get("id", "")), include_cache=True)
        if card["sample_count"] < 3 and not params.get("allow_few_samples"):
            raise ValidationError("建议至少导入 3 篇同组织、同类型的认可文案；如要继续，请明确允许少样本分析")
        provider = OpenAIProvider(str(params.get("api_key", "")), str(params.get("model", "gpt-5.4-mini")))
        generated = provider.structured(
            instructions=("你是中文组织文案风格分析器。只总结稳定、可复用的表达风格；不要复述姓名、电话、学号或具体活动事实。"
                          "不同样本矛盾时采取保守描述。"),
            input_text=f"文案类型：{card['document_kind']}\n\n{card['cache_text']}",
            schema_name="qingwu_style_card", schema=STYLE_CARD_SCHEMA,
        )
        self.db.execute(
            "UPDATE style_cards SET card_json=?, confirmed=0, updated_at=? WHERE id=?",
            (json_dumps(generated), utc_now(), card["id"]),
        )
        self._record_ai(None, "style.generate_card", provider.model, True)
        return self._style_card(card["id"], include_cache=False)

    def style_confirm_card(self, params: dict[str, Any]) -> dict[str, Any]:
        card = self._style_card(str(params.get("id", "")), include_cache=True)
        value = params.get("card", card["card"])
        required = set(STYLE_CARD_SCHEMA["required"])
        if not isinstance(value, dict) or required - set(value):
            raise ValidationError("风格卡字段不完整")
        delete_cache = bool(params.get("delete_cache", True))
        self.db.execute(
            "UPDATE style_cards SET card_json=?, confirmed=1, cache_text=?, updated_at=? WHERE id=?",
            (json_dumps(value), None if delete_cache else card.get("cache_text"), utc_now(), card["id"]),
        )
        return self._style_card(card["id"], include_cache=False)

    def _style_card(self, card_id: str, *, include_cache: bool) -> dict[str, Any]:
        row = self.db.one("SELECT * FROM style_cards WHERE id=?", (card_id,))
        if not row:
            raise NotFoundError(f"未找到风格卡：{card_id}")
        row["card"] = json_loads(row.pop("card_json"), {})
        row["confirmed"] = bool(row["confirmed"])
        if not include_cache:
            row.pop("cache_text", None)
        return row

    def style_list(self, _params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows = self.db.all("SELECT id FROM style_cards ORDER BY updated_at DESC")
        return [self._style_card(row["id"], include_cache=False) for row in rows]

    def style_open(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._style_card(str(params.get("id", "")), include_cache=False)

    @staticmethod
    def _load_examples(params: dict[str, Any]) -> list[str]:
        texts = [str(item).strip() for item in params.get("texts", []) if str(item).strip()]
        for path in params.get("paths", []):
            extracted = extract_text(path).strip()
            if extracted:
                texts.append(extracted)
        return texts

    # Templates and affairs ----------------------------------------------------
    def template_validate(self, params: dict[str, Any]) -> dict[str, Any]:
        template = self.templates.validate_file(str(params["path"]))
        return {"valid": True, "template": {key: template.get(key) for key in ("id", "version", "title", "description")}}

    def template_list(self, _params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self.templates.list()

    def affair_create(self, params: dict[str, Any]) -> dict[str, Any]:
        template = self.templates.get(str(params.get("template_id", "")))
        title = str(params.get("title", "")).strip()
        if not title:
            raise ValidationError("事务名称不能为空")
        affair_id, now = _id("affair"), utc_now()
        facts = {
            item["key"]: {
                "key": item["key"], "label": item["label"], "type": item["type"],
                "required": bool(item.get("required")), "protected": bool(item.get("protected")),
                "sensitive": bool(item.get("sensitive")), "value": None, "status": "missing",
                "source_text": None, "updated_at": now,
            }
            for item in template.get("facts", [])
        }
        initial_values = params.get("facts") or {}
        for key, value in initial_values.items():
            if key in facts and value not in (None, ""):
                facts[key]["value"] = value
                facts[key]["status"] = "confirmed" if params.get("confirm_initial", False) else "extracted"
        self.db.connection.execute(
            "INSERT INTO affairs VALUES (?, ?, ?, ?, ?, ?, 1, ?, 0, 0)",
            (affair_id, title, template["id"], template["version"], now, now, str(params.get("source_text", ""))),
        )
        self.db.connection.execute(
            "INSERT INTO fact_snapshots VALUES (?, 1, ?, '[]', ?)",
            (affair_id, json_dumps(facts), now),
        )
        for task in template.get("tasks", []):
            self.db.connection.execute(
                "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, NULL, 0, 'normal', '', 1, ?, '[]', ?)",
                (_id("task"), affair_id, task["id"], task["title"], task["stage"],
                 json_dumps(task.get("reminders", [1440, 120, 0])), now),
            )
        self.db.connection.commit()
        affair_dir = self.db.path.parent / "affairs" / affair_id
        affair_dir.mkdir(parents=True, exist_ok=True)
        (affair_dir / ".qingwu-affair.json").write_text(
            json.dumps({"id": affair_id, "database": str(self.db.path)}, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        self._recalculate_task_dates(affair_id, template, facts)
        return self.affair_open({"id": affair_id})

    def affair_list(self, _params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows = self.db.all("SELECT * FROM affairs ORDER BY updated_at DESC")
        result = []
        for row in rows:
            item = _clean_row(row)
            counts = self.db.one(
                "SELECT COUNT(*) total, SUM(completed) completed FROM tasks WHERE affair_id=?", (item["id"],),
            ) or {"total": 0, "completed": 0}
            item["task_progress"] = {"completed": counts["completed"] or 0, "total": counts["total"] or 0}
            result.append(item)
        return result

    def affair_open(self, params: dict[str, Any]) -> dict[str, Any]:
        affair_id = str(params.get("id", ""))
        row = self.db.one("SELECT * FROM affairs WHERE id=?", (affair_id,))
        if not row:
            raise NotFoundError(f"未找到事务：{affair_id}")
        affair = _clean_row(row)
        template = self.templates.get(affair["template_id"])
        affair["template"] = template
        affair["facts"] = self._facts(affair_id, affair["current_fact_version"])
        affair["tasks"] = [_clean_row(item) for item in self.db.all("SELECT * FROM tasks WHERE affair_id=? ORDER BY due_at IS NULL, due_at, rowid", (affair_id,))]
        affair["materials"] = [_clean_row(item) for item in self.db.all("SELECT * FROM materials WHERE affair_id=? ORDER BY imported_at", (affair_id,))]
        affair["group_instances"] = []
        for item in self.db.all("SELECT * FROM group_instances WHERE affair_id=? ORDER BY created_at", (affair_id,)):
            item["facts"] = json_loads(item.pop("facts_json"), {})
            affair["group_instances"].append(item)
        affair["recipients"] = self.db.all("SELECT * FROM recipients WHERE affair_id=? ORDER BY name", (affair_id,))
        affair["drafts"] = self._latest_drafts(affair_id, affair["facts"])
        return affair

    # Facts --------------------------------------------------------------------
    def fact_extract(self, params: dict[str, Any]) -> dict[str, Any]:
        affair = self.affair_open({"id": params.get("affair_id")})
        source_text = str(params.get("source_text", "")).strip()
        if not source_text:
            raise ValidationError("请先粘贴要提取的通知或聊天记录")
        provider = OpenAIProvider(str(params.get("api_key", "")), str(params.get("model", "gpt-5.4-mini")))
        definitions = affair["template"].get("facts", [])
        reference_date = affair["created_at"][:10]
        timezone_name = str(params.get("timezone", "Asia/Shanghai"))
        result = provider.structured(
            instructions=("你是事实提取器，不得补全原文没有的信息。只返回 schema 允许的字段。"
                          "相对日期可以给出基于参考日期的候选绝对值，但 needs_date_confirmation 必须为 true，并保留 original_text。"
                          "同一字段有矛盾值时，不要选择其一，放入 conflicts。"),
            input_text=(f"事务创建日期：{reference_date}\n用户时区：{timezone_name}\n"
                        f"字段定义：{json.dumps(definitions, ensure_ascii=False)}\n\n原始材料：\n{source_text}"),
            schema_name="qingwu_fact_candidates", schema=fact_extraction_schema(definitions),
        )
        facts = copy.deepcopy(affair["facts"])
        changed = []
        conflict_keys = {item["key"] for item in result.get("conflicts", [])}
        for candidate in result.get("candidates", []):
            key = candidate["key"]
            if key not in facts or key in conflict_keys:
                continue
            facts[key].update({
                "value": candidate["value"], "status": "extracted", "source_text": candidate["original_text"],
                "confidence": candidate["confidence"],
                "needs_date_confirmation": candidate["needs_date_confirmation"], "updated_at": utc_now(),
            })
            changed.append(key)
        for conflict in result.get("conflicts", []):
            key = conflict["key"]
            if key in facts:
                facts[key].update({"value": None, "status": "conflicting", "conflict": conflict, "updated_at": utc_now()})
                changed.append(key)
        version = self._save_fact_snapshot(affair["id"], facts, changed, source_text=source_text, ai_used=True)
        self._record_ai(affair["id"], "fact.extract", provider.model, True)
        return {"fact_version": version, "facts": facts, "candidates": result["candidates"], "conflicts": result["conflicts"]}

    def fact_update(self, params: dict[str, Any]) -> dict[str, Any]:
        affair = self.affair_open({"id": params.get("affair_id")})
        key = str(params.get("key", ""))
        if key not in affair["facts"]:
            raise ValidationError(f"事实字段不存在：{key}")
        facts = copy.deepcopy(affair["facts"])
        old = facts[key].get("value")
        new = params.get("value")
        if old == new and facts[key]["status"] == params.get("status", facts[key]["status"]):
            return {"fact_version": affair["current_fact_version"], "facts": facts, "changed_keys": []}
        previously_confirmed = facts[key]["status"] == "confirmed"
        facts[key]["value"] = new
        facts[key]["status"] = str(params.get("status") or ("changed" if previously_confirmed else "extracted"))
        if new in (None, ""):
            facts[key]["status"] = "missing"
        facts[key]["source_text"] = params.get("source_text", facts[key].get("source_text"))
        facts[key]["updated_at"] = utc_now()
        version = self._save_fact_snapshot(affair["id"], facts, [key])
        self._mark_stale(affair["id"], [key])
        self._recalculate_task_dates(affair["id"], affair["template"], facts)
        return {"fact_version": version, "facts": facts, "changed_keys": [key]}

    def fact_confirm(self, params: dict[str, Any]) -> dict[str, Any]:
        affair = self.affair_open({"id": params.get("affair_id")})
        facts = copy.deepcopy(affair["facts"])
        values = params.get("values")
        if values is None and params.get("key"):
            values = {str(params["key"]): params.get("value", facts.get(str(params["key"]), {}).get("value"))}
        if not isinstance(values, dict) or not values:
            raise ValidationError("请选择至少一个要确认的事实字段")
        changed = []
        for key, value in values.items():
            if key not in facts:
                raise ValidationError(f"事实字段不存在：{key}")
            if value in (None, ""):
                raise ValidationError(f"{facts[key]['label']} 为空，不能确认")
            value_changed = facts[key].get("value") != value
            status_changed = facts[key].get("status") != "confirmed"
            facts[key]["value"] = value
            facts[key]["status"] = "confirmed"
            facts[key]["updated_at"] = utc_now()
            facts[key].pop("conflict", None)
            changed.append(key)
            if value_changed or status_changed:
                self._mark_stale(affair["id"], [key])
        version = self._save_fact_snapshot(affair["id"], facts, changed)
        self._recalculate_task_dates(affair["id"], affair["template"], facts)
        return {"fact_version": version, "facts": facts, "changed_keys": changed}

    def _facts(self, affair_id: str, version: int) -> dict[str, dict[str, Any]]:
        row = self.db.one("SELECT facts_json FROM fact_snapshots WHERE affair_id=? AND version=?", (affair_id, version))
        if not row:
            raise NotFoundError(f"未找到 facts-v{version}")
        return json_loads(row["facts_json"], {})

    def _save_fact_snapshot(self, affair_id: str, facts: dict[str, Any], changed: list[str],
                            *, source_text: str | None = None, ai_used: bool = False) -> int:
        affair = self.db.one("SELECT current_fact_version, source_text, ai_used FROM affairs WHERE id=?", (affair_id,))
        if not affair:
            raise NotFoundError(f"未找到事务：{affair_id}")
        version = int(affair["current_fact_version"]) + 1
        now = utc_now()
        self.db.connection.execute(
            "INSERT INTO fact_snapshots VALUES (?, ?, ?, ?, ?)",
            (affair_id, version, json_dumps(facts), json_dumps(sorted(set(changed))), now),
        )
        self.db.connection.execute(
            "UPDATE affairs SET current_fact_version=?, source_text=?, ai_used=?, updated_at=? WHERE id=?",
            (version, source_text if source_text is not None else affair["source_text"],
             1 if ai_used or affair["ai_used"] else 0, now, affair_id),
        )
        self.db.connection.commit()
        return version

    def _mark_stale(self, affair_id: str, changed_keys: list[str]) -> None:
        changed = set(changed_keys)
        rows = self.db.all("SELECT id, used_fact_keys_json, status FROM drafts WHERE affair_id=?", (affair_id,))
        for row in rows:
            if row["status"] != "archived" and changed.intersection(json_loads(row["used_fact_keys_json"], [])):
                self.db.execute("UPDATE drafts SET status='stale' WHERE id=?", (row["id"],))

    # Drafts -------------------------------------------------------------------
    def draft_generate(self, params: dict[str, Any]) -> dict[str, Any]:
        affair = self.affair_open({"id": params.get("affair_id")})
        document_id = str(params.get("document_id", ""))
        document = next((item for item in affair["template"].get("documents", []) if item["id"] == document_id), None)
        if not document:
            raise NotFoundError(f"未找到文案类型：{document_id}")
        body = str(document["offline_template"])
        locked_blocks = list(params.get("locked_blocks") or [])
        preserve_id = params.get("preserve_locked_from")
        if preserve_id:
            preserved = self.db.one("SELECT affair_id, document_id, locked_blocks_json FROM drafts WHERE id=?", (preserve_id,))
            if not preserved or preserved["affair_id"] != affair["id"] or preserved["document_id"] != document_id:
                raise ValidationError("要保留的锁定段落不属于当前文案")
            locked_blocks = json_loads(preserved["locked_blocks_json"], [])
        ai_generated = bool(params.get("use_ai"))
        if ai_generated:
            provider = OpenAIProvider(str(params.get("api_key", "")), str(params.get("model", "gpt-5.4-mini")))
            required_tokens = list(document.get("required_facts", []))
            protected = {key: affair["facts"][key]["label"] for key in required_tokens if affair["facts"][key].get("protected")}
            narrative = {
                key: field_value(value) for key, value in affair["facts"].items()
                if not value.get("protected") and field_value(value) is not None
            }
            style = None
            if params.get("style_card_id"):
                style_card = self._style_card(str(params["style_card_id"]), include_cache=False)
                if not style_card["confirmed"]:
                    raise ValidationError("所选风格卡尚未确认")
                style = style_card["card"]
            schema = {
                "type": "object", "properties": {"body": {"type": "string"}},
                "required": ["body"], "additionalProperties": False,
            }
            result = provider.structured(
                instructions=("你是学生工作文案助手。输出一篇可直接人工审核的中文草稿。"
                              "所有给出的事实占位符必须原样保留，绝对不能改写、猜测或替换；缺失事实也保留占位符。"
                              "不得声称已发送、已发布或已完成。"),
                input_text=(f"文案类型：{document['title']}\n必须出现的事实占位符："
                            f"{json.dumps([f'{{{{{key}}}}}' for key in required_tokens], ensure_ascii=False)}\n"
                            f"受保护字段含义：{json.dumps(protected, ensure_ascii=False)}\n"
                            f"可用于叙述的已确认非关键事实：{json.dumps(narrative, ensure_ascii=False)}\n"
                            f"组织风格卡：{json.dumps(style, ensure_ascii=False)}\n"
                            f"用户补充要求：{str(params.get('instructions', ''))}\n"
                            f"基础结构参考：\n{body}"),
                schema_name="qingwu_draft", schema=schema,
            )
            body = result["body"]
            try:
                validate_ai_body(body, required_tokens)
            except ValueError as exc:
                self._record_ai(affair["id"], "draft.generate", provider.model, False, "missing_fact_tokens")
                raise ValidationError(str(exc), reason="missing_fact_tokens") from exc
            self._record_ai(affair["id"], "draft.generate", provider.model, True)
            self.db.execute("UPDATE affairs SET ai_used=1, updated_at=? WHERE id=?", (utc_now(), affair["id"]))
        body = self._apply_locked_blocks(body, locked_blocks)
        used_keys = tokens_in(body)
        required_keys = list(document.get("required_facts", []))
        missing = missing_required(required_keys, affair["facts"])
        status = "missing_facts" if missing else "needs_review"
        previous = self.db.one(
            "SELECT MAX(version) version FROM drafts WHERE affair_id=? AND document_id=?",
            (affair["id"], document_id),
        )
        version = int(previous["version"] or 0) + 1
        draft_id = _id("draft")
        self.db.execute(
            "INSERT INTO drafts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (draft_id, affair["id"], document_id, document["title"], document["kind"], version, body,
             affair["current_fact_version"], json_dumps(used_keys), json_dumps(required_keys), status,
             json_dumps(locked_blocks), 1 if ai_generated else 0, utc_now()),
        )
        return self._draft(draft_id, affair["facts"])

    def draft_update(self, params: dict[str, Any]) -> dict[str, Any]:
        previous = self.db.one("SELECT * FROM drafts WHERE id=?", (str(params.get("id", "")),))
        if not previous:
            raise NotFoundError("未找到要编辑的草稿")
        affair = self.affair_open({"id": previous["affair_id"]})
        body = str(params.get("body", "")).strip()
        if not body:
            raise ValidationError("文案正文不能为空")
        paragraphs = re.split(r"\n{2,}", body.strip())
        indices = sorted({int(value) for value in params.get("locked_paragraphs", []) if 0 <= int(value) < len(paragraphs)})
        locked_blocks = [{"index": index, "text": paragraphs[index]} for index in indices]
        used_keys = tokens_in(body)
        required_keys = json_loads(previous["required_fact_keys_json"], [])
        missing = missing_required(required_keys, affair["facts"])
        status = "missing_facts" if missing else "needs_review"
        maximum = self.db.one(
            "SELECT MAX(version) version FROM drafts WHERE affair_id=? AND document_id=?",
            (affair["id"], previous["document_id"]),
        )
        version = int(maximum["version"] or 0) + 1
        draft_id = _id("draft")
        self.db.execute(
            "INSERT INTO drafts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (draft_id, affair["id"], previous["document_id"], previous["title"], previous["kind"], version,
             body, affair["current_fact_version"], json_dumps(used_keys), json_dumps(required_keys), status,
             json_dumps(locked_blocks), utc_now()),
        )
        return self._draft(draft_id, affair["facts"])

    @staticmethod
    def _apply_locked_blocks(body: str, locked_blocks: list[dict[str, Any]]) -> str:
        if not locked_blocks:
            return body
        paragraphs = re.split(r"\n{2,}", body.strip())
        for block in locked_blocks:
            index = int(block.get("index", len(paragraphs)))
            text = str(block.get("text", ""))
            if not text:
                continue
            if index < len(paragraphs):
                paragraphs[index] = text
            else:
                paragraphs.append(text)
        return "\n\n".join(paragraphs)

    def draft_compare_versions(self, params: dict[str, Any]) -> dict[str, Any]:
        affair = self.affair_open({"id": params.get("affair_id")})
        document_id = str(params.get("document_id", ""))
        rows = self.db.all(
            "SELECT * FROM drafts WHERE affair_id=? AND document_id=? ORDER BY version",
            (affair["id"], document_id),
        )
        if not rows:
            raise NotFoundError(f"尚无文案版本：{document_id}")
        versions = [self._draft_from_row(row, affair["facts"]) for row in rows]
        return {"document_id": document_id, "versions": versions}

    def draft_mark_ready(self, params: dict[str, Any]) -> dict[str, Any]:
        row = self.db.one("SELECT * FROM drafts WHERE id=?", (str(params.get("id", "")),))
        if not row:
            raise NotFoundError("未找到草稿")
        affair = self.affair_open({"id": row["affair_id"]})
        draft = self._draft_from_row(row, affair["facts"])
        if draft["status"] == "stale":
            raise ConflictError("草稿引用了已变化的事实，请先更新或重新生成")
        missing = missing_required(draft["required_fact_keys"], affair["facts"])
        if missing:
            labels = [affair["facts"][key]["label"] for key in missing]
            raise ConflictError("仍缺少已确认事实：" + "、".join(labels))
        self.db.execute("UPDATE drafts SET status='ready_to_copy' WHERE id=?", (draft["id"],))
        draft["status"] = "ready_to_copy"
        return draft

    def _draft(self, draft_id: str, facts: dict[str, Any]) -> dict[str, Any]:
        row = self.db.one("SELECT * FROM drafts WHERE id=?", (draft_id,))
        if not row:
            raise NotFoundError(f"未找到草稿：{draft_id}")
        return self._draft_from_row(row, facts)

    @staticmethod
    def _draft_from_row(row: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
        draft = _clean_row(row)
        draft["rendered_body"] = render_body(draft["body"], facts)
        return draft

    def _latest_drafts(self, affair_id: str, facts: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.db.all(
            "SELECT d.* FROM drafts d JOIN (SELECT document_id, MAX(version) version FROM drafts WHERE affair_id=? GROUP BY document_id) x "
            "ON d.document_id=x.document_id AND d.version=x.version WHERE d.affair_id=? ORDER BY d.rowid",
            (affair_id, affair_id),
        )
        return [self._draft_from_row(item, facts) for item in rows]

    # Timeline -----------------------------------------------------------------
    def timeline_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        return self.affair_open({"id": params.get("affair_id")})["tasks"]

    def timeline_update_task(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = str(params.get("id", ""))
        row = self.db.one("SELECT * FROM tasks WHERE id=?", (task_id,))
        if not row:
            raise NotFoundError(f"未找到待办：{task_id}")
        allowed = {"title", "stage", "due_at", "priority", "notes"}
        values = {key: params[key] for key in allowed if key in params}
        if "completed" in params:
            values["completed"] = 1 if params["completed"] else 0
        if "reminder_enabled" in params:
            values["reminder_enabled"] = 1 if params["reminder_enabled"] else 0
        if "reminder_offsets" in params:
            values["reminder_offsets_json"] = json_dumps(params["reminder_offsets"])
            values["sent_reminders_json"] = "[]"
        if "due_at" in values and values["due_at"] != row["due_at"]:
            values["sent_reminders_json"] = "[]"
        values["updated_at"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in values)
        self.db.execute(f"UPDATE tasks SET {assignments} WHERE id=?", (*values.values(), task_id))
        return _clean_row(self.db.one("SELECT * FROM tasks WHERE id=?", (task_id,)) or {})

    def timeline_due_reminders(self, _params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        now = datetime.now().astimezone()
        due_items: list[dict[str, Any]] = []
        rows = self.db.all(
            "SELECT t.*, a.title affair_title FROM tasks t JOIN affairs a ON a.id=t.affair_id "
            "WHERE t.completed=0 AND t.reminder_enabled=1 AND t.due_at IS NOT NULL"
        )
        for row in rows:
            try:
                due = datetime.fromisoformat(row["due_at"].replace("Z", "+00:00"))
                if due.tzinfo is None:
                    due = due.replace(tzinfo=now.tzinfo)
            except (ValueError, TypeError):
                continue
            sent = set(json_loads(row["sent_reminders_json"], []))
            offsets = sorted((int(value) for value in json_loads(row["reminder_offsets_json"], [])), reverse=True)
            new_keys = []
            latest_due = None
            for offset in offsets:
                key = f"{row['due_at']}|{offset}"
                trigger = due - timedelta(minutes=offset)
                if key not in sent and trigger <= now <= due + timedelta(hours=24):
                    latest_due = {
                        "task_id": row["id"], "affair_id": row["affair_id"], "affair_title": row["affair_title"],
                        "title": row["title"], "due_at": row["due_at"], "offset_minutes": offset,
                    }
                    new_keys.append(key)
            if new_keys and latest_due is not None:
                due_items.append(latest_due)
                sent.update(new_keys)
                self.db.execute("UPDATE tasks SET sent_reminders_json=?, updated_at=? WHERE id=?",
                                (json_dumps(sorted(sent)), utc_now(), row["id"]))
        return due_items

    def _recalculate_task_dates(self, affair_id: str, template: dict[str, Any], facts: dict[str, Any]) -> None:
        for task in template.get("tasks", []):
            key = task.get("relative_to")
            field = facts.get(key) if key else None
            value = field_value(field) if field else None
            due_at = None
            if value:
                try:
                    base = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if len(value) == 10 and key == "activity_date":
                        time_value = field_value(facts.get("start_time", {})) or "09:00"
                        base = datetime.fromisoformat(f"{value}T{time_value}")
                    due_at = (base + timedelta(minutes=int(task.get("offset_minutes", 0)))).isoformat(timespec="minutes")
                except (ValueError, TypeError):
                    due_at = None
            existing = self.db.one(
                "SELECT due_at FROM tasks WHERE affair_id=? AND template_task_id=?", (affair_id, task["id"]),
            )
            if existing and existing["due_at"] != due_at:
                self.db.execute(
                    "UPDATE tasks SET due_at=?, sent_reminders_json='[]', updated_at=? WHERE affair_id=? AND template_task_id=?",
                    (due_at, utc_now(), affair_id, task["id"]),
                )

    # Materials, repeatable groups and recipients -----------------------------
    def material_import(self, params: dict[str, Any]) -> dict[str, Any]:
        affair = self.affair_open({"id": params.get("affair_id")})
        paths = params.get("paths") or ([params["path"]] if params.get("path") else [])
        if not paths:
            raise ValidationError("请选择至少一个文件")
        imported = []
        for path in paths:
            info = inspect_file(path)
            material_id = _id("material")
            self.db.execute(
                "INSERT INTO materials VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)",
                (material_id, affair["id"], info["source_path"], info["original_name"], info["extension"],
                 info["size_bytes"], info["sha256"], utc_now()),
            )
            imported.append({"id": material_id, **info, "slot_id": None, "group_instance_id": None,
                             "suggestions": recommend_slots(info, affair["template"])})
        return {"materials": imported}

    def material_assign(self, params: dict[str, Any]) -> dict[str, Any]:
        material_id = str(params.get("id", ""))
        material = self.db.one("SELECT * FROM materials WHERE id=?", (material_id,))
        if not material:
            raise NotFoundError(f"未找到材料：{material_id}")
        affair = self.affair_open({"id": material["affair_id"]})
        slot_id = params.get("slot_id")
        group_instance_id = params.get("group_instance_id")
        valid_slots = {item["id"] for item in affair["template"].get("material_slots", [])}
        if group_instance_id:
            instance = next((item for item in affair["group_instances"] if item["id"] == group_instance_id), None)
            if not instance:
                raise ValidationError("报销项目实例不存在")
            group = next(item for item in affair["template"].get("groups", []) if item["id"] == instance["group_id"])
            valid_slots = {item["id"] for item in group.get("material_slots", [])}
        if slot_id is not None and slot_id not in valid_slots:
            raise ValidationError(f"材料槽位不存在：{slot_id}")
        self.db.execute(
            "UPDATE materials SET slot_id=?, group_instance_id=? WHERE id=?",
            (slot_id, group_instance_id, material_id),
        )
        return _clean_row(self.db.one("SELECT * FROM materials WHERE id=?", (material_id,)) or {})

    def group_add(self, params: dict[str, Any]) -> dict[str, Any]:
        affair = self.affair_open({"id": params.get("affair_id")})
        group_id = str(params.get("group_id", ""))
        group = next((item for item in affair["template"].get("groups", []) if item["id"] == group_id), None)
        if not group:
            raise ValidationError(f"可重复项目不存在：{group_id}")
        now, instance_id = utc_now(), _id("group")
        facts = {
            item["key"]: {"label": item["label"], "value": (params.get("facts") or {}).get(item["key"]),
                           "required": bool(item.get("required")), "sensitive": bool(item.get("sensitive"))}
            for item in group.get("facts", [])
        }
        title = str(params.get("title") or f"{group['title']} {len(affair['group_instances']) + 1}")
        self.db.execute(
            "INSERT INTO group_instances VALUES (?, ?, ?, ?, ?, ?)",
            (instance_id, affair["id"], group_id, title, json_dumps(facts), now),
        )
        return {"id": instance_id, "affair_id": affair["id"], "group_id": group_id, "title": title, "facts": facts, "created_at": now}

    def group_update(self, params: dict[str, Any]) -> dict[str, Any]:
        instance = self.db.one("SELECT * FROM group_instances WHERE id=?", (str(params.get("id", "")),))
        if not instance:
            raise NotFoundError("未找到可重复项目")
        facts = json_loads(instance["facts_json"], {})
        for key, value in (params.get("facts") or {}).items():
            if key not in facts:
                raise ValidationError(f"项目字段不存在：{key}")
            facts[key]["value"] = value
        title = str(params.get("title", instance["title"]))
        self.db.execute("UPDATE group_instances SET title=?, facts_json=? WHERE id=?", (title, json_dumps(facts), instance["id"]))
        return {"id": instance["id"], "affair_id": instance["affair_id"], "group_id": instance["group_id"], "title": title, "facts": facts}

    def recipient_import(self, params: dict[str, Any]) -> dict[str, Any]:
        affair = self.affair_open({"id": params.get("affair_id")})
        names = params.get("names") or []
        if isinstance(names, str):
            names = [item.strip() for item in re.split(r"[,，;；\n\t]+", names) if item.strip()]
        created = []
        for name in names:
            recipient_id = _id("person")
            now = utc_now()
            self.db.execute("INSERT INTO recipients VALUES (?, ?, ?, 'pending', '', ?)", (recipient_id, affair["id"], name, now))
            created.append({"id": recipient_id, "name": name, "status": "pending", "notes": "", "updated_at": now})
        return {"recipients": created}

    def recipient_update(self, params: dict[str, Any]) -> dict[str, Any]:
        row = self.db.one("SELECT * FROM recipients WHERE id=?", (str(params.get("id", "")),))
        if not row:
            raise NotFoundError("未找到人员记录")
        status = str(params.get("status", row["status"]))
        if status not in {"submitted", "incomplete", "pending"}:
            raise ValidationError("人员状态必须为 submitted、incomplete 或 pending")
        notes = str(params.get("notes", row["notes"]))
        self.db.execute("UPDATE recipients SET status=?, notes=?, updated_at=? WHERE id=?", (status, notes, utc_now(), row["id"]))
        return self.db.one("SELECT * FROM recipients WHERE id=?", (row["id"],)) or {}

    # Checks and archive --------------------------------------------------------
    def affair_check(self, params: dict[str, Any]) -> dict[str, Any]:
        affair = self.affair_open({"id": params.get("affair_id")})
        issues: list[dict[str, Any]] = []
        for field in affair["facts"].values():
            if field.get("required") and field_value(field) is None:
                issues.append({"code": "required_fact_missing", "severity": "error",
                               "message": f"必填事实“{field['label']}”尚未确认", "field": field["key"]})
            elif field.get("status") == "conflicting":
                issues.append({"code": "fact_conflict", "severity": "error",
                               "message": f"事实“{field['label']}”存在冲突", "field": field["key"]})
        latest = affair["drafts"]
        for draft in latest:
            if draft["status"] == "stale":
                issues.append({"code": "stale_draft", "severity": "error", "message": f"文案“{draft['title']}”引用了旧事实"})
            elif draft["status"] in {"missing_facts", "needs_review"}:
                issues.append({"code": "draft_not_ready", "severity": "warning", "message": f"文案“{draft['title']}”尚未确认可用"})
        by_slot: dict[tuple[str | None, str | None], list[dict[str, Any]]] = {}
        for material in affair["materials"]:
            by_slot.setdefault((material.get("group_instance_id"), material.get("slot_id")), []).append(material)
            integrity, _ = check_material_integrity(material)
            if integrity == "missing":
                issues.append({"code": "material_missing", "severity": "error", "message": f"材料已被移动或删除：{material['original_name']}"})
            elif integrity == "changed":
                issues.append({"code": "material_changed", "severity": "error", "message": f"材料内容已变化：{material['original_name']}"})
            detected = detected_extension(material["source_path"]) if integrity != "missing" else None
            declared = material["extension"].lower()
            equivalent = {(".jpg", ".jpeg"), (".jpeg", ".jpg")}
            if detected and detected != declared and (detected, declared) not in equivalent:
                issues.append({"code": "material_signature_mismatch", "severity": "error",
                               "message": f"{material['original_name']} 的内容像 {detected}，与扩展名 {declared or '无'} 不一致"})
            if not material.get("slot_id"):
                issues.append({"code": "material_unassigned", "severity": "warning", "message": f"材料尚未归类：{material['original_name']}"})
        hashes: dict[str, list[str]] = {}
        for material in affair["materials"]:
            hashes.setdefault(material["sha256"], []).append(material["original_name"])
        for names in hashes.values():
            if len(names) > 1:
                issues.append({"code": "duplicate_material", "severity": "warning",
                               "message": "检测到重复内容：" + "、".join(names)})
        self._check_slots(affair["template"].get("material_slots", []), by_slot, None, issues)
        groups_by_id = {item["id"]: item for item in affair["template"].get("groups", [])}
        instances_by_group: dict[str, list[dict[str, Any]]] = {}
        for instance in affair["group_instances"]:
            instances_by_group.setdefault(instance["group_id"], []).append(instance)
            for key, fact in instance["facts"].items():
                if fact.get("required") and fact.get("value") in (None, ""):
                    issues.append({"code": "group_fact_missing", "severity": "error",
                                   "message": f"{instance['title']}缺少“{fact['label']}”"})
            group = groups_by_id[instance["group_id"]]
            self._check_slots(group.get("material_slots", []), by_slot, instance["id"], issues, instance["title"])
        for group_id, group in groups_by_id.items():
            if len(instances_by_group.get(group_id, [])) < int(group.get("min_items", 0)):
                issues.append({"code": "group_missing", "severity": "error",
                               "message": f"至少需要 {group.get('min_items', 0)} 个“{group['title']}”"})
        return {
            "affair_id": affair["id"], "ok": not any(item["severity"] == "error" for item in issues),
            "issues": issues,
            "summary": {"errors": sum(item["severity"] == "error" for item in issues),
                        "warnings": sum(item["severity"] == "warning" for item in issues)},
        }

    @staticmethod
    def _check_slots(slots: list[dict[str, Any]], by_slot: dict[tuple[str | None, str | None], list[dict[str, Any]]],
                     group_instance: str | None, issues: list[dict[str, Any]], prefix: str = "") -> None:
        for slot in slots:
            materials = by_slot.get((group_instance, slot["id"]), [])
            minimum = int(slot.get("min_items", 1 if slot.get("required") else 0))
            if len(materials) < minimum:
                issues.append({"code": "material_slot_missing", "severity": "error",
                               "message": f"{prefix + '：' if prefix else ''}“{slot['title']}”至少需要 {minimum} 个文件"})
            maximum = slot.get("max_items")
            if maximum is not None and len(materials) > int(maximum):
                issues.append({"code": "material_slot_too_many", "severity": "warning",
                               "message": f"{prefix + '：' if prefix else ''}“{slot['title']}”最多建议 {maximum} 个文件"})
            allowed = {str(value).lower() for value in slot.get("extensions", [])}
            for material in materials:
                if allowed and material["extension"].lower() not in allowed:
                    issues.append({"code": "material_extension", "severity": "error",
                                   "message": f"{material['original_name']} 的格式不符合槽位“{slot['title']}”要求"})

    def affair_preview_archive(self, params: dict[str, Any]) -> dict[str, Any]:
        affair = self.affair_open({"id": params.get("affair_id")})
        check = self.affair_check({"affair_id": affair["id"]})
        manifest = build_manifest(affair, check["issues"])
        return {"check": check, "manifest": manifest}

    def affair_export(self, params: dict[str, Any]) -> dict[str, Any]:
        affair = self.affair_open({"id": params.get("affair_id")})
        check = self.affair_check({"affair_id": affair["id"]})
        return export_affair(
            affair, check["issues"], str(params.get("output", "")), allow_warnings=bool(params.get("allow_warnings", True)),
        )

    def _record_ai(self, affair_id: str | None, purpose: str, model: str, success: bool,
                   error_code: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO ai_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_id("airun"), affair_id, purpose, model, 1 if success else 0, utc_now(), error_code),
        )

    # JSON Lines dispatch -------------------------------------------------------
    def dispatch(self, method: str, params: dict[str, Any] | None = None) -> Any:
        params = params or {}
        methods = {
            "profile.create": self.profile_create, "profile.update": self.profile_update,
            "style.import_examples": self.style_import_examples, "style.preview_upload": self.style_preview_upload,
            "style.generate_card": self.style_generate_card, "style.confirm_card": self.style_confirm_card,
            "style.list": self.style_list, "style.open": self.style_open,
            "template.validate": self.template_validate, "template.list": self.template_list,
            "affair.create": self.affair_create, "affair.list": self.affair_list, "affair.open": self.affair_open,
            "fact.extract": self.fact_extract, "fact.confirm": self.fact_confirm, "fact.update": self.fact_update,
            "draft.generate": self.draft_generate, "draft.compare_versions": self.draft_compare_versions,
            "draft.update": self.draft_update, "draft.mark_ready": self.draft_mark_ready,
            "timeline.list": self.timeline_list,
            "timeline.update_task": self.timeline_update_task, "timeline.due_reminders": self.timeline_due_reminders,
            "material.import": self.material_import,
            "material.assign": self.material_assign, "group.add": self.group_add, "group.update": self.group_update,
            "recipient.import": self.recipient_import, "recipient.update": self.recipient_update,
            "affair.check": self.affair_check, "affair.preview_archive": self.affair_preview_archive,
            "affair.export": self.affair_export,
        }
        handler = methods.get(method)
        if not handler:
            raise NotFoundError(f"未知接口：{method}")
        return handler(params)
