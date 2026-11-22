"""Content-language feature: narration / audio / subtitle languages.

Per-project ``content_language`` (id | en | zh, default id) and
``subtitle_language`` (id | en | zh | none, default = content language)
are separate from the UI language: the UI may be English while the
narration is Indonesian.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from novelvideo.freezone import audio_node
from novelvideo.freezone.audio_node import (
    EDGE_PRESET_VOICE_BY_LANGUAGE,
    _resolve_preset_voice,
)
from novelvideo.freezone.text_node import FREEZONE_TRANSLATION_SYSTEM_PROMPT
from novelvideo.project_config import (
    load_content_language_from_state_dir,
    load_content_languages_from_state_dir,
    load_subtitle_language_from_state_dir,
)
from novelvideo.task_backend.runners.video import (
    _format_srt_timestamp,
    _write_srt_file,
)
from novelvideo.utils.source_language import (
    asset_language_instruction,
    detect_asset_language,
    resolve_asset_language,
    resolve_content_language,
)


def _load_catalog_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "novelvideo"
        / "freezone"
        / "agent_workflows"
        / "catalog.py"
    )
    spec = importlib.util.spec_from_file_location("test_content_language_catalog", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CATALOG = _load_catalog_module()


# --- language detection -------------------------------------------------

def test_detect_asset_language_returns_id_for_indonesian():
    assert detect_asset_language("Dia sering tersenyum.") == "id"
    assert detect_asset_language(
        "Warga Lenteng Agung kehilangan rumah mereka setelah penggusuran."
    ) == "id"


def test_detect_asset_language_keeps_english_and_chinese():
    assert detect_asset_language("The cat sits on the mat.") == "en"
    assert detect_asset_language("这是一个中文句子。") == "zh"


def test_asset_language_instruction_has_indonesian_rule():
    instruction = asset_language_instruction("id")
    assert "Bahasa Indonesia" in instruction
    assert "verbatim" in instruction


def test_resolve_content_language_maps_id_to_id():
    assert resolve_content_language("id") == "id"
    assert resolve_content_language("en") == "en"
    assert resolve_content_language("zh") == "zh"
    assert resolve_content_language("ID") == "id"
    assert resolve_content_language("xx") is None
    assert resolve_content_language(None) is None
    assert resolve_content_language("") is None


def test_resolve_asset_language_still_maps_id_to_english():
    # Visual-prompt fields stay English even for Indonesian content.
    assert resolve_asset_language("id") == "en"
    assert resolve_asset_language("en") == "en"
    assert resolve_asset_language("zh") == "zh"


# --- project config -----------------------------------------------------

def _write_config(tmp_path: Path, config: dict) -> Path:
    config_path = tmp_path / "project_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


def test_load_content_languages_defaults_to_id(tmp_path):
    state_dir = _write_config(tmp_path, {})
    assert load_content_languages_from_state_dir(state_dir) == ("id", "id")
    assert load_content_language_from_state_dir(state_dir) == "id"
    assert load_subtitle_language_from_state_dir(state_dir) == "id"


def test_load_content_languages_reads_stored_values(tmp_path):
    state_dir = _write_config(
        tmp_path, {"content_language": "en", "subtitle_language": "none"}
    )
    assert load_content_languages_from_state_dir(state_dir) == ("en", "none")
    assert load_content_language_from_state_dir(state_dir) == "en"
    assert load_subtitle_language_from_state_dir(state_dir) == "none"


def test_subtitle_language_defaults_to_content_language(tmp_path):
    state_dir = _write_config(tmp_path, {"content_language": "zh"})
    assert load_content_languages_from_state_dir(state_dir) == ("zh", "zh")
    assert load_subtitle_language_from_state_dir(state_dir) == "zh"


def test_load_content_languages_rejects_invalid_values(tmp_path):
    state_dir = _write_config(
        tmp_path, {"content_language": "xx", "subtitle_language": "yy"}
    )
    assert load_content_languages_from_state_dir(state_dir) == ("id", "id")


# --- catalog resolution -------------------------------------------------

def test_resolve_intent_content_languages_prefers_stamp():
    content, subtitle = CATALOG._resolve_intent_content_languages(
        {"content_language": "id", "subtitle_language": "en", "language": "en"}
    )
    assert (content, subtitle) == ("id", "en")


def test_resolve_intent_content_languages_falls_back_to_ui_language():
    content, subtitle = CATALOG._resolve_intent_content_languages(
        {"language": "en"}
    )
    assert (content, subtitle) == ("en", "en")


def test_resolve_intent_content_languages_keeps_none_subtitle():
    content, subtitle = CATALOG._resolve_intent_content_languages(
        {"content_language": "id", "subtitle_language": "none"}
    )
    assert (content, subtitle) == ("id", "none")


def test_resolve_intent_content_languages_invalid_subtitle_defaults_to_content():
    content, subtitle = CATALOG._resolve_intent_content_languages(
        {"content_language": "en", "subtitle_language": "xx"}
    )
    assert (content, subtitle) == ("en", "en")


def test_background_music_prompt_follows_content_language():
    assert "musik instrumental" in CATALOG._background_music_prompt("goal", "id")
    assert "instrumental music" in CATALOG._background_music_prompt("goal", "en")
    assert "纯音乐" in CATALOG._background_music_prompt("goal", "zh")
    # Unknown language falls back to the Chinese prompt (old behaviour).
    assert "纯音乐" in CATALOG._background_music_prompt("goal", None)


def test_intent_item_node_speech_carries_content_languages():
    node = CATALOG._intent_item_node(
        skill={"id": "test-skill", "version": 1},
        recipe={"id": "test-recipe", "name": "Test", "version": 1},
        node_type="audioNode",
        item_id="speech_1",
        item={"title": "Narration", "narration": "Halo dunia", "prompt": "Halo dunia"},
        user_goal="test",
        resolved_inputs={},
        recipe_pipeline=[],
        content_language="id",
        subtitle_language="en",
    )
    assert node["data"]["audioKind"] == "speech"
    assert node["data"]["languageType"] == "Indonesian"
    assert node["data"]["subtitleLanguage"] == "en"


def test_intent_item_node_speech_defaults_to_chinese():
    node = CATALOG._intent_item_node(
        skill={"id": "test-skill", "version": 1},
        recipe={"id": "test-recipe", "name": "Test", "version": 1},
        node_type="audioNode",
        item_id="speech_1",
        item={"title": "Narration", "narration": "你好世界", "prompt": "你好世界"},
        user_goal="test",
        resolved_inputs={},
        recipe_pipeline=[],
    )
    assert node["data"]["languageType"] == "Chinese"
    assert node["data"]["subtitleLanguage"] == "zh"


# --- audio --------------------------------------------------------------

def test_edge_preset_voice_by_language():
    assert EDGE_PRESET_VOICE_BY_LANGUAGE == {
        "id": "id-ID-GadisNeural",
        "en": "en-US-AriaNeural",
        "zh": "zh-CN-XiaoxiaoNeural",
    }


def test_resolve_preset_voice_uses_language_default():
    assert _resolve_preset_voice("id", "Serena") == "id-ID-GadisNeural"
    assert _resolve_preset_voice("en", "Serena") == "en-US-AriaNeural"
    assert _resolve_preset_voice("zh", "Serena") == "zh-CN-XiaoxiaoNeural"
    assert _resolve_preset_voice("id", "") == "id-ID-GadisNeural"


def test_resolve_preset_voice_honours_explicit_voice():
    assert (
        _resolve_preset_voice("id", "zh-CN-XiaoxiaoNeural")
        == "zh-CN-XiaoxiaoNeural"
    )
    assert _resolve_preset_voice("en", "en-US-AriaNeural") == "en-US-AriaNeural"


@pytest.mark.asyncio
async def test_preset_speech_defaults_to_indonesian_voice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preset "Serena" follows the project language; unset means id."""
    calls: list[dict] = []

    async def fake_write_edge_tts_speech(**kwargs):
        calls.append(kwargs)
        output_path = Path(kwargs["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"preset-speech")

    monkeypatch.setattr(
        audio_node, "_write_edge_tts_speech", fake_write_edge_tts_speech
    )
    monkeypatch.setattr(audio_node, "_duration_ms", lambda _path: 1234)

    result = await audio_node.generate_freezone_audio_speech(
        store=SimpleNamespace(),
        username="alice",
        project="demo",
        project_dir=tmp_path,
        job_id="speech-preset-id",
        text="Selamat datang di Lenteng Agung.",
        speech_mode="preset",
        preset_voice="Serena",
    )

    assert result.model == "edge-tts"
    assert result.voice_source == "preset:Serena"
    assert calls[0]["voice"] == "id-ID-GadisNeural"


# --- translation prompt -------------------------------------------------

def test_translation_system_prompt_covers_indonesian():
    assert "Bahasa Indonesia" in FREEZONE_TRANSLATION_SYSTEM_PROMPT
    assert "id" in FREEZONE_TRANSLATION_SYSTEM_PROMPT


# --- subtitles ----------------------------------------------------------

def test_format_srt_timestamp():
    assert _format_srt_timestamp(0) == "00:00:00,000"
    assert _format_srt_timestamp(61.5) == "00:01:01,500"
    assert _format_srt_timestamp(3723.456) == "01:02:03,456"


def test_write_srt_file(tmp_path):
    srt_path = tmp_path / "subtitles.srt"
    _write_srt_file(
        srt_path,
        [
            (0.0, 5.0, "Halo dunia"),
            (5.0, 10.0, "  Warga   kehilangan rumah  "),
            (10.0, 15.0, ""),
        ],
    )
    assert srt_path.read_text(encoding="utf-8") == (
        "1\n00:00:00,000 --> 00:00:05,000\nHalo dunia\n\n"
        "2\n00:00:05,000 --> 00:00:10,000\nWarga kehilangan rumah\n"
    )
