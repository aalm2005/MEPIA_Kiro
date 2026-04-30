import { NextRequest, NextResponse } from "next/server";

const AGENTS_API = process.env.AGENTS_API_URL ?? "http://localhost:8000";

// POST /api/upload — proxies to FastAPI based on document type
// Body: FormData with `file` and `type` ("pos" | "factura")
// → POST /ingest/pos or POST /ingest/factura
export async function POST(req: NextRequest) {
  const form = await req.formData();
  const file = form.get("file") as File | null;
  const type = form.get("type") as string | null;

  if (!file) {
    return NextResponse.json({ error: "No file provided" }, { status: 400 });
  }
  if (type !== "pos" && type !== "factura") {
    return NextResponse.json(
      { error: 'Invalid type. Must be "pos" or "factura"' },
      { status: 400 }
    );
  }

  const upstream = new FormData();
  upstream.append("file", file);

  const businessId = process.env.NEXT_PUBLIC_BUSINESS_ID;
  if (businessId) {
    upstream.append("business_id", businessId);
  }

  const res = await fetch(`${AGENTS_API}/ingest/${type}`, {
    method: "POST",
    body: upstream,
  });

  const data = await res.json().catch(() => null);
  return NextResponse.json(data, { status: res.status });
}

// PATCH /api/upload/review — proxies to FastAPI review endpoint
// Body: JSON { file_id, document_type, field_corrections }
// → PATCH /ingest/{document_type}/{file_id}/review
export async function PATCH(req: NextRequest) {
  const body = await req.json();
  const { file_id, document_type, field_corrections } = body;

  if (!file_id || !document_type) {
    return NextResponse.json(
      { error: "file_id and document_type are required" },
      { status: 400 }
    );
  }

  const res = await fetch(
    `${AGENTS_API}/ingest/${document_type}/${file_id}/review`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ field_corrections }),
    }
  );

  const data = await res.json().catch(() => null);
  return NextResponse.json(data, { status: res.status });
}
