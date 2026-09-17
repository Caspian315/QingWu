export type FactStatus = "missing" | "extracted" | "confirmed" | "changed" | "conflicting";
export type DraftStatus = "draft" | "missing_facts" | "needs_review" | "ready_to_copy" | "stale" | "archived";

export interface TemplateSummary {
  id: string;
  version: string;
  title: string;
  description: string;
}

export interface FactField {
  key: string;
  label: string;
  type: string;
  required: boolean;
  protected: boolean;
  sensitive: boolean;
  value: string | number | null;
  status: FactStatus;
  source_text?: string | null;
}

export interface TemplateDocument {
  id: string;
  title: string;
  kind: string;
  required_facts: string[];
}

export interface MaterialSlot {
  id: string;
  title: string;
  required: boolean;
  min_items: number;
  max_items: number | null;
  extensions: string[];
}

export interface TemplateGroup {
  id: string;
  title: string;
  repeatable: boolean;
  min_items: number;
  facts: Array<{ key: string; label: string; type: string; required: boolean; sensitive?: boolean }>;
  material_slots: MaterialSlot[];
}

export interface GroupInstance {
  id: string;
  affair_id: string;
  group_id: string;
  title: string;
  facts: Record<string, { label: string; value: string | number | null; required: boolean; sensitive?: boolean }>;
  created_at?: string;
}

export interface WorkflowTemplate extends TemplateSummary {
  facts: Array<{ key: string; label: string; type: string; required: boolean }>;
  stages: Array<{ id: string; title: string }>;
  documents: TemplateDocument[];
  material_slots: MaterialSlot[];
  groups: TemplateGroup[];
}

export interface TimelineTask {
  id: string;
  title: string;
  stage: string;
  due_at: string | null;
  completed: boolean;
  priority: string;
  notes: string;
  reminder_enabled: boolean;
  reminder_offsets: number[];
}

export interface Draft {
  id: string;
  document_id: string;
  title: string;
  kind: string;
  version: number;
  body: string;
  rendered_body: string;
  fact_version: number;
  used_fact_keys: string[];
  required_fact_keys: string[];
  locked_blocks: Array<{ index: number; text: string }>;
  status: DraftStatus;
  ai_generated: boolean;
  created_at: string;
}

export interface Material {
  id: string;
  original_name: string;
  source_path: string;
  extension: string;
  size_bytes: number;
  sha256: string;
  slot_id: string | null;
  group_instance_id: string | null;
  suggestions?: Array<{ slot_id: string; title: string; score: number; reasons: string[] }>;
}

export interface AffairSummary {
  id: string;
  title: string;
  template_id: string;
  template_version: string;
  created_at: string;
  updated_at: string;
  current_fact_version: number;
  ai_used: boolean;
  task_progress: { completed: number; total: number };
}

export interface Affair extends Omit<AffairSummary, "task_progress"> {
  source_text: string;
  template: WorkflowTemplate;
  facts: Record<string, FactField>;
  tasks: TimelineTask[];
  drafts: Draft[];
  materials: Material[];
  recipients: Array<{ id: string; name: string; status: string; notes: string; updated_at: string }>;
  group_instances: GroupInstance[];
}

export interface CheckIssue {
  code: string;
  severity: "error" | "warning";
  message: string;
}

export interface AffairCheck {
  affair_id: string;
  ok: boolean;
  issues: CheckIssue[];
  summary: { errors: number; warnings: number };
}

export interface StyleCard {
  id: string;
  name: string;
  document_kind: string;
  card: Record<string, string | string[]>;
  confirmed: boolean;
  sample_count: number;
  created_at: string;
  updated_at: string;
}
