# ERP Platform Backend

Base técnica general del backend ERP.

## Alcance actual

La rama P-1 implementa únicamente el `Core Runtime`:

- bootstrap FastAPI;
- configuración por entorno;
- API versionada `/api/v1`;
- health/liveness/readiness de solo lectura;
- error envelope seguro;
- correlation id;
- primitivas de UUID y tiempo;
- frontera transaccional neutral;
- conexión PostgreSQL solo para readiness.

No contiene módulos de negocio, Tenancy real, Identity, Authorization ni Sync.

## Ejecución local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Configure variables desde `.env.example` mediante el mecanismo de entorno de su sistema.

## Endpoints P-1

```text
GET /api/v1/live
GET /api/v1/ready
GET /api/v1/health
```

Los endpoints de salud no crean tablas ni escriben datos.
