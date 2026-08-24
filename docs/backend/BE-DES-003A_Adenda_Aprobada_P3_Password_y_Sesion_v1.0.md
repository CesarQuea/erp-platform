# BE-DES-003A — Adenda aprobada P-3: Password y persistencia de sesión

**Versión:** 1.0
**Estado:** APROBADO / CONGELADO
**Fecha:** 2026-08-22
**Repositorio:** `CesarQuea/erp-platform`
**Rama:** `feat/platform-p3-identity-access`
**Base:** `128a7b17aeaf09d8c534f95e722e7d05fffbccbf`
**Contrato principal:** `BE-DES-003_Contrato_P3_Identity_Authentication_Authorization_v0.1.md`

---

## 1. Objeto

Esta adenda modifica y congela únicamente dos decisiones del contrato BE-DES-003 v0.1, por aprobación expresa del usuario:

1. política mínima de password;
2. persistencia de sesión en clientes first-party, especialmente Android.

En caso de contradicción, esta adenda prevalece sobre BE-DES-003 v0.1 exclusivamente en estos dos puntos.

---

## 2. Política de password aprobada

Se sustituye el mínimo inicial de 12 caracteres por la siguiente política:

- mínimo obligatorio: **8 caracteres**;
- la UI recomendará **12 o más caracteres**;
- se permitirán letras, números, símbolos, espacios y passphrases;
- no se impondrán reglas rígidas de composición como condición suficiente de seguridad;
- se rechazará password igual al login normalizado;
- la arquitectura deberá permitir rechazar passwords débiles/comunes sin acoplar la política al dominio;
- máximo permitido suficientemente amplio para passphrases; objetivo inicial: al menos 64 caracteres;
- hashing: **Argon2id**;
- password en texto plano nunca se persiste ni se registra en logs.

Los parámetros Argon2id quedan encapsulados detrás del `PasswordHasher` y configurados por servidor.

---

## 3. Mantener sesión iniciada

Para clientes first-party, la opción de UI equivalente a **“Mantener sesión iniciada”** NO significa guardar la contraseña.

Reglas:

1. el password nunca se almacena localmente para re-login automático;
2. el access token permanece efímero y de corta duración;
3. el cliente puede persistir el refresh token únicamente mediante almacenamiento seguro de plataforma;
4. en Android, el almacenamiento deberá estar protegido mediante mecanismos respaldados por **Android Keystore** en el corte de integración Android/Cloud;
5. P-3 no implementa Android, pero su contrato de tokens debe ser compatible con esta persistencia segura;
6. si el usuario desactiva “Mantener sesión iniciada”, el cliente no debe conservar el refresh token después de cerrar la sesión/aplicación según el contrato del cliente;
7. ningún refresh token se escribe en logs, analytics o almacenamiento inseguro.

---

## 4. Restauración del último contexto

Un cliente puede recordar localmente:

- `last_tenant_id`;
- `last_company_id`.

Estos valores:

- son preferencias de UX, no secretos;
- nunca constituyen autorización;
- no sustituyen los claims validados ni la autoridad global;
- deben ser revalidados por P-3 contra sesión, Membership y CompanyAccess antes de restaurar un contexto operativo.

Si el contexto recordado ya no es válido, el cliente deberá recibir/mostrar los contextos actualmente autorizados.

---

## 5. Experiencia esperada

### Usuario con un único contexto autorizado

```text
login inicial
  ↓
sesión + refresh token seguro
  ↓
contexto único validado
  ↓
acceso directo
```

En aperturas posteriores, si la sesión puede renovarse de forma segura, no se pide password nuevamente.

### Usuario con varios contextos

```text
login / refresh silencioso
  ↓
listar contextos autorizados
  ↓
restaurar último contexto si sigue autorizado
  ↓
si no, solicitar selección
```

---

## 6. Invariantes adicionales congeladas

1. “Recordar” o “Mantener sesión” nunca equivale a guardar password.
2. El password mínimo contractual de P-3 es 8 caracteres.
3. La recomendación UX es 12+ caracteres, no una obligación.
4. Android no conoce ni persiste credenciales PostgreSQL.
5. Android no decide qué base Tenant usar; P-3 valida contexto y P-2 resuelve el datasource.
6. `last_tenant_id`/`last_company_id` son hints de UX y siempre se revalidan.
7. Revocación de sesión/Membership/CompanyAccess debe impedir la restauración automática del contexto.

---

## 7. Alcance no modificado

Esta adenda NO cambia:

- identidad global única;
- Platform DB global;
- migraciones Platform separadas;
- JWT access token corto;
- refresh token opaco, rotatorio, hasheado y single-use;
- RBAC PLATFORM/TENANT/COMPANY;
- CompanyAccess explícito;
- selección de contexto autorizada;
- deny-by-default/fail-closed;
- exclusiones de Android, Sync, Web UI, MFA, SSO y módulos de negocio.

---

## 8. Aprobación

> **BE-DES-003 v0.1 queda aprobado y congelado junto con esta adenda BE-DES-003A v1.0. La implementación P-3 deberá respetar ambos documentos como una única autoridad contractual.**
