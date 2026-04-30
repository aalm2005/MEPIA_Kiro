"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useAuditPolling } from "@/hooks/useAuditPolling";
import { AuditHeader } from "@/components/dashboard/AuditHeader";
import { PipelineStatusBar } from "@/components/dashboard/PipelineStatusBar";
import { Layer2Banner } from "@/components/dashboard/Layer2Banner";
import { ForensicSummary } from "@/components/dashboard/ForensicSummary";
import { DormantMetricsList } from "@/components/dashboard/DormantMetricsList";
import AuditTable from "@/components/AuditTable";

function DashboardContent() {
  const searchParams = useSearchParams();
  const runId = searchParams.get("run_id");

  const { result, pipelineStatus, currentNode, layer2Status, error } =
    useAuditPolling(runId);

  const riskLevel =
    result?.sequential_results.forensic_report.risk_level ?? "low";
  const date = result?.date;
  const isEscalated = result?.escalation.triggered === true;

  return (
    <div className="min-h-screen bg-zinc-900 px-6 py-10 max-w-6xl mx-auto">
      {/* AuditHeader — full width */}
      <div className="mb-4">
        <AuditHeader riskLevel={riskLevel} date={date} />
      </div>

      {/* PipelineStatusBar — full width */}
      <div className="mb-4">
        <PipelineStatusBar
          status={pipelineStatus ?? "idle"}
          currentNode={currentNode ?? undefined}
          layer2Status={layer2Status ?? undefined}
        />
      </div>

      {/* Layer2Banner — conditional */}
      {isEscalated && layer2Status && (
        <div className="mb-4">
          <Layer2Banner layer2Status={layer2Status} />
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="mb-4 bg-red-950/30 border border-red-700 text-red-400 rounded p-4 text-sm font-mono">
          {error}
        </div>
      )}

      {/* Loading state */}
      {pipelineStatus === null && !error && (
        <p className="text-muted text-sm mb-4">Iniciando análisis...</p>
      )}

      {/* Main layout: 65% table | 35% side panel */}
      <div className="flex gap-6 items-start">
        {/* AuditTable — 65% */}
        <div className="flex-[65]">
          <AuditTable
            rows={result?.sequential_results.audit_insights ?? []}
            isLoading={!result && !error}
            emptyMessage="Sin resultados de auditoría"
          />
        </div>

        {/* Side panel — 35% */}
        <div className="flex-[35] flex flex-col gap-4">
          <ForensicSummary
            anomalies={result?.sequential_results.forensic_report.anomalies ?? []}
          />
          <DormantMetricsList
            metrics={result?.dormant_metrics ?? []}
          />
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="text-muted text-sm p-10">Cargando...</div>}>
      <DashboardContent />
    </Suspense>
  );
}
