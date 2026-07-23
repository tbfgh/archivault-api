"""add departments, user_departments, employee.department_id, file_index.session_id

Revision ID: 0002_departments_and_batch_linking
Revises: 0001_initial
Create Date: 2026-07-04

"""
from alembic import op
import sqlalchemy as sa

revision = '0002_dept_batch_link'  # was '0002_departments_and_batch_linking' (34 chars, overflows VARCHAR(32))
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    # ── New tables ──────────────────────────────────────────────────────────
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "user_departments",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("department_id", sa.Integer, sa.ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
    )

    # ── New columns ─────────────────────────────────────────────────────────
    op.add_column("employees", sa.Column("department_id", sa.Integer, sa.ForeignKey("departments.id"), nullable=True))
    op.add_column("file_index", sa.Column("session_id", sa.Integer, sa.ForeignKey("indexer_sessions.id"), nullable=True))
    op.create_index("ix_file_index_session_id", "file_index", ["session_id"])
    op.create_index("ix_employees_department_id", "employees", ["department_id"])

    # ── Data backfill ───────────────────────────────────────────────────────
    conn = op.get_bind()

    # 1. Create a Department row for every distinct existing Employee.department string
    distinct_depts = conn.execute(sa.text(
        "SELECT DISTINCT department FROM employees WHERE department IS NOT NULL AND department != ''"
    )).fetchall()
    for (dept_name,) in distinct_depts:
        slug = dept_name.strip().lower().replace(" ", "-")
        conn.execute(
            sa.text(
                "INSERT INTO departments (name, slug) VALUES (:name, :slug) "
                "ON CONFLICT (slug) DO NOTHING"
            ),
            {"name": dept_name.strip(), "slug": slug},
        )

    # 2. Point each employee at its new department_id based on the old string value
    conn.execute(sa.text("""
        UPDATE employees e
        SET department_id = d.id
        FROM departments d
        WHERE e.department = d.name
    """))

    # 3. Preserve current behavior: admin-role users currently see all employees'
    #    data. Auto-assign every existing department to every existing admin so
    #    nothing breaks on deploy day — narrow access afterward via the new
    #    Departments admin screen. Superadmins are intentionally left out of
    #    user_departments; they bypass the filter entirely by role.
    conn.execute(sa.text("""
        INSERT INTO user_departments (user_id, department_id)
        SELECT u.id, d.id FROM users u, departments d WHERE u.role = 'admin'
        ON CONFLICT DO NOTHING
    """))

    # NOTE: employees.department (the legacy string column) is intentionally
    # kept in place as a fallback for this release. Drop it in a later
    # migration once department_id values have been verified in production.


def downgrade():
    op.drop_index("ix_employees_department_id", table_name="employees")
    op.drop_index("ix_file_index_session_id", table_name="file_index")
    op.drop_column("file_index", "session_id")
    op.drop_column("employees", "department_id")
    op.drop_table("user_departments")
    op.drop_table("departments")
