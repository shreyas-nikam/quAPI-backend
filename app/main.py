# Standard library imports
import os
import logging
from pathlib import Path
import tempfile
from typing import Callable, Coroutine, Optional
from datetime import datetime

# Third-party imports
from fastapi import FastAPI, Request, Response, Depends, HTTPException, status, Form
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware
import marimo

# App-specific imports
from app.routes.course_design_routes import router as course_design_router
from app.routes.lecture_design_routes import router as lecture_design_router
from app.routes.lab_design_routes import router as lab_design_router
from app.routes.podcast_design_routes import router as podcast_design_router
from app.routes.user_routes import router as user_router
from app.routes.writing_generation_routes import router as writing_generation_router
from app.routes.template_design_routes import router as template_design_router
from app.routes.metaprompt_routes import router as meta_prompt_router
from app.websocket_manager import router as ws_router, start_redis_listener, redis_client


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

@app.on_event("startup")
def startup_event():
    start_redis_listener()  # Start listening to Redis in a background thread


# Add session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "your-secret-key")
)

# Example: Webhook for Airflow
class TaskCompletePayload(BaseModel):
    username: str
    creation_date: datetime
    type: str
    message: str
    read: bool
    module_id: Optional[str]
    project_id: str
    state: str
    

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


app.include_router(ws_router)
app.include_router(course_design_router)
app.include_router(lecture_design_router)
app.include_router(writing_generation_router)
app.include_router(user_router)
app.include_router(lab_design_router)
app.include_router(podcast_design_router)
app.include_router(template_design_router)
app.include_router(meta_prompt_router)

@app.get("/")
async def read_root():
    return {"message": f"Hello, World!"}



@app.post("/task-complete")
def task_complete(payload: TaskCompletePayload):
    """
    Airflow calls this endpoint with JSON like:
      {
        "type": "taskUpdate",
        "userId": "123",
        "taskId": "abc",
        "message": "Done"
      }

      OR for notifications:
      {
        "type": "notification",
        "userId": "123",
        "message": "Task abc completed successfully!"
      }
    """
    # Publish to Redis, websockets_manager will parse and broadcast
    redis_client.publish("task_updates", payload.json())
    return {"detail": "OK"}
