"""
MEPIA — MemoryService
Capa de abstracción sobre Supabase pgvector + Engram para RAG y persistencia de memoria.

Responsabilidades:
  - get_context()   → lectura semántica (todos los agentes)
  - store_memory()  → escritura de chunks (solo N12, N13, onboarding)

Reglas de integridad:
  - get_context falla silenciosamente — el pipeline puede continuar sin contexto histórico
  - store_memory falla ruidosamente  — perder un chunk es un problema de integridad de datos
  - Postgres (mepia_memory) es la Single Source of Truth
  - Engram es secundario y eventual — su fallo no revierte la escritura en Postgres

Referencia de spec: .kiro/specs/mepia/mem_memory_layer.md
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de chunking (definidas en el spec)
# ---------------------------------------------------------------------------

CHUNK_SIZE_TOKENS = 500       # tamaño máximo de cada chunk en tokens
CHUNK_OVERLAP_TOKENS = 50     # solapamiento entre chunks consecutivos
EMBEDDING_MODEL = "text-embedding-3-small"  # modelo de embeddings de OpenAI
EMBEDDING_DIMS = 1536         # dimensiones del vector resultante
DECAY_FACTOR = 0.01           # factor de decaimiento para time-weighted retrieval
                              # recuerdo de 100 días ≈ 37% del peso original


# ---------------------------------------------------------------------------
# Excepción custom
# ---------------------------------------------------------------------------

class MemoryServiceError(Exception):
    """
    Error de la capa de memoria.

    Se lanza cuando una operación de escritura falla de forma irrecuperable.
    Las operaciones de lectura nunca lanzan esta excepción — retornan string vacío.
    """
    pass


# ---------------------------------------------------------------------------
# Contrato de datos — MemoryChunk
# ---------------------------------------------------------------------------

class MemoryChunk(BaseModel):
    """
    Payload que N13, N12 o el proceso de onboarding envían a store_memory().

    Contrato definido en _glossary.md sección 'MemoryChunk'.
    MemoryService divide internamente el content en sub-chunks de ≤500 tokens.
    """

    business_id: str = Field(
        description="UUID del negocio — FK a businesses en Supabase."
    )
    source_audit_run_id: Optional[str] = Field(
        default=None,
        description=(
            "UUID del run de auditoría origen. "
            "Nullable para chunks de onboarding sin auditoría previa."
        ),
    )
    node_origin: Literal["N12", "N13", "onboarding"] = Field(
        description=(
            "Nodo que genera el chunk. "
            "Solo N12, N13 y el proceso de onboarding tienen permiso de escritura."
        )
    )
    date: str = Field(
        description="Fecha de la auditoría en formato ISO-8601 (YYYY-MM-DD)."
    )
    content: str = Field(
        description=(
            "Texto completo a persistir. "
            "MemoryService lo divide en sub-chunks de ≤500 tokens con 50 de solapamiento."
        )
    )
    archetype: Optional[Literal["Operative Genius", "Product Purist", "Growth Hacker"]] = Field(
        default=None,
        description=(
            "Arquetipo CEO del run. "
            "Null para chunks de onboarding — la identidad de marca es independiente del arquetipo."
        ),
    )
    quality_approved: bool = Field(
        description=(
            "True si N13 validó el contenido, o true para chunks de onboarding. "
            "False si el chunk proviene de un borrador no validado."
        )
    )

    @field_validator("content")
    @classmethod
    def content_no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("content no puede estar vacío")
        return v

    @field_validator("date")
    @classmethod
    def date_formato_valido(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"date debe estar en formato YYYY-MM-DD, recibido: '{v}'")
        return v


# ---------------------------------------------------------------------------
# MemoryService
# ---------------------------------------------------------------------------

class MemoryService:
    """
    Wrapper que abstrae Supabase pgvector + Engram para la capa de memoria de MEPIA.

    Uso:
        # Con Supabase real
        from supabase import create_client
        supabase = create_client(url, key)
        memory = MemoryService(supabase_client=supabase)

        # Sin infraestructura (tests, desarrollo local)
        memory = MemoryService()  # opera en modo degradado

    El cliente de Supabase se inyecta en el constructor para permitir
    mocking en tests sin parchear módulos globales.
    """

    def __init__(self, supabase_client: Any = None) -> None:
        """
        Args:
            supabase_client: Cliente de Supabase inicializado externamente.
                             Si es None, el servicio opera en modo degradado:
                             - get_context retorna string vacío
                             - store_memory lanza MemoryServiceError
        """
        self._supabase = supabase_client
        self._openai_client: Any = None  # inicializado lazy en _get_embedding()

    # ── Lectura ───────────────────────────────────────────────────────────────

    async def get_context(
        self,
        query: str,
        business_id: str,
        limit: int = 5,
    ) -> str:
        """
        Recupera contexto semántico relevante para el query dado.

        Combina resultados de pgvector (Supabase) con time-weighted retrieval
        y de Engram (patrones abstractos de largo plazo).

        Falla silenciosamente — si Supabase o Engram no están disponibles,
        retorna string vacío para no bloquear el pipeline.

        Args:
            query:       Texto de búsqueda semántica.
            business_id: UUID del negocio — filtra resultados por negocio.
            limit:       Número máximo de chunks a recuperar (default 5).

        Returns:
            String consolidado con el contexto, listo para inyectar en un prompt.
            String vacío si no hay contexto disponible o si el servicio falla.
        """
        if self._supabase is None:
            logger.warning(
                "MemoryService.get_context: Supabase no configurado — "
                "retornando contexto vacío (modo degradado)."
            )
            return ""

        try:
            embedding = await self._get_embedding(query)
            chunks = await self._search_pgvector(
                embedding=embedding,
                business_id=business_id,
                limit=limit,
            )

            if not chunks:
                return ""

            # Aplicar time-weighted retrieval y ordenar por score final
            now = datetime.now(timezone.utc)
            scored = [
                (chunk, self._time_weighted_score(chunk, now))
                for chunk in chunks
            ]
            scored.sort(key=lambda x: x[1], reverse=True)

            # Consolidar en string para el prompt
            context_parts = [chunk["content"] for chunk, _ in scored]
            return "\n\n---\n\n".join(context_parts)

        except Exception as exc:
            logger.warning(
                "MemoryService.get_context falló — retornando contexto vacío. "
                "Error: %s: %s",
                type(exc).__name__,
                exc,
            )
            return ""

    # ── Escritura ─────────────────────────────────────────────────────────────

    async def store_memory(self, chunk: MemoryChunk) -> None:
        """
        Persiste un MemoryChunk en mepia_memory (Supabase pgvector).

        Proceso:
          1. Divide content en sub-chunks de ≤500 tokens con 50 de solapamiento
          2. Inserta cada sub-chunk en mepia_memory con status="pending_embed"
          3. El embedding se genera de forma asíncrona (BackgroundTask en FastAPI)
          4. Engram se actualiza de forma eventual (best-effort)

        Falla ruidosamente — lanza MemoryServiceError si Supabase no está disponible
        o si la inserción falla. Perder un chunk es un problema de integridad de datos.

        Args:
            chunk: MemoryChunk validado con el contenido a persistir.

        Raises:
            MemoryServiceError: Si Supabase no está configurado o la inserción falla.
        """
        if self._supabase is None:
            raise MemoryServiceError(
                "MemoryService.store_memory: Supabase no configurado. "
                "No se puede persistir el MemoryChunk sin cliente de base de datos."
            )

        sub_chunks = self._split_into_chunks(chunk.content)
        total = len(sub_chunks)

        for index, sub_content in enumerate(sub_chunks):
            metadata = {
                "node_origin": chunk.node_origin,
                "date": chunk.date,
                "chunk_index": index,
                "chunk_total": total,
                "archetype": chunk.archetype,
                "quality_approved": chunk.quality_approved,
            }

            row = {
                "business_id": chunk.business_id,
                "source_audit_run_id": chunk.source_audit_run_id,
                "content": sub_content,
                "metadata": metadata,
                "status": "pending_embed",  # embedding se genera en BackgroundTask
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            try:
                # TODO: reemplazar con llamada real al cliente Supabase cuando
                # la tabla mepia_memory esté creada (ver db_schema.md).
                # Ejemplo:
                #   result = self._supabase.table("mepia_memory").insert(row).execute()
                #   if result.error:
                #       raise MemoryServiceError(f"Insert falló: {result.error}")
                await self._insert_chunk(row)

            except MemoryServiceError:
                raise  # re-lanzar sin envolver
            except Exception as exc:
                raise MemoryServiceError(
                    f"Error al insertar chunk {index + 1}/{total} en mepia_memory: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

        logger.info(
            "MemoryService.store_memory: %d sub-chunk(s) insertados para business_id=%s "
            "(node_origin=%s, status=pending_embed).",
            total,
            chunk.business_id,
            chunk.node_origin,
        )

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _split_into_chunks(self, content: str) -> List[str]:
        """
        Divide el contenido en sub-chunks de ≤CHUNK_SIZE_TOKENS tokens
        con CHUNK_OVERLAP_TOKENS tokens de solapamiento entre chunks consecutivos.

        Usa tiktoken con el encoding cl100k_base (compatible con text-embedding-3-small).
        Si tiktoken no está disponible, hace un split aproximado por caracteres.

        Args:
            content: Texto completo a dividir.

        Returns:
            Lista de strings, cada uno ≤ CHUNK_SIZE_TOKENS tokens.
        """
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            tokens = enc.encode(content)
        except ImportError:
            logger.warning(
                "tiktoken no disponible — usando split aproximado por caracteres. "
                "Instalar con: pip install tiktoken"
            )
            # Fallback: aproximar 1 token ≈ 4 caracteres
            chars_per_token = 4
            chunk_chars = CHUNK_SIZE_TOKENS * chars_per_token
            overlap_chars = CHUNK_OVERLAP_TOKENS * chars_per_token
            step = chunk_chars - overlap_chars
            return [
                content[i : i + chunk_chars]
                for i in range(0, len(content), step)
                if content[i : i + chunk_chars].strip()
            ]

        if not tokens:
            return [content]

        step = CHUNK_SIZE_TOKENS - CHUNK_OVERLAP_TOKENS
        sub_chunks: List[str] = []

        for start in range(0, len(tokens), step):
            window = tokens[start : start + CHUNK_SIZE_TOKENS]
            if not window:
                break
            decoded = enc.decode(window)
            if decoded.strip():
                sub_chunks.append(decoded)

        return sub_chunks if sub_chunks else [content]

    def _time_weighted_score(
        self,
        chunk: dict,
        now: datetime,
    ) -> float:
        """
        Calcula el score final con decaimiento temporal.

        score_final = similarity_cosine * (1 / (1 + decay_factor * days_elapsed))

        Chunks más recientes tienen mayor peso. Sin TTL — el historial nunca se borra.

        Args:
            chunk: Fila de mepia_memory con 'similarity' y 'created_at'.
            now:   Timestamp actual para calcular days_elapsed.

        Returns:
            Score final entre 0 y 1.
        """
        similarity: float = chunk.get("similarity", 0.0)
        created_at_raw = chunk.get("created_at")

        if not created_at_raw:
            return similarity

        try:
            if isinstance(created_at_raw, str):
                created_at = datetime.fromisoformat(created_at_raw)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
            else:
                created_at = created_at_raw

            days_elapsed = max(0.0, (now - created_at).total_seconds() / 86400)
            decay = 1.0 / (1.0 + DECAY_FACTOR * days_elapsed)
            return similarity * decay

        except Exception:
            return similarity

    async def _get_embedding(self, text: str) -> List[float]:
        """
        Genera el embedding vectorial del texto usando text-embedding-3-small.

        Usa openai.AsyncOpenAI para llamadas async no bloqueantes.
        El cliente se inicializa lazy y se reutiliza entre llamadas.

        Args:
            text: Texto a vectorizar (se trunca a 8191 tokens si es necesario).

        Returns:
            Lista de 1536 floats representando el vector.

        Raises:
            MemoryServiceError: Si OPENAI_API_KEY no está configurada o la API falla.
        """
        try:
            import os
            from openai import AsyncOpenAI

            if self._openai_client is None:
                api_key = os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    raise MemoryServiceError(
                        "OPENAI_API_KEY no configurada — no se puede generar embedding."
                    )
                self._openai_client = AsyncOpenAI(api_key=api_key)

            # Limpiar saltos de línea — mejora la calidad del embedding
            clean_text = text.replace("\n", " ").strip()
            if not clean_text:
                raise MemoryServiceError("Texto vacío — no se puede generar embedding.")

            response = await self._openai_client.embeddings.create(
                input=clean_text,
                model=EMBEDDING_MODEL,
            )
            return response.data[0].embedding

        except MemoryServiceError:
            raise
        except Exception as exc:
            raise MemoryServiceError(
                f"Error al generar embedding con {EMBEDDING_MODEL}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    async def _search_pgvector(
        self,
        embedding: List[float],
        business_id: str,
        limit: int,
    ) -> List[dict]:
        """
        Busca chunks similares en mepia_memory usando pgvector (cosine similarity).

        Llama al RPC `match_mepia_memory` definido en 004_rpc_and_rls.sql.
        Filtra por business_id y status='embedded'.
        Retorna los `limit` chunks más similares con su score de similitud.

        Args:
            embedding:   Vector de búsqueda (1536 dims).
            business_id: UUID del negocio para filtrar resultados.
            limit:       Número máximo de resultados.

        Returns:
            Lista de dicts con campos: content, metadata, similarity, created_at.
        """
        try:
            result = self._supabase.rpc(
                "match_mepia_memory",
                {
                    "query_embedding": embedding,
                    "business_id_filter": business_id,
                    "match_count": limit,
                },
            ).execute()
            return result.data or []
        except Exception as exc:
            logger.warning(
                "MemoryService._search_pgvector falló para business_id=%s: %s: %s",
                business_id,
                type(exc).__name__,
                exc,
            )
            return []

    async def _insert_chunk(self, row: dict) -> None:
        """
        Inserta un sub-chunk en la tabla mepia_memory de Supabase.

        Args:
            row: Dict con los campos de la fila a insertar.

        Raises:
            MemoryServiceError: Si la inserción falla.
        """
        try:
            result = self._supabase.table("mepia_memory").insert(row).execute()
            # El cliente supabase-py lanza excepción si hay error — no hay result.error
            logger.debug(
                "MemoryService._insert_chunk: chunk insertado para business_id=%s "
                "(node_origin=%s, chunk_index=%s/%s).",
                row.get("business_id"),
                row.get("metadata", {}).get("node_origin"),
                row.get("metadata", {}).get("chunk_index"),
                row.get("metadata", {}).get("chunk_total"),
            )
        except Exception as exc:
            raise MemoryServiceError(
                f"Insert en mepia_memory falló: {type(exc).__name__}: {exc}"
            ) from exc
