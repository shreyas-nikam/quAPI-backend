from app.services.user_services import *
from fastapi import APIRouter, Form
router = APIRouter()

@router.post("/add_user_to_project_waitlist")
async def add_user_to_project_waitlist_api(
    user_id: str = Form(...),
    user_email: str = Form(...), 
    project_id: str = Form(...),
    project_name: str = Form(...),
    date: str = Form(...),
):
    return await add_user_to_project_waitlist(user_id, user_email, project_id, project_name, date)
