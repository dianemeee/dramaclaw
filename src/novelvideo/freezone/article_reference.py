"""Reference-article analysis for Xia Director (Freezone + Series).

A user pastes an article link (the backend fetches it and extracts the
readable article text) or pastes the article text directly, and optionally
picks a mode (duplicate / reference / idea), a checklist of aspects to
analyse, and free-text extra notes — where she can write HER OWN story
premise and have the article applied to it. Xia Director then analyses
the article and turns the result into script / storyboard material.

Unlike the video feature this needs NO new API key or env var: articles
are plain text, so the analysis runs through the existing NewAPI text
model plumbing (the same pydantic-ai Agent pattern StyleAnalyzer uses).
No download of media, no video model, no yt-dlp.

Server-side resolution only — Series chat scope does NOT forward frontend
``context`` to the backend (see ``api/routes/chat.py``: the ``surface_context``
is ``msg.context`` for Freezone only, ``None`` for Series). So the reply
language comes from the ``DRAMACLAW_UI_LANGUAGE`` env var, never from a
``ui_language`` field in the request. That is what makes this work in both
Freezone and Series.

Limits: article text is capped at 20k characters (truncated with a note);
one analysis runs at a time (module-level lock); article fetch has a
30s timeout and refuses non-HTML / unreadably short pages, telling the
user to paste the text instead.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("novelvideo.freezone.article_reference")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARTICLE_ANALYSIS_MODEL_ENV = "ARTICLE_ANALYSIS_MODEL"

#: Cap article text at this many characters (keeps the prompt + cost sane).
MAX_ARTICLE_REFERENCE_CHARS = 20000
#: Refuse fetched pages with less readable text than this — almost
#: certainly a paywall / JS-only page, not an article.
MIN_ARTICLE_REFERENCE_CHARS = 200
#: Article fetch timeout (seconds).
ARTICLE_FETCH_TIMEOUT_SECONDS = 30.0

ARTICLE_REFERENCE_MODES = ("duplicate", "reference", "idea")

#: Same aspect keys as the video feature, relabelled for prose: the
#: frontend reuses the same checklist, and the prompt interprets each
#: aspect for a written article instead of a video.
ARTICLE_REFERENCE_ASPECTS: tuple[tuple[str, str], ...] = (
    ("hook", "Hook — the opening: what grabs attention"),
    ("pacing", "Pacing — rhythm, fast vs slow sections"),
    ("transitions", "Transitions — how scenes / sections connect"),
    ("dialogue", "Dialogue — what is said, tone of voice"),
    ("scene_structure", "Scene structure — beats, acts, how the story is ordered"),
    ("camera", "Visual imagery — how scenes are described visually"),
    ("music", "Mood / atmosphere — tone, feeling, sound of the prose"),
    ("characters", "Characters — who appears, look, behaviour, roles"),
    ("visual_style", "Writing style — voice, diction, overall feel"),
)
ARTICLE_REFERENCE_ASPECT_KEYS = frozenset(key for key, _ in ARTICLE_REFERENCE_ASPECTS)

# Tags whose content is never article text.
_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "nav",
        "footer",
        "aside",
        "header",
        "form",
        "svg",
        "button",
        "select",
        "textarea",
        "iframe",
    }
)
# Block-level tags that start a new text block.
_BLOCK_TAGS = frozenset(
    {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "figcaption"}
)


class ArticleReferenceError(ValueError):
    """User-facing failure of an article-reference analysis step."""


# One analysis at a time: the VPS is already memory-tight, and a model
# call must never run in parallel with image/video generation.
_ANALYSIS_LOCK = asyncio.Lock()


# ---------------------------------------------------------------------------
# Pure helpers (covered by tests/test_article_reference.py)
# ---------------------------------------------------------------------------

def normalize_article_reference_mode(mode: str | None) -> str:
    """Unknown/empty mode falls back to ``"reference"``."""
    cleaned = str(mode or "").strip().lower()
    return cleaned if cleaned in ARTICLE_REFERENCE_MODES else "reference"


def normalize_article_reference_checklist(items: Any) -> tuple[str, ...]:
    """Keep only known aspect keys, in canonical order, de-duplicated."""
    if not items:
        return ()
    wanted = []
    for item in items:
        key = str(item or "").strip().lower()
        if key in ARTICLE_REFERENCE_ASPECT_KEYS and key not in wanted:
            wanted.append(key)
    ordered = [key for key, _ in ARTICLE_REFERENCE_ASPECTS if key in wanted]
    return tuple(ordered)


def resolve_director_language() -> str:
    """Reply language for the analysis, from the server-side env var.

    Freezone forwards ``ui_language`` in chat context; Series does not, so
    both scopes resolve here instead. ``id`` is opt-in (see the language
    packs); anything else falls back to ``en``.
    """
    from novelvideo.freezone.video_reference import (
        resolve_director_language as _resolve,
    )

    return _resolve()


class _ArticleTextParser(HTMLParser):
    """Light HTML-to-text pass for article pages (stdlib only).

    Skips nav/ads/boilerplate tags, prefers ``<article>`` / ``<main>``
    content when it holds most of the text, and collects block-level
    paragraphs / headings / list items.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._article_depth = 0
        self._main_depth = 0
        self._blocks: list[str] = []
        self._article_blocks: list[str] = []
        self._main_blocks: list[str] = []
        self._current: list[str] = []

    def _target_blocks(self) -> list[str]:
        if self._article_depth:
            return self._article_blocks
        if self._main_depth:
            return self._main_blocks
        return self._blocks

    def _flush(self) -> None:
        text = "".join(self._current).strip()
        if text:
            self._target_blocks().append(text)
        self._current = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "article":
            self._article_depth += 1
        elif tag == "main":
            self._main_depth += 1
        elif tag in _BLOCK_TAGS:
            self._flush()
        elif tag == "br":
            self._current.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "article":
            self._article_depth = max(0, self._article_depth - 1)
        elif tag == "main":
            self._main_depth = max(0, self._main_depth - 1)
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._current.append(data)

    def text(self) -> str:
        self._flush()
        # Prefer <article> content, then <main>, then the whole page —
        # but only when the preferred slice is substantial.
        for candidate in (self._article_blocks, self._main_blocks, self._blocks):
            joined = "\n\n".join(_clean_block(b) for b in candidate if _clean_block(b))
            if len(joined) >= MIN_ARTICLE_REFERENCE_CHARS:
                return joined
        joined = "\n\n".join(_clean_block(b) for b in self._blocks if _clean_block(b))
        return joined


def _clean_block(block: str) -> str:
    return re.sub(r"\s+", " ", block).strip()


def extract_article_text(html: str) -> str:
    """Extract readable article text from an HTML page.

    Returns ``""`` when nothing readable was found.
    """
    if not (html or "").strip():
        return ""
    parser = _ArticleTextParser()
    try:
        parser.feed(html)
    except Exception:  # pragma: no cover - malformed HTML must not crash us
        logger.warning("article reference: HTML parse failed", exc_info=True)
        return ""
    return parser.text()


def truncate_article_text(text: str) -> tuple[str, bool]:
    """Cap article text at MAX_ARTICLE_REFERENCE_CHARS.

    Returns ``(text, was_truncated)``.
    """
    cleaned = _clean_block(str(text or ""))
    if len(cleaned) <= MAX_ARTICLE_REFERENCE_CHARS:
        return cleaned, False
    cut = cleaned[:MAX_ARTICLE_REFERENCE_CHARS]
    # Don't end mid-word when we can help it.
    last_space = cut.rfind(" ")
    if last_space > MAX_ARTICLE_REFERENCE_CHARS - 500:
        cut = cut[:last_space]
    return cut, True


_MODE_INSTRUCTIONS = {
    "duplicate": (
        "DUPLICATE mode: follow this article as closely as possible. "
        "Give an ordered, beat-by-beat breakdown of the article's events "
        "that another writer could follow to retell the same story: same "
        "beats, same order, same pacing, same reveals."
    ),
    "reference": (
        "REFERENCE mode: use this article as inspiration, not a template "
        "to copy. Extract the reusable craft: what makes it work (hook, "
        "pacing, structure, character introductions, reveals), and list "
        "concrete techniques the director can borrow for a NEW, original "
        "story."
    ),
    "idea": (
        "IDEA mode: extract only the core idea / premise of this article, "
        "then generate 3 fresh angles on the same idea that have NOT been "
        "done in this article. Do not copy its events; the output is new "
        "ideas, each with a one-line premise and a suggested hook."
    ),
}


def build_article_reference_prompt(
    *,
    mode: str,
    checklist: tuple[str, ...] = (),
    extra_notes: str = "",
    article_text: str,
    source_note: str = "",
    language: str = "en",
    truncated: bool = False,
) -> str:
    """Build the analysis prompt sent to the text model.

    ``checklist`` is empty by default, which means "analyse everything"
    (all aspects below). ``extra_notes`` is the user's free textbox — this
    is where she writes her OWN story premise to apply the article to.
    """
    mode = normalize_article_reference_mode(mode)
    aspects = checklist or tuple(key for key, _ in ARTICLE_REFERENCE_ASPECTS)
    aspect_lines = "\n".join(
        f"- {label}"
        for key, label in ARTICLE_REFERENCE_ASPECTS
        if key in aspects
    )
    extra = str(extra_notes or "").strip()
    extra_block = (
        "\nThe user has her OWN story she wants to make. Apply the "
        "article to it — do not replace her story with the article's "
        f"story:\n{extra}\n"
        if extra
        else ""
    )
    source_block = f"\nSource: {source_note}\n" if source_note else ""
    trunc_block = (
        "\n(Note: only the first part of the article is included below — "
        "it was truncated to keep the analysis affordable.)\n"
        if truncated
        else ""
    )
    lang_block = (
        "\nReply in Bahasa Indonesia for prose, script and dialogue. "
        "Keep visual generation prompt fields (image / video prompts) in English.\n"
        if language == "id"
        else "\nReply in English.\n"
    )
    return f"""You are a professional short-drama director analysing a reference article.
{source_block}{trunc_block}
{_MODE_INSTRUCTIONS[mode]}

First extract, in this order:
- Premise: the core idea of the article in one sentence.
- Main conflict: what is at stake, who opposes whom.
- Characters: the key people, with one line each on who they are and what they want.
- Key events / twists: the turning points, in order.
- Tone / style: how the article feels to read.

Then analyse these aspects (in this order, one short section each):
{aspect_lines}
{extra_block}
Rules:
- Only use what is actually in the article text below. If something is
  not in the text (e.g. no dialogue), say so instead of inventing it.
- Keep each section to 2-4 sentences, except the beat breakdown in
  duplicate mode, which is an ordered list.
- End with a one-paragraph "What to steal" summary: the 3 most useful
  techniques for the director.
{lang_block}
--- ARTICLE TEXT ---
{article_text}"""


# ---------------------------------------------------------------------------
# Article fetch (URL input)
# ---------------------------------------------------------------------------

async def fetch_article(url: str) -> tuple[str, dict[str, Any]]:
    """Fetch an article URL and extract its readable text.

    Returns ``(text, metadata)``. Raises ArticleReferenceError when the
    page cannot be fetched, is not HTML, or has too little readable text —
    in that case the user should paste the article text instead.
    """
    import httpx

    clean_url = str(url or "").strip()
    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ArticleReferenceError("article_url must be an http(s) URL.")
    try:
        async with httpx.AsyncClient(
            timeout=ARTICLE_FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DramaClaw/1.0)"},
        ) as client:
            response = await client.get(clean_url)
    except httpx.TimeoutException as exc:
        raise ArticleReferenceError(
            f"Fetching the article timed out after "
            f"{ARTICLE_FETCH_TIMEOUT_SECONDS:.0f}s. Try pasting the article "
            "text directly instead."
        ) from exc
    except httpx.HTTPError as exc:
        raise ArticleReferenceError(
            f"Could not fetch the article: {exc}. Try pasting the article "
            "text directly instead."
        ) from exc
    if response.status_code >= 400:
        raise ArticleReferenceError(
            f"The article page returned HTTP {response.status_code}. "
            "Try pasting the article text directly instead."
        )
    content_type = (response.headers.get("content-type") or "").lower()
    if content_type and "html" not in content_type and "text" not in content_type:
        raise ArticleReferenceError(
            "That link is not an article page (it is not HTML). "
            "Try pasting the article text directly instead."
        )
    title = ""
    text = extract_article_text(response.text)
    if len(text) < MIN_ARTICLE_REFERENCE_CHARS:
        raise ArticleReferenceError(
            "Could not read enough text from that page — it may be a "
            "paywall, a login wall, or a JavaScript-only page. Paste the "
            "article text directly instead."
        )
    match = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.I | re.S)
    if match:
        title = _clean_block(re.sub(r"<[^>]+>", " ", match.group(1)))
    return text, {"title": title, "url": clean_url}


# ---------------------------------------------------------------------------
# Text model call (existing NewAPI text plumbing — no new key)
# ---------------------------------------------------------------------------

async def call_article_text_model(
    prompt: str, *, model_override: str | None = None
) -> tuple[str, str]:
    """Run the analysis prompt through the configured NewAPI text model.

    Same pydantic-ai Agent pattern StyleAnalyzer uses; the model is the
    one already configured for text in DramaClaw (optionally overridden
    with the ARTICLE_ANALYSIS_MODEL env var or an explicit override).
    Returns ``(model, text)``.
    """
    from pydantic_ai import Agent

    from novelvideo.brainclaw_contract import BrainClawProfile
    from novelvideo.config import (
        get_effective_newapi_text_model_name,
        get_newapi_text_pydantic_model,
    )

    clean_override = str(model_override or "").strip() or None
    model_name = get_effective_newapi_text_model_name(
        ARTICLE_ANALYSIS_MODEL_ENV, model_name_override=clean_override
    )
    model = get_newapi_text_pydantic_model(
        ARTICLE_ANALYSIS_MODEL_ENV,
        model_name_override=clean_override,
        brainclaw_profile=BrainClawProfile.FREEZONE_TEXT_GENERATION,
        capability="freezone.text.generate",
    )
    agent = Agent(
        model,
        output_type=str,
        name="Freezone Article Analyzer",
    )
    result = await agent.run(prompt)
    text = str(result.output or "").strip()
    if not text:
        raise ArticleReferenceError("The text model returned no text.")
    return model_name, text


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def analyze_article_reference(
    *,
    article_url: str | None = None,
    article_text: str | None = None,
    mode: str = "reference",
    checklist: Any = (),
    extra_notes: str = "",
    model: str | None = None,
    egress_context: Any | None = None,
) -> dict[str, Any]:
    """Analyse one reference article. One analysis at a time (locked).

    Exactly one of ``article_url`` / ``article_text`` must be given
    (pasted text wins if both are given). ``egress_context`` is accepted
    (and ignored) so the task runner can route this network leaf through
    ``_call_freezone_leaf`` like the other text leaves.

    Returns ``{"analysis", "source", "model", "metadata", "fallback"}``
    where ``source`` is ``"article_url"`` | ``"pasted_text"``.
    """
    pasted = str(article_text or "").strip()
    clean_url = str(article_url or "").strip()
    if not pasted and not clean_url:
        raise ArticleReferenceError(
            "Give an article link or paste the article text."
        )

    mode = normalize_article_reference_mode(mode)
    aspects = normalize_article_reference_checklist(checklist)
    language = resolve_director_language()

    async with _ANALYSIS_LOCK:
        metadata: dict[str, Any] = {}
        truncated = False
        if pasted:
            text, truncated = truncate_article_text(pasted)
            source = "pasted_text"
            source_note = "Pasted article text"
        else:
            fetched, metadata = await fetch_article(clean_url)
            text, truncated = truncate_article_text(fetched)
            source = "article_url"
            source_note = (
                f"Article link: {clean_url}"
                + (f" — {metadata.get('title')}" if metadata.get("title") else "")
            )
        prompt = build_article_reference_prompt(
            mode=mode,
            checklist=aspects,
            extra_notes=extra_notes,
            article_text=text,
            source_note=source_note,
            language=language,
            truncated=truncated,
        )
        model_name, analysis = await call_article_text_model(
            prompt, model_override=model
        )
        return {
            "analysis": analysis,
            "source": source,
            "model": model_name,
            "metadata": metadata,
            "fallback": (
                "Article was truncated to "
                f"{MAX_ARTICLE_REFERENCE_CHARS} characters."
                if truncated
                else None
            ),
        }
