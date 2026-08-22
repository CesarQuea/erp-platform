# ERP Platform Backend

Base técnica general del backend ERP.

## Alcance actual

P-1 dejó cerrado el `Core Runtime`. P-2 incorpora la fundación de tenancy y multiempresa:

- `TenantContext` explícito y fail-closed;
- `TenantRegistry` desacoplado del código de negocio;
- datasource PostgreSQL físico independiente por Tenant;
- validación de identidad física mediante `platform_tenant_metadata`;
- `Company` neutral dentro de cada Tenant;
- transacciones SQLAlchemy encapsuladas detrás del Core;
- migraciones Alembic por Tenant;
- provisioning interno idempotente;
- ownership scopes de plataforma.

P-2 no implementa Identity, Authentication, Authorization, Sync ni módulos de negocio.
No existe un `X-Tenant-ID` público como autoridad de seguridad.

## Ejecución local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Configure variables desde `.env.example` mediante el mecanismo de entorno de su sistema.
`TENANT_DATABASES_JSON` es una implementación temporal del registry hasta disponer de Control Plane; no debe contener credenciales versionadas en Git.

## Endpoints de plataforma

```text
GET /api/v1/live
GET /api/v1/ready
GET /api/v1/health
```

Los endpoints de salud continúan siendo de solo lectura y no seleccionan Tenant.
