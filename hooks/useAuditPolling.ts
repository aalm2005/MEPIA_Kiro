"use client";

import { useEffect, useRef, useState } from "react";
import type { OrchestratorResult, PipelineStatus } from "@/types/audit";

/**
 * Response from GET /api/audit/status/{run_id}
 * → proxied to GET /orchestrator/status/{run_id}
 */
interface StatusResponse {
  run_id: string;
  pipeline_status: PipelineStatus;
  current_node?: string;
  completed_at?: string;
}

/**
 * Response from GET /api/audit/layer3/status/{layer3_run_id}
 * → proxied to GET /api/audit/layer3/status/{layer3_run_id}
 */
interface Layer3StatusResponse {
  layer3_run_id: string;
  status: "running" | "completed" | "failed";
  draft_status?: "approved" | "approved_with_warning";
  current_node?: string;
  intentos_critico?: number;
  started_at?: string;
  completed_at?: string;
}

const TERMINAL_STATUSES: PipelineStatus[] = [
  "completed",
  "partial",
  "escalated",
  "failed",
];

interface UseAuditPollingResult {
  /** Full orchestrator result (available after pipeline reaches terminal status) */
  result: OrchestratorResult | null;
  /** Current pipeline status from polling */
  pipelineStatus: PipelineStatus | null;
  /** Current node being executed in the pipeline */
  currentNode: string | null;
  /** Layer 3 status (only when escalation triggered Layer 3) */
  layer3Status: "running" | "completed" | "failed" | null;
  /** Layer 3 draft status (approved / approved_with_warning) */
  layer3DraftStatus: string | null;
  /** Error message if any polling step fails */
  error: string | null;
}

/**
 * Hook for polling the audit pipeline status.
 *
 * Flow:
 *   1. Poll GET /api/audit/status/{runId} every intervalMs
 *   2. When pipeline reaches terminal status → fetch full result
 *   3. If escalation.triggered → start second polling to GET /api/audit/layer3/status/{layer3_run_id}
 *   4. Stop all polling when Layer 3 completes or fails
 *
 * Spec: tasks_backend.md §18.3
 */
export function useAuditPolling(
  runId: string | null,
  intervalMs: number = 2000
): UseAuditPollingResult {
  const [result, setResult] = useState<OrchestratorResult | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(
    null
  );
  const [currentNode, setCurrentNode] = useState<string | null>(null);
  const [layer3Status, setLayer3Status] = useState<
    "running" | "completed" | "failed" | null
  >(null);
  const [layer3DraftStatus, setLayer3DraftStatus] = useState<string | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);

  const mainIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const layer3IntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!runId) return;

    // Reset state when runId changes
    setResult(null);
    setPipelineStatus(null);
    setCurrentNode(null);
    setLayer3Status(null);
    setLayer3DraftStatus(null);
    setError(null);

    const clearMainInterval = () => {
      if (mainIntervalRef.current !== null) {
        clearInterval(mainIntervalRef.current);
        mainIntervalRef.current = null;
      }
    };

    const clearLayer3Interval = () => {
      if (layer3IntervalRef.current !== null) {
        clearInterval(layer3IntervalRef.current);
        layer3IntervalRef.current = null;
      }
    };

    /**
     * Fetch the full orchestrator result once pipeline reaches terminal status.
     * If escalated, start Layer 3 polling.
     */
    const fetchFinalResult = async () => {
      try {
        const res = await fetch(`/api/audit/result/${runId}`);
        if (!res.ok) {
          throw new Error(
            `Error fetching result: ${res.status} ${res.statusText}`
          );
        }
        const data: OrchestratorResult = await res.json();
        setResult(data);

        // If escalated → start Layer 3 polling using layer2_run_id
        // The backend triggers Layer 3 automatically when escalation happens
        if (
          data.escalation.triggered &&
          data.escalation.layer2_run_id !== null
        ) {
          const layer2RunId = data.escalation.layer2_run_id;

          const pollLayer3 = async () => {
            try {
              const l3Res = await fetch(
                `/api/audit/layer3/status/${layer2RunId}`
              );
              if (!l3Res.ok) {
                throw new Error(
                  `Error fetching Layer 3 status: ${l3Res.status} ${l3Res.statusText}`
                );
              }
              const l3Data: Layer3StatusResponse = await l3Res.json();
              setLayer3Status(l3Data.status);
              setLayer3DraftStatus(l3Data.draft_status ?? null);

              if (l3Data.current_node) {
                setCurrentNode(l3Data.current_node);
              }

              // Stop polling when Layer 3 reaches terminal status
              if (
                l3Data.status === "completed" ||
                l3Data.status === "failed"
              ) {
                clearLayer3Interval();
              }
            } catch (err) {
              setError(
                err instanceof Error
                  ? err.message
                  : "Error polling Layer 3 status"
              );
              clearLayer3Interval();
            }
          };

          // Poll immediately, then on interval
          await pollLayer3();
          layer3IntervalRef.current = setInterval(pollLayer3, intervalMs);
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Error fetching audit result"
        );
      }
    };

    /**
     * Main polling — polls orchestrator status until terminal.
     * Terminal statuses: completed, partial, escalated, failed
     */
    const pollStatus = async () => {
      try {
        const res = await fetch(`/api/audit/status/${runId}`);
        if (!res.ok) {
          throw new Error(
            `Error fetching status: ${res.status} ${res.statusText}`
          );
        }
        const data: StatusResponse = await res.json();

        setPipelineStatus(data.pipeline_status);
        setCurrentNode(data.current_node ?? null);

        if (TERMINAL_STATUSES.includes(data.pipeline_status)) {
          clearMainInterval();
          await fetchFinalResult();
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Error polling audit status"
        );
        clearMainInterval();
      }
    };

    // Kick off immediately, then on interval
    pollStatus();
    mainIntervalRef.current = setInterval(pollStatus, intervalMs);

    return () => {
      clearMainInterval();
      clearLayer3Interval();
    };
  }, [runId, intervalMs]);

  return {
    result,
    pipelineStatus,
    currentNode,
    layer3Status,
    layer3DraftStatus,
    error,
  };
}
