# BE-DES-001 — Contrato de Implementación P-1 Bootstrap y Core Runtime

**Versión:** 0.1
**Estado:** CONGELADO PARA IMPLEMENTACIÓN P-1
**Fecha:** 2026-08-21
**Repositorio:** `CesarQuea/erp-platform`
**Base autorizada:** `3db050fdb8edfc442f0c1e67fef928185cbbf615`
**Rama:** `feat/platform-p1-core-runtime`

## 1. Objetivo

Transformar el prototipo FastAPI existente en un Core Runtime neutral, modular y verificable para `erp-platform`, sin introducir todavía lógica de negocio, tenancy real, autenticación real ni sincronización.

P-1 debe dejar una fundación que los siguientes cortes puedan extender sin reestructurar la aplicación.

## 2. Alcance

### 2.1 Estructura mínima

Crear solo carpetas con responsabilidad real:

```text
app/
├── main.py
├── bootstrap/
├── core/
│   ├── config/
│   ├── errors/
│   ├── identifiers/
│   ├── time/
│   └── transactions/
├── infrastructure/
│   ├── database/
│   └── observability/
└── api/
    └── v1/

tests/
```

No crear módulos de negocio vacíos.

### 2.2 Bootstrap

- factory/bootstrap de FastAPI;
- composición de routers;
- configuración central;
- dependency wiring básico;
- startup/shutdown explícitos cuando corresponda.

### 2.3 Configuración

- configuración por environment;
- `DATABASE_URL` solo como compatibilidad temporal de desarrollo;
- validación de configuración;
- `.env.example` sin secretos;
- no credenciales hardcodeadas.

### 2.4 API base

Exponer:

```text
GET /api/v1/health
GET /api/v1/live
GET /api/v1/ready
```

Semántica:

- `live`: proceso ejecutándose;
- `ready`: dependencias mínimas disponibles;
- `health`: resumen seguro para diagnóstico.

Ninguno puede crear tablas, insertar registros, modificar datos de negocio, exponer secretos ni devolver información sensible del servidor.

Se retira o reemplaza `/db-info` experimental.

### 2.5 Error foundation

Definir un error envelope neutral mínimo con stable code/reason code, mensaje seguro, correlation id cuando aplique y HTTP mapping fuera del dominio. No exponer stack traces al cliente.

### 2.6 Identifiers/time

- UUID estable como primitiva general;
- timestamps timezone-aware para infraestructura;
- reloj inyectable/testable donde corresponda.

No definir reglas funcionales de fecha/turno de módulos.

### 2.7 Transaction boundary

Crear una abstracción mínima para que Application/Domain futuros no dependan directamente de `sqlalchemy.orm.Session`.

No implementar todavía command processing, optimistic locking o idempotencia.

### 2.8 Logging / correlation

- logging estructurado mínimo;
- request/correlation id;
- no registrar passwords, tokens ni DSN completos.

### 2.9 Docker

Conservar/ajustar Dockerfile para arranque reproducible, dependencias explícitas, configuración externa y health compatible.

## 3. Invariantes

1. No aparece `Aliosur` en nombres internos nuevos del Core.
2. No aparece lógica Dairy/Milking/Inventory.
3. FastAPI es adaptador; lógica reusable no reside en routers.
4. Health endpoints son read-only.
5. No se crean tablas en runtime mediante endpoints.
6. No se exponen secretos.
7. No se introduce `Organization` como entidad obligatoria.
8. `Tenant`/`Company` todavía no se implementan funcionalmente en P-1.
9. No se modifica Android.
10. No se copia ningún modelo Room.

## 4. Persistencia

P-1 conserva conexión PostgreSQL suficiente para readiness y pruebas, pero no define todavía TenantDataSourceResolver, DB por Tenant, Tenant Registry, modelos de negocio ni Alembic multi-Tenant definitivo. Eso pertenece a P-2.

## 5. Migraciones

P-1 puede preparar la integración de Alembic si resulta estrictamente necesaria para la estructura, pero no debe crear schema de negocio. La estrategia multi-Tenant se congela en P-2.

## 6. Concurrencia e idempotencia

Fuera de alcance de P-1. No se crean implementaciones provisionales que condicionen P-4.

## 7. Seguridad

Incluye higiene básica: secretos fuera de Git, errores seguros, logging sin credenciales y configuración validada. Authentication/Authorization reales pertenecen a P-3.

## 8. Pruebas obligatorias

### Unit
- config validation;
- error mapping;
- identifier/time primitives si aplican.

### API
- `/live`;
- `/ready`;
- `/health`;
- no mutaciones.

### PostgreSQL
- ready responde correctamente con DB disponible;
- fallo de DB produce estado no-ready sin escribir datos.

### Security checks
- response no expone `DATABASE_URL`;
- logs no incluyen password/DSN completo.

### Regression
- aplicación inicia;
- Docker/build;
- import graph sin módulos sectoriales.

## 9. Evidencias de cierre

El agente independiente deberá aportar comandos ejecutados, salida relevante, resultados pytest/JUnit XML si se configura, lista de tests, diff real, `git diff --check`, estado de working tree, build/container, evidencia de health endpoints, no escrituras y no secretos.

ChatGPT revisará código, diff y evidencias antes de recomendar cierre.

## 10. Exclusiones expresas

- Milking;
- Inventory;
- Manufacturing;
- Sales;
- Livestock;
- Tenant Registry;
- múltiples datasources;
- Company;
- Identity;
- Authentication;
- Authorization;
- RBAC;
- idempotencia;
- optimistic locking;
- Outbox/Inbox;
- sync;
- Module Registry;
- ImplementationProfile;
- Web;
- proveedor cloud;
- cambios administrativos adicionales del repositorio.

## 11. Git

Base autorizada:

```text
3db050fdb8edfc442f0c1e67fef928185cbbf615
```

Rama:

```text
feat/platform-p1-core-runtime
```

Reglas:

1. implementar exclusivamente P-1;
2. commits pequeños;
3. push solo a esta rama;
4. sin merge/tag/force push/rebase destructivo;
5. no iniciar P-2 sin cierre expreso.

## 12. Gate de cierre

> **P-1 queda cerrable cuando el prototipo backend ha sido transformado en un Core Runtime neutral y modular, con bootstrap/configuración/API base/errores/transaction boundary/logging verificables, health endpoints read-only, sin secretos ni lógica de negocio, y con pruebas y evidencias primarias revisadas.**
