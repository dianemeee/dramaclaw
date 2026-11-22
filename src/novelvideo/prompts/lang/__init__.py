"""Language packs for Xia Director (and Freezone text agents).

Design (why this module exists)
--------------------------------
Upstream DramaClaw hardcodes Xia Director's working language to Chinese:
the prompt text handed to the agent runtime is built in
``novelvideo.chat.service`` (``_prompt_with_user_context`` /
``_user_context_parts``) and in the Freezone text agents, with no
language parameter. The UI language (``zh`` / ``en`` / ``vi`` / ``pt``,
``frontend/src/i18n/languages.ts``) only ever translated frontend
strings — it was never sent to the backend.

This package is the *only* place that holds translated director
instructions. Upstream prompt strings are **not** edited in place:
callers ask this loader for the instruction block for a language, and
the loader falls back to the ``zh`` pack for any missing string. That
keeps upstream merges clean — an upstream change to a prompt file is a
logic diff, and a language change is a diff in exactly one file here.

Supported director languages
----------------------------
- ``zh`` — original upstream behaviour (default).
- ``en`` — full English (UI language ``en``).
- ``id`` — Bahasa Indonesia for replies / scripts / dialogue; visual
  generation prompt fields stay in English (see ``lang/id.py``). The
  frontend has no ``id`` UI locale, so ``id`` is opt-in via
  ``DRAMACLAW_UI_LANGUAGE=id`` or ``ui_language: "id"`` in the chat
  context.
- ``vi`` / ``pt`` — UI locales with no director pack yet; they fall back
  to ``zh`` (upstream behaviour) until a pack is added. Add a file
  ``lang/vi.py`` / ``lang/pt.py`` with the same two constants and register
  it in ``_PACKS`` — no other code change is needed.
"""

from __future__ import annotations

import os

from . import en as _en
from . import id as _id
from . import zh as _zh

__all__ = [
    "SUPPORTED_DIRECTOR_LANGUAGES",
    "normalize_ui_language",
    "director_language_instruction",
    "story_script_language_rule",
    "workflow_item_titles",
]

#: Director languages with a pack in this package.
SUPPORTED_DIRECTOR_LANGUAGES = ("zh", "en", "id")

#: UI locales the frontend can send (frontend/src/i18n/languages.ts).
SUPPORTED_UI_LANGUAGES = ("zh", "en", "vi", "pt")

_PACKS = {"zh": _zh, "en": _en, "id": _id}


def normalize_ui_language(value: object | None) -> str:
    """Normalise a UI language tag (``en-US`` -> ``en``) to a pack name.

    Unknown / unsupported tags fall back to ``zh`` (upstream behaviour),
    never to an empty string.
    """
    tag = str(value or "").strip().lower().replace("_", "-")
    two = tag[:2]
    if two in SUPPORTED_DIRECTOR_LANGUAGES:
        return two
    return "zh"


def resolve_director_language(
    *candidates: object | None,
) -> str:
    """Pick the first usable director language from ``candidates``.

    Callers pass, in priority order, an explicit argument, the chat
    ``surface_context`` ``ui_language``, then the
    ``DRAMACLAW_UI_LANGUAGE`` env var. ``None`` / empty / unsupported
    values are skipped; the result is always a pack name.
    """
    for candidate in candidates:
        if candidate is None:
            continue
        tag = str(candidate).strip().lower().replace("_", "-")[:2]
        if tag in SUPPORTED_DIRECTOR_LANGUAGES:
            return tag
    env = os.environ.get("DRAMACLAW_UI_LANGUAGE", "")
    tag = env.strip().lower().replace("_", "-")[:2]
    if tag in SUPPORTED_DIRECTOR_LANGUAGES:
        return tag
    return "zh"


def director_language_instruction(language: object | None = None) -> str:
    """Return the ``[DRAMACLAW_LANGUAGE]`` block for ``language``."""
    pack = _PACKS[normalize_ui_language(language)]
    return pack.DIRECTOR_LANGUAGE_INSTRUCTION


def story_script_language_rule(language: object | None = None) -> str:
    """Return the story-script language rule for ``language``."""
    pack = _PACKS[normalize_ui_language(language)]
    return pack.STORY_SCRIPT_LANGUAGE_RULE


def workflow_item_titles(language: object | None = None) -> dict[str, str]:
    """Return the standard-planner workflow item titles for ``language``.

    The deterministic planner in ``freezone/agent_workflows/catalog.py``
    shows these titles verbatim in the Workflow progress card, so they
    must follow the UI language. Unknown keys fall back to the ``zh``
    pack; unknown languages fall back to ``zh`` entirely.
    """
    pack = _PACKS[normalize_ui_language(language)]
    titles = dict(_zh.WORKFLOW_ITEM_TITLES)
    titles.update(getattr(pack, "WORKFLOW_ITEM_TITLES", {}) or {})
    return titles
