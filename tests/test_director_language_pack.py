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
