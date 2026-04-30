import { NextRequest, NextResponse } from "next/server";

const AGENTS_API = process.env.AGENTS_API_URL ?? "http://localhost:8000";

// GET /api/onboarding/status?business_id=... → GET /business/{id}/onboarding/status
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const businessId = searchParams.get("business_id");

  if (!businessId) {
    return NextResponse.json(
      { error: "business_id query param is required" },
      { status: 400 }
    );
  }

  const res = await fetch(
    `${AGENTS_API}/business/${businessId}/onboarding/status`,
    { cache: "no-store" }
  );

  const data = await res.json().catch(() => null);
  return NextResponse.json(data, { status: res.status });
}

// POST /api/onboarding → POST /business/{id}/onboarding
export async function POST(req: NextRequest) {
  const body = await req.json();
  const { business_id, ...rest } = body;

  if (!business_id) {
    return NextResponse.json(
      { error: "business_id is required in request body" },
      { status: 400 }
    );
  }

  const res = await fetch(`${AGENTS_API}/business/${business_id}/onboarding`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ business_id, ...rest }),
  });

  const data = await res.json().catch(() => null);
  return NextResponse.json(data, { status: res.status });
}

// PUT /api/onboarding → PUT /business/{id}/onboarding
export async function PUT(req: NextRequest) {
  const body = await req.json();
  const { business_id, ...rest } = body;

  if (!business_id) {
    return NextResponse.json(
      { error: "business_id is required in request body" },
      { status: 400 }
    );
  }

  const res = await fetch(`${AGENTS_API}/business/${business_id}/onboarding`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ business_id, ...rest }),
  });

  const data = await res.json().catch(() => null);
  return NextResponse.json(data, { status: res.status });
}
