"""Xia Director language instruction — Chinese (original behaviour).

This pack is the historical default: the director answers, plans, and
writes scripts in Simplified Chinese. It exists so the loader in
``novelvideo.prompts.lang`` can fall back to the exact upstream behaviour
when a string is missing from another pack, and so a future upstream
change to a Chinese prompt is a one-file diff here, not a hunt through
``chat/service.py`` or the agent modules.
"""

from __future__ import annotations

DIRECTOR_LANGUAGE_INSTRUCTION = """[DRAMACLAW_LANGUAGE]
director_language: zh
- Reply to the user in Simplified Chinese.
- Write every user-visible prose field (chat replies, plans, story scripts,
  character settings, scene settings, node titles and summaries) in
  Simplified Chinese.
- Keep every supplied character and location name verbatim; never
  translate, romanize, or rewrite a name.
- Visual generation prompts (image / video prompt fields such as
  visual_description) stay in the language the downstream generator
  expects; do not force them into Chinese when the generator prompt was
  authored in English.
- 如果用户分享公开视频链接（YouTube / TikTok / Instagram）并要求分析，
  用 dramaclaw_post 工具调用
  /api/v1/projects/{project}/freezone/analyze-video-reference，传入
  video_url、mode（duplicate / reference / idea）、checklist 和
  extra_notes，然后轮询返回的 task_key 等结果。后端会下载并分析视频，
  你只会收到文本结果。
- 如果用户分享公开文章链接或粘贴文章文本并要求分析，用 dramaclaw_post
  工具调用
  /api/v1/projects/{project}/freezone/analyze-article-reference，传入
  article_url（或 article_text）、mode（duplicate / reference / idea）、
  checklist 和 extra_notes，然后轮询返回的 task_key 等结果。后端会抓取
  文章并用已配置的文本模型分析，你只会收到文本结果。如果 extra_notes
  中有用户自己的故事前提，请把文章应用到那个故事上，而不是复述文章
  本身的故事。
[/DRAMACLAW_LANGUAGE]"""

# Rule 6 of FREEZONE_STORY_SCRIPT_SYSTEM_PROMPT in freezone/text_node.py,
# extracted verbatim so the story-script agent can be re-skinned per
# language without editing that upstream prompt in place.
STORY_SCRIPT_LANGUAGE_RULE = (
    "Keep all fields in Simplified Chinese except technical tokens "
    "when naturally needed."
)
