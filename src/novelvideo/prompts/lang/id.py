"""Xia Director language instruction — Indonesian (Bahasa Indonesia).

Used when the UI language / ``DRAMACLAW_UI_LANGUAGE`` is ``id``. The
frontend UI itself has no ``id`` locale (supported UI languages are
zh / en / vi / pt), so ``id`` is opt-in: send ``ui_language: "id"`` in the
chat context, or set ``DRAMACLAW_UI_LANGUAGE=id`` on the api service.

Design note: dialogue and story prose are Indonesian, but visual
generation prompts (``visual_description`` and other image / video prompt
fields) stay in English — the image / video models are prompted in
English upstream, and translating those fields into Indonesian degrades
generation quality. Character and location names are kept verbatim.
"""

from __future__ import annotations

DIRECTOR_LANGUAGE_INSTRUCTION = """[DRAMACLAW_LANGUAGE]
director_language: id
- Reply to the user in Bahasa Indonesia.
- Write every user-visible prose field (chat replies, plans, story scripts,
  character settings, scene settings, node titles and summaries) in
  Bahasa Indonesia. Dialogue in the script must be in Bahasa Indonesia.
- Keep every supplied character and location name verbatim; never
  translate, romanize, or rewrite a name.
- Visual generation prompts (image / video prompt fields such as
  visual_description) must stay in English, because the image / video
  generators are prompted in English. Do not translate those fields into
  Indonesian.
[/DRAMACLAW_LANGUAGE]"""

# Indonesian counterpart of rule 6 of FREEZONE_STORY_SCRIPT_SYSTEM_PROMPT
# in freezone/text_node.py. Story prose is Indonesian; the visual prompt
# fields keep English (see the director instruction above).
STORY_SCRIPT_LANGUAGE_RULE = (
    "Keep all story and dialogue fields in Bahasa Indonesia, and keep "
    "visual_description / shot prompt fields in English, except technical "
    "tokens when naturally needed."
)
