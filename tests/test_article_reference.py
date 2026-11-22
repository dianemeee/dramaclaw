"""Tests for reference-article analysis (Freezone + Series).

Covers only the parts that can be checked without provider keys or
network access: HTML-to-text extraction, mode/checklist normalisation,
truncation, prompt building, and language resolution. Live article
fetches and real text-model calls are NOT tested here — they need
network and keys, and are verified live after deploy.
"""

from __future__ import annotations

import os

import pytest

from novelvideo.freezone.article_reference import (
    MAX_ARTICLE_REFERENCE_CHARS,
    MIN_ARTICLE_REFERENCE_CHARS,
    ArticleReferenceError,
    build_article_reference_prompt,
    extract_article_text,
    normalize_article_reference_checklist,
    normalize_article_reference_mode,
    resolve_director_language,
    truncate_article_text,
)


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
    assert normalize_article_reference_mode(raw) == expected


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        (["hook", "characters"], ("hook", "characters")),
        (["characters", "hook"], ("hook", "characters")),
        (["hook", "hook", "bogus"], ("hook",)),
        ([], ()),
        (None, ()),
        (["camera"], ("camera",)),
    ],
)
def test_normalize_checklist(items, expected) -> None:
    assert normalize_article_reference_checklist(items) == expected


def test_extract_article_text_prefers_article_tag() -> None:
    html = """
    <html><head><title>Test</title></head><body>
    <nav><p>Menu item one two three</p></nav>
    <article>
      <h1>The Spill</h1>
      <p>""" + "Mei spilled the wine. " * 40 + """</p>
      <p>""" + "Daniel did not shout. " * 40 + """</p>
    </article>
    <footer><p>Copyright notice here</p></footer>
    <script>var x = 1;</script>
    </body></html>
    """
    text = extract_article_text(html)
    assert "The Spill" in text
    assert "Mei spilled the wine" in text
    assert "Menu item" not in text
    assert "Copyright notice" not in text
    assert "var x" not in text


def test_extract_article_text_skips_script_and_style() -> None:
    html = (
        "<html><body><style>.a{color:red}</style>"
        "<p>" + "Real article sentence. " * 30 + "</p>"
        "<script>tracking_code()</script></body></html>"
    )
    text = extract_article_text(html)
    assert "Real article sentence" in text
    assert "color:red" not in text
    assert "tracking_code" not in text


def test_extract_article_text_empty() -> None:
    assert extract_article_text("") == ""
    assert extract_article_text("<html><body></body></html>") == ""


def test_truncate_article_text_short_unchanged() -> None:
    text, truncated = truncate_article_text("Short article.")
    assert text == "Short article."
    assert truncated is False


def test_truncate_article_text_long() -> None:
    long_text = "word " * 20000
    text, truncated = truncate_article_text(long_text)
    assert truncated is True
    assert len(text) <= MAX_ARTICLE_REFERENCE_CHARS
    assert len(text) > MAX_ARTICLE_REFERENCE_CHARS - 600


def test_build_prompt_duplicate_mode() -> None:
    prompt = build_article_reference_prompt(
        mode="duplicate",
        article_text="A short story about a waitress.",
        language="en",
    )
    assert "DUPLICATE mode" in prompt
    assert "Premise" in prompt
    assert "Main conflict" in prompt
    assert "Key events / twists" in prompt
    assert "A short story about a waitress." in prompt
    assert "Reply in English." in prompt


def test_build_prompt_reference_mode_idea_angles() -> None:
    prompt = build_article_reference_prompt(
        mode="idea",
        article_text="Some article.",
        language="en",
    )
    assert "IDEA mode" in prompt
    assert "3 fresh angles" in prompt


def test_build_prompt_checklist_limits_aspects() -> None:
    prompt = build_article_reference_prompt(
        mode="reference",
        checklist=("hook", "characters"),
        article_text="Some article.",
        language="en",
    )
    assert "Hook" in prompt
    assert "Characters" in prompt
    assert "Pacing" not in prompt


def test_build_prompt_extra_notes_is_own_story() -> None:
    prompt = build_article_reference_prompt(
        mode="reference",
        extra_notes="My story is about Mei, a waitress.",
        article_text="Some article.",
        language="en",
    )
    assert "My story is about Mei" in prompt
    assert "OWN story" in prompt
    assert "do not replace her story" in prompt


def test_build_prompt_truncation_note() -> None:
    prompt = build_article_reference_prompt(
        mode="reference",
        article_text="Some article.",
        language="en",
        truncated=True,
    )
    assert "truncated" in prompt


def test_build_prompt_indonesian() -> None:
    prompt = build_article_reference_prompt(
        mode="reference",
        article_text="Sebuah artikel.",
        language="id",
    )
    assert "Bahasa Indonesia" in prompt
    assert "Sebuah artikel." in prompt


def test_resolve_director_language(monkeypatch) -> None:
    monkeypatch.setenv("DRAMACLAW_UI_LANGUAGE", "id")
    assert resolve_director_language() == "id"
    monkeypatch.setenv("DRAMACLAW_UI_LANGUAGE", "en")
    assert resolve_director_language() == "en"
    monkeypatch.delenv("DRAMACLAW_UI_LANGUAGE", raising=False)
    assert resolve_director_language() == "en"


def test_analyze_requires_url_or_text() -> None:
    import asyncio

    from novelvideo.freezone.article_reference import analyze_article_reference

    with pytest.raises(ArticleReferenceError):
        asyncio.run(
            analyze_article_reference(article_url=None, article_text=None)
        )


def test_min_chars_constant_sane() -> None:
    assert 0 < MIN_ARTICLE_REFERENCE_CHARS < MAX_ARTICLE_REFERENCE_CHARS
    assert MAX_ARTICLE_REFERENCE_CHARS == 20000
