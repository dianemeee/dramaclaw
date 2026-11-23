"""Server-owned Freezone clarification payloads shared by API and MCP adapters."""

from __future__ import annotations

from typing import Any


#: User-facing copy for the constraint-adjustment question, keyed by director
#: language. ``resolve_director_language`` falls back to the
#: ``DRAMACLAW_UI_LANGUAGE`` env var (``en`` on Maria's server), then ``zh``.
_CONSTRAINT_ADJUSTMENT_TEXT = {
    "zh": {
        "title": "选择下一步",
        "prompt": (
            "当前没有视频模型能同时满足全部参考模式、镜头时长和生成参数。"
            "请选择是否调整一类约束。"
        ),
        "keep_requirements": ("保持当前要求并停止", "不修改当前 Plan，也不继续创建 Draft。"),
        "adjust_reference_mode": ("调整参考模式", "仅确认调整方向；提供具体新值前不修改参考边或媒体锚点。"),
        "adjust_shot_duration": ("调整镜头时长", "仅确认调整方向；提供具体新时长前不修改 Plan。"),
        "specify_video_model": ("重新指定模型", "由用户提供具体模型，再使用原约束重新执行 preflight。"),
    },
    "en": {
        "title": "Choose the next step",
        "prompt": (
            "No video model can satisfy all reference modes, shot durations, and "
            "generation parameters at the same time. Please choose whether to adjust "
            "one kind of constraint."
        ),
        "keep_requirements": (
            "Keep the current requirements and stop",
            "Do not modify the current plan, and do not continue creating a draft.",
        ),
        "adjust_reference_mode": (
            "Adjust the reference mode",
            "Only confirm the adjustment direction; reference edges or media anchors "
            "are not modified before a concrete new value is provided.",
        ),
        "adjust_shot_duration": (
            "Adjust the shot duration",
            "Only confirm the adjustment direction; the plan is not modified before "
            "a concrete new duration is provided.",
        ),
        "specify_video_model": (
            "Specify a different model",
            "The user provides a concrete model, then preflight runs again with the "
            "original constraints.",
        ),
    },
}


def video_model_constraint_adjustment_clarification(
    preflight: dict[str, Any] | None = None,
    language: object | None = None,
) -> dict[str, Any]:
    """Return the fixed user decision used when no video model fits all constraints."""
    from novelvideo.prompts.lang import resolve_director_language

    lang = resolve_director_language(language)
    text = _CONSTRAINT_ADJUSTMENT_TEXT.get(lang, _CONSTRAINT_ADJUSTMENT_TEXT["zh"])
    result = {
        "ok": True,
        "status": "video_model_clarification_required",
        "code": "no_compatible_video_model",
        "draft_created": False,
        "retryable": False,
        "required_choice": "video_model_constraint_adjustment",
        "next_action": "request_user_clarification",
        "question": {
            "id": "video_model_constraint_adjustment",
            "title": text["title"],
            "prompt": text["prompt"],
            "mode": "single",
            "options": [
                {
                    "id": option_id,
                    "label": text[option_id][0],
                    "description": text[option_id][1],
                }
                for option_id in (
                    "keep_requirements",
                    "adjust_reference_mode",
                    "adjust_shot_duration",
                    "specify_video_model",
                )
            ],
        },
    }
    if preflight is not None:
        result["preflight"] = preflight
    return result
