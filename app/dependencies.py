from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Generator, Optional

from .database import get_db, Project
from .services.ddl import load_project
from .schemas.project import Project as ProjectSchema


async def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    """Dependency to get a project by ID."""
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


async def get_project_data(project: Project = Depends(get_project)) -> tuple:
    """Dependency to load project data."""
    try:
        project_dict = {"vdj_path": project.vdj_path, "adata_path": project.adata_path}
        return await load_project(project_dict)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading project data: {str(e)}",
        )


def get_template_context(
    request,
    project: Project,
    project_id: int,
    script: Optional[str] = None,
    div: Optional[str] = None,
    active_tab: str = "graphs",
    **kwargs,
) -> dict:
    context = {
        "request": request,
        "project": project,
        "project_id": project_id,
        "active_tab": active_tab,
        **kwargs,
    }

    if script is not None:
        context["script"] = script
    if div is not None:
        context["div"] = div

    return context


def get_project(db: Session = Depends(get_db), project_id: int = None):
    """Get project by ID."""
    if project_id is None:
        return None
    return db.query(Project).filter(Project.project_id == project_id).first()


def get_project_or_404(db: Session = Depends(get_db), project_id: str = None):
    """Get project by ID or raise 404."""
    project = get_project(db, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project
