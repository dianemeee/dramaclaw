// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { describe, expect, it } from "vitest";
import {
  buildArticleDirectorMessage,
  buildCombinedDirectorMessage,
  buildVideoDirectorMessage,
  combinedSendButtonLabel,
  normalizeDirectorLanguage,
  type ReferenceSendPart,
} from "@/features/superchat/referenceSend";

function articlePart(overrides: Partial<ReferenceSendPart> = {}): ReferenceSendPart {
  return {
    kind: "article",
    title: "Lenteng Agung",
    mode: "reference",
    model: "text model",
    analysis: "ARTICLE ANALYSIS: villagers face eviction over a land deed.",
    checkedLabels: ["Hook", "Pacing"],
    allLabels: ["Hook", "Pacing", "Transitions"],
    extraNotes: "My story is about the eviction dispute.",
    ...overrides,
  };
}

function videoPart(overrides: Partial<ReferenceSendPart> = {}): ReferenceSendPart {
  return {
    kind: "video",
    title: "TikTok clip",
    mode: "reference",
    model: "video model",
    analysis: "VIDEO ANALYSIS: fast cuts, handheld POV, a dramatic reveal.",
    checkedLabels: ["Hook", "Camera shots"],
    allLabels: ["Hook", "Pacing", "Camera shots"],
    extraNotes: "",
    ...overrides,
  };
}

describe("referenceSend", () => {
  it("combined message puts the article (story) first and the video (style) second", () => {
    const message = buildCombinedDirectorMessage(
      articlePart(),
      videoPart(),
      "en",
    );
    expect(message.indexOf("ARTICLE ANALYSIS")).toBeLessThan(
      message.indexOf("VIDEO ANALYSIS"),
    );
    expect(message).toContain("STORY SOURCE");
    expect(message).toContain("STYLE REFERENCE ONLY");
    // The closing instruction ties them together.
    expect(message).toContain("STORY comes from the article analysis");
    expect(message).toContain("STYLE");
    expect(message).toContain("never copy the video's plot");
  });

  it("video part borrows only the checked aspects, never the video story", () => {
    const message = buildVideoDirectorMessage(videoPart(), "en");
    expect(message).toContain("Borrow ONLY these checked aspects from this video: Hook, Camera shots.");
    expect(message).not.toContain("Pacing");
    expect(message).toContain("Do NOT use this video's story, plot or characters.");
    expect(message).toContain("Do not follow this video's storyline");
  });

  it("video part with nothing ticked borrows every aspect", () => {
    const message = buildVideoDirectorMessage(
      videoPart({ checkedLabels: [] }),
      "en",
    );
    expect(message).toContain("Hook, Pacing, Camera shots");
    expect(message).toContain("No aspect was ticked");
  });

  it("article part labels the analysis as the story source and keeps the user's notes", () => {
    const message = buildArticleDirectorMessage(articlePart(), "en");
    expect(message).toContain("STORY SOURCE");
    expect(message).toContain("Develop the story from this article analysis.");
    expect(message).toContain("My notes: My story is about the eviction dispute.");
  });

  it("extra notes travel under the matching part in the combined message", () => {
    const message = buildCombinedDirectorMessage(
      articlePart(),
      videoPart({ extraNotes: "Only the night scenes." }),
      "en",
    );
    expect(message).toContain("My notes: My story is about the eviction dispute.");
    expect(message).toContain("My notes: Only the night scenes.");
  });

  it("renders the guard in Indonesian and Chinese", () => {
    const id = buildCombinedDirectorMessage(articlePart(), videoPart(), "id");
    expect(id).toContain("SUMBER CERITA");
    expect(id).toContain("HANYA REFERENSI GAYA");
    expect(id).toContain("jangan pernah menyalin alur video");
    expect(combinedSendButtonLabel("id")).toContain("Kirim keduanya ke Xia Director");

    const zh = buildCombinedDirectorMessage(articlePart(), videoPart(), "zh");
    expect(zh).toContain("故事来源");
    expect(zh).toContain("仅作风格参考");
    expect(zh).toContain("绝不要照搬视频的情节");
  });

  it("normalizes unknown UI languages to English", () => {
    expect(normalizeDirectorLanguage("en-US")).toBe("en");
    expect(normalizeDirectorLanguage("id")).toBe("id");
    expect(normalizeDirectorLanguage("zh-CN")).toBe("zh");
    expect(normalizeDirectorLanguage("vi")).toBe("en");
    expect(normalizeDirectorLanguage(undefined)).toBe("en");
  });
});
