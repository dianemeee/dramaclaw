# Xia Director language pack (`id-language-pack` branch)

Goal: Xia Director follows the UI language choice (`en`, and opt-in
`id`), while upstream updates keep merging cleanly.

## Audit — where the Chinese is hardcoded

| # | Location | What is Chinese | In scope for this patch? |
|---|---|---|---|
| 1 | `src/novelvideo/chat/service.py` — `_prompt_with_user_context` / `_user_context_parts` (lines ~1886–2060) | The prompt handed to the agent runtime is assembled here, with no language parameter. The frontend never sent its UI language to the backend. | **Yes — main wiring.** New `language` kwarg; a `[DRAMACLAW_LANGUAGE]` block is injected into the header, resolved explicit arg > `surface_context["ui_language"]` > `DRAMACLAW_UI_LANGUAGE` env > `zh`. |
| 2 | `frontend/src/features/superchat/use-superchat.ts` — `send()` | Chat WS frame had no language field. | **Yes.** Sends `ui_language: i18next.resolvedLanguage` inside the Freezone `context` (which the backend already forwards as `surface_context`). |
| 3 | `src/novelvideo/api/routes/chat.py` — `ChatMessageIn.context` / `chat_ws` | `msg.context` is already forwarded as `surface_context` for Freezone scopes — no change needed. | No change. **Limitation:** Series (`project`) and home scopes do not forward `context`, so they use the `DRAMACLAW_UI_LANGUAGE` env var until a follow-up threads `ui_language` through `ChatMessageIn` top-level. |
| 4 | `src/novelvideo/prompts/__init__.py` | Empty stub ("后续实现") — the prompts are *not* centralised here. | No. The packs live in `prompts/lang/` instead (see below). |
| 5 | `src/novelvideo/freezone/text_node.py` — `FREEZONE_STORY_SCRIPT_SYSTEM_PROMPT` rule 6 | "Keep all fields in Simplified Chinese…" | **Yes.** New `freezone_story_script_system_prompt(language)` swaps only rule 6 for the pack rule; `create/get_freezone_story_script_agent(..., language=...)` added. Upstream prompt text untouched. |
| 6 | `src/novelvideo/agents/keyframe_prompt_builder.py`, `video_prompt_builder.py`, `src/novelvideo/seedance2_i2v/prompt.py` | Factory / `build()` / fallback defaults hardcoded `"zh"`; `video_prompt_builder._build_task_en` was even called with a hardcoded `language="zh"`. | **Yes (entry points).** Defaults are now `None` and resolve via `default_asset_language()` (env `DRAMACLAW_UI_LANGUAGE`; `en`/`id` → English, else `zh`). Callers passing an explicit (content-detected) language are unaffected. The ~12 small internal helpers in `seedance2_i2v/prompt.py` still default to `"zh"` — they take language from their callers, and changing them is a follow-up, not needed for the director path. |
| 7 | `src/novelvideo/utils/source_language.py` — `AssetLanguage = Literal["zh", "en"]`, `detect_asset_language` | Asset prose language is *detected from the authored content*, not from the UI. Indonesian (Latin script) would be misdetected as English. | **Partial.** Added `default_asset_language()` / `resolve_asset_language()`; the `Literal` and the detector are intentionally unchanged — asset prose follows content, director prose follows the UI. |
| 8 | `src/novelvideo/agents/episode_planner.py`, `content_rewriter.py`, `episode_fixer.py`, `cognee/pipeline.py`, `freezone/recipe_runtime.py`, `freezone/catalog.py` (recipes/skills) | Dozens of further Chinese system prompts and recipe templates. | **Out of scope for the first patch.** These still run in Chinese; the director-level instruction (item 1) tells the agent to *output* in the chosen language, which covers replies, plans and scripts. Translating every planner/reviewer prompt is the follow-up, one pack file at a time. |
| 9 | Frontend node labels (`内容段`, `场景设定`, `角色设定` …) and workflow template names | Baked into canvas templates / node types, not behind `i18n`. | **Out of scope.** They stay Chinese; only generated *content* changes language. |
| 10 | Codex/Hermes agent runtime itself | External binaries; their built-in instructions are not in this repo. | Out of scope. The language instruction reaches them through the prompt text (item 1). |

## Design — language packs, not inline edits

- `src/novelvideo/prompts/lang/zh.py` — original Chinese instruction + story-script rule (the fallback).
- `src/novelvideo/prompts/lang/en.py` — English pack.
- `src/novelvideo/prompts/lang/id.py` — Bahasa Indonesia pack. Replies/scripts/dialogue in Indonesian; **visual generation prompt fields stay in English** (image/video models are prompted in English upstream).
- `src/novelvideo/prompts/lang/__init__.py` — loader: `normalize_ui_language`, `resolve_director_language` (explicit > context > env > `zh`), `director_language_instruction`, `story_script_language_rule`. Missing strings fall back to the `zh` pack. Adding `vi`/`pt` = one new file + one entry in `_PACKS`.
- `DRAMACLAW_UI_LANGUAGE` — env var on the `api` service (`en` / `id` / `zh`). Covers Series/home scopes and every agent default until the frontend threads `ui_language` through everywhere.

## Merge hygiene

- New files: `prompts/lang/*`, `.github/workflows/build-images.yml`, `.github/workflows/sync-upstream.yml`, this doc.
- Modified files: `chat/service.py` (kwarg + header block only), `freezone/text_node.py` (helper + optional params), `agents/keyframe_prompt_builder.py`, `agents/video_prompt_builder.py`, `seedance2_i2v/prompt.py`, `utils/source_language.py` (two new functions), `frontend/.../use-superchat.ts` (one context field).
- No upstream Chinese prompt string was edited in place. An upstream change to any of those files merges at line level; a conflict only appears if upstream touches the exact wired lines.

## Verification done locally

- `python3 -m compileall` on all changed Python files — pass.
- `python3` import smoke test of `novelvideo.prompts.lang` (needs the repo's deps for a full import; see `DEPLOY.md` for what still needs a live check).
- Workflows are YAML-validated locally; they have **not** run on GitHub yet (no push in this preparation step).
- **Not yet verified live:** Xia Director actually answering in English/Indonesian against a running fork image; the `ui_language` round-trip through the WS; image/video prompt builders under `DRAMACLAW_UI_LANGUAGE=en`. Those need the deploy in `~/workspace/dramaclaw-fork/DEPLOY.md`.
