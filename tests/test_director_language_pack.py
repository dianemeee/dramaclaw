"""Regression tests for the Xia Director language packs.

The packs live in ``novelvideo.prompts.lang`` so upstream prompt
changes merge without touching translated strings. These tests pin the
loader contract: normalisation, fallback to Chinese, env-var
resolution, and the asset-language defaults that follow the UI
language.
"""

from __future__ import annotations

import pytest

from novelvideo.prompts.lang import (
    director_language_instruction,
    normalize_ui_language,
    resolve_director_language,
    story_script_language_rule,
    workflow_item_titles,
)
from novelvideo.utils.source_language import (
    default_asset_language,
    resolve_asset_language,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("en", "en"),
        ("en-US", "en"),
        ("en_US", "en"),
        ("id", "id"),
        ("zh", "zh"),
        ("zh-CN", "zh"),
        ("vi", "zh"),  # UI locale with no director pack yet -> upstream default
        ("pt", "zh"),
        ("", "zh"),
        (None, "zh"),
    ],
)
def test_normalize_ui_language(raw, expected):
    assert normalize_ui_language(raw) == expected


def test_director_instruction_english():
    block = director_language_instruction("en")
    assert "director_language: en" in block
    assert "Reply to the user in English." in block


def test_director_instruction_indonesian_keeps_visual_prompts_english():
    block = director_language_instruction("id")
    assert "director_language: id" in block
    assert "Bahasa Indonesia" in block
    assert "must stay in English" in block


def test_director_instruction_falls_back_to_chinese():
    block = director_language_instruction("vi")
    assert "director_language: zh" in block


def test_story_script_rules_differ_per_language():
    assert "English" in story_script_language_rule("en")
    assert "Bahasa Indonesia" in story_script_language_rule("id")
    assert "Simplified Chinese" in story_script_language_rule("zh")


def test_resolve_director_language_prefers_explicit_over_env(monkeypatch):
    monkeypatch.setenv("DRAMACLAW_UI_LANGUAGE", "id")
    assert resolve_director_language("en") == "en"
    assert resolve_director_language(None, "en") == "en"
    assert resolve_director_language(None, None) == "id"


def test_resolve_director_language_defaults_to_chinese(monkeypatch):
    monkeypatch.delenv("DRAMACLAW_UI_LANGUAGE", raising=False)
    assert resolve_director_language(None, None) == "zh"


@pytest.mark.parametrize(
    ("env", "expected"),
    [("en", "en"), ("id", "en"), ("vi", "zh"), ("zh", "zh"), (None, "zh")],
)
def test_default_asset_language_follows_ui_language(monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv("DRAMACLAW_UI_LANGUAGE", raising=False)
    else:
        monkeypatch.setenv("DRAMACLAW_UI_LANGUAGE", env)
    assert default_asset_language() == expected


def test_resolve_asset_language_explicit_wins(monkeypatch):
    monkeypatch.setenv("DRAMACLAW_UI_LANGUAGE", "zh")
    assert resolve_asset_language("en") == "en"
    assert resolve_asset_language("id") == "en"
    assert resolve_asset_language(None) == "zh"


def test_workflow_item_titles_english():
    titles = workflow_item_titles("en")
    assert titles["outline"] == "Content Planning"
    assert titles["frame_suffix"] == " Frame"
    assert titles["video_suffix"] == " Video"
    assert titles["final_compose"] == "Final Composition"
    assert titles["workflow_input"] == "User Request / Input Material"


def test_workflow_item_titles_fall_back_to_chinese():
    titles = workflow_item_titles("vi")  # UI locale with no pack yet
    assert titles["outline"] == "内容规划"
    assert titles["frame_suffix"] == "画面"
    assert titles["video_suffix"] == "视频"
    assert titles["final_compose"] == "成片合成"


def _english_planner_titles(monkeypatch):
    """Compile the standard text-to-image-video planner in English."""
    from novelvideo.freezone.agent_workflows import catalog

    monkeypatch.delenv("DRAMACLAW_UI_LANGUAGE", raising=False)
    intent = {
        "schema_version": "freezone_workflow_intent.v1",
        "skill_id": "text-to-image-video",
        "user_goal": "Make a short video about the Lenteng Agung eviction.",
        "language": "en",
        "planner": {
            "mode": "standard",
            "deliverable": "video",
            "item_count": 2,
            "include_audio": False,
            "units": [
                {
                    "title": "Restricted Zone Discovery",
                    "prompt": "Residents face the eviction notice.",
                },
                {
                    "title": "Eviction Escalation",
                    "prompt": "Bulldozers arrive at dawn.",
                },
            ],
        },
    }
    compiled = catalog.compile_workflow_intent(intent)
    assert compiled.get("ok"), compiled
    return [
        node.get("data", {}).get("title") or node.get("title")
        for node in compiled["plan"]["nodes"]
    ]


def test_standard_planner_titles_follow_intent_language(monkeypatch):
    titles = _english_planner_titles(monkeypatch)
    assert titles == [
        "User Request / Input Material",
        "Content Planning",
        "Restricted Zone Discovery Frame",
        "Restricted Zone Discovery Video",
        "Eviction Escalation Frame",
        "Eviction Escalation Video",
        "Final Composition",
    ]


def test_standard_planner_titles_stay_chinese_without_language(monkeypatch):
    """No intent language and no env var: upstream Chinese titles, unchanged."""
    from novelvideo.freezone.agent_workflows import catalog

    monkeypatch.delenv("DRAMACLAW_UI_LANGUAGE", raising=False)
    intent = {
        "schema_version": "freezone_workflow_intent.v1",
        "skill_id": "text-to-image-video",
        "user_goal": "Make a short video about the Lenteng Agung eviction.",
        "planner": {
            "mode": "standard",
            "deliverable": "video",
            "item_count": 2,
            "include_audio": False,
            "units": [
                {
                    "title": "Restricted Zone Discovery",
                    "prompt": "Residents face the eviction notice.",
                },
                {
                    "title": "Eviction Escalation",
                    "prompt": "Bulldozers arrive at dawn.",
                },
            ],
        },
    }
    compiled = catalog.compile_workflow_intent(intent)
    assert compiled.get("ok"), compiled
    titles = [
        node.get("data", {}).get("title") or node.get("title")
        for node in compiled["plan"]["nodes"]
    ]
    assert titles == [
        "用户需求 / 输入素材",
        "内容规划",
        "Restricted Zone Discovery画面",
        "Restricted Zone Discovery视频",
        "Eviction Escalation画面",
        "Eviction Escalation视频",
        "成片合成",
    ]
