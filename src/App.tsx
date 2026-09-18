import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent } from "react";
import {
  Archive, Bell, Bot, Check, CheckCircle2, ChevronRight, CircleAlert, ClipboardList,
  Clock3, Copy, FileArchive, FileText, FolderInput, Home, KeyRound, Layers3, LoaderCircle,
  Menu, MessageSquareText, Palette, Plus, RefreshCw, Save, Settings, ShieldCheck, Sparkles, Users, X,
} from "lucide-react";
import { autostartStatus, call, chooseArchivePath, chooseMaterialFiles, chooseMaterialFolder, chooseStyleFiles, configuredModel, credentialStatus, deleteApiKey, isDesktop, listenForMaterialDrops, pasteClipboardImage, saveApiKey, saveConfiguredModel, setAutostart } from "./lib/api";
import type { Affair, AffairCheck, AffairSummary, Draft, FactField, StyleCard, TemplateSummary } from "./types";

type Tab = "overview" | "facts" | "drafts" | "style" | "timeline" | "materials" | "archive" | "settings";
type Notice = { kind: "success" | "error"; text: string } | null;
type StyleCardForm = {
  tone: string;
  greeting: string;
  paragraph_length: string;
  heading_style: string;
  emoji_policy: string;
  common_phrases: string;
  forbidden_phrases: string;
  sign_off: string;
  punctuation: string;
};

const navItems: Array<{ id: Tab; label: string; icon: typeof Home }> = [
  { id: "overview", label: "事务总览", icon: Home },
  { id: "facts", label: "事实底稿", icon: ClipboardList },
  { id: "drafts", label: "通知与推文", icon: MessageSquareText },
  { id: "style", label: "组织风格", icon: Palette },
  { id: "timeline", label: "任务进度", icon: Clock3 },
  { id: "materials", label: "材料", icon: FolderInput },
  { id: "archive", label: "检查与归档", icon: Archive },
  { id: "settings", label: "设置", icon: Settings },
];

const factStatus: Record<string, { label: string; tone: string }> = {
  missing: { label: "缺失", tone: "danger" }, extracted: { label: "待确认", tone: "warning" },
  confirmed: { label: "已确认", tone: "success" }, changed: { label: "已修改，待确认", tone: "warning" },
  conflicting: { label: "有冲突", tone: "danger" },
};

const draftStatus: Record<string, { label: string; tone: string }> = {
  draft: { label: "草稿", tone: "neutral" }, missing_facts: { label: "缺少事实", tone: "danger" },
  needs_review: { label: "待审核", tone: "warning" }, ready_to_copy: { label: "可复制", tone: "success" },
  stale: { label: "事实已变更", tone: "danger" }, archived: { label: "已归档", tone: "neutral" },
};

const documentKindLabels: Record<string, string> = {
  notice: "群通知",
  article: "公众号推文",
  recruitment: "招募推文",
};

function styleCardToForm(card: StyleCard["card"]): StyleCardForm {
  const text = (key: string, fallback = "") => typeof card[key] === "string" ? card[key] as string : fallback;
  const lines = (key: string) => Array.isArray(card[key]) ? (card[key] as string[]).join("\n") : "";
  return {
    tone: text("tone"),
    greeting: text("greeting"),
    paragraph_length: text("paragraph_length", "short"),
    heading_style: text("heading_style"),
    emoji_policy: text("emoji_policy"),
    common_phrases: lines("common_phrases"),
    forbidden_phrases: lines("forbidden_phrases"),
    sign_off: text("sign_off"),
    punctuation: text("punctuation", "中文全角标点"),
  };
}

function styleFormToCard(form: StyleCardForm): StyleCard["card"] {
  const lines = (value: string) => value.split("\n").map((item) => item.trim()).filter(Boolean);
  return {
    tone: form.tone.trim(),
    greeting: form.greeting.trim(),
    paragraph_length: form.paragraph_length,
    heading_style: form.heading_style.trim(),
    emoji_policy: form.emoji_policy.trim(),
    common_phrases: lines(form.common_phrases),
    forbidden_phrases: lines(form.forbidden_phrases),
    sign_off: form.sign_off.trim(),
    punctuation: form.punctuation.trim(),
  };
}

function formatDate(value?: string | null) {
  if (!value) return "尚未安排";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function App() {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [affairs, setAffairs] = useState<AffairSummary[]>([]);
  const [current, setCurrent] = useState<Affair | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [createOpen, setCreateOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  const show = (kind: "success" | "error", text: string) => {
    setNotice({ kind, text });
    window.setTimeout(() => setNotice(null), 4200);
  };

  const refreshAffairs = useCallback(async () => {
    const list = await call<AffairSummary[]>("affair.list");
    setAffairs(list);
    return list;
  }, []);

  const openAffair = useCallback(async (id: string) => {
    setBusy(true);
    try {
      const value = await call<Affair>("affair.open", { id });
      setCurrent(value);
      setSidebarOpen(false);
    } catch (error) {
      show("error", error instanceof Error ? error.message : String(error));
    } finally { setBusy(false); }
  }, []);

  const refreshCurrent = useCallback(async () => {
    if (!current) return;
    await Promise.all([openAffair(current.id), refreshAffairs()]);
  }, [current?.id, openAffair, refreshAffairs]);

  useEffect(() => {
    Promise.all([call<TemplateSummary[]>("template.list"), refreshAffairs()])
      .then(([templateList, affairList]) => {
        setTemplates(templateList);
        if (affairList.length) void openAffair(affairList[0].id);
      })
      .catch((error) => show("error", error instanceof Error ? error.message : String(error)));
  }, []);

  async function createAffair(title: string, templateId: string) {
    setBusy(true);
    try {
      const created = await call<Affair>("affair.create", { title, template_id: templateId });
      await refreshAffairs();
      setCurrent(created); setCreateOpen(false); setActiveTab("facts");
      show("success", "事务已创建。先确认事实，再生成文案。 ");
    } catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }

  const completed = current?.tasks.filter((task) => task.completed).length ?? 0;
  const progress = current?.tasks.length ? Math.round((completed / current.tasks.length) * 100) : 0;

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="brand"><div className="brand-mark">轻</div><div><strong>轻务</strong><span>Qingwu · v0.1.0</span></div></div>
        <button className="primary wide" onClick={() => setCreateOpen(true)}><Plus size={17} />新建事务</button>
        <div className="sidebar-caption">我的事务</div>
        <div className="affair-list">
          {affairs.length === 0 && <p className="empty-small">还没有事务。从收到的第一条通知开始吧。</p>}
          {affairs.map((affair) => (
            <button key={affair.id} className={`affair-button ${current?.id === affair.id ? "selected" : ""}`} onClick={() => void openAffair(affair.id)}>
              <span className="affair-icon"><Layers3 size={16} /></span>
              <span><strong>{affair.title}</strong><small>{templates.find((item) => item.id === affair.template_id)?.title ?? affair.template_id} · facts-v{affair.current_fact_version}</small></span>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
        <div className="local-badge"><ShieldCheck size={16} /><div><strong>默认本地保存</strong><span>{isDesktop() ? "桌面模式 · 数据不上传" : "浏览器演示模式"}</span></div></div>
      </aside>
      {sidebarOpen && <button className="sidebar-backdrop" aria-label="关闭侧栏" onClick={() => setSidebarOpen(false)} />}

      <main className="main-shell">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setSidebarOpen(true)}><Menu /></button>
          <div><span className="eyebrow">当前事务</span><h1>{current?.title ?? "欢迎使用轻务"}</h1></div>
          <div className="topbar-actions">
            {current && <span className="fact-version">facts-v{current.current_fact_version}</span>}
            <button className="icon-button" title="刷新" onClick={() => void refreshCurrent()} disabled={!current || busy}><RefreshCw className={busy ? "spin" : ""} size={18} /></button>
          </div>
        </header>

        {current ? <>
          <nav className="section-nav">
            {navItems.map(({ id: itemId, label, icon: Icon }) => <button key={itemId} className={activeTab === itemId ? "active" : ""} onClick={() => setActiveTab(itemId)}><Icon size={16} />{label}</button>)}
          </nav>
          <div className="content-area">
            {activeTab === "overview" && <Overview affair={current} progress={progress} onNavigate={setActiveTab} />}
            {activeTab === "facts" && <Facts affair={current} onChanged={refreshCurrent} show={show} />}
            {activeTab === "drafts" && <Drafts affair={current} onChanged={refreshCurrent} show={show} />}
            {activeTab === "style" && <StyleCards show={show} />}
            {activeTab === "timeline" && <Timeline affair={current} onChanged={refreshCurrent} show={show} />}
            {activeTab === "materials" && <div className="page-stack"><Materials affair={current} onChanged={refreshCurrent} show={show} />{current.template_id === "material-collection" && <RecipientProgress affair={current} onChanged={refreshCurrent} show={show} />}</div>}
            {activeTab === "archive" && <ArchivePanel affair={current} show={show} />}
            {activeTab === "settings" && <SettingsPanel show={show} />}
          </div>
        </> : <Welcome onCreate={() => setCreateOpen(true)} />}
      </main>

      {createOpen && <CreateDialog templates={templates} busy={busy} onClose={() => setCreateOpen(false)} onCreate={createAffair} />}
      {notice && <div className={`toast ${notice.kind}`}><span>{notice.kind === "success" ? <CheckCircle2 /> : <CircleAlert />}</span>{notice.text}</div>}
      {busy && <div className="busy-line" />}
    </div>
  );
}

function Welcome({ onCreate }: { onCreate: () => void }) {
  return <div className="welcome"><div className="welcome-art"><Sparkles /></div><p className="kicker">一份事实，多处复用</p><h2>把一件学生工作<br />从通知做到归档</h2><p>轻务围绕事务组织事实、文案、待办和材料。AI 可以加速录入与写作，但断网也不耽误工作。</p><button className="primary" onClick={onCreate}><Plus size={18} />创建第一项事务</button><div className="welcome-flow"><span>事实底稿</span><ChevronRight /><span>通知与提醒</span><ChevronRight /><span>材料归档</span></div></div>;
}

function CreateDialog({ templates, busy, onClose, onCreate }: { templates: TemplateSummary[]; busy: boolean; onClose: () => void; onCreate: (title: string, templateId: string) => Promise<void> }) {
  const [title, setTitle] = useState("");
  const [templateId, setTemplateId] = useState(templates[0]?.id ?? "activity-organization");
  function submit(event: FormEvent) { event.preventDefault(); if (title.trim()) void onCreate(title.trim(), templateId); }
  return <div className="modal-backdrop" role="presentation"><form className="modal" onSubmit={submit}><div className="modal-head"><div><span className="eyebrow">新建事务</span><h2>这次要办什么？</h2></div><button type="button" className="icon-button" onClick={onClose}><X /></button></div><label>事务名称<input autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：十月主题团日活动" /></label><div className="template-grid">{templates.map((template) => <button type="button" key={template.id} className={`template-card ${templateId === template.id ? "selected" : ""}`} onClick={() => setTemplateId(template.id)}><span>{template.id === "activity-organization" ? "活" : template.id === "material-collection" ? "集" : "报"}</span><strong>{template.title}</strong><small>{template.description}</small>{templateId === template.id && <Check size={18} />}</button>)}</div><div className="modal-actions"><button type="button" className="secondary" onClick={onClose}>取消</button><button className="primary" disabled={!title.trim() || busy}>{busy && <LoaderCircle className="spin" />}创建事务</button></div></form></div>;
}

export function Overview({ affair, progress, onNavigate }: { affair: Affair; progress: number; onNavigate: (tab: Tab) => void }) {
  const requiredFacts = Object.values(affair.facts).filter((field) => field.required);
  const confirmedRequired = requiredFacts.filter((field) => field.status === "confirmed").length;
  const required = requiredFacts.length;
  const readyDrafts = affair.drafts.filter((draft) => draft.status === "ready_to_copy").length;
  const nextTask = affair.tasks.find((task) => !task.completed);
  return <div className="page-stack"><section className="hero-card"><div><p className="kicker">{affair.template.title}</p><h2>{affair.title}</h2><p>{affair.template.description}</p></div><div className="progress-ring" aria-label={`任务进度 ${progress}%`} style={{ "--progress": `${progress * 3.6}deg` } as CSSProperties}><span><strong>{progress}%</strong><small>任务进度</small></span></div></section><div className="stat-grid"><button className="stat-card" onClick={() => onNavigate("facts")}><ClipboardList /><span><strong>{confirmedRequired}</strong> / {required} 个必填事实</span><small>点击继续确认</small></button><button className="stat-card" onClick={() => onNavigate("drafts")}><FileText /><span><strong>{readyDrafts}</strong> 篇可复制文案</span><small>{affair.drafts.length} 篇已有草稿</small></button><button className="stat-card" onClick={() => onNavigate("timeline")}><Clock3 /><span><strong>{affair.tasks.filter((task) => task.completed).length}</strong> / {affair.tasks.length} 项待办完成</span><small>下一项：{nextTask?.title ?? "全部完成"}</small></button><button className="stat-card" onClick={() => onNavigate("materials")}><FolderInput /><span><strong>{affair.materials.length}</strong> 份材料</span><small>检查槽位与文件状态</small></button></div><section className="panel"><div className="panel-head"><div><span className="eyebrow">推荐下一步</span><h3>{confirmedRequired < required ? "先把事实底稿确认完整" : affair.drafts.length === 0 ? "基于事实生成第一份通知" : nextTask ? nextTask.title : "检查并导出归档"}</h3></div><button className="primary" onClick={() => onNavigate(confirmedRequired < required ? "facts" : affair.drafts.length === 0 ? "drafts" : nextTask ? "timeline" : "archive")}>继续处理<ChevronRight size={17} /></button></div><p className="muted">事实变化时，轻务只会让引用相关字段的草稿过期；旧版本会继续保留。</p></section></div>;
}

export function Facts({ affair, onChanged, show }: { affair: Affair; onChanged: () => Promise<void>; show: (kind: "success" | "error", text: string) => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [source, setSource] = useState(affair.source_text || "");
  const [extracting, setExtracting] = useState(false);
  const [confirmingAll, setConfirmingAll] = useState(false);
  const dirtyKeys = useRef(new Set<string>());
  const loadedAffairId = useRef(affair.id);

  useEffect(() => {
    const freshValues = Object.fromEntries(
      Object.entries(affair.facts).map(([key, field]) => [key, field.value == null ? "" : String(field.value)]),
    );
    if (loadedAffairId.current !== affair.id) {
      loadedAffairId.current = affair.id;
      dirtyKeys.current.clear();
      setValues(freshValues);
      setSource(affair.source_text || "");
      return;
    }
    setValues((current) => Object.fromEntries(
      Object.entries(freshValues).map(([key, value]) => [
        key,
        dirtyKeys.current.has(key) ? current[key] ?? value : value,
      ]),
    ));
  }, [affair.id, affair.current_fact_version]);

  const fields = Object.values(affair.facts);
  const missingRequired = fields.filter((field) => field.required && !values[field.key]?.trim());
  const unresolvedConflicts = fields.filter((field) => field.status === "conflicting" && !dirtyKeys.current.has(field.key));
  const confirmableEntries = fields.flatMap((field) => {
    const value = values[field.key];
    if (!value?.trim()) return [];
    const matchesSavedValue = String(field.value ?? "") === value;
    if (field.status === "confirmed" && matchesSavedValue) return [];
    return [[field.key, value] as const];
  });
  const confirmableValues = Object.fromEntries(confirmableEntries);

  function changeValue(key: string, value: string) {
    dirtyKeys.current.add(key);
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function update(field: FactField, confirm: boolean) {
    try {
      await call(confirm ? "fact.confirm" : "fact.update", { affair_id: affair.id, key: field.key, value: values[field.key] });
      dirtyKeys.current.delete(field.key);
      await onChanged(); show("success", confirm ? `“${field.label}”已确认` : `“${field.label}”已保存，发布前还需确认`);
    } catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
  }
  async function confirmAll() {
    if (missingRequired.length) {
      show("error", `请先填写必填事实：${missingRequired.map((field) => field.label).join("、")}`);
      return;
    }
    if (unresolvedConflicts.length) {
      show("error", `请先修改冲突事实：${unresolvedConflicts.map((field) => field.label).join("、")}`);
      return;
    }
    if (!confirmableEntries.length) return;
    setConfirmingAll(true);
    try {
      await call("fact.confirm", { affair_id: affair.id, values: confirmableValues });
      Object.keys(confirmableValues).forEach((key) => dirtyKeys.current.delete(key));
      await onChanged();
      show("success", `已确认 ${confirmableEntries.length} 项事实。`);
    } catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
    finally { setConfirmingAll(false); }
  }
  async function extract() {
    if (!source.trim()) return;
    setExtracting(true);
    try { await call("fact.extract", { affair_id: affair.id, source_text: source, use_saved_api_key: true, model: configuredModel(), timezone: Intl.DateTimeFormat().resolvedOptions().timeZone }); await onChanged(); show("success", "候选事实已提取，请逐项核对后确认。"); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
    finally { setExtracting(false); }
  }
  const bulkHint = missingRequired.length
    ? `请先填写必填事实：${missingRequired.map((field) => field.label).join("、")}`
    : unresolvedConflicts.length
      ? `请先修改冲突事实：${unresolvedConflicts.map((field) => field.label).join("、")}`
      : confirmableEntries.length
        ? `将确认 ${confirmableEntries.length} 项已填写事实；空的可选字段仍保持缺失。`
        : "当前所有已填写事实均已确认。";
  const cannotConfirmAll = confirmingAll || missingRequired.length > 0 || unresolvedConflicts.length > 0 || confirmableEntries.length === 0;

  return (
    <div className="two-column">
      <section className="panel sticky-card">
        <div className="panel-head"><div><span className="eyebrow">可选 AI 辅助</span><h3>粘贴上级通知</h3></div><Bot size={22} /></div>
        <textarea className="source-text" value={source} onChange={(event) => setSource(event.target.value)} placeholder="粘贴群通知、聊天记录或活动要求……" />
        <button className="primary wide" onClick={() => void extract()} disabled={!source.trim() || extracting}>{extracting ? <LoaderCircle className="spin" /> : <Sparkles />}提取候选事实</button>
        <p className="hint">相对日期和 AI 结果都不会自动确认。“本周六”会保留原文，必须由你核对。</p>
      </section>
      <section className="panel">
        <div className="panel-head"><div><span className="eyebrow">facts-v{affair.current_fact_version}</span><h3>事实底稿</h3></div><span className="privacy-note"><ShieldCheck size={15} />只有已确认值可进入文案</span></div>
        <div className="fact-bulk-actions">
          <div><strong>批量确认</strong><span>{bulkHint}</span></div>
          <button className="primary" onClick={() => void confirmAll()} disabled={cannotConfirmAll}>{confirmingAll ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}确认全部已填写事实</button>
        </div>
        <div className="fact-list">
          {fields.map((field) => (
            <div className="fact-row" key={field.key}>
              <div className="field-title"><label htmlFor={`fact-${field.key}`}>{field.label}{field.required && <em>*</em>}</label><span className={`chip ${factStatus[field.status]?.tone}`}>{factStatus[field.status]?.label ?? field.status}</span></div>
              {field.type === "textarea"
                ? <textarea id={`fact-${field.key}`} value={values[field.key] ?? ""} onChange={(event) => changeValue(field.key, event.target.value)} />
                : <input id={`fact-${field.key}`} type={field.type === "datetime" ? "datetime-local" : field.type} value={values[field.key] ?? ""} onChange={(event) => changeValue(field.key, event.target.value)} />}
              <div className="field-actions">
                <small>{field.source_text ? `来源：“${field.source_text}”` : field.protected ? "关键事实 · 使用引用节点保护" : "叙述字段"}</small>
                <span><button className="text-button" onClick={() => void update(field, false)}><Save size={14} />保存</button><button className="text-button confirm" onClick={() => void update(field, true)} disabled={!values[field.key]?.trim()}><Check size={14} />确认</button></span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Drafts({ affair, onChanged, show }: { affair: Affair; onChanged: () => Promise<void>; show: (kind: "success" | "error", text: string) => void }) {
  const [selected, setSelected] = useState(affair.template.documents[0]?.id ?? "");
  const [useAI, setUseAI] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editedBody, setEditedBody] = useState("");
  const [lockedParagraphs, setLockedParagraphs] = useState<number[]>([]);
  const document = affair.template.documents.find((item) => item.id === selected);
  const draft = affair.drafts.find((item) => item.document_id === selected);
  useEffect(() => {
    setEditedBody(draft?.body ?? "");
    setLockedParagraphs((draft?.locked_blocks ?? []).map((block) => block.index));
    setEditing(false);
  }, [draft?.id]);
  async function generate() {
    setGenerating(true);
    try { await call<Draft>("draft.generate", { affair_id: affair.id, document_id: selected, use_ai: useAI, use_saved_api_key: true, model: configuredModel(), preserve_locked_from: draft?.id }); await onChanged(); show("success", "已创建新文案版本；锁定段落和旧版本均已保留。"); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
    finally { setGenerating(false); }
  }
  async function saveManualVersion() {
    if (!draft) return;
    try { await call("draft.update", { id: draft.id, body: editedBody, locked_paragraphs: lockedParagraphs }); await onChanged(); show("success", "手工修改已保存为新版本。"); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
  }
  async function markReady() {
    if (!draft) return;
    try { await call("draft.mark_ready", { id: draft.id }); await onChanged(); show("success", "文案已通过人工审核，可以复制。"); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
  }
  async function copy() {
    if (!draft) return;
    await navigator.clipboard.writeText(draft.rendered_body); show("success", "已复制到剪贴板");
  }
  const paragraphs = editedBody.trim().split(/\n{2,}/);
  return <div className="draft-layout"><aside className="document-list"><span className="eyebrow">文案类型</span>{affair.template.documents.map((item) => { const existing = affair.drafts.find((draftItem) => draftItem.document_id === item.id); return <button key={item.id} className={selected === item.id ? "selected" : ""} onClick={() => setSelected(item.id)}><FileText size={17} /><span><strong>{item.title}</strong><small>{existing ? `v${existing.version} · ${draftStatus[existing.status]?.label}` : "尚未生成"}</small></span></button>; })}</aside><section className="panel draft-editor"><div className="panel-head"><div><span className="eyebrow">{document?.kind ?? "文案"}</span><h3>{document?.title ?? "选择文案"}</h3></div><div className="heading-actions">{draft && <button className="text-button" onClick={() => setEditing(!editing)}>{editing ? "取消编辑" : "手工修改"}</button>}{draft && <span className={`chip ${draftStatus[draft.status]?.tone}`}>{draftStatus[draft.status]?.label}</span>}</div></div>{draft ? <><div className={`draft-banner ${draft.status === "stale" || draft.status === "missing_facts" ? "alert" : ""}`}>{draft.status === "stale" ? "事实底稿已经变化。这份旧草稿被保留，但不能直接标记为可复制。" : draft.status === "missing_facts" ? "文案中仍有待填写字段。确认事实后重新生成。" : draft.status === "needs_review" ? "请人工检查措辞和事实，确认后再复制。" : "这份文案已经过人工确认。"}</div>{editing ? <div className="manual-editor"><textarea value={editedBody} onChange={(event) => setEditedBody(event.target.value)} /><span className="eyebrow">重新生成时保留这些段落</span><div className="paragraph-locks">{paragraphs.map((paragraph, index) => <label key={`${index}-${paragraph.slice(0, 8)}`}><input type="checkbox" checked={lockedParagraphs.includes(index)} onChange={(event) => setLockedParagraphs(event.target.checked ? [...lockedParagraphs, index] : lockedParagraphs.filter((value) => value !== index))} /><span>{paragraph.slice(0, 70) || "空段落"}</span></label>)}</div><button className="secondary" onClick={() => void saveManualVersion()}><Save size={16} />保存为新版本</button></div> : <pre className="draft-preview">{draft.rendered_body}</pre>}<div className="draft-meta"><span>基于 facts-v{draft.fact_version}</span><span>文案 v{draft.version}</span><span>{draft.ai_generated ? "AI 辅助" : "离线模板"}</span><span>锁定 {draft.locked_blocks?.length ?? 0} 段</span></div></> : <div className="empty-state"><MessageSquareText /><h4>还没有这类文案</h4><p>轻务会从同一份事实底稿读取时间、地点和联系人。</p></div>}<div className="editor-actions"><label className="switch-row"><input type="checkbox" checked={useAI} onChange={(event) => setUseAI(event.target.checked)} /><span>使用 AI 优化表达</span><small>关闭时使用确定性模板</small></label><div><button className="secondary" onClick={() => void generate()} disabled={!selected || generating}>{generating ? <LoaderCircle className="spin" /> : <RefreshCw size={16} />}{draft ? "生成新版本" : "生成草稿"}</button>{draft && <button className="secondary" onClick={() => void markReady()} disabled={draft.status === "stale" || draft.status === "missing_facts" || draft.status === "ready_to_copy"}><CheckCircle2 size={16} />确认可用</button>}<button className="primary" onClick={() => void copy()} disabled={!draft || draft.status !== "ready_to_copy"}><Copy size={16} />复制文案</button></div></div></section></div>;
}

export function StyleCards({ show }: { show: (kind: "success" | "error", text: string) => void }) {
  const [cards, setCards] = useState<StyleCard[]>([]);
  const [active, setActive] = useState<StyleCard | null>(null);
  const [name, setName] = useState("组织通知风格");
  const [kind, setKind] = useState("notice");
  const [samples, setSamples] = useState("");
  const [paths, setPaths] = useState<string[]>([]);
  const [preview, setPreview] = useState<{ sample_count: number; text_length: number; pii_warnings: Array<{ type: string; count: number }> } | null>(null);
  const [cardForm, setCardForm] = useState<StyleCardForm>(() => styleCardToForm({}));
  const [busy, setBusy] = useState(false);
  const texts = () => samples.split(/\n\s*---+\s*\n/).map((value) => value.trim()).filter(Boolean);
  const reload = useCallback(async (selectId?: string) => {
    const list = await call<StyleCard[]>("style.list");
    setCards(list);
    const selected = list.find((item) => item.id === selectId) ?? list[0] ?? null;
    setActive(selected);
    setCardForm(styleCardToForm(selected?.card ?? {}));
  }, []);
  useEffect(() => { void reload().catch((error) => show("error", error instanceof Error ? error.message : String(error))); }, []);
  async function chooseFiles() {
    try { setPaths(await chooseStyleFiles()); setPreview(null); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
  }
  async function inspect() {
    setBusy(true);
    try { setPreview(await call("style.preview_upload", { texts: texts(), paths })); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  async function importExamples() {
    setBusy(true);
    try {
      const created = await call<StyleCard>("style.import_examples", { name, document_kind: kind, texts: texts(), paths });
      await reload(created.id); show("success", "样本已在本地导入。确认脱敏结果后可生成风格卡。");
    } catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  async function generate() {
    if (!active) return;
    setBusy(true);
    try { const generated = await call<StyleCard>("style.generate_card", { id: active.id, use_saved_api_key: true, model: configuredModel() }); await reload(generated.id); show("success", "AI 已提炼结构化风格；请编辑并人工确认。"); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if (!active) return;
    const card = styleFormToCard(cardForm);
    if ((card.common_phrases as string[]).length > 20 || (card.forbidden_phrases as string[]).length > 20) {
      show("error", "常用表达和禁用表达分别最多填写 20 条。");
      return;
    }
    try {
      const confirmed = await call<StyleCard>("style.confirm_card", { id: active.id, card, delete_cache: true });
      await reload(confirmed.id); show("success", "风格卡已确认，原始提取文本缓存已删除。");
    } catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
  }
  function selectCard(card: StyleCard) { setActive(card); setCardForm(styleCardToForm(card.card)); }
  function updateCardField<K extends keyof StyleCardForm>(key: K, value: StyleCardForm[K]) {
    setCardForm((current) => ({ ...current, [key]: value }));
  }
  return <div className="style-layout"><aside className="document-list"><span className="eyebrow">已保存风格</span>{cards.map((card) => <button key={card.id} className={active?.id === card.id ? "selected" : ""} onClick={() => selectCard(card)}><Palette size={17} /><span><strong>{card.name}</strong><small>{documentKindLabels[card.document_kind] ?? card.document_kind} · {card.confirmed ? "已确认" : "待确认"}</small></span></button>)}{!cards.length && <p className="empty-small">还没有风格卡。右侧导入 3–10 篇同类文案。</p>}</aside><div className="page-stack"><section className="panel"><div className="panel-head"><div><span className="eyebrow">本地预处理</span><h3>导入认可的历史文案</h3></div><Users size={21} /></div><div className="form-grid"><label>风格卡名称<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>文案类型<select value={kind} onChange={(event) => setKind(event.target.value)}><option value="notice">群通知</option><option value="article">公众号推文</option><option value="recruitment">招募推文</option></select></label></div><label>粘贴样本（用单独一行 <code>---</code> 分隔）<textarea className="style-samples" value={samples} onChange={(event) => { setSamples(event.target.value); setPreview(null); }} placeholder={'各位同学：……\n\n---\n\n第二篇历史文案……'} /></label><div className="inline-actions"><button className="secondary" onClick={() => void chooseFiles()}><FolderInput size={16} />选择 TXT / MD / DOCX / PDF</button><span>{paths.length ? `已选择 ${paths.length} 个文件` : "默认只提取本地文本，不上传原文件"}</span><button className="secondary" onClick={() => void inspect()} disabled={busy || (!texts().length && !paths.length)}>上传前预览</button></div>{preview && <div className="preview-box"><strong>{preview.sample_count} 篇 · {preview.text_length} 个字符</strong>{preview.pii_warnings.length ? <span className="warning-text">发现：{preview.pii_warnings.map((item) => `${item.type} ${item.count} 处`).join("、")}。请先从样本中删除。</span> : <span>未命中内置敏感信息模式，仍请人工检查。</span>}<button className="primary" onClick={() => void importExamples()} disabled={preview.sample_count === 0}>确认并导入</button></div>}</section>{active && <section className="panel style-card-editor"><div className="panel-head"><div><span className="eyebrow">{active.sample_count} 篇样本</span><h3>{active.name}</h3></div><span className={`chip ${active.confirmed ? "success" : "warning"}`}>{active.confirmed ? "已启用" : "等待确认"}</span></div><p className="muted style-editor-intro">这些设置决定以后生成文案时采用的表达习惯。可以直接修改，确认后才会启用。</p><div className="style-card-form"><label>语气风格<input value={cardForm.tone} onChange={(event) => updateCardField("tone", event.target.value)} placeholder="例如：正式但不生硬" /></label><label>开场称呼<input value={cardForm.greeting} onChange={(event) => updateCardField("greeting", event.target.value)} placeholder="例如：各位同学：" /></label><label>段落长度<select value={cardForm.paragraph_length} onChange={(event) => updateCardField("paragraph_length", event.target.value)}><option value="short">短段落</option><option value="medium">中等段落</option><option value="long">长段落</option></select></label><label>标题样式<input value={cardForm.heading_style} onChange={(event) => updateCardField("heading_style", event.target.value)} placeholder="例如：序号加短标题" /></label><label>表情使用规则<input value={cardForm.emoji_policy} onChange={(event) => updateCardField("emoji_policy", event.target.value)} placeholder="例如：通知中不使用" /></label><label>结尾署名<input value={cardForm.sign_off} onChange={(event) => updateCardField("sign_off", event.target.value)} placeholder="例如：组织落款" /></label><label className="span-two">标点风格<input value={cardForm.punctuation} onChange={(event) => updateCardField("punctuation", event.target.value)} placeholder="例如：中文全角标点" /></label></div><div className="phrase-grid"><label>常用表达<span>每行填写一条，最多 20 条</span><textarea value={cardForm.common_phrases} onChange={(event) => updateCardField("common_phrases", event.target.value)} placeholder={'请各位同学注意\n感谢大家的配合'} /></label><label>禁用表达<span>每行填写一条，最多 20 条</span><textarea value={cardForm.forbidden_phrases} onChange={(event) => updateCardField("forbidden_phrases", event.target.value)} placeholder={'速来\n家人们'} /></label></div><div className="style-card-footer"><p><ShieldCheck size={15} />确认后只保留风格规则，并删除导入的样本文本缓存；不会删除你的原始文件。</p><div className="inline-actions end"><button className="secondary" onClick={() => void generate()} disabled={busy}><Sparkles size={16} />AI 重新提炼</button><button className="primary" onClick={() => void confirm()}><Check size={16} />确认并启用风格</button></div></div></section>}</div></div>;
}

function Timeline({ affair, onChanged, show }: { affair: Affair; onChanged: () => Promise<void>; show: (kind: "success" | "error", text: string) => void }) {
  const stages = useMemo(() => new Map(affair.template.stages?.map((stage) => [stage.id, stage.title]) ?? []), [affair.template]);
  async function toggle(id: string, completed: boolean) {
    try { await call("timeline.update_task", { id, completed }); await onChanged(); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
  }
  return <section className="panel"><div className="panel-head"><div><span className="eyebrow">任务进度</span><h3>待办与截止提醒</h3></div><span className="privacy-note"><Bell size={15} />默认提前 24 小时、2 小时和到期时</span></div><div className="timeline">{affair.tasks.map((task, index) => <div className={`timeline-item ${task.completed ? "done" : ""}`} key={task.id}><button className="task-check" onClick={() => void toggle(task.id, !task.completed)}>{task.completed && <Check size={15} />}</button><div className="timeline-line" /><div className="task-content"><div><span className="chip neutral">{stages.get(task.stage) ?? task.stage}</span><strong>{task.title}</strong></div><p>{task.due_at ? formatDate(task.due_at) : "确认相关日期后自动计算"}</p>{task.reminder_enabled && task.due_at && <small><Bell size={13} />已启用本地提醒</small>}</div>{index === 0 && !task.completed && <span className="next-label">下一项</span>}</div>)}</div><p className="hint">桌面版最小化到系统托盘后仍会检查提醒；完全退出应用后不会提醒。</p></section>;
}

function Materials({ affair, onChanged, show }: { affair: Affair; onChanged: () => Promise<void>; show: (kind: "success" | "error", text: string) => void }) {
  const [importing, setImporting] = useState(false);
  const [groupValues, setGroupValues] = useState<Record<string, Record<string, string>>>({});
  useEffect(() => {
    setGroupValues(Object.fromEntries(affair.group_instances.map((instance) => [instance.id, Object.fromEntries(Object.entries(instance.facts).map(([key, field]) => [key, field.value == null ? "" : String(field.value)]))])));
  }, [affair.group_instances]);
  async function importPaths(paths: string[]) {
    if (!paths.length) return;
    await call("material.import", { affair_id: affair.id, paths });
    await onChanged();
    show("success", `已导入 ${paths.length} 个材料引用，原文件没有被修改。`);
  }
  useEffect(() => {
    let unlisten: () => void = () => undefined;
    void listenForMaterialDrops((paths) => {
      void importPaths(paths).catch((error) => show("error", error instanceof Error ? error.message : String(error)));
    }).then((dispose) => { unlisten = dispose; });
    return () => unlisten();
  }, [affair.id]);
  async function importFiles() {
    setImporting(true);
    try { await importPaths(await chooseMaterialFiles()); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
    finally { setImporting(false); }
  }
  async function importFolder() {
    setImporting(true);
    try { await importPaths(await chooseMaterialFolder()); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
    finally { setImporting(false); }
  }
  async function pasteImage() {
    setImporting(true);
    try { await importPaths([await pasteClipboardImage()]); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
    finally { setImporting(false); }
  }
  async function assign(materialId: string, target: string) {
    const [groupInstanceId, slotId] = target ? target.split(":", 2) : ["", ""];
    try { await call("material.assign", { id: materialId, slot_id: slotId || null, group_instance_id: groupInstanceId === "root" ? null : groupInstanceId || null }); await onChanged(); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
  }
  async function addGroup(groupId: string) {
    try { await call("group.add", { affair_id: affair.id, group_id: groupId }); await onChanged(); show("success", "已新增一笔报销项目"); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
  }
  async function saveGroup(instanceId: string) {
    try { await call("group.update", { id: instanceId, facts: groupValues[instanceId] }); await onChanged(); show("success", "报销项目已保存"); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
  }
  return <div className="page-stack"><section className="drop-card"><FolderInput size={32} /><div><h3>把材料拖到这里</h3><p>导入后计算 SHA-256。轻务只保存引用，不修改原文件。</p></div><div className="material-actions"><button className="secondary" onClick={() => void pasteImage()} disabled={importing}><ClipboardList size={16} />粘贴截图</button><button className="secondary" onClick={() => void importFolder()} disabled={importing}><FolderInput size={16} />选择文件夹</button><button className="primary" onClick={() => void importFiles()} disabled={importing}>{importing ? <LoaderCircle className="spin" /> : <Plus size={17} />}选择文件</button></div></section>{affair.template.groups.map((group) => <section className="panel" key={group.id}><div className="panel-head"><div><span className="eyebrow">可重复项目</span><h3>{group.title}</h3></div><button className="secondary" onClick={() => void addGroup(group.id)}><Plus size={16} />新增一笔</button></div><div className="expense-grid">{affair.group_instances.filter((instance) => instance.group_id === group.id).map((instance) => <div className="expense-card" key={instance.id}><div className="expense-title"><strong>{instance.title}</strong><span>{group.material_slots.map((slot) => `${slot.title} ${affair.materials.filter((item) => item.group_instance_id === instance.id && item.slot_id === slot.id).length}/${slot.min_items}`).join(" · ")}</span></div>{group.facts.map((field) => <label key={field.key}>{field.label}{field.required && " *"}<input type={field.type === "currency" ? "number" : field.type} step={field.type === "currency" ? "0.01" : undefined} value={groupValues[instance.id]?.[field.key] ?? ""} onChange={(event) => setGroupValues({ ...groupValues, [instance.id]: { ...groupValues[instance.id], [field.key]: event.target.value } })} /></label>)}<button className="text-button confirm" onClick={() => void saveGroup(instance.id)}><Save size={14} />保存项目</button></div>)}</div>{!affair.group_instances.some((instance) => instance.group_id === group.id) && <p className="hint">至少添加 {group.min_items} 笔项目；每笔分别核对发票和支付凭证。</p>}</section>)}<section className="panel"><div className="panel-head"><div><span className="eyebrow">待归类与材料槽位</span><h3>{affair.materials.length} 份材料</h3></div></div>{affair.materials.length ? <div className="material-list">{affair.materials.map((material) => { const target = material.slot_id ? `${material.group_instance_id ?? "root"}:${material.slot_id}` : ""; return <div className="material-row" key={material.id}><span className="file-icon">{material.extension.replace(".", "").slice(0, 4).toUpperCase()}</span><div><strong>{material.original_name}</strong><small>{(material.size_bytes / 1024).toFixed(1)} KB · SHA-256 {material.sha256.slice(0, 12)}…</small></div><select value={target} onChange={(event) => void assign(material.id, event.target.value)}><option value="">待归类</option>{affair.template.material_slots.map((slot) => <option key={`root-${slot.id}`} value={`root:${slot.id}`}>{slot.title}{slot.required ? " *" : ""}</option>)}{affair.group_instances.flatMap((instance) => { const group = affair.template.groups.find((item) => item.id === instance.group_id); return (group?.material_slots ?? []).map((slot) => <option key={`${instance.id}-${slot.id}`} value={`${instance.id}:${slot.id}`}>{instance.title} / {slot.title}{slot.required ? " *" : ""}</option>); })}</select></div>; })}</div> : <div className="empty-state"><FolderInput /><h4>材料池还是空的</h4><p>可以拖入文件，或选择文件、文件夹并粘贴剪贴板截图；原文件始终留在原位。</p></div>}</section></div>;
}

function RecipientProgress({ affair, onChanged, show }: { affair: Affair; onChanged: () => Promise<void>; show: (kind: "success" | "error", text: string) => void }) {
  const [names, setNames] = useState("");
  async function importNames() {
    if (!names.trim()) return;
    try { await call("recipient.import", { affair_id: affair.id, names }); setNames(""); await onChanged(); show("success", "人员名单已导入本地进度表"); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
  }
  async function updateStatus(id: string, status: string) {
    try { await call("recipient.update", { id, status }); await onChanged(); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); }
  }
  return <section className="panel"><div className="panel-head"><div><span className="eyebrow">仅保存在本机</span><h3>人员进度表</h3></div><Users size={20} /></div><div className="recipient-import"><input value={names} onChange={(event) => setNames(event.target.value)} placeholder="粘贴姓名，用换行、逗号或分号分隔" /><button className="secondary" onClick={() => void importNames()} disabled={!names.trim()}><Plus size={16} />导入名单</button></div>{affair.recipients.length ? <div className="recipient-table"><div className="recipient-head"><span>姓名</span><span>状态</span><span>最后更新</span></div>{affair.recipients.map((person) => <div className="recipient-row" key={person.id}><strong>{person.name}</strong><select value={person.status} onChange={(event) => void updateStatus(person.id, event.target.value)}><option value="pending">未提交</option><option value="incomplete">缺材料</option><option value="submitted">已提交</option></select><span>{formatDate(person.updated_at)}</span></div>)}</div> : <p className="hint">导入名单后可手动更新“已提交 / 缺材料 / 未提交”，并据此生成催交话术；轻务不会读取群成员或自动发送。</p>}</section>;
}

function ArchivePanel({ affair, show }: { affair: Affair; show: (kind: "success" | "error", text: string) => void }) {
  const [check, setCheck] = useState<AffairCheck | null>(null);
  const [busy, setBusy] = useState(false);
  async function runCheck() {
    setBusy(true); try { const result = await call<AffairCheck>("affair.check", { affair_id: affair.id }); setCheck(result); show(result.ok ? "success" : "error", result.ok ? "事务检查通过" : `发现 ${result.summary.errors} 个阻断问题`); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); } finally { setBusy(false); }
  }
  async function exportArchive() {
    const output = await chooseArchivePath(affair.title); if (!output) { if (!isDesktop()) show("error", "浏览器演示模式不写入归档，请使用桌面版。"); return; }
    setBusy(true); try { const result = await call<{ path: string }>("affair.export", { affair_id: affair.id, output, allow_warnings: true }); show("success", `归档已导出：${result.path}`); }
    catch (error) { show("error", error instanceof Error ? error.message : String(error)); } finally { setBusy(false); }
  }
  return <div className="page-stack"><section className="archive-hero"><div className="archive-symbol"><FileArchive /></div><div><span className="eyebrow">最后一步</span><h2>检查并封存这项事务</h2><p>归档包包含最终文案、材料副本、SHA-256 清单和 HTML/PDF 检查报告，不包含 API Key 和绝对路径。</p></div></section><section className="panel"><div className="panel-head"><div><span className="eyebrow">发布前检查</span><h3>{check ? (check.ok ? "可以归档" : "仍需处理") : "尚未运行检查"}</h3></div><button className="secondary" onClick={() => void runCheck()} disabled={busy}><RefreshCw className={busy ? "spin" : ""} size={16} />运行检查</button></div>{check && <div className="issue-list">{check.issues.length === 0 ? <div className="all-clear"><CheckCircle2 /><span><strong>没有发现问题</strong><small>事实、材料和文案状态均符合当前模板。</small></span></div> : check.issues.map((issue, index) => <div className={`issue ${issue.severity}`} key={`${issue.code}-${index}`}><CircleAlert /><span><strong>{issue.severity === "error" ? "阻断问题" : "提醒"}</strong>{issue.message}</span></div>)}</div>}<div className="archive-actions"><span>{check ? `${check.summary.errors} 个错误 · ${check.summary.warnings} 个警告` : "先运行一次完整性检查"}</span><button className="primary" onClick={() => void exportArchive()} disabled={busy || !check}><Archive size={17} />导出 ZIP 归档</button></div></section></div>;
}

function SettingsPanel({ show }: { show: (kind: "success" | "error", text: string) => void }) {
  const [hasKey, setHasKey] = useState(false);
  const [key, setKey] = useState("");
  const [model, setModel] = useState(configuredModel());
  const [autostart, setAutostartState] = useState(false);
  useEffect(() => { void credentialStatus().then(setHasKey); void autostartStatus().then(setAutostartState); }, []);
  async function saveKey() { try { await saveApiKey(key); setHasKey(true); setKey(""); show("success", "API Key 已保存到 Windows Credential Manager，不进入轻务数据库。"); } catch (error) { show("error", error instanceof Error ? error.message : String(error)); } }
  async function removeKey() { await deleteApiKey(); setHasKey(false); show("success", "API Key 已从 Windows Credential Manager 删除。"); }
  async function changeAutostart(value: boolean) { try { await setAutostart(value); setAutostartState(value); show("success", value ? "已启用开机启动" : "已关闭开机启动"); } catch (error) { show("error", error instanceof Error ? error.message : String(error)); } }
  function persistModel() { saveConfiguredModel(model); show("success", `默认模型已设为 ${configuredModel()}`); }
  return <div className="page-stack narrow"><section className="panel"><div className="panel-head"><div><span className="eyebrow">可选能力</span><h3>OpenAI</h3></div><span className={`chip ${hasKey ? "success" : "neutral"}`}>{hasKey ? "已配置" : "未配置"}</span></div><p className="muted">不配置 AI 也能使用事务、模板文案、待办、材料检查和归档。请求使用 <code>store: false</code>。</p><label>模型 ID<div className="input-action"><input value={model} onChange={(event) => setModel(event.target.value)} /><button className="secondary" onClick={persistModel}>应用</button></div></label><label>API Key<div className="input-action"><input type="password" autoComplete="off" value={key} onChange={(event) => setKey(event.target.value)} placeholder={hasKey ? "已安全保存；输入新值可替换" : "sk-…"} /><button className="primary" onClick={() => void saveKey()} disabled={!key.trim()}><KeyRound size={16} />保存</button></div></label>{hasKey && <button className="danger-link" onClick={() => void removeKey()}>删除已保存的 API Key</button>}<p className="hint"><ShieldCheck size={14} />Key 由 Rust 层从系统凭据库读取，不返回给前端，也不会进入日志和归档。</p></section><section className="panel"><div className="panel-head"><div><span className="eyebrow">本地提醒</span><h3>后台与开机启动</h3></div><Bell size={20} /></div><label className="setting-toggle"><span><strong>登录 Windows 后启动轻务</strong><small>应用会进入系统托盘，按本地截止时间提醒。</small></span><input type="checkbox" checked={autostart} onChange={(event) => void changeAutostart(event.target.checked)} disabled={!isDesktop()} /></label><p className="hint">完全退出后无法收到提醒；关闭主窗口只会最小化到托盘。</p></section><section className="panel"><div className="panel-head"><div><span className="eyebrow">运行模式</span><h3>{isDesktop() ? "Windows 桌面版" : "浏览器演示版"}</h3></div></div><p className="muted">{isDesktop() ? "桌面版通过 Tauri 调用本地 Python sidecar，数据保存在本机 SQLite。" : "当前用于预览界面，数据只放在浏览器 localStorage；材料导入、系统凭据和归档写入被禁用。"}</p></section></div>;
}

export default App;
