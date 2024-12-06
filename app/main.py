from fastapi import FastAPI
from app.routes.example import router
from app.routes.course_design_routes import router as course_design_router
from app.routes.lecture_design_routes import router as lecture_design_router
from app.routes.lab_design_routes import router as lab_design_router
from app.routes.user_routes import router as user_router
from app.routes.writing_generation_routes import router as writing_generation_router
from fastapi.middleware.cors import CORSMiddleware
import logging
import marimo
from typing import Callable, Coroutine
from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
import os
import logging
from dotenv import load_dotenv
from fastapi import Form

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


logger = logging.getLogger("weasyprint")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.setLevel(logging.ERROR)

app = FastAPI()

ui_dir = os.path.join(os.path.dirname(__file__), "ui")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
server = marimo.create_asgi_app()
app_names: list[str] = []

for filename in sorted(os.listdir(ui_dir)):
    if filename.endswith(".py"):
        app_name = os.path.splitext(filename)[0]
        app_path = os.path.join(ui_dir, filename)
        server = server.with_app(path=f"/{app_name}", root=app_path)
        app_names.append(app_name)
# Set up Jinja2 templates
templates = Jinja2Templates(directory=templates_dir)


@app.get("/marimo-home/")
async def home(request: Request):
    return templates.TemplateResponse(
        "home.html", {"request": request, "app_names": app_names}
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTP error occurred: {exc.detail}")
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "detail": exc.detail},
        status_code=exc.status_code,
    )


# Add session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "your-secret-key")
)
app.mount("/marimo/", server.build())


# Allow CORS for the frontend
origins = [
    "*",  # React frontend URL
]

# add the frontend URL to the list of allowed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(router)
app.include_router(course_design_router)
app.include_router(lecture_design_router)
app.include_router(writing_generation_router)
app.include_router(user_router)
app.include_router(lab_design_router)
app.include_router(router)


@app.get("/")
async def read_root():
    return {"message": f"Hello, World!"}
