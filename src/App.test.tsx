import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Facts, formatAiErrorMessage, Overview, StyleCards } from "./App";
import { call } from "./lib/api";
import type { Affair, FactField, StyleCard } from "./types";

vi.mock("./lib/api", () => ({
  autostartStatus: vi.fn(async () => false),
  call: vi.fn(async () => ({})),
  chooseArchivePath: vi.fn(async () => null),
  chooseMaterialFiles: vi.fn(async () => []),
  chooseMaterialFolder: vi.fn(async () => []),
  chooseStyleFiles: vi.fn(async () => []),
  configuredModel: vi.fn(() => "gpt-5.4-mini"),
  credentialStatus: vi.fn(async () => false),
  deleteApiKey: vi.fn(async () => undefined),
  isDesktop: vi.fn(() => false),
  listenForMaterialDrops: vi.fn(async () => () => undefined),
  pasteClipboardImage: vi.fn(async () => ""),
  saveApiKey: vi.fn(async () => undefined),
  saveConfiguredModel: vi.fn(),
  setAutostart: vi.fn(async () => undefined),
}));

const mockedCall = vi.mocked(call);

describe("AI error messages", () => {
  it.each([
    [new Error("尚未配置 OpenAI API Key"), "尚未配置 OpenAI API Key。请先到“设置”中保存 API Key，再重新尝试。"],
    [new Error("尚未在设置中保存 OpenAI API Key"), "尚未配置 OpenAI API Key。请先到“设置”中保存 API Key，再重新尝试。"],
    [new Error("OpenAI API 返回 HTTP 401：invalid_api_key"), "当前 API Key 无效或已经失效。请到“设置”中重新保存有效的 API Key。"],
    [new Error("OpenAI API 返回 HTTP 429：rate limited"), "AI 请求过于频繁，或者当前 API 项目额度不足。请稍后重试，并检查 API 项目的额度。"],
    [new Error("OpenAI API 返回 HTTP 404：model_not_found"), "当前模型不可用，或者模型 ID 填写不正确。请到“设置”中检查模型 ID。"],
    [new Error("无法连接 OpenAI API：timed out"), "暂时无法连接 OpenAI。请检查网络或代理设置后重试；不使用 AI 也可以继续完成当前任务。"],
    [new Error("请求超时"), "暂时无法连接 OpenAI。请检查网络或代理设置后重试；不使用 AI 也可以继续完成当前任务。"],
    [new Error("OpenAI API 响应中没有可用文本"), "AI 没有返回可用内容，本次结果没有保存。请重新尝试；如果多次出现，请联系开发者检查 AI 响应。"],
    [new Error("OpenAI API 未返回有效的结构化 JSON"), "AI 返回的内容格式异常，本次结果没有保存。请重新尝试；如果多次出现，请联系开发者检查结构化输出。"],
    [new Error("AI 返回的草稿遗漏事实引用节点：activity_name"), "AI 生成的文案缺少必要事实。为避免发布错误信息，本次草稿没有保存。你可以重试，或关闭 AI 后使用离线模板；如果重复出现，请联系开发者检查文案模板。"],
    [new Error("OpenAI API 返回 HTTP 500：internal details"), "AI 服务暂时无法完成请求，本次结果没有保存。请稍后重试；如果重复出现，请联系开发者并提供错误发生时间。"],
  ])("converts %s into actionable guidance", (error, expected) => {
    expect(formatAiErrorMessage(error)).toBe(expected);
  });

  it("keeps unrelated errors unchanged", () => {
    expect(formatAiErrorMessage(new Error("其他错误"))).toBe("其他错误");
  });
});

function fact(key: string, label: string, required: boolean, type = "text"): FactField {
  return { key, label, required, type, protected: true, sensitive: false, value: null, status: "missing" };
}

function affairFixture(): Affair {
  return {
    id: "affair_test",
    title: "事实确认测试",
    template_id: "activity-organization",
    template_version: "1.0.0",
    created_at: "2026-09-17T00:00:00Z",
    updated_at: "2026-09-17T00:00:00Z",
    current_fact_version: 1,
    ai_used: false,
    source_text: "",
    facts: {
      activity_name: fact("activity_name", "活动名称", true),
      location: fact("location", "活动地点", true),
      notes: fact("notes", "注意事项", false, "textarea"),
    },
    tasks: [],
    drafts: [],
    materials: [],
    recipients: [],
    group_instances: [],
    template: {
      id: "activity-organization",
      version: "1.0.0",
      title: "活动组织",
      description: "测试模板",
      facts: [],
      stages: [],
      documents: [],
      material_slots: [],
      groups: [],
    },
  };
}

function FactsHarness() {
  const [affair, setAffair] = useState(affairFixture);

  async function refresh() {
    const [, params = {}] = mockedCall.mock.calls.at(-1) ?? [];
    const submitted = (params.values ?? (params.key ? { [String(params.key)]: params.value } : {})) as Record<string, string>;
    setAffair((current) => ({
      ...current,
      current_fact_version: current.current_fact_version + 1,
      facts: Object.fromEntries(Object.entries(current.facts).map(([key, field]) => [
        key,
        key in submitted ? { ...field, value: submitted[key], status: "confirmed" as const } : field,
      ])),
    }));
  }

  return <Facts affair={affair} onChanged={refresh} show={vi.fn()} />;
}

describe("facts confirmation", () => {
  beforeEach(() => mockedCall.mockClear());
  afterEach(cleanup);

  it("preserves other unsaved inputs after confirming one fact", async () => {
    render(<FactsHarness />);
    fireEvent.change(screen.getByLabelText(/活动名称/), { target: { value: "示例活动" } });
    fireEvent.change(screen.getByLabelText(/活动地点/), { target: { value: "尚未保存的地点" } });

    const nameRow = screen.getByLabelText(/活动名称/).closest(".fact-row");
    expect(nameRow).not.toBeNull();
    fireEvent.click(within(nameRow as HTMLElement).getByRole("button", { name: "确认" }));

    await waitFor(() => expect(mockedCall).toHaveBeenCalledWith("fact.confirm", {
      affair_id: "affair_test",
      key: "activity_name",
      value: "示例活动",
    }));
    expect(screen.getByLabelText(/活动地点/)).toHaveValue("尚未保存的地点");
  });

  it("requires all mandatory facts and confirms only non-empty pending values", async () => {
    render(<FactsHarness />);
    const confirmAll = screen.getByRole("button", { name: "确认全部已填写事实" });

    fireEvent.change(screen.getByLabelText(/活动名称/), { target: { value: "示例活动" } });
    expect(confirmAll).toBeDisabled();
    expect(screen.getByText("请先填写必填事实：活动地点")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/活动地点/), { target: { value: "示例地点" } });
    fireEvent.change(screen.getByLabelText(/注意事项/), { target: { value: "请提前到场" } });
    expect(confirmAll).toBeEnabled();
    fireEvent.click(confirmAll);

    await waitFor(() => expect(mockedCall).toHaveBeenCalledWith("fact.confirm", {
      affair_id: "affair_test",
      values: {
        activity_name: "示例活动",
        location: "示例地点",
        notes: "请提前到场",
      },
    }));
    await waitFor(() => expect(screen.getByText("当前所有已填写事实均已确认。")).toBeInTheDocument());
  });
});

describe("affair overview", () => {
  afterEach(cleanup);

  it("labels task progress and counts only confirmed required facts", () => {
    const affair = affairFixture();
    affair.facts.activity_name = { ...affair.facts.activity_name, value: "示例活动", status: "confirmed" };
    affair.facts.notes = { ...affair.facts.notes, value: "可选说明", status: "confirmed" };

    render(<Overview affair={affair} progress={40} onNavigate={vi.fn()} />);

    expect(screen.getByLabelText("任务进度 40%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1 \/ 2 个必填事实/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /2 \/ 2 个必填事实/ })).not.toBeInTheDocument();
  });
});

describe("style card editor", () => {
  beforeEach(() => mockedCall.mockReset());
  afterEach(cleanup);

  it("shows understandable fields and converts line-based phrases back to a style card", async () => {
    const styleCard: StyleCard = {
      id: "style_test",
      name: "组织通知风格",
      document_kind: "notice",
      card: {
        tone: "正式但不生硬",
        greeting: "各位同学：",
        paragraph_length: "short",
        heading_style: "序号加短标题",
        emoji_policy: "通知不用",
        common_phrases: ["请各位同学注意", "感谢大家的配合"],
        forbidden_phrases: ["速来", "家人们"],
        sign_off: "组织落款",
        punctuation: "中文全角标点",
      },
      confirmed: true,
      sample_count: 3,
      created_at: "2026-09-17T00:00:00Z",
      updated_at: "2026-09-17T00:00:00Z",
    };
    const updated = {
      ...styleCard,
      card: { ...styleCard.card, common_phrases: ["请及时查看", "感谢配合"] },
    };
    mockedCall
      .mockResolvedValueOnce([styleCard])
      .mockResolvedValueOnce(updated)
      .mockResolvedValueOnce([updated]);

    render(<StyleCards show={vi.fn()} />);

    expect(await screen.findByLabelText("语气风格")).toHaveValue("正式但不生硬");
    expect(screen.getByLabelText("段落长度")).toHaveValue("short");
    expect(screen.getByLabelText(/常用表达/)).toHaveValue("请各位同学注意\n感谢大家的配合");

    fireEvent.change(screen.getByLabelText(/常用表达/), { target: { value: "请及时查看\n感谢配合" } });
    fireEvent.click(screen.getByRole("button", { name: "确认并启用风格" }));

    await waitFor(() => expect(mockedCall).toHaveBeenCalledWith("style.confirm_card", {
      id: "style_test",
      card: {
        tone: "正式但不生硬",
        greeting: "各位同学：",
        paragraph_length: "short",
        heading_style: "序号加短标题",
        emoji_policy: "通知不用",
        common_phrases: ["请及时查看", "感谢配合"],
        forbidden_phrases: ["速来", "家人们"],
        sign_off: "组织落款",
        punctuation: "中文全角标点",
      },
      delete_cache: true,
    }));
  });
});
