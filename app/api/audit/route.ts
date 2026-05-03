import { NextRequest, NextResponse } from "next/server";

const AGENTS_API = process.env.AGENTS_API_URL ?? "http://localhost:8000";

/**
 * POST /api/audit
 * Proxies to FastAPI N05 CEO Orchestrator.
 * Body: OrchestratorRunPayload { business_id, date, archetype, escalate_to_parallel, temporalidad }
 * → POST /orchestrator/run
 * Returns: OrchestratorResult with run_id for polling
 */
export async function POST(req: NextRequest) {
  const body = await req.json();

  // Validate required fields
  if (!body.business_id || !body.date) {
    return NextResponse.json(
      { error: "business_id and date are required" },
      { status: 400 }
    );
  }

  const res = await fetch(`${AGENTS_API}/orchestrator/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      business_id: body.business_id,
      date: body.date,
      archetype: body.archetype ?? "Operative Genius",
      escalate_to_parallel: body.escalate_to_parallel ?? true,
      temporalidad: body.temporalidad ?? "short",
    }),
  });

  const data = await res.json().catch(() => null);
  return NextResponse.json(data, { status: res.status });
}
