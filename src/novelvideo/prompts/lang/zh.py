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

# Display titles of the deterministic standard-planner workflow items
# (``freezone/agent_workflows/catalog.py`` ``_standard_skill_items``).
# These titles are shown verbatim in the Workflow progress card, so they
# must follow the UI language. Suffix values are appended to the
# agent-authored unit title (e.g. ``{title}画面``); keep them exactly as
# the planner composes them (no leading space in Chinese).
WORKFLOW_ITEM_TITLES = {
    "outline": "内容规划",
    "ad_outline": "广告创意大纲",
    "product_anchor": "商品视觉锚点",
    "character_setup": "角色设定",
    "scene_setup": "场景设定",
    "prop_setup": "道具设定",
    "character_image": "角色身份图",
    "scene_image": "场景参考图",
    "prop_image": "道具参考图",
    "shot_design_suffix": "镜头设计",
    "first_frame_suffix": "首帧",
    "frame_suffix": "画面",
    "video_suffix": "视频",
    "narration_suffix": "旁白",
    "background_music": "背景音乐",
    "outline_part": "第{index}段",
    "outline_narration_label": "旁白：",
    "outline_facts_header": "逐段事实与旁白（必须完整保留）：",
    "deferred_narration_prompt": (
        "只朗读上游镜头设计输出中的 narration、voiceover、"
        "dialogue 或 speech_text 正文，不朗读制作说明。"
    ),
    "final_compose": "成片合成",
    "final_compose_description": "汇总视频片段、配乐和旁白，进入时间线完成最终编排。",
    "workflow_input": "用户需求 / 输入素材",
}
