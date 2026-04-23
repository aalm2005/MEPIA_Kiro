import Link from "next/link";

export default function Home() {
  return (
    <main className="flex flex-col items-center justify-center min-h-screen gap-6 px-4">
      <div className="text-center">
        <p className="text-emerald-400 text-sm tracking-widest uppercase mb-2">Mise En Place AI</p>
        <h1 className="text-4xl font-semibold text-zinc-100">MEPIA</h1>
        <p className="text-zinc-400 mt-2 text-base">Tu copiloto financiero para el restaurante.</p>
      </div>
      <div className="flex gap-4 mt-4">
        <Link
          href="/dashboard"
          className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 text-zinc-900 font-medium rounded-lg transition-colors text-sm"
        >
          Ver Dashboard
        </Link>
        <Link
          href="/upload"
          className="px-5 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 font-medium rounded-lg transition-colors text-sm border border-zinc-700"
        >
          Subir Documentos
        </Link>
      </div>
    </main>
  );
}
