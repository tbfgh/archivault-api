"""widen file_index.file_extension and drive_employees.folder_path

Root cause (production bug): file_index.file_extension was VARCHAR(20).
Real-world files — especially from game engine / third-party app data
folders on Windows — can have extensions well past 20 characters
(e.g. "hbakedphysicsmaterial" = 21, "hbakedmotionproperties" = 22).
A single oversized value in a bulk_save_objects() call failed the
entire indexer batch insert with StringDataRightTruncation.

file_extension -> VARCHAR(255): an extension can never be longer than
its containing file name, and NTFS caps a file name component at 255
UTF-16 code units, so 255 is a hard upper bound that can never
legitimately truncate, while still being narrow enough to stay a cheap
indexed column (file_extension is indexed for the file-search feature).

drive_employees.folder_path -> TEXT: same class of risk (long UNC /
deeply nested Windows paths) for the employee root-folder path
selected in the Indexer; converting to TEXT removes the cap entirely
since this column isn't indexed and unbounded is the safe default for
path-like data (file_index.file_path was already TEXT, this brings the
one path-like column in this migration's blast radius in line with it).

Revision ID: 0003_widen_file_cols
Revises: 0002_dept_batch_link
Create Date: 2026-08-01

"""
from alembic import op
import sqlalchemy as sa

revision = '0003_widen_file_cols'
down_revision = '0002_dept_batch_link'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "file_index", "file_extension",
        existing_type=sa.String(20),
        type_=sa.String(255),
        existing_nullable=True,
    )
    op.alter_column(
        "drive_employees", "folder_path",
        existing_type=sa.String(1024),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade():
    # NOTE: downgrading is lossy if any row was written with values that
    # exceed the narrower limit being restored here — Postgres will refuse
    # the ALTER (or truncate, depending on version/settings) rather than
    # silently succeed. Trim any offending rows before downgrading in a
    # database that has ingested post-fix data.
    op.alter_column(
        "drive_employees", "folder_path",
        existing_type=sa.Text(),
        type_=sa.String(1024),
        existing_nullable=True,
    )
    op.alter_column(
        "file_index", "file_extension",
        existing_type=sa.String(255),
        type_=sa.String(20),
        existing_nullable=True,
    )
