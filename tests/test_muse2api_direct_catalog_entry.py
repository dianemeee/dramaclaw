"""Direct muse2api video entry in the CE video catalog.

The canvas video node picker lists only catalog models, and the CE video
catalog (built from the NewAPI model mappings, whose video apiModel is always
``"newapi_" + mapping key``) has no muse2api entry. The bypass backend
``muse2api_muse-video`` therefore needs a synthetic catalog entry with an
explicit apiModel, derived from the configured muse-video row, so the picker,
the resolve path, the backend resolution and the mode gate all see it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from novelvideo.api.routes import freezone as freezone_routes


def _muse_video_row(*, gateway_model: str = "muse-video") -> dict:
    """A built catalog entry as the CE mappings produce it for muse-video."""
    return {
        "catalogId": "muse-video",
        "catalog_id": "muse-video",
        "id": "muse-video",
        "providerId": "newapi",
        "provider": "newapi",
        "apiModel": "newapi_muse-video",
        "api_model": "newapi_muse-video",
        "gatewayModel": gateway_model,
        "gateway_model": gateway_model,
        "aliases": [],
        "label": "Muse Video",
        "sortOrder": 101,
        "request": {"endpoint": "video/generations", "parameters": []},
        "supportedModes": ["text_to_video", "image_to_video"],
    }


def _injected_catalog(*, gateway_model: str = "muse-video") -> list[dict]:
    return freezone_routes._with_muse2api_direct_video_entry(
        [_muse_video_row(gateway_model=gateway_model)]
    )


def test_direct_entry_derived_from_muse_video_row() -> None:
    catalog = _injected_catalog()

    assert len(catalog) == 2
    source, direct = catalog
    assert source["apiModel"] == "newapi_muse-video"
    assert direct["catalogId"] == "muse2api_muse-video"
    assert direct["id"] == "muse2api_muse-video"
    assert direct["apiModel"] == "muse2api_muse-video"
    assert direct["api_model"] == "muse2api_muse-video"
    assert direct["providerId"] == "muse2api"
    assert direct["provider"] == "muse2api"
    assert direct["gatewayModel"] == "muse-video"
    assert direct["gateway_model"] == "muse-video"
    assert direct["aliases"] == []
    assert direct["label"] == "Muse Video (direct)"
    assert direct["sortOrder"] == 101
    assert direct["request"] == {"endpoint": "video/generations", "parameters": []}
    assert direct["supportedModes"] == ["text_to_video", "image_to_video"]


def test_direct_entry_without_muse_video_row() -> None:
    catalog = [{"catalogId": "seedance-2.0", "apiModel": "newapi_seedance-2.0"}]

    assert freezone_routes._with_muse2api_direct_video_entry(catalog) == catalog


def test_direct_entry_not_duplicated() -> None:
    catalog = _injected_catalog()

    assert freezone_routes._with_muse2api_direct_video_entry(catalog) == catalog


def test_direct_entry_ignores_edited_gateway_model() -> None:
    """The row's gatewayModel is managed separately; it must not decide the entry."""
    catalog = _injected_catalog(gateway_model="muse2api_muse-video")

    assert len(catalog) == 2
    direct = catalog[1]
    assert direct["apiModel"] == "muse2api_muse-video"
    assert direct["gatewayModel"] == "muse-video"
    assert direct["gateway_model"] == "muse-video"


@pytest.mark.asyncio
async def test_ee_catalog_injects_direct_entry_in_ce_custom_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "novelvideo.shared.runtime_env.is_ce_effective", lambda: True
    )
    monkeypatch.setattr(
        "novelvideo.model_gateway_settings.get_effective_newapi_config",
        lambda: SimpleNamespace(mode="custom"),
    )
    monkeypatch.setattr(
        "novelvideo.model_gateway_settings.get_official_media_model_catalog",
        lambda media_type: [],
    )

    def fake_ce_catalog(media_type: str, **_kwargs) -> list[dict]:
        return [_muse_video_row()] if media_type == "video" else []

    monkeypatch.setattr(
        "novelvideo.model_gateway_settings.get_ce_media_model_catalog",
        fake_ce_catalog,
    )

    video_catalog = await freezone_routes._ee_media_model_catalog("video")
    assert video_catalog is not None
    direct = next(
        (
            item
            for item in video_catalog
            if str(item.get("apiModel") or "") == "muse2api_muse-video"
        ),
        None,
    )
    assert direct is not None
    assert direct["label"] == "Muse Video (direct)"

    image_catalog = await freezone_routes._ee_media_model_catalog("image")
    assert image_catalog == []


def _patch_scoped_catalog(
    monkeypatch: pytest.MonkeyPatch, catalog: list[dict]
) -> None:
    async def fake_catalog(
        media_type: str, *, requester_user_id: str
    ) -> list[dict] | None:
        return list(catalog) if media_type == "video" else None

    monkeypatch.setattr(
        freezone_routes, "_scoped_media_model_catalog", fake_catalog
    )


@pytest.mark.asyncio
async def test_picker_lists_direct_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_scoped_catalog(monkeypatch, _injected_catalog())

    data = await freezone_routes._freezone_video_models_data("user-1")

    direct = next(
        (
            item
            for item in data
            if str(item.get("apiModel") or "") == "muse2api_muse-video"
        ),
        None,
    )
    assert direct is not None
    assert direct["label"] == "Muse Video (direct)"
    assert direct["providerId"] == "muse2api"


@pytest.mark.asyncio
async def test_resolve_accepts_direct_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_scoped_catalog(monkeypatch, _injected_catalog())

    _schema, _values, entry = await freezone_routes._resolve_catalog_request(
        "video",
        "muse2api_muse-video",
        None,
        mode="image_to_video",
        requester_user_id="user-1",
    )

    assert entry is not None
    assert entry["apiModel"] == "muse2api_muse-video"


@pytest.mark.asyncio
async def test_resolve_rejects_unknown_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_scoped_catalog(monkeypatch, _injected_catalog())

    with pytest.raises(HTTPException) as exc:
        await freezone_routes._resolve_catalog_request(
            "video", "no-such-model", None, requester_user_id="user-1"
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_backend_resolves_to_bypass_not_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_scoped_catalog(monkeypatch, _injected_catalog())

    assert (
        await freezone_routes._resolve_catalog_video_backend(
            "muse2api_muse-video", requester_user_id="user-1"
        )
        == "muse2api_muse-video"
    )
    # The old selection keeps its gateway backend.
    assert (
        await freezone_routes._resolve_catalog_video_backend(
            "muse-video", requester_user_id="user-1"
        )
        == "newapi_muse-video"
    )


@pytest.mark.asyncio
async def test_mode_gate_passes_for_direct_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_scoped_catalog(monkeypatch, _injected_catalog())

    _schema, _values, entry = await freezone_routes._resolve_catalog_request(
        "video",
        "muse2api_muse-video",
        None,
        mode="image_to_video",
        requester_user_id="user-1",
    )

    freezone_routes._require_catalog_video_mode(entry, "image_to_video")
    freezone_routes._require_catalog_video_mode(entry, "text_to_video")
