"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('superadmin','admin','employee', name='userrole'), nullable=False, server_default='employee'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('employee_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # employees
    op.create_table('employees',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('emp_code', sa.String(50), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('department', sa.String(100), nullable=True),
        sa.Column('designation', sa.String(100), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('date_joined', sa.DateTime(timezone=True), nullable=True),
        sa.Column('date_left', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_employees_emp_code', 'employees', ['emp_code'], unique=True)
    op.create_index('ix_employees_full_name', 'employees', ['full_name'])

    # Foreign key: users → employees
    op.create_foreign_key('fk_users_employee_id', 'users', 'employees', ['employee_id'], ['id'])

    # drives
    op.create_table('drives',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('drive_number', sa.String(50), nullable=False),
        sa.Column('capacity_gb', sa.Float(), nullable=False),
        sa.Column('used_gb', sa.Float(), server_default='0'),
        sa.Column('drive_type', sa.String(20), server_default='SAS'),
        sa.Column('filesystem', sa.String(20), server_default='NTFS'),
        sa.Column('status', sa.Enum('active','damaged','retired', name='drivestatus'), server_default='active'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('date_added', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_drives_drive_number', 'drives', ['drive_number'], unique=True)

    # shelf_locations
    op.create_table('shelf_locations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('drive_id', sa.Integer(), nullable=False),
        sa.Column('row_number', sa.String(20), nullable=False),
        sa.Column('shelf', sa.String(20), nullable=False),
        sa.Column('slot', sa.String(20), nullable=False),
        sa.Column('notes', sa.String(255), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['drive_id'], ['drives.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('drive_id')
    )

    # drive_employees
    op.create_table('drive_employees',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('drive_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('folder_path', sa.String(1024), nullable=True),
        sa.Column('total_files', sa.Integer(), server_default='0'),
        sa.Column('total_size_bytes', sa.BigInteger(), server_default='0'),
        sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['drive_id'], ['drives.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # file_index
    op.create_table('file_index',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('drive_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('file_name', sa.String(512), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('file_extension', sa.String(20), nullable=True),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('file_modified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('file_created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_directory', sa.Boolean(), server_default='false'),
        sa.Column('depth_level', sa.Integer(), server_default='0'),
        sa.Column('indexed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['drive_id'], ['drives.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_file_index_drive_id', 'file_index', ['drive_id'])
    op.create_index('ix_file_index_employee_id', 'file_index', ['employee_id'])
    op.create_index('ix_file_index_file_name', 'file_index', ['file_name'])
    op.create_index('ix_file_index_file_extension', 'file_index', ['file_extension'])

    # indexer_tokens
    op.create_table('indexer_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('token', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_indexer_tokens_token', 'indexer_tokens', ['token'], unique=True)

    # indexer_sessions
    op.create_table('indexer_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_key', sa.String(64), nullable=False),
        sa.Column('drive_id', sa.Integer(), nullable=False),
        sa.Column('token_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('running','completed','failed', name='sessionstatus'), server_default='running'),
        sa.Column('total_files', sa.Integer(), server_default='0'),
        sa.Column('total_size_bytes', sa.BigInteger(), server_default='0'),
        sa.Column('employees_data', sa.JSON(), nullable=True),
        sa.Column('error_log', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['drive_id'], ['drives.id']),
        sa.ForeignKeyConstraint(['token_id'], ['indexer_tokens.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_indexer_sessions_session_key', 'indexer_sessions', ['session_key'], unique=True)

    # retrieval_requests
    op.create_table('retrieval_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('requested_by_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('pending','approved','in_progress','completed','rejected', name='requeststatus'), server_default='pending'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('estimated_minutes', sa.Float(), nullable=True),
        sa.Column('file_ids', sa.JSON(), nullable=False),
        sa.Column('total_size_bytes', sa.BigInteger(), server_default='0'),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['requested_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # audit_log
    op.create_table('audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('audit_log')
    op.drop_table('retrieval_requests')
    op.drop_table('indexer_sessions')
    op.drop_table('indexer_tokens')
    op.drop_table('file_index')
    op.drop_table('drive_employees')
    op.drop_table('shelf_locations')
    op.drop_table('drives')
    op.drop_table('users')
    op.drop_table('employees')
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS drivestatus")
    op.execute("DROP TYPE IF EXISTS sessionstatus")
    op.execute("DROP TYPE IF EXISTS requeststatus")
