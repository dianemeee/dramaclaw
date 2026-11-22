// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useState } from "react";
import { ChevronDown, ChevronRight, Loader2, Newspaper, Send } from "lucide-react";
import { toast } from "sonner";
import { awaitTaskCompletion } from "@/api/tasks";
import {
  submitFreezoneAnalyzeArticleReference,
  type ArticleReferenceMode,
} from "@/api/ops";
import { cn } from "@/lib/utils";

/**
 * Optional article-reference analysis, shown above the Xia Director composer
 * in BOTH Freezone and Series (SuperChatPanel is shared). Everything here
 * is optional: leave it empty and the director works exactly as before.
 * The analysis itself runs in the backend (fetch + text model), never in
 * the browser. No video model or extra API key is needed — articles are
 * plain text, so the already-configured NewAPI text model does the work.
 *
 * The expanded content scrolls inside itself (max-h-[45vh], result
 * max-h-[24vh]) — the video panel shipped without that and its lower part
 * fell below the viewport; do not remove these bounds.
 */
const ASPECTS: Array<{ key: string; label: string }> = [
  { key: "hook", label: "Hook" },
  { key: "pacing", label: "Pacing" },
  { key: "transitions", label: "Transitions" },
  { key: "dialogue", label: "Dialogue" },
  { key: "scene_structure", label: "Scene structure" },
  { key: "camera", label: "Visual imagery" },
  { key: "music", label: "Mood / atmosphere" },
  { key: "characters", label: "Characters" },
  { key: "visual_style", label: "Writing style" },
];

const MODES: Array<{ value: ArticleReferenceMode; label: string; hint: string }> = [
  {
    value: "duplicate",
    label: "Duplicate",
    hint: "Retell the article's story beat by beat",
  },
  {
    value: "reference",
    label: "Reference",
    hint: "Borrow its craft for a new, original story",
  },
  {
    value: "idea",
    label: "Idea",
    hint: "Take the premise, make fresh angles",
  },
];

export interface ArticleReferencePanelProps {
  projectId: string | null;
  /** Fill the director composer with the analysis (user presses Send). */
  onSendToDirector: (text: string) => void;
}

export function ArticleReferencePanel({
  projectId,
  onSendToDirector,
}: ArticleReferencePanelProps) {
  const [open, setOpen] = useState(false);
  const [articleUrl, setArticleUrl] = useState("");
  const [articleText, setArticleText] = useState("");
  const [mode, setMode] = useState<ArticleReferenceMode>("reference");
  const [checked, setChecked] = useState<ReadonlySet<string>>(new Set());
  const [extraNotes, setExtraNotes] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<{
    analysis: string;
    source: string;
    model: string;
    fallback: string | null;
    title: string;
  } | null>(null);

  const toggleAspect = (key: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleAnalyze = async () => {
    const url = articleUrl.trim();
    const text = articleText.trim();
    if (!url && !text) {
      toast.error("Paste an article link or the article text first.");
      return;
    }
    if (!projectId) {
      toast.error("Open a project first.");
      return;
    }
    setAnalyzing(true);
    setResult(null);
    try {
      const submit = await submitFreezoneAnalyzeArticleReference(projectId, {
        articleUrl: url,
        articleText: text,
        mode,
        checklist: [...checked],
        extraNotes: extraNotes.trim(),
      });
      const taskKey =
        typeof submit.task_key === "string" ? submit.task_key : null;
      if (!taskKey) {
        throw new Error("The server did not return a task to follow.");
      }
      const completed = await awaitTaskCompletion(taskKey, projectId);
      const raw = (completed.result ?? {}) as Record<string, unknown>;
      const analysis = typeof raw.analysis === "string" ? raw.analysis : "";
      if (!analysis) {
        throw new Error(
          typeof completed.error === "string" && completed.error
            ? completed.error
            : "The analysis came back empty.",
        );
      }
      const metadata =
        raw.metadata && typeof raw.metadata === "object"
          ? (raw.metadata as Record<string, unknown>)
          : {};
      setResult({
        analysis,
        source: typeof raw.source === "string" ? raw.source : "article",
        model: typeof raw.model === "string" ? raw.model : "",
        fallback:
          typeof raw.fallback === "string" ? raw.fallback : null,
        title: typeof metadata.title === "string" ? metadata.title : "",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      toast.error(message);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleSendToDirector = () => {
    if (!result) return;
    const header =
      `Article reference analysis (${mode}` +
      (result.title ? ` — ${result.title}` : "") +
      `, via ${result.model || "text model"}):\n\n`;
    onSendToDirector(`${header}${result.analysis}`);
  };

  return (
    <div className="mx-auto w-full max-w-[760px]">
      <div className="rounded-xl border border-white/10 bg-white/[0.02]">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-foreground/90"
          aria-expanded={open}
        >
          {open ? (
            <ChevronDown className="size-3.5 shrink-0" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0" />
          )}
          <Newspaper className="size-3.5 shrink-0 text-primary" />
          <span>Article reference (optional)</span>
          <span className="font-normal text-muted-foreground">
            Analyse an article link or pasted text with Xia Director
          </span>
        </button>
        {open ? (
          <div className="ui-scrollbar max-h-[45vh] space-y-3 overflow-y-auto overscroll-contain border-t border-white/10 px-3 py-3">
            <label className="block space-y-1 text-xs">
              <span className="font-medium text-foreground/90">
                Article link
              </span>
              <input
                type="url"
                value={articleUrl}
                onChange={(event) => setArticleUrl(event.target.value)}
                placeholder="https://example.com/a-short-story"
                className="w-full rounded-md border border-white/10 bg-black/20 px-2.5 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary/60"
              />
            </label>
            <label className="block space-y-1 text-xs">
              <span className="font-medium text-foreground/90">
                Or paste the article text
              </span>
              <textarea
                value={articleText}
                onChange={(event) => setArticleText(event.target.value)}
                placeholder="Paste the full article here — use this if the link is paywalled or cannot be read"
                rows={6}
                className="w-full resize-y rounded-md border border-white/10 bg-black/20 px-2.5 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary/60"
              />
            </label>
            <div className="space-y-1 text-xs">
              <span className="font-medium text-foreground/90">Mode</span>
              <div className="flex flex-wrap gap-1.5">
                {MODES.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => setMode(item.value)}
                    title={item.hint}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-xs transition",
                      mode === item.value
                        ? "border-primary bg-primary/15 text-foreground"
                        : "border-white/10 bg-black/20 text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground">
                {MODES.find((item) => item.value === mode)?.hint}
              </p>
            </div>
            <fieldset className="space-y-1.5 text-xs">
              <legend className="font-medium text-foreground/90">
                What to analyse <span className="font-normal text-muted-foreground">(optional — none ticked = everything)</span>
              </legend>
              <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                {ASPECTS.map((aspect) => (
                  <label
                    key={aspect.key}
                    className="flex cursor-pointer items-center gap-1.5 text-foreground/85"
                  >
                    <input
                      type="checkbox"
                      checked={checked.has(aspect.key)}
                      onChange={() => toggleAspect(aspect.key)}
                      className="size-3.5 accent-primary"
                    />
                    {aspect.label}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="block space-y-1 text-xs">
              <span className="font-medium text-foreground/90">
                Your story premise (optional)
              </span>
              <textarea
                value={extraNotes}
                onChange={(event) => setExtraNotes(event.target.value)}
                placeholder="e.g. My story is about Mei, a waitress who spills wine on a CEO — apply this article to MY story, don't retell the article"
                rows={2}
                className="w-full resize-y rounded-md border border-white/10 bg-black/20 px-2.5 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary/60"
              />
            </label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void handleAnalyze()}
                disabled={analyzing}
                className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition disabled:opacity-50"
              >
                {analyzing ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Newspaper className="size-3.5" />
                )}
                {analyzing ? "Analysing article…" : "Analyse article"}
              </button>
              <span className="text-[11px] text-muted-foreground">
                Articles are capped at 20,000 characters. One analysis at a time.
              </span>
            </div>
            {result ? (
              <div className="space-y-2 rounded-md border border-white/10 bg-black/20 p-2.5 text-xs">
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                  {result.title ? <span className="font-medium text-foreground/90">{result.title}</span> : null}
                  <span>Model: {result.model || "—"}</span>
                  <span>
                    Source:{" "}
                    {result.source === "pasted_text"
                      ? "pasted text"
                      : result.source === "article_url"
                        ? "article link"
                        : result.source}
                  </span>
                </div>
                {result.fallback ? (
                  <p className="text-[11px] text-amber-400">{result.fallback}</p>
                ) : null}
                <p className="ui-scrollbar max-h-[24vh] overflow-y-auto whitespace-pre-wrap pr-1 text-sm leading-relaxed text-foreground/90">
                  {result.analysis}
                </p>
                <button
                  type="button"
                  onClick={handleSendToDirector}
                  className="inline-flex items-center gap-1.5 rounded-md border border-primary/50 px-2.5 py-1.5 text-xs font-medium text-primary transition hover:bg-primary/10"
                >
                  <Send className="size-3.5" />
                  Send to Xia Director
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
