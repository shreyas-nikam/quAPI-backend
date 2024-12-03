from app.services.writing_generation_services import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()

@router.get("/writings")
async def writings_api():
    return await get_writings()

@router.get("/get_writing/{writing_id}")
async def get_writing_api(writing_id: str):
    return await get_writing(writing_id)

@router.post("/delete_writing")
async def delete_writing_api(writing_id: str = Form(...)):
    return await delete_writing(writing_id)

# generate markdown from files
@router.post("/writing_outline")
async def writing_outline_api(files: Optional[UploadFile] = File(None),
                                  instructions: str = Form(...),
                                  identifier: str = Form(...)):
    return await writing_outline(files, instructions, identifier) 

@router.post("/create_writing")
async def create_writing_api(writing_id: str = Form(...),
                             writing_name: str = Form(...),  
                             writing_description: str = Form(...), 
                             writing_outline: str = Form(...), 
                             files: List[UploadFile] = File(...), 
                             writing_image: UploadFile = File(...),
                             identifier: str = Form(...)):
    return await create_writing(writing_id=writing_id, 
                                writing_name=writing_name, 
                                writing_description=writing_description, 
                                writing_outline=writing_outline, 
                                files=files, 
                                writing_image=writing_image, 
                                identifier=identifier)

@router.post("/regenerate_outline")
async def regenerate_outline_api(assistant_id: str = Form(...)):
    return await regenerate_outline(assistant_id)


# convert file to pdf for selected template
@router.post("/convert_to_pdf")
async def convert_to_pdf_api(writing_id: str = Form(...), markdown: str = Form(...), template_name: str = Form(...)):
    return await convert_to_pdf(writing_id=writing_id, markdown=markdown, template_name=template_name)


@router.post("/add_resources_to_writing")
async def add_resources_to_writing_api(writing_id: str = Form(...), 
                                      resource_type: str = Form(...), 
                                      resource_name: str = Form(...), 
                                      resource_description: str = Form(...), 
                                      resource_file: Optional[UploadFile] = File(None) ):
    return await add_resources_to_writing(writing_id, resource_type, resource_name, resource_description, resource_file)

@router.post("/save_writing")
async def save_writing_api(writing_id: str = Form(...), 
                           writing_outline: str = Form(...)):
    return await save_writing(writing_id, writing_outline)