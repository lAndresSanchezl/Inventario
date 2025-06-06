"""Inicialización limpia

Revision ID: a0ebd304aafb
Revises: 
Create Date: 2025-04-15 12:20:51.539112

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a0ebd304aafb'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('producto', schema=None) as batch_op:
        batch_op.create_foreign_key(None, 'usuario', ['user_id'], ['id'])

    with op.batch_alter_table('usuario', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rol', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('foto_perfil', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('color_preferencia', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('avatar_clase', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('primary_color', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('secondary_color', sa.String(length=20), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('usuario', schema=None) as batch_op:
        batch_op.drop_column('secondary_color')
        batch_op.drop_column('primary_color')
        batch_op.drop_column('avatar_clase')
        batch_op.drop_column('color_preferencia')
        batch_op.drop_column('foto_perfil')
        batch_op.drop_column('rol')

    with op.batch_alter_table('producto', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')

    # ### end Alembic commands ###
