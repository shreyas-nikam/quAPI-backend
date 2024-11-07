from fastapi import FastAPI
from app.routes.example import router
from app.routes.course_design_routes import router as course_design_router

app = FastAPI()

app.include_router(router)
app.include_router(course_design_router)

@app.get("/")
async def read_root():
    return {"message": f"Hello, World!"}
