"""feedback — обращения с формы обратной связи

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('feedback',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('client_id', sa.String(length=64), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=120), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('plan', sa.String(length=20), nullable=True),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('page', sa.String(length=200), nullable=True),
    sa.Column('user_agent', sa.String(length=300), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('spam_reason', sa.String(length=40), nullable=True),
    sa.Column('admin_note', sa.Text(), nullable=True),
    sa.Column('forward_status', sa.String(length=20), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_feedback_client_id'), ['client_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_feedback_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_feedback_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_feedback_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_feedback_user_id'))
        batch_op.drop_index(batch_op.f('ix_feedback_status'))
        batch_op.drop_index(batch_op.f('ix_feedback_created_at'))
        batch_op.drop_index(batch_op.f('ix_feedback_client_id'))
    op.drop_table('feedback')
