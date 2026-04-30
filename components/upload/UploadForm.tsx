"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Archetype } from "../AuditTable";
import ArchetypeSelector from "./ArchetypeSelector";
import DocumentDropzone from "./DocumentDropzone";
import type { DropzoneStatus } from "./DocumentDropzone";
import UploadStatusBadge from "./UploadStatusBadge";
import ReviewAlert from "./ReviewAlert";

interface ReviewState {
  fileId: string;
  missingFields: string[];
}

/** Maps HTTP status codes to user-facing Spanish error messages. */
function getApiErrorMessage(status: number, body: unknown): string {
  if (status === 409) return "Faltan datos para iniciar el análisis.";
  if (status === 412) return "Completa el onboarding antes de auditar.";
  if (status === 503) return "El servicio no está disponible.";
  if (status === 422) {
    const detail =
      (body as { detail?: string } | null)?.detail;
    return detail ?? "Error de validación.";
  }
  return "Error inesperado. Intenta de nuevo.";
}

export default function UploadForm() {
  const router = useRouter();

  const [archetype, setArchetype] = useState<Archetype>("Operative Genius");
  const [posFile, setPosFile] = useState<File | null>(null);
  const [facturaFile, setFacturaFile] = useState<File | null>(null);

  const [posStatus, setPosStatus] = useState<DropzoneStatus>("idle");
  const [facturaStatus, setFacturaStatus] = useState<DropzoneStatus>("idle");

  const [posReview, setPosReview] = useState<ReviewState | null>(null);
  const [facturaReview, setFacturaReview] = useState<ReviewState | null>(null);

  const [posErrorMessage, setPosErrorMessage] = useState<string | null>(null);
  const [facturaErrorMessage, setFacturaErrorMessage] = useState<string | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // ── Derived state ──────────────────────────────────────────────────────────

  const isPosReviewPending = posStatus === "needs_human_review" && posReview !== null;
  const isFacturaReviewPending = facturaStatus === "needs_human_review" && facturaReview !== null;
  const isReviewPending = isPosReviewPending || isFacturaReviewPending;

  const noFilesSelected = posFile === null && facturaFile === null;

  const isDisabled =
    noFilesSelected ||
    isAnalyzing ||
    isReviewPending ||
    posStatus === "uploading" ||
    facturaStatus === "uploading";

  // ── CTA label ──────────────────────────────────────────────────────────────

  function getCtaLabel(): string {
    if (isPosReviewPending) return "Esperando revisión POS...";
    if (isFacturaReviewPending) return "Esperando revisión Factura...";
    if (isAnalyzing) return "Analizando...";
    return "Analizar con Agentes IA →";
  }

  // ── File handlers ──────────────────────────────────────────────────────────

  function handlePosFile(file: File) {
    setPosFile(file);
    setPosStatus("idle");
    setPosErrorMessage(null);
    setPosReview(null);
  }

  function handleFacturaFile(file: File) {
    setFacturaFile(file);
    setFacturaStatus("idle");
    setFacturaErrorMessage(null);
    setFacturaReview(null);
  }

  // ── Main upload + audit flow ───────────────────────────────────────────────

  async function handleAnalyze() {
    setAuditError(null);

    // ── Step 1: Upload POS ──────────────────────────────────────────────────
    if (posFile) {
      setPosStatus("uploading");
      setPosErrorMessage(null);

      try {
        const formData = new FormData();
        formData.append("file", posFile);
        formData.append("type", "pos");

        const res = await fetch("/api/upload", { method: "POST", body: formData });
        const body = await res.json().catch(() => null);

        if (!res.ok) {
          const msg = getApiErrorMessage(res.status, body);
          setPosStatus("error");
          setPosErrorMessage(msg);
          return;
        }

        // POSIngestResult[]
        const results: Array<{
          needs_human_review: boolean;
          file_id: string;
          missing_fields?: string[];
        }> = Array.isArray(body) ? body : [body];

        const reviewNeeded = results.find((r) => r.needs_human_review);
        if (reviewNeeded) {
          setPosStatus("needs_human_review" as DropzoneStatus);
          setPosReview({
            fileId: reviewNeeded.file_id,
            missingFields: reviewNeeded.missing_fields ?? [],
          });
          // Flow pauses here — user must complete review via ReviewAlert
          return;
        }

        setPosStatus("done");
      } catch {
        setPosStatus("error");
        setPosErrorMessage("Error inesperado. Intenta de nuevo.");
        return;
      }
    }

    // ── Step 2: Guard — if POS review is still pending, stop ───────────────
    if (posReview !== null) {
      return;
    }

    // ── Step 3: Upload Factura ──────────────────────────────────────────────
    if (facturaFile) {
      setFacturaStatus("uploading");
      setFacturaErrorMessage(null);

      try {
        const formData = new FormData();
        formData.append("file", facturaFile);
        formData.append("type", "factura");

        const res = await fetch("/api/upload", { method: "POST", body: formData });
        const body = await res.json().catch(() => null);

        if (!res.ok) {
          const msg = getApiErrorMessage(res.status, body);
          setFacturaStatus("error");
          setFacturaErrorMessage(msg);
          return;
        }

        // FacturaIngestResult[]
        const results: Array<{
          needs_human_review: boolean;
          file_id: string;
          missing_fields?: string[];
        }> = Array.isArray(body) ? body : [body];

        const reviewNeeded = results.find((r) => r.needs_human_review);
        if (reviewNeeded) {
          setFacturaStatus("needs_human_review" as DropzoneStatus);
          setFacturaReview({
            fileId: reviewNeeded.file_id,
            missingFields: reviewNeeded.missing_fields ?? [],
          });
          // Flow pauses here — user must complete review via ReviewAlert
          return;
        }

        setFacturaStatus("done");
      } catch {
        setFacturaStatus("error");
        setFacturaErrorMessage("Error inesperado. Intenta de nuevo.");
        return;
      }
    }

    // ── Step 4: Guard — if Factura review is still pending, stop ───────────
    if (facturaReview !== null) {
      return;
    }

    // ── Step 5: Trigger audit ───────────────────────────────────────────────
    setIsAnalyzing(true);

    try {
      const res = await fetch("/api/audit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          archetype,
          business_id: process.env.NEXT_PUBLIC_BUSINESS_ID,
          date: new Date().toISOString().split("T")[0],
        }),
      });

      const body = await res.json().catch(() => null);

      if (!res.ok) {
        const msg = getApiErrorMessage(res.status, body);
        setAuditError(msg);
        if (res.status === 412) {
          router.push("/onboarding");
        }
        return;
      }

      const result = body as { run_id: string };
      router.push(`/dashboard?run_id=${result.run_id}`);
    } catch {
      setAuditError("Error inesperado. Intenta de nuevo.");
    } finally {
      setIsAnalyzing(false);
    }
  }

  // ── ReviewAlert callbacks ──────────────────────────────────────────────────

  function handlePosReviewed() {
    setPosReview(null);
    setPosStatus("done");
  }

  function handleFacturaReviewed() {
    setFacturaReview(null);
    setFacturaStatus("done");
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Title */}
      <h1 className="text-forensic-lg font-semibold text-zinc-100 mb-6 uppercase tracking-widest">
        INGESTA — Subir Documentos de Auditoría
      </h1>

      {/* Archetype selector */}
      <div className="mb-6">
        <ArchetypeSelector value={archetype} onChange={setArchetype} />
      </div>

      {/* 2-column dropzone grid */}
      <div className="grid grid-cols-2 gap-6 mb-4">
        {/* POS column */}
        <div className="flex flex-col gap-2">
          <DocumentDropzone
            label="Ticket POS"
            accept={["application/pdf"]}
            status={posStatus}
            onFile={handlePosFile}
            errorMessage={posErrorMessage ?? undefined}
          />
          <UploadStatusBadge status={posStatus} />
          {posReview && (
            <ReviewAlert
              documentType="pos"
              fileId={posReview.fileId}
              missingFields={posReview.missingFields}
              onReviewed={handlePosReviewed}
            />
          )}
        </div>

        {/* Factura column */}
        <div className="flex flex-col gap-2">
          <DocumentDropzone
            label="Factura de Proveedor"
            accept={["application/pdf", "text/xml", "application/xml"]}
            status={facturaStatus}
            onFile={handleFacturaFile}
            errorMessage={facturaErrorMessage ?? undefined}
          />
          <UploadStatusBadge status={facturaStatus} />
          {facturaReview && (
            <ReviewAlert
              documentType="factura"
              fileId={facturaReview.fileId}
              missingFields={facturaReview.missingFields}
              onReviewed={handleFacturaReviewed}
            />
          )}
        </div>
      </div>

      {/* Audit error banner */}
      {auditError && (
        <div
          className="mb-4 px-4 py-3 border border-red-700 bg-red-950/30 rounded text-sm text-red-400 font-mono"
          role="alert"
        >
          {auditError}
        </div>
      )}

      {/* CTA button */}
      <button
        type="button"
        onClick={handleAnalyze}
        disabled={isDisabled}
        className="w-full mt-6 py-3 text-sm font-semibold uppercase tracking-widest border border-accent text-accent hover:bg-accent hover:text-canvas transition-colors rounded disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {getCtaLabel()}
      </button>
    </div>
  );
}
