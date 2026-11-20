"""Xia Director language instruction — English.

Used when the UI language (``i18n.resolvedLanguage`` in the frontend,
forwarded as ``ui_language`` in the chat WebSocket context, or the
``DRAMACLAW_UI_LANGUAGE`` env var) is ``en``.
"""

from __future__ import annotations

DIRECTOR_LANGUAGE_INSTRUCTION = """[DRAMACLAW_LANGUAGE]
director_language: en
- Reply to the user in English.
- Write every user-visible prose field (chat replies, plans, story scripts,
  character settings, scene settings, node titles and summaries) in
  English.
- Keep every supplied character and location name verbatim; never
  translate, romanize, or rewrite a name.
- Visual generation prompts (image / video prompt fields such as
  visual_description) should also be written in English, which is what
  the image / video generators expect.
[/DRAMACLAW_LANGUAGE]"""

# English counterpart of rule 6 of FREEZONE_STORY_SCRIPT_SYSTEM_PROMPT
# in freezone/text_node.py.
STORY_SCRIPT_LANGUAGE_RULE = (
    "Keep all fields in English except technical tokens when naturally needed."
)
