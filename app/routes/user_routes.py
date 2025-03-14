from app.services.user_services import *
from fastapi import APIRouter, Form
from typing import List, Optional
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

@router.get("/notifications/{username}")
async def fetch_notifications_api(username: str):
    return await fetch_notifications(username)

@router.post("/toggle_notification_status")
async def toggle_notification_status_api(notification_list: List[str] = Form(...)):
    return await toggle_notification_status(notification_list)

@router.post("/register_user")
async def register_user_api(username: str = Form(...), email: str = Form(...), firstName: str = Form(...), lastName: str = Form(...), phone: str = Form(...)):
    return await register_user(username, email, firstName, lastName, phone)

@router.get("/users")
async def fetch_users_api():
    return await fetch_users()

@router.post("/user")
async def fetch_user_api(username: str = Form(...)):
    return await fetch_user(username)

@router.post("/update_category")
async def update_category_api(username: str = Form(...), category: str = Form(...)):
    return await update_category(username, category)

@router.post("/quAPIVault")
async def fetch_quAPIVault_api(username: str = Form(...)):
    return await fetch_quAPIVault(username)