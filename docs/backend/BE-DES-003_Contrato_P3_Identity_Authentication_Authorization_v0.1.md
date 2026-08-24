# BE-DES-003 — Contrato P-3 Identity, Authentication, Membership y Authorization

**Versión:** 0.1
**Estado:** PROPUESTA PARA CONGELAR — IMPLEMENTACIÓN AÚN NO INICIADA
**Fecha:** 2026-08-22
**Repositorio:** `CesarQuea/erp-platform`
**Rama:** `feat/platform-p3-identity-access`
**Base autorizada:** `128a7b17aeaf09d8c534f95e722e7d05fffbccbf`

---

## 1. Objetivo

Implementar la autoridad global de identidad y la frontera de acceso de ERP Platform, manteniendo las invariantes cerradas en P-1 y P-2.

P-3 debe permitir que una identidad global autenticada pueda:

1. iniciar y cerrar sesiones de forma segura;
2. pertenecer a uno o varios Tenants mediante `Membership` explícito;
3. acceder únicamente a Companies expresamente habilitadas dentro de cada Tenant;
4. recibir roles/permisos con scope PLATFORM, TENANT o COMPANY;
5. seleccionar un contexto Tenant/Company únicamente si ese contexto está autorizado;
6. producir un `AuthenticatedPrincipal` verificable por los módulos futuros;
7. construir `TenantContext`/Company context desde autoridad autenticada, nunca desde un header público por sí solo;
8. revocar sesiones, memberships y permisos de forma fail-closed.

P-3 no implementa todavía módulos de negocio ni sincronización móvil.

---

## 2. Principios de diseño

P-3 toma como referencia las filosofías maduras de ERP de separar:

- usuario/identidad;
- pertenencia a la organización operativa;
- acceso multiempresa;
- roles/grupos;
- permisos;
- contexto activo de operación.

Se adapta esa filosofía a la arquitectura propia ya cerrada de ERP Platform:

```text
Global Identity Authority
        │
        ├── UserAccount
        ├── AuthSession
        ├── TenantMembership
        ├── CompanyAccess
        ├── Role / Permission
        │
        ▼
AuthenticatedPrincipal
        │
        ├── TenantContext
        └── CompanyContext
                │
                ▼
        Tenant PostgreSQL DB
```

No se copia literalmente el modelo de ningún ERP comercial.

---

## 3. Decisión fundamental: autoridad global

La identidad es global para toda la plataforma.

```text
UserAccount U1
├── Membership Tenant A
│   ├── Company A1
│   └── Company A2
└── Membership Tenant B
    └── Company B1
```

Invariantes:

1. `UserAccount` no se duplica por Tenant;
2. una misma identidad puede pertenecer a múltiples Tenants;
3. los Tenant DB no almacenan credenciales ni hashes de password;
4. los módulos de negocio no administran usuarios;
5. la autoridad de identidad permanece fuera de los Tenant DB físicos;
6. conocer un `tenant_id`, `company_id` o `user_id` no concede acceso.

---

## 4. Persistencia global de plataforma

P-3 utilizará la base global configurada mediante `DATABASE_URL` como **Platform/Identity Database**.

Esta base ya existe conceptualmente en P-1 como datasource global de readiness y en P-3 pasa a alojar persistencia de identidad.

No se reutiliza ninguna Tenant DB para identidad global.

### 4.1 Migraciones

Las migraciones globales de plataforma tendrán un flujo Alembic separado de las migraciones Tenant P-2.

Propuesta física:

```text
alembic-platform.ini
platform_migrations/
├── env.py
└── versions/
    └── 0001_p3_identity_access.py
```

El árbol P-2:

```text
alembic.ini
migrations/
```

continúa siendo autoridad de schema por Tenant y no se reinterpreta.

Prohibido:

- ejecutar migraciones automáticamente al arrancar FastAPI;
- usar `create_all()` como autoridad de schema;
- mezclar migraciones globales y Tenant en una única transacción.

---

## 5. Entidades globales mínimas

P-3 implementará, como mínimo, estructuras conceptualmente equivalentes a:

```text
user_accounts
password_credentials
auth_sessions
refresh_tokens
tenant_memberships
membership_company_access
roles
permissions
role_permissions
principal_role_assignments
```

Los nombres físicos podrán ajustarse durante implementación únicamente si preservan este contrato.

---

## 6. UserAccount

Representa la identidad humana global.

Campos mínimos:

```text
id
login
login_normalized
display_name
email
status
created_at
updated_at
```

Reglas:

- `id`: UUID estable;
- `login_normalized`: único global;
- `login`: identificador humano de autenticación;
- `email`: dato de contacto; puede coincidir con login;
- `status`: ACTIVE, SUSPENDED o DISABLED;
- no existe `tenant_id` ni `company_id` en `user_accounts`;
- el login se normaliza de forma determinista antes de comparar;
- nunca se persiste password en texto plano.

No se implementa auto-registro público.

---

## 7. PasswordCredential

Las credenciales password se almacenan separadas de `UserAccount`.

P-3 utilizará **Argon2id** para hashing.

Reglas:

1. password en texto plano solo vive durante la operación de autenticación/provisioning;
2. se almacena únicamente el hash Argon2id;
3. hashes y passwords nunca se escriben en logs;
4. un cambio de password invalida las sesiones activas del usuario;
5. password mínimo inicial: 12 caracteres;
6. no se imponen reglas artificiales de mayúsculas/símbolos como sustituto de longitud;
7. el algoritmo/parámetros deben quedar encapsulados detrás de un `PasswordHasher` port.

Recuperación de password por correo, email verification y MFA quedan fuera de P-3.

---

## 8. Authentication Session

Una autenticación correcta crea una sesión global por dispositivo/cliente.

Conceptualmente:

```text
AuthSession
├── session_id
├── user_id
├── created_at
├── last_seen_at
├── expires_at
├── revoked_at
└── client metadata mínima
```

Reglas:

- múltiples sesiones por usuario son válidas;
- logout revoca solo la sesión actual salvo operación administrativa explícita;
- cambio de password o suspensión del usuario revoca todas sus sesiones;
- sesión expirada/revocada falla de forma cerrada;
- metadata de cliente no debe convertirse en huella invasiva del usuario.

---

## 9. Access token

P-3 utilizará access tokens JWT de corta duración para las APIs first-party.

Algoritmo inicial propuesto:

```text
HS256
```

con secreto criptográficamente fuerte fuera de Git y algoritmo fijado por configuración segura, sin aceptar algoritmos arbitrarios desde el token.

TTL inicial propuesto:

```text
15 minutos
```

Claims mínimos:

```text
iss
aud
sub       = user_id
sid       = auth_session_id
jti
iat
exp
tenant_id    opcional
company_id   opcional
```

Reglas:

1. no incluir password, hash, email ni DSN;
2. token sin Tenant/Company es `identity-context` y solo puede usar endpoints de autenticación/contexto;
3. token con Tenant/Company es `operational-context`;
4. un token firmado no basta por sí solo si la sesión o membership ya fue revocada;
5. cada request protegido valida sesión/usuario y autorización activa en la autoridad global;
6. expiración y firma se validan antes de confiar en claims;
7. `tenant_id`/`company_id` del token no se reemplazan por headers públicos.

La migración futura a firma asimétrica podrá realizarse mediante contrato versionado sin cambiar la semántica de identidad/contexto.

---

## 10. Refresh token

El refresh token será **opaco y aleatorio**, no JWT.

Reglas:

1. generado con CSPRNG;
2. se entrega al cliente una sola vez;
3. en DB se guarda únicamente un hash SHA-256 del token;
4. refresh token single-use;
5. cada refresh rota el token;
6. reutilización de un refresh ya consumido se considera replay y revoca la familia/sesión según política;
7. logout revoca refresh tokens activos de la sesión;
8. ningún refresh token se escribe en logs;
9. TTL inicial propuesto: 30 días, configurable.

La adaptación Web a cookie `HttpOnly/Secure/SameSite` queda para el adapter Web; el modelo de sesión/refresh permanece transport-neutral.

---

## 11. TenantMembership

`TenantMembership` es la única relación que habilita a una identidad global a pertenecer a un Tenant.

Campos mínimos:

```text
id
user_id
tenant_id
status
created_at
updated_at
```

Estados:

```text
ACTIVE
SUSPENDED
REVOKED
```

Invariantes:

- unique `(user_id, tenant_id)`;
- membership ausente/inactiva → acceso denegado;
- no existe membership implícita;
- no existe Tenant por defecto silencioso;
- el Tenant debe existir/estar configurado en `TenantRegistry`;
- revocación de membership invalida inmediatamente el acceso a ese Tenant.

`INVITED` y flujo de invitación por correo quedan fuera de P-3.

---

## 12. CompanyAccess

Dentro de un Tenant, el acceso multiempresa debe ser explícito.

```text
Membership
├── Company A
└── Company B
```

La tabla conceptual `membership_company_access` contiene:

```text
membership_id
company_id
status
created_at
updated_at
```

Reglas:

- unique `(membership_id, company_id)`;
- Company debe pertenecer físicamente al Tenant de la membership;
- al conceder acceso se valida Company contra el datasource Tenant P-2;
- no existe FK SQL cross-database entre la autoridad global y Tenant DB;
- Company inactiva o inexistente no puede convertirse en contexto operativo;
- conocimiento de `company_id` no concede acceso;
- CompanyAccess no sustituye permisos: acceso y autorización son controles independientes.

---

## 13. Roles y Permissions

P-3 introduce RBAC genérico y reusable.

### 13.1 Permission

`Permission` utiliza códigos técnicos estables en inglés:

```text
identity.user.read
identity.user.manage
identity.membership.read
identity.membership.manage
identity.role.read
identity.role.manage
```

Los módulos futuros podrán agregar sus propios códigos sin modificar el motor de autorización.

P-3 no define permisos `milking.*`, `inventory.*`, etc.

### 13.2 Role

Un Role agrupa Permissions.

Puede ser:

```text
PLATFORM
TENANT
COMPANY
```

Los roles no contienen lógica sectorial.

### 13.3 PrincipalRoleAssignment

Asigna un Role a un User con scope explícito:

```text
user_id
role_id
tenant_id nullable
company_id nullable
```

Reglas:

- PLATFORM → tenant/company null;
- TENANT → tenant requerido, company null;
- COMPANY → tenant y company requeridos;
- una asignación Tenant/Company no sustituye membership activa;
- autorización siempre intersecta rol + membership + company access cuando corresponda;
- no existe permiso por simple coincidencia de UUID.

---

## 14. AuthorizationService

Debe existir una única frontera de autorización de plataforma.

Conceptualmente:

```text
AuthenticatedPrincipal
        ↓
AuthorizationService
        ↓
require(permission_code, scope)
```

Reglas:

1. deny-by-default;
2. permiso desconocido → deny;
3. usuario/sesión/membership inactivos → deny;
4. Company fuera del acceso permitido → deny;
5. rol fuera del scope actual → no concede permiso;
6. ningún módulo consulta directamente tablas RBAC;
7. ningún endpoint de negocio implementa condicionales hardcodeados por nombre de usuario/empresa;
8. no existe bypass sectorial.

---

## 15. AuthenticatedPrincipal y contextos

P-3 incorporará una representación explícita del principal autenticado.

Conceptualmente:

```text
AuthenticatedPrincipal
├── user_id
├── session_id
├── tenant_id optional
├── company_id optional
└── effective_permissions
```

Los adapters HTTP construyen este principal únicamente después de validar:

- token;
- sesión;
- usuario;
- membership;
- company access;
- roles/permisos.

Cuando existe contexto operativo:

```text
AuthenticatedPrincipal
        ↓
TenantContext(tenant_id)
        ↓
TenantDataSourceResolver P-2
```

El `CompanyContext` debe ser explícito para los casos de uso company-scoped.

---

## 16. Selección de contexto

P-3 no acepta `X-Tenant-ID` ni `X-Company-ID` como autoridad de seguridad por sí solos.

Flujo previsto:

```text
login global
   ↓
identity-context token
   ↓
listar contextos autorizados
   ↓
seleccionar Tenant/Company
   ↓
validar Membership + CompanyAccess
   ↓
operational-context access token
```

Cambiar de Company/Tenant requiere una nueva selección autorizada de contexto.

Un header podrá existir en el futuro como conveniencia de routing solo si se contrasta contra el principal autenticado; nunca será autoridad primaria.

---

## 17. API HTTP P-3

Endpoints mínimos:

```text
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
GET  /api/v1/auth/contexts
POST /api/v1/auth/context
```

### 17.1 Login

Input mínimo:

```text
login
password
```

Respuesta exitosa:

- access token identity-context;
- refresh token;
- metadata mínima de expiración/session.

Error de login debe ser genérico y no permitir enumerar si el usuario existe.

### 17.2 Contexts

Devuelve exclusivamente Tenants/Companies autorizados para el usuario autenticado.

No devuelve:

- passwords;
- hashes;
- DSN;
- secretos;
- roles internos no necesarios para UI.

### 17.3 Context selection

Recibe Tenant/Company solicitado, lo valida y emite access token de contexto operativo.

---

## 18. Provisioning inicial

No habrá auto-registro público.

P-3 incluirá un mecanismo interno/CLI para:

- crear el primer usuario administrador;
- crear usuarios;
- crear/activar memberships;
- conceder CompanyAccess;
- asignar roles.

El provisioning debe:

- usar los mismos application services que la plataforma;
- ser idempotente donde corresponda;
- no hardcodear Aliosur;
- no imprimir passwords/hashes/tokens;
- no saltarse invariantes de Tenant/Company.

Una UI administrativa queda fuera de P-3.

---

## 19. Atomicidad

Operaciones globales de identidad deben ser transaccionales en Platform DB.

Ejemplos:

```text
create_user + password credential
create_membership
assign_role
rotate_refresh_token
revoke_session
```

Cada operación:

```text
BEGIN
validate
write
COMMIT
```

ante error:

```text
ROLLBACK
```

No se implementan transacciones distribuidas Platform DB ↔ Tenant DB.

Cuando una operación necesite validar Company en Tenant DB:

1. valida lectura en Tenant DB;
2. realiza escritura global en una transacción separada;
3. revalida fail-closed al seleccionar contexto.

---

## 20. Idempotencia y concurrencia

P-3 debe proteger integridad mediante constraints y operaciones atómicas.

Obligatorio:

- unique login normalizado;
- unique membership usuario/Tenant;
- unique company access;
- unique role assignment lógico;
- refresh single-use atómico;
- dos refresh concurrentes con el mismo token no pueden producir dos cadenas válidas independientes;
- logout repetido es idempotente;
- revocar una sesión ya revocada no genera estado inconsistente;
- dos altas concurrentes del mismo login producen una sola identidad válida.

El framework general de command idempotency para módulos de negocio permanece fuera de P-3.

---

## 21. Revocación

Debe existir revocación efectiva de:

- sesión;
- todas las sesiones de un usuario;
- membership Tenant;
- CompanyAccess;
- role assignment.

Un access token firmado no puede conservar acceso si la autoridad global indica que la sesión/membership fue revocada.

P-3 prioriza seguridad y corrección sobre un JWT completamente stateless.

Optimización/caching distribuido se podrá añadir posteriormente preservando semántica fail-closed.

---

## 22. Seguridad

Invariantes obligatorias:

1. secretos fuera de Git;
2. JWT signing secret fuera de logs/API;
3. password/hash fuera de logs/API;
4. refresh token solo se almacena hasheado;
5. errores de login genéricos;
6. no stack traces al cliente;
7. no enumeración de usuario por diferencias funcionales deliberadas;
8. CORS/HTTPS de producción pertenece al deployment, pero P-3 no debe asumir HTTP inseguro;
9. token expirado/inválido → 401;
10. autenticado sin permiso → 403;
11. contexto Tenant/Company inválido o no autorizado → 403/404 según política uniforme, sin filtrar existencia sensible;
12. ninguna credencial se recibe por query string.

Rate limiting distribuido, CAPTCHA, WAF y detección avanzada de fraude quedan fuera de P-3.

---

## 23. Auditoría mínima de seguridad

P-3 registrará eventos técnicos estructurados sin secretos para:

- login success/failure;
- refresh success/replay;
- logout;
- session revoke;
- membership grant/revoke;
- company access grant/revoke;
- role assignment/revoke;
- context selection denied.

La auditoría de negocio general permanece fuera de P-3/P-4 según planificación posterior.

---

## 24. Compatibilidad P-1/P-2

P-3 debe preservar:

- `/live`;
- `/ready`;
- `/health`;
- error envelope;
- correlation ID;
- TransactionBoundary Core;
- TenantContext;
- TenantRegistry;
- TenantDataSourceResolver;
- DB física por Tenant;
- metadata física Tenant;
- Company;
- Alembic por Tenant;
- ausencia de `tenant_id` redundante en `companies`.

La Platform DB puede contener tablas P-3; esto no modifica el schema de ninguna Tenant DB salvo migraciones expresamente autorizadas, que en P-3 no deberían ser necesarias.

---

## 25. Integración con módulos futuros

Los módulos futuros, incluido Ordeño/Milking, recibirán un principal ya autenticado/autorizado.

Un módulo NO debe:

- autenticar passwords;
- validar JWT directamente;
- consultar tablas de sesiones;
- decidir membership;
- construir TenantContext desde request raw;
- duplicar CompanyAccess;
- hardcodear roles sectoriales en Core.

El flujo esperado será:

```text
HTTP
 ↓
Authentication/Authorization P-3
 ↓
AuthenticatedPrincipal
 ↓
TenantContext + CompanyContext
 ↓
Use case del módulo
```

---

## 26. Pruebas obligatorias

### 26.1 Unit

- login normalization;
- password hashing/verification;
- password policy;
- token encode/decode;
- token expiry/issuer/audience;
- refresh hashing/rotation;
- membership validation;
- company access validation;
- RBAC scope evaluation;
- deny-by-default.

### 26.2 Integration — Platform PostgreSQL real

Desde DB global vacía:

- `alembic-platform upgrade head`;
- schema esperado;
- crear usuario/credential;
- crear dos memberships;
- crear company accesses;
- roles/permisos/assignments;
- sesiones/refresh.

### 26.3 Integration — dos Tenant DB P-2

Con Tenant A y Tenant B físicos:

- mismo usuario global accede a ambos solo con membership;
- Company A no puede seleccionarse bajo Tenant B;
- Company no autorizada falla;
- Tenant desconocido falla;
- Company inactiva falla.

### 26.4 Authentication

- password correcto;
- password incorrecto;
- usuario inexistente con respuesta indistinguible funcionalmente;
- usuario suspended/disabled;
- token expirado;
- firma inválida;
- issuer/audience inválidos;
- sesión revocada.

### 26.5 Refresh / concurrency

- rotación correcta;
- token anterior deja de ser válido;
- replay detectado;
- dos refresh concurrentes no generan dos ramas válidas;
- logout invalida refresh;
- cambio de password revoca sesiones.

### 26.6 Authorization

- PLATFORM role;
- TENANT role;
- COMPANY role;
- role de otro Tenant no aplica;
- role de otra Company no aplica;
- permission desconocido → deny;
- membership revocada → deny inmediato;
- CompanyAccess revocado → deny.

### 26.7 API

- login;
- me;
- contexts;
- context selection;
- refresh;
- logout;
- 401 vs 403 coherentes;
- no secretos en body/headers/logs.

### 26.8 Regression

- suite P-1 + P-2 completa;
- PostgreSQL Tenant isolation P-2;
- Docker build/run;
- health/readiness.

---

## 27. Evidencias obligatorias de cierre

El verificador independiente deberá aportar:

- base/HEAD exactos;
- diff real;
- `git diff --check`;
- pytest + JUnit XML;
- Platform PostgreSQL real;
- migración global real;
- dos Tenant DB P-2 para pruebas de contexto;
- hash password/refresh verificados sin exponer secretos;
- revocación real;
- refresh replay/concurrency;
- cross-Tenant/cross-Company;
- RBAC por scope;
- API auth real;
- Docker build/run;
- secret scan;
- scope scan;
- working tree limpio.

No se acepta solo `BUILD SUCCESSFUL` ni un resumen del agente.

---

## 28. Exclusiones expresas

P-3 NO implementa:

- SSO/OIDC/SAML;
- MFA/TOTP/WebAuthn;
- password reset por email;
- email verification;
- invitaciones por correo;
- registro público;
- API keys;
- service accounts;
- OAuth authorization server;
- social login;
- SCIM;
- LDAP/Active Directory;
- UI administrativa;
- Web UI;
- Milking;
- Inventory;
- Manufacturing;
- Sales;
- Livestock;
- lógica Dairy/Aliosur;
- sync Android;
- Outbox/Inbox;
- command idempotency general de negocio;
- optimistic locking general;
- Control Plane persistente completo para TenantRegistry;
- billing;
- intercompany;
- consolidación contable.

---

## 29. Invariantes no negociables

1. Identidad global única; no usuario duplicado por Tenant.
2. Password/credential nunca reside en Tenant DB.
3. Membership activa requerida para acceso Tenant.
4. CompanyAccess activo requerido para contexto Company.
5. Roles/permisos respetan scope.
6. Deny-by-default.
7. Access token no sustituye revocación global.
8. Refresh token opaco, hasheado, rotatorio y single-use.
9. Tenant/Company no se autorizan solo por header o UUID conocido.
10. Los módulos de negocio no implementan autenticación/autorización propia.
11. Platform migrations y Tenant migrations permanecen separadas.
12. No `create_all()` productivo.
13. No secretos en Git/logs/respuestas.
14. No lógica Aliosur/Dairy en Core/Identity.
15. P-1 y P-2 no se rompen.
16. No cambios Android en P-3.
17. Cualquier cambio de estas invariantes requiere autorización expresa.

---

## 30. Secuencia Git

1. base P-3: `128a7b17aeaf09d8c534f95e722e7d05fffbccbf`;
2. rama: `feat/platform-p3-identity-access`;
3. Draft PR propio;
4. este contrato debe ser aprobado/congelado antes de código funcional;
5. implementación en commits pequeños;
6. push solo a rama P-3;
7. revisión estática del diff real;
8. verificación independiente;
9. cierre únicamente por autorización del usuario;
10. merge a `main` únicamente por autorización separada.

---

## 31. Decisiones propuestas que requieren aprobación para congelar P-3

Las siguientes decisiones quedan propuestas y deben considerarse aprobadas expresamente antes de implementar:

1. **Autoridad global**: User/credentials/sessions/memberships/RBAC viven en Platform DB global, no en Tenant DB.
2. **Platform DB**: `DATABASE_URL` pasa a ser la persistencia global de identidad/control de acceso, manteniendo health/readiness P-1.
3. **Migraciones separadas**: `platform_migrations` independiente de `migrations` Tenant P-2.
4. **Password**: Argon2id, mínimo 12 caracteres.
5. **Tokens**: access JWT HS256 de 15 min + refresh opaco rotatorio de 30 días almacenado como hash.
6. **Revocación**: cada request protegido revalida sesión/membership/authorization global; JWT no es autoridad stateless absoluta.
7. **RBAC**: Permission + Role con scopes PLATFORM/TENANT/COMPANY.
8. **CompanyAccess**: acceso a Companies explícito e independiente del rol.
9. **Context selection**: login global → contextos autorizados → token operativo Tenant/Company.
10. **Sin auto-registro**: alta inicial/administrativa mediante servicios/CLI internos.

---

## 32. Gate de cierre

> **P-3 será cerrable cuando ERP Platform demuestre, con Platform PostgreSQL y dos Tenant DB reales, que una identidad global puede autenticarse, mantener sesiones y refresh tokens seguros, pertenecer a múltiples Tenants, seleccionar únicamente Companies autorizadas, recibir permisos con scope correcto y ser revocada de forma fail-closed; preservando P-1/P-2, sin duplicar credenciales por Tenant, sin confiar en headers públicos y sin introducir lógica sectorial.**
