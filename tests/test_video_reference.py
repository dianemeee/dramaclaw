"""Tests for reference-video analysis (Freezone + Series).

Covers only the parts that can be checked without provider keys or
network access to social sites: URL classification, mode/checklist
normalisation, prompt building, model resolution, the OpenRouter
Responses payload parsing, and the length cap. Live YouTube / TikTok /
Instagram downloads and real Gemini calls are NOT tested here — they
need keys and network, and are verified live after deploy.
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx
import pytest

from novelvideo.freezone.video_reference import (
    DEFAULT_VIDEO_ANALYSIS_MODEL,
    MAX_FALLBACK_FRAMES,
    MAX_VIDEO_REFERENCE_SECONDS,
    VideoReferenceError,
    _responses_output_text,
    build_video_reference_prompt,
    call_openrouter_video,
    classify_video_url,
    fetch_video_metadata,
    normalize_video_reference_checklist,
    normalize_video_reference_mode,
    resolve_director_language,
    resolve_video_analysis_model,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://www.tiktok.com/@user/video/123", "other"),
        ("https://www.instagram.com/reel/abc/", "other"),
        ("https://example.com/video.mp4", "other"),
        ("not a url", "other"),
    ],
)
def test_classify_video_url(url: str, expected: str) -> None:
    assert classify_video_url(url) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("duplicate", "duplicate"),
        ("REFERENCE", "reference"),
        ("idea", "idea"),
        ("", "reference"),
        ("copy", "reference"),
        (None, "reference"),
    ],
)
def test_normalize_mode(raw, expected) -> None:
    assert normalize_video_reference_mode(raw) == expected


def test_normalize_checklist_keeps_known_keys_in_order() -> None:
    assert normalize_video_reference_checklist(
        ["music", "hook", "music", "bogus", "camera"]
    ) == ("hook", "camera", "music")


def test_normalize_checklist_empty() -> None:
    assert normalize_video_reference_checklist([]) == ()
    assert normalize_video_reference_checklist(None) == ()


def test_prompt_duplicate_mode_is_scene_by_scene() -> None:
    prompt = build_video_reference_prompt(mode="duplicate")
    assert "DUPLICATE mode" in prompt
    assert "scene-by-scene" in prompt


def test_prompt_reference_mode_is_inspiration_not_copy() -> None:
    prompt = build_video_reference_prompt(mode="reference")
    assert "REFERENCE mode" in prompt
    assert "not a template to copy" in prompt


def test_prompt_idea_mode_generates_fresh_angles() -> None:
    prompt = build_video_reference_prompt(mode="idea")
    assert "IDEA mode" in prompt
    assert "3 fresh angles" in prompt


def test_prompt_checklist_limits_aspects() -> None:
    prompt = build_video_reference_prompt(
        mode="reference", checklist=("hook", "pacing")
    )
    assert "Hook" in prompt
    assert "Pacing" in prompt
    assert "Visual style" not in prompt


def test_prompt_extra_notes_included() -> None:
    prompt = build_video_reference_prompt(
        mode="reference", extra_notes="focus on the night lighting"
    )
    assert "focus on the night lighting" in prompt


def test_prompt_indonesian_language() -> None:
    prompt = build_video_reference_prompt(mode="reference", language="id")
    assert "Bahasa Indonesia" in prompt
    prompt_en = build_video_reference_prompt(mode="reference", language="en")
    assert "Reply in English" in prompt_en


def test_prompt_includes_metadata() -> None:
    prompt = build_video_reference_prompt(
        mode="reference",
        metadata={"title": "Test clip", "duration": 42.0},
    )
    assert "Test clip" in prompt
    assert "42 seconds" in prompt


def test_resolve_model_priority(monkeypatch) -> None:
    monkeypatch.delenv("VIDEO_ANALYSIS_MODEL", raising=False)
    # No saved config in this env (settings DB absent) -> default.
    assert (
        resolve_video_analysis_model()
        == DEFAULT_VIDEO_ANALYSIS_MODEL
    )
    assert (
        resolve_video_analysis_model("google/gemini-2.5-pro")
        == "google/gemini-2.5-pro"
    )
    monkeypatch.setenv("VIDEO_ANALYSIS_MODEL", "google/gemini-3-flash")
    assert resolve_video_analysis_model() == "google/gemini-3-flash"


def test_resolve_director_language(monkeypatch) -> None:
    monkeypatch.setenv("DRAMACLAW_UI_LANGUAGE", "id")
    assert resolve_director_language() == "id"
    monkeypatch.setenv("DRAMACLAW_UI_LANGUAGE", "en")
    assert resolve_director_language() == "en"
    monkeypatch.delenv("DRAMACLAW_UI_LANGUAGE", raising=False)
    assert resolve_director_language() == "en"


def test_responses_output_text() -> None:
    payload = {
        "output": [
            {
                "type": "reasoning",
                "content": [{"type": "reasoning_text", "text": "hidden"}],
            },
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Hook: strong."},
                    {"type": "output_text", "text": "Pacing: fast."},
                ],
            },
        ]
    }
    assert (
        _responses_output_text(payload) == "Hook: strong.\n\nPacing: fast."
    )


def test_responses_output_text_empty_raises() -> None:
    with pytest.raises(VideoReferenceError):
        _responses_output_text({"output": []})


def test_fallback_frame_cap() -> None:
    assert MAX_FALLBACK_FRAMES == 8
    assert MAX_VIDEO_REFERENCE_SECONDS == 300


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self.text = json.dumps(payload)
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Minimal httpx.AsyncClient stand-in for call_openrouter_video."""

    seen: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def post(self, url, headers=None, json=None):
        _FakeAsyncClient.seen = {"url": url, "headers": headers, "json": json}
        return _FakeResponse(
            200,
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "Analysis ok."}
                        ],
                    }
                ]
            },
        )


def test_call_openrouter_video_youtube_url(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    text = asyncio.run(
        call_openrouter_video(
            model="google/gemini-2.5-flash",
            api_key="test-key",
            prompt="Analyse this.",
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
    )
    assert text == "Analysis ok."
    seen = _FakeAsyncClient.seen
    assert seen["url"].endswith("/api/v1/responses")
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert seen["json"]["model"] == "google/gemini-2.5-flash"
    content = seen["json"]["input"][0]["content"]
    assert content[1]["type"] == "input_video"
    assert (
        content[1]["video_url"]
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )


def test_call_openrouter_video_rejects_error_status(monkeypatch) -> None:
    class _FailClient(_FakeAsyncClient):
        async def post(self, url, headers=None, json=None):
            return _FakeResponse(400, {"error": {"message": "bad model"}})

    monkeypatch.setattr(httpx, "AsyncClient", _FailClient)
    with pytest.raises(VideoReferenceError, match="HTTP 400"):
        asyncio.run(
            call_openrouter_video(
                model="nope",
                api_key="test-key",
                prompt="Analyse this.",
                video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            )
        )


def test_fetch_metadata_refuses_long_videos(monkeypatch, tmp_path) -> None:
    """A >5min video is refused before any download starts."""

    class _Proc:
        returncode = 0
        stdout = json.dumps(
            {"title": "Long", "duration": 601, "uploader": "x"}
        )
        stderr = ""

    monkeypatch.setattr(
        "novelvideo.freezone.video_reference._run_yt_dlp",
        lambda args, timeout: _Proc(),
    )
    with pytest.raises(VideoReferenceError, match="601 seconds"):
        fetch_video_metadata("https://www.youtube.com/watch?v=x")


def test_fetch_metadata_missing_ytdlp(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(VideoReferenceError, match="yt-dlp is not installed"):
        fetch_video_metadata("https://www.youtube.com/watch?v=x")


def test_orchestrator_youtube_path_uses_direct_link(monkeypatch) -> None:
    """YouTube path: no download, link straight to the video model."""
    import novelvideo.freezone.video_reference as vr

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key")
    monkeypatch.delenv("VIDEO_ANALYSIS_MODEL", raising=False)
    result = asyncio.run(
        vr.analyze_video_reference(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mode="idea",
            checklist=["hook"],
            extra_notes="focus on the intro",
        )
    )
    assert result["source"] == "direct_youtube"
    assert result["analysis"] == "Analysis ok."
    assert result["model"] == DEFAULT_VIDEO_ANALYSIS_MODEL
    assert result["fallback"] is None
    prompt = _FakeAsyncClient.seen["json"]["input"][0]["content"][0]["text"]
    assert "IDEA mode" in prompt
    assert "focus on the intro" in prompt


def test_orchestrator_requires_openrouter_key(monkeypatch) -> None:
    import novelvideo.freezone.video_reference as vr

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(VideoReferenceError, match="OPENROUTER_API_KEY"):
        asyncio.run(
            vr.analyze_video_reference(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            )
        )
