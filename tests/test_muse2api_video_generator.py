"""Direct muse2api video generator tests (mocked HTTP, no live calls).

The bypass talks straight to muse2api — POST ``/v1/videos`` then poll
GET ``/v1/videos/{task_id}`` — instead of the NewAPI gateway poller that
stalled at 99% while muse2api itself completed the video. These tests pin
the submit payload, the ``completed`` status handling (including the
``video.url`` / ``result.url`` fallbacks), the usage-meter
reserve/confirm/refund flow, and that the credential is only attached to
muse2api-hosted download URLs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RELAY_URL = "https://relay.example/frame.jpg"
MEDIA_URL = "https://muse.sukablyat.my.id/v1/media/abc123.mp4"


class _FakeResponse:
    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)


class _FakeSession:
    """Scripted aiohttp session shared across instances via ``script``."""

    def __init__(self, script: list[_FakeResponse]) -> None:
        self._script = script
        self.calls: list[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        self.calls.append(("POST", url, json, headers))
        return self._script.pop(0)

    def get(self, url, headers=None):
        self.calls.append(("GET", url, headers))
        return self._script.pop(0)


@pytest.fixture
def _muse2api_env(monkeypatch):
    monkeypatch.setenv("MUSE2API_KEY", "test-muse2api-key")
    monkeypatch.delenv("MUSE2API_BASE_URL", raising=False)
    from novelvideo.generators import video_generator as vg

    sessions: list[_FakeSession] = []

    def factory(*args, **kwargs):
        session = _FakeSession(factory.script)
        sessions.append(session)
        return session

    factory.script: list[_FakeResponse] = []
    factory.sessions = sessions
    monkeypatch.setattr(vg.aiohttp, "ClientSession", factory)

    async def _fake_relay(cls, image_value, **kwargs):
        return RELAY_URL

    monkeypatch.setattr(
        vg.NewApiVideoGenerator,
        "_relay_frame_input",
        classmethod(_fake_relay),
    )

    calls: dict[str, list] = {"reserve": [], "confirm": [], "refund": []}

    async def _reserve(model, **kwargs):
        calls["reserve"].append((model, kwargs))
        return "reservation-1"

    async def _confirm(**kwargs):
        calls["confirm"].append(kwargs)

    async def _refund(reservation_id, **kwargs):
        calls["refund"].append((reservation_id, kwargs))

    monkeypatch.setattr(vg, "_reserve_video_model_call", _reserve)
    monkeypatch.setattr(vg, "_confirm_video_model_call", _confirm)
    monkeypatch.setattr(vg, "_refund_video_model_call", _refund)

    async def _fake_download(url, output_path, headers=None):
        Path(output_path).write_bytes(b"video-bytes")
        return None

    from novelvideo.utils import media_download

    monkeypatch.setattr(media_download, "download_to_path", _fake_download)
    return factory, calls


def _generator():
    from novelvideo.generators.video_generator import Muse2ApiVideoGenerator

    return Muse2ApiVideoGenerator(api_key="test-muse2api-key")


def _all_calls(factory):
    return [call for session in factory.sessions for call in session.calls]


async def test_submit_poll_download_happy_path(_muse2api_env, tmp_path: Path) -> None:
    factory, calls = _muse2api_env
    factory.script.extend(
        [
            _FakeResponse(200, {"task_id": "task_1", "status": "queued"}),
            _FakeResponse(200, {"status": "processing", "progress": 15}),
            _FakeResponse(200, {"status": "completed", "url": MEDIA_URL}),
        ]
    )
    output = tmp_path / "video.mp4"
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"fake-png")
    result = await _generator().generate(
        image_path=str(frame),
        prompt="character walks forward",
        output_path=str(output),
        aspect_ratio="9:16",
        duration=5,
        poll_interval=0,
    )

    assert result.status.value == "done"
    assert result.task_id == "task_1"
    assert result.video_url == MEDIA_URL
    assert output.read_bytes() == b"video-bytes"
    submit = _all_calls(factory)[0]
    assert submit[0] == "POST"
    assert submit[1] == "https://muse.sukablyat.my.id/v1/videos"
    assert submit[2] == {
        "model": "muse-video",
        "prompt": "character walks forward",
        "image": RELAY_URL,
        "duration": 5,
        "aspect_ratio": "9:16",
        "resolution": "720p",
    }
    assert submit[3]["Authorization"] == "Bearer test-muse2api-key"
    assert calls["reserve"] == [
        (
            "muse-video",
            {
                "source": "muse2api_video_generation",
                "resolution": "720p",
                "duration_seconds": 5,
            },
        )
    ]
    assert len(calls["confirm"]) == 1
    assert calls["refund"] == []


async def test_completed_url_falls_back_to_result_url(
    _muse2api_env, tmp_path: Path
) -> None:
    factory, _calls = _muse2api_env
    factory.script.extend(
        [
            _FakeResponse(200, {"id": "task_2"}),
            _FakeResponse(200, {"status": "completed", "result": {"url": MEDIA_URL}}),
        ]
    )
    output = tmp_path / "video.mp4"
    result = await _generator().generate(
        image_path="https://example.com/frame.jpg",
        prompt="pan left",
        output_path=str(output),
        duration=5,
        poll_interval=0,
    )

    assert result.status.value == "done"
    assert result.task_id == "task_2"
    assert result.video_url == MEDIA_URL


async def test_submit_failure_refunds_reservation(
    _muse2api_env, tmp_path: Path
) -> None:
    factory, calls = _muse2api_env
    factory.script.append(_FakeResponse(500, {"error": "boom"}))
    result = await _generator().generate(
        image_path="https://example.com/frame.jpg",
        prompt="pan left",
        output_path=str(tmp_path / "video.mp4"),
        duration=5,
        poll_interval=0,
    )

    assert result.status.value == "failed"
    assert "500" in (result.error or "")
    assert len(calls["refund"]) == 1
    assert calls["confirm"] == []


async def test_failed_poll_status_refunds_reservation(
    _muse2api_env, tmp_path: Path
) -> None:
    factory, calls = _muse2api_env
    factory.script.extend(
        [
            _FakeResponse(200, {"task_id": "task_3"}),
            _FakeResponse(200, {"status": "failed", "error": "upstream broke"}),
        ]
    )
    result = await _generator().generate(
        image_path="https://example.com/frame.jpg",
        prompt="pan left",
        output_path=str(tmp_path / "video.mp4"),
        duration=5,
        poll_interval=0,
    )

    assert result.status.value == "failed"
    assert len(calls["refund"]) == 1
    assert calls["confirm"] == []


async def test_poll_timeout_refunds_reservation(
    _muse2api_env, tmp_path: Path
) -> None:
    factory, calls = _muse2api_env
    factory.script.extend(
        [
            _FakeResponse(200, {"task_id": "task_4"}),
            _FakeResponse(200, {"status": "processing"}),
        ]
    )
    result = await _generator().generate(
        image_path="https://example.com/frame.jpg",
        prompt="pan left",
        output_path=str(tmp_path / "video.mp4"),
        duration=5,
        poll_interval=0,
        max_polls=1,
    )

    assert result.status.value == "failed"
    assert "timeout" in (result.error or "").lower()
    assert len(calls["refund"]) == 1


def test_missing_api_key_raises(monkeypatch) -> None:
    from novelvideo.generators.video_generator import Muse2ApiVideoGenerator

    monkeypatch.delenv("MUSE2API_KEY", raising=False)
    with pytest.raises(ValueError, match="MUSE2API_KEY"):
        Muse2ApiVideoGenerator()


def test_wiring_and_duration_bounds(monkeypatch) -> None:
    monkeypatch.setenv("MUSE2API_KEY", "test-muse2api-key")
    from novelvideo.generators.video_generator import (
        Muse2ApiVideoGenerator,
        create_video_generator,
        muse2api_video_backend_options,
        parse_muse2api_video_backend,
    )
    from novelvideo.video_duration import (
        normalize_video_duration_for_backend,
        video_duration_bounds_for_backend,
    )

    assert parse_muse2api_video_backend("muse2api_muse-video") == "muse-video"
    assert parse_muse2api_video_backend("muse2api") == "muse-video"
    assert parse_muse2api_video_backend("newapi_seedance-2.0-fast") is None
    assert "muse2api_muse-video" in muse2api_video_backend_options()

    generator = create_video_generator("muse2api_muse-video", api_key="k")
    assert isinstance(generator, Muse2ApiVideoGenerator)
    assert generator.model == "muse-video"
    assert generator.endpoint == "https://muse.sukablyat.my.id/v1"

    # The default bounds are unbounded, so the 5s workflow duration passes
    # through unclamped (muse2api has no duration contract of its own).
    assert video_duration_bounds_for_backend("muse2api_muse-video") == (None, None)
    assert normalize_video_duration_for_backend("muse2api_muse-video", 5) == 5


async def test_download_bearer_only_for_muse2api_host(
    monkeypatch, tmp_path: Path
) -> None:
    from novelvideo.utils import media_download

    seen: list[dict] = []

    async def _capture_download(url, output_path, headers=None):
        seen.append({"url": url, "headers": headers})
        Path(output_path).write_bytes(b"video-bytes")

    monkeypatch.setattr(media_download, "download_to_path", _capture_download)
    generator = _generator()
    output = tmp_path / "video.mp4"

    await generator._download_video(MEDIA_URL, str(output))
    await generator._download_video("https://cdn.example/video.mp4", str(output))

    assert seen[0]["headers"] == {"Authorization": "Bearer test-muse2api-key"}
    assert seen[1]["headers"] is None


def _egress_context(kind: str = "organization"):
    """Trusted egress context mirroring tests/test_p0g4c_video_egress.py."""
    from novelvideo.egress_context import TrustedEgressContext
    from novelvideo.ports.authz import BillingPrincipal
    from novelvideo.ports.model_credentials import CredentialReference

    principal_id = {
        "organization": "org-1",
        "platform": "user-1",
        "local": "local-worker",
    }[kind]
    return TrustedEgressContext(
        envelope_id="envelope-1",
        project_id="project-1",
        task_type="single_video",
        requester_user_id="user-1",
        root_task_id="root-1",
        admission_id="admission-1",
        admitted_at="2026-08-03T04:05:00Z",
        membership_id="membership-1" if kind == "organization" else None,
        authz_version=11,
        billing_principal=BillingPrincipal(kind=kind, id=principal_id),
        credential=CredentialReference(
            source=kind,
            credential_id={
                "organization": "credential-1",
                "platform": "platform-newapi",
                "local": "local-video",
            }[kind],
            key_version=7 if kind == "organization" else 1,
            org_id="org-1" if kind == "organization" else None,
        ),
    )


def test_create_muse2api_allows_organization_and_local_context(monkeypatch) -> None:
    """CE exemption: org/local egress context must not block the direct branch."""
    monkeypatch.setenv("MUSE2API_KEY", "test-muse2api-key")
    from novelvideo.generators.video_generator import (
        Muse2ApiVideoGenerator,
        create_video_generator,
    )

    for kind in ("organization", "local"):
        generator = create_video_generator(
            "muse2api_muse-video",
            api_key="test-muse2api-key",
            egress_context=_egress_context(kind),
        )
        assert isinstance(generator, Muse2ApiVideoGenerator)


def test_create_muse2api_allows_ambient_organization_context(monkeypatch) -> None:
    """Same exemption when the context is bound only by the request scope."""
    monkeypatch.setenv("MUSE2API_KEY", "test-muse2api-key")
    from novelvideo.generators.video_generator import (
        Muse2ApiVideoGenerator,
        create_video_generator,
    )
    from novelvideo.model_gateway_runtime import model_gateway_request_scope

    for kind in ("organization", "local"):
        with model_gateway_request_scope(_egress_context(kind)):
            generator = create_video_generator(
                "muse2api_muse-video", api_key="test-muse2api-key"
            )
        assert isinstance(generator, Muse2ApiVideoGenerator)


def test_create_huimeng_still_denies_organization_context() -> None:
    """The exemption is muse2api-only: huimeng direct still raises."""
    from novelvideo.generators.video_generator import (
        VideoEgressError,
        create_video_generator,
    )

    for kind in ("organization", "local"):
        with pytest.raises(VideoEgressError) as exc_info:
            create_video_generator(
                "huimeng_seedance-1.0-pro-fast",
                egress_context=_egress_context(kind),
                client=object(),
            )
        assert exc_info.value.code == "ORG_EGRESS_DENIED"


async def test_generate_muse2api_allows_organization_context(
    _muse2api_env, tmp_path: Path
) -> None:
    """The generate()-level gate is exempted too, for both explicit and ambient context."""
    from novelvideo.model_gateway_runtime import model_gateway_request_scope

    factory, _calls = _muse2api_env
    factory.script.extend(
        [
            _FakeResponse(200, {"task_id": "task_egress", "status": "queued"}),
            _FakeResponse(200, {"status": "completed", "url": MEDIA_URL}),
        ]
    )
    result = await _generator().generate(
        image_path="https://example.com/frame.jpg",
        prompt="pan left",
        output_path=str(tmp_path / "video.mp4"),
        duration=5,
        poll_interval=0,
        egress_context=_egress_context("organization"),
    )
    assert result.status.value == "done"
    assert result.task_id == "task_egress"

    # Ambient-bound local context (no explicit kwarg) must not block either.
    factory.script.extend(
        [
            _FakeResponse(200, {"task_id": "task_egress_2", "status": "queued"}),
            _FakeResponse(200, {"status": "completed", "url": MEDIA_URL}),
        ]
    )
    with model_gateway_request_scope(_egress_context("local")):
        result = await _generator().generate(
            image_path="https://example.com/frame.jpg",
            prompt="pan left",
            output_path=str(tmp_path / "video2.mp4"),
            duration=5,
            poll_interval=0,
        )
    assert result.status.value == "done"
    assert result.task_id == "task_egress_2"


RELATIVE_MEDIA_URL = "/v1/media/abc123.mp4"


async def test_relative_result_url_resolved_to_absolute(
    _muse2api_env, monkeypatch, tmp_path: Path
) -> None:
    """A relative muse2api result URL is joined against the endpoint.

    muse2api returns ``/v1/media/<name>.mp4`` when its public_base is
    unset; the downloader must be called with the absolute URL, and the
    Bearer header must be attached (same-host URL).
    """
    from novelvideo.utils import media_download

    factory, _calls = _muse2api_env
    seen: list[dict] = []

    async def _capture_download(url, output_path, headers=None):
        seen.append({"url": url, "headers": headers})
        Path(output_path).write_bytes(b"video-bytes")

    monkeypatch.setattr(media_download, "download_to_path", _capture_download)
    factory.script.extend(
        [
            _FakeResponse(200, {"task_id": "task_rel", "status": "queued"}),
            _FakeResponse(200, {"status": "completed", "url": RELATIVE_MEDIA_URL}),
        ]
    )
    output = tmp_path / "video.mp4"
    result = await _generator().generate(
        image_path="https://example.com/frame.jpg",
        prompt="pan left",
        output_path=str(output),
        duration=5,
        poll_interval=0,
    )

    assert result.status.value == "done"
    assert result.video_url == MEDIA_URL
    assert seen == [
        {
            "url": MEDIA_URL,
            "headers": {"Authorization": "Bearer test-muse2api-key"},
        }
    ]


async def test_absolute_result_url_passes_through_unchanged(
    _muse2api_env, monkeypatch, tmp_path: Path
) -> None:
    """An already-absolute result URL is downloaded exactly as returned."""
    from novelvideo.utils import media_download

    factory, _calls = _muse2api_env
    seen: list[dict] = []

    async def _capture_download(url, output_path, headers=None):
        seen.append({"url": url, "headers": headers})
        Path(output_path).write_bytes(b"video-bytes")

    monkeypatch.setattr(media_download, "download_to_path", _capture_download)
    factory.script.extend(
        [
            _FakeResponse(200, {"task_id": "task_abs", "status": "queued"}),
            _FakeResponse(200, {"status": "completed", "url": MEDIA_URL}),
        ]
    )
    result = await _generator().generate(
        image_path="https://example.com/frame.jpg",
        prompt="pan left",
        output_path=str(tmp_path / "video.mp4"),
        duration=5,
        poll_interval=0,
    )

    assert result.status.value == "done"
    assert result.video_url == MEDIA_URL
    assert seen[0]["url"] == MEDIA_URL


async def test_failed_download_error_names_the_url(
    _muse2api_env, monkeypatch, tmp_path: Path
) -> None:
    """A download failure names the (resolved) URL so it is diagnosable."""
    from novelvideo.utils import media_download

    factory, _calls = _muse2api_env

    async def _failing_download(url, output_path, headers=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(media_download, "download_to_path", _failing_download)
    factory.script.extend(
        [
            _FakeResponse(200, {"task_id": "task_dl_fail", "status": "queued"}),
            _FakeResponse(200, {"status": "completed", "url": RELATIVE_MEDIA_URL}),
        ]
    )
    result = await _generator().generate(
        image_path="https://example.com/frame.jpg",
        prompt="pan left",
        output_path=str(tmp_path / "video.mp4"),
        duration=5,
        poll_interval=0,
    )

    assert result.status.value == "failed"
    assert MEDIA_URL in (result.error or "")
    assert "Download failed" in (result.error or "")
