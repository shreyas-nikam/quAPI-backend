from fastapi import FastAPI
from app.routes.example import router
from app.routes.course_design_routes import router as course_design_router
from app.routes.lecture_design_routes import router as lecture_design_router
from app.routes.lab_design_routes import router as lab_design_router
from app.routes.user_routes import router as user_router
from app.routes.writing_generation_routes import router as writing_generation_router
from fastapi.middleware.cors import CORSMiddleware
import logging


logger = logging.getLogger("weasyprint")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.setLevel(logging.ERROR)

app = FastAPI()

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

@app.get("/")
async def read_root():
    return {"message": f"Hello, World!"}
