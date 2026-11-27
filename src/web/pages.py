"""Страница Jinja для работы через REST API."""

from pathlib import Path

from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

DIRECTORY = Path(__file__).parent
templates = Jinja2Templates(directory=DIRECTORY / "templates")
pages = APIRouter(include_in_schema=False)


@pages.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Открывает рабочее пространство администратора, организатора или гостя."""
    return templates.TemplateResponse(request=request, name="index.html")
