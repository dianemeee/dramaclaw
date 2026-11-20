"""Reference-video analysis for Xia Director (Freezone + Series).

A user pastes a social video link (YouTube, TikTok, Instagram, ...) and
optionally picks a mode (duplicate / reference / idea), a checklist of
aspects to analyse, and free-text extra notes. Xia Director then analyses
the video and turns the result into script / storyboard material.

Priority order (heavier work last — the VPS is already memory-tight):
1. DIRECT VIDEO INPUT (primary): the video itself goes to a video-capable
   model through the OpenRouter Responses API (``input_video``).
   - YouTube: the link is passed straight through — Gemini on OpenRouter
     accepts YouTube links as video URLs, no download needed.
   - TikTok / Instagram / other: download once with yt-dlp, then send the
     video FILE itself as a base64 data URL. Never frame-by-frame here.
2. FRAMES ONLY AS FALLBACK: if direct video input is unavailable for a
   given model/URL, extract at most 8 keyframes (same compression as
   StyleAnalyzer: max 1024px edge, JPEG q60) and analyse those through the
   existing NewAPI vision plumbing. The result says so explicitly.

Server-side resolution only — Series chat scope does NOT forward frontend
``context`` to the backend (see ``api/routes/chat.py``: the ``surface_context``
is ``msg.context`` for Freezone only, ``None`` for Series). So the analysis
model comes from the persisted setting / env var and the reply language
from the ``DRAMACLAW_UI_LANGUAGE`` env var, never from a ``ui_language``
field in the request. That is what makes this work in both Freezone and
Series.

Limits: videos longer than 5 minutes are refused (video tokens scale with
duration); one analysis runs at a time (module-level lock); downloads are
capped at 200 MB and live in a temp dir under the project that is removed
afterwards. The OpenRouter key is read from the ``OPENROUTER_API_KEY``
environment variable only — never from chat, never written to a file.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("novelvideo.freezone.video_reference")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_VIDEO_ANALYSIS_MODEL = "google/gemini-2.5-flash"
VIDEO_ANALYSIS_MODEL_ENV = "VIDEO_ANALYSIS_MODEL"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_RESPONSES_URL = "https://openrouter.ai/api/v1/responses"

#: Refuse videos longer than this (seconds). Video tokens scale with
#: duration; short reference clips (30-60s) stay cheap.
MAX_VIDEO_REFERENCE_SECONDS = 300
#: Refuse downloads larger than this.
MAX_VIDEO_REFERENCE_BYTES = 200 * 1024 * 1024
#: Frames fallback cap — never more than this many keyframes.
MAX_FALLBACK_FRAMES = 8

VIDEO_REFERENCE_MODES = ("duplicate", "reference", "idea")

VIDEO_REFERENCE_ASPECTS: tuple[tuple[str, str], ...] = (
    ("hook", "Hook — the first 3 seconds: what grabs attention"),
    ("pacing", "Pacing — rhythm, cuts per minute, fast vs slow sections"),
    ("transitions", "Transitions — how scenes/shots connect"),
    ("dialogue", "Dialogue / transcript — what is said, tone of voice"),
    ("scene_structure", "Scene structure — beats, acts, how the story is ordered"),
    ("camera", "Camera — shot sizes, angles, movement, framing"),
    ("music", "Music / sound — soundtrack, sound effects, silence"),
    ("characters", "Characters — who appears, look, expressions, roles"),
    ("visual_style", "Visual style — colour grade, lighting, overall look"),
)
VIDEO_REFERENCE_ASPECT_KEYS = frozenset(key for key, _ in VIDEO_REFERENCE_ASPECTS)

_YOUTUBE_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
)


class VideoReferenceError(ValueError):
    """User-facing failure of a video-reference analysis step."""


# One analysis at a time: the VPS is already memory-tight, and a video
# download + model call must never run in parallel with image/video
# generation.
_ANALYSIS_LOCK = asyncio.Lock()


# ---------------------------------------------------------------------------
# Pure helpers (covered by tests/test_video_reference.py)
# ---------------------------------------------------------------------------

def classify_video_url(url: str) -> str:
    """Return ``"youtube"`` for YouTube links, ``"other"`` for the rest."""
    host = (urlparse(str(url or "").strip()).hostname or "").lower()
    return "youtube" if host in _YOUTUBE_HOSTS or host.endswith(".youtube.com") else "other"


def is_youtube_url(url: str) -> bool:
    return classify_video_url(url) == "youtube"


def normalize_video_reference_mode(mode: str | None) -> str:
    """Unknown/empty mode falls back to ``"reference"``."""
    cleaned = str(mode or "").strip().lower()
    return cleaned if cleaned in VIDEO_REFERENCE_MODES else "reference"


def normalize_video_reference_checklist(items: Any) -> tuple[str, ...]:
    """Keep only known aspect keys, in canonical order, de-duplicated."""
    if not items:
        return ()
    wanted = []
    for item in items:
        key = str(item or "").strip().lower()
        if key in VIDEO_REFERENCE_ASPECT_KEYS and key not in wanted:
            wanted.append(key)
    ordered = [key for key, _ in VIDEO_REFERENCE_ASPECTS if key in wanted]
    return tuple(ordered)


def resolve_director_language() -> str:
    """Reply language for the analysis, from the server-side env var.

    Freezone forwards ``ui_language`` in chat context; Series does not, so
    both scopes resolve here instead. ``id`` is opt-in (see the language
    packs); anything else falls back to ``en``.
    """
    lang = os.environ.get("DRAMACLAW_UI_LANGUAGE", "").strip().lower()
    if lang.startswith("id"):
        return "id"
    return "en"


def resolve_video_analysis_model(explicit: str | None = None) -> str:
    """Priority: explicit argument > persisted setting > env var > default.

    The Agent model (qwen) is never touched — this is a separate model
    used only for video analysis.
    """
    cleaned = str(explicit or "").strip()
    if cleaned:
        return cleaned
    try:
        from novelvideo.model_gateway_settings import (
            get_video_analysis_model_config,
        )

        saved = get_video_analysis_model_config()
        saved_model = str(saved.get("model") or "").strip()
        if saved_model:
            return saved_model
    except Exception:  # pragma: no cover - settings read must never break analysis
        logger.exception("video reference: failed to read saved analysis model")
    env_model = os.environ.get(VIDEO_ANALYSIS_MODEL_ENV, "").strip()
    if env_model:
        return env_model
    return DEFAULT_VIDEO_ANALYSIS_MODEL


def resolve_openrouter_api_key() -> str:
    """OpenRouter key, from the environment only.

    The key lives in the api service environment (set in 1Panel Compose),
    never in chat and never in a file. If it is missing the caller gets a
    clear, actionable error instead of a cryptic 401.
    """
    key = os.environ.get(OPENROUTER_API_KEY_ENV, "").strip()
    if not key:
        raise VideoReferenceError(
            "OPENROUTER_API_KEY is not set on the DramaClaw api service. "
            "Add it to the api service environment in 1Panel (Compose "
            "environment variables) and recreate the api container, then "
            "retry the analysis."
        )
    return key


_MODE_INSTRUCTIONS = {
    "duplicate": (
        "DUPLICATE mode: recreate this video as closely as possible. "
        "Give a scene-by-scene breakdown (in order, with timestamps) that "
        "another creator could follow shot for shot to reproduce the same "
        "video: same beats, same order, same pacing, same camera work."
    ),
    "reference": (
        "REFERENCE mode: use this video as inspiration, not a template to "
        "copy. Extract the reusable craft: what makes it work (hook, "
        "pacing, transitions, shot choices), and list concrete techniques "
        "the director can borrow for a NEW, original video."
    ),
    "idea": (
        "IDEA mode: extract only the core idea / premise of this video, "
        "then generate 3 fresh angles on the same idea that have NOT been "
        "done in this video. Do not copy its scenes; the output is new "
        "ideas, each with a one-line premise and a suggested hook."
    ),
}


def build_video_reference_prompt(
    *,
    mode: str,
    checklist: tuple[str, ...] = (),
    extra_notes: str = "",
    metadata: dict[str, Any] | None = None,
    language: str = "en",
) -> str:
    """Build the analysis prompt sent to the video model.

    ``checklist`` is empty by default, which means "analyse everything"
    (all aspects below). ``extra_notes`` is the user's free textbox.
    """
    mode = normalize_video_reference_mode(mode)
    aspects = checklist or tuple(key for key, _ in VIDEO_REFERENCE_ASPECTS)
    aspect_lines = "\n".join(
        f"- {label}"
        for key, label in VIDEO_REFERENCE_ASPECTS
        if key in aspects
    )
    meta = metadata or {}
    meta_lines = []
    if meta.get("title"):
        meta_lines.append(f"Title: {meta['title']}")
    if meta.get("uploader"):
        meta_lines.append(f"Uploader: {meta['uploader']}")
    if meta.get("duration"):
        meta_lines.append(f"Duration: {float(meta['duration']):.0f} seconds")
    meta_block = ("\n".join(meta_lines) + "\n") if meta_lines else ""
    extra = str(extra_notes or "").strip()
    extra_block = (
        f"\nThe user also specifically wants analysed:\n{extra}\n"
        if extra
        else ""
    )
    lang_block = (
        "\nReply in Bahasa Indonesia for prose, script and dialogue. "
        "Keep visual generation prompt fields (image / video prompts) in English.\n"
        if language == "id"
        else "\nReply in English.\n"
    )
    return f"""You are a professional short-drama director analysing a reference video.
{meta_block}
{_MODE_INSTRUCTIONS[mode]}

Analyse these aspects (in this order, one short section each):
{aspect_lines}
{extra_block}
Rules:
- Only describe what you can actually see/hear in the video. If you cannot
  tell (e.g. no audible dialogue), say so instead of inventing it.
- Keep each section to 2-4 sentences, except the scene breakdown in
  duplicate mode, which is a timestamped list.
- End with a one-paragraph "What to steal" summary: the 3 most useful
  techniques for the director.
{lang_block}"""


# ---------------------------------------------------------------------------
# yt-dlp download (TikTok / Instagram / other — never for YouTube direct)
# ---------------------------------------------------------------------------

def _run_yt_dlp(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("yt-dlp")
    if not exe:
        raise VideoReferenceError(
            "yt-dlp is not installed in the DramaClaw api image. "
            "Rebuild the api image from the fork (it installs yt-dlp) and retry."
        )
    try:
        return subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoReferenceError(f"yt-dlp timed out: {exc}") from exc


def fetch_video_metadata(url: str) -> dict[str, Any]:
    """Return title/uploader/duration for a URL, enforcing the length cap."""
    proc = _run_yt_dlp(
        ["--no-playlist", "--dump-json", "--no-warnings", url],
        timeout=120,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise VideoReferenceError(
            "Could not read this video link"
            + (f": {detail}" if detail else ". The site may block downloads "
               "or require a login (TikTok / Instagram often do).")
        )
    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise VideoReferenceError("Could not parse video metadata.") from exc
    duration = info.get("duration")
    if duration is not None and float(duration) > MAX_VIDEO_REFERENCE_SECONDS:
        raise VideoReferenceError(
            f"This video is {float(duration):.0f} seconds long; videos over "
            f"{MAX_VIDEO_REFERENCE_SECONDS} seconds are refused to keep "
            "analysis cost down. Use a shorter clip."
        )
    return {
        "title": str(info.get("title") or ""),
        "uploader": str(info.get("uploader") or info.get("channel") or ""),
        "duration": float(duration) if duration is not None else None,
        "webpage_url": str(info.get("webpage_url") or url),
    }


def download_video_reference(url: str, dest_dir: Path) -> tuple[Path, dict[str, Any]]:
    """Download one video (max 720p, max 200 MB) into ``dest_dir``.

    Returns ``(video_path, metadata)``. Raises VideoReferenceError on any
    failure, including the 5-minute cap.
    """
    metadata = fetch_video_metadata(url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    template = str(dest_dir / "video.%(ext)s")
    proc = _run_yt_dlp(
        [
            "--no-playlist",
            "--no-warnings",
            "--format",
            "mp4[height<=720]/best[height<=720]/best",
            "--max-filesize",
            str(MAX_VIDEO_REFERENCE_BYTES),
            "--output",
            template,
            url,
        ],
        timeout=600,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise VideoReferenceError(
            "Could not download this video"
            + (f": {detail}" if detail else ". The site may block downloads "
               "or require a login (TikTok / Instagram often do).")
        )
    candidates = sorted(
        (p for p in dest_dir.iterdir() if p.is_file() and p.name.startswith("video.")),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    if not candidates:
        raise VideoReferenceError("Download finished but no video file was produced.")
    video_path = candidates[0]
    if video_path.stat().st_size > MAX_VIDEO_REFERENCE_BYTES:
        raise VideoReferenceError(
            f"Downloaded video is over {MAX_VIDEO_REFERENCE_BYTES // (1024 * 1024)} MB."
        )
    return video_path, metadata


# ---------------------------------------------------------------------------
# OpenRouter Responses API — direct video input (primary path)
# ---------------------------------------------------------------------------

def _responses_output_text(payload: dict[str, Any]) -> str:
    """Extract the text from an OpenRouter Responses API payload."""
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = str(content.get("text") or "").strip()
                if text:
                    parts.append(text)
    if parts:
        return "\n\n".join(parts)
    # Fallback: some providers return a Chat Completions-shaped body.
    choices = payload.get("choices") or []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        text = str(message.get("content") or "").strip()
        if text:
            return text
    raise VideoReferenceError("The video model returned no text.")


async def call_openrouter_video(
    *,
    model: str,
    api_key: str,
    prompt: str,
    video_url: str | None = None,
    video_path: Path | None = None,
    timeout_seconds: float = 600.0,
) -> str:
    """Send a video (URL or local file) to a video-capable model.

    Exactly one of ``video_url`` (YouTube link, passed straight through)
    or ``video_path`` (downloaded file, sent as a base64 data URL) must be
    given. Uses the OpenRouter Responses API (``input_video``).
    """
    import httpx

    if bool(video_url) == bool(video_path):
        raise ValueError("exactly one of video_url / video_path is required")
    if video_path is not None:
        suffix = video_path.suffix.lower()
        mime = {
            ".mp4": "video/mp4",
            ".mov": "video/mov",
            ".webm": "video/webm",
            ".mpeg": "video/mpeg",
            ".mpg": "video/mpeg",
        }.get(suffix, "video/mp4")
        encoded = base64.b64encode(video_path.read_bytes()).decode()
        video_value = f"data:{mime};base64,{encoded}"
    else:
        video_value = str(video_url)

    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_video", "video_url": video_value},
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://dramaclaw.sukablyat.my.id/",
        "X-Title": "DramaClaw video reference analysis",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                OPENROUTER_RESPONSES_URL, headers=headers, json=payload
            )
    except httpx.TimeoutException as exc:
        raise VideoReferenceError(
            f"Video analysis timed out after {timeout_seconds:.0f}s."
        ) from exc
    except httpx.HTTPError as exc:
        raise VideoReferenceError(f"Could not reach OpenRouter: {exc}") from exc
    if response.status_code >= 400:
        detail = response.text.strip()[-500:]
        raise VideoReferenceError(
            f"OpenRouter rejected the video analysis request "
            f"(HTTP {response.status_code})"
            + (f": {detail}" if detail else ".")
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise VideoReferenceError("OpenRouter returned a non-JSON response.") from exc
    return _responses_output_text(data)


# ---------------------------------------------------------------------------
# Frames fallback (max 8 keyframes, StyleAnalyzer compression)
# ---------------------------------------------------------------------------

async def analyze_video_frames_fallback(
    *,
    video_path: Path,
    project_dir: Path,
    job_id: str,
    prompt: str,
    model: str | None,
) -> str:
    """Analyse at most 8 extracted keyframes via the NewAPI vision model.

    Same compression as StyleAnalyzer (max 1024px edge, JPEG q60) via
    ``load_compact_vision_inputs``. Only used when direct video input is
    unavailable for the model/URL.
    """
    from novelvideo.freezone.jobs import run_freezone_extract_frames
    from novelvideo.freezone.vision_gateway import (
        call_freezone_vision_model,
        load_compact_vision_inputs,
    )
    from novelvideo.freezone.vision_gateway import (
        FREEZONE_VIDEO_ANALYSIS_TIMEOUT_SECONDS,
    )

    frame_paths = await run_freezone_extract_frames(
        project_dir=project_dir,
        job_id=job_id,
        video_path=video_path,
        max_frames=MAX_FALLBACK_FRAMES,
        scene_threshold=0.3,
    )
    if not frame_paths:
        raise VideoReferenceError("Could not extract any keyframe from the video.")
    frame_inputs = await load_compact_vision_inputs(frame_paths)
    if not frame_inputs:
        raise VideoReferenceError("Could not read any extracted keyframe.")
    _model, text = await call_freezone_vision_model(
        prompt=prompt,
        images=frame_inputs,
        timeout_seconds=FREEZONE_VIDEO_ANALYSIS_TIMEOUT_SECONDS,
        model_override=model,
    )
    if not (text or "").strip():
        raise VideoReferenceError("The vision model returned no text.")
    return text.strip()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def analyze_video_reference(
    *,
    url: str,
    mode: str = "reference",
    checklist: Any = (),
    extra_notes: str = "",
    model: str | None = None,
    work_dir: Path | None = None,
    project_dir: Path | None = None,
    job_id: str = "video_reference",
    egress_context: Any | None = None,
) -> dict[str, Any]:
    """Analyse one reference video. One analysis at a time (locked).

    ``egress_context`` is accepted (and ignored) so the task runner can
    route this network leaf through ``_call_freezone_leaf`` like the other
    vision leaves; the OpenRouter call is a direct provider call, not a
    gateway-routed one.

    Returns ``{"analysis", "source", "model", "metadata", "fallback"}`` where
    ``source`` is ``"direct_youtube"`` | ``"direct_file"`` |
    ``"frames_fallback"``.
    """
    clean_url = str(url or "").strip()
    if not clean_url:
        raise VideoReferenceError("video_url is required.")
    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise VideoReferenceError("video_url must be an http(s) URL.")

    mode = normalize_video_reference_mode(mode)
    aspects = normalize_video_reference_checklist(checklist)
    language = resolve_director_language()
    chosen_model = resolve_video_analysis_model(model)

    async with _ANALYSIS_LOCK:
        metadata: dict[str, Any] = {}
        video_path: Path | None = None
        tmpdir: tempfile.TemporaryDirectory | None = None
        try:
            if is_youtube_url(clean_url):
                # Path 1a: YouTube link straight to the video model.
                prompt = build_video_reference_prompt(
                    mode=mode,
                    checklist=aspects,
                    extra_notes=extra_notes,
                    metadata=metadata,
                    language=language,
                )
                api_key = resolve_openrouter_api_key()
                analysis = await call_openrouter_video(
                    model=chosen_model,
                    api_key=api_key,
                    prompt=prompt,
                    video_url=clean_url,
                )
                return {
                    "analysis": analysis,
                    "source": "direct_youtube",
                    "model": chosen_model,
                    "metadata": metadata,
                    "fallback": None,
                }

            # Path 1b: download once, send the file itself.
            base = work_dir or Path(tempfile.gettempdir())
            tmpdir = tempfile.TemporaryDirectory(
                prefix="dramaclaw_video_ref_", dir=str(base)
            )
            video_path, metadata = await asyncio.to_thread(
                download_video_reference, clean_url, Path(tmpdir.name)
            )
            prompt = build_video_reference_prompt(
                mode=mode,
                checklist=aspects,
                extra_notes=extra_notes,
                metadata=metadata,
                language=language,
            )
            api_key = resolve_openrouter_api_key()
            try:
                analysis = await call_openrouter_video(
                    model=chosen_model,
                    api_key=api_key,
                    prompt=prompt,
                    video_path=video_path,
                )
            except VideoReferenceError as exc:
                # Path 2: frames fallback, only if the direct call failed.
                if project_dir is None:
                    raise
                logger.warning(
                    "video reference: direct video input failed (%s); "
                    "falling back to %d keyframes",
                    exc,
                    MAX_FALLBACK_FRAMES,
                )
                analysis = await analyze_video_frames_fallback(
                    video_path=video_path,
                    project_dir=project_dir,
                    job_id=job_id,
                    prompt=prompt
                    + "\n\n(Note: this analysis is based on extracted "
                    "keyframes, not the full video, because direct video "
                    "input was unavailable.)",
                    model=chosen_model,
                )
                return {
                    "analysis": analysis,
                    "source": "frames_fallback",
                    "model": chosen_model,
                    "metadata": metadata,
                    "fallback": (
                        "Direct video input failed "
                        f"({exc}); analysed {MAX_FALLBACK_FRAMES} keyframes instead."
                    ),
                }
            return {
                "analysis": analysis,
                "source": "direct_file",
                "model": chosen_model,
                "metadata": metadata,
                "fallback": None,
            }
        finally:
            if tmpdir is not None:
                tmpdir.cleanup()
