# BE-MLK-CLOSE-004 — Cierre O-4 Backend Cloud Milking GENERAL

**Versión:** v1.0  
**Fecha:** 2026-08-26  
**Proyecto:** AliosurERP18  
**Repositorio:** `CesarQuea/erp-platform`  
**Corte:** O-4 — Backend Cloud Milking GENERAL  
**Estado:** CERRADO / CONGELADO / PENDIENTE DE MERGE AUTORIZADO

## 1. Identificación del corte

- Base autorizada: `8cdd0ee47db9569ca6fcec4530f3c3dffb9390ed`
- Rama: `feat/milking-o4-backend-cloud-general`
- Draft PR: `#8`
- HEAD técnico final aprobado: `dac40376ae8161d46e844b5f339cdc427923af8d`
- HEAD documental previo al acta: `f541ada212ff8e0d6eb2323db4458b49ff8da2ac`
- Contrato: `docs/backend/BE-MLK-DES-004_Contrato_O4_Backend_Cloud_Milking_GENERAL_v0.1.md`

El usuario autorizó expresamente el cierre de O-4 después de la revisión independiente de las evidencias R2.

## 2. Resultado técnico consolidado

La revisión independiente de `EVIDENCIAS_O4_R2_dac40376.zip` y el contraste posterior con Git/código/diff concluyeron PASS técnico para O-4.

### Gates principales

- Focales O-4: 49/49 PASS.
- Replay R2 específico: 1/1 PASS.
- PostgreSQL O-4 + concurrencia: 18/18 PASS.
- Alembic + forward migration: 3/3 PASS.
- P-3 real end-to-end: 2/2 PASS.
- P-4 PostgreSQL: 9/9 PASS.
- Suite completa: 157/157 PASS.
- Failures: 0.
- Errors: 0.
- Skipped: 0.
- Compile: PASS.
- Docker build/run: PASS.
- `/api/v1/health`: PASS.
- `/api/v1/live`: PASS.
- `/api/v1/ready`: PASS.
- Git working tree postcheck: limpio.

## 3. Decisiones e invariantes congeladas

1. Jerarquía transversal: `Tenant -> Company`.
2. Milking referencia `Farm`; no crea maestro `milking_farms`.
3. Product/UoM son referencias externas; no maestros sombra.
4. `OutputProfile` pertenece a Milking y es versionado.
5. `MilkingConfiguration = Company + Farm + Shift -> OutputProfileVersion`.
6. La sesión snapshottea Profile/Product/UoM al CREATE.
7. Identidad operacional activa: `Tenant DB + Company + Farm + Date + Shift`.
8. `CANCELLED` libera identidad operacional.
9. Cantidades: PostgreSQL `NUMERIC` / Python `Decimal`.
10. `MilkingOutput = 0..1` por Session; solo existe si neto > 0.
11. `MilkingOutput` representa producción propia confirmada y no es stock.
12. Compra de leche pertenece a Purchase; no crea `MilkingSession` ni `MilkingOutput`.
13. Milk Logistics/Reception/Quality/Inventory permanecen downstream.
14. Actor deriva de P-3; `localEmployeeId` no existe en Cloud.
15. P-4 gobierna command_id, fingerprint, replay, idempotencia, CAS y audit técnico.
16. Milking mantiene business audit append-only.
17. No se reintroducen `Site`, `OperationalUnit`, `ProductionUnit`, Plant, Warehouse ni Location en Milking.
18. No existe `Organization` cloud obligatoria por simetría con Android.
19. API Milking usa endpoints específicos de dominio; no `/commands` genérico.
20. Outbox/Inbox y Android<->Cloud Sync quedan fuera de O-4.

## 4. Migraciones

Cadena Tenant aprobada:

`0001_p2_tenant_company -> 0002_p4_command_execution -> 0003_o4_milking_general -> 0004_o4_milking_lifecycle_hardening`

Se mantiene el revision ID `0004_o4_milking_lifecycle_hardening`. La migración O-4 `0003` amplía `alembic_version.version_num` para soportarlo sin modificar `migrations/env.py`.

## 5. Concurrencia e idempotencia

Quedaron verificados en PostgreSQL real:

- CREATE concurrente misma identidad: máximo un ganador.
- Farms distintas mismo Date/Shift: ambas válidas.
- mismo command_id + payload idéntico: replay sin doble efecto.
- mismo command_id + payload diferente: `IDEMPOTENCY_CONFLICT`.
- updates con mismo expectedVersion: máximo un ganador.
- CONFIRM concurrente: máximo un DONE y 0..1 Output.
- replay CONFIRM: no duplica Output ni business audit.
- CONFIRM vs CANCEL: una transición válida y conflicto explícito para la otra.
- aislamiento entre Companies.
- aislamiento entre Tenant DB.
- rollback no deja mutación/audit/claim P-4 parcial.

## 6. Observaciones LOW aceptadas

Quedan registradas como LOW y no bloqueantes:

1. algunos archivos del paquete del agente registraron `True/False` en lugar de exit codes numéricos;
2. `git branch --show-current` quedó vacío en la evidencia, compatible con detached HEAD del verificador;
3. faltó una carpeta separada de revisión estática, suplida por la revisión independiente posterior de ChatGPT sobre el diff real;
4. persisten trailing spaces exclusivamente documentales;
5. el reporte narrativo indicó un skip, pero el XML JUnit autoritativo confirmó 0 skips.

Estas observaciones no implican defecto funcional del backend ni requieren un R3.

## 7. Exclusiones preservadas

O-4 NO incluye:

- Android<->Cloud Sync / O-5;
- Outbox/Inbox cloud;
- INDIVIDUAL/GROUP/test-day;
- Livestock backend completo;
- Purchase/Logistics/Reception/Quality/Inventory posting;
- Web UI;
- deployment productivo/go-live.

## 8. Decisión de cierre

Por autorización expresa del usuario, O-4 queda CERRADO y CONGELADO sobre el HEAD técnico `dac40376ae8161d46e844b5f339cdc427923af8d`.

Este cierre:

- NO autoriza merge automático del PR #8;
- NO autoriza push directo a `main`;
- NO autoriza tag;
- NO autoriza force push ni rebase destructivo;
- NO autoriza iniciar O-5.

El merge y el inicio de cualquier corte posterior requieren autorización expresa separada del usuario.
