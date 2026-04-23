import { NextResponse } from "next/server";

const AGENTS_API = process.env.AGENTS_API_URL ?? "http://localhost:8000";

export async function GET() {
  const res = await fetch(`${AGENTS_API}/audit`, { cache: "no-store" });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
