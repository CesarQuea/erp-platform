from __future__ import annotations

import argparse
import getpass
import logging
from contextlib import contextmanager
from uuid import UUID

from app.bootstrap.identity_platform import build_identity_platform
from app.bootstrap.tenant_platform import build_tenant_platform
from app.core.config.settings import Settings, get_settings
from app.infrastructure.identity.migrations import PlatformMigrationRunner
from app.infrastructure.observability.logging import configure_logging
from app.platform.identity.model import RoleScope, UserStatus


logger = logging.getLogger(__name__)


def _uuid(value: str) -> UUID:
    return UUID(value)


@contextmanager
def _identity_runtime(settings: Settings):
    tenant_platform = build_tenant_platform(settings)
    identity_platform = None
    try:
        identity_platform = build_identity_platform(settings, tenant_platform)
        if identity_platform is None:
            raise SystemExit(
                "Identity runtime requires DATABASE_URL and JWT_SIGNING_SECRET."
            )
        yield identity_platform
    finally:
        if identity_platform is not None:
            identity_platform.dispose()
        tenant_platform.dispose()


def _read_new_password() -> str:
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match.")
    return first


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Internal ERP Platform identity administration."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate-platform")

    create = sub.add_parser("create-user")
    create.add_argument("--login", required=True)
    create.add_argument("--display-name", required=True)
    create.add_argument("--email")

    password = sub.add_parser("change-password")
    password.add_argument("--user-id", required=True, type=_uuid)

    status = sub.add_parser("set-user-status")
    status.add_argument("--user-id", required=True, type=_uuid)
    status.add_argument("--status", required=True, choices=[item.value for item in UserStatus])

    membership = sub.add_parser("grant-membership")
    membership.add_argument("--user-id", required=True, type=_uuid)
    membership.add_argument("--tenant-id", required=True, type=_uuid)

    revoke_membership = sub.add_parser("revoke-membership")
    revoke_membership.add_argument("--user-id", required=True, type=_uuid)
    revoke_membership.add_argument("--tenant-id", required=True, type=_uuid)

    company = sub.add_parser("grant-company-access")
    company.add_argument("--user-id", required=True, type=_uuid)
    company.add_argument("--tenant-id", required=True, type=_uuid)
    company.add_argument("--company-id", required=True, type=_uuid)

    revoke_company = sub.add_parser("revoke-company-access")
    revoke_company.add_argument("--user-id", required=True, type=_uuid)
    revoke_company.add_argument("--tenant-id", required=True, type=_uuid)
    revoke_company.add_argument("--company-id", required=True, type=_uuid)

    permission = sub.add_parser("ensure-permission")
    permission.add_argument("--code", required=True)
    permission.add_argument("--description")

    role = sub.add_parser("ensure-role")
    role.add_argument("--code", required=True)
    role.add_argument("--name", required=True)
    role.add_argument("--scope", required=True, choices=[item.value for item in RoleScope])

    role_permission = sub.add_parser("grant-role-permission")
    role_permission.add_argument("--role-id", required=True, type=_uuid)
    role_permission.add_argument("--permission-id", required=True, type=_uuid)

    assignment = sub.add_parser("assign-role")
    assignment.add_argument("--user-id", required=True, type=_uuid)
    assignment.add_argument("--role-id", required=True, type=_uuid)
    assignment.add_argument("--tenant-id", type=_uuid)
    assignment.add_argument("--company-id", type=_uuid)

    revoke_assignment = sub.add_parser("revoke-role-assignment")
    revoke_assignment.add_argument("--assignment-id", required=True, type=_uuid)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)

    if args.command == "migrate-platform":
        if not settings.database_url:
            raise SystemExit("DATABASE_URL is required.")
        runner = PlatformMigrationRunner()
        runner.upgrade(settings.database_url)
        revision = runner.current_revision(settings.database_url)
        logger.info("platform_identity_migration_completed")
        print(f"Platform schema revision: {revision}")
        return

    with _identity_runtime(settings) as runtime:
        service = runtime.provisioning
        if args.command == "create-user":
            user = service.create_user(
                login=args.login,
                password=_read_new_password(),
                display_name=args.display_name,
                email=args.email,
            )
            logger.info("identity_user_created", extra={"user_id": str(user.id)})
            print(f"Created user_id={user.id}")
        elif args.command == "change-password":
            service.change_password(args.user_id, new_password=_read_new_password())
            logger.info(
                "identity_password_changed_sessions_revoked",
                extra={"user_id": str(args.user_id)},
            )
            print("Password changed; active sessions revoked.")
        elif args.command == "set-user-status":
            service.set_user_status(args.user_id, UserStatus(args.status))
            logger.info(
                "identity_user_status_changed",
                extra={"user_id": str(args.user_id), "status": args.status},
            )
            print(f"User status={args.status}")
        elif args.command == "grant-membership":
            membership = service.grant_membership(args.user_id, args.tenant_id)
            logger.info(
                "membership_granted",
                extra={
                    "user_id": str(args.user_id),
                    "tenant_id": str(args.tenant_id),
                    "membership_id": str(membership.id),
                },
            )
            print(f"membership_id={membership.id}")
        elif args.command == "revoke-membership":
            service.revoke_membership(args.user_id, args.tenant_id)
            logger.info(
                "membership_revoked",
                extra={
                    "user_id": str(args.user_id),
                    "tenant_id": str(args.tenant_id),
                },
            )
            print("Membership revoked.")
        elif args.command == "grant-company-access":
            access = service.grant_company_access(
                args.user_id,
                args.tenant_id,
                args.company_id,
            )
            logger.info(
                "company_access_granted",
                extra={
                    "user_id": str(args.user_id),
                    "tenant_id": str(args.tenant_id),
                    "company_id": str(args.company_id),
                    "membership_id": str(access.membership_id),
                },
            )
            print(
                f"company_access membership_id={access.membership_id} "
                f"company_id={access.company_id}"
            )
        elif args.command == "revoke-company-access":
            service.revoke_company_access(
                args.user_id,
                args.tenant_id,
                args.company_id,
            )
            logger.info(
                "company_access_revoked",
                extra={
                    "user_id": str(args.user_id),
                    "tenant_id": str(args.tenant_id),
                    "company_id": str(args.company_id),
                },
            )
            print("Company access revoked.")
        elif args.command == "ensure-permission":
            permission = service.ensure_permission(
                args.code,
                description=args.description,
            )
            logger.info(
                "permission_ensured",
                extra={"permission_id": str(permission.id)},
            )
            print(f"permission_id={permission.id}")
        elif args.command == "ensure-role":
            role = service.ensure_role(
                args.code,
                name=args.name,
                scope=RoleScope(args.scope),
            )
            logger.info("role_ensured", extra={"role_id": str(role.id)})
            print(f"role_id={role.id}")
        elif args.command == "grant-role-permission":
            service.grant_permission_to_role(args.role_id, args.permission_id)
            logger.info(
                "role_permission_granted",
                extra={
                    "role_id": str(args.role_id),
                    "permission_id": str(args.permission_id),
                },
            )
            print("Permission granted to role.")
        elif args.command == "assign-role":
            assignment = service.assign_role(
                args.user_id,
                args.role_id,
                tenant_id=args.tenant_id,
                company_id=args.company_id,
            )
            logger.info(
                "role_assignment_granted",
                extra={
                    "user_id": str(args.user_id),
                    "role_id": str(args.role_id),
                    "assignment_id": str(assignment.id),
                    "tenant_id": str(args.tenant_id) if args.tenant_id else None,
                    "company_id": str(args.company_id) if args.company_id else None,
                },
            )
            print(f"assignment_id={assignment.id}")
        elif args.command == "revoke-role-assignment":
            service.revoke_role_assignment(args.assignment_id)
            logger.info(
                "role_assignment_revoked",
                extra={"assignment_id": str(args.assignment_id)},
            )
            print("Role assignment revoked.")
        else:
            raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
