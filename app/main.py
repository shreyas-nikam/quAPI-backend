from fastapi import FastAPI
from app.routes.example import router
from app.routes.course_design_routes import router as course_design_router
from app.routes.lecture_design_routes import router as lecture_design_router
from app.routes.lab_design_routes import router as lab_design_router
from app.routes.podcast_design_routes import router as podcast_design_router
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
from pathlib import Path
import tempfile

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


logger = logging.getLogger("weasyprint")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.setLevel(logging.ERROR)
templates_dir = os.path.join(os.path.dirname(__file__), "templates")

app = FastAPI()

# Marimo server
server = marimo.create_asgi_app()
app_names: list[str] = []

# Path to the "ui" directory
notebooks_dir = Path(__file__).parent / "ui"
print(notebooks_dir)

# Iterate over Python files in the "ui" directory
for filename in sorted(notebooks_dir.iterdir()):
    if filename.suffix == ".py":  # Only process .py files
        app_name = filename.stem  # Extract app name (file name without extension)
        
        # Add the app to the server
        server = server.with_app(path=f"/{app_name}", root=filename)
        
        # Print the app details (corrected f-string syntax)
        print(f"Added app: {app_name} at path /{app_name} with root as {filename}")
        
        # Append the app name to the list
        app_names.append(app_name)


# Set up Jinja2 templates
templates = Jinja2Templates(directory=templates_dir)




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

@app.get("/marimo")
async def home(request: Request):
    return templates.TemplateResponse(
        "home.html", {"request": request, "app_names": app_names}
    )

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
app.include_router(podcast_design_router)


@app.get("/")
async def read_root():
    return {"message": f"Hello, World!"}
