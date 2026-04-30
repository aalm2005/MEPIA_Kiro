"use client";

import { useEffect, useRef, useState } from "react";
import type { OrchestratorResult, PipelineStatus } from "@/types/audit";

interface StatusResponse {
  pipeline_status: PipelineStatus;
  current_node?: string;
}

interface Layer2StatusResponse {
  status: "running" | "completed" | "failed";
}

const TERMINAL_STATUSES: PipelineStatus[] = [
  "completed",
  "partial",
  "escalated",
  "failed",
];

interface UseAuditPollingResult {
  result: OrchestratorResult | null;
  pipelineStatus: PipelineStatus | null;
  currentNode: string | null;
  layer2Status: "running" | "completed" | "failed" | null;
  error: string | null;
}

export function useAuditPolling(
  runId: string | null,
  intervalMs: number = 2000
): UseAuditPollingResult {
  const [result, setResult] = useState<OrchestratorResult | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(
    null
  );
  const [currentNode, setCurrentNode] = useState<string | null>(null);
  const [layer2Status, setLayer2Status] = useState<
    "running" | "completed" | "failed" | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  // Refs to hold interval IDs so cleanup always has the latest values
  const mainIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const layer2IntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    // Nothing to do without a runId
    if (!runId) return;

    // Reset state when runId changes
    setResult(null);
    setPipelineStatus(null);
    setCurrentNode(null);
    setLayer2Status(null);
    setError(null);

    const clearMainInterval = () => {
      if (mainIntervalRef.current !== null) {
        clearInterval(mainIntervalRef.current);
        mainIntervalRef.current = null;
      }
    };

    const clearLayer2Interval = () => {
      if (layer2IntervalRef.current !== null) {
        clearInterval(layer2IntervalRef.current);
        layer2IntervalRef.current = null;
      }
    };

    /**
     * Fetch the full orchestrator result and, if escalated, start Layer 2 polling.
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

        // Start Layer 2 polling if the run was escalated
        if (
          data.escalation.triggered &&
          data.escalation.layer2_run_id !== null
        ) {
          const layer2RunId = data.escalation.layer2_run_id;

          const pollLayer2 = async () => {
            try {
              const l2Res = await fetch(
                `/api/audit/layer3/status/${layer2RunId}`
              );
              if (!l2Res.ok) {
                throw new Error(
                  `Error fetching Layer 2 status: ${l2Res.status} ${l2Res.statusText}`
                );
              }
              const l2Data: Layer2StatusResponse = await l2Res.json();
              setLayer2Status(l2Data.status);

              if (
                l2Data.status === "completed" ||
                l2Data.status === "failed"
              ) {
                clearLayer2Interval();
              }
            } catch (err) {
              setError(
                err instanceof Error
                  ? err.message
                  : "Error polling Layer 2 status"
              );
              clearLayer2Interval();
            }
          };

          // Poll immediately, then on interval
          await pollLayer2();
          layer2IntervalRef.current = setInterval(pollLayer2, intervalMs);
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Error fetching audit result"
        );
      }
    };

    /**
     * Main polling function — polls pipeline status and stops when terminal.
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
      clearLayer2Interval();
    };
  }, [runId, intervalMs]);

  return { result, pipelineStatus, currentNode, layer2Status, error };
}
