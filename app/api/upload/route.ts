import { NextRequest, NextResponse } from "next/server";

// Reenvía el PDF al microservicio Python (FastAPI)
const AGENTS_API = process.env.AGENTS_API_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const file = form.get("file") as File | null;

  if (!file) return NextResponse.json({ error: "No file" }, { status: 400 });

  // Proxy al backend Python
  const upstream = new FormData();
  upstream.append("file", file);

  const res = await fetch(`${AGENTS_API}/ingest`, {
    method: "POST",
    body: upstream,
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
