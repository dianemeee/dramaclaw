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
  English. That includes the titles, descriptions, and option labels of
  any clarification question you ask (for example the video-sound /
  generate-audio question and the image / video model, ratio, resolution,
  duration, and variant questions): ask them in English and offer the
  choices in English, never in Chinese.
- Keep every supplied character and location name verbatim; never
  translate, romanize, or rewrite a name.
- Visual generation prompts (image / video prompt fields such as
  visual_description) should also be written in English, which is what
  the image / video generators expect.
- If the user shares a public video link (YouTube / TikTok / Instagram)
  and asks for an analysis, use the dramaclaw_post tool on
  /api/v1/projects/{project}/freezone/analyze-video-reference with
  video_url, mode (duplicate / reference / idea), checklist and
  extra_notes, then poll the returned task_key for the result. The
  backend downloads the video and analyses it; you only receive text.
- If the user shares a public article link or pastes article text and
  asks for an analysis, use the dramaclaw_post tool on
  /api/v1/projects/{project}/freezone/analyze-article-reference with
  article_url (or article_text), mode (duplicate / reference / idea),
  checklist and extra_notes, then poll the returned task_key for the
  result. The backend fetches the article and analyses it with the
  configured text model; you only receive text. If extra_notes carries
  the user's own story premise, apply the article to THAT story instead
  of retelling the article's story.
[/DRAMACLAW_LANGUAGE]"""

# English counterpart of rule 6 of FREEZONE_STORY_SCRIPT_SYSTEM_PROMPT
# in freezone/text_node.py.
STORY_SCRIPT_LANGUAGE_RULE = (
    "Keep all fields in English except technical tokens when naturally needed."
)

# English display titles of the deterministic standard-planner workflow
# items (see ``lang/zh.py`` for the layout contract). Suffix values are
# appended to the agent-authored unit title, so they carry a leading
# space in English (``{title} Frame``) where Chinese has none.
WORKFLOW_ITEM_TITLES = {
    "outline": "Content Planning",
    "ad_outline": "Ad Creative Outline",
    "product_anchor": "Product Visual Anchor",
    "character_setup": "Character Setup",
    "scene_setup": "Scene Setup",
    "prop_setup": "Prop Setup",
    "character_image": "Character Identity Image",
    "scene_image": "Scene Reference Image",
    "prop_image": "Prop Reference Image",
    "shot_design_suffix": " Shot Design",
    "first_frame_suffix": " First Frame",
    "frame_suffix": " Frame",
    "video_suffix": " Video",
    "narration_suffix": " Narration",
    "background_music": "Background Music",
    "outline_part": "Part {index}",
    "outline_narration_label": "Narration: ",
    "outline_facts_header": "Per-part facts and narration (must be kept in full):",
    "deferred_narration_prompt": (
        "Only read aloud the narration, voiceover, dialogue or "
        "speech_text from the upstream shot-design output. "
        "Do not read production notes."
    ),
    "final_compose": "Final Composition",
    "final_compose_description": (
        "Combine the video clips, music and narration into the "
        "timeline for the final cut."
    ),
    "workflow_input": "User Request / Input Material",
}
