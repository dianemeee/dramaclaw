"""Regression tests: NewAPI video result downloads must authenticate.

The gateway's own result URLs (``/v1/videos/{task}/content``) require a
valid token, but ``download_to_path`` used to send no headers at all, so
every fetch failed 401 "Invalid token" and the poll loop retried it
forever with the node stuck at ~99%. The gateway key must be attached
only for URLs hosted by the gateway itself — never for public result
URLs, where it would leak the credential.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.m09


def _generator() -> "NewApiVideoGenerator":
    from novelvideo.generators.video_generator import NewApiVideoGenerator

    return NewApiVideoGenerator(
        api_key="gateway-key",
        endpoint="http://gateway.internal:3000",
    )


class _CapturingDownload:
    """Stand-in for download_to_path that records what it was given."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, url: str, output_path: str, **kwargs) -> object:
        from novelvideo.ports.video_delivery import VideoDeliveryReceipt

        self.calls.append({"url": url, "output_path": output_path, **kwargs})
        Path(output_path).write_bytes(b"video")
        return VideoDeliveryReceipt(
            method="download",
            size=len(b"video"),
            sha256=hashlib.sha256(b"video").hexdigest(),
        )


@pytest.mark.asyncio
async def test_gateway_result_url_download_sends_bearer_token(
    monkeypatch, tmp_path: Path
) -> None:
    from novelvideo.utils import media_download

    capture = _CapturingDownload()
    monkeypatch.setattr(media_download, "download_to_path", capture)
    generator = _generator()

    output = tmp_path / "video.mp4"
    await generator._download_video(
        "http://gateway.internal:3000/v1/videos/task-1/content",
        str(output),
    )

    assert len(capture.calls) == 1
    assert capture.calls[0]["headers"] == {"Authorization": "Bearer gateway-key"}


@pytest.mark.asyncio
async def test_localhost_result_url_is_resolved_to_gateway_and_authenticated(
    monkeypatch, tmp_path: Path
) -> None:
    from novelvideo.utils import media_download

    capture = _CapturingDownload()
    monkeypatch.setattr(media_download, "download_to_path", capture)
    generator = _generator()

    output = tmp_path / "video.mp4"
    await generator._download_video(
        "http://127.0.0.1:3000/v1/videos/task-1/content",
        str(output),
    )

    assert len(capture.calls) == 1
    assert (
        capture.calls[0]["url"]
        == "http://gateway.internal:3000/v1/videos/task-1/content"
    )
    assert capture.calls[0]["headers"] == {"Authorization": "Bearer gateway-key"}


@pytest.mark.asyncio
async def test_external_result_url_download_sends_no_credential(
    monkeypatch, tmp_path: Path
) -> None:
    from novelvideo.utils import media_download

    capture = _CapturingDownload()
    monkeypatch.setattr(media_download, "download_to_path", capture)
    generator = _generator()

    output = tmp_path / "video.mp4"
    await generator._download_video(
        "https://cdn.example/video.mp4",
        str(output),
    )

    assert len(capture.calls) == 1
    assert capture.calls[0]["url"] == "https://cdn.example/video.mp4"
    assert capture.calls[0]["headers"] is None


@pytest.mark.asyncio
async def test_gateway_download_without_api_key_sends_no_header(
    monkeypatch, tmp_path: Path
) -> None:
    from novelvideo.utils import media_download

    capture = _CapturingDownload()
    monkeypatch.setattr(media_download, "download_to_path", capture)
    generator = _generator()
    generator.api_key = ""

    output = tmp_path / "video.mp4"
    await generator._download_video(
        "http://gateway.internal:3000/v1/videos/task-1/content",
        str(output),
    )

    assert len(capture.calls) == 1
    assert capture.calls[0]["headers"] is None


class _HeaderCapturingResponse:
    def __init__(self, headers: dict | None) -> None:
        self.status = 200
        self.headers = headers
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def iter_chunked(self, _size: int):
        yield b"video"


class _HeaderCapturingSession:
    seen: list[dict] = []

    def __init__(self, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def get(self, url: str, headers: dict | None = None):
        _HeaderCapturingSession.seen.append({"url": url, "headers": headers})
        return _HeaderCapturingResponse(headers)


@pytest.mark.asyncio
async def test_download_to_path_forwards_headers_to_the_request(
    monkeypatch, tmp_path: Path
) -> None:
    from novelvideo.utils import media_download

    _HeaderCapturingSession.seen = []
    monkeypatch.setattr(
        media_download.aiohttp,
        "ClientSession",
        lambda **kwargs: _HeaderCapturingSession(**kwargs),
    )

    output = tmp_path / "video.mp4"
    await media_download.download_to_path(
        "http://gateway.internal:3000/v1/videos/task-1/content",
        str(output),
        headers={"Authorization": "Bearer gateway-key"},
    )

    assert output.read_bytes() == b"video"
    assert _HeaderCapturingSession.seen == [
        {
            "url": "http://gateway.internal:3000/v1/videos/task-1/content",
            "headers": {"Authorization": "Bearer gateway-key"},
        }
    ]
