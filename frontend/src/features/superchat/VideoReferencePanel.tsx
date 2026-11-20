// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useState } from "react";
import { ChevronDown, ChevronRight, Clapperboard, Loader2, Send } from "lucide-react";
import { toast } from "sonner";
import { awaitTaskCompletion } from "@/api/tasks";
import {
  submitFreezoneAnalyzeVideoReference,
  type VideoReferenceMode,
} from "@/api/ops";
import { cn } from "@/lib/utils";

/**
 * Optional video-reference analysis, shown above the Xia Director composer
 * in BOTH Freezone and Series (SuperChatPanel is shared). Everything here
 * is optional: leave the link empty and the director works exactly as
 * before. The analysis itself runs in the backend (download + video model),
 * never in the browser.
 */
const ASPECTS: Array<{ key: string; label: string }> = [
  { key: "hook", label: "Hook" },
  { key: "pacing", label: "Pacing" },
  { key: "transitions", label: "Transitions" },
  { key: "dialogue", label: "Dialogue / transcript" },
  { key: "scene_structure", label: "Scene structure" },
  { key: "camera", label: "Camera shots" },
  { key: "music", label: "Music / sound" },
  { key: "characters", label: "Characters" },
  { key: "visual_style", label: "Visual style" },
];

const MODES: Array<{ value: VideoReferenceMode; label: string; hint: string }> = [
  {
    value: "duplicate",
    label: "Duplicate",
    hint: "Recreate the video scene by scene",
  },
  {
    value: "reference",
    label: "Reference",
    hint: "Borrow its style, hook and pacing",
  },
  {
    value: "idea",
    label: "Idea",
    hint: "Take the premise, make fresh angles",
  },
];

export interface VideoReferencePanelProps {
  projectId: string | null;
  /** Fill the director composer with the analysis (user presses Send). */
  onSendToDirector: (text: string) => void;
}

export function VideoReferencePanel({
  projectId,
  onSendToDirector,
}: VideoReferencePanelProps) {
  const [open, setOpen] = useState(false);
  const [videoUrl, setVideoUrl] = useState("");
  const [mode, setMode] = useState<VideoReferenceMode>("reference");
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
    const url = videoUrl.trim();
    if (!url) {
      toast.error("Paste a video link first (YouTube, TikTok, Instagram).");
      return;
    }
    if (!projectId) {
      toast.error("Open a project first.");
      return;
    }
    setAnalyzing(true);
    setResult(null);
    try {
      const submit = await submitFreezoneAnalyzeVideoReference(projectId, {
        videoUrl: url,
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
        source: typeof raw.source === "string" ? raw.source : "direct",
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
      `Video reference analysis (${mode}` +
      (result.title ? ` — ${result.title}` : "") +
      `, via ${result.model || "video model"}):\n\n`;
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
          <Clapperboard className="size-3.5 shrink-0 text-primary" />
          <span>Video reference (optional)</span>
          <span className="font-normal text-muted-foreground">
            Analyse a YouTube / TikTok / Instagram link with Xia Director
          </span>
        </button>
        {open ? (
          <div className="space-y-3 border-t border-white/10 px-3 py-3">
            <label className="block space-y-1 text-xs">
              <span className="font-medium text-foreground/90">
                Social video link
              </span>
              <input
                type="url"
                value={videoUrl}
                onChange={(event) => setVideoUrl(event.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                className="w-full rounded-md border border-white/10 bg-black/20 px-2.5 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary/60"
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
                Anything extra to analyse
              </span>
              <textarea
                value={extraNotes}
                onChange={(event) => setExtraNotes(event.target.value)}
                placeholder="e.g. focus on the lighting in the night scenes, and how the villain is introduced"
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
                  <Clapperboard className="size-3.5" />
                )}
                {analyzing ? "Analysing video…" : "Analyse video"}
              </button>
              <span className="text-[11px] text-muted-foreground">
                Videos over 5 minutes are refused. One analysis at a time.
              </span>
            </div>
            {result ? (
              <div className="space-y-2 rounded-md border border-white/10 bg-black/20 p-2.5 text-xs">
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                  {result.title ? <span className="font-medium text-foreground/90">{result.title}</span> : null}
                  <span>Model: {result.model || "—"}</span>
                  <span>
                    Source:{" "}
                    {result.source === "frames_fallback"
                      ? "keyframes (fallback)"
                      : result.source === "direct_youtube"
                        ? "YouTube link"
                        : "downloaded file"}
                  </span>
                </div>
                {result.fallback ? (
                  <p className="text-[11px] text-amber-400">{result.fallback}</p>
                ) : null}
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
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
