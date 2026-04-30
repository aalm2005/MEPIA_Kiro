"use client";

import { useRef, useState } from "react";

export type DropzoneStatus = "idle" | "uploading" | "done" | "error" | "needs_human_review";

interface DocumentDropzoneProps {
  label: string;
  accept: string[]; // MIME types, e.g. ["application/pdf", "text/xml"]
  status: DropzoneStatus;
  onFile: (file: File) => void;
  errorMessage?: string;
}

function Spinner() {
  return (
    <svg
      className="animate-spin h-6 w-6 text-zinc-400 mx-auto"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      className="h-6 w-6 text-emerald-500 mx-auto"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2.5}
      aria-hidden="true"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function ErrorIcon() {
  return (
    <svg
      className="h-6 w-6 text-red-500 mx-auto"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2.5}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
      />
    </svg>
  );
}

export default function DocumentDropzone({
  label,
  accept,
  status,
  onFile,
  errorMessage,
}: DocumentDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [mimeError, setMimeError] = useState<string | null>(null);

  const isInteractive = status === "idle" || status === "error";

  function validateAndDispatch(file: File) {
    setMimeError(null);
    if (!accept.includes(file.type)) {
      setMimeError(
        `Tipo de archivo no permitido: ${file.type || "desconocido"}. Se acepta: ${accept.join(", ")}`
      );
      return;
    }
    onFile(file);
  }

  function handleClick() {
    if (!isInteractive) return;
    inputRef.current?.click();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (!isInteractive) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      inputRef.current?.click();
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) validateAndDispatch(file);
    // Reset input so the same file can be re-selected after an error
    e.target.value = "";
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    if (!isInteractive) return;
    e.preventDefault();
    setIsDragOver(true);
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
    if (!isInteractive) return;
    const file = e.dataTransfer.files?.[0];
    if (file) validateAndDispatch(file);
  }

  // Border + background classes per status
  const borderClass =
    status === "done"
      ? "border-emerald-500"
      : status === "error"
      ? "border-red-500"
      : status === "needs_human_review"
      ? "border-amber-600"
      : isDragOver
      ? "border-zinc-500"
      : "border-dashed border-zinc-700";

  const cursorClass = isInteractive ? "cursor-pointer" : "cursor-default";

  const displayError = mimeError ?? (status === "error" ? errorMessage : null);

  return (
    <div
      role="button"
      tabIndex={isInteractive ? 0 : -1}
      aria-label={label}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`border-2 rounded p-6 text-center transition-colors ${borderClass} ${cursorClass} select-none`}
    >
      {/* Hidden file input */}
      <input
        ref={inputRef}
        type="file"
        hidden
        accept={accept.join(",")}
        onChange={handleInputChange}
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* Label */}
      <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-zinc-500">
        {label}
      </p>

      {/* Status content */}
      {status === "idle" && (
        <div className="space-y-2">
          <svg
            className="h-8 w-8 text-zinc-600 mx-auto"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
            />
          </svg>
          <p className="text-sm text-zinc-400">
            Arrastra tu archivo o haz clic para seleccionar
          </p>
          <p className="text-xs text-zinc-600">
            {accept.join(", ")}
          </p>
        </div>
      )}

      {status === "uploading" && (
        <div className="space-y-2">
          <Spinner />
          <p className="text-sm text-zinc-400">Procesando...</p>
        </div>
      )}

      {status === "done" && (
        <div className="space-y-2">
          <CheckIcon />
          <p className="text-sm text-emerald-400">Archivo cargado ✓</p>
        </div>
      )}

      {status === "error" && (
        <div className="space-y-2">
          <ErrorIcon />
          <p className="text-sm text-red-400">
            {displayError ?? "Error al cargar el archivo"}
          </p>
        </div>
      )}

      {status === "needs_human_review" && (
        <div className="space-y-2">
          <p className="text-2xl mx-auto text-center">⚠</p>
          <p className="text-sm text-amber-400">Revisión requerida</p>
        </div>
      )}

      {/* MIME validation error shown on top of idle state */}
      {status === "idle" && mimeError && (
        <p className="mt-2 text-xs text-red-400">{mimeError}</p>
      )}
    </div>
  );
}
