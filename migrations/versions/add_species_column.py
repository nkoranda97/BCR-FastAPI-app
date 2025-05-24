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
    # SQLite doesn't support ALTER TABLE ADD COLUMN with NOT NULL constraint
    # So we add it as nullable first
    op.add_column('projects', sa.Column('species', String(), nullable=True))
    # Set default value for existing rows
    op.execute("UPDATE projects SET species = 'human' WHERE species IS NULL")
    # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
    # This is a simplified version - in production you'd want to preserve all data
    op.create_table(
        'projects_new',
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('project_name', sa.String(), nullable=False),
        sa.Column('project_author', sa.String(), nullable=False),
        sa.Column('creation_date', sa.Date(), nullable=False),
        sa.Column('directory_path', sa.String(), nullable=False),
        sa.Column('vdj_path', sa.String(), nullable=True),
        sa.Column('adata_path', sa.String(), nullable=True),
        sa.Column('species', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('project_id'),
        sa.UniqueConstraint('project_name')
    )
    # Copy data to new table
    op.execute("""
        INSERT INTO projects_new 
        SELECT project_id, project_name, project_author, creation_date, 
               directory_path, vdj_path, adata_path, species 
        FROM projects
    """)
    # Drop old table and rename new one
    op.drop_table('projects')
    op.rename_table('projects_new', 'projects')


def downgrade():
    # Remove the species column
    op.drop_column('projects', 'species') 