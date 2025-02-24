from app.services.podcast_design_services import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()

@router.post("/generate_podcast_outline")
async def generate_podcast_outline_api(files: Optional[List[UploadFile]] = File(None),
                                  instructions: str = Form(...), 
                                  prompt: str = Form(...),
                                  ):
    return await generate_podcast_outline(files, instructions, prompt) 

@router.post("/generate_audio_for_podcast")
async def generate_audio_for_podcast_api(
    outline_text: str = Form(...),
    podcast_id: str = Form(...),
):
    return await generate_audio_for_podcast(outline_text)

@router.post("/podcasts")
async def podcasts_api(username: str = Form(...)):
    return await get_podcasts(username)

@router.post("/create_podcast")
async def create_podcast_api(username: str = Form(...), podcast_name: str = Form(...),  podcast_description: str = Form(...), podcast_transcript: str = Form(...), files: Optional[List[UploadFile]] = File(None), podcast_image: UploadFile = File(...)):
    return await create_podcast(username, podcast_name, podcast_description, podcast_transcript, files, podcast_image)

@router.get("/get_podcast/{podcast_id}")
async def get_podcast_api(podcast_id: str):
    return await get_podcast(podcast_id)

@router.post("/delete_podcast")
async def delete_podcast_api(podcast_id: str = Form(...)):
    return await delete_podcast(podcast_id)

@router.get("/podcast_prompt")
async def podcast_prompt_api():
    return await podcast_prompt()

@router.post("/update_podcast_info")
async def update_podcast_info_api(podcast_id: str = Form(...), podcast_name: str = Form(...),  podcast_description: str = Form(...)):
    return await update_podcast_info(podcast_id, podcast_name, podcast_description)