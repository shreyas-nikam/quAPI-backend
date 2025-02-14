from app.services.writing_generation_services import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()

@router.post("/writings")
async def writings_api(username: str = Form(...)):
    return await get_writings(username)

@router.get("/get_writing/{writing_id}")
async def get_writing_api(writing_id: str):
    return await get_writing(writing_id)

@router.post("/delete_writing")
async def delete_writing_api(writing_id: str = Form(...)):
    return await delete_writing(writing_id)

@router.post("/delete_resources_from_writing")
async def delete_resources_from_writing_api(writing_id: str = Form(...),  resource_id: str = Form(...)):
    return await delete_resources_from_writing(writing_id, resource_id)

@router.post("/writing_outline")
async def writing_outline_api(files: Optional[List[UploadFile]] = File(None),
                                  instructions: str = Form(...),
                                  identifier: str = Form(...),
                                  use_metaprompt: Optional[bool] = Form(False)
                                  ):
    return await writing_outline(files, instructions, identifier, use_metaprompt) 

@router.post("/generate_templates")
async def generate_templates_api(files: Optional[List[UploadFile]] = File(None), 
                                 identifier: str = Form(...),
                                 target_audience: str = Form(...),
                                 tone: str = Form(...),
                                 expected_length: str = Form(...),
                                 use_metaprompt: Optional[bool] = Form(False)
                                ):
    return await generate_templates(files, identifier, target_audience, tone, expected_length, use_metaprompt)

@router.post("/create_writing")
async def create_writing_api(
        username: str = Form(...),
        writing_id: str = Form(...),
        writing_name: str = Form(...),  
        writing_description: str = Form(...), 
        writing_outline: str = Form(...), 
        files: Optional[List[UploadFile]] = File(None), 
        writing_image: UploadFile = File(...),
        identifier: str = Form(...)
    ):
    return await create_writing(
        username = username,
        writing_id=writing_id, 
        writing_name=writing_name, 
        writing_description=writing_description, 
        writing_outline=writing_outline, 
        files=files, 
        writing_image=writing_image, 
        identifier=identifier
    )

@router.post("/regenerate_outline")
async def regenerate_outline_api(
        writing_id: str = Form(...),
        instructions: str = Form(...),
        previous_outline: str = Form(...),
        selected_resources: str = Form(...),
        identifier: str = Form(...),
        use_metaprompt: Optional[bool] = Form(False)
    ):
    #TODO check implementation
    return await regenerate_outline(writing_id, instructions, previous_outline, selected_resources, identifier, use_metaprompt)


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
                           writing_outline: str = Form(...),
                            message: str = Form(...),
                            resources: str = Form(...)):
    return await save_writing(writing_id, writing_outline, message, resources)

@router.post("/rewrite_writing")
async def rewrite_writing_api(writing_input: str = Form(...)):
    return await rewrite_writing(writing_input)


@router.post("/create_rewriting")
async def create_rewriting_api(writing_name: str = Form(...), writing_description: str = Form(...)):
    return await create_rewriting_project(writing_name, writing_description)