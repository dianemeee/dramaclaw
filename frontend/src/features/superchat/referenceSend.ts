// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import i18next from "i18next";

/**
 * One-click "Send to Xia Director" for the Article + Video reference
 * panels (both Freezone and Series — SuperChatPanel is shared).
 *
 * The split the user should never have to explain by hand:
 * - the user's own PREMISE / NASKAH (written in the article panel's
 *   "Your story premise" box before Analyse) is the story to develop —
 *   it goes first, verbatim, as its own section;
 * - the ARTICLE analysis is the STORY source — the story, characters and
 *   plot are developed from it;
 * - the VIDEO analysis is STYLE / RESULT reference ONLY — borrow only the
 *   checklist aspects the user actually ticked (hook, pacing, transitions,
 *   camera/POV, visual style, ...), never the video's story or plot.
 *
 * The premise is sent to the backend with the Analyse request, so the
 * returned analysis may already quote it verbatim — in that case no
 * separate premise section is added, so the premise appears exactly once.
 *
 * The composed text is written in the UI language (en / id / zh, default
 * en) so the director reads the guard in the same language it answers in.
 * The backend director language packs (src/novelvideo/prompts/lang) are
 * NOT read by the frontend, so the templates live here, next to the
 * panels, following the panels' own hardcoded-English pattern.
 */

export type ReferenceKind = "article" | "video";

export interface ReferenceSendPart {
  kind: ReferenceKind;
  /** Human title of the analysed article / video (may be empty). */
  title: string;
  /** Mode picked in the panel: duplicate / reference / idea. */
  mode: string;
  /** Model that produced the analysis (may be empty). */
  model: string;
  /** The analysis text returned by the backend. */
  analysis: string;
  /** Labels of the checklist aspects the user ticked (may be empty). */
  checkedLabels: string[];
  /** Labels of every checklist aspect (used when nothing was ticked). */
  allLabels: string[];
  /** Free-text notes the user wrote in the panel (may be empty). */
  extraNotes: string;
}

export type DirectorLanguage = "en" | "id" | "zh";

/** UI language -> director message language. Unknown locales fall back to English. */
export function normalizeDirectorLanguage(
  value: string | undefined | null,
): DirectorLanguage {
  const lang = (value ?? "").toLowerCase();
  if (lang.startsWith("id")) return "id";
  if (lang.startsWith("zh")) return "zh";
  return "en";
}

/** Resolve the current UI language the same way use-superchat does. */
export function currentDirectorLanguage(): DirectorLanguage {
  return normalizeDirectorLanguage(
    i18next.resolvedLanguage ?? i18next.language,
  );
}

interface ReferenceTemplates {
  premiseTitle: string;
  premiseGuard: string;
  articleTitle: string;
  articleStoryGuard: string;
  videoTitle: string;
  videoStyleGuard: string;
  borrowedAspects: (aspects: string) => string;
  allAspectsNote: string;
  myNotes: (notes: string) => string;
  combinedClosing: string;
  combinedButton: string;
  combinedButtonHint: string;
}

const TEMPLATES: Record<DirectorLanguage, ReferenceTemplates> = {
  en: {
    premiseTitle: "MY SCRIPT / PREMISE:",
    premiseGuard:
      "Develop THIS story. The premise below is my own script — use it as the story to develop, with the article as its source material. The video is style reference only.",
    articleTitle: "STORY SOURCE",
    articleStoryGuard:
      "Develop the story from this article analysis. The story, characters and plot come from this article.",
    videoTitle: "STYLE REFERENCE ONLY",
    videoStyleGuard:
      "Do NOT use this video's story, plot or characters. Do not follow this video's storyline — borrow only its result / style: its POV, images, pacing and the aspects listed below.",
    borrowedAspects: (aspects) =>
      `Borrow ONLY these checked aspects from this video: ${aspects}.`,
    allAspectsNote:
      "No aspect was ticked, so every aspect of the video's result may be borrowed as style.",
    myNotes: (notes) => `My notes: ${notes}`,
    combinedClosing:
      "Make one complete video: the STORY comes from the article analysis above; the STYLE (hook, pacing, transitions, camera / POV, visuals) comes from the video analysis above. Develop the story from the article — never copy the video's plot.",
    combinedButton: "Send both to Xia Director",
    combinedButtonHint: " — article story + video style",
  },
  id: {
    premiseTitle: "NASKAH / PREMIS SAYA:",
    premiseGuard:
      "Kembangkan cerita INI. Premis di bawah ini adalah naskah saya sendiri — pakai sebagai cerita yang dikembangkan, dengan artikel sebagai bahan sumbernya. Video hanya referensi gaya.",
    articleTitle: "SUMBER CERITA",
    articleStoryGuard:
      "Kembangkan ceritanya dari analisis artikel ini. Cerita, karakter, dan alurnya berasal dari artikel ini.",
    videoTitle: "HANYA REFERENSI GAYA",
    videoStyleGuard:
      "JANGAN pakai cerita, alur, atau karakter video ini. Jangan ikuti alur video ini — ambil hanya hasil / gayanya: POV, gambar, pacing, dan aspek yang tercantum di bawah ini.",
    borrowedAspects: (aspects) =>
      `Ambil HANYA aspek yang saya centang ini dari video ini: ${aspects}.`,
    allAspectsNote:
      "Tidak ada aspek yang dicentang, jadi semua aspek hasil video ini boleh diambil sebagai gaya.",
    myNotes: (notes) => `Catatan saya: ${notes}`,
    combinedClosing:
      "Buatkan satu video lengkap: CERITANYA dari analisis artikel di atas; GAYANYA (hook, pacing, transisi, kamera / POV, visual) dari analisis video di atas. Kembangkan cerita dari artikel — jangan pernah menyalin alur video.",
    combinedButton: "Kirim keduanya ke Xia Director",
    combinedButtonHint: " — cerita artikel + gaya video",
  },
  zh: {
    premiseTitle: "我的剧本 / 前提：",
    premiseGuard:
      "请发展这个故事。下面的前提是我自己的剧本——以它为要发展的故事，文章作为素材来源。视频仅作风格参考。",
    articleTitle: "故事来源",
    articleStoryGuard:
      "请根据这篇分析发展故事。故事、角色和情节都来自这篇文章。",
    videoTitle: "仅作风格参考",
    videoStyleGuard:
      "请勿使用该视频的故事、情节或角色。不要沿用该视频的剧情——只借鉴它的成片效果 / 风格：POV、画面、节奏以及下面列出的方面。",
    borrowedAspects: (aspects) => `只借鉴该视频中我勾选的这些方面：${aspects}。`,
    allAspectsNote: "未勾选任何方面，因此该视频成片的全部方面均可作为风格借鉴。",
    myNotes: (notes) => `我的备注：${notes}`,
    combinedClosing:
      "请制作一条完整视频：故事来自上文的文章分析；风格（hook、pacing、transitions、镜头 / POV、视觉）来自上文的视频分析。请根据文章发展故事——绝不要照搬视频的情节。",
    combinedButton: "同时发送给虾导",
    combinedButtonHint: "——文章故事 + 视频风格",
  },
};

function templates(lang: DirectorLanguage): ReferenceTemplates {
  return TEMPLATES[lang];
}

/** Aspects to borrow: the ticked ones, or all of them when none was ticked. */
function borrowedAspects(part: ReferenceSendPart): string {
  const labels = part.checkedLabels.length > 0 ? part.checkedLabels : part.allLabels;
  return labels.join(", ");
}

function partHeader(part: ReferenceSendPart, title: string): string {
  const model = part.model ? `, via ${part.model}` : "";
  const name = part.title ? ` — ${part.title}` : "";
  return `${title} (${part.mode}${name}${model}):`;
}

function renderPart(
  part: ReferenceSendPart,
  lang: DirectorLanguage,
): string {
  const t = templates(lang);
  const lines: string[] = [];
  if (part.kind === "article") {
    lines.push(partHeader(part, t.articleTitle));
    lines.push("");
    lines.push(part.analysis);
    lines.push("");
    lines.push(t.articleStoryGuard);
  } else {
    lines.push(partHeader(part, t.videoTitle));
    lines.push("");
    lines.push(part.analysis);
    lines.push("");
    lines.push(t.borrowedAspects(borrowedAspects(part)));
    if (part.checkedLabels.length === 0) {
      lines.push(t.allAspectsNote);
    }
    lines.push(t.videoStyleGuard);
  }
  if (part.extraNotes.trim()) {
    lines.push("");
    lines.push(t.myNotes(part.extraNotes.trim()));
  }
  return lines.join("\n");
}

/** Hardened individual send for the article panel: story source, always labelled. */
export function buildArticleDirectorMessage(
  part: ReferenceSendPart,
  lang: DirectorLanguage = currentDirectorLanguage(),
): string {
  return renderPart(part, lang);
}

/**
 * Hardened individual send for the video panel: style only, never the
 * story — borrow only the checklist aspects the user actually ticked.
 */
export function buildVideoDirectorMessage(
  part: ReferenceSendPart,
  lang: DirectorLanguage = currentDirectorLanguage(),
): string {
  return renderPart(part, lang);
}

/** The user's premise, as its own first section, verbatim. */
function renderPremiseSection(premise: string, lang: DirectorLanguage): string {
  const t = templates(lang);
  return [t.premiseTitle, "", premise, "", t.premiseGuard].join("\n");
}

/**
 * A verbatim quote only counts as "already embedded" when it is long
 * enough to be a real quote — a one-word premise ("Mei") merely appearing
 * as a substring of the analysis is not the premise being embedded.
 */
const MIN_VERBATIM_QUOTE_LENGTH = 20;

/**
 * One combined message: the user's own premise / naskah first (verbatim,
 * as its own section), then the article analysis as the STORY source,
 * then the video analysis as STYLE reference only, closed by one fixed
 * instruction tying them together. The user never has to explain the
 * story/style split herself, and never has to paste her premise again.
 *
 * Dedupe: the premise is sent to the backend with the Analyse request,
 * so the returned article analysis may already quote it verbatim — in
 * that case no separate premise section is added. Either way the premise
 * appears exactly once: the trailing "My notes:" line under the article
 * part is always suppressed here (the individual article send keeps it).
 */
export function buildCombinedDirectorMessage(
  article: ReferenceSendPart,
  video: ReferenceSendPart,
  lang: DirectorLanguage = currentDirectorLanguage(),
): string {
  const t = templates(lang);
  const premise = article.extraNotes.trim();
  const premiseAlreadyInAnalysis =
    premise.length >= MIN_VERBATIM_QUOTE_LENGTH &&
    article.analysis.includes(premise);
  const sections: string[] = [];
  if (premise && !premiseAlreadyInAnalysis) {
    sections.push(renderPremiseSection(premise, lang));
    sections.push("", "");
  }
  sections.push(renderPart({ ...article, extraNotes: "" }, lang));
  sections.push("", "");
  sections.push(renderPart(video, lang));
  sections.push("", "");
  sections.push(t.combinedClosing);
  return sections.join("\n");
}

/** Label for the combined button, in the UI language. */
export function combinedSendButtonLabel(
  lang: DirectorLanguage = currentDirectorLanguage(),
): string {
  const t = templates(lang);
  return `${t.combinedButton}${t.combinedButtonHint}`;
}
