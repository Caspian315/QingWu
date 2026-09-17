import type { Affair, AffairCheck, AffairSummary, Draft, FactField, StyleCard, TemplateSummary, TimelineTask } from "../types";

const templates: TemplateSummary[] = [
  { id: "activity-organization", version: "1.0.0", title: "活动组织", description: "通知、执行、总结与归档" },
  { id: "material-collection", version: "1.0.0", title: "材料收集", description: "收集、催交、核对与归档" },
  { id: "reimbursement", version: "1.0.0", title: "报销", description: "票据、支付凭证与报销说明" },
];

const factDefinitions: Record<string, Array<[string, string, string, boolean]>> = {
  "activity-organization": [
    ["activity_name", "活动名称", "text", true], ["activity_theme", "活动主题", "text", false],
    ["activity_date", "活动日期", "date", true], ["start_time", "开始时间", "time", true],
    ["end_time", "结束时间", "time", false], ["location", "活动地点", "text", true],
    ["audience", "面向对象", "text", true], ["signup_method", "报名方式", "textarea", false],
    ["signup_deadline", "报名截止时间", "datetime", false], ["contact_person", "联系人", "text", true],
    ["contact_method", "联系方式", "text", false], ["organizer", "主办或承办组织", "text", true],
    ["notes", "注意事项", "textarea", false],
  ],
  "material-collection": [
    ["collection_name", "收集事项", "text", true], ["audience", "收集对象", "text", true],
    ["requirements", "材料要求", "textarea", true], ["naming_rule", "文件命名要求", "text", false],
    ["submission_method", "提交方式", "textarea", true], ["deadline", "截止时间", "datetime", true],
    ["contact_person", "联系人", "text", true], ["contact_method", "联系方式", "text", false],
    ["organizer", "组织或部门", "text", true], ["notes", "补充说明", "textarea", false],
  ],
  reimbursement: [
    ["project_name", "项目名称", "text", true], ["handler", "经办人", "text", true],
    ["organization", "组织或部门", "text", true], ["description", "报销说明", "textarea", true],
    ["deadline", "截止时间", "datetime", false], ["contact_method", "联系方式", "text", false],
  ],
};

const documentDefinitions: Record<string, Array<[string, string, string]>> = {
  "activity-organization": [["notice_full", "完整群通知", "notice"], ["notice_short", "简洁群通知", "notice"], ["deadline_reminder", "截止前提醒", "reminder"], ["article_preview", "活动预告推文", "article_preview"], ["article_recap", "活动回顾推文", "article_recap"]],
  "material-collection": [["collection_notice", "首次收集通知", "notice"], ["collection_short", "简短版通知", "notice"], ["deadline_reminder", "截止前提醒", "reminder"], ["overdue_reminder", "已逾期提醒", "reminder"], ["direct_message", "私聊催交话术", "direct_message"], ["completion_note", "完成确认话术", "reminder"]],
  reimbursement: [["receipt_request", "收集票据通知", "notice"], ["missing_proof_reminder", "补充凭证提醒", "reminder"], ["completion_note", "材料收齐确认", "reminder"], ["submission_note", "向上级提交说明", "submission_note"]],
};

const storageKey = "qingwu-browser-demo-v1";
let affairs: Affair[] = JSON.parse(localStorage.getItem(storageKey) || "[]") as Affair[];
let styleCards: StyleCard[] = JSON.parse(localStorage.getItem(`${storageKey}-styles`) || "[]") as StyleCard[];
const persist = () => localStorage.setItem(storageKey, JSON.stringify(affairs));
const persistStyles = () => localStorage.setItem(`${storageKey}-styles`, JSON.stringify(styleCards));
const now = () => new Date().toISOString();
const id = (prefix: string) => `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;

function requiredTokens(templateId: string, documentId: string): string[] {
  const all = factDefinitions[templateId].filter((item) => item[3]).map((item) => item[0]);
  if (documentId.includes("reminder") || documentId === "direct_message") return all.filter((key) => /name|deadline|contact|project/.test(key));
  return all;
}

function render(body: string, facts: Record<string, FactField>) {
  return body.replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (_, key: string) => {
    const field = facts[key];
    return field?.status === "confirmed" && field.value ? String(field.value) : `【待填写：${field?.label || key}】`;
  });
}

function bodyFor(templateId: string, documentId: string) {
  const map: Record<string, string> = {
    "activity-organization": "各位同学：\n\n现将{{activity_name}}有关安排通知如下：\n时间：{{activity_date}} {{start_time}}\n地点：{{location}}\n面向对象：{{audience}}\n报名方式：{{signup_method}}\n截止时间：{{signup_deadline}}\n\n如有疑问，请联系{{contact_person}}（{{contact_method}}）。\n\n{{organizer}}",
    "material-collection": "各位同学：\n\n现需收集{{collection_name}}。\n材料要求：{{requirements}}\n提交方式：{{submission_method}}\n截止时间：{{deadline}}\n命名要求：{{naming_rule}}\n\n如有问题，请联系{{contact_person}}。\n{{organizer}}",
    reimbursement: "各位同学：\n\n现开始收集{{project_name}}相关报销材料，请提供票据和对应支付凭证。截止时间：{{deadline}}。\n\n经办人：{{handler}}\n{{organization}}",
  };
  if (documentId.includes("article")) return `# {{activity_name}}\n\n## 活动信息\n\n活动将于{{activity_date}} {{start_time}}在{{location}}举行。\n\n【图片 1：活动现场全景】\n\n{{organizer}}`;
  if (documentId.includes("reminder") || documentId === "direct_message") return `提醒一下，相关事项将于{{${templateId === "activity-organization" ? "signup_deadline" : "deadline"}}}截止，请尚未完成的同学及时处理。`;
  return map[templateId];
}

function summary(affair: Affair): AffairSummary {
  return { ...affair, task_progress: { completed: affair.tasks.filter((task) => task.completed).length, total: affair.tasks.length } };
}

export async function mockCall<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  let affair: Affair | undefined;
  switch (method) {
    case "template.list": return templates as T;
    case "style.list": return structuredClone(styleCards) as T;
    case "style.preview_upload": {
      const texts = (params.texts as string[] | undefined) ?? [];
      const combined = texts.join("\n");
      const pii = [];
      if (/1[3-9]\d{9}/.test(combined)) pii.push({ type: "疑似手机号", count: 1 });
      if (/(?:^|\D)\d{8,14}(?:\D|$)/.test(combined)) pii.push({ type: "疑似学号", count: 1 });
      return { sample_count: texts.length, text_length: combined.length, pii_warnings: pii, preview: combined.slice(0, 3000) } as T;
    }
    case "style.import_examples": {
      const created = now();
      const card: StyleCard = { id: id("style"), name: String(params.name), document_kind: String(params.document_kind), card: { tone: "", greeting: "", paragraph_length: "short", heading_style: "", emoji_policy: "", common_phrases: [], forbidden_phrases: [], sign_off: "", punctuation: "中文全角标点" }, confirmed: false, sample_count: ((params.texts as string[] | undefined) ?? []).length, created_at: created, updated_at: created };
      styleCards.unshift(card); persistStyles(); return card as T;
    }
    case "style.generate_card": {
      const card = styleCards.find((item) => item.id === params.id)!;
      card.card = { tone: "正式但不生硬", greeting: "各位同学：", paragraph_length: "short", heading_style: "序号加短标题", emoji_policy: "通知不用", common_phrases: ["请各位同学注意", "感谢大家的配合"], forbidden_phrases: ["速来", "家人们"], sign_off: "组织落款", punctuation: "中文全角标点" };
      card.updated_at = now(); persistStyles(); return card as T;
    }
    case "style.confirm_card": {
      const card = styleCards.find((item) => item.id === params.id)!;
      card.card = params.card as Record<string, string | string[]>; card.confirmed = true; card.updated_at = now();
      persistStyles(); return card as T;
    }
    case "affair.list": return affairs.map(summary) as T;
    case "affair.create": {
      const templateId = String(params.template_id);
      const facts: Record<string, FactField> = Object.fromEntries(factDefinitions[templateId].map(([key, label, type, required]) => [key, { key, label, type, required, protected: true, sensitive: false, value: null, status: "missing" as const }]));
      const tasks: TimelineTask[] = ["确认关键信息", "发布首次通知", "发送截止提醒", "核对材料", "完成归档"].map((title, index) => ({ id: id("task"), title, stage: ["prepare", "announce", "remind", "verify", "archive"][index], due_at: null, completed: false, priority: "normal", notes: "", reminder_enabled: true, reminder_offsets: [1440, 120, 0] }));
      const created = now();
      affair = { id: id("affair"), title: String(params.title), template_id: templateId, template_version: "1.0.0", created_at: created, updated_at: created, current_fact_version: 1, ai_used: false, source_text: "", facts, tasks, drafts: [], materials: [], recipients: [], group_instances: [], template: { ...templates.find((item) => item.id === templateId)!, facts: factDefinitions[templateId].map(([key, label, type, required]) => ({ key, label, type, required })), stages: [], documents: documentDefinitions[templateId].map(([docId, title, kind]) => ({ id: docId, title, kind, required_facts: requiredTokens(templateId, docId) })), material_slots: [], groups: [] } };
      affairs.unshift(affair!); persist(); return affair as T;
    }
    case "affair.open": affair = affairs.find((item) => item.id === params.id); return structuredClone(affair) as T;
    case "fact.update":
    case "fact.confirm": {
      affair = affairs.find((item) => item.id === params.affair_id)!;
      const values = (params.values || { [String(params.key)]: params.value }) as Record<string, string>;
      const changed = Object.keys(values);
      for (const [key, value] of Object.entries(values)) {
        const old = affair.facts[key].value;
        affair.facts[key].value = value;
        affair.facts[key].status = method === "fact.confirm" ? "confirmed" : old && old !== value ? "changed" : "extracted";
      }
      affair.current_fact_version += 1;
      affair.drafts.forEach((draft) => { if (draft.used_fact_keys.some((key) => changed.includes(key))) draft.status = "stale"; });
      persist(); return { fact_version: affair.current_fact_version, facts: affair.facts, changed_keys: changed } as T;
    }
    case "draft.generate": {
      affair = affairs.find((item) => item.id === params.affair_id)!;
      const documentId = String(params.document_id);
      const definition = documentDefinitions[affair.template_id].find((item) => item[0] === documentId)!;
      const body = bodyFor(affair.template_id, documentId);
      const required = requiredTokens(affair.template_id, documentId);
      const missing = required.some((key) => affair!.facts[key]?.status !== "confirmed");
      const draft: Draft = { id: id("draft"), document_id: documentId, title: definition[1], kind: definition[2], version: (affair.drafts.filter((item) => item.document_id === documentId).at(-1)?.version || 0) + 1, body, rendered_body: render(body, affair.facts), fact_version: affair.current_fact_version, used_fact_keys: [...body.matchAll(/\{\{([\w.-]+)\}\}/g)].map((match) => match[1]), required_fact_keys: required, locked_blocks: [], status: missing ? "missing_facts" : "needs_review", ai_generated: false, created_at: now() };
      affair.drafts = affair.drafts.filter((item) => item.document_id !== documentId).concat(draft); persist(); return draft as T;
    }
    case "draft.update": {
      affair = affairs.find((item) => item.drafts.some((draft) => draft.id === params.id))!;
      const previous = affair.drafts.find((item) => item.id === params.id)!;
      const body = String(params.body);
      const paragraphs = body.trim().split(/\n{2,}/);
      const lockedBlocks = ((params.locked_paragraphs as number[] | undefined) ?? []).map((index) => ({ index, text: paragraphs[index] })).filter((item) => item.text != null);
      const updated: Draft = { ...previous, id: id("draft"), version: previous.version + 1, body, rendered_body: render(body, affair.facts), locked_blocks: lockedBlocks, status: "needs_review", ai_generated: false, created_at: now() };
      affair.drafts = affair.drafts.filter((item) => item.document_id !== previous.document_id).concat(updated); persist(); return updated as T;
    }
    case "draft.mark_ready": {
      affair = affairs.find((item) => item.drafts.some((draft) => draft.id === params.id))!;
      const draft = affair.drafts.find((item) => item.id === params.id)!;
      if (draft.status === "stale" || draft.required_fact_keys.some((key) => affair!.facts[key]?.status !== "confirmed")) throw new Error("草稿仍有缺失或过期事实");
      draft.status = "ready_to_copy"; persist(); return draft as T;
    }
    case "timeline.update_task": {
      affair = affairs.find((item) => item.tasks.some((task) => task.id === params.id))!;
      const task = affair.tasks.find((item) => item.id === params.id)!;
      Object.assign(task, params); persist(); return task as T;
    }
    case "recipient.import": {
      affair = affairs.find((item) => item.id === params.affair_id)!;
      const raw = String(params.names ?? "");
      const names = raw.split(/[,，;；\n\t]+/).map((value) => value.trim()).filter(Boolean);
      const created = names.map((name) => ({ id: id("person"), name, status: "pending", notes: "", updated_at: now() }));
      affair.recipients.push(...created); persist(); return { recipients: created } as T;
    }
    case "recipient.update": {
      affair = affairs.find((item) => item.recipients.some((person) => person.id === params.id))!;
      const person = affair.recipients.find((item) => item.id === params.id)!;
      person.status = String(params.status); person.updated_at = now(); persist(); return person as T;
    }
    case "affair.check": {
      affair = affairs.find((item) => item.id === params.affair_id)!;
      const issues = Object.values(affair.facts).filter((field) => field.required && field.status !== "confirmed").map((field) => ({ code: "required_fact_missing", severity: "error" as const, message: `必填事实“${field.label}”尚未确认` }));
      return { affair_id: affair.id, ok: issues.length === 0, issues, summary: { errors: issues.length, warnings: 0 } } as T;
    }
    default: throw new Error(`浏览器演示模式暂不支持：${method}`);
  }
}
