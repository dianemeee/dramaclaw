"""Factory automation: per-clip durations for text-to-image-video.

muse-video caps at 10s per clip, so a scene longer than 10s is split into
sequential chunks (10 + remainder), each chunk stating its own duration in
its prompt text and its duration parameter, with the narration split across
the chunks. No clip ever exceeds 10s.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from novelvideo.video_duration import video_duration_bounds_for_backend


def _load_catalog_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "novelvideo"
        / "freezone"
        / "agent_workflows"
        / "catalog.py"
    )
    spec = importlib.util.spec_from_file_location("test_factory_workflow_catalog", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def catalog(monkeypatch):
    module = _load_catalog_module()
    monkeypatch.setattr(module, "list_user_agent_config_items", None)
    return module


def _compile(catalog, units, **planner_extra):
    planner = {"mode": "standard", "item_count": len(units), "units": units}
    planner.update(planner_extra)
    result = catalog.compile_workflow_intent(
        {
            "skill_id": "text-to-image-video",
            "user_goal": "Lenteng Agung demolition story",
            "planner": planner,
        }
    )
    assert result["ok"] is True, result
    return result


def _video_nodes(result):
    return [
        node
        for node in result["plan"]["nodes"]
        if node.get("node_type") == "videoNode"
    ]


def _item_narration(node):
    return (
        node["data"]["workflowCatalog"]["promptBuilder"]["planItem"].get(
            "narration", ""
        )
    )


@pytest.mark.parametrize(
    "total,expected",
    [
        (3, [3]),
        (5, [5]),
        (9, [9]),
        (10, [10]),
        (11, [6, 5]),
        (12, [6, 6]),
        (15, [10, 5]),
        (21, [7, 7, 7]),
        (25, [10, 10, 5]),
        (26, [10, 10, 6]),
        (30, [10, 10, 10]),
    ],
)
def test_clip_durations_for_scene(total, expected):
    catalog = _load_catalog_module()
    assert catalog._clip_durations_for_scene(total) == expected


@pytest.mark.parametrize(
    "unit,expected",
    [
        ({"duration_seconds": 8}, 8),
        ({"duration_seconds": 15}, 15),
        ({"duration_seconds": 3}, 3),
        ({"narration": " ".join(["kata"] * 25)}, 10),
        ({"narration": " ".join(["kata"] * 13)}, 6),
        ({"narration": " ".join(["kata"] * 6)}, 3),
        ({"narration": ""}, 3),
    ],
)
def test_scene_clip_seconds(unit, expected):
    catalog = _load_catalog_module()
    assert catalog._scene_clip_seconds(unit) == expected


def test_split_narration_preserves_words():
    catalog = _load_catalog_module()
    narration = " ".join(f"kata{i}" for i in range(30))
    parts = catalog._split_narration(narration, [10, 5])
    assert " ".join(parts) == narration
    assert len(parts[0].split()) > len(parts[1].split())


def test_split_narration_prefers_sentence_boundary():
    catalog = _load_catalog_module()
    parts = catalog._split_narration(
        "Satu dua tiga. Empat lima enam tujuh delapan.", [5, 5]
    )
    assert parts == ["Satu dua tiga.", "Empat lima enam tujuh delapan."]


def test_clip_prompt_states_duration_and_narration():
    catalog = _load_catalog_module()
    prompt = catalog._clip_prompt_with_narration(
        "kampung scene", "Narasi di sini.", "id", 7
    )
    assert "7秒" in prompt
    assert "Narasi di sini." in prompt
    assert "Indonesian" in prompt
    assert "10秒" in prompt


def test_clip_prompt_without_narration_still_states_duration():
    catalog = _load_catalog_module()
    prompt = catalog._clip_prompt_with_narration("kampung scene", "", "id", 6)
    assert "6秒" in prompt
    assert "旁白" not in prompt
    assert catalog._clip_prompt_with_narration("kampung scene", "", "id") == (
        "kampung scene"
    )


def test_long_scene_splits_into_sequential_clips(catalog):
    narration = (
        "Di balik tembok besar ini, tanah yang mereka rawat puluhan tahun "
        "disebut tak bertuan, sementara warga kampung tetap bertahan menjaga "
        "rumah mereka setiap hari."
    )
    result = _compile(
        catalog,
        [
            {
                "title": "Tembok",
                "prompt": "kampung di Lenteng Agung",
                "narration": narration,
                "duration_seconds": 15,
            }
        ],
    )
    clips = _video_nodes(result)
    assert [node["id"] for node in clips] == ["clip_1", "clip_1_2"]
    assert [node["data"]["durationSec"] for node in clips] == [10, 5]
    assert "10秒" in clips[0]["data"]["prompt"]
    assert "5秒" in clips[1]["data"]["prompt"]
    joined = " ".join(_item_narration(node) for node in clips)
    assert joined == narration
    for node in clips:
        part = _item_narration(node)
        assert part and node["data"]["prompt"].endswith(f'"{part}"')
    assert _item_narration(clips[1]) not in clips[0]["data"]["prompt"]
    edges = result["plan"]["edges"]
    assert any(
        edge.get("source") == "clip_1" and edge.get("target") == "clip_1_2"
        for edge in edges
    )
    compose = next(
        node
        for node in result["plan"]["nodes"]
        if node.get("node_type") == "videoComposeNode"
    )
    assert compose["data"]["compositionInputOrder"] == ["clip_1", "clip_1_2"]


def test_short_scene_stays_one_clip(catalog):
    result = _compile(
        catalog,
        [
            {
                "title": "Singkat",
                "prompt": "warga bertanya",
                "narration": "Tiga juta mana cukup?",
            }
        ],
    )
    clips = _video_nodes(result)
    assert [node["id"] for node in clips] == ["clip_1"]
    assert clips[0]["data"]["durationSec"] == 3
    assert "3秒" in clips[0]["data"]["prompt"]


def test_no_clip_exceeds_ten_seconds(catalog):
    result = _compile(
        catalog,
        [
            {
                "title": f"Scene {index}",
                "prompt": f"scene {index}",
                "narration": " ".join(["kata"] * 25),
                "duration_seconds": duration,
            }
            for index, duration in enumerate([15, 25, 40], 1)
        ],
    )
    clips = _video_nodes(result)
    assert len(clips) == 2 + 3 + 4
    assert all(3 <= node["data"]["durationSec"] <= 10 for node in clips)


def test_narration_only_scene_duration_is_derived_and_split(catalog):
    result = _compile(
        catalog,
        [
            {
                "title": "Panjang",
                "prompt": "kampung digusur",
                "narration": " ".join(["kata"] * 40),
            }
        ],
    )
    clips = _video_nodes(result)
    assert [node["data"]["durationSec"] for node in clips] == [10, 6]


def test_split_chunks_each_consume_the_scene_frame(catalog):
    """Regression: every split chunk must be fed by its scene's frame.

    Before the fix, chunks after the first only depended on the previous
    chunk (dependency_for), so no media_input_for edge was emitted and the
    images→video stage check flagged them (clip_1_2, clip_2_2, ...).
    """
    result = _compile(
        catalog,
        [
            {
                "title": f"Scene {index}",
                "prompt": f"scene {index}",
                "narration": " ".join(["kata"] * 25),
                "duration_seconds": duration,
            }
            for index, duration in enumerate([15, 15, 20, 20], 1)
        ],
    )
    plan = result["plan"]
    assert catalog.skill_stage_blockers(
        "text-to-image-video", plan["nodes"], plan["edges"]
    ) == []
    edges = plan["edges"]
    for scene in range(1, 5):
        frame = f"frame_{scene}"
        chunks = [
            node["id"]
            for node in _video_nodes(result)
            if node["id"] == f"clip_{scene}"
            or node["id"].startswith(f"clip_{scene}_")
        ]
        assert chunks, f"scene {scene} has no clips"
        for chunk in chunks:
            assert any(
                edge.get("source") == frame
                and edge.get("target") == chunk
                and edge.get("link_type") == "media_input_for"
                for edge in edges
            ), f"{chunk} is not fed by {frame}"
    validated = catalog.validate_agent_workflow_plan(plan)
    assert validated["ok"] is True, validated
    assert validated["preflight"]["status"] == "ready"


def test_muse_video_duration_bounds_cap_at_ten_seconds():
    assert video_duration_bounds_for_backend("muse2api_muse-video") == (None, 10)
    assert video_duration_bounds_for_backend("huimeng_muse-video") == (None, 10)


def _raw_plan(catalog, result):
    import copy

    plan = copy.deepcopy(result["plan"])
    plan.pop("planner", None)
    plan.pop("layout", None)
    return plan


def test_compiled_plan_round_trips_through_template_reroute(catalog):
    # The planner-appended duration line must not break the template round
    # trip: the plan restates the template and is rerouted, not kept as
    # agent-authored.
    result = _compile(
        catalog,
        [
            {"title": "Satu", "prompt": "jalan kampung pagi", "narration": ""},
            {"title": "Dua", "prompt": "warga berkumpul", "narration": ""},
        ],
    )
    validated = catalog.validate_agent_workflow_plan(_raw_plan(catalog, result))
    assert validated["ok"] is True, validated
    assert validated["planner"]["mode"] == "deterministic_standard"
    assert validated["planner"]["selected_by"] == "template_isomorphic"


def test_narrated_plan_round_trips_through_template_reroute(catalog):
    # Same, with narration carried in the clip prompts and no speech nodes:
    # the narration line is recovered from the prompt on the round trip.
    result = _compile(
        catalog,
        [
            {
                "title": "Satu",
                "prompt": "jalan kampung pagi",
                "narration": "Di balik tembok besar ini, tanah mereka disebut tak bertuan.",
            },
            {
                "title": "Dua",
                "prompt": "warga berkumpul",
                "narration": "Mereka tetap bertahan menjaga rumah mereka.",
            },
        ],
    )
    validated = catalog.validate_agent_workflow_plan(_raw_plan(catalog, result))
    assert validated["ok"] is True, validated
    assert validated["planner"]["mode"] == "deterministic_standard"
    assert validated["planner"]["selected_by"] == "template_isomorphic"
