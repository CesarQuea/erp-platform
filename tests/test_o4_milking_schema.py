from __future__ import annotations

from sqlalchemy import CheckConstraint, Numeric

from app.infrastructure.database.milking_models import (
    MilkingAnnulmentRequestRecord,
    MilkingAuditEventRecord,
    MilkingConfigurationRecord,
    MilkingOutputProfileRecord,
    MilkingOutputRecord,
    MilkingSessionRecord,
)


def _column_names(record: type) -> set[str]:
    return {column.name for column in record.__table__.columns}


def _constraint_names(record: type) -> set[str]:
    return {constraint.name for constraint in record.__table__.constraints if constraint.name}


def _check_sql(record: type, name: str) -> str:
    for constraint in record.__table__.constraints:
        if isinstance(constraint, CheckConstraint) and constraint.name == name:
            return str(constraint.sqltext)
    raise AssertionError(f"missing check constraint {name}")


def test_o4_schema_contains_only_contractual_milking_tables() -> None:
    records = (
        MilkingOutputProfileRecord,
        MilkingConfigurationRecord,
        MilkingSessionRecord,
        MilkingOutputRecord,
        MilkingAnnulmentRequestRecord,
        MilkingAuditEventRecord,
    )
    assert {record.__tablename__ for record in records} == {
        "milking_output_profiles",
        "milking_configurations",
        "milking_sessions",
        "milking_outputs",
        "milking_annulment_requests",
        "milking_audit_events",
    }


def test_o4_schema_does_not_reintroduce_transversal_or_shadow_masters() -> None:
    records = (
        MilkingOutputProfileRecord,
        MilkingConfigurationRecord,
        MilkingSessionRecord,
        MilkingOutputRecord,
        MilkingAnnulmentRequestRecord,
        MilkingAuditEventRecord,
    )
    all_columns = set().union(*(_column_names(record) for record in records))
    forbidden_columns = {
        "organization_id",
        "site_id",
        "site_uuid",
        "operational_unit_id",
        "production_unit_id",
        "warehouse_id",
        "location_id",
    }
    assert all_columns.isdisjoint(forbidden_columns)


def test_farm_product_and_uom_are_external_uuid_references_not_shadow_tables() -> None:
    assert "farm_id" in _column_names(MilkingConfigurationRecord)
    assert "farm_id" in _column_names(MilkingSessionRecord)
    assert "farm_id" in _column_names(MilkingOutputRecord)
    assert "product_id" in _column_names(MilkingOutputProfileRecord)
    assert "quantity_uom_id" in _column_names(MilkingOutputProfileRecord)
    assert "product_id" in _column_names(MilkingSessionRecord)
    assert "quantity_uom_id" in _column_names(MilkingSessionRecord)


def test_configuration_is_unique_by_company_farm_shift() -> None:
    assert "uq_milking_configuration_company_farm_shift" in _constraint_names(
        MilkingConfigurationRecord
    )


def test_session_active_operational_identity_is_partial_unique_index() -> None:
    indexes = {index.name: index for index in MilkingSessionRecord.__table__.indexes}
    index = indexes["uq_milking_session_active_identity"]
    assert index.unique is True
    assert [column.name for column in index.columns] == [
        "company_id",
        "farm_id",
        "milking_date",
        "shift_code",
    ]
    predicate = str(index.dialect_options["postgresql"]["where"])
    assert "status <> 'CANCELLED'" in predicate


def test_output_is_zero_or_one_per_session_at_schema_level() -> None:
    assert "uq_milking_output_session" in _constraint_names(MilkingOutputRecord)
    assert "ck_milking_output_quantity_positive" in _constraint_names(MilkingOutputRecord)


def test_pending_annulment_is_unique_per_session() -> None:
    indexes = {index.name: index for index in MilkingAnnulmentRequestRecord.__table__.indexes}
    index = indexes["uq_milking_annulment_pending_session"]
    assert index.unique is True
    assert "state = 'PENDING'" in str(index.dialect_options["postgresql"]["where"])


def test_company_isolation_is_reinforced_by_same_company_foreign_keys() -> None:
    assert "fk_milking_configuration_profile_same_company" in _constraint_names(
        MilkingConfigurationRecord
    )
    assert "fk_milking_session_profile_same_company" in _constraint_names(MilkingSessionRecord)
    assert "fk_milking_output_session_same_company" in _constraint_names(MilkingOutputRecord)
    assert "fk_milking_annulment_session_same_company" in _constraint_names(
        MilkingAnnulmentRequestRecord
    )
    assert "fk_milking_audit_session_same_company" in _constraint_names(
        MilkingAuditEventRecord
    )


def test_milking_quantities_use_exact_numeric_not_float() -> None:
    session = MilkingSessionRecord.__table__.columns
    output = MilkingOutputRecord.__table__.columns
    for name in (
        "general_gross_quantity",
        "authoritative_gross_quantity",
        "used_on_farm_quantity",
        "discarded_quantity",
        "net_output_quantity",
    ):
        assert isinstance(session[name].type, Numeric)
    assert isinstance(output["quantity"].type, Numeric)


def test_session_schema_enforces_general_only_and_lifecycle_consistency() -> None:
    constraints = _constraint_names(MilkingSessionRecord)
    assert {
        "ck_milking_session_status",
        "ck_milking_session_general_only",
        "ck_milking_session_done_consistent",
        "ck_milking_session_cancelled_consistent",
        "ck_milking_session_draft_not_authoritative",
        "ck_milking_session_use_discard_within_general",
    } <= constraints

    done_sql = _check_sql(MilkingSessionRecord, "ck_milking_session_done_consistent")
    assert "general_gross_quantity IS NOT NULL" in done_sql
    assert "authoritative_gross_quantity = general_gross_quantity" in done_sql
    assert "reconciliation_status = 'NOT_REQUIRED'" in done_sql

    cancelled_sql = _check_sql(MilkingSessionRecord, "ck_milking_session_cancelled_consistent")
    assert "cancel_reason IS NOT NULL" in cancelled_sql
    assert "char_length(btrim(cancel_reason)) > 0" in cancelled_sql
