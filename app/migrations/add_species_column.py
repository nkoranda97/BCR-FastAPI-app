"""Add species column to projects table"""

from sqlalchemy import String
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_species_column'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add species column with a default value of 'human' for existing projects
    op.add_column('projects', sa.Column('species', String(), nullable=True))
    op.execute("UPDATE projects SET species = 'human' WHERE species IS NULL")
    # Make the column non-nullable after setting default values
    op.alter_column('projects', 'species', nullable=False)


def downgrade():
    op.drop_column('projects', 'species') 