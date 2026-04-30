import { NextRequest, NextResponse } from "next/server";

const AGENTS_API = process.env.AGENTS_API_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.json();

  const res = await fetch(`${AGENTS_API}/orchestrator/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await res.json().catch(() => null);
  return NextResponse.json(data, { status: res.status });
}
