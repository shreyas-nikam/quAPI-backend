from app.services.podcast_design_services import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()

@router.post("/generate_podcast_outline")
async def generate_podcast_outline_api(files: Optional[List[UploadFile]] = File(None),
                                  instructions: str = Form(...)):
    return await generate_podcast_outline(files, instructions) 


@router.get("/podcasts")
async def podcasts_api():
    return await get_podcasts()

@router.post("/create_podcast")
async def create_podcast_api(podcast_name: str = Form(...),  podcast_description: str = Form(...), podcast_transcript: str = Form(...), files: Optional[List[UploadFile]] = File(None), podcast_image: UploadFile = File(...)):
    return await create_podcast(podcast_name, podcast_description, podcast_transcript, files, podcast_image)

@router.get("/get_podcast/{podcast_id}")
async def get_podcast_api(podcast_id: str):
    return await get_podcast(podcast_id)

@router.post("/delete_podcast")
async def delete_podcast_api(podcast_id: str = Form(...)):
    return await delete_podcast(podcast_id)

