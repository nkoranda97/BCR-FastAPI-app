from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import os

from app.routers import project_selection, analyze
from app.database import init_db, get_db
from sqlalchemy.orm import Session

# Initialize database
init_db()

app = FastAPI(title="BCR Analysis")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(project_selection.router)
app.include_router(analyze.router)


@app.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    from app.database import Project

    projects = db.query(Project).all()
    return templates.TemplateResponse(
        "select/project_list.html", {"request": request, "projects": projects}
    )
