// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { WORKFLOW_STABLE_CONTRACT } from "@/features/freezone/generated/workflowContract";
import type { ModelOption } from "@/features/canvas/domain/modelOptions";
import { isMuse2ApiDirectVideoModel } from "@/features/canvas/nodes/shared/videoModelCapabilities";

const videoAliases: Readonly<Record<string, string>> =
  WORKFLOW_STABLE_CONTRACT.model_aliases_by_node_type.videoNode;

/**
 * A node with no stored model choice defaults to the direct muse2api model
 * when it is configured: the direct route is the working path for
 * muse-video (the gateway route stalls), and Maria had to switch the picker
 * on every node by hand. Without a direct entry the first catalog model is
 * still the default, so setups without muse2api are unchanged.
 */
function preferDirectVideoModel(
  models: readonly ModelOption[],
): ModelOption | undefined {
  return models.find((model) =>
    isMuse2ApiDirectVideoModel(model.id) ||
    isMuse2ApiDirectVideoModel(model.apiModel),
  );
}

/** Preserve catalog identity first; resolve legacy workflow aliases only when unambiguous. */
export function selectVideoModel(
  models: readonly ModelOption[],
  persistedModel: unknown,
): ModelOption | undefined {
  const requested = typeof persistedModel === "string" ? persistedModel.trim() : "";
  if (!requested) return preferDirectVideoModel(models) ?? models[0];

  const exact = models.find((model) => model.id === requested || model.catalogId === requested);
  if (exact) return exact;

  const canonical = videoAliases[requested];
  if (!canonical) return preferDirectVideoModel(models) ?? models[0];
  const matches = models.filter((model) =>
    videoAliases[model.id] === canonical ||
    model.apiModel === canonical ||
    videoAliases[model.apiModel] === canonical,
  );
  // A model name cannot choose between multiple configured provider routes.
  return matches.length > 1 ? undefined : matches[0] ?? preferDirectVideoModel(models) ?? models[0];
}
