from scripts.identity_admin import build_parser


def test_identity_admin_cli_does_not_accept_password_arguments() -> None:
    parser = build_parser()
    create = parser.parse_args(
        [
            "create-user",
            "--login",
            "operator",
            "--display-name",
            "Operator",
        ]
    )
    assert create.command == "create-user"
    assert not hasattr(create, "password")


def test_identity_admin_cli_exposes_explicit_scope_for_roles() -> None:
    parser = build_parser()
    role = parser.parse_args(
        [
            "ensure-role",
            "--code",
            "tenant_admin",
            "--name",
            "Tenant Admin",
            "--scope",
            "TENANT",
        ]
    )
    assert role.scope == "TENANT"
