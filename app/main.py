from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import os

from app.routers import project_selection, analyze, auth
from app.database import init_db, get_db
from app.core.config import get_settings
from app.core.sessions import SessionMiddleware
from sqlalchemy.orm import Session

settings = get_settings()

# Initialize database
init_db()

app = FastAPI(title="BCR Analysis")

# Add session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(project_selection.router, dependencies=[Depends(auth.require_login)])
app.include_router(analyze.router, dependencies=[Depends(auth.require_login)])

@app.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    from app.database import Project
    projects = db.query(Project).all()
    return templates.TemplateResponse("select/project_list.html", {
        "request": request,
        "projects": projects,
        "username": request.state.session.get("user")
    })
