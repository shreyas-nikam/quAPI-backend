from app.services.metaprompt import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()


@router.post("/generate_prompt")
async def generate_prompt_api(prompt: str = Form(...)):
    return await generate_prompt(prompt) 