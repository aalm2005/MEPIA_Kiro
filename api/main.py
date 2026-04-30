"""
MEPIA — FastAPI backend
Expone /ingest y /audit al frontend Next.js
"""
import asyncio
from dataclasses import asdict

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from agents import CashReconciliationAgent, OperativeCostAgent, BusinessHealthAgent
from core.config import settings

app = FastAPI(title="MEPIA Agents API")

# En prod, reemplazar por el dominio real del frontend.
_ALLOWED_ORIGINS = (
    ["http://localhost:3000"]
    if settings.ENVIRONMENT == "dev"
    else ["https://mepia.app"]  # ajustar al dominio de producción
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Flujo paralelo: los tres agentes corren simultáneamente
# ---------------------------------------------------------------------------
async def run_audit_pipeline(payload: dict) -> list[dict]:
    loop = asyncio.get_event_loop()

    cash_agent   = CashReconciliationAgent()
    cost_agent   = OperativeCostAgent()
    health_agent = BusinessHealthAgent()

    results = await asyncio.gather(
        loop.run_in_executor(None, cash_agent.run,   payload.get("cash", {})),
        loop.run_in_executor(None, cost_agent.run,   payload.get("cost", {})),
        loop.run_in_executor(None, health_agent.run, payload.get("health", {})),
    )

    return [asdict(r) for r in results]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/audit")
async def audit():
    """Devuelve resultados de auditoría con datos de ejemplo."""
    sample_payload = {
        "cash":   {"pos_total": 5150.00, "deposit": 5000.00},
        "cost":   {"item": "leche deslactosada", "prev": 800.0, "current": 896.0},
        "health": {"revenue": 50000.0, "costs": 41000.0, "archetype": "Operative Genius"},
    }
    rows = await run_audit_pipeline(sample_payload)
    return {"rows": rows}


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    """Recibe un PDF, extrae datos y dispara el pipeline de agentes."""
    content = await file.read()
    # TODO: parsear PDF con pdfplumber y extraer tablas de POS/facturas
    # Por ahora retorna confirmación
    return {
        "status": "received",
        "filename": file.filename,
        "size_kb": round(len(content) / 1024, 1),
        "message": "Documento en cola para procesamiento.",
    }
