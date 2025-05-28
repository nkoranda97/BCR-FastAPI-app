from fastapi import APIRouter, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import HTTPException
from app.core.config import get_settings

settings = get_settings()
USERNAME = settings.login_username
PASSWORD = settings.login_password

router = APIRouter()


def require_login(request: Request):
    if not request.state.session.get("user"):
        raise HTTPException(status_code=307, headers={"Location": "/login"})


templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    error = request.query_params.get("error", "")
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": error}
    )


@router.post("/login")
def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == USERNAME and password == PASSWORD:
        request.state.session["user"] = username
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    else:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"},
            status_code=401,
        )


@router.get("/logout")
def logout(request: Request):
    request.state.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
