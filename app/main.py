from fastapi import FastAPI
from app.routes.example import router
from app.routes.course_design_routes import router as course_design_router
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/")
async def read_root():
    return {"message": f"Hello, World!"}
