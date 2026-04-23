"use client";
import { useState } from "react";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setStatus("uploading");

    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch("/api/upload", { method: "POST", body: form });
      setStatus(res.ok ? "done" : "error");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className="min-h-screen bg-zinc-900 flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-zinc-800 rounded-2xl p-8 border border-zinc-700">
        <p className="text-emerald-400 text-xs tracking-widest uppercase mb-1">Ingesta</p>
        <h1 className="text-xl font-semibold text-zinc-100 mb-6">Subir Documento</h1>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-2">
            <span className="text-zinc-400 text-sm">PDF de POS o Factura</span>
            <input
              type="file"
              accept=".pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm text-zinc-300 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-zinc-700 file:text-zinc-200 hover:file:bg-zinc-600 cursor-pointer"
            />
          </label>

          <button
            type="submit"
            disabled={!file || status === "uploading"}
            className="mt-2 px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-zinc-900 font-medium rounded-lg transition-colors text-sm"
          >
            {status === "uploading" ? "Procesando..." : "Analizar con Agentes"}
          </button>

          {status === "done" && (
            <p className="text-emerald-400 text-sm text-center">Documento procesado. Revisa el dashboard.</p>
          )}
          {status === "error" && (
            <p className="text-red-400 text-sm text-center">Error al procesar. Intenta de nuevo.</p>
          )}
        </form>
      </div>
    </div>
  );
}
