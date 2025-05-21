from pydantic import BaseModel
from datetime import date
from typing import Optional


class ProjectBase(BaseModel):
    project_name: str
    project_author: str
    creation_date: date
    directory_path: str
    vdj_path: str
    adata_path: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class Project(ProjectBase):
    project_id: int

    class Config:
        from_attributes = True


class ProjectInDB(Project):
    pass
