// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import type { CanvasChatCommandApplyResult } from '@/features/canvas/core/commands/types';

export const CANVAS_COMMAND_VALIDATION_FAILURE_MESSAGE = "画布命令预校验失败，前端未展示确认卡，也未执行。";

export function canvasCommandValidationFailureResult(
  errors: string[],
  translate?: (key: string) => string,
): CanvasChatCommandApplyResult {
  // Keep the zh fallback as the literal `label:` value: the server parity
  // test (server-apply-commands) extracts it from this file by regex.
  const result: CanvasChatCommandApplyResult = {
    applied: 0,
    openedUiActions: 0,
    createdNodeIds: [],
    errors,
    commandResults: [
      {
        commandIndex: -1,
        type: "validate",
        status: "error",
        label: "校验画布命令",
        error: errors.join("; "),
      },
    ],
  };
  const translated = translate?.("canvas.command.validate");
  if (translated && translated !== "canvas.command.validate") {
    result.commandResults[0].label = translated;
  }
  return result;
}
