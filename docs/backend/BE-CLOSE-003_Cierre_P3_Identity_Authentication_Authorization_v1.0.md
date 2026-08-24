# BE-CLOSE-003 — Cierre P-3 Identity, Authentication, Membership & Authorization

**Versión:** 1.0  
**Estado:** CERRADO  
**Fecha de cierre:** 2026-08-23  
**Repositorio:** `CesarQuea/erp-platform`  
**Rama:** `feat/platform-p3-identity-access`  
**Draft PR:** #3  
**Base autorizada:** `128a7b17aeaf09d8c534f95e722e7d05fffbccbf`  
**HEAD funcional verificado:** `97b9d939e3bd5c554fffe90515c77beb764b5c84`  
**Reporte consolidado:** `docs/backend/verification/P3/Reporte_Verificacion_Final_P3.md`  
**Commit de archivo del reporte:** `3c41f9610b8b3ac59e8343aaadbfbccee223f5e3`

---

## 1. Objeto del cierre

Formalizar el cierre del corte **P-3 — Identity, Authentication, Membership & Authorization** de ERP Platform, después de contrastar independientemente:

- contrato `BE-DES-003`;
- adenda aprobada `BE-DES-003A`;
- código y diff real contra la base autorizada;
- Platform DB y migración Alembic separada;
- password hashing Argon2id;
- JWT access token;
- refresh token opaco, rotatorio y single-use;
- replay y revocación de sesión/familia;
- Membership y CompanyAccess;
- selección de contexto Tenant/Company;
- RBAC con scopes PLATFORM/TENANT/COMPANY;
- revocación inmediata/fail-closed;
- Company inactiva;
- auditoría runtime;
- Docker/PostgreSQL;
- regresión P-1/P-2;
- XML JUnit y evidencias primarias.

El cierre fue autorizado expresamente por el usuario el **2026-08-23**.

---

## 2. Alcance cerrado

P-3 deja implementado y cerrado:

- identidad global única mediante `UserAccount`;
- credencial de password separada mediante `PasswordCredential`;
- hashing Argon2id;
- política de password con mínimo obligatorio de 8 caracteres y recomendación UX de 12+;
- sesiones globales `AuthSession`;
- access token JWT HS256 corto con issuer/audience/expiración;
- refresh token opaco, aleatorio, almacenado solo como hash, rotatorio y single-use;
- detección de replay de refresh;
- revocación de refresh family y sesión ante replay;
- evento de auditoría `refresh_replay_detected` sin secretos;
- `TenantMembership`;
- `CompanyAccess`;
- selección explícita de contexto Tenant/Company;
- `AuthenticatedPrincipal`;
- RBAC genérico con `Permission`, `Role`, `RoleAssignment`;
- scopes `PLATFORM`, `TENANT` y `COMPANY`;
- autorización deny-by-default;
- revocación efectiva de Membership, CompanyAccess, sesión y roles;
- Platform Identity DB global separada de Tenant DB;
- Alembic Platform separado de Alembic Tenant;
- migración `0001_p3_identity_access`;
- CLI administrativo interno sin password en argumentos;
- endpoints:
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/refresh`
  - `POST /api/v1/auth/logout`
  - `GET /api/v1/auth/me`
  - `GET /api/v1/auth/contexts`
  - `POST /api/v1/auth/context`;
- sanitización de errores 422 para no reflejar inputs sensibles;
- logging JSON con allowlist de metadatos seguros;
- preservación de loggers de aplicación durante Platform Alembic.

---

## 3. Invariantes cerradas

Quedan congeladas para cortes posteriores las siguientes invariantes:

1. La identidad del usuario es global y no se duplica por Tenant.
2. Passwords/credenciales no se almacenan en las Tenant DB.
3. `TenantMembership` determina pertenencia a Tenant.
4. `CompanyAccess` determina acceso explícito a Company.
5. `CompanyAccess` y `Role` son responsabilidades distintas: dónde puede entrar vs. qué puede hacer.
6. Los scopes globales de autorización de plataforma son `PLATFORM`, `TENANT` y `COMPANY`.
7. La autorización es fail-closed y deny-by-default.
8. UUID/header no constituyen autorización por sí solos.
9. La autoridad global debe validarse antes de tocar el datasource Tenant solicitado cuando Membership/CompanyAccess no autoriza el contexto.
10. Un contexto operacional requiere Tenant + Company autorizados.
11. Una Company inexistente o inactiva no puede producir token operacional.
12. Access token válido criptográficamente no es autoridad suficiente si sesión/usuario/Membership/CompanyAccess han sido revocados.
13. Refresh token es single-use y rotatorio; replay revoca familia/sesión según la política cerrada.
14. Password nunca se persiste en plaintext ni se utiliza como mecanismo de “recordarme”.
15. “Mantener sesión iniciada” en clientes first-party se implementará mediante refresh token seguro, no guardando password.
16. Platform Alembic y Tenant Alembic permanecen separados.
17. Platform Alembic no debe deshabilitar loggers existentes de la aplicación.
18. P-3 permanece neutral y sin lógica Aliosur/Dairy/Milking/Inventory hardcodeada.
19. P-3 no introduce `Site` ni `OperationalUnit` como scopes de autenticación/autorización; cualquier decisión transversal futura sobre esos conceptos requiere contrato/ADR separado.

Cualquier modificación posterior de estas invariantes requiere contrato/corrección expresamente autorizada.

---

## 4. Exclusiones preservadas

P-3 no implementa ni autoriza todavía:

- auto-registro público;
- recuperación de password por correo;
- MFA;
- SSO/OIDC/OAuth externo;
- LDAP/Active Directory;
- API keys;
- service accounts;
- UI Android de autenticación cloud;
- Web UI;
- sincronización Android ↔ Cloud;
- almacenamiento Android/Keystore efectivo;
- permisos sectoriales `milking.*`, `inventory.*`, etc.;
- Milking;
- Inventory;
- Manufacturing;
- Sales;
- Livestock;
- lógica Aliosur/Dairy;
- Redis/cache de autorización;
- infraestructura HA/backup productivo;
- cloud provider específico;
- `Site`/`OperationalUnit` como jerarquía universal del Core.

---

## 5. Evidencias finales

La verificación final se consolidó sobre:

```text
Base: 128a7b17aeaf09d8c534f95e722e7d05fffbccbf
HEAD funcional verificado: 97b9d939e3bd5c554fffe90515c77beb764b5c84
```

Resultados finales:

```text
git diff --check                 PASS
focales finales                  3/3 PASS
suite completa                   53/53 PASS
JUnit failures                   0
JUnit errors                     0
JUnit skipped                    0
compileall                       PASS
Platform Alembic                 PASS
revision Platform                0001_p3_identity_access
logger preservation              PASS
Docker build/run                 PASS
/api/v1/health                   200 PASS
/api/v1/live                     200 PASS
/api/v1/ready                    200 PASS
refresh rotation                 PASS
refresh replay                   401 PASS
session revoked post-replay      PASS
refresh_replay_detected          PASS
Company inactive                 403 ACCESS_DENIED PASS
operational token inactive Co.   NO emitido PASS
audit runtime                    PASS
P-1/P-2 regression               PASS
secret/evidence hygiene          PASS
working tree                     limpio
```

El reporte consolidado queda archivado en:

`docs/backend/verification/P3/Reporte_Verificacion_Final_P3.md`

---

## 6. Trazabilidad de evidencia externa

Paquete final complementario:

```text
EVIDENCIAS_P3_FINAL_AFTER_LOGGING_FIX_97b9d939.zip
SHA-256: b1f98b48d06cc97bd4bfc3bb377b47b2c2e74412e600fff7fab59ec319d0b038
```

El paquete contiene XML JUnit, logs, evidencia Alembic/logger, Docker, refresh/replay, Company inactive, auditoría y postcheck Git.

Git, contratos, código, diff y reporte archivado son la referencia principal; el ZIP es evidencia complementaria.

---

## 7. Revisión independiente

La revisión independiente no aceptó automáticamente los informes del agente.

Durante P-3 se detectaron y resolvieron, entre otros:

- persistencia correcta de revocación ante refresh replay;
- autorización global antes de acceder al datasource Tenant solicitado;
- sanitización de errores 422;
- logging seguro con allowlist;
- Company inactiva;
- evidencia dinámica de refresh rotation/replay;
- captura explícita de `refresh_replay_detected`;
- interacción de `logging.config.fileConfig()` con loggers existentes durante Alembic.

La corrección final de logging/Alembic se validó con focales y suite completa verde.

No quedan hallazgos de implementación bloqueantes para P-3.

---

## 8. Decisión de cierre

Con base en BE-DES-003, BE-DES-003A, Git real, código, diff y evidencias contrastadas:

> **P-3 — Identity, Authentication, Membership & Authorization queda CERRADO.**

Este cierre congela el comportamiento e invariantes verificados del corte.

---

## 9. Estado Git posterior al cierre

El HEAD funcional verificado permanece:

`97b9d939e3bd5c554fffe90515c77beb764b5c84`

Los commits posteriores a ese SHA son exclusivamente documentales de archivo/cierre y no deben modificar código productivo, migraciones ni tests.

El Draft PR #3 debe permanecer sin merge hasta autorización expresa separada.

Este cierre NO autoriza automáticamente:

- merge del PR #3 a `main`;
- tag/release;
- rebase o force push;
- inicio de P-4;
- inicio de O-4;
- cambios adicionales de código en la rama P-3.

---

## 10. Siguiente paso

Antes de iniciar un nuevo corte de ERP Platform deberá:

1. autorizarse expresamente el merge de P-3 a `main`;
2. obtenerse el SHA exacto resultante de `main`;
3. autorizarse ese SHA como base del siguiente corte;
4. congelarse el contrato del siguiente corte;
5. crear rama y Draft PR propios.

La decisión transversal sobre `Site/OperationalUnit`, tratada durante la puesta en operación de Milking, no modifica retroactivamente el código funcional de P-3. Su aclaración arquitectónica deberá quedar en contrato/ADR separado antes de introducir esos conceptos en futuros cortes de plataforma.

---

## 11. Regla final

> **P-3 queda cerrado sobre el HEAD funcional `97b9d939e3bd5c554fffe90515c77beb764b5c84`, con verificación consolidada PASS y autorización expresa del usuario. El PR #3 permanece Draft y sin merge hasta autorización separada.**
