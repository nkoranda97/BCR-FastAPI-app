from datetime import date
import os
import shutil
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, Project
from app.services.ddl import preprocess
from app.services.file_handle import file_extraction

router = APIRouter(prefix="/select", tags=["project_selection"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/upload")
async def upload_form(request: Request):
    return templates.TemplateResponse("select/upload.html", {"request": request})


@router.post("/upload")
async def upload_project(
    request: Request,
    project_name: str = Form(...),
    author_name: str = Form(...),
    data_uploaded: str = Form(...),
    species: str = Form(...),
    zip_folder: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    current_date = date.today()
    project_folder = os.path.join("instance", "uploads", project_name)

    if not os.path.exists(project_folder):
        os.makedirs(project_folder)

    try:
        sample_folders = await file_extraction(
            files=[zip_folder],
            project_folder=project_folder,
            landing_page=str(request.url),
        )

        if data_uploaded == "Both":
            adata_path, vdj_path = await preprocess(
                project_folder, sample_folders, data_uploaded, species
            )

            # Create project in database
            db_project = Project(
                project_name=project_name,
                project_author=author_name,
                creation_date=current_date,
                directory_path=project_folder,
                vdj_path=vdj_path,
                adata_path=adata_path,
            )
            db.add(db_project)
            db.commit()

        elif data_uploaded == "VDJ":
            vdj_path = await preprocess(
                project_folder, sample_folders, data_uploaded, species
            )

            # Create project in database
            db_project = Project(
                project_name=project_name,
                project_author=author_name,
                creation_date=current_date,
                directory_path=project_folder,
                vdj_path=vdj_path,
                adata_path="NULL",
            )
            db.add(db_project)
            db.commit()

        return RedirectResponse(url="/select/project_list", status_code=303)

    except Exception as e:
        # Clean up project folder if it exists
        if os.path.exists(project_folder):
            shutil.rmtree(project_folder)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/project_list")
async def project_list(request: Request, db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    return templates.TemplateResponse(
        "select/project_list.html", {"request": request, "projects": projects}
    )


@router.post("/delete_project/{project_id}")
async def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.project_id == project_id).first()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    directory_path = project.directory_path

    if os.path.exists(directory_path):
        shutil.rmtree(directory_path)

    db.delete(project)
    db.commit()

    return RedirectResponse(url="/select/project_list", status_code=303)
