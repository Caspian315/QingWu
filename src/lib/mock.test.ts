import { describe, expect, it } from "vitest";
import type { Affair, Draft } from "../types";
import { mockCall } from "./mock";

describe("browser demo workflow", () => {
  it("creates an affair and invalidates a draft when an included fact changes", async () => {
    const affair = await mockCall<Affair>("affair.create", {
      template_id: "activity-organization",
      title: "浏览器演示测试",
    });
    await mockCall("fact.confirm", {
      affair_id: affair.id,
      values: {
        activity_name: "主题团日",
        activity_date: "2026-10-18",
        start_time: "18:00",
        location: "活动中心 203",
        audience: "全体同学",
        contact_person: "张同学",
        organizer: "计算机 2401 团支部",
      },
    });
    const draft = await mockCall<Draft>("draft.generate", {
      affair_id: affair.id,
      document_id: "notice_full",
    });
    expect(draft.rendered_body).toContain("18:00");
    await mockCall("fact.update", { affair_id: affair.id, key: "start_time", value: "19:00" });
    const reopened = await mockCall<Affair>("affair.open", { id: affair.id });
    expect(reopened.drafts[0].status).toBe("stale");
  });
});
