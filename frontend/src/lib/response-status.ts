import type { ScoreResponse } from "@/lib/types";

const ACTIVE_PROCESSING_STATES = new Set<ScoreResponse["processing_state"]>([
  "QUEUED",
  "RUNNING",
  "SCORING",
]);

export function responseNeedsProcessing(response: ScoreResponse): boolean {
  if (response.processing_state === "FAILED") return false;
  return (
    ACTIVE_PROCESSING_STATES.has(response.processing_state) ||
    Boolean(response.resolution_pending) ||
    Boolean(response.scores_stale)
  );
}
