"""roles

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07 21:30:00.000000

Roles are created without a password: they cannot log in by password until someone sets one
(see docs/plans/12-subir-postgres-vps-manual.md). An existing role is never touched, so a
password already set on the server survives.

The downgrade revokes every privilege granted here, including the default privileges, but does
not drop the roles: roles are global to the server and may hold privileges in other databases,
so DROP ROLE would fail.

Default privileges without FOR ROLE apply to objects created by the role that runs the
migrations, so migrations must always run with the same admin (DATABASE_URL_ADMIN).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("ingestor", "scientist", "scorer", "reader")
ALL_ROLES = ", ".join(ROLES)
SCHEMAS = ("raw", "ref", "features", "predictions", "monitoring")
ALL_SCHEMAS = ", ".join(SCHEMAS)
INGESTOR_SCHEMAS = "raw, ref"
SCORER_SCHEMAS = "predictions, monitoring"
FEATURES_READERS = "ingestor, scorer, reader"


def upgrade() -> None:
    """Upgrade schema."""
    for role in ROLES:
        op.execute(
            "DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
            f"CREATE ROLE {role} LOGIN; "
            "END IF; END $$"
        )
    op.execute(f"GRANT USAGE ON SCHEMA {ALL_SCHEMAS} TO {ALL_ROLES}")
    for schema in SCHEMAS:
        op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {ALL_ROLES}")
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {ALL_ROLES}"
        )
    for schemas, role in ((INGESTOR_SCHEMAS, "ingestor"), (SCORER_SCHEMAS, "scorer")):
        op.execute(f"GRANT INSERT, UPDATE ON ALL TABLES IN SCHEMA {schemas} TO {role}")
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schemas} GRANT INSERT, UPDATE ON TABLES TO {role}"
        )
    op.execute("GRANT CREATE ON SCHEMA features TO scientist")
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE scientist IN SCHEMA features "
        f"GRANT SELECT ON TABLES TO {FEATURES_READERS}"
    )


def downgrade() -> None:
    """Downgrade schema (revokes privileges; the roles are kept)."""
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE scientist IN SCHEMA features "
        f"REVOKE SELECT ON TABLES FROM {FEATURES_READERS}"
    )
    op.execute("REVOKE CREATE ON SCHEMA features FROM scientist")
    for schemas, role in ((SCORER_SCHEMAS, "scorer"), (INGESTOR_SCHEMAS, "ingestor")):
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schemas} "
            f"REVOKE INSERT, UPDATE ON TABLES FROM {role}"
        )
        op.execute(f"REVOKE INSERT, UPDATE ON ALL TABLES IN SCHEMA {schemas} FROM {role}")
    for schema in reversed(SCHEMAS):
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE SELECT ON TABLES FROM {ALL_ROLES}"
        )
        op.execute(f"REVOKE SELECT ON ALL TABLES IN SCHEMA {schema} FROM {ALL_ROLES}")
    op.execute(f"REVOKE USAGE ON SCHEMA {ALL_SCHEMAS} FROM {ALL_ROLES}")
