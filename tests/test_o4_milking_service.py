from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.core.errors.models import PlatformError
from app.modules.milking.commands import (
    ConfirmMilkingSession,
    CreateMilkingSession,
    RequestMilkingAnnulment,
    SetMilkingGeneral,
    SetMilkingUseDiscard,
)
from app.modules.milking.configuration import MilkingConfiguration, MilkingOutputProfile
from app.modules.milking.domain import MilkingOutput, MilkingSession, MilkingSessionStatus
from app.modules.milking.service import (
    MilkingCommandApplicationService,
    PERM_CANCEL,
    PERM_CONFIRM,
    PERM_CREATE,
    PERM_UPDATE_DRAFT,
)
from app.platform.commands.model import CommandExecutionOutcome
from app.platform.identity.model import AuthenticatedPrincipal


CLIENT_AT = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
SERVER_AT = datetime(2026, 8, 25, 13, 0, tzinfo=UTC)
MILKING_DATE = date(2026, 8, 25)


class FixedClock:
    def now(self) -> datetime:
        return SERVER_AT


class DirectCommandExecution:
    def execute(self, request, payload, *, authorize, operation):
        authorize()
        return CommandExecutionOutcome(operation(), replayed=False)


class FakeMilkingRepository:
    def __init__(self, company_id: UUID, farm_id: UUID) -> None:
        self.company_id = company_id
        self.farm_id = farm_id
        self.profile = MilkingOutputProfile(
            profile_id=uuid4(),
            profile_version=1,
            company_id=company_id,
            product_id=uuid4(),
            quantity_uom_id=uuid4(),
            is_active=True,
            row_version=1,
            created_at=SERVER_AT,
            created_by=uuid4(),
        )
        self.configuration = MilkingConfiguration(
            id=uuid4(),
            company_id=company_id,
            farm_id=farm_id,
            shift_code="MORNING",
            output_profile_id=self.profile.profile_id,
            output_profile_version=self.profile.profile_version,
            is_active=True,
            version=1,
            created_at=SERVER_AT,
            created_by=uuid4(),
        )
        self.sessions: dict[UUID, MilkingSession] = {}
        self.outputs: dict[UUID, MilkingOutput] = {}
        self.pending_annulments: set[UUID] = set()
        self.audit_events: list[dict[str, object]] = []

    def get_output_profile(self, *, company_id, profile_id, profile_version):
        if (
            company_id == self.profile.company_id
            and profile_id == self.profile.profile_id
            and profile_version == self.profile.profile_version
        ):
            return self.profile
        return None

    def get_configuration(self, *, company_id, farm_id, shift_code):
        if (
            company_id == self.configuration.company_id
            and farm_id == self.configuration.farm_id
            and shift_code == self.configuration.shift_code
        ):
            return self.configuration
        return None

    def find_active_session_by_identity(
        self, *, company_id, farm_id, milking_date, shift_code
    ):
        for session in self.sessions.values():
            if (
                session.company_id == company_id
                and session.farm_id == farm_id
                and session.milking_date == milking_date
                and session.shift_code == shift_code
                and session.status is not MilkingSessionStatus.CANCELLED
            ):
                return session
        return None

    def insert_session(self, session):
        self.sessions[session.id] = session

    def get_session(self, *, company_id, session_id, for_update=False):
        session = self.sessions.get(session_id)
        if session is None or session.company_id != company_id:
            return None
        return session

    def update_session(self, session, *, expected_version):
        current = self.sessions.get(session.id)
        if current is None or current.version != expected_version:
            raise AssertionError("fake CAS conflict")
        self.sessions[session.id] = session
        return session.version

    def insert_output(self, output):
        if output.milking_session_id in self.outputs:
            raise AssertionError("duplicate output")
        self.outputs[output.milking_session_id] = output

    def get_output_for_session(self, *, company_id, session_id):
        output = self.outputs.get(session_id)
        if output is None or output.company_id != company_id:
            return None
        return output

    def has_pending_annulment(self, *, company_id, session_id):
        return session_id in self.pending_annulments

    def insert_annulment_request(
        self,
        *,
        request_id,
        company_id,
        session_id,
        reason,
        requested_by,
        client_occurred_at,
        recorded_at,
    ):
        self.pending_annulments.add(session_id)

    def insert_audit_event(self, **kwargs):
        self.audit_events.append(kwargs)


def principal(company_id: UUID, permissions: set[str] | None = None) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=uuid4(),
        company_id=company_id,
        effective_permissions=frozenset(
            permissions
            or {PERM_CREATE, PERM_UPDATE_DRAFT, PERM_CONFIRM, PERM_CANCEL}
        ),
    )


def service(repo: FakeMilkingRepository) -> MilkingCommandApplicationService:
    return MilkingCommandApplicationService(
        repo,
        DirectCommandExecution(),
        clock=FixedClock(),
    )


def create(repo: FakeMilkingRepository, actor: AuthenticatedPrincipal):
    return service(repo).create_session(
        CreateMilkingSession(
            command_id=uuid4(),
            farm_id=repo.farm_id,
            milking_date=MILKING_DATE,
            shift_code=" MORNING ",
            operator_id=uuid4(),
            client_occurred_at=CLIENT_AT,
            client_instance_id="android-A",
        ),
        principal=actor,
    )


def test_create_uses_company_context_and_snapshots_profile() -> None:
    company_id = uuid4()
    farm_id = uuid4()
    repo = FakeMilkingRepository(company_id, farm_id)
    actor = principal(company_id)

    outcome = create(repo, actor)
    session_id = UUID(outcome.result.data["session_id"])
    session = repo.sessions[session_id]

    assert session.company_id == company_id
    assert session.farm_id == farm_id
    assert session.shift_code == "MORNING"
    assert session.product_id == repo.profile.product_id
    assert session.quantity_uom_id == repo.profile.quantity_uom_id
    assert session.output_profile_id == repo.profile.profile_id
    assert session.created_by == actor.user_id
    assert session.created_at == SERVER_AT
    assert repo.audit_events[0]["client_occurred_at"] == CLIENT_AT
    assert repo.audit_events[0]["recorded_at"] == SERVER_AT


def test_create_requires_p3_permission() -> None:
    company_id = uuid4()
    repo = FakeMilkingRepository(company_id, uuid4())
    actor = principal(company_id, permissions={PERM_CONFIRM})

    with pytest.raises(PlatformError) as error:
        create(repo, actor)
    assert error.value.code == "ACCESS_DENIED"
    assert repo.sessions == {}


def test_general_use_discard_confirm_creates_exactly_one_output() -> None:
    company_id = uuid4()
    repo = FakeMilkingRepository(company_id, uuid4())
    actor = principal(company_id)
    app = service(repo)
    created = create(repo, actor)
    session_id = UUID(created.result.data["session_id"])

    app.set_general(
        SetMilkingGeneral(
            command_id=uuid4(),
            session_id=session_id,
            expected_version=1,
            general_gross_quantity=Decimal("100.50"),
            animals_milked_count=74,
            client_occurred_at=CLIENT_AT,
        ),
        principal=actor,
    )
    app.set_use_discard(
        SetMilkingUseDiscard(
            command_id=uuid4(),
            session_id=session_id,
            expected_version=2,
            used_on_farm_quantity=Decimal("8.00"),
            discarded_quantity=Decimal("1.50"),
            client_occurred_at=CLIENT_AT,
        ),
        principal=actor,
    )
    confirmed = app.confirm(
        ConfirmMilkingSession(
            command_id=uuid4(),
            session_id=session_id,
            expected_version=3,
            client_occurred_at=CLIENT_AT,
        ),
        principal=actor,
    )

    session = repo.sessions[session_id]
    assert session.status is MilkingSessionStatus.DONE
    assert session.net_output_quantity == Decimal("91.00")
    assert len(repo.outputs) == 1
    assert repo.outputs[session_id].quantity == Decimal("91.00")
    assert confirmed.result.data["output_id"] == str(repo.outputs[session_id].id)


def test_confirm_with_zero_net_creates_no_output() -> None:
    company_id = uuid4()
    repo = FakeMilkingRepository(company_id, uuid4())
    actor = principal(company_id)
    app = service(repo)
    session_id = UUID(create(repo, actor).result.data["session_id"])

    app.set_general(
        SetMilkingGeneral(
            command_id=uuid4(), session_id=session_id, expected_version=1,
            general_gross_quantity=Decimal("10"), animals_milked_count=None,
            client_occurred_at=CLIENT_AT,
        ), principal=actor,
    )
    app.set_use_discard(
        SetMilkingUseDiscard(
            command_id=uuid4(), session_id=session_id, expected_version=2,
            used_on_farm_quantity=Decimal("8"), discarded_quantity=Decimal("2"),
            client_occurred_at=CLIENT_AT,
        ), principal=actor,
    )
    outcome = app.confirm(
        ConfirmMilkingSession(
            command_id=uuid4(), session_id=session_id, expected_version=3,
            client_occurred_at=CLIENT_AT,
        ), principal=actor,
    )

    assert outcome.result.data["output_id"] is None
    assert repo.outputs == {}


def test_done_with_output_creates_pending_annulment_without_version_change() -> None:
    company_id = uuid4()
    repo = FakeMilkingRepository(company_id, uuid4())
    actor = principal(company_id)
    app = service(repo)
    session_id = UUID(create(repo, actor).result.data["session_id"])
    app.set_general(
        SetMilkingGeneral(
            command_id=uuid4(), session_id=session_id, expected_version=1,
            general_gross_quantity=Decimal("10"), animals_milked_count=None,
            client_occurred_at=CLIENT_AT,
        ), principal=actor,
    )
    app.set_use_discard(
        SetMilkingUseDiscard(
            command_id=uuid4(), session_id=session_id, expected_version=2,
            used_on_farm_quantity=Decimal("1"), discarded_quantity=Decimal("1"),
            client_occurred_at=CLIENT_AT,
        ), principal=actor,
    )
    app.confirm(
        ConfirmMilkingSession(
            command_id=uuid4(), session_id=session_id, expected_version=3,
            client_occurred_at=CLIENT_AT,
        ), principal=actor,
    )
    before_version = repo.sessions[session_id].version

    outcome = app.request_annulment(
        RequestMilkingAnnulment(
            command_id=uuid4(), session_id=session_id, expected_version=before_version,
            reason="Quality downstream review", client_occurred_at=CLIENT_AT,
        ), principal=actor,
    )

    assert repo.sessions[session_id].status is MilkingSessionStatus.DONE
    assert repo.sessions[session_id].version == before_version
    assert session_id in repo.pending_annulments
    assert outcome.result.data["version"] == before_version


def test_done_without_output_annuls_immediately_and_increments_version() -> None:
    company_id = uuid4()
    repo = FakeMilkingRepository(company_id, uuid4())
    actor = principal(company_id)
    app = service(repo)
    session_id = UUID(create(repo, actor).result.data["session_id"])
    app.set_general(
        SetMilkingGeneral(
            command_id=uuid4(), session_id=session_id, expected_version=1,
            general_gross_quantity=Decimal("10"), animals_milked_count=None,
            client_occurred_at=CLIENT_AT,
        ), principal=actor,
    )
    app.set_use_discard(
        SetMilkingUseDiscard(
            command_id=uuid4(), session_id=session_id, expected_version=2,
            used_on_farm_quantity=Decimal("10"), discarded_quantity=Decimal("0"),
            client_occurred_at=CLIENT_AT,
        ), principal=actor,
    )
    app.confirm(
        ConfirmMilkingSession(
            command_id=uuid4(), session_id=session_id, expected_version=3,
            client_occurred_at=CLIENT_AT,
        ), principal=actor,
    )
    assert repo.outputs == {}
    before = repo.sessions[session_id].version

    outcome = app.request_annulment(
        RequestMilkingAnnulment(
            command_id=uuid4(), session_id=session_id, expected_version=before,
            reason="Administrative annulment", client_occurred_at=CLIENT_AT,
        ), principal=actor,
    )

    assert repo.sessions[session_id].status is MilkingSessionStatus.CANCELLED
    assert repo.sessions[session_id].version == before + 1
    assert outcome.result.data["status"] == "CANCELLED"


def test_inactive_configuration_fails_closed_on_mutation() -> None:
    company_id = uuid4()
    repo = FakeMilkingRepository(company_id, uuid4())
    actor = principal(company_id)
    app = service(repo)
    session_id = UUID(create(repo, actor).result.data["session_id"])
    repo.configuration = replace(repo.configuration, is_active=False)

    with pytest.raises(PlatformError) as error:
        app.set_general(
            SetMilkingGeneral(
                command_id=uuid4(), session_id=session_id, expected_version=1,
                general_gross_quantity=Decimal("10"), animals_milked_count=None,
                client_occurred_at=CLIENT_AT,
            ), principal=actor,
        )
    assert error.value.code == "RESOURCE_NOT_AVAILABLE"
