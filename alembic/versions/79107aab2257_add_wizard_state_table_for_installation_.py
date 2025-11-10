"""add wizard_state table for installation wizard

Revision ID: 79107aab2257
Revises: 
Create Date: 2025-11-10 20:48:35.665989

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79107aab2257'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create wizard_state table for v1.0.0 Installation Wizard (Issue #163)"""
    op.create_table(
        'wizard_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED', name='wizardstatus'), nullable=False),
        sa.Column('current_step', sa.Enum('WELCOME', 'ADMIN_ACCOUNT', 'DIRECTORIES', 'API_CONFIG', 'VIDEO_IMPORT', 'COMPLETE', name='wizardstep'), nullable=False),
        sa.Column('welcome_completed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('admin_account_completed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('directories_completed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('api_config_completed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('video_import_completed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('config_data', sa.JSON(), nullable=True),
        sa.Column('import_job_id', sa.String(length=255), nullable=True),
        sa.Column('videos_imported', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('import_errors', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('last_step_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4'
    )

    # Create indexes for performance
    op.create_index('idx_wizard_status', 'wizard_state', ['status'], unique=False)
    op.create_index('idx_wizard_current_step', 'wizard_state', ['current_step'], unique=False)


def downgrade() -> None:
    """Drop wizard_state table"""
    op.drop_index('idx_wizard_current_step', table_name='wizard_state')
    op.drop_index('idx_wizard_status', table_name='wizard_state')
    op.drop_table('wizard_state')
