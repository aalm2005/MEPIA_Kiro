# MEPIA — Estrategia de Autenticación y Autorización

**Tipo:** Spec transversal — aplica a todos los endpoints del backend FastAPI
**Archivo de implementación:** `api/core/auth.py` (a crear)
**Depende de:** `api/core/config.py` (settings), tabla `businesses` en Supabase

---

## Principio de Diseño

El backend usa `SUPABASE_SERVICE_ROLE_KEY` (bypass RLS). Esto significa que
**RLS nativo de Supabase no protege los datos** — la autorización es responsabilidad
exclusiva del backend Python. Todo endpoint que reciba un `business_id` debe
verificar que el usuario autenticado tiene permisos sobre ese negocio.

---

## Flujo de Autenticación

```
Frontend (Next.js)
  │  Supabase Auth genera JWT de sesión al hacer login
  │  Header: Authorization: Bearer <supabase_jwt>
  ↓
FastAPI Middleware (verify_token dependency)
  │  1. Extrae el JWT del header Authorization
  │  2. Valida la firma con SUPABASE_JWT_SECRET
  │  3. Verifica expiración (exp claim)
  │  4. Extrae user_id del claim sub
  ↓
FastAPI Authorization (verify_business_access dependency)
  │  5. Extrae business_id del path param o body
  │  6. Consulta: SELECT id FROM businesses WHERE id = :bid AND owner_id = :uid
  │  7. Si no existe → HTTP 403
  ↓
Handler del endpoint
```

---

## Variables de Entorno Requeridas

Agregar a `api/.env.example` y `api/core/config.py`:

```
SUPABASE_JWT_SECRET=   # Settings → Project → API → JWT Secret
                       # Distinto de SUPABASE_SERVICE_ROLE_KEY
```

```python
# En api/core/config.py — agregar al modelo Settings:
SUPABASE_JWT_SECRET: str   # para validar firmas de JWT de sesión
```

---

## Implementación — `api/core/auth.py`

```python
"""
MEPIA — Capa de autenticación y autorización.

Dependencias FastAPI reutilizables:
  - get_current_user_id()  → extrae y valida el JWT, retorna user_id
  - verify_business_access() → verifica que user_id tiene acceso a business_id
"""
import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from core.config import settings

bearer_scheme = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> str:
    """
    Dependencia FastAPI — valida el JWT de Supabase y retorna el user_id.

    Raises:
        HTTP 401: Token ausente, expirado o con firma inválida.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token inválido: sub ausente")
        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Token inválido: {e}")


async def verify_business_access(
    business_id: str,
    user_id: str = Depends(get_current_user_id),
    db=Depends(get_db),   # inyección del cliente Supabase
) -> str:
    """
    Dependencia FastAPI — verifica que user_id tiene acceso a business_id.

    Retorna business_id si el acceso es válido.

    Raises:
        HTTP 403: El usuario no tiene permisos sobre este negocio.
        HTTP 404: El negocio no existe.
    """
    row = await db.fetchone(
        "SELECT id FROM businesses WHERE id = :bid AND owner_id = :uid",
        {"bid": business_id, "uid": user_id}
    )
    if not row:
        # Deliberadamente ambiguo: no revelar si el negocio existe pero no pertenece al usuario
        raise HTTPException(status_code=403, detail="Sin acceso a este negocio")
    return business_id
```

---

## Uso en Endpoints

```python
# Endpoint con autenticación + autorización
@app.post("/ingest/pos")
async def ingest_pos(
    file: UploadFile,
    business_id: str = Form(...),
    verified_bid: str = Depends(verify_business_access),  # valida JWT + permisos
):
    # verified_bid == business_id si el acceso es válido
    ...

# Endpoint solo con autenticación (sin business_id en path)
@app.get("/me/businesses")
async def list_my_businesses(
    user_id: str = Depends(get_current_user_id),
):
    ...
```

---

## Schema — Campo `owner_id` en `businesses`

La tabla `businesses` requiere el campo `owner_id` para la verificación de acceso:

```sql
-- Agregar a 002_hybrid_schema.sql:
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS
    owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_businesses_owner
    ON businesses (owner_id);
```

> `auth.users` es la tabla de usuarios de Supabase Auth.
> El backend usa `service_role_key` → puede leer `auth.users` directamente.

---

## Tabla de Endpoints y Nivel de Protección

| Endpoint | Autenticación | Autorización |
|---|---|---|
| `POST /ingest/pos` | ✅ JWT | ✅ `business_id` en form |
| `POST /ingest/factura` | ✅ JWT | ✅ `business_id` en form |
| `POST /business/{id}/onboarding` | ✅ JWT | ✅ `business_id` en path |
| `POST /orchestrator/run` | ✅ JWT | ✅ `business_id` en body |
| `POST /api/audit/layer3/run` | ✅ JWT | ✅ via `audit_run_id` → `business_id` |
| `GET /api/audit/layer3/status/{id}` | ✅ JWT | ✅ via `layer3_run_id` → `business_id` |
| `GET /api/audit/layer3/result/{id}` | ✅ JWT | ✅ via `layer3_run_id` → `business_id` |
| `GET /audit` (demo) | ❌ público | ❌ solo en `ENVIRONMENT=dev` |

---

## Acceptance Criteria

- WHEN request sin header `Authorization` → HTTP 401
- WHEN JWT expirado → HTTP 401 con mensaje "Token expirado"
- WHEN JWT con firma inválida → HTTP 401
- WHEN JWT válido pero `business_id` no pertenece al usuario → HTTP 403
- WHEN JWT válido y `business_id` correcto → request procesado normalmente
- WHEN `ENVIRONMENT=prod` y endpoint `/audit` (demo) → HTTP 404 o deshabilitado
- WHEN `SUPABASE_JWT_SECRET` no configurado → error de startup, no silencioso

---

## Edge Cases

- Token válido pero `sub` ausente → HTTP 401 (no asumir user_id)
- `business_id` en path vs body: `verify_business_access` acepta el `business_id` como parámetro — el endpoint decide de dónde lo extrae
- Layer 3 con `audit_run_id`: verificar `business_id` del run, no del payload directo
- Modo aislado de Layer 3 (`audit_run_id` ausente): `business_id` viene del body → misma verificación aplica

---

## Archivos relacionados
- `api/core/config.py` — agregar `SUPABASE_JWT_SECRET`
- `api/.env.example` — agregar `SUPABASE_JWT_SECRET=`
- `db_schema.md` — agregar `owner_id` a tabla `businesses`
- `n03_human_input_endpoints.md` — endpoints de input manual que requieren auth
