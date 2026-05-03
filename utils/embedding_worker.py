"""
MEPIA — Embedding Worker
Procesa chunks pendientes en mepia_memory y genera sus embeddings con OpenAI.

Flujo:
  1. Consultar mepia_memory WHERE status = 'pending_embed'
  2. Para cada chunk: generar embedding con text-embedding-3-small
  3. Actualizar embedding + status = 'embedded'
  4. Marcar status = 'failed' tras 3 intentos fallidos

Puede ejecutarse como:
  - FastAPI BackgroundTask (llamado desde POST /memory/store)
  - Script standalone: python -m utils.embedding_worker
  - Endpoint admin: GET /admin/memory/reconcile

Spec: .kiro/specs/mepia/mem_memory_layer.md §Worker Asíncrono de Embeddings
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Número máximo de intentos antes de marcar como 'failed'
MAX_ATTEMPTS = 3

# Modelo de embeddings (debe coincidir con EMBEDDING_MODEL en memory_service.py)
EMBEDDING_MODEL = "text-embedding-3-small"


async def process_pending_embeddings(
    supabase_client: Any,
    batch_size: int = 50,
) -> dict:
    """
    Procesa todos los chunks con status='pending_embed' o status='failed' (< MAX_ATTEMPTS).

    Llamado por:
      - FastAPI BackgroundTask tras POST /memory/store
      - GET /admin/memory/reconcile (reconciliación manual)
      - Script de startup del servidor

    Args:
        supabase_client: Cliente Supabase inicializado.
        batch_size:      Número máximo de chunks a procesar por ejecución.

    Returns:
        Dict con estadísticas: { processed, embedded, failed, skipped }
    """
    stats = {"processed": 0, "embedded": 0, "failed": 0, "skipped": 0}

    if supabase_client is None:
        logger.warning("embedding_worker: Supabase no configurado — abortando.")
        return stats

    # --- 1. Obtener chunks pendientes ---
    try:
        resp = (
            supabase_client.table("mepia_memory")
            .select("id, content, metadata, attempt_count")
            .in_("status", ["pending_embed", "failed"])
            .limit(batch_size)
            .execute()
        )
        pending = resp.data or []
    except Exception as exc:
        logger.error("embedding_worker: Error al consultar chunks pendientes: %s", exc)
        return stats

    if not pending:
        logger.info("embedding_worker: No hay chunks pendientes.")
        return stats

    logger.info("embedding_worker: Procesando %d chunk(s) pendientes.", len(pending))

    # --- 2. Inicializar cliente OpenAI ---
    try:
        from openai import AsyncOpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.error("embedding_worker: OPENAI_API_KEY no configurada.")
            return stats
        openai_client = AsyncOpenAI(api_key=api_key)
    except ImportError:
        logger.error("embedding_worker: openai no instalado. pip install openai")
        return stats

    # --- 3. Procesar cada chunk ---
    for chunk in pending:
        chunk_id = chunk["id"]
        content = chunk.get("content", "")
        attempt_count = chunk.get("attempt_count") or 0
        stats["processed"] += 1

        # Saltar si ya superó el máximo de intentos
        if attempt_count >= MAX_ATTEMPTS:
            logger.warning(
                "embedding_worker: chunk %s superó %d intentos — marcando como failed.",
                chunk_id,
                MAX_ATTEMPTS,
            )
            _mark_failed(supabase_client, chunk_id, attempt_count)
            stats["skipped"] += 1
            continue

        # Generar embedding
        embedding = await _generate_embedding(openai_client, content, chunk_id)

        if embedding is not None:
            # Éxito: actualizar embedding + status = 'embedded'
            success = _update_embedded(supabase_client, chunk_id, embedding)
            if success:
                stats["embedded"] += 1
                logger.debug("embedding_worker: chunk %s → embedded.", chunk_id)
            else:
                stats["failed"] += 1
        else:
            # Fallo: incrementar attempt_count
            new_attempts = attempt_count + 1
            if new_attempts >= MAX_ATTEMPTS:
                _mark_failed(supabase_client, chunk_id, new_attempts)
                logger.warning(
                    "embedding_worker: chunk %s falló %d veces → status=failed.",
                    chunk_id,
                    new_attempts,
                )
            else:
                _increment_attempts(supabase_client, chunk_id, new_attempts)
                logger.warning(
                    "embedding_worker: chunk %s falló (intento %d/%d).",
                    chunk_id,
                    new_attempts,
                    MAX_ATTEMPTS,
                )
            stats["failed"] += 1

    logger.info(
        "embedding_worker: Completado — embedded=%d, failed=%d, skipped=%d.",
        stats["embedded"],
        stats["failed"],
        stats["skipped"],
    )
    return stats


async def process_single_chunk(
    supabase_client: Any,
    chunk_id: str,
) -> bool:
    """
    Procesa un único chunk por ID. Usado por FastAPI BackgroundTask
    inmediatamente después de insertar un chunk nuevo.

    Args:
        supabase_client: Cliente Supabase.
        chunk_id:        UUID del chunk en mepia_memory.

    Returns:
        True si el embedding se generó y guardó correctamente, False si falló.
    """
    if supabase_client is None:
        return False

    try:
        resp = (
            supabase_client.table("mepia_memory")
            .select("id, content, attempt_count")
            .eq("id", chunk_id)
            .single()
            .execute()
        )
        chunk = resp.data
        if not chunk:
            logger.warning("embedding_worker: chunk %s no encontrado.", chunk_id)
            return False
    except Exception as exc:
        logger.error("embedding_worker: Error al leer chunk %s: %s", chunk_id, exc)
        return False

    try:
        from openai import AsyncOpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return False
        openai_client = AsyncOpenAI(api_key=api_key)
    except ImportError:
        return False

    embedding = await _generate_embedding(openai_client, chunk["content"], chunk_id)
    if embedding is None:
        attempt_count = (chunk.get("attempt_count") or 0) + 1
        if attempt_count >= MAX_ATTEMPTS:
            _mark_failed(supabase_client, chunk_id, attempt_count)
        else:
            _increment_attempts(supabase_client, chunk_id, attempt_count)
        return False

    return _update_embedded(supabase_client, chunk_id, embedding)


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

async def _generate_embedding(
    openai_client: Any,
    content: str,
    chunk_id: str,
) -> Optional[list]:
    """
    Genera el embedding para un texto. Retorna None si falla.
    Limpia saltos de línea antes de enviar (mejora calidad del embedding).
    """
    try:
        clean = content.replace("\n", " ").strip()
        if not clean:
            logger.warning("embedding_worker: chunk %s tiene contenido vacío.", chunk_id)
            return None

        response = await openai_client.embeddings.create(
            input=clean,
            model=EMBEDDING_MODEL,
        )
        return response.data[0].embedding

    except Exception as exc:
        logger.warning(
            "embedding_worker: Error al generar embedding para chunk %s: %s: %s",
            chunk_id,
            type(exc).__name__,
            exc,
        )
        return None


def _update_embedded(
    supabase_client: Any,
    chunk_id: str,
    embedding: list,
) -> bool:
    """Actualiza el chunk con el embedding generado y status='embedded'."""
    try:
        supabase_client.table("mepia_memory").update(
            {
                "embedding": embedding,
                "status": "embedded",
                "embedded_at": datetime.now(timezone.utc).isoformat(),
                "attempt_count": 1,  # reset — éxito
            }
        ).eq("id", chunk_id).execute()
        return True
    except Exception as exc:
        logger.error(
            "embedding_worker: Error al actualizar chunk %s como embedded: %s",
            chunk_id,
            exc,
        )
        return False


def _mark_failed(
    supabase_client: Any,
    chunk_id: str,
    attempt_count: int,
) -> None:
    """Marca el chunk como 'failed' tras agotar los intentos."""
    try:
        supabase_client.table("mepia_memory").update(
            {
                "status": "failed",
                "attempt_count": attempt_count,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", chunk_id).execute()
    except Exception as exc:
        logger.error(
            "embedding_worker: Error al marcar chunk %s como failed: %s",
            chunk_id,
            exc,
        )


def _increment_attempts(
    supabase_client: Any,
    chunk_id: str,
    new_count: int,
) -> None:
    """Incrementa el contador de intentos fallidos sin cambiar el status."""
    try:
        supabase_client.table("mepia_memory").update(
            {
                "attempt_count": new_count,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", chunk_id).execute()
    except Exception as exc:
        logger.error(
            "embedding_worker: Error al incrementar attempts para chunk %s: %s",
            chunk_id,
            exc,
        )


# ---------------------------------------------------------------------------
# Punto de entrada como script standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Cargar variables de entorno desde api/.env si existe
    try:
        from dotenv import load_dotenv
        load_dotenv("api/.env")
    except ImportError:
        pass

    # Inicializar cliente Supabase
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY son requeridos.")
        sys.exit(1)

    from supabase import create_client
    db = create_client(supabase_url, supabase_key)

    stats = asyncio.run(process_pending_embeddings(db))
    print(f"Resultado: {stats}")
